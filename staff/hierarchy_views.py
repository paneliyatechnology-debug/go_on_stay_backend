"""
API Views for GoOnStay 4-Level Admin & Staff Hierarchy.
Enforces strict RBAC, IDOR protection, department isolation,
and permission delegation boundaries.
"""

from django.utils import timezone
from django.db import transaction
from django.db.models import Count, Q
from django.contrib.auth import get_user_model
from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import PermissionDenied, NotFound

from .models import (
    Department, StaffPermission, StaffProfile,
    DepartmentManagerAssignment, PermissionDelegationPolicy,
    HierarchyAuditLog, StaffActivityLog
)
from .hierarchy_serializers import (
    DepartmentManagementSerializer, PermissionCatalogueSerializer,
    PermissionDelegationPolicySerializer, DepartmentManagerAssignmentSerializer,
    MainManagerCreateSerializer, DepartmentStaffManagerCreateSerializer,
    HierarchyAuditLogSerializer
)
from .serializers import (
    StaffProfileListSerializer, StaffProfileDetailSerializer,
    StaffCreateSerializer, StaffUpdateSerializer
)
from .permissions import (
    IsAdminUserRole, IsMainManagerRole, IsHierarchyManagerRole,
    IsDepartmentStaffManagerRole, CanManageStaffObjectPermission,
    is_platform_admin
)
from .services import (
    get_user_hierarchy_level, can_actor_manage_role,
    get_actor_manageable_department_ids, validate_can_manage_target_staff,
    validate_permission_delegation, log_hierarchy_audit, revoke_user_sessions
)
from .utils import generate_temporary_password

User = get_user_model()


class HierarchyPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


# =============================================================================
# LEVEL 4: ADMIN APIS
# =============================================================================

class AdminMainManagerListCreateView(APIView):
    """
    GET, POST /api/staff/admin/main-managers/
    Admin-only management of Level 3 Main Managers.
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminUserRole]

    def get(self, request):
        qs = StaffProfile.objects.filter(user__role=User.ROLE_MAIN_MANAGER).select_related('user', 'department')
        serializer = StaffProfileDetailSerializer(qs, many=True)
        return Response({
            "success": True,
            "count": qs.count(),
            "main_managers": serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = MainManagerCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        profile = serializer.save()

        temp_password = getattr(profile.user, '_temporary_password', None)

        log_hierarchy_audit(
            actor_user=request.user,
            action_type=HierarchyAuditLog.ACTION_MANAGER_CREATE,
            target_user=profile.user,
            description=f"Created Main Manager {profile.user.username} ({profile.employee_id}).",
            request=request
        )

        return Response({
            "success": True,
            "message": "Main Manager account created successfully.",
            "data": StaffProfileDetailSerializer(profile).data,
            "temporary_password": temp_password,
            "login_id": profile.login_id,
            "employee_id": profile.employee_id
        }, status=status.HTTP_201_CREATED)


class AdminDepartmentListCreateView(generics.ListCreateAPIView):
    """
    GET, POST /api/staff/admin/departments/
    Admin creates and lists all system departments.
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminUserRole]
    queryset = Department.objects.all().order_by('name')
    serializer_class = DepartmentManagementSerializer

    def perform_create(self, serializer):
        dept = serializer.save()
        log_hierarchy_audit(
            actor_user=self.request.user,
            action_type=HierarchyAuditLog.ACTION_DEPARTMENT_CHANGE,
            department=dept,
            description=f"Created department {dept.name} ({dept.code}).",
            request=self.request
        )


