from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied
from django.contrib.auth import get_user_model


def is_platform_admin(user):
    """Checks if user possesses platform Admin privileges."""
    if not (user and user.is_authenticated):
        return False
    role = str(getattr(user, 'role', '')).upper()
    if role in ['STAFF', 'CUSTOMER', 'HOTEL_OWNER', 'HOTEL_STAFF', 'SUPPORT_AGENT']:
        return False
    return user.is_superuser or role in ['ADMIN', 'SUPER_ADMIN']


PORTAL_MAPPINGS = {
    'RESERVATION': {
        'portal': 'RESERVATION',
        'portal_name': 'Reservation Portal',
        'portal_url': '/staff/reservation',
        'department_code': 'RESERVATION',
        'department_name': 'Reservation',
    },
    'CUSTOMER_SUPPORT': {
        'portal': 'CUSTOMER_SUPPORT',
        'portal_name': 'Customer Support Portal',
        'portal_url': '/staff/support',
        'department_code': 'CUSTOMER_SUPPORT',
        'department_name': 'Customer Support',
    },
    'REFUNDS_AND_CLAIMS': {
        'portal': 'REFUNDS_AND_CLAIMS',
        'portal_name': 'Refunds & Claims Portal',
        'portal_url': '/staff/refunds',
        'department_code': 'REFUNDS_AND_CLAIMS',
        'department_name': 'Refunds & Claims',
    },
    'PAYOUT_AND_ESCROW': {
        'portal': 'PAYOUT_AND_ESCROW',
        'portal_name': 'Payout & Escrow Portal',
        'portal_url': '/staff/payouts',
        'department_code': 'PAYOUT_AND_ESCROW',
        'department_name': 'Payout & Escrow',
    },
    'HOTEL_VERIFICATION': {
        'portal': 'HOTEL_VERIFICATION',
        'portal_name': 'Hotel Verification Portal',
        'portal_url': '/staff/verification',
        'department_code': 'HOTEL_VERIFICATION',
        'department_name': 'Hotel Verification',
    },
}


def get_department_portal_info(department_code):
    """
    Returns verified portal mapping for a given department code.
    Prevents staff from accessing other departments' portals.
    """
    if not department_code:
        return {
            'portal': 'STAFF_PORTAL',
            'portal_name': 'Staff Portal',
            'portal_url': '/staff/dashboard',
            'department_code': 'NONE',
            'department_name': 'Unassigned',
        }

    c = str(department_code).strip().upper()
    if c in ['REFUND', 'REFUNDS', 'REFUNDS_AND_CLAIMS', 'CLAIMS']:
        normalized = 'REFUNDS_AND_CLAIMS'
    elif c in ['PAYOUT', 'PAYOUTS', 'PAYOUT_AND_ESCROW', 'ESCROW']:
        normalized = 'PAYOUT_AND_ESCROW'
    elif c in ['SUPPORT', 'CUSTOMER_SUPPORT', 'CS']:
        normalized = 'CUSTOMER_SUPPORT'
    elif c in ['HOTEL', 'HOTEL_VERIFICATION', 'VERIFICATION']:
        normalized = 'HOTEL_VERIFICATION'
    elif c in ['RESERVATION', 'RESERVATIONS', 'BOOKING', 'BOOKINGS']:
        normalized = 'RESERVATION'
    else:
        normalized = c

    return PORTAL_MAPPINGS.get(normalized, {
        'portal': normalized,
        'portal_name': f'{normalized.title()} Portal',
        'portal_url': f'/staff/{normalized.lower()}',
        'department_code': normalized,
        'department_name': normalized.replace('_', ' ').title(),
    })


class IsAdminUserRole(permissions.BasePermission):
    """
    Strictly grants access to Platform Administrators.
    Staff members, customers, and hotel owners are denied.
    """
    message = "Administrator privileges are required for this action."

    def has_permission(self, request, view):
        return is_platform_admin(request.user)


def is_authorized_payout_staff(user, required_permission='PROCESS_PAYOUT'):
    """
    Checks if user is a Platform Admin OR active GoOnStay Staff member
    in PAYOUT_AND_ESCROW department possessing the required payout permission.
    """
    if not (user and user.is_authenticated):
        return False
    if is_platform_admin(user):
        return True
    if getattr(user, 'role', '') != 'STAFF' or not hasattr(user, 'staff_profile'):
        return False
    profile = user.staff_profile
    try:
        profile.refresh_from_db(fields=['department', 'status', 'must_change_password'])
    except Exception:
        pass
    if not profile.is_active_account or profile.must_change_password:
        return False
    if not profile.department:
        return False
    from staff.models import Department
    user_dept = Department.normalize_code(profile.department.code)
    if user_dept != Department.CODE_PAYOUT_AND_ESCROW:
        return False
    if required_permission:
        return profile.has_perm(required_permission)
    return True


