from rest_framework import serializers
from django.utils import timezone
from .models import Coupon, CouponUsage


class CouponSerializer(serializers.ModelSerializer):
    is_currently_valid = serializers.SerializerMethodField()
    days_remaining = serializers.SerializerMethodField()
    campaign_badge = serializers.SerializerMethodField()
    status_label = serializers.SerializerMethodField()
    valid_dates_label = serializers.SerializerMethodField()
    festival_name = serializers.SerializerMethodField()

    class Meta:
        model = Coupon
        fields = '__all__'

    def get_is_currently_valid(self, obj):
        today = timezone.now().date()
        return bool(obj.is_active and obj.valid_from <= today <= obj.valid_until)

    def get_days_remaining(self, obj):
        today = timezone.now().date()
        if obj.valid_until < today:
            return 0
        return (obj.valid_until - today).days

    def get_campaign_badge(self, obj):
        if obj.campaign_type == Coupon.CAMPAIGN_FESTIVE:
            return 'Festive Special'
        elif obj.campaign_type == Coupon.CAMPAIGN_SEASONAL:
            return 'Seasonal Offer'
        elif obj.campaign_type == Coupon.CAMPAIGN_FIRST_BOOKING or obj.is_first_booking_only:
            return 'New User Welcome'
        return 'Special Offer'

    def get_status_label(self, obj):
        today = timezone.now().date()
        if not obj.is_active:
            return 'DEACTIVATED'
        if obj.valid_until < today:
            return 'EXPIRED'
        if obj.valid_from > today:
            return 'UPCOMING'
        return 'ACTIVE'

    def get_valid_dates_label(self, obj):
        return f"Valid from {obj.valid_from.strftime('%d %b %Y')} to {obj.valid_until.strftime('%d %b %Y')}"

    def get_festival_name(self, obj):
        return obj.campaign_name or obj.title or ''


class CouponUsageSerializer(serializers.ModelSerializer):
    coupon_code = serializers.CharField(source='coupon.code', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = CouponUsage
        fields = ['id', 'coupon', 'coupon_code', 'user', 'username', 'booking', 'discount_applied', 'used_at']
        read_only_fields = ['id', 'used_at']
