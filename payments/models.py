import uuid
from django.db import models
from django.conf import settings
from bookings.models import Booking

class Payment(models.Model):
    STATUS_CREATED = 'CREATED'
    STATUS_PENDING = 'PENDING'
    STATUS_AUTHORIZED = 'AUTHORIZED'
    STATUS_CAPTURED = 'CAPTURED'
    STATUS_FAILED = 'FAILED'
    STATUS_REFUND_PENDING = 'REFUND_PENDING'
    STATUS_PARTIALLY_REFUNDED = 'PARTIALLY_REFUNDED'
    STATUS_REFUNDED = 'REFUNDED'

    PAYMENT_STATUS_CHOICES = (
        (STATUS_CREATED, 'Created'),
        (STATUS_PENDING, 'Pending'),
        (STATUS_AUTHORIZED, 'Authorized'),
        (STATUS_CAPTURED, 'Captured'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_REFUND_PENDING, 'Refund Pending'),
        (STATUS_PARTIALLY_REFUNDED, 'Partially Refunded'),
        (STATUS_REFUNDED, 'Refunded'),
    )

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='payments')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payments')
    
    razorpay_order_id = models.CharField(max_length=100, db_index=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True, unique=True, db_index=True)
    razorpay_signature = models.TextField(blank=True, null=True)
    
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default='INR')
    
    status = models.CharField(max_length=30, choices=PAYMENT_STATUS_CHOICES, default=STATUS_CREATED, db_index=True)
    payment_method = models.CharField(max_length=50, blank=True, null=True)
    failure_reason = models.TextField(blank=True, null=True)
    error_code = models.CharField(max_length=100, blank=True, null=True)
    
    paid_at = models.DateTimeField(blank=True, null=True)
    is_duplicate_captured = models.BooleanField(default=False, db_index=True)
    review_notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['booking', 'status']),
            models.Index(fields=['razorpay_order_id', 'status']),
        ]

    def __str__(self):
        return f"Payment {self.razorpay_order_id} - {self.status} (₹{self.amount})"


class Refund(models.Model):
    STATUS_REFUND_PENDING = 'REFUND_PENDING'
    STATUS_REFUND_PROCESSING = 'REFUND_PROCESSING'
    STATUS_REFUNDED = 'REFUNDED'
    STATUS_REFUND_FAILED = 'REFUND_FAILED'

    # Refund Destination Mode
    REFUND_MODE_ORIGINAL = 'ORIGINAL_SOURCE'
    REFUND_MODE_BANK = 'BANK_TRANSFER'
    REFUND_MODE_UPI = 'UPI'

    REFUND_MODE_CHOICES = (
        (REFUND_MODE_ORIGINAL, 'Original Payment Source (Razorpay Refund)'),
        (REFUND_MODE_BANK, 'Direct Bank Transfer (RazorpayX Payout)'),
        (REFUND_MODE_UPI, 'UPI VPA Transfer (RazorpayX Payout)'),
    )

    # Backward compatibility aliases
    STATUS_PENDING = 'REFUND_PENDING'
    STATUS_PROCESSED = 'REFUNDED'
    STATUS_FAILED = 'REFUND_FAILED'

    REFUND_STATUS_CHOICES = (
        (STATUS_REFUND_PENDING, 'Refund Pending'),
        (STATUS_REFUND_PROCESSING, 'Refund Processing'),
        (STATUS_REFUNDED, 'Refund Completed'),
        (STATUS_REFUND_FAILED, 'Refund Failed'),
        # Legacy support
        ('PENDING', 'Refund Pending'),
        ('PROCESSED', 'Refund Completed'),
        ('FAILED', 'Refund Failed'),
    )

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='refunds')
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='refunds')
    
    refund_mode = models.CharField(max_length=30, choices=REFUND_MODE_CHOICES, default=REFUND_MODE_ORIGINAL)
    
    # Customer Provided Payout Destination (Securely restricted)
    customer_account_holder = models.CharField(max_length=150, blank=True, null=True)
    customer_bank_name = models.CharField(max_length=100, blank=True, null=True)
    customer_account_number = models.CharField(max_length=50, blank=True, null=True)
    customer_ifsc_code = models.CharField(max_length=20, blank=True, null=True)
    customer_upi_id = models.CharField(max_length=100, blank=True, null=True)

    razorpay_payment_id = models.CharField(max_length=100)
    razorpay_refund_id = models.CharField(max_length=100, unique=True, null=True, blank=True, db_index=True)
    payout_reference_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    contact_id = models.CharField(max_length=100, blank=True, null=True, help_text="RazorpayX Contact ID")
    fund_account_id = models.CharField(max_length=100, blank=True, null=True, help_text="RazorpayX Fund Account ID")
    payout_mode = models.CharField(max_length=20, default='NEFT', blank=True, help_text="NEFT, UPI, IMPS, RTGS")
    idempotency_key = models.CharField(max_length=120, unique=True, null=True, blank=True, db_index=True)
    
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default='INR')
    reason = models.TextField(blank=True, null=True)
    failure_reason = models.TextField(blank=True, null=True)
    admin_notes = models.TextField(blank=True, null=True)
    provider_status = models.CharField(max_length=50, blank=True, null=True)
    provider_raw_response = models.JSONField(blank=True, null=True)
    retry_count = models.IntegerField(default=0)
    
    status = models.CharField(max_length=30, choices=REFUND_STATUS_CHOICES, default=STATUS_REFUND_PENDING, db_index=True)
    
    processed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='processed_refunds')
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(blank=True, null=True)
    failed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        ref_id = self.razorpay_refund_id or self.idempotency_key or f"REF-{self.id}"
        return f"Refund {ref_id} - ₹{self.amount} ({self.status})"