class IsAdminOrPayoutStaff(permissions.BasePermission):
    """
    Grants access to:
    1. Platform Administrators (full access).
    2. Active GoOnStay Staff members in PAYOUT_AND_ESCROW department
       possessing payout authorization.
    """
    message = "Administrator or authorized Payout & Escrow Staff privilege required."

    def __init__(self, required_permission='PROCESS_PAYOUT'):
        self.required_permission = required_permission

    def __call__(self):
        return self

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if is_platform_admin(user):
            return True
        req_perm = getattr(view, 'required_staff_permission', self.required_permission)
        return is_authorized_payout_staff(user, req_perm)


class IsStaffUser(permissions.BasePermission):
    """
    Grants access to active GoOnStay Staff members (and Platform Admins).
    Enforces immediate deactivation blocking and first-login password change.
    """
    message = "Access restricted to active GoOnStay Staff."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False

        if is_platform_admin(user):
            return True

        if not hasattr(user, 'staff_profile'):
            return False

        profile = user.staff_profile
        try:
            profile.refresh_from_db(fields=['department', 'status', 'must_change_password'])
        except Exception:
            pass
        if not profile.is_active_account:
            raise PermissionDenied({
                "code": "ACCOUNT_INACTIVE",
                "message": "Your staff account is inactive or suspended. Please contact Administrator."
            })

        # If must_change_password is true, only password change or logout is permitted
        if profile.must_change_password:
            view_name = getattr(view, '__class__', None).__name__
            if view_name not in ['StaffChangePasswordView', 'StaffLogoutView', 'StaffMeView']:
                raise PermissionDenied({
                    "code": "PASSWORD_CHANGE_REQUIRED",
                    "message": "You must change your temporary password before accessing staff workflows."
                })

        return True


class HasDepartmentPermission(permissions.BasePermission):
    """
    CRITICAL SECURITY ENFORCER:
    Validates:
    1. Authenticated user and active account.
    2. Platform Admin (full access) OR Staff with assigned department.
    3. The staff member's assigned department matches the view's allowed department.
    4. The staff member has the specific granular permission code.
    5. Rejects any attempt by one department to access another department's APIs.
    """
    def __init__(self, allowed_departments=None, required_permission=None):
        if allowed_departments is None:
            self.allowed_departments = []
        elif isinstance(allowed_departments, str):
            self.allowed_departments = [self._normalize(allowed_departments)]
        else:
            self.allowed_departments = [self._normalize(d) for d in allowed_departments]
        self.required_permission = required_permission

    def __call__(self):
        return self

    def _normalize(self, code_str):
        if not code_str:
            return ""
        c = str(code_str).strip().upper()
        if c in ['REFUND', 'REFUNDS', 'REFUNDS_AND_CLAIMS', 'CLAIMS']:
            return 'REFUNDS_AND_CLAIMS'
        if c in ['PAYOUT', 'PAYOUTS', 'PAYOUT_AND_ESCROW', 'ESCROW']:
            return 'PAYOUT_AND_ESCROW'
        if c in ['SUPPORT', 'CUSTOMER_SUPPORT', 'CS']:
            return 'CUSTOMER_SUPPORT'
        if c in ['HOTEL', 'HOTEL_VERIFICATION', 'VERIFICATION']:
            return 'HOTEL_VERIFICATION'
        if c in ['RESERVATION', 'RESERVATIONS', 'BOOKING', 'BOOKINGS']:
            return 'RESERVATION'
        return c

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False

        if is_platform_admin(user):
            return True

        if getattr(user, 'role', '') != 'STAFF' or not hasattr(user, 'staff_profile'):
            raise PermissionDenied({
                "code": "STAFF_ROLE_REQUIRED",
                "message": "Access restricted to GoOnStay Staff members."
            })

        profile = user.staff_profile
        try:
            profile.refresh_from_db(fields=['department', 'status', 'must_change_password'])
        except Exception:
            pass
        if not profile.is_active_account:
            raise PermissionDenied({
                "code": "ACCOUNT_INACTIVE",
                "message": "Your staff account is inactive or suspended. Please contact Administrator."
            })

        if profile.must_change_password:
            view_name = getattr(view, '__class__', None).__name__
            if view_name not in ['StaffChangePasswordView', 'StaffLogoutView', 'StaffMeView']:
                raise PermissionDenied({
                    "code": "PASSWORD_CHANGE_REQUIRED",
                    "message": "You must change your temporary password before accessing staff workflows."
                })

        if not profile.department:
            raise PermissionDenied({
                "code": "NO_DEPARTMENT_ASSIGNED",
                "message": "Your staff account has no department assigned. Please contact Administrator."
            })

        # 1. Strict Department Access Check
        user_dept = self._normalize(profile.department.code)
        if user_dept not in self.allowed_departments:
            dept_name = profile.department.name
            allowed_display = ", ".join(self.allowed_departments)
            raise PermissionDenied({
                "code": "DEPARTMENT_FORBIDDEN",
                "message": f"Access denied. Your assigned department '{dept_name}' does not permit access to {allowed_display} workflows."
            })

        # 2. Granular Action Permission Check
        if self.required_permission:
            if not profile.has_perm(self.required_permission):
                raise PermissionDenied({
                    "code": "PERMISSION_DENIED",
                    "message": f"Permission '{self.required_permission}' is required for this action."
                })

        return True


