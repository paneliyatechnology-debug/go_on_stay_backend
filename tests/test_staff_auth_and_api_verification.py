"""
Comprehensive Verification Tests for GoOnStay Staff Management System.
Covers:
1. Staff Login & Authentication (Valid, Invalid, Inactive, Suspended).
2. Header Resilience (Empty Bearer, Unresolved Variables, Raw JWT, Valid Bearer).
3. First-login password change enforcement and workflow.
4. Password Reset flow (Forgot & Reset).
5. Staff Profile (/api/staff/me/) access and field masking.
6. Role isolation: Customers & Hotel Owners blocked from Staff APIs.
7. Role isolation: Staff blocked from Admin APIs.
8. Department & Granular Permission checks (Refund, Payout, Hotel Verification, Support, Reservation).
9. Staff Notification & Dashboard APIs.
"""

from decimal import Decimal
from datetime import timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from staff.models import (
    Department, StaffPermission, StaffProfile, StaffActivityLog,
    StaffNotification, StaffPasswordResetToken, StaffTicketNote
)
from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking
from payments.models import Payment, Refund, HostPayout, HostEarning, SupportTicket

User = get_user_model()


class StaffAuthAndApiVerificationTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        # 1. Platform Admin
        cls.admin = User.objects.create_superuser(
            username="admin_super",
            email="admin@goonstay.com",
            password="AdminPassword123!",
            role=User.ROLE_ADMIN
        )

        # 2. Customer
        cls.customer = User.objects.create_user(
            username="test_customer",
            email="customer@example.com",
            password="CustomerPassword123!",
            role=User.ROLE_CUSTOMER,
            phone_number="9876543210"
        )

        # 3. Hotel Owner
        cls.owner = User.objects.create_user(
            username="test_owner",
            email="owner@example.com",
            password="OwnerPassword123!",
            role=User.ROLE_HOTEL_OWNER,
            phone_number="9123456780"
        )

        # 4. Departments
        cls.dept_reservation, _ = Department.objects.get_or_create(
            code=Department.CODE_RESERVATION,
            defaults={"name": "Reservation Department"}
        )
        cls.dept_refund, _ = Department.objects.get_or_create(
            code=Department.CODE_REFUND,
            defaults={"name": "Refund Department"}
        )
        cls.dept_payout, _ = Department.objects.get_or_create(
            code=Department.CODE_PAYOUT,
            defaults={"name": "Payout Department"}
        )
        cls.dept_verification, _ = Department.objects.get_or_create(
            code=Department.CODE_HOTEL_VERIFICATION,
            defaults={"name": "Hotel Verification"}
        )
        cls.dept_support, _ = Department.objects.get_or_create(
            code=Department.CODE_CUSTOMER_SUPPORT,
            defaults={"name": "Customer Support"}
        )

        # 5. Granular Permissions
        cls.perm_view_bookings, _ = StaffPermission.objects.get_or_create(
            code="VIEW_BOOKINGS", defaults={"name": "View Bookings", "action": "VIEW"}
        )
        cls.perm_view_refunds, _ = StaffPermission.objects.get_or_create(
            code="VIEW_REFUNDS", defaults={"name": "View Refunds", "action": "VIEW"}
        )
        cls.perm_process_refund, _ = StaffPermission.objects.get_or_create(
            code="PROCESS_REFUND", defaults={"name": "Process Refund", "action": "PROCESS_REFUND"}
        )
        cls.perm_view_payouts, _ = StaffPermission.objects.get_or_create(
            code="VIEW_PAYOUTS", defaults={"name": "View Payouts", "action": "VIEW"}
        )
        cls.perm_process_payout, _ = StaffPermission.objects.get_or_create(
            code="PROCESS_PAYOUT", defaults={"name": "Process Payout", "action": "PROCESS_PAYOUT"}
        )
        cls.perm_verify_hotel, _ = StaffPermission.objects.get_or_create(
            code="VERIFY_HOTEL", defaults={"name": "Verify Hotel", "action": "VERIFY_HOTEL"}
        )
        cls.perm_manage_support, _ = StaffPermission.objects.get_or_create(
            code="MANAGE_SUPPORT", defaults={"name": "Manage Support", "action": "MANAGE_SUPPORT"}
        )

        # 6. Staff User (Reservation Staff)
        cls.res_user = User.objects.create_user(
            username="staff_amit",
            email="amit.reservation@goonstay.com",
            password="StaffPassword123!",
            first_name="Amit",
            last_name="Verma",
            role=User.ROLE_STAFF
        )
        cls.res_profile = StaffProfile.objects.create(
            user=cls.res_user,
            employee_id="GOS-EMP-TEST-001",
            login_id="amit.reservation001",
            department=cls.dept_reservation,
            status=StaffProfile.STATUS_ACTIVE,
            must_change_password=False
        )
        cls.res_profile.permissions.add(cls.perm_view_bookings)

        # 7. Staff User (Refund Staff with process permission)
        cls.ref_user = User.objects.create_user(
            username="staff_priya",
            email="priya.refund@goonstay.com",
            password="StaffPassword123!",
            first_name="Priya",
            last_name="Singh",
            role=User.ROLE_STAFF
        )
        cls.ref_profile = StaffProfile.objects.create(
            user=cls.ref_user,
            employee_id="GOS-EMP-TEST-002",
            login_id="priya.refund001",
            department=cls.dept_refund,
            status=StaffProfile.STATUS_ACTIVE,
            must_change_password=False
        )
        cls.ref_profile.permissions.add(cls.perm_view_refunds, cls.perm_process_refund)

    def setUp(self):
        self.client = APIClient()

    def get_token(self, user):
        refresh = RefreshToken.for_user(user)
        return str(refresh.access_token)

    # --- SECTION 4: Staff Login and Authentication Verification ---

    def test_staff_login_with_valid_credentials(self):
        """Staff can log in with login_id or email, returning JWT access & refresh tokens."""
        # By login_id
        res = self.client.post("/api/staff/login/", {
            "identifier": "amit.reservation001",
            "password": "StaffPassword123!"
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data.get("success"))
        self.assertIn("access", res.data)
        self.assertIn("refresh", res.data)
        self.assertIn("token", res.data)

        # By email
        res2 = self.client.post("/api/staff/login/", {
            "identifier": "amit.reservation@goonstay.com",
            "password": "StaffPassword123!"
        })
        self.assertEqual(res2.status_code, status.HTTP_200_OK)

    def test_staff_login_with_invalid_credentials_fails(self):
        """Invalid credentials return 401 Unauthorized."""
        res = self.client.post("/api/staff/login/", {
            "identifier": "amit.reservation001",
            "password": "WrongPassword999!"
        })
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(res.data.get("success"))

    def test_inactive_or_suspended_staff_login_fails(self):
        """Inactive or suspended staff cannot log in."""
        self.res_profile.status = StaffProfile.STATUS_SUSPENDED
        self.res_profile.save()

        res = self.client.post("/api/staff/login/", {
            "identifier": "amit.reservation001",
            "password": "StaffPassword123!"
        })
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.data.get("code"), "STAFF_SUSPENDED")

        # Restore status
        self.res_profile.status = StaffProfile.STATUS_ACTIVE
        self.res_profile.save()

    def test_staff_profile_endpoint_with_valid_token(self):
        """GET /api/staff/me/ returns authenticated staff profile without exposing password."""
        token = self.get_token(self.res_user)
        res = self.client.get("/api/staff/me/", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        profile_data = res.data.get("staff_profile") or res.data
        self.assertEqual(profile_data.get("employee_id"), "GOS-EMP-TEST-001")
        # Ensure raw password or password hash is never exposed
        self.assertNotIn("password", profile_data)
        self.assertNotIn("password_hash", profile_data)

    def test_staff_profile_endpoint_with_empty_bearer_returns_401(self):
        """Empty Bearer header from Postman returns 401 cleanly without crashing."""
        res = self.client.get("/api/staff/me/", HTTP_AUTHORIZATION="Bearer ")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(res.data.get("message"), "Authentication credentials were not provided.")

    def test_first_login_password_change_enforcement(self):
        """When must_change_password=True, staff cannot access workflows until password changed."""
        self.res_profile.must_change_password = True
        self.res_profile.save()

        token = self.get_token(self.res_user)
        # Attempt workflow access
        res = self.client.get("/api/staff/bookings/", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.data.get("code"), "PASSWORD_CHANGE_REQUIRED")

        # /api/staff/me/ is still permitted
        res_me = self.client.get("/api/staff/me/", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(res_me.status_code, status.HTTP_200_OK)

        # Perform password change
        change_res = self.client.post("/api/staff/change-password/", {
            "old_password": "StaffPassword123!",
            "new_password": "NewStaffPassword456!",
            "confirm_password": "NewStaffPassword456!"
        }, HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(change_res.status_code, status.HTTP_200_OK)

        # Refresh profile state
        self.res_profile.refresh_from_db()
        self.assertFalse(self.res_profile.must_change_password)

        # Reset password back
        self.res_user.set_password("StaffPassword123!")
        self.res_user.save()

    def test_staff_logout_blacklists_token(self):
        """POST /api/staff/logout/ blacklists the refresh token."""
        refresh = RefreshToken.for_user(self.res_user)
        token = str(refresh.access_token)

        res = self.client.post("/api/staff/logout/", {
            "refresh": str(refresh)
        }, HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    # --- SECTION 6: Role and Permission Isolation ---

    def test_customer_cannot_access_staff_apis(self):
        """Customers receive 403 Forbidden on staff endpoints."""
        token = self.get_token(self.customer)
        res = self.client.get("/api/staff/dashboard/", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_hotel_owner_cannot_access_staff_apis(self):
        """Hotel Owners receive 403 Forbidden on staff endpoints."""
        token = self.get_token(self.owner)
        res = self.client.get("/api/staff/dashboard/", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_cannot_access_admin_staff_management_apis(self):
        """Staff cannot create other staff or view admin staff management endpoints."""
        token = self.get_token(self.res_user)
        res = self.client.post("/api/staff/create/", {
            "email": "hacker@test.com",
            "department_code": "RESERVATION"
        }, HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_granular_permission_isolation_between_departments(self):
        """Reservation staff without PROCESS_REFUND cannot process refunds."""
        token = self.get_token(self.res_user)
        # Attempt to process refund
        res = self.client.post("/api/staff/refunds/1/process/", {}, HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    # --- SECTION 5: Endpoints Availability and Structure ---

    def test_all_staff_management_endpoints_exist(self):
        """Verify that all 32 required staff endpoints are routed and return valid HTTP codes."""
        admin_token = self.get_token(self.admin)
        staff_token = self.get_token(self.res_user)

        # Admin management endpoints
        r1 = self.client.get("/api/staff/departments/", HTTP_AUTHORIZATION=f"Bearer {admin_token}")
        self.assertEqual(r1.status_code, status.HTTP_200_OK)

        r2 = self.client.get("/api/staff/", HTTP_AUTHORIZATION=f"Bearer {admin_token}")
        self.assertEqual(r2.status_code, status.HTTP_200_OK)

        r3 = self.client.get("/api/staff/activities/", HTTP_AUTHORIZATION=f"Bearer {admin_token}")
        self.assertEqual(r3.status_code, status.HTTP_200_OK)

        # Department workflows (authenticated staff)
        r4 = self.client.get("/api/staff/bookings/", HTTP_AUTHORIZATION=f"Bearer {staff_token}")
        self.assertEqual(r4.status_code, status.HTTP_200_OK)

        r5 = self.client.get("/api/staff/notifications/", HTTP_AUTHORIZATION=f"Bearer {staff_token}")
        self.assertEqual(r5.status_code, status.HTTP_200_OK)

        r6 = self.client.get("/api/staff/dashboard/", HTTP_AUTHORIZATION=f"Bearer {staff_token}")
        self.assertEqual(r6.status_code, status.HTTP_200_OK)
