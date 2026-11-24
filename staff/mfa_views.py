"""
Multi-Factor Authentication (MFA) views for GoOnStay Manager & Admin hierarchy.
Mandatory TOTP MFA for Level 2 (Department Staff Manager), Level 3 (Main Manager),
and Level 4 (Admin / Super Admin).
"""

import json
from django.utils import timezone
from django.conf import settings
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.contrib.auth import get_user_model
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .models import ManagerMFAProfile, HierarchyAuditLog, StaffProfile
from .serializers import StaffProfileDetailSerializer
from .permissions import is_platform_admin, get_department_portal_info
from .services import (
    get_user_hierarchy_level, log_hierarchy_audit
)
from util.totp import (
    generate_totp_secret, verify_totp_code,
    get_provisioning_uri, generate_backup_codes,
    hash_backup_code, verify_and_consume_backup_code
)

User = get_user_model()
signer = TimestampSigner()


def _get_user_from_temp_token(token_str, max_age=600):
    """Decodes and validates a signed temporary pre-auth MFA token (valid 10 minutes)."""
    if not token_str:
        return None
    try:
        unsigned = signer.unsign(token_str, max_age=max_age)
        prefix, user_id = unsigned.split(':', 1)
        return User.objects.filter(id=int(user_id), is_active=True).first()
    except (BadSignature, SignatureExpired, ValueError):
        return None


class MFASetupView(APIView):
    """
    POST /api/staff/mfa/setup/
    Initiate MFA enrollment. Generates TOTP secret, provisioning URI, and 8 backup codes.
    Accessible with valid authentication or valid pre-auth temp_token.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        user = request.user if (request.user and request.user.is_authenticated) else None
        if not user:
            temp_token = request.data.get('temp_token')
            user = _get_user_from_temp_token(temp_token)

        if not user:
            return Response({
                "success": False,
                "code": "AUTHENTICATION_REQUIRED",
                "error": "Authentication or valid temporary token required."
            }, status=status.HTTP_401_UNAUTHORIZED)

        profile, _ = ManagerMFAProfile.objects.get_or_create(
            user=user,
            defaults={'totp_secret': generate_totp_secret()}
        )
        if not profile.totp_secret:
            profile.totp_secret = generate_totp_secret()

        # Generate fresh backup codes
        raw_backup_codes = generate_backup_codes(count=8)
        hashed_codes = [hash_backup_code(c) for c in raw_backup_codes]
        profile.backup_codes_hash = json.dumps(hashed_codes)
        profile.save()

        uri = get_provisioning_uri(profile.totp_secret, user.username)

        # Generate a new temp token for confirmation
        confirmation_token = signer.sign(f"mfa_enroll:{user.id}")

        return Response({
            "success": True,
            "message": "MFA setup initiated. Configure your authenticator application.",
            "secret": profile.totp_secret,
            "provisioning_uri": uri,
            "backup_codes": raw_backup_codes,
            "temp_token": confirmation_token
        }, status=status.HTTP_200_OK)


class MFAEnrollVerifyView(APIView):
    """
    POST /api/staff/mfa/enroll-verify/
    Verifies the first TOTP code and activates MFA for the user account.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        user = request.user if (request.user and request.user.is_authenticated) else None
        if not user:
            temp_token = request.data.get('temp_token')
            user = _get_user_from_temp_token(temp_token)

        if not user:
            return Response({
                "success": False,
                "code": "AUTHENTICATION_REQUIRED",
                "error": "Authentication or valid temporary token required."
            }, status=status.HTTP_401_UNAUTHORIZED)

        profile = ManagerMFAProfile.objects.filter(user=user).first()
        if not profile or not profile.totp_secret:
            return Response({
                "success": False,
                "code": "MFA_NOT_INITIALIZED",
                "error": "MFA setup has not been initiated for this account."
            }, status=status.HTTP_400_BAD_REQUEST)

        code = request.data.get('totp_code') or request.data.get('code')
        if not code or not verify_totp_code(profile.totp_secret, code):
            return Response({
                "success": False,
                "code": "INVALID_MFA_CODE",
                "error": "Invalid verification code. Please check your authenticator app."
            }, status=status.HTTP_400_BAD_REQUEST)

        profile.is_mfa_enabled = True
        profile.is_enrolled = True
        profile.last_verified_at = timezone.now()
        profile.failed_attempts = 0
        profile.locked_until = None
        profile.save()

        log_hierarchy_audit(
            actor_user=user,
            action_type=HierarchyAuditLog.ACTION_MFA_ENROLL,
            target_user=user,
            description="MFA successfully enrolled and activated.",
            request=request
        )

        # Issue JWT tokens
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        staff_prof = getattr(user, 'staff_profile', None)
        dept_code = staff_prof.department.code if (staff_prof and staff_prof.department) else None
        portal_info = get_department_portal_info(dept_code)

        return Response({
            "success": True,
            "message": "MFA successfully enrolled and verified.",
            "access": access_token,
            "refresh": refresh_token,
            "token": access_token,
            "tokens": {"access": access_token, "refresh": refresh_token},
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role
            },
            "staff_profile": StaffProfileDetailSerializer(staff_prof).data if staff_prof else None,
            "portal_info": portal_info
        }, status=status.HTTP_200_OK)


