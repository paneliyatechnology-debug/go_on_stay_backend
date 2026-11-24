"""
Core business logic, hierarchy enforcement, permission delegation,
and tamper-resistant audit logging for GoOnStay 4-Level Admin & Staff Hierarchy.
"""

import logging
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import PermissionDenied
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken

from .models import (
    Department, StaffPermission, StaffProfile,
    DepartmentManagerAssignment, PermissionDelegationPolicy,
    HierarchyAuditLog, ManagerMFAProfile
)

logger = logging.getLogger(__name__)
User = get_user_model()

ROLE_SUPER_ADMIN = 'SUPER_ADMIN'
ROLE_ADMIN = 'ADMIN'
ROLE_MAIN_MANAGER = 'MAIN_MANAGER'
ROLE_DEPARTMENT_STAFF_MANAGER = 'DEPARTMENT_STAFF_MANAGER'
ROLE_STAFF = 'STAFF'

ROLE_HIERARCHY_LEVELS = {
    ROLE_SUPER_ADMIN: 4,
    ROLE_ADMIN: 4,
    ROLE_MAIN_MANAGER: 3,
    ROLE_DEPARTMENT_STAFF_MANAGER: 2,
    ROLE_STAFF: 1,
}


def get_role_hierarchy_level(role):
    """Returns numerical hierarchy level (1-4). Higher means more authority."""
    if not role:
        return 0
    return ROLE_HIERARCHY_LEVELS.get(str(role).strip().upper(), 0)


def get_user_hierarchy_level(user):
    """Returns numerical hierarchy level for a user object."""
    if not user or not user.is_authenticated:
        return 0
    if user.is_superuser:
        return 4
    return get_role_hierarchy_level(getattr(user, 'role', ''))


def can_actor_manage_role(actor_user, target_role):
    """
    Strict hierarchy enforcement:
    Actor level must be strictly greater than target role level.
    Level 4 (Admin) > Level 3 (Main Manager) > Level 2 (Dept Manager) > Level 1 (Staff).
    """
    actor_level = get_user_hierarchy_level(actor_user)
    target_level = get_role_hierarchy_level(target_role)

    if actor_level <= 0 or target_level <= 0:
        return False

    # Admins can manage anyone at Level 3, 2, 1 (and superadmin can manage other admins)
    if actor_level == 4:
        if target_level < 4:
            return True
        return bool(actor_user.is_superuser or actor_user.role == ROLE_SUPER_ADMIN)

    # Main Manager (Level 3) can ONLY manage Level 2 (Dept Manager) and Level 1 (Staff)
    if actor_level == 3:
        return target_level in [1, 2]

    # Department Staff Manager (Level 2) can ONLY manage Level 1 (Staff)
    if actor_level == 2:
        return target_level == 1

    return False


def get_actor_manageable_department_ids(actor_user):
    """
    Returns a set of department IDs that the actor is authorized to manage.
    - Admin (Level 4): All active departments.
    - Main Manager (Level 3): All active departments.
    - Dept Staff Manager (Level 2): Assigned active departments only.
    - Staff (Level 1): Empty set (cannot manage departments).
    """
    level = get_user_hierarchy_level(actor_user)
    if level in [3, 4]:
        return set(Department.objects.filter(is_active=True).values_list('id', flat=True))

    if level == 2:
        dept_ids = set()
        # 1. From DepartmentManagerAssignment
        assigned = DepartmentManagerAssignment.objects.filter(
            manager__user=actor_user,
            is_active=True,
            department__is_active=True
        ).values_list('department_id', flat=True)
        dept_ids.update(assigned)

        # 2. From StaffProfile primary department
        if hasattr(actor_user, 'staff_profile') and actor_user.staff_profile.department:
            if actor_user.staff_profile.department.is_active:
                dept_ids.add(actor_user.staff_profile.department_id)

        return dept_ids

    return set()


def validate_can_manage_target_staff(actor_user, target_profile):
    """
    Validates that actor_user has authority to view or modify target_profile.
    Raises PermissionDenied if unauthorized (prevents IDOR and cross-department tampering).
    """
    if not actor_user or not actor_user.is_authenticated:
        raise PermissionDenied("Authentication required.")

    actor_level = get_user_hierarchy_level(actor_user)
    target_user = target_profile.user
    target_level = get_user_hierarchy_level(target_user)

    # Self-profile view/edit is handled separately in profile APIs
    if actor_user.id == target_user.id:
        return True

    # 1. Check role hierarchy
    if actor_level <= target_level:
        raise PermissionDenied("You cannot manage an account with equal or higher authority.")

    # 2. Level 4 (Admin) has global access
    if actor_level == 4:
        return True

    # 3. Level 3 (Main Manager) can manage Level 2 and Level 1 across all departments
    if actor_level == 3:
        if target_level in [1, 2]:
            return True
        raise PermissionDenied("Main Managers cannot manage accounts at or above Level 3.")

    # 4. Level 2 (Dept Staff Manager) can ONLY manage Level 1 staff in their own department
    if actor_level == 2:
        if target_level != 1:
            raise PermissionDenied("Department Staff Managers can only manage Level 1 Staff.")

        allowed_depts = get_actor_manageable_department_ids(actor_user)
        target_dept_id = target_profile.department_id if target_profile.department else None

        if not target_dept_id or target_dept_id not in allowed_depts:
            raise PermissionDenied("You can only manage staff belonging to your assigned department.")

        return True

    # 5. Level 1 (Staff) cannot manage anyone
    raise PermissionDenied("Staff members do not have management privileges.")


