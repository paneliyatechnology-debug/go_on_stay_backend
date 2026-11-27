from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from payments.views import SettlementLedgerListView, AdminAuditLogListView, HostSubscriptionView, HostSubscriptionHistoryView
from staff.views import PortalNavigationDetailView, AdminDashboardView
from hotels.views import AdminDeletedHotelListView, AdminDeletedHotelDetailView, AdminDeletedHotelRestoreView
from core.cloudinary_views import CloudinarySignatureView, CloudinaryConfigCheckView
from core.views import HealthCheckView, ReadinessCheckView

urlpatterns = [
    path('api/', HealthCheckView.as_view(), name='api-root-health'),
    path('api/health/', HealthCheckView.as_view(), name='api-health-check'),
    path('api/health/ready/', ReadinessCheckView.as_view(), name='api-health-ready'),
    path('admin/', admin.site.urls),
    path('api/portal/navigation/', PortalNavigationDetailView.as_view(), name='api-portal-navigation'),
    path('api/admin/dashboard/', AdminDashboardView.as_view(), name='api-admin-dashboard'),
    path('api/admin/deleted-hotels/', AdminDeletedHotelListView.as_view(), name='api-admin-deleted-hotels'),
    path('api/admin/deleted-hotels/<int:pk>/', AdminDeletedHotelDetailView.as_view(), name='api-admin-deleted-hotels-detail'),
    path('api/admin/deleted-hotels/<int:pk>/restore/', AdminDeletedHotelRestoreView.as_view(), name='api-admin-deleted-hotels-restore'),
    path('api/auth/', include('users.urls')),
    path('api/users/', include('users.urls')),
    path('api/locations/', include('hotels.location_urls')),
    path('api/hotels/', include('hotels.urls')),
    path('api/rooms/', include('rooms.urls')),
    path('api/bookings/', include('bookings.urls')),
    path('api/payments/', include('payments.urls')),
    path('payments/', include('payments.urls')),
    path('api/host-subscriptions/', HostSubscriptionView.as_view(), name='api-host-subscriptions-alias'),
    path('host-subscriptions/', HostSubscriptionView.as_view(), name='host-subscriptions-alias-root'),
    path('api/host-subscriptions/history/', HostSubscriptionHistoryView.as_view(), name='api-host-subscriptions-history-alias'),
    path('host-subscriptions/history/', HostSubscriptionHistoryView.as_view(), name='host-subscriptions-history-alias-root'),
    path('api/my-subscription/', HostSubscriptionView.as_view(), name='api-my-subscription-alias'),
    path('my-subscription/', HostSubscriptionView.as_view(), name='my-subscription-alias-root'),
    path('api/host/earnings/', SettlementLedgerListView.as_view(), name='api-host-earnings'),
    path('api/admin/audit-logs/', AdminAuditLogListView.as_view(), name='api-admin-audit-logs'),
    path('api/reviews/', include('reviews.urls')),
    path('api/wishlist/', include('wishlist.urls')),
    path('api/coupons/', include('coupons.urls')),
    path('api/notifications/', include('notifications.urls')),
    path('api/staff/', include('staff.urls')),
    path('api/cloudinary/signature/', CloudinarySignatureView.as_view(), name='api-cloudinary-signature'),
    path('api/cloudinary/status/', CloudinaryConfigCheckView.as_view(), name='api-cloudinary-status'),
    path('api/media/cloudinary/signature/', CloudinarySignatureView.as_view(), name='api-media-cloudinary-signature'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