class WebhookEvent(models.Model):
    event_id = models.CharField(max_length=100, unique=True, db_index=True)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField()
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Webhook {self.event_id} ({self.event_type})"


class HostPayoutAccount(models.Model):
    METHOD_BANK = 'BANK_ACCOUNT'
    METHOD_UPI = 'UPI'
    METHOD_CHOICES = (
        (METHOD_BANK, 'Bank Account (NEFT/IMPS/RTGS)'),
        (METHOD_UPI, 'UPI ID (Virtual Payment Address)'),
    )

    STATUS_UNVERIFIED = 'UNVERIFIED'
    STATUS_PENDING = 'PENDING_VERIFICATION'
    STATUS_VERIFIED = 'VERIFIED'
    STATUS_FAILED = 'FAILED'
    STATUS_CHOICES = (
        (STATUS_UNVERIFIED, 'Unverified'),
        (STATUS_PENDING, 'Verification Pending'),
        (STATUS_VERIFIED, 'Verified'),
        (STATUS_FAILED, 'Verification Failed'),
    )

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payout_account')
    payout_method = models.CharField(max_length=20, choices=METHOD_CHOICES, default=METHOD_BANK)
    account_holder_name = models.CharField(max_length=150)
    bank_name = models.CharField(max_length=150, blank=True, null=True)
    account_number = models.CharField(max_length=50, blank=True, null=True)
    ifsc_code = models.CharField(max_length=20, blank=True, null=True)
    upi_id = models.CharField(max_length=100, blank=True, null=True)
    
    is_verified = models.BooleanField(default=False)
    verification_status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_UNVERIFIED)
    fund_account_id = models.CharField(max_length=100, blank=True, null=True)
    contact_id = models.CharField(max_length=100, blank=True, null=True)
    verification_error = models.TextField(blank=True, null=True)
    verified_at = models.DateTimeField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def masked_account_number(self):
        if not self.account_number:
            return ''
        clean = self.account_number.strip()
        if len(clean) <= 4:
            return '•••• ' + clean
        return f"•••• •••• •••• {clean[-4:]}"

    @property
    def masked_upi_id(self):
        if not self.upi_id:
            return ''
        parts = self.upi_id.split('@')
        if len(parts) == 2:
            handle, bank = parts
            masked_handle = handle[:2] + '••••' if len(handle) > 2 else handle + '••••'
            return f"{masked_handle}@{bank}"
        return self.upi_id

    @property
    def destination_summary(self):
        if self.payout_method == self.METHOD_UPI:
            return f"UPI: {self.masked_upi_id} ({self.account_holder_name})"
        bank = self.bank_name or 'Bank'
        return f"{bank} {self.masked_account_number} [IFSC: {self.ifsc_code}] ({self.account_holder_name})"

    def __str__(self):
        return f"PayoutAccount for {self.user.username} ({self.destination_summary})"


