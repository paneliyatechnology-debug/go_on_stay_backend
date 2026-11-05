from rest_framework import permissions

class IsCustomer(permissions.BasePermission):
    """
    Allows access only to authenticated users with Customer / Guest role.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        role = str(getattr(request.user, 'role', '')).upper()
        return role in ['CUSTOMER', 'GUEST']


class IsHostOrOwner(permissions.BasePermission):
    """
    Allows access only to authenticated users with Hotel Owner / Host / Hotel Staff role.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        role = str(getattr(request.user, 'role', '')).upper()
        if role in ['HOTEL_OWNER', 'HOTEL_STAFF', 'HOST', 'OWNER']:
            return True
        if hasattr(request.user, 'hotels') and request.user.hotels.exists():
            return True
        return False


class IsPlatformAdmin(permissions.BasePermission):
    """
    Allows access only to staff members or Super/Platform Admins.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        role = str(getattr(request.user, 'role', '')).upper()
        return request.user.is_staff or role in ['ADMIN', 'SUPER_ADMIN']


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Object-level permission allowing only the owner of the object or a platform admin.
    """
    def has_object_permission(self, request, view, obj):
        if not (request.user and request.user.is_authenticated):
            return False
        role = str(getattr(request.user, 'role', '')).upper()
        if request.user.is_staff or role in ['ADMIN', 'SUPER_ADMIN']:
            return True
        owner = getattr(obj, 'owner', getattr(obj, 'host', getattr(obj, 'user', getattr(obj, 'customer', None))))
        return owner == request.user


class IsOwnerOrAdminOrReadOnly(permissions.BasePermission):
    """
    Allows read-only access for safe methods, and requires owner or admin for write operations.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        if not (request.user and request.user.is_authenticated):
            return False
        role = str(getattr(request.user, 'role', '')).upper()
        if request.user.is_staff or role in ['ADMIN', 'SUPER_ADMIN']:
            return True
        owner = getattr(obj, 'owner', getattr(obj, 'host', getattr(obj, 'user', getattr(obj, 'customer', None))))
        return owner == request.user