def check_department_permission(user, allowed_departments, required_permission=None):
    """
    Functional department permission check utility.
    """
    if is_platform_admin(user):
        return True
    if not (user and user.is_authenticated and hasattr(user, 'staff_profile')):
        return False
    profile = user.staff_profile
    if not profile.is_active_account or profile.must_change_password:
        return False

    perm_checker = HasDepartmentPermission(allowed_departments, required_permission)
    try:
        return perm_checker.has_permission(type('Req', (), {'user': user})(), None)
    except PermissionDenied:
        return False


def check_staff_permission(user, permission_code):
    """Functional permission check utility."""
    if is_platform_admin(user):
        return True
    if hasattr(user, 'staff_profile') and user.staff_profile.is_active_account:
        return user.staff_profile.has_perm(permission_code)
    return False


class HasStaffPermission:
    """Backward compatibility permission wrapper."""
    def __init__(self, required_permission):
        self.required_permission = required_permission

    def __call__(self):
        perm_code = self.required_permission

        class _DynamicPermission(permissions.BasePermission):
            message = f"Permission '{perm_code}' is required for this operation."

            def has_permission(self, request, view):
                user = request.user
                if is_platform_admin(user):
                    return True
                if not hasattr(user, 'staff_profile'):
                    return False
                return user.staff_profile.has_perm(perm_code)

        return _DynamicPermission()


class IsMainManagerRole(permissions.BasePermission):
    """
    Grants access to Main Managers and Platform Admins (Level 3 & 4).
    """
    message = "Main Manager or Administrator privileges are required for this action."

    def has_permission(self, request, view):
        from .services import get_user_hierarchy_level
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return get_user_hierarchy_level(user) >= 3


class IsDepartmentStaffManagerRole(permissions.BasePermission):
    """
    Grants access to Department Staff Managers, Main Managers, and Admins (Level 2+).
    """
    message = "Department Staff Manager, Main Manager, or Administrator privileges required."

    def has_permission(self, request, view):
        from .services import get_user_hierarchy_level
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return get_user_hierarchy_level(user) >= 2


class IsHierarchyManagerRole(permissions.BasePermission):
    """
    Grants access to any hierarchy manager:
    - Level 2: Department Staff Manager
    - Level 3: Main Manager
    - Level 4: Administrator
    """
    message = "Manager or Administrator privileges are required for this action."

    def has_permission(self, request, view):
        from .services import get_user_hierarchy_level
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return get_user_hierarchy_level(user) >= 2


class CanManageStaffObjectPermission(permissions.BasePermission):
    """
    Object-level permission enforcer:
    Prevents IDOR and cross-department tampering.
    """
    message = "You do not have authority to manage this staff member."

    def has_object_permission(self, request, view, obj):
        from .services import validate_can_manage_target_staff
        profile = obj if hasattr(obj, 'employee_id') else getattr(obj, 'staff_profile', None)
        if not profile:
            return False
        try:
            return validate_can_manage_target_staff(request.user, profile)
        except PermissionDenied:
            return False

