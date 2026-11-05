from django.urls import path
from .views import (
    NotificationListView, MarkNotificationReadView,
    MarkAllNotificationsReadView, UnreadNotificationCountView,
    SendTestNotificationView, SimulatePayoutDueView
)

urlpatterns = [
    path('', NotificationListView.as_view(), name='notification_list'),
    path('unread-count/', UnreadNotificationCountView.as_view(), name='notification_unread_count'),
    path('read-all/', MarkAllNotificationsReadView.as_view(), name='notification_read_all'),
    path('mark-all-read/', MarkAllNotificationsReadView.as_view(), name='notification_mark_all_read'),
    path('send-test/', SendTestNotificationView.as_view(), name='notification_send_test'),
    path('simulate-payout-due/', SimulatePayoutDueView.as_view(), name='notification_simulate_payout_due'),
    path('<int:pk>/read/', MarkNotificationReadView.as_view(), name='notification_mark_read'),
]
