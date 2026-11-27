from django.urls import path
from .views import (
    CreateOrderView, VerifyPaymentView, WebhookView,
    CancelPaymentView, PaymentFailureNotificationView,
    RetryPaymentView, RefundView, RefundProcessView, RefundDetailView,
    RefundStatusView, RefundRetryView, AdminPaymentListView, AdminRefundListView,
    CustomerPayoutDisburseView,
    HostPayoutListCreateView, PlatformSettingsView, SupportTicketListCreateView,
    SupportTicketDetailView, TicketMessageCreateView, CustomerHotelChatView,
    AdminAuditLogListView, CreateHostSubscriptionOrderView, VerifyHostSubscriptionPaymentView,
    HostSubscriptionView, HostSubscriptionHistoryView,
    HostPayoutAccountView, SettlementLedgerListView, SettlementStatementView,
    InitiateHostPayoutView, VerifyPayoutStatusView, ToggleDisputeHoldView,
    ProviderSetupStatusView
)

urlpatterns = [
    path('create-order/', CreateOrderView.as_view(), name='payment-create-order'),
    path('verify/', VerifyPaymentView.as_view(), name='payment-verify'),
    path('cancel-payment/', CancelPaymentView.as_view(), name='payment-cancel'),
    path('cancel/', CancelPaymentView.as_view(), name='payment-cancel-alias'),
    path('payment-failed/', PaymentFailureNotificationView.as_view(), name='payment-failed'),
    path('failed/', PaymentFailureNotificationView.as_view(), name='payment-failed-alias'),
    
    # Host Subscription Management APIs
    path('host-subscriptions/', HostSubscriptionView.as_view(), name='host-subscriptions'),
    path('host-subscription/', HostSubscriptionView.as_view(), name='host-subscription-alias'),
    path('host-subscriptions/current/', HostSubscriptionView.as_view(), name='host-subscription-current'),
    path('host-subscriptions/history/', HostSubscriptionHistoryView.as_view(), name='host-subscriptions-history'),
    path('subscription-history/', HostSubscriptionHistoryView.as_view(), name='subscription-history'),
    path('history/', HostSubscriptionHistoryView.as_view(), name='subscription-history-short'),
    path('my-subscription/', HostSubscriptionView.as_view(), name='my-subscription'),
    path('subscriptions/', HostSubscriptionView.as_view(), name='host-subscriptions-alias2'),
    path('subscription/', HostSubscriptionView.as_view(), name='host-subscription-alias3'),
    path('create-host-subscription-order/', CreateHostSubscriptionOrderView.as_view(), name='host-subscription-create-order'),
    path('verify-host-subscription/', VerifyHostSubscriptionPaymentView.as_view(), name='host-subscription-verify'),
    path('webhook/', WebhookView.as_view(), name='payment-webhook'),
    path('retry/', RetryPaymentView.as_view(), name='payment-retry'),
    
    # RazorpayX Customer Bank Payout API (NEFT / UPI Sandbox Integration)
    path('payouts/customer/', CustomerPayoutDisburseView.as_view(), name='customer-bank-payout'),
    path('payouts/customer/<str:lookup>/', CustomerPayoutDisburseView.as_view(), name='customer-bank-payout-detail'),
    path('razorpayx/payout/', CustomerPayoutDisburseView.as_view(), name='razorpayx-customer-payout'),

    # Complete Refund API System
    path('refund/', RefundView.as_view(), name='payment-refund'),
    path('refund/process/', RefundProcessView.as_view(), name='payment-refund-process'),
    path('refunds/', AdminRefundListView.as_view(), name='refund-list-alias'),
    path('refunds/<str:lookup>/', RefundDetailView.as_view(), name='refund-detail'),
    path('refunds/<str:lookup>/status/', RefundStatusView.as_view(), name='refund-status'),
    path('refunds/<str:lookup>/retry/', RefundRetryView.as_view(), name='refund-retry'),
    
    # Settlement & Payouts Architecture
    path('payout-account/', HostPayoutAccountView.as_view(), name='host-payout-account'),
    path('settlements/', SettlementLedgerListView.as_view(), name='settlement-ledger'),
    path('host/earnings/', SettlementLedgerListView.as_view(), name='host-earnings-alias'),
    path('settlement-statement/', SettlementStatementView.as_view(), name='settlement-statement'),
    path('payouts/', HostPayoutListCreateView.as_view(), name='host-payouts'),
    path('admin/payouts/initiate/', InitiateHostPayoutView.as_view(), name='admin-payout-initiate'),
    path('admin/payouts/<str:payout_id>/verify/', VerifyPayoutStatusView.as_view(), name='admin-payout-verify'),
    path('admin/earnings/toggle-dispute/', ToggleDisputeHoldView.as_view(), name='admin-toggle-dispute'),
    path('admin/provider-setup-status/', ProviderSetupStatusView.as_view(), name='admin-provider-setup-status'),
    path('settings/', PlatformSettingsView.as_view(), name='platform-settings'),
    path('platform-settings/', PlatformSettingsView.as_view(), name='platform-settings-alias'),

    # Support Tickets & Messaging
    path('support-tickets/', SupportTicketListCreateView.as_view(), name='support-tickets'),
    path('support-tickets/<int:pk>/', SupportTicketDetailView.as_view(), name='support-ticket-detail'),
    path('support-tickets/<int:pk>/messages/', TicketMessageCreateView.as_view(), name='support-ticket-messages'),
    path('chat/<str:booking_id>/', CustomerHotelChatView.as_view(), name='customer-hotel-chat'),

    # Admin Audit Endpoints
    path('admin/all/', AdminPaymentListView.as_view(), name='admin-payment-list'),
    path('admin/refunds/', AdminRefundListView.as_view(), name='admin-refund-list'),
    path('admin/audit-logs/', AdminAuditLogListView.as_view(), name='admin-audit-logs'),
]
