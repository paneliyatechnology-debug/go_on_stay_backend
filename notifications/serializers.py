from rest_framework import serializers
from .models import Notification
from .navigation import resolve_notification_navigation

class NotificationSerializer(serializers.ModelSerializer):
    booking_id = serializers.CharField(source='booking.booking_id', read_only=True)
    hotel_name = serializers.CharField(source='booking.hotel.name', read_only=True)
    target_url = serializers.SerializerMethodField()
    target_entity_type = serializers.SerializerMethodField()
    target_entity_id = serializers.SerializerMethodField()
    fallback_url = serializers.SerializerMethodField()
    navigation_metadata = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            'id', 'recipient', 'booking', 'booking_id', 'hotel_name',
            'title', 'message', 'notification_type', 'is_read', 'created_at',
            'target_url', 'target_entity_type', 'target_entity_id', 'fallback_url', 'navigation_metadata'
        ]
        read_only_fields = ['id', 'recipient', 'created_at']

    def _get_nav(self, obj):
        if not hasattr(obj, '_cached_navigation'):
            request = self.context.get('request')
            user = request.user if request and hasattr(request, 'user') and request.user.is_authenticated else obj.recipient
            obj._cached_navigation = resolve_notification_navigation(notification=obj, user=user)
        return obj._cached_navigation

    def get_target_url(self, obj):
        return self._get_nav(obj).get('target_url', '')

    def get_target_entity_type(self, obj):
        return self._get_nav(obj).get('target_entity_type', '')

    def get_target_entity_id(self, obj):
        return self._get_nav(obj).get('target_entity_id', '')

    def get_fallback_url(self, obj):
        return self._get_nav(obj).get('fallback_url', '')

    def get_navigation_metadata(self, obj):
        return self._get_nav(obj)
