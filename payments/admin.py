from django.contrib import admin
from django.db.models import Max
from .models import Payment, Refund, WebhookEvent, HostEarning, HostPayout, HostPayoutAccount, PlatformSetting, AuditLog

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        'payment_id_display', 'razorpay_order_id', 'booking_id_display',
        'customer_display', 'hotel_display', 'amount_display', 'status', 'paid_at', 'created_at'
    )
    list_filter = ('status', 'currency', 'created_at')
    search_fields = ('razorpay_payment_id', 'razorpay_order_id', 'booking__booking_id', 'user__username', 'user__email')
    readonly_fields = ('created_at', 'updated_at')

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related('booking', 'booking__hotel', 'user')
        # Ensure only 1 canonical payment entry per booking is shown in admin panel (removes ghost duplicates)
        confirmed_booking_ids = Payment.objects.filter(
            status__in=[Payment.STATUS_CAPTURED, Payment.STATUS_REFUNDED, Payment.STATUS_PARTIALLY_REFUNDED]
        ).values_list('booking_id', flat=True)

        # Exclude draft CREATED records if booking has a confirmed or refunded payment
        qs = qs.exclude(
            booking_id__in=confirmed_booking_ids,
            status=Payment.STATUS_CREATED
        )

        # For bookings with multiple draft CREATED payments, display only the latest one
        latest_ids = qs.values('booking_id').annotate(max_id=Max('id')).values_list('max_id', flat=True)
        return qs.filter(id__in=latest_ids).order_by('-created_at')

    def payment_id_display(self, obj):
        return obj.razorpay_payment_id if obj.razorpay_payment_id else "— (Pending)"
    payment_id_display.short_description = "Payment ID"

    def booking_id_display(self, obj):
        return obj.booking.booking_id if obj.booking else "—"
    booking_id_display.short_description = "Booking ID"

    def customer_display(self, obj):
        return obj.user.get_full_name() or obj.user.username if obj.user else "—"
    customer_display.short_description = "Customer"

    def hotel_display(self, obj):
        return obj.booking.hotel.name if (obj.booking and obj.booking.hotel) else "—"
    hotel_display.short_description = "Hotel"

    def amount_display(self, obj):
        return f"₹{obj.amount}"
    amount_display.short_description = "Amount"


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ('razorpay_refund_id', 'booking_id_display', 'payment_id_display', 'amount', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('razorpay_refund_id', 'razorpay_payment_id', 'booking__booking_id')
    readonly_fields = ('created_at',)

    def booking_id_display(self, obj):
        return obj.booking.booking_id if obj.booking else "—"
    booking_id_display.short_description = "Booking ID"

    def payment_id_display(self, obj):
        return obj.razorpay_payment_id or (obj.payment.razorpay_payment_id if obj.payment else "—")
    payment_id_display.short_description = "Payment ID"


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ('event_id', 'event_type', 'processed', 'processed_at', 'created_at')
    list_filter = ('processed', 'event_type', 'created_at')
    search_fields = ('event_id', 'event_type')
    readonly_fields = ('created_at',)


@admin.register(HostEarning)
class HostEarningAdmin(admin.ModelAdmin):
    list_display = (
        'payment_id_display', 'booking_id_display', 'hotel_display',
        'host', 'gross_amount', 'platform_fee', 'net_amount', 'status', 'created_at'
    )
    list_filter = ('status', 'created_at')
    search_fields = ('host__username', 'booking__booking_id', 'booking__payments__razorpay_payment_id')
    readonly_fields = ('created_at',)

    def payment_id_display(self, obj):
        if not obj.booking:
            return "—"
        captured = obj.booking.payments.filter(status='CAPTURED').first() or obj.booking.payments.first()
        return captured.razorpay_payment_id if (captured and captured.razorpay_payment_id) else "—"
    payment_id_display.short_description = "Payment ID"

    def booking_id_display(self, obj):
        return obj.booking.booking_id if obj.booking else "—"
    booking_id_display.short_description = "Booking ID"

    def hotel_display(self, obj):
        return obj.booking.hotel.name if (obj.booking and obj.booking.hotel) else "—"
    hotel_display.short_description = "Hotel"


@admin.register(HostPayout)
class HostPayoutAdmin(admin.ModelAdmin):
    list_display = ('payout_id', 'host', 'payout_account', 'amount', 'currency', 'status', 'provider_mode', 'created_at', 'processed_at')
    list_filter = ('status', 'provider_mode', 'created_at')
    search_fields = ('payout_id', 'host__username', 'provider_payout_id', 'bank_reference')
    readonly_fields = ('created_at', 'processed_at')


@admin.register(HostPayoutAccount)
class HostPayoutAccountAdmin(admin.ModelAdmin):
    list_display = ('user', 'payout_method', 'account_holder_name', 'bank_name', 'destination_summary', 'is_verified')
    list_filter = ('payout_method', 'is_verified')
    search_fields = ('user__username', 'user__email', 'account_holder_name')


@admin.register(PlatformSetting)
class PlatformSettingAdmin(admin.ModelAdmin):
    list_display = ('commission_percentage', 'gst_tax_percentage', 'payout_hold_days', 'payout_provider_mode', 'updated_at')


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'entity_type', 'entity_id', 'ip_address', 'created_at')
    list_filter = ('action', 'entity_type', 'created_at')
    search_fields = ('action', 'entity_type', 'entity_id', 'user__username')
    readonly_fields = ('created_at',)

