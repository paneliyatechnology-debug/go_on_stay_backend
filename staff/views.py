import re
import secrets
from decimal import Decimal
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from django.db.models import Q, Count, Sum
from django.contrib.auth import authenticate, get_user_model
from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    Department, StaffPermission, StaffProfile, StaffActivityLog,
    StaffNotification, StaffPasswordResetToken, StaffTicketNote, StaffAssignment
)
from .serializers import (
    DepartmentSerializer, StaffPermissionSerializer,
    StaffProfileListSerializer, StaffProfileDetailSerializer,
    StaffCreateSerializer, StaffUpdateSerializer,
    StaffStatusUpdateSerializer, StaffPermissionsUpdateSerializer,
    StaffLoginSerializer, StaffChangePasswordSerializer,
    StaffForgotPasswordSerializer, StaffResetPasswordSerializer,
    StaffActivityLogSerializer, StaffNotificationSerializer,
    StaffTicketNoteSerializer
)
from .permissions import (
    IsAdminUserRole, IsStaffUser, check_staff_permission, is_platform_admin,
    HasDepartmentPermission, get_department_portal_info
)
from .portals import (
    get_portal_for_user, PORTAL_ADMIN, PORTAL_RESERVATION,
    PORTAL_CUSTOMER_SUPPORT, PORTAL_REFUNDS_AND_CLAIMS,
    PORTAL_PAYOUT_AND_ESCROW, PORTAL_HOTEL_VERIFICATION,
    PORTAL_CUSTOMER, PORTAL_HOTEL_OWNER
)
from .utils import (
    generate_temporary_password, hash_token,
    log_staff_activity, create_staff_notification,
    send_staff_password_reset_email
)
from bookings.models import Booking
from bookings.serializers import BookingSerializer
from hotels.models import Hotel
from hotels.serializers import HotelSerializer
from payments.models import Refund, HostPayout, HostEarning, SupportTicket, TicketMessage, Payment
from payments.views import execute_refund_with_provider

User = get_user_model()


class StandardStaffPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


# =============================================================================
# 1. STAFF AUTHENTICATION APIS
# =============================================================================

class StaffLoginView(APIView):
    """
    POST /api/staff/login/
    Secure Staff Login. Separated from Customer & Hotel Owner authentication.
    Validates employee status, active state, and flags first-login password change.
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def get_throttles(self):
        import sys
        if 'test' in sys.argv or getattr(settings, 'TESTING', False) or getattr(settings, 'BYPASS_THROTTLING_IN_TESTS', False):
            return []
        return super().get_throttles()

    def post(self, request):
        serializer = StaffLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        login_id_raw = (serializer.validated_data.get('identifier') or serializer.validated_data.get('login_id', '')).strip()
        password = serializer.validated_data['password']

        # Lookup user by login_id, employee_id, username, email, or phone
        user_obj = None
        profile = (
            StaffProfile.objects.filter(login_id__iexact=login_id_raw).first() or
            StaffProfile.objects.filter(employee_id__iexact=login_id_raw).first()
        )
        if profile:
            user_obj = profile.user
        else:
            user_obj = (
                User.objects.filter(username__iexact=login_id_raw).first() or
                User.objects.filter(email__iexact=login_id_raw).first() or
                User.objects.filter(phone_number__iexact=login_id_raw).first()
            )
            if user_obj:
                profile = StaffProfile.objects.filter(user=user_obj).first()

        # Only allow users with StaffProfile OR platform Admin
        is_admin = is_platform_admin(user_obj)
        STAFF_ROLES = {
            User.ROLE_STAFF,
            User.ROLE_DEPARTMENT_STAFF_MANAGER,
            User.ROLE_MAIN_MANAGER,
            User.ROLE_ADMIN,
            getattr(User, 'ROLE_SUPER_ADMIN', 'SUPER_ADMIN'),
            getattr(User, 'ROLE_SUPPORT_AGENT', 'SUPPORT_AGENT'),
        }

        # 1. Unknown user
        if not user_obj:
            return Response({
                "success": False,
                "code": "INVALID_CREDENTIALS",
                "error": "Invalid staff credentials."
            }, status=status.HTTP_401_UNAUTHORIZED)

        # 2. Non-staff accounts (Customer, Hotel Owner, etc.) are strictly forbidden
        if user_obj.role not in STAFF_ROLES and not is_admin:
            return Response({
                "success": False,
                "code": "AUTHENTICATION_FAILED",
                "error": "No staff account found with the provided credentials."
            }, status=status.HTTP_401_UNAUTHORIZED)

        # 3. Controlled error for genuine staff user lacking a StaffProfile
        if not profile and not is_admin:
            return Response({
                "success": False,
                "code": "STAFF_PROFILE_MISSING",
                "error": "Staff profile not found for this account. Please contact Administrator."
            }, status=status.HTTP_401_UNAUTHORIZED)

        # 4. Check password directly first so we can differentiate wrong password vs inactive account
        if not user_obj.check_password(password):
            return Response({
                "success": False,
                "code": "INVALID_CREDENTIALS",
                "error": "Invalid staff credentials."
            }, status=status.HTTP_401_UNAUTHORIZED)

        # 5. Enforce account active status
        if not user_obj.is_active or getattr(user_obj, 'is_blocked', False):
            return Response({
                "success": False,
                "code": "ACCOUNT_DISABLED",
                "error": "Your account has been deactivated. Please contact Administrator."
            }, status=status.HTTP_403_FORBIDDEN)

        # 6. Enforce staff profile active status
        if profile and profile.status != StaffProfile.STATUS_ACTIVE:
            return Response({
                "success": False,
                "code": "STAFF_SUSPENDED",
                "error": f"Your staff account is currently {profile.get_status_display().lower()}. Please contact Administrator."
            }, status=status.HTTP_403_FORBIDDEN)

        user = user_obj

        # Check Hierarchy Level & MFA enforcement for Level 2, 3, 4 (Dept Manager, Main Manager, Admin)
        from .services import get_user_hierarchy_level, log_hierarchy_audit
        from .models import ManagerMFAProfile, HierarchyAuditLog
        from util.totp import verify_totp_code, generate_totp_secret, get_provisioning_uri
        from django.core.signing import TimestampSigner

        actor_level = get_user_hierarchy_level(user)
        if actor_level >= 2:
            mfa_profile, _ = ManagerMFAProfile.objects.get_or_create(
                user=user,
                defaults={'totp_secret': generate_totp_secret()}
            )
            supplied_code = request.data.get('totp_code') or request.data.get('otp')
            if supplied_code:
                if verify_totp_code(mfa_profile.totp_secret, supplied_code):
                    if not mfa_profile.is_enrolled:
                        mfa_profile.is_enrolled = True
                        mfa_profile.is_mfa_enabled = True
                        mfa_profile.save()
                    log_hierarchy_audit(
                        actor_user=user,
                        action_type=HierarchyAuditLog.ACTION_LOGIN_MFA_SUCCESS,
                        target_user=user,
                        description="Manager logged in with TOTP code.",
                        request=request
                    )
                else:
                    log_hierarchy_audit(
                        actor_user=user,
                        action_type=HierarchyAuditLog.ACTION_LOGIN_MFA_FAILED,
                        target_user=user,
                        description="Failed TOTP verification on manager login.",
                        request=request
                    )
                    return Response({
                        "success": False,
                        "code": "INVALID_MFA_CODE",
                        "error": "Invalid multi-factor authentication code."
                    }, status=status.HTTP_401_UNAUTHORIZED)
            elif mfa_profile.is_mfa_enabled:
                signer = TimestampSigner()
                temp_token = signer.sign(f"mfa:{user.id}")
                return Response({
                    "success": True,
                    "mfa_required": True,
                    "temp_token": temp_token,
                    "message": "Multi-Factor Authentication code required."
                }, status=status.HTTP_200_OK)
            elif not mfa_profile.is_enrolled and not getattr(settings, 'BYPASS_MFA_ENROLLMENT_IN_TESTS', False):
                signer = TimestampSigner()
                temp_token = signer.sign(f"mfa_enroll:{user.id}")
                return Response({
                    "success": True,
                    "mfa_enrollment_required": True,
                    "temp_token": temp_token,
                    "secret": mfa_profile.totp_secret,
                    "provisioning_uri": get_provisioning_uri(mfa_profile.totp_secret, user.username),
                    "message": "Manager accounts require Multi-Factor Authentication. Please enroll your authenticator app."
                }, status=status.HTTP_200_OK)

        # Generate JWT Tokens
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)
        tokens_dict = {
            "access": access_token,
            "refresh": refresh_token
        }
        user_data = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role
        }
        profile_data = StaffProfileDetailSerializer(profile).data if profile else None

        # Determine department and portal routing
        dept_code = profile.department.code if (profile and profile.department) else None
        dept_name = profile.department.name if (profile and profile.department) else None
        portal_info = get_department_portal_info(dept_code)

        # Log activity
        log_staff_activity(
            request=request,
            staff_profile=profile,
            actor_user=user,
            action="LOGIN",
            description=f"Staff employee {profile.employee_id if profile else 'Admin'} logged in successfully."
        )

        response_data = {
            "success": True,
            "message": "Staff authentication successful.",
            "access": access_token,
            "refresh": refresh_token,
            "token": access_token,
            "tokens": tokens_dict,
            "must_change_password": profile.must_change_password if profile else False,
            "is_admin": is_admin,
            "department": dept_code,
            "department_name": dept_name,
            "portal": portal_info["portal"],
            "portal_name": portal_info["portal_name"],
            "portal_url": portal_info["portal_url"],
            "portal_info": portal_info,
            "user": user_data,
            "staff_profile": profile_data,
            "data": {
                "tokens": tokens_dict,
                "access": access_token,
                "refresh": refresh_token,
                "must_change_password": profile.must_change_password if profile else False,
                "is_admin": is_admin,
                "department": dept_code,
                "department_name": dept_name,
                "portal": portal_info["portal"],
                "portal_name": portal_info["portal_name"],
                "portal_url": portal_info["portal_url"],
                "portal_info": portal_info,
                "user": user_data,
                "staff_profile": profile_data
            }
        }

        return Response(response_data, status=status.HTTP_200_OK)


class StaffMeView(APIView):
    """
    GET /api/staff/me/
    Retrieves authenticated staff profile, department, and assigned permissions.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if hasattr(user, 'staff_profile'):
            profile = user.staff_profile
            try:
                profile.refresh_from_db(fields=['department', 'status', 'must_change_password'])
            except Exception:
                pass
            dept_code = profile.department.code if profile.department else None
            dept_name = profile.department.name if profile.department else None
            portal_info = get_department_portal_info(dept_code)
            return Response({
                "success": True,
                "is_admin": False,
                "department": dept_code,
                "department_name": dept_name,
                "portal": portal_info["portal"],
                "portal_name": portal_info["portal_name"],
                "portal_url": portal_info["portal_url"],
                "portal_info": portal_info,
                "staff_profile": StaffProfileDetailSerializer(profile).data,
                "must_change_password": profile.must_change_password
            }, status=status.HTTP_200_OK)

        if is_platform_admin(user):
            portal_info = get_department_portal_info(None)
            return Response({
                "success": True,
                "is_admin": True,
                "portal": portal_info["portal"],
                "portal_name": portal_info["portal_name"],
                "portal_url": portal_info["portal_url"],
                "portal_info": portal_info,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "role": user.role,
                    "full_name": user.get_full_name() or user.username
                },
                "permissions": ["ALL"]
            }, status=status.HTTP_200_OK)

        return Response({
            "success": False,
            "error": "Logged-in user is not a staff member."
        }, status=status.HTTP_403_FORBIDDEN)


