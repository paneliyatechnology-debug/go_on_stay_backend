from django.urls import path
from .views import (
    ValidateCouponView, CouponListCreateView,
    CouponDetailView, ActiveCouponsListView, CouponToggleStatusView
)

urlpatterns = [
    path('apply/', ValidateCouponView.as_view(), name='apply_coupon'),
    path('validate/', ValidateCouponView.as_view(), name='validate_coupon'),
    path('available/', ActiveCouponsListView.as_view(), name='available_coupons'),
    path('active/', ActiveCouponsListView.as_view(), name='active_coupons'),
    path('<int:pk>/toggle/', CouponToggleStatusView.as_view(), name='toggle_coupon_status_alias'),
    path('<int:pk>/toggle-status/', CouponToggleStatusView.as_view(), name='toggle_coupon_status'),
    path('', CouponListCreateView.as_view(), name='coupon_list_create'),
    path('<int:pk>/', CouponDetailView.as_view(), name='coupon_detail'),
]
