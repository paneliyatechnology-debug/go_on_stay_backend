from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Notification
from .serializers import NotificationSerializer
from .utils import check_and_create_stay_reminders, check_and_create_payout_notifications

class NotificationListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        user = self.request.user
        check_and_create_stay_reminders(user)
        check_and_create_payout_notifications(user)
        return Notification.objects.filter(recipient=user).order_by('-created_at')

class MarkNotificationReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            notification = Notification.objects.get(pk=pk, recipient=request.user)
            notification.is_read = True
            notification.save()
            return Response({"message": "Notification marked as read.", "is_read": True}, status=status.HTTP_200_OK)
        except Notification.DoesNotExist:
            return Response({"error": "Notification not found."}, status=status.HTTP_404_NOT_FOUND)

    def patch(self, request, pk):
        return self.post(request, pk)

class MarkAllNotificationsReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return Response({"message": "All notifications marked as read."}, status=status.HTTP_200_OK)

class UnreadNotificationCountView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        check_and_create_stay_reminders(request.user)
        check_and_create_payout_notifications(request.user)
        count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return Response({"unread_count": count}, status=status.HTTP_200_OK)

class SimulatePayoutDueView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not (request.user.is_staff or getattr(request.user, 'role', '') in ['ADMIN', 'SUPER_ADMIN']):
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
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        user = request.user if request.user.is_authenticated else None
        if not user:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.first()

        title = request.data.get('title', '🔔 GoOnStay Test Alert!')
        message = request.data.get(
            'message', 
            'Yeh test notification hai! Live stay alerts, reminders aur booking updates successfully work kar rahe hain. 🎉'
        )

        notification = None
        if user:
            notification = Notification.objects.create(
                recipient=user,
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
