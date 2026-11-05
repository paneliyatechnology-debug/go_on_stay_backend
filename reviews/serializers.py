from rest_framework import serializers
from .models import Review

class ReviewSerializer(serializers.ModelSerializer):
    booking_id = serializers.CharField(source='booking.booking_id', read_only=True)
    hotel_name = serializers.CharField(source='hotel.name', read_only=True)
    hotel_city = serializers.CharField(source='hotel.city', read_only=True)
    reviewer_name = serializers.SerializerMethodField()
    reviewer_username = serializers.CharField(source='user.username', read_only=True)
    booking = serializers.CharField(required=False, write_only=False)

    class Meta:
        model = Review
        fields = (
            'id', 'booking', 'booking_id', 'hotel', 'hotel_name', 'hotel_city',
            'user', 'reviewer_name', 'reviewer_username',
            'rating', 'comment', 'owner_response', 'owner_responded_at',
            'status', 'created_at', 'updated_at'
        )
        read_only_fields = (
            'id', 'hotel', 'hotel_name', 'hotel_city', 'user',
            'reviewer_name', 'reviewer_username', 'booking_id',
            'owner_responded_at', 'status', 'created_at', 'updated_at'
        )

    def get_reviewer_name(self, obj):
        if obj.user:
            name = f"{obj.user.first_name} {obj.user.last_name}".strip()
            return name if name else obj.user.username
        return "Verified Guest"

    def validate_rating(self, value):
        try:
            val = int(value)
        except (ValueError, TypeError):
            raise serializers.ValidationError("Rating must be an integer between 1 and 5.")
        if val < 1 or val > 5:
            raise serializers.ValidationError("Rating must be an integer between 1 and 5.")
        return val
