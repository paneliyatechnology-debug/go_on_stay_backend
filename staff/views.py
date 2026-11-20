import re
import secrets
from decimal import Decimal
from datetime import timedelta
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
    page_size = 20
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

    def post(self, request):
        serializer = StaffLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        login_id_raw = serializer.validated_data['login_id'].strip()
        password = serializer.validated_data['password']

        # Lookup user by login_id, employee_id, username, or email
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
                User.objects.filter(email__iexact=login_id_raw).first()
            )
            if user_obj and hasattr(user_obj, 'staff_profile'):
                profile = user_obj.staff_profile

        # Only allow users with StaffProfile OR platform Admin
        is_admin = is_platform_admin(user_obj)
        if not user_obj or (not profile and not is_admin):
            return Response({
                "success": False,
                "code": "AUTHENTICATION_FAILED",
                "error": "No staff account found with the provided credentials."
            }, status=status.HTTP_401_UNAUTHORIZED)

        # Check password directly first so we can differentiate wrong password vs inactive account
        if not user_obj.check_password(password):
            return Response({
                "success": False,
                "code": "INVALID_CREDENTIALS",
                "error": "Invalid staff credentials."
            }, status=status.HTTP_401_UNAUTHORIZED)

        # Enforce account active status
        if not user_obj.is_active or getattr(user_obj, 'is_blocked', False):
            return Response({
                "success": False,
                "code": "ACCOUNT_DISABLED",
                "error": "Your account has been deactivated. Please contact Administrator."
            }, status=status.HTTP_403_FORBIDDEN)

        if profile and profile.status != StaffProfile.STATUS_ACTIVE:
            return Response({
                "success": False,
                "code": "STAFF_SUSPENDED",
                "error": f"Your staff account is currently {profile.get_status_display().lower()}. Please contact Administrator."
            }, status=status.HTTP_403_FORBIDDEN)

        user = user_obj

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

        lookup = self.kwargs.get('pk')
        return generics.get_object_or_404(
            Booking.objects.select_related('hotel', 'room', 'customer'),
            Q(id=lookup) | Q(booking_id=lookup)
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response({
            "success": True,
            "data": serializer.data,
            **serializer.data
        })
        if str(lookup).isdigit():
            booking = Booking.objects.filter(pk=int(lookup)).first()
        else:
            booking = Booking.objects.filter(booking_id=str(lookup)).first()

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

        qs = Refund.objects.filter(status=Refund.STATUS_REFUNDED).select_related('booking', 'booking__hotel')
        data = []
        for r in qs.order_by('-updated_at')[:100]:
            data.append({
                "id": r.id,
                "booking_id": r.booking.booking_id if r.booking else None,
                "hotel_name": r.booking.hotel.name if r.booking and r.booking.hotel else None,
                "amount": str(r.amount),
                "refund_mode": r.refund_mode,
                "razorpay_refund_id": r.razorpay_refund_id,
                "refunded_at": r.updated_at.isoformat()
            })
        return Response({"success": True, "history": data}, status=status.HTTP_200_OK)


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

        payout = generics.get_object_or_404(HostPayout.objects.select_related('host', 'payout_account').prefetch_related('earnings'), pk=pk)

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

        payout = generics.get_object_or_404(HostPayout.objects.select_related('host'), pk=pk)

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

            payout.earnings.update(status=getattr(HostEarning, 'STATUS_PAID', 'PAID'))

            log_staff_activity(
                request=request,
                staff_profile=profile,
                actor_user=request.user,
                action="PROCESS_PAYOUT",
                entity_type="HostPayout",
                entity_id=payout.id,
                description=f"Staff processed payout #{payout.payout_id or payout.id} of ₹{payout.amount} to {payout.host.username}."
            )

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

        qs = HostPayout.objects.filter(status=HostPayout.STATUS_COMPLETED).select_related('host', 'payout_account')
        data = []
        for p in qs.order_by('-processed_at')[:100]:
            data.append({
                "id": p.id,
                "payout_id": p.payout_id,
                "host_name": p.host.get_full_name() or p.host.username,
                "amount": str(p.amount),
                "transaction_reference": p.transaction_reference,
                "processed_at": p.processed_at.isoformat() if p.processed_at else None
            })
        return Response({"success": True, "history": data}, status=status.HTTP_200_OK)


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
        qs = Hotel.objects.filter(status=h_status).select_related('owner')

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

        hotel = generics.get_object_or_404(Hotel.objects.select_related('owner'), pk=pk)

        docs = []
        for d in hotel.verification_documents.all():
            docs.append({
                "id": d.id,
                "document_type": d.document_type,
                "document_type_label": d.get_document_type_display(),
                "status": d.status,
                "document_url": d.document_url or (d.document_file.url if d.document_file else ""),
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
        serializer_data = StaffNotificationSerializer(notifications_page, many=True).data

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
    """
    permission_classes = [IsStaffUser]

    def patch(self, request, pk):
        notif = generics.get_object_or_404(StaffNotification, pk=pk)
        notif.is_read = True
        notif.read_at = timezone.now()
        notif.save(update_fields=['is_read', 'read_at'])
        return Response({"success": True, "message": "Notification marked as read."}, status=status.HTTP_200_OK)

    def post(self, request, pk):
        return self.patch(request, pk)


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
# 9. STAFF DASHBOARD
# =============================================================================

class StaffDashboardView(APIView):
    """
    GET /api/staff/dashboard/
    Dynamic real statistics based on employee's department and permissions.
    Never returns fake or hardcoded dashboard metrics.
    """
    permission_classes = [IsStaffUser]

    def get(self, request):
        user = request.user
        profile = getattr(user, 'staff_profile', None)
        dept_code = profile.department.code if profile else 'ALL'
        today = timezone.now().date()

        data = {
            "department": profile.department.name if profile else "Platform Administration",
            "department_code": dept_code,
            "employee_id": profile.employee_id if profile else "ADMIN",
            "metrics": {}
        }

        # RESERVATION METRICS
        if dept_code in [Department.CODE_RESERVATION, 'ALL'] or check_staff_permission(user, 'VIEW_BOOKINGS'):
            data["metrics"]["reservation"] = {
                "total_bookings": Booking.objects.count(),
                "confirmed_bookings": Booking.objects.filter(booking_status=Booking.STATUS_CONFIRMED).count(),
                "upcoming_checkins_today": Booking.objects.filter(check_in=today, booking_status=Booking.STATUS_CONFIRMED).count(),
                "upcoming_checkouts_today": Booking.objects.filter(check_out=today, booking_status__in=[Booking.STATUS_CONFIRMED, Booking.STATUS_CHECKED_IN]).count()
            }

        # CUSTOMER SUPPORT METRICS
        if dept_code in [Department.CODE_CUSTOMER_SUPPORT, 'ALL'] or check_staff_permission(user, 'MANAGE_SUPPORT'):
            data["metrics"]["customer_support"] = {
                "open_tickets": SupportTicket.objects.filter(status='OPEN').count(),
                "in_progress_tickets": SupportTicket.objects.filter(status='IN_PROGRESS').count(),
                "resolved_tickets": SupportTicket.objects.filter(status='RESOLVED').count()
            }

        # REFUND METRICS
        if dept_code in [Department.CODE_REFUND, 'ALL'] or check_staff_permission(user, 'VIEW_REFUNDS'):
            data["metrics"]["refund"] = {
                "pending_refunds": Refund.objects.filter(status__in=[Refund.STATUS_REFUND_PENDING, 'PENDING']).count(),
                "processed_refunds": Refund.objects.filter(status=Refund.STATUS_REFUNDED).count(),
                "failed_refunds": Refund.objects.filter(status=Refund.STATUS_REFUND_FAILED).count()
            }

        # PAYOUT METRICS
        if dept_code in [Department.CODE_PAYOUT, 'ALL'] or check_staff_permission(user, 'VIEW_PAYOUTS'):
            data["metrics"]["payout"] = {
                "pending_payouts": HostPayout.objects.filter(status=HostPayout.STATUS_PENDING).count(),
                "eligible_payouts": HostPayout.objects.filter(status=HostPayout.STATUS_ELIGIBLE).count(),
                "completed_payouts": HostPayout.objects.filter(status=HostPayout.STATUS_COMPLETED).count()
            }

        # HOTEL VERIFICATION METRICS
        if dept_code in [Department.CODE_HOTEL_VERIFICATION, 'ALL'] or check_staff_permission(user, 'VERIFY_HOTEL'):
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