class StaffChangePasswordView(APIView):
    """
    POST /api/staff/change-password/
    Allows an authenticated staff member to change their password.
    Clears must_change_password flag upon first successful password change.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = StaffChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user

        if not user.check_password(serializer.validated_data['old_password']):
            return Response({
                "success": False,
                "code": "INVALID_OLD_PASSWORD",
                "error": "The old password you provided is incorrect."
            }, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(serializer.validated_data['new_password'])
        user.save()

        profile = getattr(user, 'staff_profile', None)
        if profile and profile.must_change_password:
            profile.must_change_password = False
            profile.save(update_fields=['must_change_password'])

        log_staff_activity(
            request=request,
            staff_profile=profile,
            actor_user=user,
            action="CHANGE_PASSWORD",
            description="Staff member successfully changed their password."
        )

        return Response({
            "success": True,
            "message": "Password changed successfully. You can now access your staff dashboard."
        }, status=status.HTTP_200_OK)


class StaffForgotPasswordView(APIView):
    """
    POST /api/staff/forgot-password/
    Initiates a secure password reset for staff.
    Sends reset link with cryptographically hashed token.
    Generic response prevents user enumeration.
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'password_reset'

    def post(self, request):
        serializer = StaffForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        raw_id = serializer.validated_data['identifier'].strip()

        profile = (
            StaffProfile.objects.filter(login_id__iexact=raw_id).first() or
            StaffProfile.objects.filter(employee_id__iexact=raw_id).first() or
            StaffProfile.objects.filter(user__email__iexact=raw_id).first()
        )

        if profile and profile.is_active_account:
            raw_token = secrets.token_urlsafe(32)
            token_hashed = hash_token(raw_token)
            expires_at = timezone.now() + timedelta(minutes=15)

            StaffPasswordResetToken.objects.create(
                staff_profile=profile,
                token_hash=token_hashed,
                expires_at=expires_at
            )

            send_staff_password_reset_email(profile, raw_token)

            log_staff_activity(
                request=request,
                staff_profile=profile,
                action="FORGOT_PASSWORD_REQUEST",
                description=f"Password reset token issued for {profile.employee_id}."
            )

        # Always return generic message to prevent account enumeration
        return Response({
            "success": True,
            "message": "If a matching active staff account was found, a secure reset link has been dispatched to the registered email address.",
            "mail_sent": True
        }, status=status.HTTP_200_OK)


class StaffResetPasswordView(APIView):
    """
    POST /api/staff/reset-password/
    Completes password reset using single-use hashed token.
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'password_reset'

    def post(self, request):
        serializer = StaffResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        raw_token = serializer.validated_data['token'].strip()
        emp_id = serializer.validated_data.get('employee_id', '').strip()
        new_password = serializer.validated_data['new_password']

        hashed = hash_token(raw_token)
        reset_record = StaffPasswordResetToken.objects.filter(
            token_hash=hashed
        ).select_related('staff_profile__user').first()

        if not reset_record or not reset_record.is_valid():
            return Response({
                "success": False,
                "code": "TOKEN_EXPIRED_OR_USED",
                "error": "The password reset token is invalid, expired, or has already been used."
            }, status=status.HTTP_400_BAD_REQUEST)

        profile = reset_record.staff_profile
        if emp_id and emp_id.lower() not in [profile.employee_id.lower(), profile.login_id.lower()]:
            return Response({
                "success": False,
                "code": "INVALID_TOKEN",
                "error": "Token does not match the specified employee identifier."
            }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            reset_record.is_used = True
            reset_record.used_at = timezone.now()
            reset_record.save(update_fields=['is_used', 'used_at'])

            user = profile.user
            user.set_password(new_password)
            user.save()

            if profile.must_change_password:
                profile.must_change_password = False
                profile.save(update_fields=['must_change_password'])

            log_staff_activity(
                request=request,
                staff_profile=profile,
                actor_user=user,
                action="RESET_PASSWORD",
                description="Staff member reset their password using a valid reset token."
            )

        return Response({
            "success": True,
            "message": "Password reset successfully. You may now log in with your new password."
        }, status=status.HTTP_200_OK)


class StaffLogoutView(APIView):
    """
    POST /api/staff/logout/
    Logs out the staff member and invalidates refresh token.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        profile = getattr(request.user, 'staff_profile', None)

        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception:
                pass

        log_staff_activity(
            request=request,
            staff_profile=profile,
            actor_user=request.user,
            action="LOGOUT",
            description="Staff member logged out."
        )

        return Response({
            "success": True,
            "message": "Logged out successfully."
        }, status=status.HTTP_200_OK)


# =============================================================================
# 2. STAFF MANAGEMENT APIS (ADMIN ONLY)
# =============================================================================

class StaffCreateView(APIView):
    """
    POST /api/staff/create/
    Admin creates a staff employee.
    Generates GOS-EMP-XXX, login ID, and cryptographically secure temporary password.
    Temporary password is returned ONCE to the Admin and never stored in plain text.
    """
    permission_classes = [IsAdminUserRole]

    def post(self, request):
        serializer = StaffCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        profile = serializer.save()

        temp_pwd = getattr(profile, '_temporary_password', None)

        log_staff_activity(
            request=request,
            staff_profile=profile,
            actor_user=request.user,
            action="CREATE_STAFF",
            entity_type="StaffProfile",
            entity_id=profile.employee_id,
            description=f"Admin created employee {profile.employee_id} ({profile.login_id}) in department {profile.department.name}."
        )

        profile_data = StaffProfileDetailSerializer(profile).data
        creds = {
            "employee_id": profile.employee_id,
            "login_id": profile.login_id,
            "email": profile.user.email,
            "temporary_password": temp_pwd,
            "must_change_password": profile.must_change_password,
            "notice": "This temporary password is displayed ONLY ONCE. Please securely communicate it to the employee."
        }
        combined_data = {
            **profile_data,
            **creds,
            "credentials": creds,
            "temporary_password": temp_pwd
        }
        resp_data = {
            "success": True,
            "message": "Staff employee created successfully.",
            "employee": profile_data,
            "credentials": creds,
            "data": combined_data,
            **combined_data
        }
        return Response(resp_data, status=status.HTTP_201_CREATED)


class StaffListView(generics.ListAPIView):
    """
    GET /api/staff/
    Admin lists all employees with filtering and search.
    """
    permission_classes = [IsAdminUserRole]
    serializer_class = StaffProfileListSerializer
    pagination_class = StandardStaffPagination

    def get_queryset(self):
        qs = StaffProfile.objects.select_related('user', 'department').prefetch_related('permissions').all()
        dept = self.request.query_params.get('department')
        stat = self.request.query_params.get('status')
        search = self.request.query_params.get('search')

        if dept:
            qs = qs.filter(Q(department__code__iexact=dept) | Q(department__name__iexact=dept) | Q(department_id=dept if dept.isdigit() else 0))
        if stat:
            qs = qs.filter(status__iexact=stat)
        if search:
            qs = qs.filter(
                Q(employee_id__icontains=search) |
                Q(login_id__icontains=search) |
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(user__email__icontains=search)
            )
        return qs.order_by('-created_at')


class StaffDetailView(generics.RetrieveAPIView):
    """
    GET /api/staff/{id}/
    Admin views individual employee details.
    """
    permission_classes = [IsAdminUserRole]
    serializer_class = StaffProfileDetailSerializer
    queryset = StaffProfile.objects.select_related('user', 'department').prefetch_related('permissions').all()
    lookup_field = 'pk'


class StaffUpdateView(APIView):
    """
    PATCH /api/staff/{id}/update/
    Admin updates employee profile details.
    """
    permission_classes = [IsAdminUserRole]

    def patch(self, request, pk):
        profile = generics.get_object_or_404(StaffProfile, pk=pk)
        serializer = StaffUpdateSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        log_staff_activity(
            request=request,
            staff_profile=profile,
            actor_user=request.user,
            action="UPDATE_EMPLOYEE",
            entity_type="StaffProfile",
            entity_id=profile.id,
            description=f"Admin updated employee {profile.employee_id} details."
        )

        return Response({
            "success": True,
            "message": "Employee details updated successfully.",
            "employee": StaffProfileDetailSerializer(profile).data
        }, status=status.HTTP_200_OK)

    def put(self, request, pk):
        return self.patch(request, pk)


class StaffStatusUpdateView(APIView):
    """
    PATCH /api/staff/{id}/status/
    Admin activates, deactivates, or suspends an employee.
    Takes effect immediately.
    """
    permission_classes = [IsAdminUserRole]

    def patch(self, request, pk):
        profile = generics.get_object_or_404(StaffProfile, pk=pk)
        serializer = StaffStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data['status']
        reason = serializer.validated_data.get('reason', '')

        with transaction.atomic():
            profile.status = new_status
            profile.save(update_fields=['status', 'updated_at'])

            # Mirror to user.is_active
            profile.user.is_active = (new_status == StaffProfile.STATUS_ACTIVE)
            profile.user.save(update_fields=['is_active'])

            log_staff_activity(
                request=request,
                staff_profile=profile,
                actor_user=request.user,
                action="UPDATE_STATUS",
                entity_type="StaffProfile",
                entity_id=profile.id,
                description=f"Admin changed status of employee {profile.employee_id} to {new_status}. Reason: {reason}"
            )

        return Response({
            "success": True,
            "message": f"Employee status updated to {new_status}.",
            "employee_id": profile.employee_id,
            "status": profile.status,
            "is_active": profile.user.is_active
        }, status=status.HTTP_200_OK)

    def put(self, request, pk):
        return self.patch(request, pk)

    def post(self, request, pk):
        return self.patch(request, pk)


class StaffDepartmentListView(generics.ListAPIView):
    """
    GET /api/staff/departments/
    Lists available departments.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DepartmentSerializer
    queryset = Department.objects.filter(is_active=True).order_by('name')


class StaffPermissionView(APIView):
    """
    GET /api/staff/{id}/permissions/
    PUT /api/staff/{id}/permissions/update/
    View or update individual permissions for an employee.
    """
    permission_classes = [IsAdminUserRole]

    def get(self, request, pk):
        profile = generics.get_object_or_404(StaffProfile, pk=pk)
        perms = profile.permissions.all()
        return Response({
            "success": True,
            "employee_id": profile.employee_id,
            "login_id": profile.login_id,
            "department": profile.department.name,
            "permissions": StaffPermissionSerializer(perms, many=True).data
        }, status=status.HTTP_200_OK)

    def put(self, request, pk):
        profile = generics.get_object_or_404(StaffProfile, pk=pk)
        serializer = StaffPermissionsUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        perm_codes = serializer.validated_data['permissions']

        perms = StaffPermission.objects.filter(code__in=perm_codes)
        profile.permissions.set(perms)

        log_staff_activity(
            request=request,
            staff_profile=profile,
            actor_user=request.user,
            action="UPDATE_PERMISSIONS",
            entity_type="StaffProfile",
            entity_id=profile.id,
            description=f"Admin updated permissions for {profile.employee_id}: {', '.join(perm_codes)}."
        )

        return Response({
            "success": True,
            "message": "Permissions updated successfully.",
            "employee_id": profile.employee_id,
            "assigned_permissions": [p.code for p in perms]
        }, status=status.HTTP_200_OK)

    def post(self, request, pk):
        return self.put(request, pk)

    def patch(self, request, pk):
        return self.put(request, pk)


class StaffAdminResetPasswordView(APIView):
    """
    POST /api/staff/{id}/reset-password/
    Admin manually resets an employee's password.
    Returns a new temporary password shown only once.
    """
    permission_classes = [IsAdminUserRole]

    def post(self, request, pk):
        profile = generics.get_object_or_404(StaffProfile, pk=pk)
        new_temp_pwd = generate_temporary_password(12)

        with transaction.atomic():
            profile.user.set_password(new_temp_pwd)
            profile.user.save()

            profile.must_change_password = True
            profile.save(update_fields=['must_change_password'])

            log_staff_activity(
                request=request,
                staff_profile=profile,
                actor_user=request.user,
                action="ADMIN_PASSWORD_RESET",
                entity_type="StaffProfile",
                entity_id=profile.id,
                description=f"Admin initiated temporary password reset for {profile.employee_id}."
            )

        return Response({
            "success": True,
            "message": "Temporary password generated successfully.",
            "employee_id": profile.employee_id,
            "login_id": profile.login_id,
            "temporary_password": new_temp_pwd,
            "notice": "This temporary password is displayed ONLY ONCE. Please communicate it securely to the employee."
        }, status=status.HTTP_200_OK)


class StaffActivityLogListView(generics.ListAPIView):
    """
    GET /api/staff/activities/
    Admin views full employee activity and audit history.
    """
    permission_classes = [IsAdminUserRole]
    serializer_class = StaffActivityLogSerializer
    pagination_class = StandardStaffPagination

    def get_queryset(self):
        qs = StaffActivityLog.objects.all()
        emp_id = self.request.query_params.get('employee_id')
        action = self.request.query_params.get('action')
        search = self.request.query_params.get('search')

        if emp_id:
            qs = qs.filter(employee_id__iexact=emp_id)
        if action:
            qs = qs.filter(action__iexact=action)
        if search:
            qs = qs.filter(
                Q(employee_id__icontains=search) |
                Q(actor_username__icontains=search) |
                Q(description__icontains=search)
            )
        return qs.order_by('-timestamp')


# =============================================================================
# 3. RESERVATION STAFF – BOOKING MANAGEMENT
# =============================================================================

class StaffBookingListView(generics.ListAPIView):
    """
    GET /api/staff/bookings/
    Reservation Staff views bookings with customer, hotel, and payment details.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_RESERVATION, 'VIEW_BOOKINGS')]
    serializer_class = BookingSerializer
    pagination_class = StandardStaffPagination

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not check_staff_permission(request.user, 'VIEW_BOOKINGS'):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Permission 'VIEW_BOOKINGS' is required.")

    def get_queryset(self):
        user = self.request.user
        qs = Booking.objects.select_related('hotel', 'room', 'customer').all()

        b_id = self.request.query_params.get('booking_id')
        b_status = self.request.query_params.get('status') or self.request.query_params.get('booking_status')
        hotel_id = self.request.query_params.get('hotel_id')
        cin = self.request.query_params.get('check_in')
        cout = self.request.query_params.get('check_out')
        search = self.request.query_params.get('search') or self.request.query_params.get('q') or self.request.query_params.get('query')

        if b_id:
            qs = qs.filter(booking_id__icontains=b_id)
        if b_status:
            qs = qs.filter(booking_status__iexact=b_status)
        if hotel_id and hotel_id.isdigit():
            qs = qs.filter(hotel_id=int(hotel_id))
        if cin:
            qs = qs.filter(check_in__gte=cin)
        if cout:
            qs = qs.filter(check_out__lte=cout)
        if search:
            qs = qs.filter(
                Q(booking_id__icontains=search) |
                Q(guest_name__icontains=search) |
                Q(guest_email__icontains=search) |
                Q(guest_phone__icontains=search) |
                Q(customer__first_name__icontains=search) |
                Q(customer__last_name__icontains=search) |
                Q(hotel__name__icontains=search)
            )

        return qs.order_by('-created_at')

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({
            "success": True,
            "data": response.data,
            **response.data
        })