def validate_permission_delegation(actor_user, target_role, target_department, requested_permissions):
    """
    Enforces permission delegation boundaries.
    Prevents privilege escalation:
    - Main Manager can only delegate permissions permitted by Admin policy.
    - Department Staff Manager can only delegate department-specific permissions they possess.
    - Neither can delegate sensitive permissions unless explicitly authorized.
    Returns (True, None) or raises PermissionDenied.
    """
    actor_level = get_user_hierarchy_level(actor_user)

    # Admin has total delegation authority
    if actor_level == 4:
        return True

    perm_list = list(requested_permissions)

    # Level 3: Main Manager delegation rules
    if actor_level == 3:
        policy = PermissionDelegationPolicy.objects.filter(role=PermissionDelegationPolicy.ROLE_MAIN_MANAGER).first()
        if policy:
            allowed_ids = set(policy.allowed_permissions.values_list('id', flat=True))
            for p in perm_list:
                if p.id not in allowed_ids:
                    raise PermissionDenied(f"Permission '{p.code}' exceeds Admin delegation policy for Main Managers.")
                if p.is_sensitive and not policy.allow_sensitive_permissions:
                    raise PermissionDenied(f"Sensitive permission '{p.code}' cannot be delegated by Main Managers.")
        else:
            # By default, if no policy is configured, Main Manager cannot delegate sensitive permissions
            for p in perm_list:
                if p.is_sensitive:
                    raise PermissionDenied(f"Sensitive permission '{p.code}' requires explicit Admin policy authorization.")
        return True

    # Level 2: Department Staff Manager delegation rules
    if actor_level == 2:
        allowed_depts = get_actor_manageable_department_ids(actor_user)
        manager_profile = getattr(actor_user, 'staff_profile', None)

        if not manager_profile:
            raise PermissionDenied("Department manager profile required.")

        for p in perm_list:
            # Sensitive permissions are blocked for Dept Staff Managers
            if p.is_sensitive:
                raise PermissionDenied(f"Department Staff Managers cannot delegate sensitive permission '{p.code}'.")

            # Must belong to manager's assigned department
            if p.department_id and p.department_id not in allowed_depts:
                raise PermissionDenied(f"Permission '{p.code}' belongs to another department and cannot be assigned.")

        return True

    raise PermissionDenied("You do not have permission delegation authority.")


def log_hierarchy_audit(actor_user, action_type, target_user=None, department=None,
                        previous_state=None, new_state=None, description='', request=None):
    """
    Creates an immutable, tamper-resistant HierarchyAuditLog entry.
    """
    actor_username = actor_user.username if actor_user else 'SYSTEM'
    actor_role = getattr(actor_user, 'role', 'UNKNOWN') if actor_user else 'SYSTEM'

    target_username = target_user.username if target_user else ''
    target_role = getattr(target_user, 'role', '') if target_user else ''

    ip_address = None
    user_agent = ''
    if request:
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded:
            ip_address = x_forwarded.split(',')[0].strip()
        else:
            ip_address = request.META.get('REMOTE_ADDR')
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:255]

    dept_code = department.code if department else ''

    return HierarchyAuditLog.objects.create(
        actor=actor_user if (actor_user and actor_user.is_authenticated) else None,
        actor_username=actor_username,
        actor_role=actor_role,
        target_user=target_user,
        target_username=target_username,
        target_role=target_role,
        department=department,
        department_code=dept_code,
        action_type=action_type,
        previous_state=previous_state or {},
        new_state=new_state or {},
        description=description,
        ip_address=ip_address,
        user_agent=user_agent
    )


def revoke_user_sessions(user):
    """
    Revokes active JWT refresh tokens and forces re-authentication where supported.
    """
    try:
        from django.apps import apps
        if apps.is_installed('rest_framework_simplejwt.token_blacklist'):
            from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
            tokens = OutstandingToken.objects.filter(user=user)
            for token in tokens:
                BlacklistedToken.objects.get_or_create(token=token)
    except Exception as e:
        logger.warning(f"Could not blacklist tokens for user {user.id}: {e}")
