from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.throttling import ScopedRateThrottle
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from .models import Booking
from .serializers import BookingSerializer, BookingCreateSerializer
from staff.permissions import is_platform_admin, check_staff_permission
from staff.models import Department

from core.pagination import StandardPageNumberPagination

class BookingPagination(StandardPageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

class BookingListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = BookingPagination

    def get_throttles(self):
        if self.request.method == 'POST':
            self.throttle_scope = 'booking_create'
        else:
            self.throttle_scope = None
        return super().get_throttles()

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return BookingCreateSerializer
        return BookingSerializer

    def get_queryset(self):
        user = self.request.user
        role = str(getattr(user, 'role', '')).upper()
        if is_platform_admin(user):
            base_qs = Booking.objects.all().order_by('-created_at')
        elif role == 'STAFF':
            profile = getattr(user, 'staff_profile', None)
            dept_code = profile.department.code if (profile and profile.department) else ''
            if Department.normalize_code(dept_code) == Department.CODE_RESERVATION or check_staff_permission(user, 'VIEW_BOOKINGS'):
                base_qs = Booking.objects.all().order_by('-created_at')
            else:
                return Booking.objects.none()
        elif role == 'HOTEL_STAFF':
            from hotels.models import HotelStaff
            staff_hotel_ids = HotelStaff.objects.filter(user=user).values_list('hotel_id', flat=True)
            base_qs = Booking.objects.filter(hotel_id__in=staff_hotel_ids).order_by('-created_at')
        elif role in ['HOTEL_OWNER', 'HOST', 'OWNER'] or (hasattr(user, 'hotels') and user.hotels.exists()):
            base_qs = Booking.objects.filter(hotel__owner=user).order_by('-created_at')
        else:
            base_qs = Booking.objects.filter(customer=user).order_by('-created_at')

        return base_qs.select_related(
            'customer', 'hotel', 'hotel__owner', 'room', 'room__hotel'
        ).prefetch_related(
            'payments', 'refunds',
            'hotel__images', 'hotel__amenities', 'hotel__rooms', 'hotel__verification_documents', 'hotel__reviews',
            'room__images', 'room__amenities', 'room__calendar_blocks'
        )

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        user_role = str(getattr(request.user, 'role', '')).upper()
        if user_role not in ['CUSTOMER', 'ADMIN', 'SUPER_ADMIN', 'GUEST']:
            return Response(
                {"error": "Only Customer accounts are allowed to make room reservations. Hotel Owners and Admins manage properties."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Early Occupancy Validation across all 3 parts (Adults, Children, Rooms)
        from util.validators import validate_occupancy
        try:
            cleaned_occ = validate_occupancy(
                adults=request.data.get('adults'),
                children=request.data.get('children'),
                rooms=request.data.get('number_of_rooms') or request.data.get('rooms', 1),
                total_guests=request.data.get('number_of_guests') or request.data.get('guests'),
                room=None
            )
            requested_rooms = cleaned_occ['rooms']
        except Exception as e:
            err_detail = getattr(e, 'detail', str(e))
            if isinstance(err_detail, dict):
                first_k = next(iter(err_detail))
                err_msg = str(err_detail[first_k][0] if isinstance(err_detail[first_k], list) else err_detail[first_k])
            elif isinstance(err_detail, list):
                err_msg = str(err_detail[0])
            else:
                err_msg = str(err_detail)
            return Response({"error": err_msg, "details": err_detail}, status=status.HTTP_400_BAD_REQUEST)

        # Concurrency & Overselling Prevention (select_for_update lock & global mutex)
        room_id = request.data.get('room') or request.data.get('room_id')
        check_in = request.data.get('check_in')
        check_out = request.data.get('check_out')

        from rooms.models import Room
        from rooms.utils import (
            auto_update_past_checkout_bookings, get_available_room_count,
            _ROOM_ALLOCATION_LOCK, get_payment_hold_duration, release_temporary_hold
        )
        from util.validators import parse_flexible_date

        cin = parse_flexible_date(check_in) if check_in else None
        cout = parse_flexible_date(check_out) if check_out else None

        with _ROOM_ALLOCATION_LOCK:
            # ---------------------------------------------------------------------
            # IDEMPOTENCY & PENDING BOOKING REUSE
            # Prevents duplicate bookings from browser refresh, network lag, or rapid clicks.
            # 1. If an explicit Idempotency-Key header is supplied, reuse matching booking.
            # 2. If the same guest already holds an active, unexpired PENDING_PAYMENT booking
            #    for this exact room and dates with the same room count, reuse and return it.
            # ---------------------------------------------------------------------
            idempotency_key = (
                request.headers.get('Idempotency-Key')
                or request.headers.get('X-Idempotency-Key')
                or request.data.get('idempotency_key')
            )
            if idempotency_key:
                idempotency_key = str(idempotency_key).strip()
                existing_by_key = Booking.objects.filter(
                    customer=request.user,
                    price_snapshot__idempotency_key=idempotency_key
                ).order_by('-created_at').first()

                if existing_by_key:
                    is_valid_replay = (
                        existing_by_key.booking_status == Booking.STATUS_CONFIRMED or (
                            existing_by_key.booking_status == Booking.STATUS_PENDING_PAYMENT and
                            existing_by_key.expires_at and existing_by_key.expires_at > timezone.now()
                        )
                    )
                    if is_valid_replay:
                        resp = Response(BookingSerializer(existing_by_key).data, status=status.HTTP_200_OK)
                        resp['X-Idempotent-Replay'] = 'true'
                        return resp

            # Check for active unexpired PENDING_PAYMENT booking for same customer, room, and dates
            if room_id and cin and cout:
                active_pending = Booking.objects.filter(
                    customer=request.user,
                    room_id=room_id,
                    check_in=cin,
                    check_out=cout,
                    booking_status=Booking.STATUS_PENDING_PAYMENT,
                    payment_status=Booking.PAYMENT_PENDING,
                    expires_at__gt=timezone.now()
                ).order_by('-created_at').first()

                if active_pending:
                    if active_pending.number_of_rooms == requested_rooms:
                        resp = Response(BookingSerializer(active_pending).data, status=status.HTTP_200_OK)
                        resp['X-Idempotent-Replay'] = 'true'
                        return resp
                    else:
                        # User requested different room count -> safely release old hold first
                        release_temporary_hold(active_pending, reason="REPLACED_BY_NEW_RESERVATION")

            if room_id:
                try:
                    # Lock the room inventory row during reservation
                    room_locked = Room.objects.select_for_update().get(id=room_id)
                except Room.DoesNotExist:
                    return Response({"error": "Room not found."}, status=status.HTTP_404_NOT_FOUND)

                if cin and cout and cout > cin:
                    auto_update_past_checkout_bookings()
                    # Escalate write lock in SQLite/PostgreSQL to prevent race condition during reservation
                    Room.objects.filter(id=room_locked.id).update(updated_at=timezone.now())

                    available_count = get_available_room_count(room_locked, cin, cout, include_holds=True)
                    all_nums = room_locked.get_all_room_numbers() if hasattr(room_locked, 'get_all_room_numbers') else []
                    total_units = len(all_nums) if all_nums else (getattr(room_locked, 'total_rooms', 1) or 1)

                    if requested_rooms > available_count:
                        return Response(
                            {
                                "success": False,
                                "code": "ROOMS_SOLD_OUT",
                                "message": "All rooms are booked for your selected dates. Please select different dates or another room category.",
                                "available_rooms": available_count,
                                "requested_rooms": requested_rooms,
                                # Backwards compatibility fields
                                "error": "All rooms are booked for your selected dates. Please select different dates or another room category.",
                                "available_count": available_count,
                                "total_units": total_units
                            },
                            status=status.HTTP_409_CONFLICT
                        )

            serializer = self.get_serializer(data=request.data, context={'request': request})
            serializer.is_valid(raise_exception=True)
            booking = serializer.save()

            # Save immutable price snapshot & set pending payment expiration timeout (15 mins)
            preferred_room = request.data.get('room_number') or getattr(booking, 'preferred_room_number', None)
            coupon_code_used = (
                getattr(booking, 'applied_coupon_code', None)
                or request.data.get('coupon_code')
                or request.data.get('coupon')
            )
            if coupon_code_used:
                coupon_code_used = str(coupon_code_used).strip().upper()

            booking.expires_at = timezone.now() + get_payment_hold_duration()
            booking.price_snapshot = {
                'idempotency_key': idempotency_key if idempotency_key else None,
                'price_per_night': float(booking.price_per_night),
                'number_of_nights': booking.number_of_nights,
                'number_of_rooms': booking.number_of_rooms,
                'subtotal': float(booking.subtotal),
                'cleaning_fee': float(booking.cleaning_fee),
                'service_fee': float(booking.service_fee),
                'taxes': float(booking.taxes),
                'discount': float(booking.discount),
                'coupon_code': coupon_code_used,
                'preferred_room_number': str(preferred_room).strip() if preferred_room else None,
                'allocated_room_number': None,
                'room_number': None,
                'meal_plan': booking.meal_plan,
                'total_amount': float(booking.total_amount),
                'currency': booking.currency,
                'created_at_timestamp': timezone.now().isoformat()
            }
            booking.save(update_fields=['expires_at', 'price_snapshot'])

            return Response(BookingSerializer(booking).data, status=status.HTTP_201_CREATED)


class BookingDetailView(generics.RetrieveAPIView):
    serializer_class = BookingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        lookup = self.kwargs.get('pk')
        qs = Booking.objects.select_related(
            'customer', 'hotel', 'hotel__owner', 'room', 'room__hotel'
        ).prefetch_related(
            'payments', 'refunds',
            'hotel__images', 'hotel__amenities', 'hotel__rooms', 'hotel__verification_documents', 'hotel__reviews',
            'room__images', 'room__amenities', 'room__calendar_blocks'
        )
        booking = None

        if str(lookup).isdigit():
            booking = qs.filter(pk=int(lookup)).first()
        
        if not booking:
            booking = qs.filter(booking_id=lookup).first()

        if not booking:
            from rest_framework.exceptions import NotFound
            raise NotFound("Booking receipt not found.")

        user = self.request.user
        role = str(getattr(user, 'role', '')).upper()
        is_reservation_staff = False
        if role == 'STAFF':
            profile = getattr(user, 'staff_profile', None)
            dept_code = profile.department.code if (profile and profile.department) else ''
            is_reservation_staff = bool(Department.normalize_code(dept_code) == Department.CODE_RESERVATION or check_staff_permission(user, 'VIEW_BOOKINGS'))

        is_admin = is_platform_admin(user) or is_reservation_staff
        is_owner = bool(booking.hotel and booking.hotel.owner == user)
        is_customer = (booking.customer == user)

        if not (is_customer or is_owner or is_admin):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You do not have permission to view this booking.")
        return booking


class BookingCancelView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _get_booking(self, pk, user):
        lookup = str(pk)
        booking = Booking.objects.filter(pk=int(lookup)).first() if lookup.isdigit() else Booking.objects.filter(booking_id=lookup).first()
        if not booking:
            return None, Response({"error": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)

        role = str(getattr(user, 'role', '')).upper()
        is_admin = is_platform_admin(user)
        is_owner = (booking.hotel.owner == user)
        is_customer = (booking.customer == user)

        if not (is_customer or is_owner or is_admin):
            return None, Response({
                "success": False,
                "error": "Permission denied. You cannot modify another user's booking."
            }, status=status.HTTP_403_FORBIDDEN)

        return booking, None

    def get(self, request, pk):
        """
        Preview cancellation fee, refund percentage, and time remaining before confirming.
        """
        booking, error_response = self._get_booking(pk, request.user)
        if error_response:
            return error_response

        from .cancellation import calculate_cancellation_details
        calc = calculate_cancellation_details(booking)

        captured_payment = booking.payments.filter(status='CAPTURED').first()
        is_paid = (booking.payment_status == Booking.PAYMENT_PAID) or bool(captured_payment)

        return Response({
            "booking_id": booking.booking_id,
            "hotel_name": booking.hotel.name,
            "room_title": booking.room.title if booking.room else 'Room',
            "guest_name": booking.guest_name,
            "check_in": str(booking.check_in),
            "check_out": str(booking.check_out),
            "check_in_time": getattr(booking.hotel, 'check_in_time', '12:00 PM'),
            "is_paid": is_paid,
            "can_cancel": booking.booking_status in [Booking.STATUS_CONFIRMED, Booking.STATUS_PENDING_PAYMENT],
            **calc
        }, status=status.HTTP_200_OK)

    def post(self, request, pk):
        """
        Execute cancellation applying the tiered policy slabs, or handle Hotel Owner Approval/Rejection.
        If booking is paid, queues the refund as REFUND_PENDING and notifies Admins to process.
        """
        booking, error_response = self._get_booking(pk, request.user)
        if error_response:
            return error_response

        user = request.user
        role = str(getattr(user, 'role', '')).upper()
        is_admin = is_platform_admin(user)
        is_owner = (booking.hotel.owner == user)

        action = (request.data.get('action') or '').strip().upper()

        # Handle Hotel Owner Approval / Rejection Workflow (TASK-11)
        if action == 'OWNER_APPROVE':
            if not (is_owner or is_admin):
                return Response({"error": "Only the hotel owner or administrator can approve cancellation requests."}, status=status.HTTP_403_FORBIDDEN)
            booking.booking_status = 'OWNER_APPROVED'
            booking.save(update_fields=['booking_status'])

            from notifications.utils import create_notification
            from notifications.models import Notification
            create_notification(
                recipient=booking.customer,
                title=f"✅ Cancellation Approved ({booking.booking_id})",
                message=f"The hotel owner has approved your cancellation request for booking {booking.booking_id}. Refund is being processed.",
                notification_type=Notification.TYPE_BOOKING_CANCELLED,
                booking=booking
            )
            return Response({
                "message": "Cancellation request approved successfully. Queued for refund disbursement.",
                "booking_id": booking.booking_id,
                "status": booking.booking_status,
                "action": "OWNER_APPROVE"
            }, status=status.HTTP_200_OK)

        elif action == 'OWNER_REJECT':
            if not (is_owner or is_admin):
                return Response({"error": "Only the hotel owner or administrator can reject cancellation requests."}, status=status.HTTP_403_FORBIDDEN)
            reason = (request.data.get('reason') or '').strip()
            if not reason:
                return Response({"error": "Rejection reason is required."}, status=status.HTTP_400_BAD_REQUEST)
            booking.booking_status = 'OWNER_REJECTED'
            booking.cancellation_reason = f"Owner Rejection: {reason}"
            booking.save(update_fields=['booking_status', 'cancellation_reason'])

            from notifications.utils import create_notification
            from notifications.models import Notification
            create_notification(
                recipient=booking.customer,
                title=f"❌ Cancellation Request Rejected ({booking.booking_id})",
                message=f"Your cancellation request for booking {booking.booking_id} was rejected by the hotel owner. Reason: {reason}",
                notification_type=Notification.TYPE_BOOKING_CANCELLED,
                booking=booking
            )
            return Response({
                "message": "Cancellation request rejected.",
                "booking_id": booking.booking_id,
                "status": booking.booking_status,
                "reason": reason,
                "action": "OWNER_REJECT"
            }, status=status.HTTP_200_OK)

        if booking.booking_status in [Booking.STATUS_CANCELLED, Booking.STATUS_REFUNDED]:
            return Response({"error": "Booking is already cancelled."}, status=status.HTTP_400_BAD_REQUEST)

        if booking.booking_status in [Booking.STATUS_CHECKED_OUT, Booking.STATUS_COMPLETED, Booking.STATUS_CHECKED_IN]:
            return Response({"error": "Cannot cancel a stay after check-in or check-out."}, status=status.HTTP_400_BAD_REQUEST)

        today = timezone.now().date()
        if booking.check_out <= today:
            return Response({"error": "Cannot cancel a stay on or after check-out date."}, status=status.HTTP_400_BAD_REQUEST)

        from .cancellation import calculate_cancellation_details
        from decimal import Decimal
        from django.contrib.auth import get_user_model
        from django.db.models import Q
        from payments.models import Payment, Refund
        from notifications.utils import create_notification
        from notifications.models import Notification

        calc = calculate_cancellation_details(booking)
        User = get_user_model()

        # Retrieve and validate customer payout details (support both flat and nested bank_details)
        from util.validators import validate_indian_bank_account, validate_indian_ifsc, validate_indian_upi
        bdetails = request.data.get('bank_details') if isinstance(request.data.get('bank_details'), dict) else {}
        raw_mode = (request.data.get('refund_mode') or bdetails.get('refund_mode') or '').strip().upper()
        raw_holder = (request.data.get('account_holder_name') or bdetails.get('account_holder_name') or request.data.get('account_holder') or '').strip()
        raw_bank = (request.data.get('bank_name') or bdetails.get('bank_name') or '').strip()
        raw_acc = (request.data.get('account_number') or bdetails.get('account_number') or '').strip()
        raw_confirm_acc = (request.data.get('confirm_account_number') or bdetails.get('confirm_account_number') or '').strip()
        raw_ifsc = (request.data.get('ifsc_code') or bdetails.get('ifsc_code') or '').strip().upper()
        raw_upi = (request.data.get('upi_id') or bdetails.get('upi_id') or '').strip().lower()

        if raw_confirm_acc and raw_acc and raw_confirm_acc != raw_acc:
            return Response({"error": "Account numbers do not match."}, status=status.HTTP_400_BAD_REQUEST)

        clean_acc = None
        clean_ifsc = None
        clean_upi = None
        refund_mode = Refund.REFUND_MODE_ORIGINAL

        if raw_acc or raw_ifsc:
            refund_mode = Refund.REFUND_MODE_BANK
            if raw_acc:
                clean_acc = validate_indian_bank_account(raw_acc)
            if raw_ifsc:
                clean_ifsc = validate_indian_ifsc(raw_ifsc)
        elif raw_upi:
            refund_mode = Refund.REFUND_MODE_UPI
            clean_upi = validate_indian_upi(raw_upi)
        elif raw_mode in [Refund.REFUND_MODE_BANK, Refund.REFUND_MODE_UPI, Refund.REFUND_MODE_ORIGINAL]:
            refund_mode = raw_mode

        if clean_acc or clean_upi:
            calc['customer_payout_details'] = {
                'refund_mode': refund_mode,
                'account_holder_name': raw_holder or booking.guest_name,
                'bank_name': raw_bank,
                'account_number_masked': f"{'*' * max(0, len(clean_acc) - 4)}{clean_acc[-4:]}" if clean_acc else None,
                'ifsc_code': clean_ifsc,
                'upi_id_masked': f"{clean_upi[:2]}***@{clean_upi.split('@')[-1]}" if clean_upi and '@' in clean_upi else clean_upi
            }

        booking.booking_status = Booking.STATUS_CANCELLED
        booking.cancelled_at = timezone.now()
        booking.cancellation_reason = request.data.get('reason', 'Guest requested cancellation')
        booking.cancellation_fee_percentage = Decimal(str(calc['cancellation_fee_percentage']))
        booking.cancellation_charge = Decimal(str(calc['cancellation_charge']))
        booking.refundable_amount = Decimal(str(calc['refundable_amount']))
        booking.cancellation_calculated_at = timezone.now()
        booking.applied_cancellation_policy = calc['policy_label']
        booking.cancellation_breakdown = calc

        captured_payment = booking.payments.filter(status=Payment.STATUS_CAPTURED).first()
        is_paid = (booking.payment_status == Booking.PAYMENT_PAID) or bool(captured_payment)

        if is_paid and Decimal(str(calc['refundable_amount'])) > Decimal('0.00'):
            booking.payment_status = Booking.PAYMENT_REFUND_PENDING

            # Queue a pending Refund record for Admin to approve & process via Razorpay / RazorpayX
            existing_refund = Refund.objects.filter(booking=booking).first()
            if not existing_refund:
                Refund.objects.create(
                    booking=booking,
                    payment=captured_payment if captured_payment else booking.payments.first(),
                    razorpay_payment_id=captured_payment.razorpay_payment_id if (captured_payment and captured_payment.razorpay_payment_id) else (booking.razorpay_order_id or "PENDING"),
                    razorpay_refund_id=None,
                    idempotency_key=f"ref_{booking.booking_id}",
                    amount=Decimal(str(calc['refundable_amount'])),
                    currency=booking.currency,
                    reason=booking.cancellation_reason,
                    status=Refund.STATUS_REFUND_PENDING,
                    refund_mode=refund_mode,
                    customer_account_holder=raw_holder or booking.guest_name,
                    customer_bank_name=raw_bank,
                    customer_account_number=clean_acc,
                    customer_ifsc_code=clean_ifsc,
                    customer_upi_id=clean_upi
                )
            else:
                existing_refund.amount = Decimal(str(calc['refundable_amount']))
                if existing_refund.status not in [Refund.STATUS_REFUNDED, 'PROCESSED']:
                    existing_refund.status = Refund.STATUS_REFUND_PENDING
                existing_refund.reason = booking.cancellation_reason
                existing_refund.refund_mode = refund_mode
                if clean_acc:
                    existing_refund.customer_account_number = clean_acc
                if clean_ifsc:
                    existing_refund.customer_ifsc_code = clean_ifsc
                if clean_upi:
                    existing_refund.customer_upi_id = clean_upi
                if raw_holder:
                    existing_refund.customer_account_holder = raw_holder
                if raw_bank:
                    existing_refund.customer_bank_name = raw_bank
                existing_refund.save()
            booking.save()
        elif is_paid and Decimal(str(calc['refundable_amount'])) == Decimal('0.00'):
            booking.payment_status = Booking.PAYMENT_REFUNDED
            booking.save()
        else:
            booking.payment_status = Booking.PAYMENT_FAILED
            booking.room_number = None
            booking.expires_at = timezone.now() - timedelta(seconds=1)
            booking.save()
            from rooms.utils import release_temporary_hold
            release_temporary_hold(booking, reason=booking.cancellation_reason, new_status=Booking.STATUS_CANCELLED)

        # TASK: Immediately reverse HostEarning and safely handle any pending HostPayout
        from payments.models import HostEarning, HostPayout
        earning = HostEarning.objects.filter(booking=booking).first()
        if earning:
            earning.status = HostEarning.STATUS_REVERSED
            earning.refund_amount = Decimal(str(calc['refundable_amount']))
            earning.hold_reason = "Booking cancelled by customer. Host payout eligibility excluded."
            if earning.payout and earning.payout.status in [HostPayout.STATUS_PENDING, HostPayout.STATUS_ELIGIBLE, HostPayout.STATUS_ON_HOLD]:
                payout = earning.payout
                earning.payout = None
                earning.save(update_fields=['status', 'refund_amount', 'hold_reason', 'payout', 'updated_at'])
                rem_total = sum(Decimal(str(e.net_amount)) for e in payout.earnings.exclude(id=earning.id))
                if rem_total <= 0:
                    payout.status = HostPayout.STATUS_FAILED
                    payout.save(update_fields=['status'])
                else:
                    payout.amount = rem_total
                    payout.save(update_fields=['amount'])
            else:
                earning.save(update_fields=['status', 'refund_amount', 'hold_reason', 'updated_at'])

        # 1. Live Notification directly to Hotel Owner for Review & Refund Processing
        create_notification(
            recipient=booking.hotel.owner,
            title=f"🔔 Guest Cancelled Stay - Refund Required ({booking.booking_id})",
            message=(
                f"Guest '{booking.guest_name}' has cancelled booking {booking.booking_id} at '{booking.hotel.name}'.\n"
                f"Check-in: {booking.check_in} (Remaining: {calc['hours_remaining']} hrs, {calc['policy_label']}).\n"
                f"Total Paid: ₹{calc['total_amount']} | Fee Retained ({calc['cancellation_fee_percentage']}%): ₹{calc['cancellation_charge']} | Refund Due ({calc['refund_percentage']}%): ₹{calc['refundable_amount']}.\n"
                f"Please review this request and click 'Refund' in your Host Dashboard (Bookings) to process payout via Razorpay."
            ),
            notification_type=Notification.TYPE_BOOKING_CANCELLED,
            booking=booking
        )

        # 2. Live Notification to Guest (Customer)
        create_notification(
            recipient=booking.customer,
            title=f"❌ Booking Cancelled ({booking.booking_id})",
            message=(
                f"Your reservation at {booking.hotel.name} has been cancelled successfully.\n"
                f"Cancellation charge ({calc['cancellation_fee_percentage']}%): ₹{calc['cancellation_charge']}.\n"
                + (f"A refund request of ₹{calc['refundable_amount']} ({calc['refund_percentage']}%) has been submitted to the Hotel Host for processing."
                   if calc['refundable_amount'] > 0 else "As per cancellation policy, 0% refund is applicable.")
            ),
            notification_type=Notification.TYPE_BOOKING_CANCELLED,
            booking=booking
        )

        # 3. Smart Notifications to Staff Departments (Reservation & Refunds)
        try:
            from staff.models import Department
            from staff.utils import create_staff_notification
            res_dept = Department.objects.filter(code=Department.CODE_RESERVATION).first()
            if res_dept:
                create_staff_notification(
                    department=res_dept,
                    title=f"Cancellation: Booking {booking.booking_id}",
                    message=f"Booking {booking.booking_id} at {booking.hotel.name} was cancelled by guest {booking.guest_name}.",
                    notification_type='BOOKING_CANCELLED',
                    metadata={'booking_id': booking.booking_id, 'hotel_id': booking.hotel_id}
                )
            if calc.get('refundable_amount', 0) > 0:
                ref_dept = Department.objects.filter(code=Department.CODE_REFUNDS_AND_CLAIMS).first()
                if ref_dept:
                    create_staff_notification(
                        department=ref_dept,
                        title=f"Refund Required: Booking {booking.booking_id}",
                        message=f"Refund of ₹{calc['refundable_amount']} required for cancelled reservation {booking.booking_id}.",
                        notification_type='REFUND_REQUESTED',
                        metadata={'booking_id': booking.booking_id, 'refundable_amount': str(calc['refundable_amount'])}
                    )
        except Exception as notif_err:
            pass

        return Response({
            "message": f"Booking {booking.booking_id} cancelled successfully. Refund request submitted to Hotel Owner.",
            "booking_id": booking.booking_id,
            "status": booking.booking_status,
            "payment_status": booking.payment_status,
            "refund_status": "PENDING" if is_paid and calc['refundable_amount'] > 0 else "NONE",
            **calc
        }, status=status.HTTP_200_OK)


class BookingOwnerApprovalView(APIView):
    """
    POST /api/bookings/{pk}/owner-approval/
    Hotel Owner approves or rejects a guest cancellation request for their property.
    Supports pk as numeric ID or booking_id string (e.g. KH-2026-748CB7).
    Accepts:
      - action: 'APPROVE' / 'OWNER_APPROVE'
      - action: 'REJECT' / 'OWNER_REJECT' (with 'reason')
    """
    permission_classes = [permissions.IsAuthenticated]

    def _get_booking(self, pk, user):
        lookup = str(pk).strip()
        booking = (
            (Booking.objects.select_related('hotel', 'hotel__owner', 'customer').filter(pk=int(lookup)).first() if lookup.isdigit() else None)
            or Booking.objects.select_related('hotel', 'hotel__owner', 'customer').filter(booking_id=lookup).first()
        )
        if not booking:
            return None, Response({"error": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)

        is_owner = bool(booking.hotel and booking.hotel.owner == user)
        is_admin = is_platform_admin(user)

        if not (is_owner or is_admin):
            return None, Response({
                "error": "Permission denied. Only the authorized hotel owner can approve or reject cancellation requests for this property."
            }, status=status.HTTP_403_FORBIDDEN)

        return booking, None

    def get(self, request, pk):
        booking, err = self._get_booking(pk, request.user)
        if err:
            return err

        from .cancellation import calculate_cancellation_details
        calc = calculate_cancellation_details(booking)

        return Response({
            "booking_id": booking.booking_id,
            "hotel_id": booking.hotel.id if booking.hotel else None,
            "hotel_name": booking.hotel.name if booking.hotel else '',
            "guest_name": booking.guest_name,
            "check_in": str(booking.check_in),
            "check_out": str(booking.check_out),
            "booking_status": booking.booking_status,
            "payment_status": booking.payment_status,
            "cancellation_reason": booking.cancellation_reason,
            "total_amount": float(booking.total_amount),
            "cancellation_fee": float(booking.cancellation_charge or calc.get('cancellation_charge', 0)),
            "refundable_amount": float(booking.refundable_amount or calc.get('refundable_amount', 0)),
            "can_decide": booking.booking_status in [Booking.STATUS_CANCELLED, Booking.STATUS_CANCELLATION_REQUESTED, 'CANCELLED', 'CANCELLATION_REQUESTED'],
            "cancellation_breakdown": booking.cancellation_breakdown or calc
        }, status=status.HTTP_200_OK)

    def post(self, request, pk):
        booking, err = self._get_booking(pk, request.user)
        if err:
            return err

        raw_action = (
            request.data.get('action') or
            request.data.get('decision') or
            request.data.get('status') or
            ''
        ).strip().upper()

        if raw_action in ['APPROVE', 'OWNER_APPROVE', 'APPROVED']:
            return self._handle_approval(request, booking)
        elif raw_action in ['REJECT', 'OWNER_REJECT', 'REJECTED']:
            return self._handle_rejection(request, booking)
        else:
            return Response({
                "error": "Invalid action. Expected 'action': 'APPROVE' or 'action': 'REJECT'."
            }, status=status.HTTP_400_BAD_REQUEST)

    def _handle_approval(self, request, booking):
        if booking.booking_status in [Booking.STATUS_REFUNDED, 'REFUNDED']:
            return Response({"error": "Booking is already refunded."}, status=status.HTTP_400_BAD_REQUEST)

        # Idempotent re-approval check
        if booking.booking_status in [Booking.STATUS_OWNER_APPROVED, 'OWNER_APPROVED']:
            return Response({
                "success": True,
                "message": "Cancellation request has already been approved. Forwarded to Admin for refund review.",
                "booking_id": booking.booking_id,
                "status": booking.booking_status,
                "booking_status": booking.booking_status,
                "action": "OWNER_APPROVE",
                "refundable_amount": float(booking.refundable_amount or 0),
                "cancellation_fee": float(booking.cancellation_charge or 0),
                "updated_at": booking.updated_at.isoformat() if booking.updated_at else timezone.now().isoformat()
            }, status=status.HTTP_200_OK)

        booking.booking_status = Booking.STATUS_OWNER_APPROVED
        booking.save(update_fields=['booking_status', 'updated_at'])

        # Ensure pending Refund record is active for Admin to review and process
        from payments.models import Payment, Refund
        captured_payment = booking.payments.filter(status=Payment.STATUS_CAPTURED).first()
        is_paid = (booking.payment_status == Booking.PAYMENT_PAID) or bool(captured_payment)

        if is_paid and booking.refundable_amount and booking.refundable_amount > 0:
            existing_refund = Refund.objects.filter(booking=booking).first()
            if not existing_refund:
                Refund.objects.create(
                    booking=booking,
                    payment=captured_payment if captured_payment else booking.payments.first(),
                    razorpay_payment_id=captured_payment.razorpay_payment_id if (captured_payment and captured_payment.razorpay_payment_id) else (booking.razorpay_order_id or "PENDING"),
                    razorpay_refund_id=None,
                    idempotency_key=f"ref_{booking.booking_id}",
                    amount=booking.refundable_amount,
                    currency=booking.currency,
                    reason=booking.cancellation_reason or "Customer cancellation approved by Hotel Owner",
                    status=Refund.STATUS_REFUND_PENDING,
                    refund_mode=Refund.REFUND_MODE_ORIGINAL
                )
            elif existing_refund.status not in [Refund.STATUS_REFUNDED, 'PROCESSED']:
                existing_refund.status = Refund.STATUS_REFUND_PENDING
                existing_refund.amount = booking.refundable_amount
                existing_refund.save(update_fields=['status', 'amount', 'updated_at'])

        # Notifications
        from notifications.utils import create_notification
        from notifications.models import Notification
        create_notification(
            recipient=booking.customer,
            title=f"✅ Cancellation Approved ({booking.booking_id})",
            message=f"The hotel owner has approved your cancellation request for booking {booking.booking_id}. Refund is being processed by administration.",
            notification_type=Notification.TYPE_BOOKING_CANCELLED,
            booking=booking
        )

        # Notify Refunds Staff / Admin
        try:
            from staff.models import Department
            from staff.utils import create_staff_notification
            ref_dept = Department.objects.filter(code=Department.CODE_REFUNDS_AND_CLAIMS).first()
            if ref_dept:
                create_staff_notification(
                    department=ref_dept,
                    title=f"Cancellation Approved: {booking.booking_id}",
                    message=f"Hotel Owner approved cancellation for {booking.booking_id}. Refund of ₹{booking.refundable_amount or 0} requires admin processing.",
                    notification_type='REFUND_PENDING',
                    metadata={'booking_id': booking.booking_id, 'refundable_amount': str(booking.refundable_amount or 0)}
                )
        except Exception:
            pass

        return Response({
            "success": True,
            "message": "Cancellation request approved successfully. Forwarded to Admin for refund review.",
            "booking_id": booking.booking_id,
            "status": booking.booking_status,
            "booking_status": booking.booking_status,
            "action": "OWNER_APPROVE",
            "decision": "APPROVE",
            "refundable_amount": float(booking.refundable_amount or 0),
            "cancellation_fee": float(booking.cancellation_charge or 0),
            "updated_at": booking.updated_at.isoformat() if booking.updated_at else timezone.now().isoformat()
        }, status=status.HTTP_200_OK)

    def _handle_rejection(self, request, booking):
        reason = (
            request.data.get('reason') or
            request.data.get('rejection_reason') or
            request.data.get('notes') or
            ''
        ).strip()
        if not reason:
            return Response({"error": "Rejection reason is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Idempotent re-rejection check
        if booking.booking_status in [Booking.STATUS_OWNER_REJECTED, 'OWNER_REJECTED']:
            return Response({
                "success": True,
                "message": "Cancellation request has already been rejected.",
                "booking_id": booking.booking_id,
                "status": booking.booking_status,
                "booking_status": booking.booking_status,
                "action": "OWNER_REJECT",
                "reason": booking.cancellation_reason,
                "updated_at": booking.updated_at.isoformat() if booking.updated_at else timezone.now().isoformat()
            }, status=status.HTTP_200_OK)

        booking.booking_status = Booking.STATUS_OWNER_REJECTED
        booking.cancellation_reason = f"Owner Rejection: {reason}"
        booking.save(update_fields=['booking_status', 'cancellation_reason', 'updated_at'])

        # Update any pending refund record
        from payments.models import Refund
        Refund.objects.filter(booking=booking, status=Refund.STATUS_REFUND_PENDING).update(
            status=Refund.STATUS_REFUND_FAILED,
            failure_reason=f"Hotel Owner rejected cancellation: {reason}"
        )

        from notifications.utils import create_notification
        from notifications.models import Notification
        create_notification(
            recipient=booking.customer,
            title=f"❌ Cancellation Request Rejected ({booking.booking_id})",
            message=f"Your cancellation request for booking {booking.booking_id} was rejected by the hotel owner. Reason: {reason}",
            notification_type=Notification.TYPE_BOOKING_CANCELLED,
            booking=booking
        )

        return Response({
            "success": True,
            "message": "Cancellation request rejected.",
            "booking_id": booking.booking_id,
            "status": booking.booking_status,
            "booking_status": booking.booking_status,
            "reason": reason,
            "action": "OWNER_REJECT",
            "decision": "REJECT",
            "updated_at": booking.updated_at.isoformat() if booking.updated_at else timezone.now().isoformat()
        }, status=status.HTTP_200_OK)


def is_authorized_hotel_staff_or_owner_or_admin(user, hotel, permission_field='can_checkin_checkout'):
    """
    Enforces property-level multi-tenant authorization for hotel operational actions.
    Returns True if:
    1. User is Django superuser or is_staff
    2. User role is ADMIN or SUPER_ADMIN
    3. User is the verified Owner of this specific hotel (hotel.owner == user)
    4. User has role HOTEL_STAFF AND is explicitly registered in HotelStaff for THIS hotel
       (with permission_field enabled if specified).
    Returns False otherwise.
    """
    if not (user and user.is_authenticated):
        return False
    if is_platform_admin(user):
        return True
    user_role = str(getattr(user, 'role', '')).upper()
    if user_role == 'STAFF':
        profile = getattr(user, 'staff_profile', None)
        if not (profile and profile.is_active_account):
            return False
        dept_code = profile.department.code if (profile and profile.department) else ''
        if Department.normalize_code(dept_code) == Department.CODE_RESERVATION:
            return bool(profile.has_perm('CHECKIN_GUEST') or profile.has_perm('CHECKOUT_GUEST') or profile.has_perm('MANAGE_RESERVATIONS') or profile.has_perm('EDIT_BOOKINGS'))
        return False
    if hotel.owner == user:
        return True
    if user_role == 'HOTEL_STAFF':
        from hotels.models import HotelStaff
        staff_qs = HotelStaff.objects.filter(hotel=hotel, user=user)
        if permission_field:
            staff_qs = staff_qs.filter(**{permission_field: True})
        return staff_qs.exists()
    return False


class StaffCheckInView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        lookup = str(pk)
        booking = Booking.objects.filter(pk=int(lookup)).first() if lookup.isdigit() else Booking.objects.filter(booking_id=lookup).first()

        if not booking:
            return Response({"error": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)

        if not is_authorized_hotel_staff_or_owner_or_admin(request.user, booking.hotel, permission_field='can_checkin_checkout'):
            return Response({
                "error": "Permission denied to perform check-in. You must be an authorized staff member or owner of this hotel."
            }, status=status.HTTP_403_FORBIDDEN)

        booking.booking_status = Booking.STATUS_CHECKED_IN
        booking.actual_check_in_at = timezone.now()
        booking.action_by_staff = request.user
        booking.save()

        # Push Notification for Guest
        from notifications.utils import create_notification
        from notifications.models import Notification
        create_notification(
            recipient=booking.customer,
            title=f"🔑 Checked In: {booking.hotel.name}",
            message=f"Welcome! You have been successfully checked in to Room {booking.room_number or booking.room.title}. Enjoy your stay!",
            notification_type=Notification.TYPE_CHECKED_IN,
            booking=booking
        )

        return Response({
            "message": f"Guest {booking.guest_name} checked in successfully for Booking {booking.booking_id}.",
            "status": booking.booking_status,
            "actual_check_in_at": booking.actual_check_in_at
        }, status=status.HTTP_200_OK)


class StaffCheckOutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        lookup = str(pk)
        booking = Booking.objects.filter(pk=int(lookup)).first() if lookup.isdigit() else Booking.objects.filter(booking_id=lookup).first()

        if not booking:
            return Response({"error": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)

        if not is_authorized_hotel_staff_or_owner_or_admin(request.user, booking.hotel, permission_field='can_checkin_checkout'):
            return Response({
                "error": "Permission denied to perform check-out. You must be an authorized staff member or owner of this hotel."
            }, status=status.HTTP_403_FORBIDDEN)

        booking.booking_status = Booking.STATUS_CHECKED_OUT
        booking.actual_check_out_at = timezone.now()
        booking.action_by_staff = request.user
        booking.save()

        # Push Notification for Guest
        from notifications.utils import create_notification
        from notifications.models import Notification
        create_notification(
            recipient=booking.customer,
            title=f"👋 Check-Out Complete: {booking.hotel.name}",
            message=f"Thank you for staying at {booking.hotel.name}! Your check-out for booking {booking.booking_id} is completed. Please rate your stay.",
            notification_type=Notification.TYPE_CHECKED_OUT,
            booking=booking
        )

        return Response({
            "message": f"Booking {booking.booking_id} completed check-out successfully.",
            "status": booking.booking_status,
            "actual_check_out_at": booking.actual_check_out_at
        }, status=status.HTTP_200_OK)


class StaffNoShowView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        lookup = str(pk)
        booking = Booking.objects.filter(pk=int(lookup)).first() if lookup.isdigit() else Booking.objects.filter(booking_id=lookup).first()

        if not booking:
            return Response({"error": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)

        if not is_authorized_hotel_staff_or_owner_or_admin(request.user, booking.hotel, permission_field='can_checkin_checkout'):
            return Response({
                "error": "Permission denied to mark no-show. You must be an authorized staff member or owner of this hotel."
            }, status=status.HTTP_403_FORBIDDEN)

        booking.booking_status = Booking.STATUS_NO_SHOW
        booking.action_by_staff = request.user
        booking.save()

        return Response({
            "message": f"Booking {booking.booking_id} marked as NO_SHOW.",
            "status": booking.booking_status
        }, status=status.HTTP_200_OK)


class ResendBookingConfirmationEmailView(APIView):
    """
    Allows the customer, hotel host/staff, or administrator to trigger
    a safe retry or manual resend of the booking confirmation email with PDF voucher attached.
    """
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'email_resend'

    def post(self, request, pk):
        lookup = str(pk)
        booking = Booking.objects.filter(pk=int(lookup)).first() if lookup.isdigit() else Booking.objects.filter(booking_id=lookup).first()

        if not booking:
            return Response({"error": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)

        # Check permissions: Booking owner, hotel owner, or authorized staff/admin
        is_owner = request.user == booking.customer
        is_authorized_staff = is_authorized_hotel_staff_or_owner_or_admin(request.user, booking.hotel, permission_field='can_manage_bookings')
        is_admin = is_platform_admin(request.user)

        if not (is_owner or is_authorized_staff or is_admin):
            return Response({"error": "You do not have permission to resend confirmation for this booking."}, status=status.HTTP_403_FORBIDDEN)

        # Duplicate-send cooldown protection: prevent repeated clicks within 60 seconds
        cache_key = f"email_resend_cooldown_{booking.id}"
        if cache.get(cache_key) and not is_admin:
            return Response({
                "error": "A confirmation email was recently dispatched. Please wait at least 60 seconds before requesting another email."
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)

        if booking.booking_status not in [Booking.STATUS_CONFIRMED, Booking.STATUS_CHECKED_IN, Booking.STATUS_CHECKED_OUT, Booking.STATUS_COMPLETED]:
            return Response({
                "error": f"Cannot send confirmation email for booking with status '{booking.booking_status}'. Only confirmed bookings can receive vouchers."
            }, status=status.HTTP_400_BAD_REQUEST)

        from services.booking_email_service import send_booking_confirmation_email
        result = send_booking_confirmation_email(booking, force_retry=True)

        if result.get("success"):
            cache.set(cache_key, True, timeout=60)
            return Response({
                "status": "success",
                "message": f"Booking confirmation email with PDF invoice dispatched successfully to {result.get('recipient')}.",
                "recipient": result.get('recipient'),
                "booking_id": booking.booking_id
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                "status": "failed",
                "error": result.get("error") or "Failed to deliver confirmation email.",
                "booking_id": booking.booking_id
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BookingInvoiceDownloadView(APIView):
    """
    Downloads the official PDF Tax Invoice / Booking Bill / Receipt.
    Room number is clearly stated on the bill after successful payment.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        lookup = str(pk)
        booking = Booking.objects.filter(pk=int(lookup)).first() if lookup.isdigit() else Booking.objects.filter(booking_id=lookup).first()
        if not booking:
            return Response({"error": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)

        role = str(getattr(request.user, 'role', '')).upper()
        is_owner = (request.user == booking.customer)
        is_host = (request.user == booking.hotel.owner)
        is_res_staff = False
        if role == 'STAFF':
            profile = getattr(request.user, 'staff_profile', None)
            dept_code = profile.department.code if (profile and profile.department) else ''
            is_res_staff = bool(Department.normalize_code(dept_code) == Department.CODE_RESERVATION or check_staff_permission(request.user, 'VIEW_BOOKINGS'))
        is_staff = is_platform_admin(request.user) or is_res_staff or role == 'HOTEL_STAFF'

        if not (is_owner or is_host or is_staff):
            return Response({"error": "You do not have permission to view or download this invoice."}, status=status.HTTP_403_FORBIDDEN)

        if booking.payment_status != Booking.PAYMENT_PAID and booking.booking_status != Booking.STATUS_CONFIRMED:
            return Response({
                "error": "Invoice and room allocation receipt are only generated after successful payment."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Ensure room is allocated if not already set
        if not booking.room_number:
            from rooms.utils import allocate_room_number_for_booking
            allocate_room_number_for_booking(booking)

        from services.booking_email_service import generate_booking_confirmation_pdf
        from django.http import HttpResponse

        pdf_bytes = generate_booking_confirmation_pdf(booking)
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        filename = f"Invoice_{booking.booking_id}.pdf"
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response


