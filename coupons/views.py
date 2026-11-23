from rest_framework import status, permissions, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from django.utils import timezone
from decimal import Decimal
from .models import Coupon, CouponUsage
from .serializers import CouponSerializer
from util.validators import parse_flexible_date


class ValidateCouponView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'coupon_apply'

    def post(self, request):
        code = (
            request.data.get('code') or
            request.data.get('coupon_code') or
            request.data.get('coupon') or
            ''
        ).strip().upper()

        amount_raw = (
            request.data.get('amount') or
            request.data.get('subtotal') or
            request.data.get('cart_total') or
            request.data.get('total') or
            request.data.get('total_amount') or
            request.data.get('room_subtotal')
        )
        try:
            amount = float(amount_raw) if amount_raw is not None else None
        except (ValueError, TypeError):
            amount = None

        check_in_raw = request.data.get('check_in') or request.data.get('check_in_date')
        check_in = parse_flexible_date(check_in_raw) if check_in_raw else None
        booking_id = request.data.get('booking_id')

        if not code:
            return Response({"error": "Please enter a coupon code."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            coupon = Coupon.objects.get(code__iexact=code)
        except Coupon.DoesNotExist:
            return Response({"error": f"Invalid promo coupon code '{code}'."}, status=status.HTTP_404_NOT_FOUND)

        # Check if this user already applied the coupon to an existing booking before deactivation
        is_already_applied = False
        if booking_id:
            try:
                from bookings.models import Booking
                from django.db.models import Q
                prior_b = Booking.objects.filter(
                    Q(id=booking_id) if str(booking_id).isdigit() else Q(booking_id=str(booking_id))
                ).first()
                if prior_b:
                    sn = prior_b.price_snapshot or {}
                    code_in_snap = str(sn.get('coupon_code', '')).strip().upper()
                    if code_in_snap == coupon.code.upper() or (prior_b.discount and prior_b.discount > 0):
                        is_already_applied = True
            except Exception:
                pass

        is_valid, err_msg, discount_val = coupon.validate_eligibility(
            user=request.user,
            amount=amount,
            check_in_date=check_in,
            exclude_booking_id=booking_id,
            is_already_applied=is_already_applied
        )

        if not is_valid:
            return Response({
                "valid": False,
                "success": False,
                "error": err_msg,
                "message": err_msg
            }, status=status.HTTP_400_BAD_REQUEST)

        discount_amount = float(discount_val)
        net_amount = round(max(0.0, amount - discount_amount), 2) if amount is not None else None

        return Response({
            "valid": True,
            "success": True,
            "code": coupon.code,
            "title": coupon.title or f"{coupon.discount_percentage}% OFF Promo",
            "description": coupon.description or "",
            "discount_percentage": float(coupon.discount_percentage),
            "max_discount_amount": float(coupon.max_discount_amount),
            "min_booking_amount": float(coupon.min_booking_amount),
            "discount_amount": round(discount_amount, 2),
            "discount": round(discount_amount, 2),
            "net_amount": net_amount,
            "campaign_type": coupon.campaign_type,
            "campaign_name": coupon.campaign_name or "",
            "user_type_eligibility": coupon.user_type_eligibility,
            "is_first_booking_only": coupon.is_first_booking_only,
            "max_uses_per_user": coupon.max_uses_per_user,
            "times_used": coupon.times_used,
            "message": f"Coupon {coupon.code} applied successfully! Saved ₹{discount_amount}."
        }, status=status.HTTP_200_OK)


class ActiveCouponsListView(generics.ListAPIView):
    """
    Returns available, active and campaign-valid coupons tailored for the requesting user.
    Dynamic dates & festive/seasonal campaign prioritization.
    Accepts optional query params: ?amount=5000&check_in=2026-11-20&campaign_type=FESTIVE
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = CouponSerializer

    def get_queryset(self):
        today = timezone.now().date()
        qs = Coupon.objects.filter(is_active=True, valid_from__lte=today, valid_until__gte=today)
        campaign_type = self.request.query_params.get('campaign_type')
        if campaign_type:
            qs = qs.filter(campaign_type__iexact=campaign_type.strip())
        return qs.order_by('-discount_percentage')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        user = request.user
        amount_raw = (
            request.query_params.get('amount') or
            request.query_params.get('cart_total') or
            request.query_params.get('subtotal') or
            request.query_params.get('total')
        )
        try:
            amount = float(amount_raw) if amount_raw is not None else None
        except (ValueError, TypeError):
            amount = None

        check_in_raw = request.query_params.get('check_in') or request.query_params.get('check_in_date')
        check_in = parse_flexible_date(check_in_raw) if check_in_raw else None

        coupons_data = []
        for c in queryset:
            is_valid, err_msg, disc = c.validate_eligibility(user=user, amount=amount, check_in_date=check_in)
            item = CouponSerializer(c).data
            item['is_eligible'] = is_valid
            item['reason_ineligible'] = None if is_valid else err_msg
            item['potential_discount'] = float(disc) if is_valid else (float(c.calculate_discount(amount)) if amount else 0.0)
            coupons_data.append(item)

        # Highlight Festive and Seasonal campaigns first, followed by First Booking
        def sort_priority(item):
            camp = item.get('campaign_type', 'GENERAL')
            if camp == 'FESTIVE':
                return 0
            elif camp == 'SEASONAL':
                return 1
            elif camp == 'FIRST_BOOKING':
                return 2
            return 3

        coupons_data.sort(key=sort_priority)

        return Response({
            "count": len(coupons_data),
            "available_coupons": coupons_data,
            "coupons": coupons_data,
            "results": coupons_data,
            "data": coupons_data
        }, status=status.HTTP_200_OK)


class CouponToggleStatusView(APIView):
    """
    Admin-controlled coupon activation toggle (Rule 5).
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        role = str(getattr(request.user, 'role', '')).upper()
        if not (request.user.is_staff or role in ['ADMIN', 'SUPER_ADMIN']):
            return Response({"error": "Admin permission required to toggle coupon activation."}, status=status.HTTP_403_FORBIDDEN)

        try:
            coupon = Coupon.objects.get(pk=pk)
            old_status = coupon.is_active
            coupon.is_active = not coupon.is_active
            coupon.save(update_fields=['is_active'])

            # Audit logging
            try:
                from payments.models import AuditLog
                AuditLog.objects.create(
                    user=request.user,
                    action='ACTIVATE_COUPON' if coupon.is_active else 'DEACTIVATE_COUPON',
                    entity_type='Coupon',
                    entity_id=str(coupon.id),
                    old_values={'is_active': old_status},
                    new_values={'is_active': coupon.is_active},
                    ip_address=request.META.get('REMOTE_ADDR')
                )
            except Exception:
                pass

            status_label = "activated" if coupon.is_active else "deactivated"
            return Response({
                "message": f"Coupon '{coupon.code}' has been {status_label}.",
                "coupon_id": coupon.id,
                "code": coupon.code,
                "is_active": coupon.is_active
            }, status=status.HTTP_200_OK)
        except Coupon.DoesNotExist:
            return Response({"error": "Coupon not found."}, status=status.HTTP_404_NOT_FOUND)


class CouponListCreateView(generics.ListCreateAPIView):
    serializer_class = CouponSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        user = self.request.user
        role = str(getattr(user, 'role', '')).upper()
        if user.is_authenticated and (user.is_staff or role in ['ADMIN', 'SUPER_ADMIN']):
            return Coupon.objects.all().order_by('-id')
        today = timezone.now().date()
        return Coupon.objects.filter(is_active=True, valid_from__lte=today, valid_until__gte=today).order_by('-id')

    def perform_create(self, serializer):
        user = self.request.user
        role = str(getattr(user, 'role', '')).upper()
        if not (user.is_authenticated and (user.is_staff or role in ['ADMIN', 'SUPER_ADMIN'])):
            raise permissions.PermissionDenied("Admin permission required to create coupons.")
        code = serializer.validated_data.get('code', '').upper()
        serializer.save(code=code)


class CouponDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Coupon.objects.all()
    serializer_class = CouponSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
