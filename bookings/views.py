from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from .models import Booking
from .serializers import BookingSerializer, BookingCreateSerializer

class BookingPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 1000

class BookingListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = BookingPagination

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return BookingCreateSerializer
        return BookingSerializer

    def get_queryset(self):
        user = self.request.user
        role = str(getattr(user, 'role', '')).upper()
        if user.is_staff or user.is_superuser or role in ['ADMIN', 'SUPER_ADMIN', 'SUPPORT_AGENT']:
            return Booking.objects.all().order_by('-created_at')
        elif role == 'HOTEL_STAFF':
            from hotels.models import HotelStaff
            staff_hotel_ids = HotelStaff.objects.filter(user=user).values_list('hotel_id', flat=True)
            return Booking.objects.filter(hotel_id__in=staff_hotel_ids).order_by('-created_at')
        elif role in ['HOTEL_OWNER', 'HOST', 'OWNER'] or (hasattr(user, 'hotels') and user.hotels.exists()):
            return Booking.objects.filter(hotel__owner=user).order_by('-created_at')
        return Booking.objects.filter(customer=user).order_by('-created_at')

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        user_role = str(getattr(request.user, 'role', '')).upper()
        if user_role not in ['CUSTOMER', 'ADMIN', 'SUPER_ADMIN', 'GUEST']:
            return Response(
                {"error": "Only Customer accounts are allowed to make room reservations. Hotel Owners and Admins manage properties."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Concurrency & Overselling Prevention (select_for_update lock)
        room_id = request.data.get('room') or request.data.get('room_id')
        check_in = request.data.get('check_in')
        check_out = request.data.get('check_out')
        requested_rooms = int(request.data.get('number_of_rooms') or 1)

        from rooms.models import Room
        from django.db.models import Sum
        from datetime import date

        if room_id:
            try:
                # Lock the room inventory row during reservation
                room_locked = Room.objects.select_for_update().get(id=room_id)
            except Room.DoesNotExist:
                return Response({"error": "Room not found."}, status=status.HTTP_404_NOT_FOUND)

            if check_in and check_out:
                from util.validators import parse_flexible_date
                cin = parse_flexible_date(check_in)
                cout = parse_flexible_date(check_out)

                if cin and cout and cout > cin:
                    from rooms.utils import auto_update_past_checkout_bookings, get_room_numbers_availability
                    auto_update_past_checkout_bookings()

                    from django.db.models import Q
                    overlapping_bookings = Booking.objects.filter(
                        room=room_locked,
                        check_in__lt=cout,
                        check_out__gt=cin
                    ).filter(
                        Q(booking_status__in=[
                            Booking.STATUS_CONFIRMED,
                            Booking.STATUS_CHECKED_IN,
                            Booking.STATUS_COMPLETED,
                        ]) |
                        Q(payment_status=Booking.PAYMENT_PAID)
                    ).exclude(
                        booking_status__in=[
                            Booking.STATUS_CANCELLED,
                            Booking.STATUS_CHECKED_OUT,
                            Booking.STATUS_REFUNDED,
                            Booking.STATUS_EXPIRED,
                        ]
                    )
                    booked_count = overlapping_bookings.aggregate(Sum('number_of_rooms'))['number_of_rooms__sum'] or 0
                    all_nums = room_locked.get_all_room_numbers() if hasattr(room_locked, 'get_all_room_numbers') else []
                    total_units = max(getattr(room_locked, 'total_rooms', 1) or 1, len(all_nums))

                    if (booked_count + requested_rooms) > total_units:
                        return Response(
                            {
                                "success": False,
                                "error": "Room is no longer available for the selected dates.",
                                "available_count": max(0, total_units - booked_count),
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

        booking.expires_at = timezone.now() + timedelta(minutes=15)
        booking.price_snapshot = {
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
        booking = None

        if str(lookup).isdigit():
            booking = Booking.objects.filter(pk=int(lookup)).first()
        
        if not booking:
            booking = Booking.objects.filter(booking_id=lookup).first()

        if not booking:
            from rest_framework.exceptions import NotFound
            raise NotFound("Booking receipt not found.")

        user = self.request.user
        role = str(getattr(user, 'role', '')).upper()
        is_admin = user.is_staff or role in ['ADMIN', 'SUPER_ADMIN', 'SUPPORT_AGENT']
        is_owner = (booking.hotel.owner == user)
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
        is_admin = user.is_staff or role in ['ADMIN', 'SUPER_ADMIN']
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
        is_admin = user.is_staff or role in ['ADMIN', 'SUPER_ADMIN']
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
        elif is_paid and Decimal(str(calc['refundable_amount'])) == Decimal('0.00'):
            booking.payment_status = Booking.PAYMENT_REFUNDED
        else:
            booking.payment_status = Booking.PAYMENT_FAILED

        booking.save()

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

        return Response({
            "message": f"Booking {booking.booking_id} cancelled successfully. Refund request submitted to Hotel Owner.",
            "booking_id": booking.booking_id,
            "status": booking.booking_status,
            "payment_status": booking.payment_status,
            "refund_status": "PENDING" if is_paid and calc['refundable_amount'] > 0 else "NONE",
            **calc
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
    if user.is_superuser or user.is_staff:
        return True
    user_role = str(getattr(user, 'role', '')).upper()
    if user_role in ['ADMIN', 'SUPER_ADMIN']:
        return True
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

    def post(self, request, pk):
        lookup = str(pk)
        booking = Booking.objects.filter(pk=int(lookup)).first() if lookup.isdigit() else Booking.objects.filter(booking_id=lookup).first()

        if not booking:
            return Response({"error": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)

        # Check permissions: Booking owner, hotel owner, or authorized staff/admin
        is_owner = request.user == booking.customer
        is_authorized_staff = is_authorized_hotel_staff_or_owner_or_admin(request.user, booking.hotel, permission_field='can_manage_bookings')

        if not (is_owner or is_authorized_staff):
            return Response({"error": "You do not have permission to resend confirmation for this booking."}, status=status.HTTP_403_FORBIDDEN)

        if booking.booking_status != Booking.STATUS_CONFIRMED:
            return Response({
                "error": f"Cannot send confirmation email for booking with status '{booking.booking_status}'. Only confirmed bookings can receive vouchers."
            }, status=status.HTTP_400_BAD_REQUEST)

        from services.booking_email_service import send_booking_confirmation_email
        result = send_booking_confirmation_email(booking, force_retry=True)

        if result.get("success"):
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
        is_staff = request.user.is_staff or role in ['ADMIN', 'SUPER_ADMIN', 'HOTEL_STAFF']

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


