from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal


class Coupon(models.Model):
    ELIGIBILITY_ALL = 'ALL'
    ELIGIBILITY_NEW_USER = 'NEW_USER_ONLY'
    ELIGIBILITY_EXISTING_USER = 'EXISTING_USER_ONLY'

    ELIGIBILITY_CHOICES = (
        (ELIGIBILITY_ALL, 'All Users'),
        (ELIGIBILITY_NEW_USER, 'New Users Only (First Successful Booking)'),
        (ELIGIBILITY_EXISTING_USER, 'Existing Users Only (Repeat Customers)'),
    )

    CAMPAIGN_GENERAL = 'GENERAL'
    CAMPAIGN_SEASONAL = 'SEASONAL'
    CAMPAIGN_FESTIVE = 'FESTIVE'
    CAMPAIGN_FIRST_BOOKING = 'FIRST_BOOKING'

    CAMPAIGN_CHOICES = (
        (CAMPAIGN_GENERAL, 'Standard Promotional Coupon'),
        (CAMPAIGN_SEASONAL, 'Seasonal Travel Campaign'),
        (CAMPAIGN_FESTIVE, 'Festive / Holiday Event Campaign'),
        (CAMPAIGN_FIRST_BOOKING, 'First-Time User Welcome Offer'),
    )

    # Core identification & financial discount rules (Preserved for 100% backwards compatibility)
    code = models.CharField(max_length=50, unique=True)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=10.00)
    max_discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=1000.00)
    min_booking_amount = models.DecimalField(max_digits=10, decimal_places=2, default=2000.00)
    valid_from = models.DateField()
    valid_until = models.DateField()
    is_active = models.BooleanField(default=True)
    max_uses_per_user = models.PositiveIntegerField(default=1)
    times_used = models.PositiveIntegerField(default=0)

    # Rule 1 & 2: User segmentation & First Booking detection
    user_type_eligibility = models.CharField(
        max_length=30,
        choices=ELIGIBILITY_CHOICES,
        default=ELIGIBILITY_ALL,
        help_text="Target audience eligibility for this coupon"
    )
    is_first_booking_only = models.BooleanField(
        default=False,
        help_text="If True, coupon can only be used by users with 0 previous paid bookings"
    )

    # Rule 3 & 4: Campaign Classification (Seasonal & Festive)
    campaign_type = models.CharField(
        max_length=30,
        choices=CAMPAIGN_CHOICES,
        default=CAMPAIGN_GENERAL,
        help_text="Type of campaign running this coupon"
    )
    campaign_name = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        help_text="e.g. 'Diwali Dhamaka 2026', 'Summer Holiday Bonanza'"
    )
    title = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="User-facing title e.g. 'Flat 20% OFF on Summer Bookings'"
    )
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Marketing description / terms and conditions for frontend cards"
    )

    # Seasonal stay dates (optional check-in window)
    stay_checkin_from = models.DateField(
        blank=True,
        null=True,
        help_text="Optional: Check-in date must be on or after this date"
    )
    stay_checkin_until = models.DateField(
        blank=True,
        null=True,
        help_text="Optional: Check-in date must be on or before this date"
    )

    # Rule 8: Total global redemptions cap (anti-abuse)
    usage_limit_total = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Optional: Total platform-wide redemptions allowed across all users"
    )

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def min_purchase_amount(self):
        return self.min_booking_amount

    def calculate_discount(self, amount):
        if amount is None or amount <= Decimal('0.00'):
            return Decimal('0.00')
        amt = Decimal(str(amount))
        pct = Decimal(str(self.discount_percentage))
        raw_disc = round(amt * (pct / Decimal('100.00')), 2)
        if self.max_discount_amount:
            return min(raw_disc, Decimal(str(self.max_discount_amount)))
        return raw_disc

    def validate_eligibility(self, user=None, amount=None, check_in_date=None, exclude_booking_id=None, is_already_applied=False):
        """
        Comprehensive business validation for coupon applicability.
        Returns: (is_valid: bool, error_msg: str, calculated_discount: Decimal)
        """
        today = timezone.now().date()

        # Check if coupon was already applied to an existing booking before deactivation (Rule: last time discount honored)
        if not is_already_applied and exclude_booking_id:
            try:
                from bookings.models import Booking
                from django.db.models import Q
                prior_b = Booking.objects.filter(
                    Q(id=exclude_booking_id) if str(exclude_booking_id).isdigit() else Q(booking_id=str(exclude_booking_id))
                ).first()
                if prior_b:
                    sn = prior_b.price_snapshot or {}
                    code_in_snap = str(sn.get('coupon_code', '')).strip().upper()
                    if code_in_snap == self.code.upper() or (prior_b.discount and prior_b.discount > 0):
                        is_already_applied = True
            except Exception:
                pass

        # 1. Active status check (Admin-controlled activation)
        if not self.is_active:
            if is_already_applied:
                # User already applied this coupon before admin deactivated it; honor it for this booking (last time discount)!
                pass
            else:
                return False, f"Coupon '{self.code}' is currently deactivated by platform administrators.", Decimal('0.00')

        # 2. General validity date range check
        if self.valid_from > today:
            if not is_already_applied:
                return False, f"Coupon '{self.code}' is not active yet. Valid from {self.valid_from.strftime('%d %b %Y')}.", Decimal('0.00')
        if self.valid_until < today:
            if not is_already_applied:
                return False, f"This coupon code has expired.", Decimal('0.00')

        # 3. Total global redemptions limit check
        if self.usage_limit_total and self.times_used >= self.usage_limit_total:
            if not is_already_applied:
                return False, f"Coupon '{self.code}' has reached its total maximum redemption limit.", Decimal('0.00')

        # 4. Minimum booking amount check
        if amount is not None:
            amt = Decimal(str(amount))
            min_req = Decimal(str(self.min_booking_amount))
            if amt < min_req:
                return False, f"Minimum booking subtotal of ₹{self.min_booking_amount} required to apply code {self.code}.", Decimal('0.00')

        # 5. Seasonal check-in date window check
        if check_in_date:
            from util.validators import parse_flexible_date
            parsed_cin = parse_flexible_date(check_in_date)
            if parsed_cin:
                if self.stay_checkin_from and parsed_cin < self.stay_checkin_from:
                    return False, f"Seasonal coupon '{self.code}' is only valid for stays with check-in from {self.stay_checkin_from.strftime('%d %b %Y')}.", Decimal('0.00')
                if self.stay_checkin_until and parsed_cin > self.stay_checkin_until:
                    return False, f"Seasonal coupon '{self.code}' is only valid for stays with check-in up to {self.stay_checkin_until.strftime('%d %b %Y')}.", Decimal('0.00')

        # 6. User-specific validation (if user authenticated)
        if user and user.is_authenticated:
            # Per-user usage limit check
            user_usages = self.usages.filter(user=user)
            if exclude_booking_id:
                from django.db.models import Q
                user_usages = user_usages.exclude(
                    Q(booking_id=exclude_booking_id) if str(exclude_booking_id).isdigit() else Q(booking__booking_id=str(exclude_booking_id))
                )
            if user_usages.count() >= self.max_uses_per_user:
                return False, f"You have already used coupon {self.code}. It cannot be used again.", Decimal('0.00')

            # Rule 1 & 2: New User / First Booking Detection
            from bookings.models import Booking
            prior_paid_qs = Booking.objects.filter(
                customer=user,
                payment_status=Booking.PAYMENT_PAID
            )
            if exclude_booking_id:
                from django.db.models import Q
                prior_paid_qs = prior_paid_qs.exclude(
                    Q(id=exclude_booking_id) if str(exclude_booking_id).isdigit() else Q(booking_id=str(exclude_booking_id))
                )
            has_prior_paid = prior_paid_qs.exists()

            if self.is_first_booking_only or self.user_type_eligibility == self.ELIGIBILITY_NEW_USER or self.campaign_type == self.CAMPAIGN_FIRST_BOOKING:
                if has_prior_paid or user_usages.exists():
                    return False, f"Coupon '{self.code}' is exclusively for new users on their first booking. You cannot use it again.", Decimal('0.00')

            if self.user_type_eligibility == self.ELIGIBILITY_EXISTING_USER:
                if not has_prior_paid:
                    return False, f"Coupon '{self.code}' is reserved for existing customers with at least 1 prior completed booking.", Decimal('0.00')

        disc = self.calculate_discount(amount) if amount is not None else Decimal('0.00')
        return True, "", disc

    def __str__(self):
        return f"{self.code} ({self.discount_percentage}% OFF - {self.campaign_type})"


class CouponUsage(models.Model):
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name='usages')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='coupon_usages')
    booking = models.ForeignKey('bookings.Booking', on_delete=models.SET_NULL, null=True, blank=True, related_name='coupon_usages')
    discount_applied = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-used_at']
        unique_together = ('coupon', 'booking')

    def __str__(self):
        b_id = self.booking.booking_id if self.booking else "N/A"
        return f"{self.user.username} redeemed {self.coupon.code} on Booking {b_id}"