class HostEarning(models.Model):
    STATUS_ON_HOLD = 'ON_HOLD'
    STATUS_ELIGIBLE = 'ELIGIBLE'
    STATUS_PROCESSING = 'PROCESSING'
    STATUS_PAID = 'PAID'
    STATUS_REVERSED = 'REVERSED'
    STATUS_DISPUTED = 'DISPUTED'

    # Backwards-compatible aliases
    STATUS_PENDING = STATUS_ON_HOLD
    STATUS_AVAILABLE = STATUS_ELIGIBLE

    HOST_EARNING_STATUS_CHOICES = (
        (STATUS_ON_HOLD, 'On Hold (7-Day Escrow)'),
        (STATUS_ELIGIBLE, 'Eligible for Payout'),
        (STATUS_PROCESSING, 'Processing Transfer'),
        (STATUS_PAID, 'Paid & Settled'),
        (STATUS_REVERSED, 'Reversed / Cancelled'),
        (STATUS_DISPUTED, 'Dispute / Hold'),
    )

    host = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='host_earnings')
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='host_earning')
    payout = models.ForeignKey('HostPayout', on_delete=models.SET_NULL, blank=True, null=True, related_name='earnings')
    
    gross_amount = models.DecimalField(max_digits=12, decimal_places=2)
    platform_fee_percent = models.DecimalField(max_digits=5, decimal_places=2, default=10.00)
    platform_fee = models.DecimalField(max_digits=12, decimal_places=2)  # Platform commission
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    refund_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    net_amount = models.DecimalField(max_digits=12, decimal_places=2)
    
    status = models.CharField(max_length=30, choices=HOST_EARNING_STATUS_CHOICES, default=STATUS_ON_HOLD, db_index=True)
    holding_period_days = models.PositiveIntegerField(default=7)
    hold_until = models.DateTimeField(db_index=True, blank=True, null=True)
    hold_reason = models.TextField(blank=True, null=True)
    
    is_disputed = models.BooleanField(default=False, db_index=True)
    dispute_reason = models.TextField(blank=True, null=True)
    
    available_at = models.DateTimeField(blank=True, null=True)
    settled_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def calculate_eligibility(self, as_of_time=None):
        """
        Calculates whether this earning is eligible for owner payout.
        Returns (is_eligible: bool, reasons: list[str])
        """
        from django.utils import timezone
        now = as_of_time or timezone.now()
        reasons = []

        if self.status == self.STATUS_PAID:
            return False, ["Payout already completed and settled."]

        if self.status == self.STATUS_REVERSED:
            return False, ["Host earning is reversed due to booking cancellation or refund."]

        # EXCLUDE REFUNDABLE & CANCELLED BOOKINGS FROM HOST PAYOUT
        if self.booking.booking_status in [Booking.STATUS_CANCELLED, Booking.STATUS_REFUND_PENDING, Booking.STATUS_REFUNDED]:
            reasons.append("Booking is cancelled or in refund process.")

        if self.booking.payment_status in [Booking.PAYMENT_REFUND_PENDING, Booking.PAYMENT_REFUNDED, Booking.PAYMENT_PARTIALLY_REFUNDED]:
            reasons.append("Booking is in refund process or already refunded.")

        if self.refund_amount and self.refund_amount > 0:
            reasons.append(f"Refund of ₹{self.refund_amount} recorded for this booking.")

        if self.booking.refundable_amount and self.booking.refundable_amount > 0:
            reasons.append("Booking has an active refundable balance.")

        if self.booking.refunds.filter(status__in=['REFUNDED', 'PROCESSED', 'REFUND_PROCESSING', 'PROCESSING', 'REFUND_PENDING', 'PENDING']).exists():
            reasons.append("Active or processed refund exists for this booking.")

        if self.is_disputed:
            reasons.append(f"Dispute hold: {self.dispute_reason or 'Under active review'}")

        # Check for unresolved support tickets referencing this booking
        unresolved_tickets = SupportTicket.objects.filter(
            booking=self.booking,
            status__in=['OPEN', 'IN_PROGRESS', 'WAITING_FOR_USER']
        ).count()
        if unresolved_tickets > 0:
            reasons.append(f"Unresolved customer support ticket/complaint ({unresolved_tickets} active ticket(s)).")

        # 7-day holding period check
        if self.hold_until and now < self.hold_until:
            remaining_seconds = int((self.hold_until - now).total_seconds())
            remaining_days = max(1, (remaining_seconds + 86399) // 86400)
            reasons.append(f"7-Day holding period active until {self.hold_until.strftime('%b %d, %Y')} ({remaining_days} day(s) remaining).")

        # Check payout account
        payout_acc = getattr(self.host, 'payout_account', None)
        if not payout_acc:
            reasons.append("Hotel owner has not registered a payout bank account or UPI ID.")
        elif not payout_acc.is_verified and payout_acc.verification_status != HostPayoutAccount.STATUS_VERIFIED:
            reasons.append("Hotel owner payout account is pending verification.")

        is_eligible = len(reasons) == 0
        return is_eligible, reasons

    def update_dynamic_status(self, as_of_time=None):
        """Updates internal status if holding period has passed and no disputes exist."""
        if self.status == self.STATUS_PAID:
            return self.status

        # If booking is cancelled or has refund active, immediately transition to REVERSED
        is_cancelled_or_refunded = (
            self.booking.booking_status in [Booking.STATUS_CANCELLED, Booking.STATUS_REFUND_PENDING, Booking.STATUS_REFUNDED] or
            self.booking.payment_status in [Booking.PAYMENT_REFUND_PENDING, Booking.PAYMENT_REFUNDED, Booking.PAYMENT_PARTIALLY_REFUNDED] or
            (self.refund_amount and self.refund_amount > 0) or
            (self.booking.refundable_amount and self.booking.refundable_amount > 0 and self.booking.booking_status == Booking.STATUS_CANCELLED) or
            self.booking.refunds.filter(status__in=['REFUNDED', 'PROCESSED', 'REFUND_PROCESSING', 'PROCESSING', 'REFUND_PENDING', 'PENDING']).exists()
        )

        if is_cancelled_or_refunded:
            if self.status != self.STATUS_REVERSED:
                self.status = self.STATUS_REVERSED
                self.hold_reason = "Booking is cancelled/refunded. Host payout eligibility excluded."
                if self.pk:
                    self.save(update_fields=['status', 'hold_reason', 'updated_at'])
            return self.status

        old_status = self.status
        old_reason = self.hold_reason
        is_eligible, reasons = self.calculate_eligibility(as_of_time)
        if is_eligible:
            self.status = self.STATUS_ELIGIBLE
            self.hold_reason = ''
        elif self.is_disputed:
            self.status = self.STATUS_DISPUTED
            self.hold_reason = "; ".join(reasons)
        else:
            self.status = self.STATUS_ON_HOLD
            self.hold_reason = "; ".join(reasons)

        if (self.status != old_status or self.hold_reason != old_reason) and self.pk:
            self.save(update_fields=['status', 'hold_reason', 'updated_at'])
        return self.status
        return self.status

    def __str__(self):
        return f"HostEarning {self.host.username} - Booking {self.booking.booking_id} (Net: ₹{self.net_amount}, Status: {self.status})"


class HostPayout(models.Model):
    STATUS_PENDING = 'PENDING'
    STATUS_ELIGIBLE = 'ELIGIBLE'
    STATUS_PROCESSING = 'PROCESSING'
    STATUS_COMPLETED = 'COMPLETED'
    STATUS_FAILED = 'FAILED'
    STATUS_PROVIDER_SETUP_REQUIRED = 'PROVIDER_SETUP_REQUIRED'
    STATUS_ON_HOLD = 'ON_HOLD'

    PAYOUT_STATUS_CHOICES = (
        (STATUS_PENDING, 'Pending Review'),
        (STATUS_ELIGIBLE, 'Eligible for Payout'),
        (STATUS_PROCESSING, 'Processing with Provider'),
        (STATUS_COMPLETED, 'Completed & Verified'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_PROVIDER_SETUP_REQUIRED, 'Provider Setup Required'),
        (STATUS_ON_HOLD, 'On Hold'),
    )

    payout_id = models.CharField(max_length=50, unique=True, db_index=True)
    idempotency_key = models.CharField(max_length=120, blank=True, null=True, unique=True, db_index=True)
    host = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payouts')
    payout_account = models.ForeignKey(HostPayoutAccount, on_delete=models.SET_NULL, blank=True, null=True, related_name='payouts')
    
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default='INR')
    status = models.CharField(max_length=35, choices=PAYOUT_STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    
    provider_mode = models.CharField(max_length=50, default='RAZORPAYX')
    provider_payout_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    provider_status = models.CharField(max_length=50, blank=True, null=True)
    provider_error = models.TextField(blank=True, null=True)
    setup_required_instructions = models.TextField(blank=True, null=True)
    
    bank_reference = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    
    processed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name='approved_payouts')
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.payout_id:
            from django.utils import timezone
            self.payout_id = f"PO-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        if not self.idempotency_key:
            self.idempotency_key = f"idem_{uuid.uuid4().hex}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Payout {self.payout_id} - {self.host.username} (₹{self.amount}, Status: {self.status})"


