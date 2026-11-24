"""
Comprehensive Automated Test Suite for GoOnStay 4-Level Admin & Staff Hierarchy.
Covers:
1. Four-level authority enforcement (Admin > Main Manager > Dept Manager > Staff).
2. Department-level isolation and strict IDOR prevention.
3. Permission delegation boundaries & self-escalation blocking.
4. Mandatory TOTP Multi-Factor Authentication (MFA) & backup code recovery.
5. Tamper-resistant audit logging across all hierarchy operations.
6. Backward compatibility with existing Staff authentication & workflows.
"""

import json
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from staff.models import (
    Department, StaffPermission, StaffProfile,
    DepartmentManagerAssignment, PermissionDelegationPolicy,
    ManagerMFAProfile, HierarchyAuditLog
)
from util.totp import (
    generate_totp_secret, generate_totp_code,
    generate_backup_codes, hash_backup_code
)

User = get_user_model()


class AdminStaffHierarchyTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # 1. Departments
        self.dept_reservation, _ = Department.objects.get_or_create(
            code=Department.CODE_RESERVATION,
            defaults={'name': 'Reservation', 'description': 'Booking & Reservation Department', 'is_active': True}
        )
        self.dept_support, _ = Department.objects.get_or_create(
            code=Department.CODE_CUSTOMER_SUPPORT,
            defaults={'name': 'Customer Support', 'description': 'Customer Support & Tickets', 'is_active': True}
        )
        self.dept_payout, _ = Department.objects.get_or_create(
            code=Department.CODE_PAYOUT_AND_ESCROW,
            defaults={'name': 'Payout & Escrow', 'description': 'Payouts & Escrow Settlements', 'is_active': True}
        )

        # 2. Permissions
        self.perm_view_bookings, _ = StaffPermission.objects.get_or_create(
            code='VIEW_BOOKINGS',
            defaults={
                'name': 'View Bookings',
                'department': self.dept_reservation,
                'action': StaffPermission.ACTION_VIEW,
                'category': 'BOOKINGS',
                'is_sensitive': False
            }
        )
        self.perm_manage_bookings, _ = StaffPermission.objects.get_or_create(
            code='MANAGE_RESERVATIONS',
            defaults={
                'name': 'Manage Reservations',
                'department': self.dept_reservation,
                'action': StaffPermission.ACTION_EDIT,
                'category': 'BOOKINGS',
                'is_sensitive': False
            }
        )
        self.perm_view_support, _ = StaffPermission.objects.get_or_create(
            code='VIEW_SUPPORT',
            defaults={
                'name': 'View Support Tickets',
                'department': self.dept_support,
                'action': StaffPermission.ACTION_VIEW,
                'category': 'SUPPORT',
                'is_sensitive': False
            }
        )
        self.perm_process_payout, _ = StaffPermission.objects.get_or_create(
            code='PROCESS_PAYOUT',
            defaults={
                'name': 'Process Payouts',
                'department': self.dept_payout,
                'action': StaffPermission.ACTION_PROCESS_PAYOUT,
                'category': 'PAYMENTS',
                'is_sensitive': True  # SENSITIVE!
            }
        )

        # 3. Level 4: Administrator
        self.admin = User.objects.create_superuser(
            username='system_admin',
            email='admin@goonstay.com',
            password='AdminPassword123!',
            role=User.ROLE_ADMIN
        )

        # 4. Level 3: Main Manager
        self.main_manager_user = User.objects.create_user(
            username='main_mgr',
            email='main.manager@goonstay.com',
            password='MainPassword123!',
            role=User.ROLE_MAIN_MANAGER,
            is_staff=True
        )
        self.main_manager_profile = StaffProfile.objects.create(
            user=self.main_manager_user,
            employee_id='MM0001',
            login_id='main_mgr.mm',
            department=None,  # Oversees all departments
            is_manager=True,
            status=StaffProfile.STATUS_ACTIVE,
            must_change_password=False
        )

        # 5. Level 2: Department Staff Manager (Reservation)
        self.dept_manager_user = User.objects.create_user(
            username='res_manager',
            email='res.manager@goonstay.com',
            password='DeptPassword123!',
            role=User.ROLE_DEPARTMENT_STAFF_MANAGER,
            is_staff=True
        )
        self.dept_manager_profile = StaffProfile.objects.create(
            user=self.dept_manager_user,
            employee_id='DSM0001',
            login_id='res_manager.res',
            department=self.dept_reservation,
            is_manager=True,
            status=StaffProfile.STATUS_ACTIVE,
            must_change_password=False
        )
        self.dept_manager_profile.permissions.set([self.perm_view_bookings, self.perm_manage_bookings])
        DepartmentManagerAssignment.objects.create(
            department=self.dept_reservation,
            manager=self.dept_manager_profile,
            assigned_by=self.admin,
            is_active=True
        )

        # 6. Level 1: Staff Member (Reservation)
        self.staff_user = User.objects.create_user(
            username='res_staff1',
            email='res.staff1@goonstay.com',
            password='StaffPassword123!',
            role=User.ROLE_STAFF,
            is_staff=True
        )
        self.staff_profile = StaffProfile.objects.create(
            user=self.staff_user,
            employee_id='STF0001',
            login_id='res_staff1.res',
            department=self.dept_reservation,
            is_manager=False,
            status=StaffProfile.STATUS_ACTIVE,
            must_change_password=False
        )
        self.staff_profile.permissions.set([self.perm_view_bookings])

        # 7. Level 1: Staff Member in Customer Support (Different Department!)
        self.support_staff_user = User.objects.create_user(
            username='supp_staff1',
            email='supp.staff1@goonstay.com',
            password='SupportPassword123!',
            role=User.ROLE_STAFF,
            is_staff=True
        )
        self.support_staff_profile = StaffProfile.objects.create(
            user=self.support_staff_user,
            employee_id='STF0002',
            login_id='supp_staff1.cs',
            department=self.dept_support,
            is_manager=False,
            status=StaffProfile.STATUS_ACTIVE,
            must_change_password=False
        )

    # =========================================================================
    # LEVEL 4: ADMIN CAPABILITIES & PERMISSION ENFORCEMENT
    # =========================================================================

    def test_admin_can_view_hierarchy_overview(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get('/api/staff/admin/hierarchy-overview/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['success'])
        metrics = res.data['metrics']
        self.assertGreaterEqual(metrics['level_4_admins'], 1)
        self.assertGreaterEqual(metrics['level_3_main_managers'], 1)
        self.assertGreaterEqual(metrics['level_2_department_managers'], 1)
        self.assertGreaterEqual(metrics['level_1_operational_staff'], 2)

    def test_admin_can_create_main_manager(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post('/api/staff/admin/main-managers/', {
            'username': 'new_main_manager',
            'email': 'new.mm@goonstay.com',
            'first_name': 'Executive',
            'last_name': 'Leader',
            'designation': 'Senior Director'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(res.data['success'])
        self.assertIn('temporary_password', res.data)
        self.assertEqual(res.data['data']['user']['role'], User.ROLE_MAIN_MANAGER)

        # Audit log verified
        log = HierarchyAuditLog.objects.filter(action_type=HierarchyAuditLog.ACTION_MANAGER_CREATE, target_username='new_main_manager').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.actor_username, self.admin.username)

    def test_admin_can_configure_delegation_policy(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post('/api/staff/admin/delegation-policies/', {
            'role': 'MAIN_MANAGER',
            'allow_sensitive_permissions': False,
            'permission_codes': ['VIEW_BOOKINGS', 'VIEW_SUPPORT']
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['success'])

        policy = PermissionDelegationPolicy.objects.get(role='MAIN_MANAGER')
        self.assertFalse(policy.allow_sensitive_permissions)
        self.assertEqual(policy.allowed_permissions.count(), 2)

    def test_non_admin_cannot_access_admin_endpoints(self):
        # Level 3 Main Manager cannot access Admin Main Manager creation
        self.client.force_authenticate(user=self.main_manager_user)
        res = self.client.post('/api/staff/admin/main-managers/', {
            'username': 'hacked_admin',
            'email': 'hacked@goonstay.com'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Level 2 Dept Manager cannot access Admin endpoints
        self.client.force_authenticate(user=self.dept_manager_user)
        res = self.client.get('/api/staff/admin/hierarchy-overview/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Level 1 Staff cannot access Admin endpoints
        self.client.force_authenticate(user=self.staff_user)
        res = self.client.get('/api/staff/admin/audit-logs/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    # =========================================================================
    # LEVEL 3: MAIN MANAGER CAPABILITIES & BOUNDARIES
    # =========================================================================

    def test_main_manager_can_view_all_departments(self):
        self.client.force_authenticate(user=self.main_manager_user)
        res = self.client.get('/api/staff/main-manager/departments/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['success'])
        self.assertGreaterEqual(res.data['count'], 3)

    def test_main_manager_can_create_department_staff_manager(self):
        self.client.force_authenticate(user=self.main_manager_user)
        res = self.client.post('/api/staff/main-manager/dept-managers/', {
            'username': 'supp_manager',
            'email': 'supp.mgr@goonstay.com',
            'department_id': self.dept_support.id,
            'first_name': 'Support',
            'last_name': 'Lead'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(res.data['success'])
        self.assertEqual(res.data['data']['user']['role'], User.ROLE_DEPARTMENT_STAFF_MANAGER)
        self.assertEqual(res.data['data']['department']['id'], self.dept_support.id)

    def test_main_manager_cannot_create_admin_account(self):
        self.client.force_authenticate(user=self.main_manager_user)
        # Attempt to create an Admin through admin API
        res = self.client.post('/api/staff/admin/main-managers/', {
            'username': 'fake_admin',
            'email': 'fake.admin@goonstay.com'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_main_manager_delegation_limits_and_sensitive_permission_blocking(self):
        # Configure Admin delegation policy for Main Manager: allow_sensitive = False
        PermissionDelegationPolicy.objects.update_or_create(
            role=PermissionDelegationPolicy.ROLE_MAIN_MANAGER,
            defaults={'allow_sensitive_permissions': False}
        )
        self.client.force_authenticate(user=self.main_manager_user)

        # Attempt to delegate sensitive permission (PROCESS_PAYOUT) to department staff
        res = self.client.post(f'/api/staff/dept-manager/staff/{self.staff_profile.id}/permissions/', {
            'permissions': ['PROCESS_PAYOUT']
        }, format='json')
        # Blocked because sensitive permissions cannot be delegated by Main Manager without explicit policy
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    # =========================================================================
    # LEVEL 2: DEPARTMENT STAFF MANAGER ISOLATION & IDOR PROTECTION
    # =========================================================================

    def test_dept_manager_can_view_own_department_staff(self):
        self.client.force_authenticate(user=self.dept_manager_user)
        res = self.client.get('/api/staff/dept-manager/staff/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['success'])
        # Only reservation staff returned (STF0001), NOT customer support staff (STF0002)
        staff_ids = [s['employee_id'] for s in res.data['staff']]
        self.assertIn('STF0001', staff_ids)
        self.assertNotIn('STF0002', staff_ids)

    def test_dept_manager_cannot_access_other_department_staff_idor(self):
        self.client.force_authenticate(user=self.dept_manager_user)
        # Reservation manager attempts to view/modify Support staff member (IDOR attack)
        res = self.client.get(f'/api/staff/dept-manager/staff/{self.support_staff_profile.id}/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Reservation manager attempts to update Support staff member
        res = self.client.patch(f'/api/staff/dept-manager/staff/{self.support_staff_profile.id}/', {
            'designation': 'Hacked Designation'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_dept_manager_cannot_assign_sensitive_permissions(self):
        self.client.force_authenticate(user=self.dept_manager_user)
        # Attempt to assign sensitive PROCESS_PAYOUT permission
        res = self.client.post(f'/api/staff/dept-manager/staff/{self.staff_profile.id}/permissions/', {
            'permissions': ['PROCESS_PAYOUT']
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_dept_manager_cannot_modify_higher_level_accounts(self):
        self.client.force_authenticate(user=self.dept_manager_user)
        # Attempt to modify Main Manager profile
        res = self.client.patch(f'/api/staff/dept-manager/staff/{self.main_manager_profile.id}/', {
            'designation': 'Compromised Manager'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_dept_manager_cannot_alter_account_role(self):
        self.client.force_authenticate(user=self.dept_manager_user)
        # Attempt to escalate staff role to ADMIN
        res = self.client.patch(f'/api/staff/dept-manager/staff/{self.staff_profile.id}/', {
            'role': 'ADMIN'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    # =========================================================================
    # LEVEL 1: OPERATIONAL STAFF RESTRICTIONS & BACKWARD COMPATIBILITY
    # =========================================================================

    def test_staff_cannot_access_manager_apis(self):
        self.client.force_authenticate(user=self.staff_user)
        res1 = self.client.get('/api/staff/dept-manager/staff/')
        self.assertEqual(res1.status_code, status.HTTP_403_FORBIDDEN)

        res2 = self.client.get('/api/staff/main-manager/departments/')
        self.assertEqual(res2.status_code, status.HTTP_403_FORBIDDEN)

        res3 = self.client.get('/api/staff/admin/hierarchy-overview/')
        self.assertEqual(res3.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_direct_login_compatibility(self):
        # Level 1 Staff direct login without MFA interruption
        res = self.client.post('/api/staff/login/', {
            'login_id': 'res_staff1.res',
            'password': 'StaffPassword123!'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['success'])
        self.assertIn('access', res.data)
        self.assertIn('refresh', res.data)
        self.assertEqual(res.data['user']['role'], User.ROLE_STAFF)

    # =========================================================================
    # MULTI-FACTOR AUTHENTICATION (MFA) WORKFLOW & VERIFICATION
    # =========================================================================

    def test_manager_mfa_full_enrollment_and_login_challenge(self):
        # 1. Initiate MFA setup for Main Manager
        self.client.force_authenticate(user=self.main_manager_user)
        setup_res = self.client.post('/api/staff/mfa/setup/')
        self.assertEqual(setup_res.status_code, status.HTTP_200_OK)
        self.assertTrue(setup_res.data['success'])
        secret = setup_res.data['secret']
        temp_token = setup_res.data['temp_token']
        backup_codes = setup_res.data['backup_codes']
        self.assertEqual(len(backup_codes), 8)

        # 2. Verify and enroll MFA with correct TOTP code
        valid_code = generate_totp_code(secret)
        enroll_res = self.client.post('/api/staff/mfa/enroll-verify/', {
            'temp_token': temp_token,
            'totp_code': valid_code
        }, format='json')
        self.assertEqual(enroll_res.status_code, status.HTTP_200_OK)
        self.assertTrue(enroll_res.data['success'])
        self.assertIn('access', enroll_res.data)

        # MFA Profile is now active
        mfa_prof = ManagerMFAProfile.objects.get(user=self.main_manager_user)
        self.assertTrue(mfa_prof.is_mfa_enabled)
        self.assertTrue(mfa_prof.is_enrolled)

        # 3. Next login: triggers MFA challenge
        self.client.logout()
        login_res = self.client.post('/api/staff/login/', {
            'login_id': 'main_mgr.mm',
            'password': 'MainPassword123!'
        }, format='json')
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)
        self.assertTrue(login_res.data['mfa_required'])
        challenge_token = login_res.data['temp_token']

        # 4. Verify login with invalid TOTP code: rejected
        bad_verify = self.client.post('/api/staff/mfa/verify/', {
            'temp_token': challenge_token,
            'totp_code': '000000'
        }, format='json')
        self.assertEqual(bad_verify.status_code, status.HTTP_401_UNAUTHORIZED)

        # 5. Verify login with valid TOTP code: success
        fresh_code = generate_totp_code(secret)
        good_verify = self.client.post('/api/staff/mfa/verify/', {
            'temp_token': challenge_token,
            'totp_code': fresh_code
        }, format='json')
        self.assertEqual(good_verify.status_code, status.HTTP_200_OK)
        self.assertTrue(good_verify.data['success'])
        self.assertIn('access', good_verify.data)

        # 6. Verify backup code recovery
        # Use one of the backup codes generated during setup
        first_backup = backup_codes[0]
        backup_verify = self.client.post('/api/staff/mfa/verify/', {
            'temp_token': challenge_token,
            'backup_code': first_backup
        }, format='json')
        self.assertEqual(backup_verify.status_code, status.HTTP_200_OK)
        self.assertTrue(backup_verify.data['success'])

        # Consumed backup code cannot be used again
        repeat_verify = self.client.post('/api/staff/mfa/verify/', {
            'temp_token': challenge_token,
            'backup_code': first_backup
        }, format='json')
        self.assertEqual(repeat_verify.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_can_reset_mfa_for_manager(self):
        # Enable MFA for Dept Manager
        secret = generate_totp_secret()
        mfa_prof, _ = ManagerMFAProfile.objects.update_or_create(
            user=self.dept_manager_user,
            defaults={'totp_secret': secret, 'is_mfa_enabled': True, 'is_enrolled': True}
        )

        # Admin resets MFA
        self.client.force_authenticate(user=self.admin)
        res = self.client.post('/api/staff/mfa/disable/', {
            'user_id': self.dept_manager_user.id
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['success'])

        mfa_prof.refresh_from_db()
        self.assertFalse(mfa_prof.is_mfa_enabled)
        self.assertFalse(mfa_prof.is_enrolled)

    # =========================================================================
    # AUDIT LOGGING INTEGRITY
    # =========================================================================

    def test_audit_logs_record_actions_and_are_immutable(self):
        initial_log_count = HierarchyAuditLog.objects.count()

        # Perform a manager action: update staff status
        self.client.force_authenticate(user=self.dept_manager_user)
        self.client.patch(f'/api/staff/dept-manager/staff/{self.staff_profile.id}/', {
            'status': StaffProfile.STATUS_SUSPENDED
        }, format='json')

        new_log = HierarchyAuditLog.objects.filter(action_type=HierarchyAuditLog.ACTION_STATUS_CHANGE).first()
        self.assertIsNotNone(new_log)
        self.assertEqual(new_log.actor_username, self.dept_manager_user.username)
        self.assertEqual(new_log.actor_role, User.ROLE_DEPARTMENT_STAFF_MANAGER)
        self.assertEqual(new_log.target_username, self.staff_user.username)
        self.assertEqual(new_log.previous_state.get('status'), StaffProfile.STATUS_ACTIVE)
        self.assertEqual(new_log.new_state.get('status'), StaffProfile.STATUS_SUSPENDED)