class StaffBookingDetailView(generics.RetrieveAPIView):
    """
    GET /api/staff/bookings/{id}/
    Authorized Reservation Staff views complete booking details.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_RESERVATION, 'VIEW_BOOKINGS')]
    serializer_class = BookingSerializer
    queryset = Booking.objects.select_related('hotel', 'room', 'customer').all()
    lookup_field = 'pk'

    def get_object(self):
        user = self.request.user
        if not check_staff_permission(user, 'VIEW_BOOKINGS'):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You do not have permission to view reservation bookings.")

        lookup = str(self.kwargs.get('pk', '')).strip()
        qs = Booking.objects.select_related('hotel', 'room', 'customer')
        if lookup.isdigit():
            booking = qs.filter(id=int(lookup)).first()
        else:
            booking = qs.filter(booking_id=lookup).first()

        if not booking:
            from rest_framework.exceptions import NotFound
            raise NotFound("Booking not found.")

        # Log read access by staff
        profile = getattr(user, 'staff_profile', None)
        log_staff_activity(
            request=self.request,
            staff_profile=profile,
            actor_user=user,
            action="VIEW_BOOKING_DETAILS",
            entity_type="Booking",
            entity_id=booking.booking_id,
            description=f"Staff viewed booking {booking.booking_id}."
        )

        return booking

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response({
            "success": True,
            "data": serializer.data,
            **serializer.data
        })


class StaffBookingCheckInView(APIView):
    """
    POST /api/staff/bookings/{id}/check-in/
    Reservation Staff checks in guest.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_RESERVATION, 'CHECKIN_GUEST')]

    def post(self, request, pk):
        lookup = str(pk).strip()
        qs = Booking.objects.select_related('hotel', 'room', 'customer')
        booking = qs.filter(id=int(lookup)).first() if lookup.isdigit() else qs.filter(booking_id=lookup).first()
        if not booking:
            return Response({"success": False, "error": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)

        booking.booking_status = Booking.STATUS_CHECKED_IN
        booking.actual_check_in_at = timezone.now()
        booking.action_by_staff = request.user
        booking.save(update_fields=['booking_status', 'actual_check_in_at', 'action_by_staff', 'updated_at'])

        profile = getattr(request.user, 'staff_profile', None)
        log_staff_activity(
            request=request,
            staff_profile=profile,
            actor_user=request.user,
            action="CHECKIN_GUEST",
            entity_type="Booking",
            entity_id=booking.booking_id,
            description=f"Staff checked in guest {booking.guest_name} for booking {booking.booking_id}."
        )

        return Response({
            "success": True,
            "message": f"Guest {booking.guest_name} checked in successfully.",
            "booking_id": booking.booking_id,
            "status": booking.booking_status,
            "actual_check_in_at": booking.actual_check_in_at.isoformat()
        }, status=status.HTTP_200_OK)


class StaffBookingCheckOutView(APIView):
    """
    POST /api/staff/bookings/{id}/check-out/
    Reservation Staff checks out guest.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_RESERVATION, 'CHECKOUT_GUEST')]

    def post(self, request, pk):
        lookup = str(pk).strip()
        qs = Booking.objects.select_related('hotel', 'room', 'customer')
        booking = qs.filter(id=int(lookup)).first() if lookup.isdigit() else qs.filter(booking_id=lookup).first()
        if not booking:
            return Response({"success": False, "error": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)

        booking.booking_status = Booking.STATUS_CHECKED_OUT
        booking.actual_check_out_at = timezone.now()
        booking.action_by_staff = request.user
        booking.save(update_fields=['booking_status', 'actual_check_out_at', 'action_by_staff', 'updated_at'])

        profile = getattr(request.user, 'staff_profile', None)
        log_staff_activity(
            request=request,
            staff_profile=profile,
            actor_user=request.user,
            action="CHECKOUT_GUEST",
            entity_type="Booking",
            entity_id=booking.booking_id,
            description=f"Staff checked out guest {booking.guest_name} for booking {booking.booking_id}."
        )

        return Response({
            "success": True,
            "message": f"Guest {booking.guest_name} checked out successfully.",
            "booking_id": booking.booking_id,
            "status": booking.booking_status,
            "actual_check_out_at": booking.actual_check_out_at.isoformat()
        }, status=status.HTTP_200_OK)


class StaffRoomListView(APIView):
    """
    GET /api/staff/rooms/
    Reservation Staff views rooms and room status across hotels.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_RESERVATION, 'VIEW_BOOKINGS')]

    def get(self, request):
        from rooms.models import Room
        qs = Room.objects.select_related('hotel').all()
        hotel_id = request.query_params.get('hotel_id')
        if hotel_id and str(hotel_id).isdigit():
            qs = qs.filter(hotel_id=int(hotel_id))

        rooms_data = []
        for r in qs[:50]:
            rooms_data.append({
                "id": r.id,
                "title": r.title,
                "hotel_id": r.hotel_id,
                "hotel_name": r.hotel.name if r.hotel else "",
                "room_type": r.room_type,
                "price_per_night": str(r.price_per_night),
                "capacity": (getattr(r, 'capacity_adults', 2) or 2) + (getattr(r, 'capacity_children', 0) or 0),
                "total_rooms": getattr(r, 'total_rooms', 1) or 1
            })
        return Response({"success": True, "rooms": rooms_data}, status=status.HTTP_200_OK)


class StaffGuestListView(APIView):
    """
    GET /api/staff/guests/
    Reservation Staff views guest booking directory.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_RESERVATION, 'VIEW_BOOKINGS')]

    def get(self, request):
        bookings_qs = Booking.objects.select_related('customer', 'hotel').order_by('-created_at')
        search = request.query_params.get('search', '').strip()
        if search:
            bookings_qs = bookings_qs.filter(
                Q(guest_name__icontains=search) |
                Q(guest_email__icontains=search) |
                Q(guest_phone__icontains=search) |
                Q(booking_id__icontains=search)
            )

        seen_emails = set()
        guests_data = []
        for b in bookings_qs[:100]:
            email_key = b.guest_email.lower() if b.guest_email else f"id_{b.id}"
            if email_key not in seen_emails:
                seen_emails.add(email_key)
                guests_data.append({
                    "guest_name": b.guest_name,
                    "guest_email": b.guest_email,
                    "guest_phone": b.guest_phone,
                    "latest_booking_id": b.booking_id,
                    "hotel_name": b.hotel.name if b.hotel else "",
                    "check_in": str(b.check_in),
                    "check_out": str(b.check_out),
                    "status": b.booking_status
                })
        return Response({"success": True, "guests": guests_data}, status=status.HTTP_200_OK)



# =============================================================================
# 4. REFUND STAFF – REFUND MANAGEMENT
# =============================================================================

class StaffRefundListView(APIView):
    """
    GET /api/staff/refunds/
    Refund Staff views pending and active refund requests.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_REFUNDS_AND_CLAIMS, 'VIEW_REFUNDS')]

    def get(self, request):
        if not check_staff_permission(request.user, 'VIEW_REFUNDS'):
            return Response({"error": "Permission 'VIEW_REFUNDS' is required."}, status=status.HTTP_403_FORBIDDEN)

        qs = Refund.objects.select_related('booking', 'payment', 'booking__customer', 'booking__hotel').all()
        ref_status = request.query_params.get('status')
        if ref_status:
            qs = qs.filter(status__iexact=ref_status)

        data = []
        for r in qs.order_by('-created_at')[:50]:
            data.append({
                "id": r.id,
                "booking_id": r.booking.booking_id if r.booking else None,
                "customer_name": r.booking.guest_name if r.booking else None,
                "hotel_name": r.booking.hotel.name if r.booking and r.booking.hotel else None,
                "amount": str(r.amount),
                "currency": r.currency,
                "status": r.status,
                "refund_mode": r.refund_mode,
                "reason": r.reason,
                "razorpay_refund_id": r.razorpay_refund_id,
                "created_at": r.created_at.isoformat()
            })
        return Response({"success": True, "refunds": data}, status=status.HTTP_200_OK)


class StaffRefundDetailView(APIView):
    """
    GET /api/staff/refunds/{id}/
    Refund Staff inspects refund eligibility and payment information.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_REFUNDS_AND_CLAIMS, 'VIEW_REFUNDS')]

    def get(self, request, pk):
        if not check_staff_permission(request.user, 'VIEW_REFUNDS'):
            return Response({"error": "Permission 'VIEW_REFUNDS' is required."}, status=status.HTTP_403_FORBIDDEN)

        refund = generics.get_object_or_404(Refund.objects.select_related('booking', 'payment', 'booking__customer', 'booking__hotel'), pk=pk)
        b = refund.booking

        return Response({
            "success": True,
            "refund": {
                "id": refund.id,
                "status": refund.status,
                "amount": str(refund.amount),
                "currency": refund.currency,
                "reason": refund.reason,
                "refund_mode": refund.refund_mode,
                "razorpay_payment_id": refund.razorpay_payment_id,
                "razorpay_refund_id": refund.razorpay_refund_id,
                "customer_bank_details": {
                    "account_holder": refund.customer_account_holder,
                    "bank_name": refund.customer_bank_name,
                    "account_number": refund.customer_account_number,
                    "ifsc_code": refund.customer_ifsc_code,
                    "upi_id": refund.customer_upi_id
                },
                "booking": {
                    "booking_id": b.booking_id if b else None,
                    "status": b.booking_status if b else None,
                    "payment_status": b.payment_status if b else None,
                    "total_amount": str(b.total_amount) if b else None,
                    "refundable_amount": str(b.refundable_amount) if b else None,
                    "cancellation_charge": str(b.cancellation_charge) if b else None,
                    "guest_name": b.guest_name if b else None,
                    "guest_phone": b.guest_phone if b else None,
                    "guest_email": b.guest_email if b else None
                },
                "created_at": refund.created_at.isoformat()
            }
        }, status=status.HTTP_200_OK)


class StaffRefundEligibilityCheckView(APIView):
    """
    GET /api/staff/refunds/{id}/eligibility/
    Refunds & Claims Staff inspects cancellation policy eligibility and refund breakdown.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_REFUNDS_AND_CLAIMS, 'VERIFY_CLAIM')]

    def get(self, request, pk):
        if not check_staff_permission(request.user, 'VERIFY_CLAIM'):
            return Response({"error": "Permission 'VERIFY_CLAIM' is required."}, status=status.HTTP_403_FORBIDDEN)

        refund = generics.get_object_or_404(Refund.objects.select_related('booking', 'booking__hotel'), pk=pk)
        b = refund.booking

        total_amount = float(b.total_amount) if b else float(refund.amount)
        refundable_amount = float(b.refundable_amount) if (b and b.refundable_amount is not None) else float(refund.amount)
        cancellation_charge = float(b.cancellation_charge) if (b and b.cancellation_charge is not None) else max(0.0, total_amount - refundable_amount)

        is_eligible = refund.status not in [Refund.STATUS_REFUNDED, 'PROCESSED']

        return Response({
            "success": True,
            "refund_id": refund.id,
            "booking_id": b.booking_id if b else None,
            "policy": b.hotel.cancellation_policy if (b and b.hotel) else "STANDARD",
            "is_eligible": is_eligible,
            "total_amount": total_amount,
            "refundable_amount": refundable_amount,
            "cancellation_charge": cancellation_charge,
            "status": refund.status,
            "reason": refund.reason
        }, status=status.HTTP_200_OK)



