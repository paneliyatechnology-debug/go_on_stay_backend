"""
Serializers for GoOnStay 4-Level Admin & Staff Hierarchy.
Includes validation, sanitization, role enforcement, and department isolation.
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.db import transaction

from .models import (
    Department, StaffPermission, StaffProfile,
    DepartmentManagerAssignment, PermissionDelegationPolicy,
    HierarchyAuditLog, ManagerMFAProfile
)
from .utils import generate_temporary_password
from util.totp import generate_totp_secret

User = get_user_model()


class DepartmentManagementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ['id', 'code', 'name', 'description', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_code(self, value):
        return str(value).strip().upper()


class PermissionCatalogueSerializer(serializers.ModelSerializer):
    department_code = serializers.CharField(source='department.code', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)

    class Meta:
        model = StaffPermission
        fields = [
            'id', 'code', 'name', 'department', 'department_code',
            'department_name', 'action', 'category', 'is_sensitive', 'description'
        ]
        read_only_fields = ['id', 'department_code', 'department_name']


class PermissionDelegationPolicySerializer(serializers.ModelSerializer):
    allowed_permission_codes = serializers.SerializerMethodField()
    permission_ids = serializers.PrimaryKeyRelatedField(
        queryset=StaffPermission.objects.all(),
        many=True,
        write_only=True,
        required=False,
        source='allowed_permissions'
    )

    class Meta:
        model = PermissionDelegationPolicy
        fields = [
            'id', 'role', 'allow_sensitive_permissions', 'allowed_permissions',
            'allowed_permission_codes', 'permission_ids', 'updated_at'
        ]
        read_only_fields = ['id', 'updated_at', 'allowed_permissions']

    def get_allowed_permission_codes(self, obj):
        return list(obj.allowed_permissions.values_list('code', flat=True))


class DepartmentManagerAssignmentSerializer(serializers.ModelSerializer):
    department_code = serializers.CharField(source='department.code', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    manager_employee_id = serializers.CharField(source='manager.employee_id', read_only=True)
    manager_name = serializers.SerializerMethodField()

    class Meta:
        model = DepartmentManagerAssignment
        fields = [
            'id', 'department', 'department_code', 'department_name',
            'manager', 'manager_employee_id', 'manager_name',
            'is_active', 'assigned_at', 'revoked_at'
        ]
        read_only_fields = ['id', 'assigned_at', 'revoked_at']

    def get_manager_name(self, obj):
        u = obj.manager.user
        return u.get_full_name() or u.username


class MainManagerCreateSerializer(serializers.Serializer):
    """Admin-only serializer to create Level 3 Main Manager accounts."""
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150, required=False, default='')
    last_name = serializers.CharField(max_length=150, required=False, default='')
    phone_number = serializers.CharField(max_length=20, required=False, default='')
    designation = serializers.CharField(max_length=100, required=False, default='Main Manager')
    password = serializers.CharField(write_only=True, required=False, default='')

    def validate_username(self, value):
        val = str(value).strip().lower()
        if User.objects.filter(username__iexact=val).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return val

    def validate_email(self, value):
        val = str(value).strip().lower()
        if User.objects.filter(email__iexact=val).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return val

    def validate_phone_number(self, value):
        val = str(value).strip()
        if val and User.objects.filter(phone_number=val).exists():
            raise serializers.ValidationError("A user with this phone number already exists.")
        return val

    @transaction.atomic
    def create(self, validated_data):
        admin_user = self.context.get('request').user if self.context.get('request') else None
        password = validated_data.get('password') or generate_temporary_password()

        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            phone_number=validated_data.get('phone_number', ''),
            role=User.ROLE_MAIN_MANAGER,
            is_staff=True,
            is_active=True
        )
        user.set_password(password)
        user.save()

        # Employee ID & Login ID
        emp_id = f"MM{user.id:04d}"
        login_id = f"{validated_data['username']}.mm"

        profile = StaffProfile.objects.create(
            user=user,
            employee_id=emp_id,
            login_id=login_id,
            department=None,  # Main Manager oversees all departments
            is_manager=True,
            status=StaffProfile.STATUS_ACTIVE,
            must_change_password=True,
            designation=validated_data.get('designation', 'Main Manager'),
            phone_number=validated_data.get('phone_number', ''),
            created_by=admin_user
        )

        # Initialize MFA Profile (mandatory for Level 3)
        ManagerMFAProfile.objects.create(
            user=user,
            totp_secret=generate_totp_secret(),
            is_mfa_enabled=False,
            is_enrolled=False
        )

        user._temporary_password = password
        return profile


class DepartmentStaffManagerCreateSerializer(serializers.Serializer):
    """Admin or Main Manager serializer to create Level 2 Department Staff Manager accounts."""
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    department_id = serializers.IntegerField()
    first_name = serializers.CharField(max_length=150, required=False, default='')
    last_name = serializers.CharField(max_length=150, required=False, default='')
    phone_number = serializers.CharField(max_length=20, required=False, default='')
    designation = serializers.CharField(max_length=100, required=False, default='Department Staff Manager')
    password = serializers.CharField(write_only=True, required=False, default='')

    def validate_username(self, value):
        val = str(value).strip().lower()
        if User.objects.filter(username__iexact=val).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return val

    def validate_email(self, value):
        val = str(value).strip().lower()
        if User.objects.filter(email__iexact=val).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return val

    def validate_phone_number(self, value):
        val = str(value).strip()
        if val and User.objects.filter(phone_number=val).exists():
            raise serializers.ValidationError("A user with this phone number already exists.")
        return val

    def validate_department_id(self, value):
        dept = Department.objects.filter(id=value, is_active=True).first()
        if not dept:
            raise serializers.ValidationError("Active department with specified ID does not exist.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        actor_user = self.context.get('request').user if self.context.get('request') else None
        department = Department.objects.get(id=validated_data['department_id'])
        password = validated_data.get('password') or generate_temporary_password()

        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            phone_number=validated_data.get('phone_number', ''),
            role=User.ROLE_DEPARTMENT_STAFF_MANAGER,
            is_staff=True,
            is_active=True
        )
        user.set_password(password)
        user.save()

        emp_id = f"DSM{department.code[:3]}{user.id:04d}"
        login_id = f"{validated_data['username']}.{department.code.lower()[:8]}"

        profile = StaffProfile.objects.create(
            user=user,
            employee_id=emp_id,
            login_id=login_id,
            department=department,
            is_manager=True,
            status=StaffProfile.STATUS_ACTIVE,
            must_change_password=True,
            designation=validated_data.get('designation', f"{department.name} Manager"),
            phone_number=validated_data.get('phone_number', ''),
            created_by=actor_user
        )

        # Create active assignment
        DepartmentManagerAssignment.objects.create(
            department=department,
            manager=profile,
            assigned_by=actor_user,
            is_active=True
        )

        # Assign default department permissions to this manager
        dept_perms = department.permissions.all()
        if dept_perms.exists():
            profile.permissions.set(dept_perms)

        # Initialize MFA Profile (mandatory for Level 2)
        ManagerMFAProfile.objects.create(
            user=user,
            totp_secret=generate_totp_secret(),
            is_mfa_enabled=False,
            is_enrolled=False
        )

        user._temporary_password = password
        return profile


class HierarchyAuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = HierarchyAuditLog
        fields = [
            'id', 'actor_username', 'actor_role', 'target_username',
            'target_role', 'department_code', 'action_type',
            'previous_state', 'new_state', 'description',
            'ip_address', 'timestamp'
        ]
        read_only_fields = fields
