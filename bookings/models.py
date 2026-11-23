import uuid
from django.db import models
from django.conf import settings
from hotels.models import Hotel
from rooms.models import Room

class Booking(models.Model):
    STATUS_PENDING_PAYMENT = 'PENDING_PAYMENT'
    STATUS_CONFIRMED = 'CONFIRMED'
    STATUS_CHECKED_IN = 'CHECKED_IN'
    STATUS_CHECKED_OUT = 'CHECKED_OUT'
    STATUS_CANCELLED = 'CANCELLED'
    STATUS_CANCELLATION_REQUESTED = 'CANCELLATION_REQUESTED'
    STATUS_OWNER_APPROVED = 'OWNER_APPROVED'
    STATUS_OWNER_REJECTED = 'OWNER_REJECTED'
    STATUS_COMPLETED = 'COMPLETED'
    STATUS_REFUND_PENDING = 'REFUND_PENDING'
    STATUS_REFUNDED = 'REFUNDED'
    STATUS_NO_SHOW = 'NO_SHOW'
    STATUS_EXPIRED = 'EXPIRED'

    BOOKING_STATUS_CHOICES = (
        (STATUS_PENDING_PAYMENT, 'Pending Payment'),
        (STATUS_CONFIRMED, 'Confirmed'),
        (STATUS_CHECKED_IN, 'Checked In'),
        (STATUS_CHECKED_OUT, 'Checked Out'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_CANCELLED, 'Cancelled'),
        (STATUS_CANCELLATION_REQUESTED, 'Cancellation Requested'),
        (STATUS_OWNER_APPROVED, 'Owner Approved'),
        (STATUS_OWNER_REJECTED, 'Owner Rejected'),
        (STATUS_REFUND_PENDING, 'Refund Pending'),
        (STATUS_REFUNDED, 'Refunded'),
        (STATUS_NO_SHOW, 'No Show'),
        (STATUS_EXPIRED, 'Expired'),
    )

    PAYMENT_PENDING = 'PENDING'
    PAYMENT_PAID = 'PAID'
    PAYMENT_FAILED = 'FAILED'
    PAYMENT_REFUND_PENDING = 'REFUND_PENDING'
    PAYMENT_PARTIALLY_REFUNDED = 'PARTIALLY_REFUNDED'
    PAYMENT_REFUNDED = 'REFUNDED'

    PAYMENT_STATUS_CHOICES = (
        (PAYMENT_PENDING, 'Pending'),
        (PAYMENT_PAID, 'Paid'),
        (PAYMENT_FAILED, 'Failed'),
        (PAYMENT_REFUND_PENDING, 'Refund Pending'),
        (PAYMENT_PARTIALLY_REFUNDED, 'Partially Refunded'),
        (PAYMENT_REFUNDED, 'Refunded'),
    )

    booking_id = models.CharField(max_length=50, unique=True, db_index=True)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='bookings'
    )
    hotel = models.ForeignKey(Hotel, on_delete=models.PROTECT, related_name='bookings')
    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name='bookings')
    
    check_in = models.DateField(db_index=True)
    check_out = models.DateField(db_index=True)
    number_of_guests = models.IntegerField(default=2)
    number_of_rooms = models.IntegerField(default=1)
    room_number = models.CharField(max_length=150, blank=True, null=True, help_text="Specific assigned room number e.g. 101, 102 or Villa-1")
    
    price_per_night = models.DecimalField(max_digits=10, decimal_places=2)
    number_of_nights = models.IntegerField(default=1)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    cleaning_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    service_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    taxes = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default='INR')
    
    price_snapshot = models.JSONField(blank=True, null=True, help_text="Immutable financial price calculation snapshot")

    payment_status = models.CharField(max_length=30, choices=PAYMENT_STATUS_CHOICES, default=PAYMENT_PENDING, db_index=True)
    booking_status = models.CharField(max_length=30, choices=BOOKING_STATUS_CHOICES, default=STATUS_PENDING_PAYMENT, db_index=True)
    
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    
    guest_name = models.CharField(max_length=150)
    guest_email = models.EmailField()
    guest_phone = models.CharField(max_length=20)
    meal_plan = models.CharField(max_length=50, default='ROOM_ONLY')
    estimated_arrival_time = models.CharField(max_length=50, default='12:00 PM - 02:00 PM')
    special_requests = models.TextField(blank=True, null=True)
    
    # Cancellation & Refund Fields
    cancellation_reason = models.TextField(blank=True, null=True)
    cancellation_fee_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    cancellation_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    refundable_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    cancellation_calculated_at = models.DateTimeField(blank=True, null=True)
    cancellation_breakdown = models.JSONField(blank=True, null=True, help_text="Immutable financial snapshot of cancellation calculation")
    applied_cancellation_policy = models.CharField(max_length=255, blank=True, null=True)

    # Email Confirmation Dispatch Tracking
    confirmation_email_sent = models.BooleanField(default=False, db_index=True)
    confirmation_email_sent_at = models.DateTimeField(blank=True, null=True)
    confirmation_email_error = models.TextField(blank=True, null=True)
    confirmation_email_retry_count = models.IntegerField(default=0)

    confirmed_at = models.DateTimeField(blank=True, null=True)
    cancelled_at = models.DateTimeField(blank=True, null=True)
    actual_check_in_at = models.DateTimeField(blank=True, null=True)
    actual_check_out_at = models.DateTimeField(blank=True, null=True)
    action_by_staff = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name='processed_stay_actions')
    
    expires_at = models.DateTimeField(blank=True, null=True, help_text="Pending booking auto-expiration timestamp")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def status(self):
        return self.booking_status

    @status.setter
    def status(self, value):
        self.booking_status = value

    def save(self, *args, **kwargs):
        if not self.booking_id:
            unique_num = uuid.uuid4().hex[:6].upper()
            self.booking_id = f"KH-2026-{unique_num}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Booking {self.booking_id} - {self.hotel.name} ({self.customer.username})"


class CancellationPolicyRule(models.Model):
    name = models.CharField(max_length=150, help_text="Display title of the rule, e.g. Free Cancellation Tier")
    min_hours_before_checkin = models.DecimalField(
        max_digits=8, decimal_places=2, blank=True, null=True,
        help_text="Hours remaining before check-in must be strictly greater than this (None for no lower limit)"
    )
    max_hours_before_checkin = models.DecimalField(
        max_digits=8, decimal_places=2, blank=True, null=True,
        help_text="Hours remaining before check-in must be less than or equal to this (None for no upper limit)"
    )
    cancellation_fee_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=0.00,
        help_text="Percentage of booking amount deducted as cancellation charge (0-100)"
    )
    refund_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=100.00,
        help_text="Percentage of booking amount refunded to customer (0-100)"
    )
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(default=10, help_text="Evaluation priority order (lower number = evaluated first)")
    description = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['priority', 'id']

    def __str__(self):
        return f"{self.name} (Fee: {self.cancellation_fee_percentage}%, Refund: {self.refund_percentage}%)"


class BookingEmailLog(models.Model):
    STATUS_SENT = 'SENT'
    STATUS_FAILED = 'FAILED'
    STATUS_SKIPPED = 'SKIPPED'
    
    STATUS_CHOICES = (
        (STATUS_SENT, 'Sent'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_SKIPPED, 'Skipped'),
    )

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='email_logs')
    recipient_email = models.EmailField()
    subject = models.CharField(max_length=255)
    pdf_attached = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    error_message = models.TextField(blank=True, null=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-sent_at']

    def __str__(self):
        return f"{self.booking.booking_id} -> {self.recipient_email} [{self.status}]"