class StaffRefundProcessView(APIView):
    """
    POST /api/staff/refunds/{id}/process/
    Refund Staff processes an authorized refund using existing payment gateway workflow.
    Prevents duplicate processing and maintains complete audit history.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_REFUNDS_AND_CLAIMS, 'PROCESS_REFUND')]

    def post(self, request, pk):
        if not check_staff_permission(request.user, 'PROCESS_REFUND'):
            return Response({"error": "Permission 'PROCESS_REFUND' is required."}, status=status.HTTP_403_FORBIDDEN)

        refund = generics.get_object_or_404(Refund.objects.select_related('booking', 'payment'), pk=pk)

        # Idempotency Guard
        if refund.status in [Refund.STATUS_REFUNDED, 'PROCESSED'] or refund.razorpay_refund_id:
            return Response({
                "success": False,
                "code": "ALREADY_REFUNDED",
                "error": "This refund has already been processed successfully.",
                "razorpay_refund_id": refund.razorpay_refund_id
            }, status=status.HTTP_400_BAD_REQUEST)

        booking = refund.booking

        # Hotel Owner Approval Guard
        if booking.booking_status in [Booking.STATUS_OWNER_REJECTED, 'OWNER_REJECTED']:
            return Response({
                "success": False,
                "error": "Refund cannot be processed because the hotel owner rejected the cancellation request."
            }, status=status.HTTP_400_BAD_REQUEST)

        if booking.booking_status not in [Booking.STATUS_OWNER_APPROVED, 'OWNER_APPROVED', Booking.STATUS_CANCELLED]:
            return Response({
                "success": False,
                "error": f"Cancellation must be approved by the hotel owner ('OWNER_APPROVED') before refund can be processed. Current status: '{booking.booking_status}'."
            }, status=status.HTTP_400_BAD_REQUEST)

        captured_payment = refund.payment or booking.payments.filter(status=Payment.STATUS_CAPTURED).first()
        if not captured_payment:
            return Response({
                "success": False,
                "error": "No captured payment found for this reservation."
            }, status=status.HTTP_400_BAD_REQUEST)

        notes = request.data.get('notes', 'Staff approved and processed refund')
        profile = getattr(request.user, 'staff_profile', None)

        try:
            executed = execute_refund_with_provider(
                refund_record=refund,
                booking_locked=booking,
                captured_payment=captured_payment,
                refund_amount=refund.amount,
                reason=refund.reason or "Staff processed refund",
                refund_mode=refund.refund_mode,
                user=request.user,
                admin_notes=notes
            )

            log_staff_activity(
                request=request,
                staff_profile=profile,
                actor_user=request.user,
                action="PROCESS_REFUND",
                entity_type="Refund",
                entity_id=refund.id,
                description=f"Staff processed refund of ₹{refund.amount} for Booking {booking.booking_id}."
            )

            return Response({
                "success": True,
                "message": f"Refund of ₹{refund.amount} processed successfully.",
                "refund_id": refund.id,
                "status": refund.status,
                "razorpay_refund_id": refund.razorpay_refund_id
            }, status=status.HTTP_200_OK)

        except Exception as exc:
            return Response({
                "success": False,
                "error": f"Failed to execute refund with provider: {str(exc)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class StaffRefundHistoryView(APIView):
    """
    GET /api/staff/refunds/history/
    Refund Staff views history of processed refunds.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_REFUNDS_AND_CLAIMS, 'VIEW_REFUNDS')]

    def get(self, request):
        if not check_staff_permission(request.user, 'VIEW_REFUNDS'):
            return Response({"error": "Permission 'VIEW_REFUNDS' is required."}, status=status.HTTP_403_FORBIDDEN)

        qs = Refund.objects.filter(status=Refund.STATUS_REFUNDED).select_related('booking', 'booking__hotel').order_by('-processed_at')
        paginator = StandardStaffPagination()
        page_qs = paginator.paginate_queryset(qs, request, view=self)
        data = []
        target_list = page_qs if page_qs is not None else qs
        for r in target_list:
            data.append({
                "id": r.id,
                "booking_id": r.booking.booking_id if r.booking else None,
                "hotel_name": r.booking.hotel.name if r.booking and r.booking.hotel else None,
                "amount": str(r.amount),
                "refund_mode": r.refund_mode,
                "razorpay_refund_id": r.razorpay_refund_id,
                "refunded_at": (r.processed_at or r.created_at).isoformat() if (r.processed_at or r.created_at) else None
            })
        if page_qs is not None:
            return Response({
                "success": True,
                "count": paginator.page.paginator.count,
                "next": paginator.get_next_link(),
                "previous": paginator.get_previous_link(),
                "history": data,
                "results": data
            }, status=status.HTTP_200_OK)
        return Response({"success": True, "count": len(data), "history": data, "results": data}, status=status.HTTP_200_OK)


# =============================================================================
# 5. PAYOUT STAFF – HOTEL OWNER PAYOUT MANAGEMENT
# =============================================================================

class StaffPayoutListView(APIView):
    """
    GET /api/staff/payouts/
    Payout Staff views pending and eligible hotel owner payouts.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_PAYOUT_AND_ESCROW, 'VIEW_PAYOUTS')]

    def get(self, request):
        if not check_staff_permission(request.user, 'VIEW_PAYOUTS'):
            return Response({"error": "Permission 'VIEW_PAYOUTS' is required."}, status=status.HTTP_403_FORBIDDEN)

        qs = HostPayout.objects.select_related('host', 'payout_account').all()
        p_status = request.query_params.get('status')
        if p_status:
            qs = qs.filter(status__iexact=p_status)

        data = []
        for p in qs.order_by('-created_at')[:50]:
            data.append({
                "id": p.id,
                "payout_id": p.payout_id,
                "host_name": p.host.get_full_name() or p.host.username,
                "amount": str(p.amount),
                "currency": p.currency,
                "status": p.status,
                "payout_method": getattr(p, 'provider_mode', 'RAZORPAYX'),
                "created_at": p.created_at.isoformat()
            })
        return Response({"success": True, "payouts": data}, status=status.HTTP_200_OK)


class StaffPayoutDetailView(APIView):
    """
    GET /api/staff/payouts/{id}/
    Payout Staff views payout details, host earnings, and 7-day holding status.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_PAYOUT_AND_ESCROW, 'VIEW_PAYOUTS')]

    def get(self, request, pk):
        if not check_staff_permission(request.user, 'VIEW_PAYOUTS'):
            return Response({"error": "Permission 'VIEW_PAYOUTS' is required."}, status=status.HTTP_403_FORBIDDEN)

        qs = HostPayout.objects.select_related('host', 'payout_account').prefetch_related('earnings')
        if str(pk).isdigit():
            payout = qs.filter(pk=int(pk)).first()
        else:
            payout = qs.filter(payout_id=pk).first()
        if not payout:
            return Response({"error": "Payout not found."}, status=status.HTTP_404_NOT_FOUND)

        earnings_data = []
        for e in payout.earnings.all():
            earnings_data.append({
                "id": e.id,
                "booking_id": e.booking.booking_id if e.booking else None,
                "gross_amount": str(e.gross_amount),
                "platform_fee": str(e.platform_fee),
                "net_amount": str(e.net_amount),
                "status": e.status,
                "hold_until": e.hold_until.isoformat() if e.hold_until else None,
                "is_hold_matured": e.is_hold_matured
            })

        return Response({
            "success": True,
            "payout": {
                "id": payout.id,
                "payout_id": payout.payout_id,
                "host_name": payout.host.get_full_name() or payout.host.username,
                "host_email": payout.host.email,
                "amount": str(payout.amount),
                "currency": payout.currency,
                "status": payout.status,
                "payout_method": getattr(payout, 'provider_mode', 'RAZORPAYX'),
                "earnings": earnings_data,
                "created_at": payout.created_at.isoformat()
            }
        }, status=status.HTTP_200_OK)


class StaffPayoutProcessView(APIView):
    """
    POST /api/staff/payouts/{id}/process/
    Payout Staff executes authorized payout disbursement via existing settlement system.
    Enforces 7-day holding period and records responsible employee.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_PAYOUT_AND_ESCROW, 'PROCESS_PAYOUT')]

    def post(self, request, pk):
        if not check_staff_permission(request.user, 'PROCESS_PAYOUT'):
            return Response({"error": "Permission 'PROCESS_PAYOUT' is required."}, status=status.HTTP_403_FORBIDDEN)

        qs = HostPayout.objects.select_related('host')
        if str(pk).isdigit():
            payout = qs.filter(pk=int(pk)).first()
        else:
            payout = qs.filter(payout_id=pk).first()
        if not payout:
            return Response({"error": "Payout not found."}, status=status.HTTP_404_NOT_FOUND)

        if payout.status == HostPayout.STATUS_COMPLETED:
            return Response({
                "success": False,
                "error": "This payout has already been completed."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Holding period check
        now = timezone.now()
        unmatured = payout.earnings.filter(hold_until__gt=now, status=HostEarning.STATUS_ON_HOLD).exists()
        allow_override = request.data.get('override_hold', False) and is_platform_admin(request.user)

        if unmatured and not allow_override:
            return Response({
                "success": False,
                "code": "HOLD_PERIOD_ACTIVE",
                "error": "Cannot process payout: some bookings are still within the mandatory 7-day holding period."
            }, status=status.HTTP_400_BAD_REQUEST)

        profile = getattr(request.user, 'staff_profile', None)

        with transaction.atomic():
            payout.status = HostPayout.STATUS_COMPLETED
            payout.processed_at = now
            payout.processed_by = request.user
            payout.transaction_reference = f"tx_payout_{secrets.token_hex(6)}"
            payout.save()

            payout.earnings.update(status=getattr(HostEarning, 'STATUS_PAID', 'PAID'), settled_at=now)

            log_staff_activity(
                request=request,
                staff_profile=profile,
                actor_user=request.user,
                action="PROCESS_PAYOUT",
                entity_type="HostPayout",
                entity_id=payout.id,
                description=f"Staff processed payout #{payout.payout_id or payout.id} of ₹{payout.amount} to {payout.host.username}."
            )

            try:
                from payments.models import AuditLog
                AuditLog.objects.create(
                    user=request.user,
                    action='PAYOUT_DISBURSED',
                    entity_type='HostPayout',
                    entity_id=payout.payout_id or str(payout.id),
                    new_values={
                        'amount': str(payout.amount),
                        'host': payout.host.username,
                        'transaction_reference': payout.transaction_reference,
                        'status': 'COMPLETED'
                    }
                )
            except Exception as audit_err:
                logger.warning(f"Failed to record audit log for staff payout disbursement: {audit_err}")

        return Response({
            "success": True,
            "message": f"Payout of ₹{payout.amount} processed successfully.",
            "payout_id": payout.payout_id,
            "status": payout.status,
            "transaction_reference": payout.transaction_reference
        }, status=status.HTTP_200_OK)


class StaffPayoutHistoryView(APIView):
    """
    GET /api/staff/payouts/history/
    Payout Staff views disbursement history.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_PAYOUT_AND_ESCROW, 'VIEW_PAYOUTS')]

    def get(self, request):
        if not check_staff_permission(request.user, 'VIEW_PAYOUTS'):
            return Response({"error": "Permission 'VIEW_PAYOUTS' is required."}, status=status.HTTP_403_FORBIDDEN)

        qs = HostPayout.objects.filter(status=HostPayout.STATUS_COMPLETED).select_related('host', 'payout_account').order_by('-processed_at')
        paginator = StandardStaffPagination()
        page_qs = paginator.paginate_queryset(qs, request, view=self)
        data = []
        target_list = page_qs if page_qs is not None else qs
        for p in target_list:
            data.append({
                "id": p.id,
                "payout_id": p.payout_id,
                "host_name": p.host.get_full_name() or p.host.username,
                "amount": str(p.amount),
                "transaction_reference": getattr(p, 'bank_reference', None) or getattr(p, 'provider_payout_id', None) or "",
                "processed_at": p.processed_at.isoformat() if p.processed_at else None
            })
        if page_qs is not None:
            return Response({
                "success": True,
                "count": paginator.page.paginator.count,
                "next": paginator.get_next_link(),
                "previous": paginator.get_previous_link(),
                "history": data,
                "results": data
            }, status=status.HTTP_200_OK)
        return Response({"success": True, "count": len(data), "history": data, "results": data}, status=status.HTTP_200_OK)


