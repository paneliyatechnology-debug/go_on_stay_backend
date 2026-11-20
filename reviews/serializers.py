from rest_framework import serializers
from .models import Review

class ReviewSerializer(serializers.ModelSerializer):
    booking_id = serializers.CharField(source='booking.booking_id', read_only=True)
    hotel_name = serializers.CharField(source='hotel.name', read_only=True)
    hotel_city = serializers.CharField(source='hotel.city', read_only=True)
    reviewer_name = serializers.SerializerMethodField()
    reviewer_username = serializers.CharField(source='user.username', read_only=True)
    booking = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    rating = serializers.IntegerField(
        required=True,
        min_value=1,
        max_value=5,
        error_messages={
            'required': 'Rating is required and must be an integer between 1 and 5.',
            'null': 'Rating cannot be null.',
            'min_value': 'Rating must be an integer between 1 and 5.',
            'max_value': 'Rating must be an integer between 1 and 5.',
            'invalid': 'Rating must be an integer between 1 and 5.'
        }
    )
    comment = serializers.CharField(required=False, allow_blank=True, allow_null=True, default='')

    def to_internal_value(self, data):
        if isinstance(data, dict):
            data = data.copy()
            # If booking is passed as dict or int
            if 'booking' in data:
                b_val = data['booking']
                if isinstance(b_val, dict):
                    data['booking'] = str(b_val.get('booking_id') or b_val.get('id') or '')
                elif isinstance(b_val, (int, float)):
                    data['booking'] = str(b_val)
            elif 'booking_id' in data:
                data['booking'] = str(data['booking_id'])
            elif 'bookingId' in data:
                data['booking'] = str(data['bookingId'])
        return super().to_internal_value(data)

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

    def validate_comment(self, value):
        if value is None:
            return ''
        return str(value).strip()