class AdminDepartmentDetailView(generics.RetrieveUpdateAPIView):
    """
    GET, PATCH, PUT /api/staff/admin/departments/<id>/
    Admin updates or deactivates a department.
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminUserRole]
    queryset = Department.objects.all()
    serializer_class = DepartmentManagementSerializer

    def perform_update(self, serializer):
        old_inst = self.get_object()
        prev_state = {"is_active": old_inst.is_active, "name": old_inst.name}
        dept = serializer.save()
        new_state = {"is_active": dept.is_active, "name": dept.name}

        log_hierarchy_audit(
            actor_user=self.request.user,
            action_type=HierarchyAuditLog.ACTION_DEPARTMENT_CHANGE,
            department=dept,
            previous_state=prev_state,
            new_state=new_state,
            description=f"Updated department {dept.code}.",
            request=self.request
        )


class AdminDelegationPolicyView(APIView):
    """
    GET, POST /api/staff/admin/delegation-policies/
    Admin configures maximum delegated permissions for Main Managers & Dept Managers.
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminUserRole]

    def get(self, request):
        policies = PermissionDelegationPolicy.objects.all().prefetch_related('allowed_permissions')
        serializer = PermissionDelegationPolicySerializer(policies, many=True)
        return Response({
            "success": True,
            "policies": serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request):
        target_role = request.data.get('role')
        if target_role not in [PermissionDelegationPolicy.ROLE_MAIN_MANAGER, PermissionDelegationPolicy.ROLE_DEPARTMENT_STAFF_MANAGER]:
            return Response({
                "success": False,
                "error": "Valid role required (MAIN_MANAGER or DEPARTMENT_STAFF_MANAGER)."
            }, status=status.HTTP_400_BAD_REQUEST)

        policy, _ = PermissionDelegationPolicy.objects.get_or_create(role=target_role)

        allow_sensitive = request.data.get('allow_sensitive_permissions')
        if allow_sensitive is not None:
            policy.allow_sensitive_permissions = bool(allow_sensitive)

        perm_ids = request.data.get('permission_ids')
        if perm_ids is not None:
            perms = StaffPermission.objects.filter(id__in=perm_ids)
            policy.allowed_permissions.set(perms)

        perm_codes = request.data.get('permission_codes')
        if perm_codes is not None:
            perms = StaffPermission.objects.filter(code__in=perm_codes)
            policy.allowed_permissions.set(perms)

        policy.updated_by = request.user
        policy.save()

        log_hierarchy_audit(
            actor_user=request.user,
            action_type=HierarchyAuditLog.ACTION_DELEGATION_POLICY_UPDATE,
            description=f"Updated delegation policy for {target_role}.",
            request=request
        )

        return Response({
            "success": True,
            "message": f"Delegation policy for {target_role} updated successfully.",
            "data": PermissionDelegationPolicySerializer(policy).data
        }, status=status.HTTP_200_OK)


class AdminPermissionCatalogueView(generics.ListCreateAPIView):
    """
    GET, POST /api/staff/admin/permissions/
    Admin views and manages the system permission catalogue.
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminUserRole]
    queryset = StaffPermission.objects.all().select_related('department').order_by('code')
    serializer_class = PermissionCatalogueSerializer
    pagination_class = HierarchyPagination


class AdminAuditLogListView(generics.ListAPIView):
    """
    GET /api/staff/admin/audit-logs/
    Admin views complete tamper-resistant hierarchy audit logs.
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminUserRole]
    serializer_class = HierarchyAuditLogSerializer
    pagination_class = HierarchyPagination

    def get_queryset(self):
        qs = HierarchyAuditLog.objects.all()
        action_type = self.request.query_params.get('action_type')
        if action_type:
            qs = qs.filter(action_type=action_type)
        actor_role = self.request.query_params.get('actor_role')
        if actor_role:
            qs = qs.filter(actor_role=actor_role)
        dept_code = self.request.query_params.get('department')
        if dept_code:
            qs = qs.filter(department_code=dept_code)
        return qs