class StaffEscrowListView(APIView):
    """
    GET /api/staff/payouts/escrow/
    Payout & Escrow Staff inspects on-hold earnings, mature bookings, and 7-day holding rules.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_PAYOUT_AND_ESCROW, 'MANAGE_ESCROW')]

    def get(self, request):
        if not check_staff_permission(request.user, 'MANAGE_ESCROW'):
            return Response({"error": "Permission 'MANAGE_ESCROW' is required."}, status=status.HTTP_403_FORBIDDEN)

        now = timezone.now()
        qs = HostEarning.objects.filter(status=HostEarning.STATUS_ON_HOLD).select_related('host', 'booking', 'booking__hotel')

        data = []
        for e in qs.order_by('hold_until')[:100]:
            data.append({
                "id": e.id,
                "booking_id": e.booking.booking_id if e.booking else None,
                "hotel_name": e.booking.hotel.name if (e.booking and e.booking.hotel) else None,
                "host_name": e.host.get_full_name() or e.host.username,
                "gross_amount": str(e.gross_amount),
                "platform_fee": str(e.platform_fee),
                "net_amount": str(e.net_amount),
                "hold_until": e.hold_until.isoformat() if e.hold_until else None,
                "is_hold_matured": bool(e.hold_until and e.hold_until <= now),
                "status": e.status
            })
        return Response({
            "success": True,
            "escrow_holdings": data,
            "total_count": len(data)
        }, status=status.HTTP_200_OK)


class StaffSettlementListView(APIView):
    """
    GET /api/staff/payouts/settlements/
    Payout & Escrow Staff inspects host settlement ledgers and fee deductions.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_PAYOUT_AND_ESCROW, 'AUDIT_SETTLEMENT')]

    def get(self, request):
        if not check_staff_permission(request.user, 'AUDIT_SETTLEMENT'):
            return Response({"error": "Permission 'AUDIT_SETTLEMENT' is required."}, status=status.HTTP_403_FORBIDDEN)

        qs = HostEarning.objects.select_related('host', 'booking', 'booking__hotel', 'payout')
        p_status = request.query_params.get('status')
        if p_status:
            qs = qs.filter(status__iexact=p_status)

        data = []
        for e in qs.order_by('-created_at')[:100]:
            data.append({
                "id": e.id,
                "booking_id": e.booking.booking_id if e.booking else None,
                "host_name": e.host.get_full_name() or e.host.username,
                "hotel_name": e.booking.hotel.name if (e.booking and e.booking.hotel) else None,
                "gross_amount": str(e.gross_amount),
                "platform_fee": str(e.platform_fee),
                "net_amount": str(e.net_amount),
                "status": e.status,
                "payout_id": e.payout.payout_id if e.payout else None,
                "created_at": e.created_at.isoformat()
            })
        return Response({
            "success": True,
            "settlements": data,
            "total_count": len(data)
        }, status=status.HTTP_200_OK)



# =============================================================================
# 6. CUSTOMER SUPPORT STAFF APIS
# =============================================================================

class StaffSupportTicketListView(APIView):
    """
    GET /api/staff/support/
    Support Staff views support tickets with filters.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_CUSTOMER_SUPPORT, 'MANAGE_SUPPORT')]

    def get(self, request):
        if not check_staff_permission(request.user, 'MANAGE_SUPPORT'):
            return Response({"error": "Permission 'MANAGE_SUPPORT' is required."}, status=status.HTTP_403_FORBIDDEN)

        qs = SupportTicket.objects.select_related('user', 'booking', 'hotel').all()
        t_status = request.query_params.get('status')
        priority = request.query_params.get('priority')
        search = request.query_params.get('search')

        if t_status:
            qs = qs.filter(status__iexact=t_status)
        if priority:
            qs = qs.filter(priority__iexact=priority)
        if search:
            qs = qs.filter(
                Q(ticket_number__icontains=search) |
                Q(subject__icontains=search) |
                Q(user__username__icontains=search) |
                Q(user__email__icontains=search)
            )

        data = []
        for t in qs.order_by('-created_at')[:50]:
            data.append({
                "id": t.id,
                "ticket_number": t.ticket_number,
                "subject": t.subject,
                "customer_name": t.user.get_full_name() or t.user.username,
                "category": t.category,
                "priority": t.priority,
                "status": t.status,
                "created_at": t.created_at.isoformat()
            })
        return Response({"success": True, "tickets": data}, status=status.HTTP_200_OK)


class StaffSupportTicketDetailView(APIView):
    """
    GET /api/staff/support/{id}/
    Support Staff inspects ticket, user messages, and internal staff notes.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_CUSTOMER_SUPPORT, 'MANAGE_SUPPORT')]

    def get(self, request, pk):
        if not check_staff_permission(request.user, 'MANAGE_SUPPORT'):
            return Response({"error": "Permission 'MANAGE_SUPPORT' is required."}, status=status.HTTP_403_FORBIDDEN)

        ticket = generics.get_object_or_404(SupportTicket.objects.select_related('user', 'booking', 'hotel'), pk=pk)

        # Messages
        messages_data = []
        for m in ticket.messages.select_related('sender').all():
            messages_data.append({
                "id": m.id,
                "sender_username": m.sender.username,
                "sender_role": getattr(m.sender, 'role', ''),
                "message": m.message,
                "created_at": m.created_at.isoformat()
            })

        # Internal staff notes (strictly confidential)
        notes_data = []
        for n in ticket.staff_notes.select_related('staff').all():
            notes_data.append({
                "id": n.id,
                "staff_name": n.staff.user.get_full_name() if n.staff else "Staff",
                "employee_id": n.staff.employee_id if n.staff else "",
                "note": n.note,
                "created_at": n.created_at.isoformat()
            })

        return Response({
            "success": True,
            "ticket": {
                "id": ticket.id,
                "ticket_number": ticket.ticket_number,
                "subject": ticket.subject,
                "description": ticket.description,
                "category": ticket.category,
                "priority": ticket.priority,
                "status": ticket.status,
                "customer": {
                    "username": ticket.user.username,
                    "email": ticket.user.email,
                    "phone": ticket.user.phone_number
                },
                "booking_id": ticket.booking.booking_id if ticket.booking else None,
                "messages": messages_data,
                "internal_notes": notes_data,
                "created_at": ticket.created_at.isoformat()
            }
        }, status=status.HTTP_200_OK)


class StaffSupportTicketUpdateView(APIView):
    """
    PATCH /api/staff/support/{id}/update/
    Support Staff updates ticket status or priority.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_CUSTOMER_SUPPORT, 'MANAGE_SUPPORT')]

    def patch(self, request, pk):
        if not check_staff_permission(request.user, 'MANAGE_SUPPORT'):
            return Response({"error": "Permission 'MANAGE_SUPPORT' is required."}, status=status.HTTP_403_FORBIDDEN)

        ticket = generics.get_object_or_404(SupportTicket, pk=pk)
        new_status = request.data.get('status')
        new_priority = request.data.get('priority')
        profile = getattr(request.user, 'staff_profile', None)

        update_fields = ['updated_at']
        if new_status:
            ticket.status = new_status
            update_fields.append('status')
        if new_priority:
            ticket.priority = new_priority
            update_fields.append('priority')

        ticket.save(update_fields=update_fields)

        log_staff_activity(
            request=request,
            staff_profile=profile,
            actor_user=request.user,
            action="UPDATE_TICKET",
            entity_type="SupportTicket",
            entity_id=ticket.ticket_number,
            description=f"Staff updated ticket {ticket.ticket_number} (status={ticket.status}, priority={ticket.priority})."
        )

        return Response({
            "success": True,
            "message": "Ticket updated successfully.",
            "ticket_number": ticket.ticket_number,
            "status": ticket.status,
            "priority": ticket.priority
        }, status=status.HTTP_200_OK)


class StaffSupportTicketNotesView(APIView):
    """
    POST /api/staff/support/{id}/notes/
    Support Staff adds internal notes (never visible to customer).
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_CUSTOMER_SUPPORT, 'MANAGE_SUPPORT')]

    def post(self, request, pk):
        if not check_staff_permission(request.user, 'MANAGE_SUPPORT'):
            return Response({"error": "Permission 'MANAGE_SUPPORT' is required."}, status=status.HTTP_403_FORBIDDEN)

        ticket = generics.get_object_or_404(SupportTicket, pk=pk)
        note_text = str(request.data.get('note', '')).strip()

        if not note_text:
            return Response({"error": "Note text is required."}, status=status.HTTP_400_BAD_REQUEST)

        profile = getattr(request.user, 'staff_profile', None)
        note_obj = StaffTicketNote.objects.create(
            ticket=ticket,
            staff=profile,
            note=note_text,
            is_internal_only=True
        )

        log_staff_activity(
            request=request,
            staff_profile=profile,
            actor_user=request.user,
            action="ADD_INTERNAL_NOTE",
            entity_type="SupportTicket",
            entity_id=ticket.ticket_number,
            description=f"Staff added internal note on ticket {ticket.ticket_number}."
        )

        note_data = StaffTicketNoteSerializer(note_obj).data
        return Response({
            "success": True,
            "message": "Internal staff note added successfully.",
            "note": note_data,
            "data": note_data,
            **note_data
        }, status=status.HTTP_201_CREATED)


class StaffSupportTicketMessageView(APIView):
    """
    POST /api/staff/support/{id}/messages/
    Customer Support Staff sends a reply to the customer on a support ticket.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_CUSTOMER_SUPPORT, 'RESPOND_TICKET')]

    def post(self, request, pk):
        if not check_staff_permission(request.user, 'RESPOND_TICKET'):
            return Response({"error": "Permission 'RESPOND_TICKET' is required."}, status=status.HTTP_403_FORBIDDEN)

        ticket = generics.get_object_or_404(SupportTicket, pk=pk)
        message_text = str(request.data.get('message', '')).strip()
        if not message_text:
            return Response({"success": False, "error": "Message content is required."}, status=status.HTTP_400_BAD_REQUEST)

        profile = getattr(request.user, 'staff_profile', None)
        msg_obj = TicketMessage.objects.create(
            ticket=ticket,
            sender=request.user,
            message=message_text
        )

        ticket.updated_at = timezone.now()
        if ticket.status == 'OPEN':
            ticket.status = 'IN_PROGRESS'
            ticket.save(update_fields=['status', 'updated_at'])
        else:
            ticket.save(update_fields=['updated_at'])

        log_staff_activity(
            request=request,
            staff_profile=profile,
            actor_user=request.user,
            action="RESPOND_TICKET",
            entity_type="SupportTicket",
            entity_id=ticket.ticket_number,
            description=f"Staff responded to ticket {ticket.ticket_number}."
        )

        return Response({
            "success": True,
            "message": "Response message sent to customer successfully.",
            "ticket_number": ticket.ticket_number,
            "message_id": msg_obj.id,
            "created_at": msg_obj.created_at.isoformat()
        }, status=status.HTTP_201_CREATED)



# =============================================================================
# 7. HOTEL VERIFICATION STAFF APIS
# =============================================================================

class StaffHotelVerificationListView(APIView):
    """
    GET /api/staff/verifications/
    Hotel Verification Staff lists pending hotel verification submissions.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_HOTEL_VERIFICATION, 'VERIFY_HOTEL')]

    def get(self, request):
        if not check_staff_permission(request.user, 'VERIFY_HOTEL'):
            return Response({"error": "Permission 'VERIFY_HOTEL' is required."}, status=status.HTTP_403_FORBIDDEN)

        h_status = request.query_params.get('status') or Hotel.STATUS_SUBMITTED
        qs = Hotel.objects.filter(status=h_status, is_deleted=False).select_related('owner')

        data = []
        for h in qs.order_by('-created_at')[:50]:
            data.append({
                "id": h.id,
                "name": h.name,
                "property_type": h.property_type,
                "city": h.city,
                "state": h.state,
                "owner_name": h.owner.get_full_name() or h.owner.username,
                "owner_email": h.owner.email,
                "owner_phone": h.owner.phone_number,
                "status": h.status,
                "documents_count": h.verification_documents.count(),
                "created_at": h.created_at.isoformat()
            })
        return Response({"success": True, "verifications": data}, status=status.HTTP_200_OK)


