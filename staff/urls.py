from django.urls import path
from .views import (
    # Auth APIs
    StaffLoginView, StaffMeView, StaffChangePasswordView,
    StaffForgotPasswordView, StaffResetPasswordView, StaffLogoutView,

    # Staff Management (Admin)
    StaffCreateView, StaffListView, StaffDetailView,
    StaffUpdateView, StaffStatusUpdateView, StaffDepartmentListView,
    StaffPermissionView, StaffAdminResetPasswordView, StaffActivityLogListView,

    # Reservation Department
    StaffBookingListView, StaffBookingDetailView,

    # Refund Department
    StaffRefundListView, StaffRefundDetailView,
    StaffRefundProcessView, StaffRefundHistoryView,

    # Payout Department
    StaffPayoutListView, StaffPayoutDetailView,
    StaffPayoutProcessView, StaffPayoutHistoryView,

    # Customer Support Department
    StaffSupportTicketListView, StaffSupportTicketDetailView,
    StaffSupportTicketUpdateView, StaffSupportTicketNotesView,

    # Hotel Verification Department
    StaffHotelVerificationListView, StaffHotelVerificationDetailView,
    StaffHotelVerificationApproveView, StaffHotelVerificationRejectView,

    # Staff Notifications
    StaffNotificationListView, StaffNotificationReadView, StaffNotificationReadAllView,

    # Staff Dashboard
    StaffDashboardView
)

urlpatterns = [
    # 1. Staff Authentication
    path('login/', StaffLoginView.as_view(), name='staff-login'),
    path('me/', StaffMeView.as_view(), name='staff-me'),
    path('change-password/', StaffChangePasswordView.as_view(), name='staff-change-password'),
    path('forgot-password/', StaffForgotPasswordView.as_view(), name='staff-forgot-password'),
    path('reset-password/', StaffResetPasswordView.as_view(), name='staff-reset-password'),
    path('logout/', StaffLogoutView.as_view(), name='staff-logout'),

    # 2. Staff Management (Admin)
    path('create/', StaffCreateView.as_view(), name='staff-create'),
    path('', StaffListView.as_view(), name='staff-list'),
    path('departments/', StaffDepartmentListView.as_view(), name='staff-departments'),
    path('activities/', StaffActivityLogListView.as_view(), name='staff-activities'),
    path('<int:pk>/', StaffDetailView.as_view(), name='staff-detail'),
    path('<int:pk>/update/', StaffUpdateView.as_view(), name='staff-update'),
    path('<int:pk>/status/', StaffStatusUpdateView.as_view(), name='staff-status-update'),
    path('<int:pk>/permissions/', StaffPermissionView.as_view(), name='staff-permissions-detail'),
    path('<int:pk>/permissions/update/', StaffPermissionView.as_view(), name='staff-permissions-update'),
    path('<int:pk>/reset-password/', StaffAdminResetPasswordView.as_view(), name='staff-admin-reset-password'),

    # 3. Reservation Department – Booking Management
    path('bookings/', StaffBookingListView.as_view(), name='staff-bookings-list'),
    path('bookings/<str:pk>/', StaffBookingDetailView.as_view(), name='staff-bookings-detail'),

    # 4. Refund Department – Refund Management
    path('refunds/', StaffRefundListView.as_view(), name='staff-refunds-list'),
    path('refunds/history/', StaffRefundHistoryView.as_view(), name='staff-refunds-history'),
    path('refunds/<int:pk>/', StaffRefundDetailView.as_view(), name='staff-refunds-detail'),
    path('refunds/<int:pk>/process/', StaffRefundProcessView.as_view(), name='staff-refunds-process'),

    # 5. Payout Department – Hotel Owner Payouts
    path('payouts/', StaffPayoutListView.as_view(), name='staff-payouts-list'),
    path('payouts/history/', StaffPayoutHistoryView.as_view(), name='staff-payouts-history'),
    path('payouts/<int:pk>/', StaffPayoutDetailView.as_view(), name='staff-payouts-detail'),
    path('payouts/<int:pk>/process/', StaffPayoutProcessView.as_view(), name='staff-payouts-process'),

    # 6. Customer Support Department
    path('support/', StaffSupportTicketListView.as_view(), name='staff-support-list'),
    path('support/<int:pk>/', StaffSupportTicketDetailView.as_view(), name='staff-support-detail'),
    path('support/<int:pk>/update/', StaffSupportTicketUpdateView.as_view(), name='staff-support-update'),
    path('support/<int:pk>/notes/', StaffSupportTicketNotesView.as_view(), name='staff-support-notes'),

    # 7. Hotel Verification Department
    path('verifications/', StaffHotelVerificationListView.as_view(), name='staff-verifications-list'),
    path('verifications/<int:pk>/', StaffHotelVerificationDetailView.as_view(), name='staff-verifications-detail'),
    path('verifications/<int:pk>/approve/', StaffHotelVerificationApproveView.as_view(), name='staff-verifications-approve'),
    path('verifications/<int:pk>/reject/', StaffHotelVerificationRejectView.as_view(), name='staff-verifications-reject'),

    # 8. Staff Notifications
    path('notifications/', StaffNotificationListView.as_view(), name='staff-notifications-list'),
    path('notifications/<int:pk>/read/', StaffNotificationReadView.as_view(), name='staff-notifications-read'),
    path('notifications/read-all/', StaffNotificationReadAllView.as_view(), name='staff-notifications-read-all'),

    # 9. Staff Dashboard
    path('dashboard/', StaffDashboardView.as_view(), name='staff-dashboard'),
]
