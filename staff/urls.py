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
    StaffBookingCheckInView, StaffBookingCheckOutView,
    StaffRoomListView, StaffGuestListView,

    # Refund Department
    StaffRefundListView, StaffRefundDetailView,
    StaffRefundProcessView, StaffRefundHistoryView,
    StaffRefundEligibilityCheckView,

    # Payout Department
    StaffPayoutListView, StaffPayoutDetailView,
    StaffPayoutProcessView, StaffPayoutHistoryView,
    StaffEscrowListView, StaffSettlementListView,

    # Customer Support Department
    StaffSupportTicketListView, StaffSupportTicketDetailView,
    StaffSupportTicketUpdateView, StaffSupportTicketNotesView,
    StaffSupportTicketMessageView,

    # Hotel Verification Department
    StaffHotelVerificationListView, StaffHotelVerificationDetailView,
    StaffHotelVerificationApproveView, StaffHotelVerificationRejectView,
    StaffHotelVerificationHistoryView, StaffHotelDocumentsListView,

    # Staff Notifications
    StaffNotificationListView, StaffNotificationReadView, StaffNotificationClickView, StaffNotificationReadAllView,

    # Staff Dashboard & Dedicated Role Portals
    StaffDashboardView, PortalNavigationDetailView, AdminDashboardView,
    ReservationDashboardView, CustomerSupportDashboardView,
    RefundsClaimsDashboardView, PayoutEscrowDashboardView,
    HotelVerificationDashboardView
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

    # 3. Reservation Department – Booking Management & Operations
    path('bookings/', StaffBookingListView.as_view(), name='staff-bookings-list'),
    path('bookings/<str:pk>/', StaffBookingDetailView.as_view(), name='staff-bookings-detail'),
    path('bookings/<str:pk>/check-in/', StaffBookingCheckInView.as_view(), name='staff-bookings-checkin'),
    path('bookings/<str:pk>/check-out/', StaffBookingCheckOutView.as_view(), name='staff-bookings-checkout'),
    path('rooms/', StaffRoomListView.as_view(), name='staff-rooms-list'),
    path('guests/', StaffGuestListView.as_view(), name='staff-guests-list'),

    # 4. Refund Department – Refund Management & Gateway Execution
    path('refunds/', StaffRefundListView.as_view(), name='staff-refunds-list'),
    path('refunds/history/', StaffRefundHistoryView.as_view(), name='staff-refunds-history'),
    path('refunds/<int:pk>/', StaffRefundDetailView.as_view(), name='staff-refunds-detail'),
    path('refunds/<int:pk>/eligibility/', StaffRefundEligibilityCheckView.as_view(), name='staff-refunds-eligibility'),
    path('refunds/<int:pk>/process/', StaffRefundProcessView.as_view(), name='staff-refunds-process'),

    # 5. Payout Department – Hotel Owner Payouts, Escrow & Settlements
    path('payouts/', StaffPayoutListView.as_view(), name='staff-payouts-list'),
    path('payouts/history/', StaffPayoutHistoryView.as_view(), name='staff-payouts-history'),
    path('payouts/escrow/', StaffEscrowListView.as_view(), name='staff-payouts-escrow'),
    path('payouts/settlements/', StaffSettlementListView.as_view(), name='staff-payouts-settlements'),
    path('payouts/<int:pk>/', StaffPayoutDetailView.as_view(), name='staff-payouts-detail'),
    path('payouts/<int:pk>/process/', StaffPayoutProcessView.as_view(), name='staff-payouts-process'),

    # 6. Customer Support Department – Tickets, Inquiries & Internal Notes
    path('support/', StaffSupportTicketListView.as_view(), name='staff-support-list'),
    path('support/<int:pk>/', StaffSupportTicketDetailView.as_view(), name='staff-support-detail'),
    path('support/<int:pk>/update/', StaffSupportTicketUpdateView.as_view(), name='staff-support-update'),
    path('support/<int:pk>/notes/', StaffSupportTicketNotesView.as_view(), name='staff-support-notes'),
    path('support/<int:pk>/messages/', StaffSupportTicketMessageView.as_view(), name='staff-support-messages'),

    # 7. Hotel Verification Department – Applications, Documents & Approvals
    path('verifications/', StaffHotelVerificationListView.as_view(), name='staff-verifications-list'),
    path('verifications/history/', StaffHotelVerificationHistoryView.as_view(), name='staff-verifications-history'),
    path('verifications/documents/', StaffHotelDocumentsListView.as_view(), name='staff-verifications-documents'),
    path('verifications/<int:pk>/', StaffHotelVerificationDetailView.as_view(), name='staff-verifications-detail'),
    path('verifications/<int:pk>/approve/', StaffHotelVerificationApproveView.as_view(), name='staff-verifications-approve'),
    path('verifications/<int:pk>/reject/', StaffHotelVerificationRejectView.as_view(), name='staff-verifications-reject'),

    # 8. Staff Notifications
    path('notifications/', StaffNotificationListView.as_view(), name='staff-notifications-list'),
    path('notifications/<int:pk>/read/', StaffNotificationReadView.as_view(), name='staff-notifications-read'),
    path('notifications/<int:pk>/click/', StaffNotificationClickView.as_view(), name='staff-notifications-click'),
    path('notifications/read-all/', StaffNotificationReadAllView.as_view(), name='staff-notifications-read-all'),

    # Staff Dashboard & Dedicated Role Portals
    path('dashboard/', StaffDashboardView.as_view(), name='staff-dashboard'),
    path('portal/navigation/', PortalNavigationDetailView.as_view(), name='staff-portal-navigation'),
    path('reservation/dashboard/', ReservationDashboardView.as_view(), name='staff-reservation-dashboard'),
    path('support/dashboard/', CustomerSupportDashboardView.as_view(), name='staff-support-dashboard'),
    path('refunds/dashboard/', RefundsClaimsDashboardView.as_view(), name='staff-refunds-dashboard'),
    path('payouts/dashboard/', PayoutEscrowDashboardView.as_view(), name='staff-payouts-dashboard'),
    path('verification/dashboard/', HotelVerificationDashboardView.as_view(), name='staff-verification-dashboard'),
]