class StaffHotelVerificationDetailView(APIView):
    """
    GET /api/staff/verifications/{id}/
    Hotel Verification Staff inspects hotel details, owner identity, and verification documents.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_HOTEL_VERIFICATION, 'VERIFY_HOTEL')]

    def get(self, request, pk):
        if not check_staff_permission(request.user, 'VERIFY_HOTEL'):
            return Response({"error": "Permission 'VERIFY_HOTEL' is required."}, status=status.HTTP_403_FORBIDDEN)

        hotel = generics.get_object_or_404(Hotel.objects.filter(is_deleted=False).select_related('owner'), pk=pk)

        docs = []
        for d in hotel.verification_documents.all():
            docs.append({
                "id": d.id,
                "document_type": d.document_type,
                "document_type_label": d.get_document_type_display(),
                "status": d.status,
                "document_url": d.document_url or (f"/api/hotels/{d.hotel_id}/documents/{d.id}/download/" if d.document_file else ""),
                "created_at": d.created_at.isoformat()
            })

        return Response({
            "success": True,
            "hotel": {
                "id": hotel.id,
                "name": hotel.name,
                "property_type": hotel.property_type,
                "address": hotel.address,
                "city": hotel.city,
                "state": hotel.state,
                "status": hotel.status,
                "is_approved": hotel.is_approved,
                "owner": {
                    "id": hotel.owner.id,
                    "name": hotel.owner.get_full_name() or hotel.owner.username,
                    "email": hotel.owner.email,
                    "phone": hotel.owner.phone_number
                },
                "documents": docs,
                "created_at": hotel.created_at.isoformat()
            }
        }, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        if not check_staff_permission(request.user, 'VERIFY_HOTEL'):
            return Response({"error": "Permission 'VERIFY_HOTEL' is required."}, status=status.HTTP_403_FORBIDDEN)

        hotel = generics.get_object_or_404(Hotel.objects.filter(is_deleted=False), pk=pk)
        from bookings.models import Booking
        from django.utils import timezone
        today = timezone.now().date()
        active_bookings = Booking.objects.filter(
            hotel=hotel,
            booking_status__in=[Booking.STATUS_CONFIRMED, Booking.STATUS_CHECKED_IN],
            check_out__gte=today
        )
        if active_bookings.exists():
            return Response(
                {"error": "Cannot delete hotel with active upcoming reservations."},
                status=status.HTTP_400_BAD_REQUEST
            )

        reason = request.data.get('reason') if hasattr(request, 'data') else None
        if not reason:
            reason = request.query_params.get('reason') or f"Deleted by staff {request.user.username}"

        from hotels.models import DeletedHotelArchive
        snapshot_data = {
            "hotel_id": hotel.id,
            "name": hotel.name,
            "description": hotel.description,
            "property_type": hotel.property_type,
            "address": hotel.address,
            "city": hotel.city,
            "state": hotel.state,
            "country": hotel.country,
            "zip_code": hotel.zip_code,
            "star_rating": hotel.star_rating,
            "guest_rating": str(hotel.guest_rating),
            "owner": {
                "id": hotel.owner.id if hotel.owner else None,
                "username": hotel.owner.username if hotel.owner else '',
                "email": hotel.owner.email if hotel.owner else '',
                "full_name": hotel.owner.get_full_name() if hotel.owner else '',
                "phone": getattr(hotel.owner, 'phone_number', '') if hotel.owner else ''
            },
            "amenities": [a.name for a in hotel.amenities.all()],
            "rooms": [
                {
                    "id": r.id,
                    "title": r.title,
                    "room_type": r.room_type,
                    "price_per_night": str(r.price_per_night),
                    "capacity_adults": getattr(r, 'capacity_adults', 2),
                    "capacity_children": getattr(r, 'capacity_children', 1),
                    "total_rooms": r.total_rooms,
                    "room_numbers": r.room_numbers,
                }
                for r in hotel.rooms.all()
            ],
            "images": [
                {
                    "id": img.id,
                    "image_url": img.get_image_display(),
                    "caption": img.caption,
                    "is_primary": img.is_primary
                }
                for img in hotel.images.all()
            ],
            "verification_documents": [
                {
                    "id": doc.id,
                    "document_type": doc.document_type,
                    "status": doc.status,
                    "document_url": doc.document_url or (f"/api/hotels/{doc.hotel_id}/documents/{doc.id}/download/" if doc.document_file else ''),
                }
                for doc in hotel.verification_documents.all()
            ],
            "stats": {
                "total_past_bookings": hotel.bookings.count(),
                "total_rooms_count": hotel.rooms.count()
            }
        }

        hotel.is_deleted = True
        hotel.status = Hotel.STATUS_DELETED
        hotel.is_active = False
        hotel.is_approved = False
        hotel.deleted_at = timezone.now()
        hotel.deleted_by = request.user
        hotel.rejection_reason = reason
        hotel.save(update_fields=['is_deleted', 'status', 'is_active', 'is_approved', 'deleted_at', 'deleted_by', 'rejection_reason', 'updated_at'])

        owner_name = (hotel.owner.get_full_name() or hotel.owner.username or '') if hotel.owner else ''
        owner_email = (hotel.owner.email or '') if hotel.owner else ''
        owner_phone = (getattr(hotel.owner, 'phone_number', '') or '') if hotel.owner else ''
        deleted_by_name = (request.user.get_full_name() or request.user.username or '') if request.user else ''
        deleted_by_role = str(getattr(request.user, 'role', '') or '').upper()

        archive, _ = DeletedHotelArchive.objects.update_or_create(
            hotel=hotel,
            defaults={
                "hotel_name": hotel.name,
                "city": hotel.city,
                "address": hotel.address,
                "property_type": hotel.property_type,
                "owner": hotel.owner,
                "owner_name": owner_name,
                "owner_email": owner_email,
                "owner_phone": owner_phone,
                "deleted_by": request.user,
                "deleted_by_name": deleted_by_name,
                "deleted_by_role": deleted_by_role,
                "deletion_reason": reason or '',
                "snapshot_data": snapshot_data,
                "is_restored": False,
            }
        )

        profile = getattr(request.user, 'staff_profile', None)
        log_staff_activity(
            request=request,
            staff_profile=profile,
            actor_user=request.user,
            action="DELETE_HOTEL",
            entity_type="Hotel",
            entity_id=str(hotel.id),
            description=f"Staff deleted hotel '{hotel.name}' (ID {hotel.id}). Archived to Admin Deleted section."
        )

        return Response({
            "success": True,
            "message": f"Hotel '{hotel.name}' deleted and archived successfully.",
            "hotel_id": hotel.id,
            "archive_id": archive.id,
            "deleted_at": hotel.deleted_at.isoformat()
        }, status=status.HTTP_200_OK)


class StaffHotelVerificationApproveView(APIView):
    """
    POST /api/staff/verifications/{id}/approve/
    Hotel Verification Staff approves submitted property.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_HOTEL_VERIFICATION, 'VERIFY_HOTEL')]

    def post(self, request, pk):
        if not check_staff_permission(request.user, 'VERIFY_HOTEL'):
            return Response({"error": "Permission 'VERIFY_HOTEL' is required."}, status=status.HTTP_403_FORBIDDEN)

        hotel = generics.get_object_or_404(Hotel, pk=pk)
        profile = getattr(request.user, 'staff_profile', None)

        with transaction.atomic():
            hotel.status = Hotel.STATUS_APPROVED
            hotel.is_approved = True
            hotel.rejection_reason = None
            hotel.save(update_fields=['status', 'is_approved', 'rejection_reason', 'updated_at'])

            # Approve all pending documents
            hotel.verification_documents.filter(status='PENDING').update(status='APPROVED')

            # Notify Hotel Owner
            from notifications.utils import create_notification
            from notifications.models import Notification
            create_notification(
                recipient=hotel.owner,
                title=f"✅ Property Approved: {hotel.name}",
                message=f"Your hotel '{hotel.name}' has been verified and approved by GoOnStay Verification Staff.",
                notification_type=Notification.TYPE_HOTEL_APPROVED
            )

            log_staff_activity(
                request=request,
                staff_profile=profile,
                actor_user=request.user,
                action="APPROVE_HOTEL",
                entity_type="Hotel",
                entity_id=hotel.id,
                description=f"Staff approved hotel '{hotel.name}' (ID: {hotel.id})."
            )

        return Response({
            "success": True,
            "message": f"Hotel '{hotel.name}' approved successfully.",
            "hotel_id": hotel.id,
            "status": hotel.status,
            "is_approved": hotel.is_approved
        }, status=status.HTTP_200_OK)


class StaffHotelVerificationRejectView(APIView):
    """
    POST /api/staff/verifications/{id}/reject/
    Hotel Verification Staff rejects property with reason.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_HOTEL_VERIFICATION, 'VERIFY_HOTEL')]

    def post(self, request, pk):
        if not check_staff_permission(request.user, 'VERIFY_HOTEL'):
            return Response({"error": "Permission 'VERIFY_HOTEL' is required."}, status=status.HTTP_403_FORBIDDEN)

        hotel = generics.get_object_or_404(Hotel, pk=pk)
        reason = str(request.data.get('reason', '') or request.data.get('rejection_reason', '')).strip()

        if not reason:
            return Response({"error": "Rejection reason is required."}, status=status.HTTP_400_BAD_REQUEST)

        profile = getattr(request.user, 'staff_profile', None)

        with transaction.atomic():
            hotel.status = Hotel.STATUS_REJECTED
            hotel.is_approved = False
            hotel.rejection_reason = reason
            hotel.rejected_at = timezone.now()
            hotel.rejected_by = request.user
            hotel.save(update_fields=['status', 'is_approved', 'rejection_reason', 'rejected_at', 'rejected_by', 'updated_at'])

            # Notify Hotel Owner
            from notifications.utils import create_notification
            from notifications.models import Notification
            create_notification(
                recipient=hotel.owner,
                title=f"⚠️ Hotel Verification Rejected: {hotel.name}",
                message=f"Your property '{hotel.name}' was rejected by Verification Staff. Reason: {reason}",
                notification_type=Notification.TYPE_HOTEL_REJECTED
            )

            log_staff_activity(
                request=request,
                staff_profile=profile,
                actor_user=request.user,
                action="REJECT_HOTEL",
                entity_type="Hotel",
                entity_id=hotel.id,
                description=f"Staff rejected hotel '{hotel.name}'. Reason: {reason}"
            )

        return Response({
            "success": True,
            "message": f"Hotel '{hotel.name}' rejected.",
            "hotel_id": hotel.id,
            "status": hotel.status,
            "rejection_reason": hotel.rejection_reason
        }, status=status.HTTP_200_OK)


class StaffHotelVerificationHistoryView(APIView):
    """
    GET /api/staff/verifications/history/
    Hotel Verification Staff inspects history of approved and rejected hotel submissions.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_HOTEL_VERIFICATION, 'VIEW_HOTELS')]

    def get(self, request):
        if not check_staff_permission(request.user, 'VIEW_HOTELS'):
            return Response({"error": "Permission 'VIEW_HOTELS' is required."}, status=status.HTTP_403_FORBIDDEN)

        qs = Hotel.objects.filter(status__in=[Hotel.STATUS_APPROVED, Hotel.STATUS_REJECTED]).select_related('owner').order_by('-updated_at')
        paginator = StandardStaffPagination()
        page_qs = paginator.paginate_queryset(qs, request, view=self)
        data = []
        target_list = page_qs if page_qs is not None else qs
        for h in target_list:
            data.append({
                "id": h.id,
                "name": h.name,
                "property_type": h.property_type,
                "city": h.city,
                "state": h.state,
                "owner_name": h.owner.get_full_name() or h.owner.username,
                "status": h.status,
                "is_approved": h.is_approved,
                "rejection_reason": h.rejection_reason,
                "decided_at": (h.rejected_at or h.updated_at).isoformat() if (h.rejected_at or h.updated_at) else None
            })
        if page_qs is not None:
            return Response({
                "success": True,
                "count": paginator.page.paginator.count,
                "next": paginator.get_next_link(),
                "previous": paginator.get_previous_link(),
                "history": data,
                "results": data
            }, status=status.HTTP_200_OK)
        return Response({"success": True, "count": len(data), "history": data, "results": data}, status=status.HTTP_200_OK)


