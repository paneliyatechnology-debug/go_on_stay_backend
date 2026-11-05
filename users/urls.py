from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    RegisterView, BecomeHostView, LoginView, HostLoginView, LogoutView, UserProfileView,
    ChangePasswordView, ForgotPasswordView, ResetPasswordView,
    UserListView, UserBlockToggleView, UserRoleChangeView, UserDeleteView,
    CheckEmailView, CheckPhoneView, SendOTPView, VerifyOTPView
)

urlpatterns = [
    # Auth Endpoints
    path('register/', RegisterView.as_view(), name='register'),
    path('signup/', RegisterView.as_view(), name='signup'),
    path('become-host/', BecomeHostView.as_view(), name='become_host'),
    path('host/register/', BecomeHostView.as_view(), name='host_register'),
    path('login/', LoginView.as_view(), name='login'),
    path('signin/', LoginView.as_view(), name='signin'),
    path('host/login/', HostLoginView.as_view(), name='host_login'),
    path('host-login/', HostLoginView.as_view(), name='host_login_alt'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Profile Endpoints
    path('me/', UserProfileView.as_view(), name='user_me'),
    path('profile/', UserProfileView.as_view(), name='profile'),

    # Validation & OTP Endpoints
    path('check-email/', CheckEmailView.as_view(), name='check_email'),
    path('check-phone/', CheckPhoneView.as_view(), name='check_phone'),
    path('send-otp/', SendOTPView.as_view(), name='send_otp'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify_otp'),

    # Password Management
    path('change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('forgot-password/', ForgotPasswordView.as_view(), name='forgot_password'),
    path('reset-password/', ResetPasswordView.as_view(), name='reset_password'),

    # Admin Management Endpoints
    path('all/', UserListView.as_view(), name='user_list'),
    path('<int:pk>/toggle-block/', UserBlockToggleView.as_view(), name='toggle_block_user'),
    path('<int:pk>/block-toggle/', UserBlockToggleView.as_view(), name='block_toggle_user'),
    path('<int:pk>/change-role/', UserRoleChangeView.as_view(), name='change_user_role'),
    path('<int:pk>/delete/', UserDeleteView.as_view(), name='delete_user'),
]