class PlatformSetting(models.Model):
    commission_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=10.00)
    gst_tax_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=18.00)
    payout_hold_days = models.PositiveIntegerField(default=7, help_text="Holding period in days after guest check-out before payout is eligible")
    payout_provider_mode = models.CharField(
        max_length=50,
        choices=(
            ('RAZORPAYX', 'RazorpayX Business Payouts API'),
            ('RAZORPAY_ROUTE', 'Razorpay Route (Marketplace Split)'),
            ('MANUAL_ESCROW', 'Platform Escrow Settlement / Bank Transfer'),
        ),
        default='RAZORPAYX'
    )
    razorpayx_account_number = models.CharField(max_length=100, blank=True, null=True, help_text="Platform RazorpayX Account Number")
    razorpay_route_enabled = models.BooleanField(default=False)
    default_currency = models.CharField(max_length=10, default='INR')
    support_email = models.EmailField(default='support@bookmyroom.com')
    support_phone = models.CharField(max_length=20, default='+91 98765 43210')
    is_maintenance_mode = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_settings(cls):
        obj = cls.objects.first()
        if not obj:
            obj = cls.objects.create()
        return obj

    def __str__(self):
        return f"Platform Settings (Hold: {self.payout_hold_days} days, Commission: {self.commission_percentage}%)"