class StaffHotelDocumentsListView(APIView):
    """
    GET /api/staff/verifications/documents/
    Hotel Verification Staff inspects submitted compliance documents across hotels.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_HOTEL_VERIFICATION, 'REVIEW_DOCUMENTS')]

    def get(self, request):
        if not check_staff_permission(request.user, 'REVIEW_DOCUMENTS'):
            return Response({"error": "Permission 'REVIEW_DOCUMENTS' is required."}, status=status.HTTP_403_FORBIDDEN)

        from hotels.models import HotelVerificationDocument
        qs = HotelVerificationDocument.objects.select_related('hotel', 'hotel__owner')
        doc_status = request.query_params.get('status')
        if doc_status:
            qs = qs.filter(status__iexact=doc_status)

        docs = []
        for d in qs.order_by('-created_at')[:100]:
            docs.append({
                "id": d.id,
                "hotel_id": d.hotel.id,
                "hotel_name": d.hotel.name,
                "owner_name": d.hotel.owner.get_full_name() or d.hotel.owner.username,
                "document_type": d.document_type,
                "document_type_label": d.get_document_type_display(),
                "status": d.status,
                "document_url": d.document_url or (f"/api/hotels/{d.hotel_id}/documents/{d.id}/download/" if d.document_file else ""),
                "created_at": d.created_at.isoformat()
            })
        return Response({"success": True, "documents": docs}, status=status.HTTP_200_OK)



# =============================================================================
# 8. STAFF NOTIFICATIONS APIS
# =============================================================================

class StaffNotificationListView(APIView):
    """
    GET /api/staff/notifications/
    Retrieves notifications for the logged-in staff member and their department.
    """
    permission_classes = [IsStaffUser]

    def get(self, request):
        user = request.user
        profile = getattr(user, 'staff_profile', None)

        if profile:
            qs = StaffNotification.objects.filter(
                Q(recipient=profile) | Q(department=profile.department)
            ).distinct()
        else:
            qs = StaffNotification.objects.all()

        unread_count = qs.filter(is_read=False).count()
        unread_only = str(request.query_params.get('unread_only', '')).lower() in ['true', '1']
        if unread_only:
            qs = qs.filter(is_read=False)

        notifications_page = qs.order_by('-created_at')[:50]
        serializer_data = StaffNotificationSerializer(notifications_page, many=True, context={'request': request}).data

        return Response({
            "success": True,
            "unread_count": unread_count,
            "notifications": serializer_data,
            "data": {
                "unread_count": unread_count,
                "notifications": serializer_data,
                "results": serializer_data
            }
        }, status=status.HTTP_200_OK)


class StaffNotificationReadView(APIView):
    """
    PATCH /api/staff/notifications/{id}/read/
    Marks an individual notification as read.
    Guarantees object-level department and recipient isolation.
    """
    permission_classes = [IsStaffUser]

    def patch(self, request, pk):
        notif = generics.get_object_or_404(StaffNotification, pk=pk)
        user = request.user
        if not is_platform_admin(user):
            profile = getattr(user, 'staff_profile', None)
            if not profile:
                return Response({"error": "Staff profile not found."}, status=status.HTTP_403_FORBIDDEN)
            is_own = (notif.recipient_id == profile.id)
            is_dept = bool(notif.department_id and profile.department_id and notif.department_id == profile.department_id)
            if not (is_own or is_dept):
                return Response({
                    "success": False,
                    "error": "Permission denied. You cannot access notifications belonging to another staff member or department.",
                    "code": "DEPARTMENT_FORBIDDEN"
                }, status=status.HTTP_403_FORBIDDEN)

        if not notif.is_read:
            notif.is_read = True
            notif.read_at = timezone.now()
            notif.save(update_fields=['is_read', 'read_at'])

        from notifications.navigation import resolve_notification_navigation
        nav = resolve_notification_navigation(notification=notif, user=user)

        return Response({
            "success": True,
            "message": "Notification marked as read.",
            "is_read": True,
            "target_url": nav.get('target_url', ''),
            "target_entity_type": nav.get('target_entity_type', ''),
            "target_entity_id": nav.get('target_entity_id', ''),
            "fallback_url": nav.get('fallback_url', ''),
            "action": nav.get('action', ''),
            "record_exists": nav.get('record_exists', True),
            "navigation": nav
        }, status=status.HTTP_200_OK)

    def post(self, request, pk):
        return self.patch(request, pk)


class StaffNotificationClickView(APIView):
    """
    POST /api/staff/notifications/{id}/click/
    Handles staff smart notification click-through:
    - Department and recipient isolation check.
    - Marks the notification as read.
    - Resolves department-isolated destination and exact record identifier.
    """
    permission_classes = [IsStaffUser]

    def post(self, request, pk):
        notif = generics.get_object_or_404(StaffNotification, pk=pk)
        user = request.user
        if not is_platform_admin(user):
            profile = getattr(user, 'staff_profile', None)
            if not profile:
                return Response({"error": "Staff profile not found."}, status=status.HTTP_403_FORBIDDEN)
            is_own = (notif.recipient_id == profile.id)
            is_dept = bool(notif.department_id and profile.department_id and notif.department_id == profile.department_id)
            if not (is_own or is_dept):
                return Response({
                    "success": False,
                    "error": "Permission denied. You cannot access notifications belonging to another staff member or department.",
                    "code": "DEPARTMENT_FORBIDDEN"
                }, status=status.HTTP_403_FORBIDDEN)

        if not notif.is_read:
            notif.is_read = True
            notif.read_at = timezone.now()
            notif.save(update_fields=['is_read', 'read_at'])

        from notifications.navigation import resolve_notification_navigation
        nav = resolve_notification_navigation(notification=notif, user=user)

        return Response({
            "success": True,
            "notification_id": notif.id,
            "is_read": True,
            "target_url": nav.get('target_url', ''),
            "target_entity_type": nav.get('target_entity_type', ''),
            "target_entity_id": nav.get('target_entity_id', ''),
            "fallback_url": nav.get('fallback_url', ''),
            "action": nav.get('action', ''),
            "record_exists": nav.get('record_exists', True),
            "navigation": nav
        }, status=status.HTTP_200_OK)


class StaffNotificationReadAllView(APIView):
    """
    POST /api/staff/notifications/read-all/
    Marks all notifications for the logged-in staff as read.
    """
    permission_classes = [IsStaffUser]

    def post(self, request):
        user = request.user
        profile = getattr(user, 'staff_profile', None)

        if profile:
            StaffNotification.objects.filter(
                Q(recipient=profile) | Q(department=profile.department),
                is_read=False
            ).update(is_read=True, read_at=timezone.now())
        else:
            StaffNotification.objects.filter(is_read=False).update(is_read=True, read_at=timezone.now())

        return Response({"success": True, "message": "All notifications marked as read."}, status=status.HTTP_200_OK)

    def patch(self, request):
        return self.post(request)


# =============================================================================
# 9. ROLE-WISE DEDICATED DASHBOARDS & CENTRAL NAVIGATION
# =============================================================================

class StaffDashboardView(APIView):
    """
    GET /api/staff/dashboard/
    Dynamic real statistics based strictly on employee's verified department.
    Guarantees no cross-department metrics leak.
    """
    permission_classes = [IsStaffUser]

    def get(self, request):
        user = request.user
        profile = getattr(user, 'staff_profile', None)
        if profile:
            try:
                profile.refresh_from_db(fields=['department', 'status', 'must_change_password'])
            except Exception:
                pass

        is_admin = is_platform_admin(user)
        raw_dept = profile.department.code if (profile and profile.department) else ('ALL' if is_admin else None)
        dept_code = Department.normalize_code(raw_dept) if raw_dept != 'ALL' else 'ALL'
        today = timezone.now().date()

        data = {
            "department": profile.department.name if (profile and profile.department) else ("Platform Administration" if is_admin else "Unknown"),
            "department_code": dept_code,
            "employee_id": profile.employee_id if profile else ("ADMIN" if is_admin else "N/A"),
            "metrics": {}
        }

        # RESERVATION METRICS
        if dept_code in [Department.CODE_RESERVATION, 'ALL']:
            data["metrics"]["reservation"] = {
                "total_bookings": Booking.objects.count(),
                "confirmed_bookings": Booking.objects.filter(booking_status=Booking.STATUS_CONFIRMED).count(),
                "upcoming_checkins_today": Booking.objects.filter(check_in=today, booking_status=Booking.STATUS_CONFIRMED).count(),
                "upcoming_checkouts_today": Booking.objects.filter(check_out=today, booking_status__in=[Booking.STATUS_CONFIRMED, Booking.STATUS_CHECKED_IN]).count()
            }

        # CUSTOMER SUPPORT METRICS
        if dept_code in [Department.CODE_CUSTOMER_SUPPORT, 'ALL']:
            data["metrics"]["customer_support"] = {
                "open_tickets": SupportTicket.objects.filter(status='OPEN').count(),
                "in_progress_tickets": SupportTicket.objects.filter(status='IN_PROGRESS').count(),
                "resolved_tickets": SupportTicket.objects.filter(status='RESOLVED').count()
            }

        # REFUND METRICS
        if dept_code in [Department.CODE_REFUNDS_AND_CLAIMS, 'ALL']:
            data["metrics"]["refund"] = {
                "pending_refunds": Refund.objects.filter(status__in=[Refund.STATUS_REFUND_PENDING, 'PENDING']).count(),
                "processed_refunds": Refund.objects.filter(status=Refund.STATUS_REFUNDED).count(),
                "failed_refunds": Refund.objects.filter(status=Refund.STATUS_REFUND_FAILED).count()
            }

        # PAYOUT METRICS
        if dept_code in [Department.CODE_PAYOUT_AND_ESCROW, 'ALL']:
            data["metrics"]["payout"] = {
                "pending_payouts": HostPayout.objects.filter(status=HostPayout.STATUS_PENDING).count(),
                "eligible_payouts": HostPayout.objects.filter(status=HostPayout.STATUS_ELIGIBLE).count(),
                "completed_payouts": HostPayout.objects.filter(status=HostPayout.STATUS_COMPLETED).count()
            }

        # HOTEL VERIFICATION METRICS
        if dept_code in [Department.CODE_HOTEL_VERIFICATION, 'ALL']:
            data["metrics"]["hotel_verification"] = {
                "pending_verifications": Hotel.objects.filter(status__in=[Hotel.STATUS_SUBMITTED, Hotel.STATUS_UNDER_REVIEW]).count(),
                "approved_hotels": Hotel.objects.filter(status=Hotel.STATUS_APPROVED, is_approved=True).count(),
                "rejected_hotels": Hotel.objects.filter(status=Hotel.STATUS_REJECTED).count()
            }

        return Response({
            "success": True,
            "dashboard": data,
            "data": data,
            **data
        }, status=status.HTTP_200_OK)


class PortalNavigationDetailView(APIView):
    """
    GET /api/portal/navigation/ and /api/staff/portal/navigation/
    Centralized portal verification & navigation contract.
    Returns strictly isolated sidebar, layout, dashboard URL, permissions, and allowed routes for the authenticated user.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        role = str(getattr(user, 'role', '')).upper()

        # Enforce staff checks
        if role == 'STAFF':
            if not hasattr(user, 'staff_profile'):
                return Response({
                    "success": False,
                    "message": "Staff profile not found for this account.",
                    "code": "NO_STAFF_PROFILE"
                }, status=status.HTTP_403_FORBIDDEN)

            profile = user.staff_profile
            try:
                profile.refresh_from_db(fields=['department', 'status', 'must_change_password'])
            except Exception:
                pass
            if not profile.is_active_account:
                return Response({
                    "success": False,
                    "message": "Staff account is inactive or suspended.",
                    "code": "ACCOUNT_INACTIVE"
                }, status=status.HTTP_403_FORBIDDEN)
            if profile.must_change_password:
                return Response({
                    "success": False,
                    "message": "Temporary password change required before accessing portal navigation.",
                    "code": "PASSWORD_CHANGE_REQUIRED",
                    "must_change_password": True
                }, status=status.HTTP_403_FORBIDDEN)
            if not profile.department:
                return Response({
                    "success": False,
                    "message": "No department assigned to this staff account. Please contact Administrator.",
                    "code": "NO_DEPARTMENT_ASSIGNED"
                }, status=status.HTTP_403_FORBIDDEN)

        portal_def = get_portal_for_user(user)
        if not portal_def:
            return Response({
                "success": False,
                "message": "No authorized portal configured for this account role or department.",
                "code": "PORTAL_NOT_FOUND"
            }, status=status.HTTP_403_FORBIDDEN)

        # Build permissions list
        if is_platform_admin(user):
            perm_list = ["*"]
        elif role == 'STAFF' and hasattr(user, 'staff_profile'):
            perm_list = list(user.staff_profile.permissions.values_list('code', flat=True))
        else:
            perm_list = portal_def.get("permitted_actions", [])

        dept_code = None
        dept_name = None
        emp_id = None
        if hasattr(user, 'staff_profile') and user.staff_profile and user.staff_profile.department:
            dept_code = user.staff_profile.department.code
            dept_name = user.staff_profile.department.name
            emp_id = user.staff_profile.employee_id

        # Format navigation items with 'label' and 'path'
        nav_items = []
        for s in portal_def["sidebar"]:
            if not s.get("hidden_from_menu") and not s.get("hiddenFromMenu"):
                nav_items.append({
                    "id": s.get("id"),
                    "label": s.get("title", s.get("label")),
                    "title": s.get("title", s.get("label")),
                    "path": s.get("path"),
                    "icon": s.get("icon")
                })

        user_info = {
            "id": user.id,
            "email": getattr(user, 'email', ''),
            "full_name": user.get_full_name() or getattr(user, 'username', ''),
            "role": role,
            "is_staff": user.is_staff,
            "department": dept_code,
            "department_name": dept_name,
            "employee_id": emp_id
        }

        data_payload = {
            "role": role,
            "department": dept_code,
            "department_name": dept_name,
            "portal": portal_def["portal_id"],
            "portal_name": portal_def["portal_name"],
            "dashboard_url": portal_def["dashboard_url"],
            "layout": portal_def["layout"],
            "permissions": perm_list,
            "navigation": nav_items,
            "permitted_routes": portal_def["permitted_routes"],
            "permitted_actions": portal_def["permitted_actions"],
            "account_status": getattr(getattr(user, 'staff_profile', None), 'status', 'ACTIVE' if user.is_active else 'INACTIVE')
        }

        return Response({
            "success": True,
            "user": user_info,
            "portal": portal_def,
            "dashboard_url": portal_def["dashboard_url"],
            "layout": portal_def["layout"],
            "navigation": portal_def["sidebar"],
            "permitted_routes": portal_def["permitted_routes"],
            "permitted_actions": portal_def["permitted_actions"],
            "data": data_payload
        }, status=status.HTTP_200_OK)


