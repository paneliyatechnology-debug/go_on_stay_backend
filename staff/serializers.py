import re
from rest_framework import serializers
from django.contrib.auth import get_user_model, authenticate
from django.db import transaction
from django.utils import timezone
from .models import (
    Department, StaffPermission, StaffProfile, StaffActivityLog,
    StaffNotification, StaffPasswordResetToken, StaffTicketNote, StaffAssignment
)
from .utils import (
    generate_next_employee_id, generate_login_id,
    generate_temporary_password, hash_token
)
from util.validators import clean_indian_phone

User = get_user_model()


class DepartmentSerializer(serializers.ModelSerializer):
    employee_count = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = ('id', 'code', 'name', 'description', 'is_active', 'employee_count', 'created_at', 'updated_at')

    def get_employee_count(self, obj):
        return obj.staff_members.count()


class StaffPermissionSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.name', read_only=True)
    department_code = serializers.CharField(source='department.code', read_only=True)

    class Meta:
        model = StaffPermission
        fields = ('id', 'code', 'name', 'department', 'department_name', 'department_code', 'action', 'description')


class StaffProfileListSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source='user.id', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    full_name = serializers.SerializerMethodField()
    email = serializers.EmailField(source='user.email', read_only=True)
    department_id = serializers.IntegerField(source='department.id', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    department_code = serializers.CharField(source='department.code', read_only=True)
    permissions_count = serializers.SerializerMethodField()

    class Meta:
        model = StaffProfile
        fields = (
            'id', 'user_id', 'employee_id', 'login_id', 'username',
            'first_name', 'last_name', 'full_name', 'email', 'phone_number',
            'department_id', 'department_name', 'department_code', 'designation',
            'status', 'must_change_password', 'permissions_count', 'created_at', 'updated_at'
        )

    def get_full_name(self, obj):
        name = f"{obj.user.first_name} {obj.user.last_name}".strip()
        return name if name else obj.login_id

    def get_permissions_count(self, obj):
        return obj.permissions.count()


class StaffProfileDetailSerializer(StaffProfileListSerializer):
    permissions = StaffPermissionSerializer(many=True, read_only=True)
    assigned_by_name = serializers.SerializerMethodField()

    class Meta(StaffProfileListSerializer.Meta):
        fields = StaffProfileListSerializer.Meta.fields + ('permissions', 'assigned_by_name')

    def get_assigned_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return "Admin"


class StaffCreateSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150, required=True)
    last_name = serializers.CharField(max_length=150, required=True)
    email = serializers.EmailField(required=True)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True, default='')
    department = serializers.CharField(required=False, allow_blank=True, default='')
    department_id = serializers.CharField(required=False, allow_blank=True, default='')
    designation = serializers.CharField(max_length=100, required=False, allow_blank=True, default='Associate')
    permissions = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )
    permission_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list
    )

    def validate_email(self, value):
        val = value.strip().lower()
        if User.objects.filter(email__iexact=val).exists():
            raise serializers.ValidationError("A user account with this email address already exists.")
        return val

    def validate(self, attrs):
        dept_val = attrs.get('department') or attrs.get('department_id')
        if not dept_val:
            raise serializers.ValidationError({"department": "Department is required."})

        val = str(dept_val).strip()
        dept = None
        if val.isdigit():
            dept = Department.objects.filter(id=int(val)).first()
        if not dept:
            dept = Department.objects.filter(code__iexact=val).first()
        if not dept:
            dept = Department.objects.filter(name__iexact=val).first()
        if not dept:
            raise serializers.ValidationError({"department": f"Invalid department identifier: '{val}'."})
        attrs['department_obj'] = dept

        perm_codes = [str(p).strip().upper() for p in attrs.get('permissions', [])]
        perm_ids = attrs.get('permission_ids', [])
        if perm_ids:
            found = list(StaffPermission.objects.filter(id__in=perm_ids).values_list('code', flat=True))
            perm_codes.extend(found)
        attrs['normalized_permissions'] = list(set(perm_codes))

        phone = attrs.get('phone_number', '')
        if phone:
            attrs['phone_number'] = clean_indian_phone(phone)

        return attrs

    def create(self, validated_data):
        first_name = validated_data['first_name'].strip()
        last_name = validated_data['last_name'].strip()
        email = validated_data['email'].strip().lower()
        phone_number = validated_data.get('phone_number', '')
        department = validated_data['department_obj']
        designation = validated_data.get('designation', 'Associate').strip()
        permission_codes = validated_data.get('normalized_permissions', [])
        admin_user = self.context.get('request').user if self.context.get('request') else None

        with transaction.atomic():
            employee_id = generate_next_employee_id()
            login_id = generate_login_id(first_name, department.code)
            temp_password = generate_temporary_password(12)

            # Create User
            user = User.objects.create_user(
                username=login_id,
                email=email,
                password=temp_password,
                first_name=first_name,
                last_name=last_name,
                phone_number=phone_number,
                role=getattr(User, 'ROLE_STAFF', 'STAFF'),
                is_staff=True,
                is_active=True
            )

            # Create StaffProfile
            profile = StaffProfile.objects.create(
                user=user,
                employee_id=employee_id,
                login_id=login_id,
                department=department,
                designation=designation,
                phone_number=phone_number,
                status=StaffProfile.STATUS_ACTIVE,
                must_change_password=True,
                created_by=admin_user
            )

            # Assign permissions
            if permission_codes:
                perms = StaffPermission.objects.filter(code__in=[p.strip().upper() for p in permission_codes])
                profile.permissions.set(perms)
            else:
                # Assign default department permissions if none provided
                dept_perms = StaffPermission.objects.filter(department=department)
                profile.permissions.set(dept_perms)

            # Store temporary password in in-memory instance attribute ONLY for one-time display
            profile._temporary_password = temp_password
            return profile


class StaffUpdateSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(source='user.first_name', required=False)
    last_name = serializers.CharField(source='user.last_name', required=False)
    email = serializers.EmailField(source='user.email', required=False)
    department_id = serializers.CharField(required=False, allow_blank=True)
    department = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = StaffProfile
        fields = ('first_name', 'last_name', 'email', 'phone_number', 'designation', 'department_id', 'department')

    def validate_email(self, value):
        val = value.strip().lower()
        instance = self.instance
        if User.objects.filter(email__iexact=val).exclude(id=instance.user.id).exists():
            raise serializers.ValidationError("Another user already exists with this email address.")
        return val

    def validate_phone_number(self, value):
        if not value:
            return ""
        return clean_indian_phone(value)

    def update(self, instance, validated_data):
        user_data = validated_data.pop('user', {})
        dept_val = validated_data.pop('department', None) or validated_data.pop('department_id', None)

        with transaction.atomic():
            if user_data:
                user = instance.user
                if 'first_name' in user_data:
                    user.first_name = user_data['first_name']
                if 'last_name' in user_data:
                    user.last_name = user_data['last_name']
                if 'email' in user_data:
                    user.email = user_data['email']
                user.save()

            if dept_val:
                val = str(dept_val).strip()
                dept = None
                if val.isdigit():
                    dept = Department.objects.filter(id=int(val)).first()
                if not dept:
                    norm = Department.normalize_code(val)
                    dept = Department.objects.filter(code__iexact=norm).first()
                if not dept:
                    dept = Department.objects.filter(name__iexact=val).first()
                if not dept:
                    raise serializers.ValidationError({"department": f"Invalid department identifier: '{val}'."})
                instance.department = dept

            if 'phone_number' in validated_data:
                instance.phone_number = validated_data['phone_number']
                instance.user.phone_number = validated_data['phone_number']
                instance.user.save(update_fields=['phone_number'])

            if 'designation' in validated_data:
                instance.designation = validated_data['designation']

            instance.save()
            return instance


class StaffStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=StaffProfile.STATUS_CHOICES)
    reason = serializers.CharField(required=False, allow_blank=True, default='')


class StaffPermissionsUpdateSerializer(serializers.Serializer):
    permissions = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )
    permission_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list
    )

    def validate(self, attrs):
        codes = [str(p).strip().upper() for p in attrs.get('permissions', [])]
        ids = attrs.get('permission_ids', [])
        if ids:
            found_by_ids = list(StaffPermission.objects.filter(id__in=ids).values_list('code', flat=True))
            codes.extend(found_by_ids)
        codes = list(set(codes))

        existing_codes = set(StaffPermission.objects.values_list('code', flat=True))
        invalid = [p for p in codes if p not in existing_codes]
        if invalid:
            raise serializers.ValidationError(f"Invalid permission code(s): {', '.join(invalid)}")
        attrs['permissions'] = codes
        return attrs


class StaffLoginSerializer(serializers.Serializer):
    login_id = serializers.CharField(required=False, allow_blank=True, default='')
    identifier = serializers.CharField(required=False, allow_blank=True, default='')
    email = serializers.CharField(required=False, allow_blank=True, default='')
    username = serializers.CharField(required=False, allow_blank=True, default='')
    password = serializers.CharField(required=True, write_only=True)

    def validate(self, attrs):
        ident = attrs.get('login_id') or attrs.get('identifier') or attrs.get('email') or attrs.get('username')
        if not ident:
            raise serializers.ValidationError({"identifier": "Login ID, email, or username is required."})
        attrs['login_id'] = str(ident).strip()
        return attrs


class StaffChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True)
    confirm_password = serializers.CharField(required=True, write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "New passwords do not match."})
        if len(attrs['new_password']) < 8:
            raise serializers.ValidationError({"new_password": "Password must be at least 8 characters long."})
        if attrs['new_password'] == attrs['old_password']:
            raise serializers.ValidationError({"new_password": "New password cannot be identical to old password."})
        return attrs


class StaffForgotPasswordSerializer(serializers.Serializer):
    identifier = serializers.CharField(required=True)


class StaffResetPasswordSerializer(serializers.Serializer):
    token = serializers.CharField(required=True)
    employee_id = serializers.CharField(required=False, allow_blank=True, default='')
    new_password = serializers.CharField(required=True, write_only=True)
    confirm_password = serializers.CharField(required=True, write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        if len(attrs['new_password']) < 8:
            raise serializers.ValidationError({"new_password": "Password must be at least 8 characters long."})
        return attrs


class StaffActivityLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffActivityLog
        fields = (
            'id', 'employee_id', 'actor_username', 'action',
            'target_entity_type', 'target_entity_id', 'description',
            'metadata', 'ip_address', 'timestamp'
        )


class StaffNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffNotification
        fields = (
            'id', 'title', 'message', 'notification_type',
            'is_read', 'read_at', 'metadata', 'created_at'
        )


class StaffTicketNoteSerializer(serializers.ModelSerializer):
    staff_name = serializers.SerializerMethodField()
    employee_id = serializers.CharField(source='staff.employee_id', read_only=True)

    class Meta:
        model = StaffTicketNote
        fields = ('id', 'ticket', 'staff', 'staff_name', 'employee_id', 'note', 'is_internal_only', 'created_at')
        read_only_fields = ('id', 'staff', 'created_at')

    def get_staff_name(self, obj):
        if obj.staff:
            return obj.staff.user.get_full_name() or obj.staff.login_id
        return "Support Staff"
