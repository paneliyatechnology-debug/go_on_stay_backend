import json
from datetime import timedelta
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken

from staff.models import Department, StaffProfile, StaffPermission, ManagerMFAProfile
from util.totp import generate_totp_secret, generate_totp_code

User = get_user_model()


@override_settings(
    BYPASS_MFA_ENROLLMENT_IN_TESTS=False,
    BYPASS_THROTTLING_IN_TESTS=True,
    TESTING=True
)
class StaffAuthenticationRemediationTests(TestCase):
    """
    Comprehensive 23-Test Suite for GoOnStay Staff Authentication Remediation.
    Tests all P0 scenarios defined in the Task Specification.
    Runs exclusively on Django's isolated test database.
    """

    @classmethod
    def setUpTestData(cls):
        # 1. Departments
        cls.dept_res, _ = Department.objects.get_or_create(
            code="RESERVATION",
            defaults={"name": "Reservation & Booking", "description": "Bookings department"}
        )
        cls.dept_ref, _ = Department.objects.get_or_create(
            code="REFUNDS_CLAIMS",
            defaults={"name": "Refunds & Claims", "description": "Refunds department"}
        )

        # 2. Permissions
        cls.perm_res_view, _ = StaffPermission.objects.get_or_create(
            code="VIEW_BOOKINGS",
            defaults={"name": "View Bookings", "department": cls.dept_res, "category": "RESERVATION"}
        )
        cls.perm_ref_view, _ = StaffPermission.objects.get_or_create(
            code="VIEW_REFUNDS",
            defaults={"name": "View Refunds", "department": cls.dept_ref, "category": "REFUNDS"}
        )

        # 3. Regular Staff User (Level 1)
        cls.staff_password = "StaffSecurePass123!"
        cls.staff_user = User.objects.create_user(
            username="arun.reservation001",
            email="arun.staff@goonstay.com",
            password=cls.staff_password,
            first_name="Arun",
            last_name="Kumar",
            role=User.ROLE_STAFF,
            is_staff=True,
            is_active=True
        )
        cls.staff_profile = StaffProfile.objects.create(
            user=cls.staff_user,
            employee_id="GOS-EMP-TEST-001",
            login_id="arun.reservation001",
            department=cls.dept_res,
            status=StaffProfile.STATUS_ACTIVE,
            designation="Booking Associate",
            must_change_password=False
        )
        cls.staff_profile.permissions.set([cls.perm_res_view])

        # 4. Department Staff Manager (Level 2)
        cls.dept_mgr_password = "DeptManagerPass123!"
        cls.dept_mgr_user = User.objects.create_user(
            username="dept.mgr001",
            email="dept.mgr@goonstay.com",
            password=cls.dept_mgr_password,
            first_name="Suresh",
            last_name="Patel",
            role=User.ROLE_DEPARTMENT_STAFF_MANAGER,
            is_staff=True,
            is_active=True
        )
        cls.dept_mgr_profile = StaffProfile.objects.create(
            user=cls.dept_mgr_user,
            employee_id="GOS-EMP-TEST-002",
            login_id="dept.mgr001",
            department=cls.dept_res,
            status=StaffProfile.STATUS_ACTIVE,
            is_manager=True,
            designation="Reservation Manager",
            must_change_password=False
        )
        cls.dept_mgr_mfa = ManagerMFAProfile.objects.create(
            user=cls.dept_mgr_user,
            totp_secret=generate_totp_secret(),
            is_enrolled=True,
            is_mfa_enabled=True
        )

        # 5. Main Manager (Level 3)
        cls.main_mgr_password = "MainManagerPass123!"
        cls.main_mgr_user = User.objects.create_user(
            username="main.mgr001",
            email="main.mgr@goonstay.com",
            password=cls.main_mgr_password,
            first_name="Vikram",
            last_name="Mehta",
            role=User.ROLE_MAIN_MANAGER,
            is_staff=True,
            is_active=True
        )
        cls.main_mgr_profile = StaffProfile.objects.create(
            user=cls.main_mgr_user,
            employee_id="GOS-EMP-TEST-003",
            login_id="main.mgr001",
            department=None,
            status=StaffProfile.STATUS_ACTIVE,
            is_manager=True,
            designation="Operations Director",
            must_change_password=False
        )
        cls.main_mgr_mfa = ManagerMFAProfile.objects.create(
            user=cls.main_mgr_user,
            totp_secret=generate_totp_secret(),
            is_enrolled=True,
            is_mfa_enabled=True
        )

        # 6. Admin User (Level 4)
        cls.admin_password = "AdminSuperPass123!"
        cls.admin_user = User.objects.create_superuser(
            username="test_admin01",
            email="test_admin01@goonstay.com",
            password=cls.admin_password,
            first_name="System",
            last_name="Admin",
            role=User.ROLE_ADMIN,
            is_staff=True,
            is_active=True
        )

        # 7. Customer User
        cls.customer_password = "CustomerPass123!"
        cls.customer_user = User.objects.create_user(
            username="test_guest01",
            email="guest01@example.com",
            password=cls.customer_password,
            role=User.ROLE_CUSTOMER,
            is_staff=False,
            is_active=True
        )

        # 8. Hotel Owner User
        cls.host_password = "HostPassword123!"
        cls.host_user = User.objects.create_user(
            username="test_owner01",
            email="owner01@example.com",
            password=cls.host_password,
            role=User.ROLE_HOTEL_OWNER,
            is_staff=False,
            is_active=True
        )

    def setUp(self):
        self.client = APIClient()

    # =========================================================================
    # TEST CASE 1: Valid staff email and password
    # =========================================================================
    def test_01_valid_staff_email_and_password(self):
        """Staff authenticates with email and password, receives JWT tokens and correct envelope."""
        res = self.client.post("/api/staff/login/", {
            "identifier": "arun.staff@goonstay.com",
            "password": self.staff_password
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data.get("success"))
        # Top-level token access
        self.assertIn("access", res.data)
        self.assertIn("refresh", res.data)
        self.assertIn("tokens", res.data)
        self.assertIn("access", res.data["tokens"])
        self.assertIn("refresh", res.data["tokens"])
        # Nested data token access
        self.assertIn("data", res.data)
        self.assertIn("tokens", res.data["data"])
        self.assertEqual(res.data["tokens"]["access"], res.data["access"])

        # Also verify login by login_id
        res2 = self.client.post("/api/staff/login/", {
            "identifier": "arun.reservation001",
            "password": self.staff_password
        }, format="json")
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertTrue(res2.data.get("success"))

    # =========================================================================
    # TEST CASE 2: Invalid password
    # =========================================================================
    def test_02_invalid_password(self):
        """Mismatched password returns HTTP 401 with INVALID_CREDENTIALS."""
        res = self.client.post("/api/staff/login/", {
            "identifier": "arun.staff@goonstay.com",
            "password": "WrongPassword999!"
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(res.data.get("success"))
        self.assertEqual(res.data.get("code"), "INVALID_CREDENTIALS")
        self.assertEqual(res.data.get("error"), "Invalid staff credentials.")

    # =========================================================================
    # TEST CASE 3: Unknown staff email
    # =========================================================================
    def test_03_unknown_staff_email(self):
        """Non-existent staff email returns HTTP 401 with INVALID_CREDENTIALS (no user enumeration)."""
        res = self.client.post("/api/staff/login/", {
            "identifier": "ghost.staff@goonstay.com",
            "password": "SomePassword123!"
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(res.data.get("success"))
        self.assertEqual(res.data.get("code"), "INVALID_CREDENTIALS")

    # =========================================================================
    # TEST CASE 4: Missing identifier
    # =========================================================================
    def test_04_missing_identifier(self):
        """Payload omitting identifier field returns HTTP 400 with VALIDATION_ERROR."""
        res = self.client.post("/api/staff/login/", {
            "password": self.staff_password
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(res.data.get("success"))
        self.assertEqual(res.data.get("error", {}).get("code"), "VALIDATION_ERROR")
        self.assertIn("identifier", str(res.data))

    # =========================================================================
    # TEST CASE 5: Missing password
    # =========================================================================
    def test_05_missing_password(self):
        """Payload omitting password field returns HTTP 400 with VALIDATION_ERROR."""
        res = self.client.post("/api/staff/login/", {
            "identifier": "arun.staff@goonstay.com"
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(res.data.get("success"))
        self.assertEqual(res.data.get("error", {}).get("code"), "VALIDATION_ERROR")
        self.assertIn("password", str(res.data))

    # =========================================================================
    # TEST CASE 6: Null identifier
    # =========================================================================
    def test_06_null_identifier(self):
        """Payload with identifier: null returns HTTP 400 with 'This field may not be null.'"""
        res = self.client.post("/api/staff/login/", {
            "identifier": None,
            "password": self.staff_password
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(res.data.get("success"))
        self.assertEqual(res.data.get("error", {}).get("code"), "VALIDATION_ERROR")
        self.assertIn("This field may not be null.", str(res.data))

    # =========================================================================
    # TEST CASE 7: Null password
    # =========================================================================
    def test_07_null_password(self):
        """Payload with password: null returns HTTP 400 with 'This field may not be null.'"""
        res = self.client.post("/api/staff/login/", {
            "identifier": "arun.staff@goonstay.com",
            "password": None
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(res.data.get("success"))
        self.assertEqual(res.data.get("error", {}).get("code"), "VALIDATION_ERROR")
        self.assertIn("This field may not be null.", str(res.data))

    # =========================================================================
    # TEST CASE 8: Empty identifier
    # =========================================================================
    def test_08_empty_identifier(self):
        """Empty string or whitespace identifier returns HTTP 400 with 'This field may not be blank.'"""
        # Empty string
        res = self.client.post("/api/staff/login/", {
            "identifier": "",
            "password": self.staff_password
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(res.data.get("success"))
        self.assertIn("This field may not be blank.", str(res.data))

        # Whitespace-only string
        res2 = self.client.post("/api/staff/login/", {
            "identifier": "     ",
            "password": self.staff_password
        }, format="json")
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(res2.data.get("success"))
        self.assertIn("This field may not be blank.", str(res2.data))

    # =========================================================================
    # TEST CASE 9: Empty password
    # =========================================================================
    def test_09_empty_password(self):
        """Empty string or whitespace password returns HTTP 400 with 'This field may not be blank.'"""
        res = self.client.post("/api/staff/login/", {
            "identifier": "arun.staff@goonstay.com",
            "password": ""
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(res.data.get("success"))
        self.assertIn("This field may not be blank.", str(res.data))

        res2 = self.client.post("/api/staff/login/", {
            "identifier": "arun.staff@goonstay.com",
            "password": "   "
        }, format="json")
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(res2.data.get("success"))
        self.assertIn("This field may not be blank.", str(res2.data))

    # =========================================================================
    # TEST CASE 10: Invalid JSON
    # =========================================================================
    def test_10_invalid_json(self):
        """Malformed JSON payload returns HTTP 400 Bad Request."""
        res = self.client.post(
            "/api/staff/login/",
            data='{"identifier": "arun.staff@goonstay.com", "password": ',
            content_type="application/json"
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(res.data.get("success"))

    # =========================================================================
    # TEST CASE 11: Staff user without StaffProfile
    # =========================================================================
    def test_11_staff_user_without_staff_profile(self):
        """User with STAFF role but missing StaffProfile returns controlled HTTP 401 STAFF_PROFILE_MISSING."""
        orphan_user = User.objects.create_user(
            username="orphan.staff01",
            email="orphan@goonstay.com",
            password="OrphanPassword123!",
            role=User.ROLE_STAFF,
            is_staff=True,
            is_active=True
        )
        res = self.client.post("/api/staff/login/", {
            "identifier": "orphan@goonstay.com",
            "password": "OrphanPassword123!"
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(res.data.get("success"))
        self.assertEqual(res.data.get("code"), "STAFF_PROFILE_MISSING")

    # =========================================================================
    # TEST CASE 12: Inactive staff
    # =========================================================================
    def test_12_inactive_staff(self):
        """User with is_active=False returns HTTP 403 ACCOUNT_DISABLED."""
        self.staff_user.is_active = False
        self.staff_user.save()
        try:
            res = self.client.post("/api/staff/login/", {
                "identifier": "arun.staff@goonstay.com",
                "password": self.staff_password
            }, format="json")
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
            self.assertFalse(res.data.get("success"))
            self.assertEqual(res.data.get("code"), "ACCOUNT_DISABLED")
        finally:
            self.staff_user.is_active = True
            self.staff_user.save()

    # =========================================================================
    # TEST CASE 13: Disabled staff (blocked or suspended)
    # =========================================================================
    def test_13_disabled_staff_blocked_and_suspended(self):
        """User with is_blocked=True returns 403 ACCOUNT_DISABLED; profile status SUSPENDED returns 403 STAFF_SUSPENDED."""
        # 1. Blocked
        self.staff_user.is_blocked = True
        self.staff_user.save()
        try:
            res = self.client.post("/api/staff/login/", {
                "identifier": "arun.staff@goonstay.com",
                "password": self.staff_password
            }, format="json")
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(res.data.get("code"), "ACCOUNT_DISABLED")
        finally:
            self.staff_user.is_blocked = False
            self.staff_user.save()

        # 2. Suspended
        self.staff_profile.status = StaffProfile.STATUS_SUSPENDED
        self.staff_profile.save()
        try:
            res = self.client.post("/api/staff/login/", {
                "identifier": "arun.staff@goonstay.com",
                "password": self.staff_password
            }, format="json")
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(res.data.get("code"), "STAFF_SUSPENDED")
        finally:
            self.staff_profile.status = StaffProfile.STATUS_ACTIVE
            self.staff_profile.save()

    # =========================================================================
    # TEST CASE 14: Valid Department Staff Manager
    # =========================================================================
    def test_14_valid_department_staff_manager(self):
        """Department Staff Manager (Level 2) login returns MFA challenge or direct tokens with valid OTP."""
        # 1. Login with credentials triggers MFA challenge
        res = self.client.post("/api/staff/login/", {
            "identifier": "dept.mgr@goonstay.com",
            "password": self.dept_mgr_password
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data.get("mfa_required"))
        self.assertIn("temp_token", res.data)

        # 2. Login providing valid totp_code simultaneously returns tokens directly
        valid_otp = generate_totp_code(self.dept_mgr_mfa.totp_secret)
        res_direct = self.client.post("/api/staff/login/", {
            "identifier": "dept.mgr@goonstay.com",
            "password": self.dept_mgr_password,
            "totp_code": valid_otp
        }, format="json")
        self.assertEqual(res_direct.status_code, status.HTTP_200_OK)
        self.assertTrue(res_direct.data.get("success"))
        self.assertIn("access", res_direct.data)

    # =========================================================================
    # TEST CASE 15: Valid Main Manager
    # =========================================================================
    def test_15_valid_main_manager(self):
        """Main Manager (Level 3) login returns MFA challenge and verifies successfully."""
        valid_otp = generate_totp_code(self.main_mgr_mfa.totp_secret)
        res = self.client.post("/api/staff/login/", {
            "identifier": "main.mgr@goonstay.com",
            "password": self.main_mgr_password,
            "totp_code": valid_otp
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data.get("success"))
        self.assertIn("access", res.data)
        self.assertEqual(res.data.get("user", {}).get("role"), User.ROLE_MAIN_MANAGER)

    # =========================================================================
    # TEST CASE 16: Valid Admin
    # =========================================================================
    def test_16_valid_admin(self):
        """Platform Admin (Level 4) authenticates via Staff Login."""
        # Setup Admin MFA Profile so direct MFA verification works
        admin_mfa, _ = ManagerMFAProfile.objects.get_or_create(
            user=self.admin_user,
            defaults={"totp_secret": generate_totp_secret(), "is_enrolled": True, "is_mfa_enabled": True}
        )
        admin_otp = generate_totp_code(admin_mfa.totp_secret)
        res = self.client.post("/api/staff/login/", {
            "identifier": "test_admin01@goonstay.com",
            "password": self.admin_password,
            "totp_code": admin_otp
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data.get("success"))
        self.assertTrue(res.data.get("is_admin"))

    # =========================================================================
    # TEST CASE 17: Customer attempting staff login
    # =========================================================================
    def test_17_customer_attempting_staff_login(self):
        """Customer role attempting to log in via /api/staff/login/ is rejected with HTTP 401."""
        res = self.client.post("/api/staff/login/", {
            "identifier": "guest01@example.com",
            "password": self.customer_password
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(res.data.get("success"))
        self.assertEqual(res.data.get("code"), "AUTHENTICATION_FAILED")

    # =========================================================================
    # TEST CASE 18: Hotel Owner attempting staff login
    # =========================================================================
    def test_18_hotel_owner_attempting_staff_login(self):
        """Hotel Owner role attempting to log in via /api/staff/login/ is rejected with HTTP 401."""
        res = self.client.post("/api/staff/login/", {
            "identifier": "owner01@example.com",
            "password": self.host_password
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(res.data.get("success"))
        self.assertEqual(res.data.get("code"), "AUTHENTICATION_FAILED")

    # =========================================================================
    # TEST CASE 19: Valid JWT access token
    # =========================================================================
    def test_19_valid_jwt_access_token(self):
        """Generated JWT access token grants access to protected /api/staff/me/ endpoint."""
        token = str(RefreshToken.for_user(self.staff_user).access_token)
        res = self.client.get(
            "/api/staff/me/",
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data.get("success"))
        self.assertEqual(res.data.get("staff_profile", {}).get("login_id"), "arun.reservation001")

    # =========================================================================
    # TEST CASE 20: Invalid JWT
    # =========================================================================
    def test_20_invalid_jwt(self):
        """Malformed or tampered JWT returns HTTP 401 on protected endpoints."""
        res = self.client.get(
            "/api/staff/me/",
            HTTP_AUTHORIZATION="Bearer invalid.tampered.token123"
        )
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    # =========================================================================
    # TEST CASE 21: Expired JWT
    # =========================================================================
    def test_21_expired_jwt(self):
        """Expired JWT token returns HTTP 401 on protected endpoints."""
        token = AccessToken.for_user(self.staff_user)
        # Manually force expiration timestamp into the past
        token.set_exp(lifetime=-timedelta(minutes=10))
        expired_token_str = str(token)

        res = self.client.get(
            "/api/staff/me/",
            HTTP_AUTHORIZATION=f"Bearer {expired_token_str}"
        )
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    # =========================================================================
    # TEST CASE 22: Unauthorized department access
    # =========================================================================
    def test_22_unauthorized_department_access(self):
        """Staff member from Reservation department cannot access Refunds department operations."""
        token = str(RefreshToken.for_user(self.staff_user).access_token)
        # Attempt to access refund department endpoints
        res = self.client.get(
            "/api/staff/refunds/",
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    # =========================================================================
    # TEST CASE 23: Existing authentication regression verification
    # =========================================================================
    def test_23_existing_authentication_regression_verification(self):
        """Backward compatibility for legacy payloads sending 'login_id' instead of 'identifier'."""
        res = self.client.post("/api/staff/login/", {
            "login_id": "arun.reservation001",
            "password": self.staff_password
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data.get("success"))
        self.assertIn("access", res.data)
        # Verify null both fields returns Error B structure
        res_null = self.client.post("/api/staff/login/", {
            "identifier": None,
            "password": None
        }, format="json")
        self.assertEqual(res_null.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res_null.data.get("error", {}).get("code"), "VALIDATION_ERROR")
        self.assertIn("identifier", res_null.data.get("error", {}).get("details", {}))
        self.assertIn("password", res_null.data.get("error", {}).get("details", {}))
