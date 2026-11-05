from django.urls import path
from .views import ReviewListCreateView, ReviewDetailView, OwnerReviewResponseView

urlpatterns = [
    path('', ReviewListCreateView.as_view(), name='review_list_create'),
    path('<int:pk>/', ReviewDetailView.as_view(), name='review_detail'),
    path('<int:pk>/respond/', OwnerReviewResponseView.as_view(), name='review_owner_response'),
]
