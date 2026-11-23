import uuid
import logging
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.db.models import F
from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate, get_user_model
from .serializers import (
    UserSerializer, RegisterSerializer,
    UserProfileUpdateSerializer, ChangePasswordSerializer,
    ForgotPasswordSerializer, ResetPasswordSerializer
)
from util.otp import generate_otp, hash_otp
from services.email_service import send_otp_email
from .models import EmailOTP

logger = logging.getLogger(__name__)

User = get_user_model()

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = 'register'

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)
        return Response({
            "user": UserSerializer(user).data,
            "access": access_token,
            "refresh": refresh_token,
            "token": access_token,
            "message": "User registered successfully."
        }, status=status.HTTP_201_CREATED)

class BecomeHostView(APIView):
    """
    Become a Host API:
    - If unauthenticated: Registers a new user with role HOTEL_OWNER.
    - If authenticated: Upgrades existing customer account to HOTEL_OWNER, saving bank/payout details if provided.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        from payments.models import HostPayoutAccount
        from django.utils import timezone
        import uuid

        # 1. Existing authenticated user upgrading to Host
        if request.user and request.user.is_authenticated:
            from util.validators import (
                clean_indian_phone, validate_indian_bank_account,
                validate_indian_ifsc, validate_indian_upi
            )
            user = request.user
            user.role = User.ROLE_HOTEL_OWNER
            phone = request.data.get('phone_number') or request.data.get('phone')
            if phone and not user.phone_number:
                user.phone_number = clean_indian_phone(phone)
            user.save()

            # Optional payout details
            payout_method = request.data.get('payout_method')
            account_holder_name = request.data.get('account_holder_name')
            bank_name = request.data.get('bank_name')
            account_number = request.data.get('account_number')
            ifsc_code = request.data.get('ifsc_code')
            upi_id = request.data.get('upi_id')

            if account_number or upi_id:
                clean_acc = validate_indian_bank_account(account_number) if account_number else None
                clean_ifsc = validate_indian_ifsc(ifsc_code) if ifsc_code else None
                clean_upi = validate_indian_upi(upi_id) if upi_id else None

                HostPayoutAccount.objects.update_or_create(
                    user=user,
                    defaults={
                        'payout_method': payout_method or (HostPayoutAccount.METHOD_UPI if clean_upi else HostPayoutAccount.METHOD_BANK),
                        'account_holder_name': account_holder_name or user.get_full_name() or user.username,
                        'bank_name': bank_name or 'Bank',
                        'account_number': clean_acc,
                        'ifsc_code': clean_ifsc,
                        'upi_id': clean_upi,
                        'is_verified': True,
                        'verification_status': HostPayoutAccount.STATUS_VERIFIED,
                        'fund_account_id': f"fa_host_{uuid.uuid4().hex[:10]}",
                        'verified_at': timezone.now()
                    }
                )

            # Optional Hotel Property Info (Step 1)
            raw_hname = request.data.get('hotel_name') or request.data.get('name') or request.data.get('hotelName')
            raw_addr = (
                request.data.get('address') or
                request.data.get('full_property_address') or
                request.data.get('property_address') or
                request.data.get('propertyAddress')
            )
            raw_city = (
                request.data.get('city') or
                request.data.get('destination_city') or
                request.data.get('destination') or
                request.data.get('destinationCity')
            )
            raw_prop_type = request.data.get('property_type')

            created_hotel = None
            if raw_hname or raw_addr:
                from util.validators import validate_hotel_name, validate_hotel_address
                from hotels.models import Hotel

                clean_hname = validate_hotel_name(raw_hname) if raw_hname else f"{user.get_full_name() or user.username}'s Hotel"
                clean_addr = validate_hotel_address(raw_addr) if raw_addr else 'Plot 1, Main Road'
                clean_city = 'Jaipur'
                clean_state = 'Rajasthan'
                if raw_city:
                    if ',' in raw_city:
                        parts = [p.strip() for p in raw_city.split(',')]
                        clean_city = parts[0]
                        clean_state = parts[1] if len(parts) > 1 else 'Rajasthan'
                    else:
                        clean_city = raw_city

                prop_type = (raw_prop_type or 'HOTEL').upper()
                valid_types = [t[0] for t in Hotel.PROPERTY_TYPE_CHOICES]
                if prop_type not in valid_types:
                    prop_type = Hotel.PROPERTY_TYPE_HOTEL

                created_hotel = Hotel.objects.create(
                    owner=user,
                    name=clean_hname,
                    property_type=prop_type,
                    city=clean_city,
                    state=clean_state,
                    address=clean_addr,
                    status=Hotel.STATUS_SUBMITTED,
                    is_approved=False
                )

            resp_data = {
                "user": UserSerializer(user).data,
                "message": "Congratulations! Your account has been upgraded to Hotel Host / Owner.",
                "role": user.role
            }
            if created_hotel:
                from hotels.serializers import HotelSerializer
                resp_data["hotel"] = HotelSerializer(created_hotel).data
            return Response(resp_data, status=status.HTTP_200_OK)

        # 2. New user registering as Host
        data = request.data.copy()
        data['role'] = User.ROLE_HOTEL_OWNER
        serializer = RegisterSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)
        resp_data = {
            "user": UserSerializer(user).data,
            "access": access_token,
            "refresh": refresh_token,
            "token": access_token,
            "message": "Host account registered successfully."
        }
        if getattr(user, '_created_hotel', None):
            from hotels.serializers import HotelSerializer
            resp_data["hotel"] = HotelSerializer(user._created_hotel).data
        return Response(resp_data, status=status.HTTP_201_CREATED)

class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = 'login'

    def post(self, request):
        username = (
            request.data.get('username') or
            request.data.get('email') or
            request.data.get('phone_number') or
            request.data.get('phone') or
            request.data.get('identifier')
        )
        password = request.data.get('password')

        if not username or not password:
            return Response({"error": "Username/Email and password are required."}, status=status.HTTP_400_BAD_REQUEST)

        username = str(username).strip()

        # Allow login by email, username, or mobile number
        import re
        from django.db.models import Q
        clean_input = re.sub(r'[\s\-\(\)]', '', username)
        user_obj = (
            User.objects.filter(email__iexact=username).first() or
            User.objects.filter(username__iexact=username).first() or
            User.objects.filter(phone_number__iexact=username).first() or
            (User.objects.filter(phone_number__endswith=clean_input[-10:]).first() if len(clean_input) >= 10 else None)
        )
        if user_obj:
            username = user_obj.username

        user = authenticate(request=request, username=username, password=password)

        if not user:
            candidate = user_obj or User.objects.filter(Q(username__iexact=username) | Q(email__iexact=username)).first()
            if candidate and candidate.check_password(password) and not candidate.is_active:
                return Response({
                    "detail": "Your account has been deactivated. Please contact support.",
                    "error": "Your account has been deactivated. Please contact support."
                }, status=status.HTTP_403_FORBIDDEN)

            return Response({
                "detail": "No active account found with the given credentials",
                "error": "No active account found with the given credentials"
            }, status=status.HTTP_401_UNAUTHORIZED)

        if not user.is_active:
            return Response({
                "detail": "Your account has been deactivated. Please contact support.",
                "error": "Your account has been deactivated. Please contact support."
            }, status=status.HTTP_403_FORBIDDEN)

        if user.is_blocked:
            return Response({
                "detail": "Your account has been blocked by the Administrator.",
                "error": "Your account has been blocked by the Administrator."
            }, status=status.HTTP_403_FORBIDDEN)

        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        user_data = UserSerializer(user).data
        user_data['name'] = user.get_full_name() or user.username
        user_data['phone'] = user.phone_number or ""

        return Response({
            "user": user_data,
            "access": access_token,
            "refresh": refresh_token,
            "token": access_token,
            "message": "Login successful."
        }, status=status.HTTP_200_OK)

class HostLoginView(APIView):
    """
    Dedicated Host / Hotel Owner Login API.
    Authenticates user AND verifies that the account has Hotel Owner / Host permissions.
    """
    permission_classes = [permissions.AllowAny]
    throttle_scope = 'login'

    def post(self, request):
        username = (
            request.data.get('username') or
            request.data.get('email') or
            request.data.get('phone_number') or
            request.data.get('phone') or
            request.data.get('identifier')
        )
        password = request.data.get('password')

        if not username or not password:
            return Response({"error": "Host Email/Username and password are required."}, status=status.HTTP_400_BAD_REQUEST)

        username = str(username).strip()

        import re
        clean_input = re.sub(r'[\s\-\(\)]', '', username)
        user_obj = (
            User.objects.filter(email__iexact=username).first() or
            User.objects.filter(username__iexact=username).first() or
            User.objects.filter(phone_number__iexact=username).first() or
            (User.objects.filter(phone_number__endswith=clean_input[-10:]).first() if len(clean_input) >= 10 else None)
        )
        if user_obj:
            username = user_obj.username

        user = authenticate(request=request, username=username, password=password)

        if not user:
            candidate = user_obj or User.objects.filter(Q(username__iexact=username) | Q(email__iexact=username)).first()
            if candidate and candidate.check_password(password) and not candidate.is_active:
                return Response({
                    "detail": "Your host account has been deactivated. Please contact support.",
                    "error": "Your host account has been deactivated. Please contact support."
                }, status=status.HTTP_403_FORBIDDEN)

            return Response({
                "detail": "No active host account found with the given credentials",
                "error": "No active host account found with the given credentials"
            }, status=status.HTTP_401_UNAUTHORIZED)

        if not user.is_active:
            return Response({
                "detail": "Your host account has been deactivated. Please contact support.",
                "error": "Your host account has been deactivated. Please contact support."
            }, status=status.HTTP_403_FORBIDDEN)

        if user.is_blocked:
            return Response({
                "detail": "Your host account has been blocked by the Administrator.",
                "error": "Your host account has been blocked by the Administrator."
            }, status=status.HTTP_403_FORBIDDEN)

        # Check if user is a host (HOTEL_OWNER, HOTEL_STAFF, ADMIN, or has created hotels)
        is_host = (
            user.role in [User.ROLE_HOTEL_OWNER, User.ROLE_HOTEL_STAFF, User.ROLE_ADMIN, User.ROLE_SUPER_ADMIN]
            or (hasattr(user, 'hotels') and user.hotels.exists())
        )
        if not is_host:
            return Response(
                {"error": "Access Denied: This account is registered as a Guest, not a Hotel Host/Owner."},
                status=status.HTTP_403_FORBIDDEN
            )

        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        user_data = UserSerializer(user).data
        user_data['name'] = user.get_full_name() or user.username
        user_data['phone'] = user.phone_number or ""

        return Response({
            "user": user_data,
            "access": access_token,
            "refresh": refresh_token,
            "token": access_token,
            "message": "Host login successful."
        }, status=status.HTTP_200_OK)

class LogoutView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        refresh_token = request.data.get("refresh") or request.data.get("refresh_token")
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception:
                pass
        return Response({"message": "Successfully logged out."}, status=status.HTTP_200_OK)

class UserProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return UserProfileUpdateSerializer
        return UserSerializer

    def update(self, request, *args, **kwargs):
        user = self.get_object()
        
        new_key_id = request.data.get('razorpay_key_id')
        new_key_secret = request.data.get('razorpay_key_secret')
        
        key_id_changed = new_key_id is not None and new_key_id != (user.razorpay_key_id or '')
        key_secret_changed = new_key_secret is not None and new_key_secret != (user.razorpay_key_secret or '')
        
        if key_id_changed or key_secret_changed:
            current_password = request.data.get('current_password') or request.data.get('password')
            if not current_password:
                return Response(
                    {"error": "Security Verification Required: Please enter your current account password to update Razorpay Merchant Keys."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if not user.check_password(current_password):
                return Response(
                    {"error": "Security Verification Failed: Incorrect account password provided."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        return super().update(request, *args, **kwargs)

class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user
            if not user.check_password(serializer.data.get("old_password")):
                return Response({"old_password": ["Wrong password."]}, status=status.HTTP_400_BAD_REQUEST)
            user.set_password(serializer.data.get("new_password"))
            user.save()
            return Response({"message": "Password updated successfully."}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ForgotPasswordView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'password_reset'

    def post(self, request):
        identifier = request.data.get('identifier') or request.data.get('email') or request.data.get('username')
        identifier = str(identifier or '').strip()

        if not identifier:
            return Response({"error": "Please enter your username or registered email address."}, status=status.HTTP_400_BAD_REQUEST)

        # Lookup user by email or username
        user = User.objects.filter(email__iexact=identifier).first() or User.objects.filter(username__iexact=identifier).first()
        if not user:
            # Safe generic response to avoid account enumeration while remaining compatible with clients
            return Response({
                "message": "If an account with that username or email address exists, a 6-digit verification code has been dispatched.",
                "mail_sent": True
            }, status=status.HTTP_200_OK)

        if not user.email:
            return Response({"error": "No email address linked to this account. Please contact support."}, status=status.HTTP_400_BAD_REQUEST)

        # Generate 6-digit cryptographically secure OTP
        otp = generate_otp()
        otp_hashed = hash_otp(otp)

        # Invalidate old OTPs for this email and initialize attempt counter to 0
        EmailOTP.objects.filter(email__iexact=user.email).delete()
        EmailOTP.objects.create(email=user.email.lower(), otp_hash=otp_hashed, attempts=0)

        # Send OTP email
        mail_sent = False
        try:
            mail_sent = send_otp_email(user.email, otp)
        except Exception as e:
            logger.error(f"Failed to deliver forgot password OTP email to {user.email}: {e}")

        if not mail_sent:
            logger.error(f"SMTP delivery failed for forgot password OTP to {user.email}")

        # Create masked email display: e.g. p***a@gmail.com
        parts = user.email.split('@')
        if len(parts) == 2:
            name_p, domain_p = parts
            if len(name_p) > 2:
                masked = name_p[0] + '*' * (len(name_p) - 2) + name_p[-1] + '@' + domain_p
            else:
                masked = name_p[0] + '*@' + domain_p
        else:
            masked = user.email

        # SAFE RESPONSE: Never disclose plaintext OTP or dev_hint_otp
        return Response({
            "message": f"6-digit verification code sent to {masked}.",
            "email": user.email,
            "username": user.username,
            "masked_email": masked,
            "mail_sent": mail_sent,
        }, status=status.HTTP_200_OK)


class ResetPasswordView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'password_reset'

    def post(self, request):
        email = str(request.data.get('email') or '').strip()
        otp = str(request.data.get('otp') or '').strip()
        new_password = request.data.get('new_password')
        confirm_password = request.data.get('confirm_password') or request.data.get('password_confirm')

        if not email or not otp:
            return Response({"error": "Email address and 6-digit OTP code are required."}, status=status.HTTP_400_BAD_REQUEST)

        if not new_password:
            return Response({"error": "Please enter your new password."}, status=status.HTTP_400_BAD_REQUEST)

        if len(new_password) < 8:
            return Response({"error": "Password must be at least 8 characters long."}, status=status.HTTP_400_BAD_REQUEST)

        if confirm_password and new_password != confirm_password:
            return Response({"error": "Passwords do not match. Please verify."}, status=status.HTTP_400_BAD_REQUEST)

        record = EmailOTP.objects.filter(email__iexact=email).first()

        if not record:
            return Response({"error": "No OTP verification record found. Please click 'Send OTP' first."}, status=status.HTTP_400_BAD_REQUEST)

        if record.is_expired(expiry_minutes=15):
            record.delete()
            return Response({"error": "OTP code has expired (valid for 15 mins). Please request a new verification code."}, status=status.HTTP_400_BAD_REQUEST)

        # Check if maximum attempts were already reached
        if record.is_locked() or record.attempts >= EmailOTP.MAX_ATTEMPTS:
            record.delete()
            return Response({
                "error": "Maximum OTP verification attempts exceeded (5/5). Code has been invalidated. Please request a new verification code."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Verify OTP hash
        otp_hashed = hash_otp(otp)
        if record.otp_hash != otp_hashed:
            with transaction.atomic():
                EmailOTP.objects.filter(id=record.id).update(attempts=F('attempts') + 1)
                record.refresh_from_db(fields=['attempts'])

            if record.attempts >= EmailOTP.MAX_ATTEMPTS:
                record.delete()
                return Response({
                    "error": "Maximum OTP verification attempts exceeded (5/5). Code has been invalidated. Please request a new verification code."
                }, status=status.HTTP_400_BAD_REQUEST)

            remaining = EmailOTP.MAX_ATTEMPTS - record.attempts
            return Response({
                "error": f"Invalid 6-digit OTP code. {remaining} attempt(s) remaining. Please check your email and try again."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Reset password on user model
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            return Response({"error": "User account not found."}, status=status.HTTP_404_NOT_FOUND)

        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError
        try:
            validate_password(new_password, user=user)
        except DjangoValidationError as val_err:
            return Response({"error": list(val_err.messages)}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save()

        # Invalidate OTP once used (prevent replay attack)
        record.delete()

        return Response({
            "message": "Password reset successfully! You can now log in with your new password.",
            "success": True
        }, status=status.HTTP_200_OK)

class IsAdminOrSuperAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user and 
            request.user.is_authenticated and 
            (request.user.is_staff or request.user.is_superuser or getattr(request.user, 'role', '') in ['ADMIN', 'SUPER_ADMIN'])
        )

class UserListView(generics.ListAPIView):
    queryset = User.objects.all().order_by('-created_at')
    serializer_class = UserSerializer
    permission_classes = [IsAdminOrSuperAdmin]

class UserBlockToggleView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def post(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
            if user.is_superuser:
                return Response({"error": "Cannot block superuser."}, status=status.HTTP_400_BAD_REQUEST)
            if user == request.user:
                return Response({"error": "Cannot block your own admin account."}, status=status.HTTP_400_BAD_REQUEST)

            user.is_blocked = not user.is_blocked
            user.is_active = not user.is_blocked
            user.save(update_fields=['is_blocked', 'is_active'])

            # TASK-17 Audit Logging
            try:
                from payments.models import AuditLog
                AuditLog.objects.create(
                    user=request.user if request.user and request.user.is_authenticated else None,
                    action='BLOCK_USER' if user.is_blocked else 'UNBLOCK_USER',
                    entity_type='User',
                    entity_id=str(user.id),
                    old_values={'is_blocked': not user.is_blocked, 'is_active': user.is_blocked},
                    new_values={'is_blocked': user.is_blocked, 'is_active': user.is_active},
                    ip_address=request.META.get('REMOTE_ADDR')
                )
            except Exception:
                pass

            affected_hotels = 0
            if user.role == User.ROLE_HOTEL_OWNER:
                from hotels.models import Hotel
                if user.is_blocked:
                    # Suspend active hotels owned by this blocked owner so they are not bookable
                    affected_hotels = Hotel.objects.filter(owner=user, status=Hotel.STATUS_APPROVED).update(
                        status=Hotel.STATUS_SUSPENDED,
                        rejection_reason="Hotel Owner account has been blocked by Platform Administrator."
                    )
                else:
                    # Restore hotels that were suspended due to owner block
                    affected_hotels = Hotel.objects.filter(
                        owner=user, 
                        status=Hotel.STATUS_SUSPENDED,
                        rejection_reason="Hotel Owner account has been blocked by Platform Administrator."
                    ).update(
                        status=Hotel.STATUS_APPROVED,
                        rejection_reason=""
                    )

            status_text = "blocked" if user.is_blocked else "unblocked"
            owner_suffix = f" ({affected_hotels} hotel(s) suspended)" if (user.is_blocked and affected_hotels > 0) else (f" ({affected_hotels} hotel(s) restored)" if (not user.is_blocked and affected_hotels > 0) else "")
            return Response({
                "message": f"User '@{user.username}' has been {status_text}{owner_suffix}.", 
                "is_blocked": user.is_blocked,
                "is_active": user.is_active,
                "user_id": user.id,
                "username": user.username,
                "role": user.role,
                "affected_hotels": affected_hotels
            }, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)


class UserRoleChangeView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def post(self, request, pk):
        role = request.data.get('role')
        valid_roles = [r[0] for r in User.ROLE_CHOICES]
        if role not in valid_roles:
            return Response({"error": f"Invalid role. Must be one of: {', '.join(valid_roles)}"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user = User.objects.get(pk=pk)
            user.role = role
            user.save()
            return Response({"message": f"User {user.username}'s role changed to {role}.", "role": user.role})
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)


class UserDeleteView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def delete(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
            if user.is_superuser:
                return Response({"error": "Cannot delete superuser account."}, status=status.HTTP_400_BAD_REQUEST)

            has_bookings = user.bookings.exists() if hasattr(user, 'bookings') else False
            has_hotels = user.hotels.exists() if hasattr(user, 'hotels') else False
            has_payments = user.payments.exists() if hasattr(user, 'payments') else False

            if has_bookings or has_hotels or has_payments:
                return Response({
                    "error": "Cannot permanently delete user account with existing bookings, hotels, or financial transaction history. Please block or deactivate the user account instead to preserve financial audit trail.",
                    "has_bookings": has_bookings,
                    "has_hotels": has_hotels,
                    "has_payments": has_payments
                }, status=status.HTTP_400_BAD_REQUEST)

            from django.db.models import ProtectedError
            try:
                username = user.username
                user.delete()
                return Response({"message": f"User account '{username}' deleted permanently."})
            except ProtectedError:
                return Response({
                    "error": "Cannot delete user account because related financial or audit records are protected."
                }, status=status.HTTP_400_BAD_REQUEST)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)


class CheckEmailView(APIView):
    permission_classes = [permissions.AllowAny]

    def _check(self, email_input):
        from util.validators import clean_email
        email = str(email_input or '').strip()
        if not email:
            return Response({"valid": False, "exists": False, "error": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            clean_val = clean_email(email)
        except Exception as e:
            msg = getattr(e, 'detail', str(e))
            if isinstance(msg, list):
                msg = msg[0]
            return Response({"valid": False, "exists": False, "error": str(msg)}, status=status.HTTP_400_BAD_REQUEST)
        
        exists = User.objects.filter(email__iexact=clean_val).exists()
        return Response({
            "valid": True,
            "exists": exists,
            "email": clean_val,
            "message": "An account with this email address is already registered (as Admin, Hotel Owner, or Guest). The same email cannot be used for multiple roles." if exists else "Email is valid and available for registration."
        }, status=status.HTTP_200_OK)

    def get(self, request):
        return self._check(request.query_params.get('email'))

    def post(self, request):
        return self._check(request.data.get('email') or request.query_params.get('email'))


class CheckPhoneView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'check_phone'

    def _check(self, phone_input):
        from util.validators import clean_indian_phone
        from django.db.models import Q
        phone = str(phone_input or '').strip()
        if not phone:
            return Response({"valid": False, "exists": False, "available": False, "error": "Phone number is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            clean_val = clean_indian_phone(phone)
        except Exception as e:
            msg = getattr(e, 'detail', str(e))
            if isinstance(msg, list):
                msg = msg[0]
            return Response({"valid": False, "exists": False, "available": False, "error": str(msg)}, status=status.HTTP_400_BAD_REQUEST)

        last10 = clean_val[-10:]
        exists = User.objects.filter(
            Q(phone_number__iexact=clean_val) |
            Q(phone_number__endswith=last10)
        ).exclude(phone_number__isnull=True).exclude(phone_number='').exists()

        return Response({
            "valid": True,
            "exists": exists,
            "available": not exists,
            "phone_number": clean_val,
            "message": "Mobile number is valid and available for registration." if not exists else "An account with this mobile number is already registered (as Admin, Hotel Owner, or Guest). The same mobile number cannot be used for multiple roles."
        }, status=status.HTTP_200_OK)

    def get(self, request):
        return self._check(request.query_params.get('phone') or request.query_params.get('phone_number'))

    def post(self, request):
        return self._check(request.data.get('phone') or request.data.get('phone_number') or request.query_params.get('phone'))


from util.otp import generate_otp, hash_otp
class SendOTPView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'otp_verify'

    def post(self, request):
        from util.validators import clean_email
        raw_email = request.data.get('email', '')
        if not raw_email:
            return Response({"error": "Email address is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            email = clean_email(raw_email)
        except Exception as e:
            msg = getattr(e, 'detail', str(e))
            if isinstance(msg, list):
                msg = msg[0]
            return Response({"error": str(msg)}, status=status.HTTP_400_BAD_REQUEST)

        # Check if email is already in use by any role (Admin, Hotel Owner, Customer)
        if User.objects.filter(email__iexact=email).exists():
            return Response({"error": "An account with this email address is already registered (as Admin, Hotel Owner, or Guest). The same email cannot be used for multiple roles or accounts."}, status=status.HTTP_400_BAD_REQUEST)

        otp = generate_otp()
        otp_hashed = hash_otp(otp)

        # Invalidate old unverified OTPs for this email and initialize attempts to 0
        EmailOTP.objects.filter(email__iexact=email, is_verified=False).delete()
        EmailOTP.objects.create(email=email.lower(), otp_hash=otp_hashed, attempts=0)

        # Send email via SMTP / Email Service
        sent = False
        try:
            sent = send_otp_email(email, otp)
        except Exception as e:
            logger.error(f"Failed to deliver registration OTP email to {email}: {e}")

        if not sent:
            logger.error(f"SMTP delivery failed for registration OTP to {email}")
            return Response({
                "error": "Failed to deliver OTP email to your inbox. Please check your internet connection or email address and try again."
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "message": f"Verification OTP sent to {email}. Check your inbox.",
            "email": email,
            "mail_sent": True
        }, status=status.HTTP_200_OK)


class VerifyOTPView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'otp_verify'

    def post(self, request):
        email = request.data.get('email', '').strip()
        otp = request.data.get('otp', '').strip()

        if not email or not otp:
            return Response({"error": "Both email and 6-digit OTP code are required."}, status=status.HTTP_400_BAD_REQUEST)

        record = EmailOTP.objects.filter(email__iexact=email).first()

        if not record:
            return Response({"error": "No OTP requested for this email. Please click 'Send OTP' first."}, status=status.HTTP_400_BAD_REQUEST)

        if record.is_expired():
            record.delete()
            return Response({"error": "OTP has expired (valid for 5 mins). Please request a new verification code."}, status=status.HTTP_400_BAD_REQUEST)

        # Prevent replay of previously verified OTP
        if record.is_verified:
            return Response({"error": "This OTP has already been verified and cannot be reused."}, status=status.HTTP_400_BAD_REQUEST)

        # Check if maximum attempts were already reached
        if record.is_locked() or record.attempts >= EmailOTP.MAX_ATTEMPTS:
            record.delete()
            return Response({
                "error": "Maximum OTP verification attempts exceeded (5/5). Code has been invalidated. Please request a new verification code."
            }, status=status.HTTP_400_BAD_REQUEST)

        otp_hashed = hash_otp(otp)
        if record.otp_hash != otp_hashed:
            with transaction.atomic():
                EmailOTP.objects.filter(id=record.id).update(attempts=F('attempts') + 1)
                record.refresh_from_db(fields=['attempts'])

            if record.attempts >= EmailOTP.MAX_ATTEMPTS:
                record.delete()
                return Response({
                    "error": "Maximum OTP verification attempts exceeded (5/5). Code has been invalidated. Please request a new verification code."
                }, status=status.HTTP_400_BAD_REQUEST)

            remaining = EmailOTP.MAX_ATTEMPTS - record.attempts
            return Response({
                "error": f"Invalid 6-digit OTP code. {remaining} attempt(s) remaining."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Mark OTP as verified and reset attempts
        record.is_verified = True
        record.attempts = 0
        record.save(update_fields=['is_verified', 'attempts'])

        # If user account already exists, update is_email_verified
        user = User.objects.filter(email__iexact=email).first()
        if user:
            user.is_email_verified = True
            user.save(update_fields=['is_email_verified'])

        return Response({
            "message": "Email address verified successfully!",
            "is_verified": True,
            "email": email
        }, status=status.HTTP_200_OK)