# Backward compatibility alias
PaymentSetting = PlatformSetting


class SupportTicket(models.Model):
    CATEGORY_CHOICES = (
        ('BOOKING', 'Booking Inquiry'),
        ('PAYMENT', 'Payment Issue'),
        ('REFUND', 'Refund Request'),
        ('HOTEL', 'Hotel Property Info'),
        ('CANCELLATION', 'Cancellation'),
        ('ACCOUNT', 'Account Settings'),
        ('TECHNICAL', 'Technical Bug'),
    )

    PRIORITY_CHOICES = (
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
        ('URGENT', 'Urgent'),
    )

    STATUS_CHOICES = (
        ('OPEN', 'Open'),
        ('IN_PROGRESS', 'In Progress'),
        ('WAITING_FOR_USER', 'Waiting for Customer'),
        ('RESOLVED', 'Resolved'),
        ('CLOSED', 'Closed'),
    )

    ticket_number = models.CharField(max_length=50, unique=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='support_tickets')
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, blank=True, null=True, related_name='support_tickets')
    hotel = models.ForeignKey('hotels.Hotel', on_delete=models.SET_NULL, blank=True, null=True, related_name='support_tickets')
    room = models.ForeignKey('rooms.Room', on_delete=models.SET_NULL, blank=True, null=True, related_name='support_tickets')
    
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default='BOOKING')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='MEDIUM')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='OPEN')
    
    subject = models.CharField(max_length=255)
    description = models.TextField()
    attachment = models.FileField(upload_to='support_tickets/attachments/', blank=True, null=True)
    attachment_url = models.URLField(max_length=500, blank=True, null=True)
    
    assigned_agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name='assigned_tickets')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def customer(self):
        return self.user

    @customer.setter
    def customer(self, val):
        self.user = val

    def save(self, *args, **kwargs):
        if not self.ticket_number:
            self.ticket_number = f"TICK-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Ticket {self.ticket_number} - {self.subject} ({self.status})"


class TicketMessage(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    message = models.TextField()
    attachment = models.FileField(upload_to='support_tickets/messages/', blank=True, null=True)
    attachment_url = models.URLField(max_length=500, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Message on {self.ticket.ticket_number} by {self.sender.username}"


class CustomerHotelMessage(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='chat_messages')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_chat_messages')
    receiver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_chat_messages')
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Chat on Booking {self.booking.booking_id} from {self.sender.username}"


class AuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True)
    action = models.CharField(max_length=150)
    entity_type = models.CharField(max_length=100)
    entity_id = models.CharField(max_length=100, blank=True, null=True)
    old_values = models.JSONField(blank=True, null=True)
    new_values = models.JSONField(blank=True, null=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Aliases for TASK-17 specification compliance
    @property
    def admin_user(self):
        return self.user

    @admin_user.setter
    def admin_user(self, val):
        self.user = val

    @property
    def target_model(self):
        return self.entity_type

    @target_model.setter
    def target_model(self, val):
        self.entity_type = val

    @property
    def target_id(self):
        return self.entity_id

    @target_id.setter
    def target_id(self, val):
        self.entity_id = val

    @property
    def timestamp(self):
        return self.created_at

    @property
    def previous_state(self):
        return self.old_values

    @previous_state.setter
    def previous_state(self, val):
        self.old_values = val

    @property
    def new_state(self):
        return self.new_values

    @new_state.setter
    def new_state(self, val):
        self.new_values = val

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"AuditLog {self.action} on {self.entity_type} by {self.user}"