class AdminHierarchyOverviewView(APIView):
    """
    GET /api/staff/admin/hierarchy-overview/
    Returns high-level statistics across all 4 levels.
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminUserRole]

    def get(self, request):
        total_admins = User.objects.filter(Q(role__in=['ADMIN', 'SUPER_ADMIN']) | Q(is_superuser=True)).count()
        total_main_managers = User.objects.filter(role=User.ROLE_MAIN_MANAGER).count()
        total_dept_managers = User.objects.filter(role=User.ROLE_DEPARTMENT_STAFF_MANAGER).count()
        total_staff = User.objects.filter(role=User.ROLE_STAFF).count()
        total_depts = Department.objects.filter(is_active=True).count()

        dept_breakdown = []
        for d in Department.objects.all():
            m_count = DepartmentManagerAssignment.objects.filter(department=d, is_active=True).count()
            s_count = StaffProfile.objects.filter(department=d, user__role=User.ROLE_STAFF).count()
            dept_breakdown.append({
                "id": d.id,
                "code": d.code,
                "name": d.name,
                "is_active": d.is_active,
                "managers_count": m_count,
                "staff_count": s_count
            })

        return Response({
            "success": True,
            "metrics": {
                "level_4_admins": total_admins,
                "level_3_main_managers": total_main_managers,
                "level_2_department_managers": total_dept_managers,
                "level_1_operational_staff": total_staff,
                "active_departments": total_depts
            },
            "departments": dept_breakdown
        }, status=status.HTTP_200_OK)


# =============================================================================
# LEVEL 3: MAIN MANAGER APIS
# =============================================================================

class MainManagerDepartmentListView(APIView):
    """
    GET /api/staff/main-manager/departments/
    Main Manager views all departments, assigned managers, and staff statistics.
    """
    permission_classes = [permissions.IsAuthenticated, IsMainManagerRole]

    def get(self, request):
        departments = Department.objects.all().order_by('name')
        data = []
        for d in departments:
            active_assignments = DepartmentManagerAssignment.objects.filter(
                department=d, is_active=True
            ).select_related('manager__user')
            managers = [
                {
                    "assignment_id": a.id,
                    "manager_id": a.manager.id,
                    "employee_id": a.manager.employee_id,
                    "username": a.manager.user.username,
                    "name": a.manager.user.get_full_name() or a.manager.user.username,
                    "assigned_at": a.assigned_at
                }
                for a in active_assignments
            ]
            staff_count = StaffProfile.objects.filter(department=d, user__role=User.ROLE_STAFF, status=StaffProfile.STATUS_ACTIVE).count()
            data.append({
                "id": d.id,
                "code": d.code,
                "name": d.name,
                "description": d.description,
                "is_active": d.is_active,
                "managers": managers,
                "staff_count": staff_count
            })

        return Response({
            "success": True,
            "count": len(data),
            "departments": data
        }, status=status.HTTP_200_OK)


class MainManagerDeptManagerListCreateView(APIView):
    """
    GET, POST /api/staff/main-manager/dept-managers/
    Main Manager creates and views Level 2 Department Staff Managers.
    """
    permission_classes = [permissions.IsAuthenticated, IsMainManagerRole]

    def get(self, request):
        dept_id = request.query_params.get('department_id')
        qs = StaffProfile.objects.filter(user__role=User.ROLE_DEPARTMENT_STAFF_MANAGER).select_related('user', 'department')
        if dept_id:
            qs = qs.filter(department_id=dept_id)
        serializer = StaffProfileDetailSerializer(qs, many=True)
        return Response({
            "success": True,
            "count": qs.count(),
            "department_managers": serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = DepartmentStaffManagerCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        profile = serializer.save()

        temp_password = getattr(profile.user, '_temporary_password', None)

        log_hierarchy_audit(
            actor_user=request.user,
            action_type=HierarchyAuditLog.ACTION_MANAGER_CREATE,
            target_user=profile.user,
            department=profile.department,
            description=f"Created Department Staff Manager {profile.user.username} for {profile.department.code}.",
            request=request
        )

        return Response({
            "success": True,
            "message": "Department Staff Manager account created successfully.",
            "data": StaffProfileDetailSerializer(profile).data,
            "temporary_password": temp_password,
            "login_id": profile.login_id,
            "employee_id": profile.employee_id
        }, status=status.HTTP_201_CREATED)


class MainManagerAssignDeptManagerView(APIView):
    """
    POST /api/staff/main-manager/dept-managers/assign/
    Main Manager assigns or reassigns a manager to a department.
    """
    permission_classes = [permissions.IsAuthenticated, IsMainManagerRole]

    @transaction.atomic
    def post(self, request):
        manager_id = request.data.get('manager_id')
        dept_id = request.data.get('department_id')
        reassign_existing = request.data.get('reassign_existing', False)

        if not manager_id or not dept_id:
            return Response({
                "success": False,
                "error": "manager_id and department_id are required."
            }, status=status.HTTP_400_BAD_REQUEST)

        manager_profile = StaffProfile.objects.filter(id=manager_id).select_related('user').first()
        if not manager_profile or manager_profile.user.role != User.ROLE_DEPARTMENT_STAFF_MANAGER:
            return Response({
                "success": False,
                "error": "Target user is not a valid Department Staff Manager."
            }, status=status.HTTP_400_BAD_REQUEST)

        department = Department.objects.filter(id=dept_id, is_active=True).first()
        if not department:
            return Response({
                "success": False,
                "error": "Target department not found or is inactive."
            }, status=status.HTTP_404_NOT_FOUND)

        # Deactivate existing active assignment if reassigning
        if reassign_existing:
            DepartmentManagerAssignment.objects.filter(department=department, is_active=True).update(
                is_active=False,
                revoked_at=timezone.now(),
                revoked_by=request.user
            )

        assignment, created = DepartmentManagerAssignment.objects.get_or_create(
            department=department,
            manager=manager_profile,
            defaults={'assigned_by': request.user, 'is_active': True}
        )
        if not created and not assignment.is_active:
            assignment.is_active = True
            assignment.revoked_at = None
            assignment.revoked_by = None
            assignment.assigned_by = request.user
            assignment.save()

        # Update primary department on profile as well
        manager_profile.department = department
        manager_profile.save()

        log_hierarchy_audit(
            actor_user=request.user,
            action_type=HierarchyAuditLog.ACTION_DEPARTMENT_CHANGE,
            target_user=manager_profile.user,
            department=department,
            description=f"Assigned manager {manager_profile.employee_id} to department {department.code}.",
            request=request
        )

        return Response({
            "success": True,
            "message": f"Manager {manager_profile.employee_id} assigned to {department.name}.",
            "assignment": DepartmentManagerAssignmentSerializer(assignment).data
        }, status=status.HTTP_200_OK)


class MainManagerAllStaffListView(generics.ListAPIView):
    """
    GET /api/staff/main-manager/staff/
    Main Manager views all staff across all departments.
    """
    permission_classes = [permissions.IsAuthenticated, IsMainManagerRole]
    serializer_class = StaffProfileListSerializer
    pagination_class = HierarchyPagination

    def get_queryset(self):
        qs = StaffProfile.objects.filter(user__role=User.ROLE_STAFF).select_related('user', 'department')
        dept_id = self.request.query_params.get('department_id')
        if dept_id:
            qs = qs.filter(department_id=dept_id)
        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param.upper())
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(employee_id__icontains=search) |
                Q(login_id__icontains=search) |
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(user__email__icontains=search)
            )
        return qs


# =============================================================================
# LEVEL 2: DEPARTMENT-WISE STAFF MANAGER APIS
# =============================================================================

class DeptManagerStaffListCreateView(APIView):
    """
    GET, POST /api/staff/dept-manager/staff/
    Department Staff Manager manages Level 1 Staff in their assigned department ONLY.
    Strictly prevents cross-department staff visibility and creation.
    """
    permission_classes = [permissions.IsAuthenticated, IsDepartmentStaffManagerRole]

    def get(self, request):
        allowed_depts = get_actor_manageable_department_ids(request.user)
        if not allowed_depts:
            return Response({
                "success": False,
                "code": "NO_DEPARTMENT_ASSIGNED",
                "error": "You are not assigned to any active department."
            }, status=status.HTTP_403_FORBIDDEN)

        qs = StaffProfile.objects.filter(
            department_id__in=allowed_depts,
            user__role=User.ROLE_STAFF
        ).select_related('user', 'department').prefetch_related('permissions')

        serializer = StaffProfileListSerializer(qs, many=True)
        return Response({
            "success": True,
            "count": qs.count(),
            "staff": serializer.data
        }, status=status.HTTP_200_OK)

    @transaction.atomic
    def post(self, request):
        allowed_depts = get_actor_manageable_department_ids(request.user)
        if not allowed_depts:
            return Response({
                "success": False,
                "error": "You do not have an active department assignment."
            }, status=status.HTTP_403_FORBIDDEN)

        # Department must match actor's assigned department
        req_dept_id = request.data.get('department_id')
        if not req_dept_id or int(req_dept_id) not in allowed_depts:
            # Default to manager's primary department if only one assigned
            if len(allowed_depts) == 1:
                req_dept_id = list(allowed_depts)[0]
            else:
                return Response({
                    "success": False,
                    "error": "You can only create staff within your assigned department."
                }, status=status.HTTP_403_FORBIDDEN)

        department = Department.objects.get(id=req_dept_id)
        username = request.data.get('username')
        email = request.data.get('email')

        if not username or not email:
            return Response({
                "success": False,
                "error": "username and email are required."
            }, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(username__iexact=username).exists():
            return Response({
                "success": False,
                "error": "A user with this username already exists."
            }, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(email__iexact=email).exists():
            return Response({
                "success": False,
                "error": "A user with this email already exists."
            }, status=status.HTTP_400_BAD_REQUEST)

        password = request.data.get('password') or generate_temporary_password()

        user = User.objects.create_user(
            username=username,
            email=email,
            first_name=request.data.get('first_name', ''),
            last_name=request.data.get('last_name', ''),
            phone_number=request.data.get('phone_number', ''),
            role=User.ROLE_STAFF,
            is_staff=True,
            is_active=True
        )
        user.set_password(password)
        user.save()

        emp_id = f"STF{department.code[:3]}{user.id:04d}"
        login_id = f"{username}.{department.code.lower()[:8]}"

        profile = StaffProfile.objects.create(
            user=user,
            employee_id=emp_id,
            login_id=login_id,
            department=department,
            is_manager=False,
            status=StaffProfile.STATUS_ACTIVE,
            must_change_password=True,
            designation=request.data.get('designation', f"{department.name} Staff"),
            phone_number=request.data.get('phone_number', ''),
            created_by=request.user
        )

        # Default permissions for department
        dept_perms = department.permissions.filter(is_sensitive=False)
        profile.permissions.set(dept_perms)

        log_hierarchy_audit(
            actor_user=request.user,
            action_type=HierarchyAuditLog.ACTION_STAFF_CREATE,
            target_user=user,
            department=department,
            description=f"Created staff member {emp_id} in {department.code}.",
            request=request
        )

        return Response({
            "success": True,
            "message": "Department staff member created successfully.",
            "data": StaffProfileDetailSerializer(profile).data,
            "temporary_password": password,
            "login_id": login_id,
            "employee_id": emp_id
        }, status=status.HTTP_201_CREATED)


class DeptManagerStaffDetailUpdateView(APIView):
    """
    GET, PATCH /api/staff/dept-manager/staff/<id>/
    Department Staff Manager updates staff in their assigned department.
    Prevents IDOR and self-escalation.
    """
    permission_classes = [permissions.IsAuthenticated, IsDepartmentStaffManagerRole]

    def get_target_profile(self, pk, request_user):
        profile = StaffProfile.objects.filter(id=pk).select_related('user', 'department').first()
        if not profile:
            raise NotFound("Staff profile not found.")
        validate_can_manage_target_staff(request_user, profile)
        return profile

    def get(self, request, pk):
        profile = self.get_target_profile(pk, request.user)
        return Response({
            "success": True,
            "data": StaffProfileDetailSerializer(profile).data
        }, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        profile = self.get_target_profile(pk, request.user)
        user = profile.user

        # Prevent role tampering: Dept Manager cannot change role
        if 'role' in request.data:
            raise PermissionDenied("Department Staff Managers cannot alter account roles.")

        # Status update
        new_status = request.data.get('status')
        if new_status:
            new_status_str = str(new_status).upper()
            if new_status_str in [StaffProfile.STATUS_ACTIVE, StaffProfile.STATUS_INACTIVE, StaffProfile.STATUS_SUSPENDED]:
                prev_status = profile.status
                profile.status = new_status_str
                profile.save()
                if new_status_str != StaffProfile.STATUS_ACTIVE:
                    revoke_user_sessions(user)
                log_hierarchy_audit(
                    actor_user=request.user,
                    action_type=HierarchyAuditLog.ACTION_STATUS_CHANGE,
                    target_user=user,
                    previous_state={"status": prev_status},
                    new_state={"status": new_status_str},
                    description=f"Updated status of {profile.employee_id} to {new_status_str}.",
                    request=request
                )

        # Personal details update
        first_name = request.data.get('first_name')
        if first_name is not None:
            user.first_name = first_name
        last_name = request.data.get('last_name')
        if last_name is not None:
            user.last_name = last_name
        user.save()

        designation = request.data.get('designation')
        if designation is not None:
            profile.designation = designation
        phone_number = request.data.get('phone_number')
        if phone_number is not None:
            profile.phone_number = phone_number
        profile.save()

        return Response({
            "success": True,
            "message": "Staff details updated successfully.",
            "data": StaffProfileDetailSerializer(profile).data
        }, status=status.HTTP_200_OK)


class DeptManagerStaffPermissionsView(APIView):
    """
    GET, POST /api/staff/dept-manager/staff/<id>/permissions/
    Assign or revoke permissions for a staff member.
    Enforces strict delegation limits and blocks sensitive permissions.
    """
    permission_classes = [permissions.IsAuthenticated, IsDepartmentStaffManagerRole]

    def get(self, request, pk):
        profile = StaffProfile.objects.filter(id=pk).select_related('user', 'department').first()
        if not profile:
            raise NotFound("Staff profile not found.")
        validate_can_manage_target_staff(request.user, profile)

        perms = profile.permissions.all().select_related('department')
        return Response({
            "success": True,
            "employee_id": profile.employee_id,
            "permissions": PermissionCatalogueSerializer(perms, many=True).data
        }, status=status.HTTP_200_OK)

    @transaction.atomic
    def post(self, request, pk):
        profile = StaffProfile.objects.filter(id=pk).select_related('user', 'department').first()
        if not profile:
            raise NotFound("Staff profile not found.")
        validate_can_manage_target_staff(request.user, profile)

        perm_codes = request.data.get('permissions') or request.data.get('permission_codes') or []
        perm_objs = StaffPermission.objects.filter(code__in=perm_codes)

        # Enforce delegation boundaries
        validate_permission_delegation(
            actor_user=request.user,
            target_role=profile.user.role,
            target_department=profile.department,
            requested_permissions=perm_objs
        )

        prev_perms = list(profile.permissions.values_list('code', flat=True))
        profile.permissions.set(perm_objs)
        new_perms = list(profile.permissions.values_list('code', flat=True))

        log_hierarchy_audit(
            actor_user=request.user,
            action_type=HierarchyAuditLog.ACTION_PERMISSION_ASSIGN,
            target_user=profile.user,
            department=profile.department,
            previous_state={"permissions": prev_perms},
            new_state={"permissions": new_perms},
            description=f"Updated permissions for staff member {profile.employee_id}.",
            request=request
        )

        return Response({
            "success": True,
            "message": f"Permissions updated for {profile.employee_id}.",
            "permissions": new_perms
        }, status=status.HTTP_200_OK)
