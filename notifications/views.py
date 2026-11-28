from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Notification
from .serializers import NotificationSerializer
from .utils import check_and_create_stay_reminders, check_and_create_payout_notifications
from staff.permissions import is_platform_admin

class NotificationListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        user = self.request.user
        check_and_create_stay_reminders(user)
        check_and_create_payout_notifications(user)
        return Notification.objects.filter(recipient=user).order_by('-created_at')

from .navigation import resolve_notification_navigation

class MarkNotificationReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        is_admin = request.user.is_superuser or request.user.is_staff or str(getattr(request.user, 'role', '')).upper() in ['ADMIN', 'SUPER_ADMIN']
        if is_admin:
            notification = Notification.objects.filter(pk=pk).first()
        else:
            notification = Notification.objects.filter(pk=pk, recipient=request.user).first()

        if not notification:
            user_role = str(getattr(request.user, 'role', 'CUSTOMER')).upper()
            if is_admin:
                fb = '/admin/dashboard'
            elif user_role == 'HOTEL_OWNER':
                fb = '/owner/dashboard'
            elif user_role == 'STAFF':
                fb = '/staff/reservation'
            else:
                fb = '/customer/dashboard'
            return Response({"error": "Notification not found.", "fallback_url": fb}, status=status.HTTP_404_NOT_FOUND)

        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=['is_read'])

        nav = resolve_notification_navigation(notification, request.user)
        return Response({
            "success": True,
            "message": "Notification marked as read.",
            "is_read": True,
            "notification_id": notification.id,
            "target_url": nav.get('target_url', ''),
            "url": nav.get('target_url', ''),
            "link": nav.get('target_url', ''),
            "path": nav.get('target_url', ''),
            "route": nav.get('target_url', ''),
            "target_entity_type": nav.get('target_entity_type', ''),
            "target_entity_id": nav.get('target_entity_id', ''),
            "entity_type": nav.get('target_entity_type', ''),
            "entity_id": nav.get('target_entity_id', ''),
            "fallback_url": nav.get('fallback_url', ''),
            "action": nav.get('action', ''),
            "record_exists": nav.get('record_exists', True),
            "navigation": nav
        }, status=status.HTTP_200_OK)

    def get(self, request, pk):
        return self.post(request, pk)

    def patch(self, request, pk):
        return self.post(request, pk)