class AdminDashboardView(APIView):
    """
    GET /api/admin/dashboard/
    Dedicated Admin Dashboard with comprehensive platform oversight metrics.
    Only accessible by users with ADMIN role.
    """
    permission_classes = [IsAdminUserRole]

    def get(self, request):
        today = timezone.now().date()

        # Staff metrics
        staff_total = StaffProfile.objects.count()
        staff_active = StaffProfile.objects.filter(status='ACTIVE').count()

        # User metrics
        customers_count = User.objects.filter(role='CUSTOMER').count()
        hotel_owners_count = User.objects.filter(role__in=['HOTEL_OWNER', 'HOTEL_STAFF']).count()

        # Hotels
        hotels_total = Hotel.objects.count()
        hotels_approved = Hotel.objects.filter(status=Hotel.STATUS_APPROVED, is_approved=True).count()
        hotels_pending = Hotel.objects.filter(status__in=[Hotel.STATUS_SUBMITTED, Hotel.STATUS_UNDER_REVIEW]).count()

        # Bookings
        bookings_total = Booking.objects.count()
        bookings_confirmed = Booking.objects.filter(booking_status=Booking.STATUS_CONFIRMED).count()
        bookings_completed = Booking.objects.filter(booking_status=Booking.STATUS_COMPLETED).count()
        bookings_cancelled = Booking.objects.filter(booking_status=Booking.STATUS_CANCELLED).count()

        # Payments volume
        payments_qs = Payment.objects.filter(status__in=[Payment.STATUS_CAPTURED, 'SUCCESS', 'PAID'])
        payments_total_count = payments_qs.count()
        payments_volume = payments_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        # Refunds oversight
        refunds_pending = Refund.objects.filter(status__in=[Refund.STATUS_REFUND_PENDING, 'PENDING']).count()
        refunds_processed = Refund.objects.filter(status=Refund.STATUS_REFUNDED).count()

        # Payouts oversight
        payouts_pending = HostPayout.objects.filter(status=HostPayout.STATUS_PENDING).count()
        payouts_completed = HostPayout.objects.filter(status=HostPayout.STATUS_COMPLETED).count()

        # Support oversight
        tickets_open = SupportTicket.objects.filter(status='OPEN').count()
        tickets_in_progress = SupportTicket.objects.filter(status='IN_PROGRESS').count()

        return Response({
            "success": True,
            "portal": PORTAL_ADMIN,
            "overview": {
                "staff": {"total": staff_total, "active": staff_active},
                "customers": {"total": customers_count},
                "hotel_owners": {"total": hotel_owners_count},
                "hotels": {"total": hotels_total, "approved": hotels_approved, "pending": hotels_pending},
                "bookings": {
                    "total": bookings_total,
                    "confirmed": bookings_confirmed,
                    "completed": bookings_completed,
                    "cancelled": bookings_cancelled
                },
                "financials": {
                    "payments_count": payments_total_count,
                    "total_revenue": float(payments_volume),
                    "pending_refunds": refunds_pending,
                    "processed_refunds": refunds_processed,
                    "pending_payouts": payouts_pending,
                    "completed_payouts": payouts_completed
                },
                "support": {
                    "open_tickets": tickets_open,
                    "in_progress_tickets": tickets_in_progress
                }
            }
        }, status=status.HTTP_200_OK)


class ReservationDashboardView(APIView):
    """
    GET /api/staff/reservation/dashboard/
    Dedicated Reservation Dashboard.
    Strictly restricted to Reservation Staff and Admin oversight.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_RESERVATION, 'VIEW_BOOKINGS')]

    def get(self, request):
        today = timezone.now().date()
        bookings_qs = Booking.objects.all().order_by('-created_at')

        total_bookings = bookings_qs.count()
        confirmed = bookings_qs.filter(booking_status=Booking.STATUS_CONFIRMED).count()
        checked_in = bookings_qs.filter(booking_status=Booking.STATUS_CHECKED_IN).count()
        completed = bookings_qs.filter(booking_status=Booking.STATUS_COMPLETED).count()
        cancelled = bookings_qs.filter(booking_status=Booking.STATUS_CANCELLED).count()

        upcoming_checkins = bookings_qs.filter(check_in=today, booking_status=Booking.STATUS_CONFIRMED).count()
        upcoming_checkouts = bookings_qs.filter(check_out=today, booking_status__in=[Booking.STATUS_CONFIRMED, Booking.STATUS_CHECKED_IN]).count()

        recent_bookings = list(bookings_qs[:10].values(
            'id', 'booking_id', 'booking_status', 'check_in', 'check_out',
            'guest_name', 'guest_phone', 'total_amount', 'created_at'
        ))

        return Response({
            "success": True,
            "portal": PORTAL_RESERVATION,
            "department": "RESERVATION",
            "metrics": {
                "total_bookings": total_bookings,
                "confirmed_bookings": confirmed,
                "checked_in_bookings": checked_in,
                "completed_bookings": completed,
                "cancelled_bookings": cancelled,
                "upcoming_checkins_today": upcoming_checkins,
                "upcoming_checkouts_today": upcoming_checkouts
            },
            "recent_bookings": recent_bookings
        }, status=status.HTTP_200_OK)


class CustomerSupportDashboardView(APIView):
    """
    GET /api/staff/support/dashboard/
    Dedicated Customer Support Dashboard.
    Strictly restricted to Customer Support Staff and Admin oversight.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_CUSTOMER_SUPPORT, 'MANAGE_SUPPORT')]

    def get(self, request):
        tickets_qs = SupportTicket.objects.all().order_by('-created_at')

        open_tickets = tickets_qs.filter(status='OPEN').count()
        in_progress = tickets_qs.filter(status='IN_PROGRESS').count()
        resolved = tickets_qs.filter(status='RESOLVED').count()
        closed = tickets_qs.filter(status='CLOSED').count()

        urgent_tickets = tickets_qs.filter(priority='URGENT', status__in=['OPEN', 'IN_PROGRESS']).count()
        high_tickets = tickets_qs.filter(priority='HIGH', status__in=['OPEN', 'IN_PROGRESS']).count()

        recent_tickets = list(tickets_qs[:10].values(
            'id', 'ticket_number', 'subject', 'category', 'priority', 'status', 'created_at'
        ))

        return Response({
            "success": True,
            "portal": PORTAL_CUSTOMER_SUPPORT,
            "department": "CUSTOMER_SUPPORT",
            "metrics": {
                "open_tickets": open_tickets,
                "in_progress_tickets": in_progress,
                "resolved_tickets": resolved,
                "closed_tickets": closed,
                "urgent_tickets": urgent_tickets,
                "high_priority_tickets": high_tickets
            },
            "recent_tickets": recent_tickets
        }, status=status.HTTP_200_OK)


class RefundsClaimsDashboardView(APIView):
    """
    GET /api/staff/refunds/dashboard/
    Dedicated Refunds & Claims Dashboard.
    Strictly restricted to Refunds & Claims Staff and Admin oversight.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_REFUNDS_AND_CLAIMS, 'VIEW_REFUNDS')]

    def get(self, request):
        refunds_qs = Refund.objects.all().order_by('-created_at')

        pending_refunds = refunds_qs.filter(status__in=[Refund.STATUS_REFUND_PENDING, 'PENDING']).count()
        processed_refunds = refunds_qs.filter(status=Refund.STATUS_REFUNDED).count()
        failed_refunds = refunds_qs.filter(status=Refund.STATUS_REFUND_FAILED).count()

        total_refunded = refunds_qs.filter(status=Refund.STATUS_REFUNDED).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        pending_amount = refunds_qs.filter(status__in=[Refund.STATUS_REFUND_PENDING, 'PENDING']).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        recent_refunds = list(refunds_qs[:10].values(
            'id', 'booking_id', 'amount', 'status', 'reason', 'created_at'
        ))

        return Response({
            "success": True,
            "portal": PORTAL_REFUNDS_AND_CLAIMS,
            "department": "REFUNDS_AND_CLAIMS",
            "metrics": {
                "pending_refunds": pending_refunds,
                "processed_refunds": processed_refunds,
                "failed_refunds": failed_refunds,
                "total_refunded_amount": float(total_refunded),
                "pending_refund_amount": float(pending_amount)
            },
            "recent_refunds": recent_refunds
        }, status=status.HTTP_200_OK)


class PayoutEscrowDashboardView(APIView):
    """
    GET /api/staff/payouts/dashboard/
    Dedicated Payout & Escrow Dashboard.
    Strictly restricted to Payout & Escrow Staff and Admin oversight.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_PAYOUT_AND_ESCROW, 'VIEW_PAYOUTS')]

    def get(self, request):
        payouts_qs = HostPayout.objects.all().order_by('-created_at')

        pending_payouts = payouts_qs.filter(status=HostPayout.STATUS_PENDING).count()
        eligible_payouts = payouts_qs.filter(status=HostPayout.STATUS_ELIGIBLE).count()
        completed_payouts = payouts_qs.filter(status=HostPayout.STATUS_COMPLETED).count()
        failed_payouts = payouts_qs.filter(status=HostPayout.STATUS_FAILED).count()

        total_paid_out = payouts_qs.filter(status=HostPayout.STATUS_COMPLETED).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        escrow_holding = HostEarning.objects.filter(status=HostEarning.STATUS_ON_HOLD).aggregate(total=Sum('net_amount'))['total'] or Decimal('0.00')

        recent_payouts = list(payouts_qs[:10].values(
            'id', 'payout_id', 'host_id', 'amount', 'status', 'created_at'
        ))

        return Response({
            "success": True,
            "portal": PORTAL_PAYOUT_AND_ESCROW,
            "department": "PAYOUT_AND_ESCROW",
            "metrics": {
                "pending_payouts": pending_payouts,
                "eligible_payouts": eligible_payouts,
                "completed_payouts": completed_payouts,
                "failed_payouts": failed_payouts,
                "total_paid_out": float(total_paid_out),
                "total_escrow_holding": float(escrow_holding)
            },
            "recent_payouts": recent_payouts
        }, status=status.HTTP_200_OK)


class HotelVerificationDashboardView(APIView):
    """
    GET /api/staff/verification/dashboard/
    Dedicated Hotel Verification Dashboard.
    Strictly restricted to Hotel Verification Staff and Admin oversight.
    """
    permission_classes = [HasDepartmentPermission(Department.CODE_HOTEL_VERIFICATION, 'VERIFY_HOTEL')]

    def get(self, request):
        hotels_qs = Hotel.objects.all().order_by('-created_at')

        pending_verifications = hotels_qs.filter(status=Hotel.STATUS_SUBMITTED).count()
        under_review = hotels_qs.filter(status=Hotel.STATUS_UNDER_REVIEW).count()
        approved_hotels = hotels_qs.filter(status=Hotel.STATUS_APPROVED, is_approved=True).count()
        rejected_hotels = hotels_qs.filter(status=Hotel.STATUS_REJECTED).count()

        recent_applications = list(hotels_qs[:10].values(
            'id', 'name', 'status', 'city', 'state', 'created_at', 'is_approved'
        ))

        return Response({
            "success": True,
            "portal": PORTAL_HOTEL_VERIFICATION,
            "department": "HOTEL_VERIFICATION",
            "metrics": {
                "pending_verifications": pending_verifications,
                "under_review_hotels": under_review,
                "approved_hotels": approved_hotels,
                "rejected_hotels": rejected_hotels
            },
            "recent_applications": recent_applications
        }, status=status.HTTP_200_OK)