class MFAVerifyView(APIView):
    """
    POST /api/staff/mfa/verify/
    Verify TOTP or backup code during login challenge.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        temp_token = request.data.get('temp_token')
        code = request.data.get('totp_code') or request.data.get('code')
        backup_code = request.data.get('backup_code')

        user = _get_user_from_temp_token(temp_token)
        if not user:
            return Response({
                "success": False,
                "code": "EXPIRED_SESSION",
                "error": "MFA session expired or invalid. Please login again."
            }, status=status.HTTP_401_UNAUTHORIZED)

        profile = ManagerMFAProfile.objects.filter(user=user).first()
        if not profile or not profile.is_mfa_enabled:
            return Response({
                "success": False,
                "code": "MFA_NOT_ENABLED",
                "error": "MFA is not enabled for this user."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check account lockout
        if profile.locked_until and profile.locked_until > timezone.now():
            remaining = int((profile.locked_until - timezone.now()).total_seconds())
            return Response({
                "success": False,
                "code": "ACCOUNT_LOCKED",
                "error": f"Account temporarily locked due to excessive failed attempts. Try again in {remaining} seconds."
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)

        # Verify either TOTP code or Backup code
        is_valid = False
        used_backup = False

        if code:
            is_valid = verify_totp_code(profile.totp_secret, code)

        if not is_valid and backup_code and profile.backup_codes_hash:
            try:
                hashed_list = json.loads(profile.backup_codes_hash)
                matched, remaining = verify_and_consume_backup_code(backup_code, hashed_list)
                if matched:
                    is_valid = True
                    used_backup = True
                    profile.backup_codes_hash = json.dumps(remaining)
            except Exception:
                pass

        if not is_valid:
            profile.failed_attempts += 1
            if profile.failed_attempts >= 5:
                profile.locked_until = timezone.now() + timezone.timedelta(minutes=15)
                profile.failed_attempts = 0
            profile.save()

            log_hierarchy_audit(
                actor_user=user,
                action_type=HierarchyAuditLog.ACTION_LOGIN_MFA_FAILED,
                target_user=user,
                description="Failed MFA verification attempt.",
                request=request
            )
            return Response({
                "success": False,
                "code": "INVALID_MFA_CODE",
                "error": "Invalid verification code."
            }, status=status.HTTP_401_UNAUTHORIZED)

        # Success
        profile.failed_attempts = 0
        profile.locked_until = None
        profile.last_verified_at = timezone.now()
        profile.save()

        log_hierarchy_audit(
            actor_user=user,
            action_type=HierarchyAuditLog.ACTION_LOGIN_MFA_SUCCESS,
            target_user=user,
            description="MFA verified successfully." + (" (Used backup code)" if used_backup else ""),
            request=request
        )

        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        staff_prof = getattr(user, 'staff_profile', None)
        dept_code = staff_prof.department.code if (staff_prof and staff_prof.department) else None
        portal_info = get_department_portal_info(dept_code)

        return Response({
            "success": True,
            "message": "Authentication successful.",
            "access": access_token,
            "refresh": refresh_token,
            "token": access_token,
            "tokens": {"access": access_token, "refresh": refresh_token},
            "must_change_password": staff_prof.must_change_password if staff_prof else False,
            "is_admin": is_platform_admin(user),
            "department": dept_code,
            "department_name": staff_prof.department.name if (staff_prof and staff_prof.department) else None,
            "portal": portal_info["portal"],
            "portal_name": portal_info["portal_name"],
            "portal_url": portal_info["portal_url"],
            "portal_info": portal_info,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": user.role
            },
            "staff_profile": StaffProfileDetailSerializer(staff_prof).data if staff_prof else None
        }, status=status.HTTP_200_OK)


class MFADisableView(APIView):
    """
    POST /api/staff/mfa/disable/
    Admin-only endpoint to reset/disable MFA for a compromised or locked account.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not is_platform_admin(request.user):
            return Response({
                "success": False,
                "code": "FORBIDDEN",
                "error": "Only Administrators can disable or reset MFA."
            }, status=status.HTTP_403_FORBIDDEN)

        target_user_id = request.data.get('user_id')
        if not target_user_id:
            return Response({
                "success": False,
                "error": "user_id is required."
            }, status=status.HTTP_400_BAD_REQUEST)

        target_user = User.objects.filter(id=target_user_id).first()
        if not target_user:
            return Response({
                "success": False,
                "error": "Target user not found."
            }, status=status.HTTP_404_NOT_FOUND)

        profile = ManagerMFAProfile.objects.filter(user=target_user).first()
        if profile:
            profile.is_mfa_enabled = False
            profile.is_enrolled = False
            profile.totp_secret = generate_totp_secret()
            profile.backup_codes_hash = ''
            profile.failed_attempts = 0
            profile.locked_until = None
            profile.save()

        log_hierarchy_audit(
            actor_user=request.user,
            action_type=HierarchyAuditLog.ACTION_MFA_DISABLE,
            target_user=target_user,
            description=f"Administrator {request.user.username} reset MFA for {target_user.username}.",
            request=request
        )

        return Response({
            "success": True,
            "message": f"MFA has been reset for {target_user.username}."
        }, status=status.HTTP_200_OK)