class NotificationClickView(APIView):
    """
    POST /api/notifications/<id>/click/
    GET  /api/notifications/<id>/click/
    PATCH /api/notifications/<id>/click/
    Handles smart notification click-through:
    - Marks the notification as read.
    - Resolves role-aware destination, exact entity identifier, and record verification.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        is_admin = request.user.is_superuser or request.user.is_staff or str(getattr(request.user, 'role', '')).upper() in ['ADMIN', 'SUPER_ADMIN']
        if is_admin:
            notification = Notification.objects.filter(pk=pk).first()
        else:
            notification = Notification.objects.filter(pk=pk, recipient=request.user).first()

        if not notification:
            user_role = str(getattr(request.user, 'role', 'CUSTOMER')).upper()
            if is_admin:
                fb = '/admin/dashboard'
            elif user_role == 'HOTEL_OWNER':
                fb = '/owner/dashboard'
            elif user_role == 'STAFF':
                fb = '/staff/reservation'
            else:
                fb = '/customer/dashboard'
            return Response({
                "success": False,
                "error": "Notification not found.",
                "fallback_url": fb,
                "target_url": fb,
                "url": fb
            }, status=status.HTTP_404_NOT_FOUND)

        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=['is_read'])

        nav = resolve_notification_navigation(notification, request.user)
        return Response({
            "success": True,
            "notification_id": notification.id,
            "is_read": True,
            "target_url": nav.get('target_url', ''),
            "url": nav.get('target_url', ''),
            "link": nav.get('target_url', ''),
            "path": nav.get('target_url', ''),
            "route": nav.get('target_url', ''),
            "target_entity_type": nav.get('target_entity_type', ''),
            "target_entity_id": nav.get('target_entity_id', ''),
            "entity_type": nav.get('target_entity_type', ''),
            "entity_id": nav.get('target_entity_id', ''),
            "fallback_url": nav.get('fallback_url', ''),
            "action": nav.get('action', ''),
            "record_exists": nav.get('record_exists', True),
            "navigation": nav
        }, status=status.HTTP_200_OK)

    def get(self, request, pk):
        return self.post(request, pk)

    def patch(self, request, pk):
        return self.post(request, pk)

class MarkAllNotificationsReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return Response({"message": "All notifications marked as read."}, status=status.HTTP_200_OK)

class UnreadNotificationCountView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        if not request.user or not request.user.is_authenticated:
            return Response({"unread_count": 0}, status=status.HTTP_200_OK)
        count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return Response({"unread_count": count}, status=status.HTTP_200_OK)

class SimulatePayoutDueView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not is_platform_admin(request.user):
            return Response({"error": "Admin permission required."}, status=status.HTTP_403_FORBIDDEN)
        
        from payments.models import HostEarning
        from django.utils import timezone
        now = timezone.now()
        
        hotel_id = request.data.get('hotel_id')
        
        # Select earnings to mature: if a specific hotel is requested, mature that hotel's on-hold earnings;
        # otherwise mature all non-paid ON_HOLD earnings across all hotels.
        qs = HostEarning.objects.filter(status=HostEarning.STATUS_ON_HOLD)
        if hotel_id and str(hotel_id) != 'ALL':
            hotel_qs = qs.filter(booking__hotel_id=hotel_id)
            if hotel_qs.exists():
                qs = hotel_qs

        # If no ON_HOLD exists, also check non-paid, non-disputed earnings
        if not qs.exists():
            qs = HostEarning.objects.exclude(status=HostEarning.STATUS_PAID).filter(is_disputed=False)

        count = 0
        for earning in qs:
            earning.hold_until = now - timezone.timedelta(minutes=5)
            earning.status = HostEarning.STATUS_ELIGIBLE
            earning.hold_reason = ''
            earning.save(update_fields=['hold_until', 'status', 'hold_reason', 'updated_at'])
            count += 1

        # Reset any alert from today so a fresh notification triggers
        Notification.objects.filter(
            recipient=request.user,
            notification_type=Notification.TYPE_PAYOUT_DUE
        ).delete()

        check_and_create_payout_notifications(request.user)

        notif = Notification.objects.filter(
            recipient=request.user,
            notification_type=Notification.TYPE_PAYOUT_DUE
        ).first()

        return Response({
            "message": f"Payout day simulated successfully! {count} holding(s) released and ready for payout.",
            "matured_count": count,
            "notification": NotificationSerializer(notif).data if notif else None
        }, status=status.HTTP_200_OK)

class SendTestNotificationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from payments.views import is_platform_admin
        if not is_platform_admin(request.user):
            return Response(
                {"error": "Permission denied. Only Platform Administrators can dispatch test notifications."},
                status=status.HTTP_403_FORBIDDEN
            )

        recipient = request.user
        recipient_id = request.data.get('recipient_id')
        if recipient_id:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            target_user = User.objects.filter(id=recipient_id).first()
            if target_user:
                recipient = target_user

        title = request.data.get('title', '🔔 GoOnStay Test Alert!')
        message = request.data.get(
            'message', 
            'Yeh test notification hai! Live stay alerts, reminders aur booking updates successfully work kar rahe hain. 🎉'
        )

        notification = Notification.objects.create(
            recipient=recipient,
            title=title,
            message=message,
            notification_type=Notification.TYPE_GENERAL
        )

        return Response({
            "message": "Test notification created successfully!",
            "notification": NotificationSerializer(notification).data if notification else None,
            "title": title,
            "body": message
        }, status=status.HTTP_201_CREATED)
