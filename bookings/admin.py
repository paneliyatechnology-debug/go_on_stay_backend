from django.contrib import admin
from .models import Booking, CancellationPolicyRule

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        'booking_id',
        'hotel',
        'guest_name',
        'guest_phone',
        'room',
        'room_number',
        'check_in',
        'check_out',
        'total_amount',
        'booking_status',
        'payment_status',
        'created_at',
    )
    list_filter = (
        'booking_status',
        'payment_status',
        'hotel',
        'check_in',
        'check_out',
    )
    search_fields = (
        'booking_id',
        'guest_name',
        'guest_email',
        'guest_phone',
        'hotel__name',
        'room_number',
        'customer__username',
        'customer__email',
    )
    ordering = ('-created_at',)
    readonly_fields = (
        'booking_id',
        'created_at',
        'updated_at',
        'confirmed_at',
        'cancelled_at',
        'actual_check_in_at',
        'actual_check_out_at',
        'price_snapshot',
        'cancellation_calculated_at',
        'cancellation_breakdown',
    )
    fieldsets = (
        ('Booking Reference & Parties', {
            'fields': ('booking_id', 'customer', 'hotel', 'room', 'room_number')
        }),
        ('Guest Details', {
            'fields': ('guest_name', 'guest_email', 'guest_phone', 'estimated_arrival_time', 'meal_plan', 'special_requests')
        }),
        ('Stay Dates & Occupancy', {
            'fields': ('check_in', 'check_out', 'number_of_guests', 'number_of_rooms', 'number_of_nights')
        }),
        ('Financials & Payment', {
            'fields': (
                'price_per_night', 'subtotal', 'cleaning_fee', 'service_fee',
                'taxes', 'discount', 'total_amount', 'currency', 'payment_status',
                'booking_status', 'razorpay_order_id', 'price_snapshot'
            )
        }),
        ('Cancellation & Refund Details', {
            'fields': (
                'cancellation_reason', 'cancellation_fee_percentage', 'cancellation_charge',
                'refundable_amount', 'cancellation_calculated_at', 'cancellation_breakdown',
                'applied_cancellation_policy'
            )
        }),
        ('Audit Timestamps', {
            'fields': (
                'created_at', 'updated_at', 'confirmed_at', 'cancelled_at',
                'actual_check_in_at', 'actual_check_out_at', 'action_by_staff', 'expires_at'
            )
        }),
    )

@admin.register(CancellationPolicyRule)
class CancellationPolicyRuleAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'priority',
        'min_hours_before_checkin',
        'max_hours_before_checkin',
        'cancellation_fee_percentage',
        'refund_percentage',
        'is_active',
        'updated_at',
    )
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    ordering = ('priority', 'id')

