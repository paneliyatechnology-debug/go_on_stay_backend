from django.contrib import admin
from .models import Hotel, HotelImage, Amenity

class HotelImageInline(admin.TabularInline):
    model = HotelImage
    extra = 1

from bookings.models import Booking

class BookingInline(admin.TabularInline):
    model = Booking
    extra = 0
    can_delete = False
    readonly_fields = (
        'booking_id', 'guest_name', 'guest_phone', 'guest_email',
        'room', 'room_number', 'check_in', 'check_out', 'total_amount',
        'booking_status', 'payment_status', 'created_at'
    )
    fields = (
        'booking_id', 'guest_name', 'guest_phone', 'guest_email',
        'room', 'room_number', 'check_in', 'check_out', 'total_amount',
        'booking_status', 'payment_status'
    )
    show_change_link = True

@admin.register(Hotel)
class HotelAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'owner', 'star_rating', 'guest_rating', 'is_approved', 'created_at')
    list_filter = ('city', 'star_rating', 'is_approved')
    search_fields = ('name', 'city', 'address', 'owner__username')
    inlines = [HotelImageInline, BookingInline]

@admin.register(Amenity)
class AmenityAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'icon_name')
    list_filter = ('category',)

@admin.register(HotelImage)
class HotelImageAdmin(admin.ModelAdmin):
    list_display = ('hotel', 'caption', 'is_primary', 'created_at')
