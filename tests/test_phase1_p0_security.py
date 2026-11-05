import inspect
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.core.cache import cache
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

import util.otp
from users.models import EmailOTP
from hotels.models import Hotel, HotelStaff
from rooms.models import Room
from bookings.models import Booking
from reviews.models import Review

User = get_user_model()


class Phase1SecurityP0Tests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

        # Create Customer Users
        self.user_a = User.objects.create_user(
            username="user_a",
            email="usera@example.com",
            password="Password123!",
            role=User.ROLE_CUSTOMER
        )
        self.user_b = User.objects.create_user(
            username="user_b",
            email="userb@example.com",
            password="Password123!",
            role=User.ROLE_CUSTOMER
        )

        # Create Admin User
        self.admin_user = User.objects.create_user(
            username="admin_user",
            email="admin@goonstay.com",
            password="AdminPassword123!",
            role=User.ROLE_ADMIN,
            is_staff=True
        )

        # Create Hotel Owners
        self.owner_a = User.objects.create_user(
            username="owner_a",
            email="ownera@example.com",
            password="OwnerPassword123!",
            role=User.ROLE_HOTEL_OWNER
        )
        self.owner_b = User.objects.create_user(
            username="owner_b",
            email="ownerb@example.com",
            password="OwnerPassword123!",
            role=User.ROLE_HOTEL_OWNER
        )

        # Create Hotels
        self.hotel_a = Hotel.objects.create(
            owner=self.owner_a,
            name="Hotel Alpha Mumbai",
            description="Luxury Alpha stay",
            address="Marine Drive",
            city="Mumbai",
            state="Maharashtra",
            is_approved=True,
            is_active=True
        )
        self.hotel_b = Hotel.objects.create(
            owner=self.owner_b,
            name="Hotel Bravo Goa",
            description="Beachside Bravo resort",
            address="Calangute",
            city="Goa",
            state="Goa",
            is_approved=True,
            is_active=True
        )

        # Create Rooms
        self.room_a = Room.objects.create(
            hotel=self.hotel_a,
            title="Deluxe Ocean Suite",
            room_type="DELUXE",
            price_per_night=3000.00,
            total_rooms=5,
            room_numbers="101, 102, 103, 104, 105"
        )
        self.room_b = Room.objects.create(
            hotel=self.hotel_b,
            title="Standard Villa",
            room_type="VILLA",
            price_per_night=4500.00,
            total_rooms=3,
            room_numbers="V-1, V-2, V-3"
        )

        # Create Staff Users
        self.staff_a = User.objects.create_user(
            username="staff_a",
            email="staffa@example.com",
            password="StaffPassword123!",
            role=User.ROLE_HOTEL_STAFF
        )
        self.staff_b = User.objects.create_user(
            username="staff_b",
            email="staffb@example.com",
            password="StaffPassword123!",
            role=User.ROLE_HOTEL_STAFF
        )

        # Associate Staff A with Hotel A ONLY
        HotelStaff.objects.create(
            hotel=self.hotel_a,
            user=self.staff_a,
            role_title="Front Desk Executive",
            can_checkin_checkout=True,
            can_manage_bookings=True
        )

        # Associate Staff B with Hotel B ONLY
        HotelStaff.objects.create(
            hotel=self.hotel_b,
            user=self.staff_b,
            role_title="Duty Manager",
            can_checkin_checkout=True,
            can_manage_bookings=True
        )

        # Create Bookings
        today = timezone.now().date()
        self.booking_a = Booking.objects.create(
            booking_id="BK-HOTEL-A-001",
            customer=self.user_a,
            hotel=self.hotel_a,
            room=self.room_a,
            check_in=today,
            check_out=today + timedelta(days=2),
            number_of_guests=2,
            number_of_rooms=1,
            price_per_night=3000.00,
            subtotal=6000.00,
            total_amount=7080.00,
            payment_status=Booking.PAYMENT_PAID,
            booking_status=Booking.STATUS_CONFIRMED,
            guest_name="Guest User A",
            guest_email=self.user_a.email,
            guest_phone="9876543210"
        )

        self.booking_b = Booking.objects.create(
            booking_id="BK-HOTEL-B-002",
            customer=self.user_b,
            hotel=self.hotel_b,
            room=self.room_b,
            check_in=today,
            check_out=today + timedelta(days=3),
            number_of_guests=2,
            number_of_rooms=1,
            price_per_night=4500.00,
            subtotal=13500.00,
            total_amount=15930.00,
            payment_status=Booking.PAYMENT_PAID,
            booking_status=Booking.STATUS_CONFIRMED,
            guest_name="Guest User B",
            guest_email=self.user_b.email,
            guest_phone="9876543211"
        )

    # =========================================================================
    # TASK P0-01: Remove Plaintext OTP Leakage
    # =========================================================================
    @override_settings(DEBUG=True)
    def test_p0_01_forgot_password_no_dev_hint_otp_with_debug_true(self):
        """Verifies that dev_hint_otp is NEVER returned even when DEBUG=True."""
        cache.clear()
        with patch("users.views.send_otp_email", return_value=True):
            response = self.client.post("/api/auth/forgot-password/", {
                "identifier": self.user_a.email
            }, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("dev_hint_otp", response.data)
        self.assertNotIn("otp", response.data)
        self.assertTrue(response.data.get("mail_sent"))

    @override_settings(DEBUG=False)
    def test_p0_01_forgot_password_no_dev_hint_otp_with_debug_false(self):
        """Verifies that dev_hint_otp is NEVER returned when DEBUG=False."""
        cache.clear()
        with patch("users.views.send_otp_email", return_value=True):
            response = self.client.post("/api/auth/forgot-password/", {
                "identifier": self.user_a.email
            }, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("dev_hint_otp", response.data)
        self.assertNotIn("otp", response.data)

    def test_p0_01_forgot_password_when_smtp_fails(self):
        """Verifies that failed SMTP email delivery does NOT leak OTP in response."""
        cache.clear()
        with patch("users.views.send_otp_email", return_value=False):
            response = self.client.post("/api/auth/forgot-password/", {
                "identifier": self.user_a.email
            }, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("dev_hint_otp", response.data)
        self.assertNotIn("otp", response.data)
        self.assertFalse(response.data.get("mail_sent"))

    def test_p0_01_forgot_password_unknown_identifier_safe_response(self):
        """Verifies that querying a non-existent account returns a safe generic message."""
        cache.clear()
        response = self.client.post("/api/auth/forgot-password/", {
            "identifier": "nonexistent_ghost@example.com"
        }, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("message", response.data)
        self.assertNotIn("dev_hint_otp", response.data)

    # =========================================================================
    # TASK P0-02: Fix Review Deletion Authorization (BOLA)
    # =========================================================================
    def test_p0_02_user_b_cannot_delete_user_a_review(self):
        """Verifies that User B receives HTTP 403 when trying to delete User A's review."""
        review_a = Review.objects.create(
            booking=self.booking_a,
            hotel=self.hotel_a,
            user=self.user_a,
            rating=5,
            comment="Exceptional experience!"
        )

        # Authenticate as User B (attacker)
        self.client.force_authenticate(user=self.user_b)
        response = self.client.delete(f"/api/reviews/{review_a.id}/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        # Ensure review was NOT deleted from the database
        self.assertTrue(Review.objects.filter(id=review_a.id).exists())

    def test_p0_02_user_a_can_delete_own_review(self):
        """Verifies that review author can delete their own review."""
        review_a = Review.objects.create(
            booking=self.booking_a,
            hotel=self.hotel_a,
            user=self.user_a,
            rating=4,
            comment="Very pleasant stay."
        )

        self.client.force_authenticate(user=self.user_a)
        response = self.client.delete(f"/api/reviews/{review_a.id}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Review.objects.filter(id=review_a.id).exists())

    def test_p0_02_admin_can_delete_any_review(self):
        """Verifies that an administrator can delete any review."""
        review_a = Review.objects.create(
            booking=self.booking_a,
            hotel=self.hotel_a,
            user=self.user_a,
            rating=1,
            comment="Spam review"
        )

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.delete(f"/api/reviews/{review_a.id}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Review.objects.filter(id=review_a.id).exists())

    # =========================================================================
    # TASK P0-03: Fix Cross-Hotel Staff Privilege Escalation
    # =========================================================================
    def test_p0_03_staff_a_can_checkin_booking_at_hotel_a(self):
        """Verifies Staff A can check in guests at Hotel A."""
        self.client.force_authenticate(user=self.staff_a)
        response = self.client.post(f"/api/bookings/{self.booking_a.booking_id}/check-in/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.booking_a.refresh_from_db()
        self.assertEqual(self.booking_a.booking_status, Booking.STATUS_CHECKED_IN)

    def test_p0_03_staff_a_cannot_checkin_booking_at_hotel_b(self):
        """Verifies Staff A receives HTTP 403 when attempting check-in at Hotel B."""
        self.client.force_authenticate(user=self.staff_a)
        response = self.client.post(f"/api/bookings/{self.booking_b.booking_id}/check-in/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.booking_b.refresh_from_db()
        self.assertNotEqual(self.booking_b.booking_status, Booking.STATUS_CHECKED_IN)

    def test_p0_03_staff_a_cannot_checkout_booking_at_hotel_b(self):
        """Verifies Staff A receives HTTP 403 when attempting check-out at Hotel B."""
        self.booking_b.booking_status = Booking.STATUS_CHECKED_IN
        self.booking_b.save()

        self.client.force_authenticate(user=self.staff_a)
        response = self.client.post(f"/api/bookings/{self.booking_b.booking_id}/check-out/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.booking_b.refresh_from_db()
        self.assertEqual(self.booking_b.booking_status, Booking.STATUS_CHECKED_IN)

    def test_p0_03_staff_a_cannot_noshow_booking_at_hotel_b(self):
        """Verifies Staff A receives HTTP 403 when attempting no-show at Hotel B."""
        self.client.force_authenticate(user=self.staff_a)
        response = self.client.post(f"/api/bookings/{self.booking_b.booking_id}/no-show/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.booking_b.refresh_from_db()
        self.assertNotEqual(self.booking_b.booking_status, Booking.STATUS_NO_SHOW)

    def test_p0_03_hotel_owner_and_admin_retain_access(self):
        """Verifies that hotel owners and administrators retain authorized access."""
        # Owner A checks in Booking A
        self.client.force_authenticate(user=self.owner_a)
        res_owner = self.client.post(f"/api/bookings/{self.booking_a.booking_id}/check-in/")
        self.assertEqual(res_owner.status_code, status.HTTP_200_OK)

        # Admin checks out Booking A
        self.client.force_authenticate(user=self.admin_user)
        res_admin = self.client.post(f"/api/bookings/{self.booking_a.booking_id}/check-out/")
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)

    # =========================================================================
    # TASK P0-04: Replace Insecure OTP Random Generation
    # =========================================================================
    def test_p0_04_otp_properties_and_csprng(self):
        """Verifies that generated OTPs are 6-digit numeric strings in range 100000-999999."""
        otps = [util.otp.generate_otp() for _ in range(100)]
        for otp in otps:
            self.assertEqual(len(otp), 6, f"OTP '{otp}' must be exactly 6 characters")
            self.assertTrue(otp.isdigit(), f"OTP '{otp}' must be numeric")
            num = int(otp)
            self.assertTrue(100000 <= num <= 999999, f"OTP {num} out of range 100000-999999")

        # Verify that util.otp source code uses 'secrets' and NOT 'random.randint'
        src = inspect.getsource(util.otp.generate_otp)
        self.assertIn("secrets", src)
        self.assertNotIn("random.randint", src)

    # =========================================================================
    # TASK P0-05: Add OTP Attempt Limiting and Lockout
    # =========================================================================
    def test_p0_05_correct_otp_accepted(self):
        """Verifies that correct OTP is accepted before expiry."""
        cache.clear()
        test_otp = "482910"
        EmailOTP.objects.create(
            email="verify_test@example.com",
            otp_hash=util.otp.hash_otp(test_otp),
            attempts=0
        )

        response = self.client.post("/api/auth/verify-otp/", {
            "email": "verify_test@example.com",
            "otp": test_otp
        }, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get("is_verified"))

    def test_p0_05_failed_attempts_increment_and_lockout_at_5(self):
        """
        Verifies attempts 1-4 are rejected with remaining count,
        and attempt 5 triggers lockout and invalidates the OTP.
        """
        email = "lockout_test@example.com"
        correct_otp = "654321"
        record = EmailOTP.objects.create(
            email=email,
            otp_hash=util.otp.hash_otp(correct_otp),
            attempts=0
        )

        # Attempts 1 to 4: Wrong OTP (clear throttle cache to isolate attempt counter logic)
        for i in range(1, 5):
            cache.clear()
            res = self.client.post("/api/auth/verify-otp/", {
                "email": email,
                "otp": "000000"
            }, format="json")
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            record.refresh_from_db()
            self.assertEqual(record.attempts, i)
            expected_remaining = 5 - i
            self.assertIn(f"{expected_remaining} attempt(s) remaining", str(res.data))

        # Attempt 5: Lockout trigger
        cache.clear()
        res_5 = self.client.post("/api/auth/verify-otp/", {
            "email": email,
            "otp": "000000"
        }, format="json")
        self.assertEqual(res_5.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Maximum OTP verification attempts exceeded", str(res_5.data))

        # Record must be deleted/invalidated
        self.assertFalse(EmailOTP.objects.filter(email=email).exists())

        # Attempt 6: Any further attempt rejected
        cache.clear()
        res_6 = self.client.post("/api/auth/verify-otp/", {
            "email": email,
            "otp": correct_otp
        }, format="json")
        self.assertEqual(res_6.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("No OTP requested", str(res_6.data))

    def test_p0_05_expired_otp_rejected(self):
        """Verifies that an expired OTP is rejected and purged."""
        cache.clear()
        email = "expired@example.com"
        record = EmailOTP.objects.create(
            email=email,
            otp_hash=util.otp.hash_otp("123456"),
            attempts=0
        )
        # Artificially age the record by 20 minutes
        EmailOTP.objects.filter(id=record.id).update(
            created_at=timezone.now() - timedelta(minutes=20)
        )

        response = self.client.post("/api/auth/verify-otp/", {
            "email": email,
            "otp": "123456"
        }, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("expired", str(response.data).lower())
        self.assertFalse(EmailOTP.objects.filter(email=email).exists())

    def test_p0_05_otp_replay_prevented(self):
        """Verifies that an already-verified OTP cannot be reused."""
        cache.clear()
        email = "replay@example.com"
        record = EmailOTP.objects.create(
            email=email,
            otp_hash=util.otp.hash_otp("123456"),
            is_verified=True,
            attempts=0
        )

        response = self.client.post("/api/auth/verify-otp/", {
            "email": email,
            "otp": "123456"
        }, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already been verified", str(response.data))

    def test_p0_05_reset_password_attempt_lockout(self):
        """Verifies that ResetPasswordView also enforces the 5-attempt lockout."""
        email = self.user_a.email
        correct_otp = "777888"
        EmailOTP.objects.filter(email=email).delete()
        record = EmailOTP.objects.create(
            email=email,
            otp_hash=util.otp.hash_otp(correct_otp),
            attempts=0
        )

        # 4 wrong attempts
        for _ in range(4):
            cache.clear()
            res = self.client.post("/api/auth/reset-password/", {
                "email": email,
                "otp": "111111",
                "new_password": "NewSecretPassword123!"
            }, format="json")
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        record.refresh_from_db()
        self.assertEqual(record.attempts, 4)

        # 5th attempt invalidates
        cache.clear()
        res_5 = self.client.post("/api/auth/reset-password/", {
            "email": email,
            "otp": "111111",
            "new_password": "NewSecretPassword123!"
        }, format="json")
        self.assertEqual(res_5.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Maximum OTP verification attempts exceeded", str(res_5.data))
        self.assertFalse(EmailOTP.objects.filter(email=email).exists())

    def test_p0_05_rate_limiting_throttles_excessive_requests(self):
        """Verifies that exceeding the scoped rate limit triggers HTTP 429."""
        cache.clear()
        email = "throttle_test@example.com"
        EmailOTP.objects.create(
            email=email,
            otp_hash=util.otp.hash_otp("123456"),
            attempts=0
        )
        # Send 5 rapid requests (within 1 minute rate limit)
        for _ in range(5):
            self.client.post("/api/auth/verify-otp/", {"email": email, "otp": "999999"}, format="json")

        # 6th request within the same minute window must be throttled with 429
        res_throttled = self.client.post("/api/auth/verify-otp/", {"email": email, "otp": "999999"}, format="json")
        self.assertEqual(res_throttled.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_p0_05_multiple_attempts_atomic_increment_cannot_bypass_limit(self):
        """Verifies that failed attempts atomically increment attempts counter and enforce lockout."""
        cache.clear()
        email = "atomic_test@example.com"
        record = EmailOTP.objects.create(
            email=email,
            otp_hash=util.otp.hash_otp("999999"),
            attempts=0
        )

        # 4 successive invalid attempts
        for i in range(1, 5):
            cache.clear()
            res = self.client.post("/api/auth/verify-otp/", {"email": email, "otp": "000000"}, format="json")
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            record.refresh_from_db()
            self.assertEqual(record.attempts, i)

        # 5th invalid attempt enforces lockout and deletes record
        cache.clear()
        res_5 = self.client.post("/api/auth/verify-otp/", {"email": email, "otp": "000000"}, format="json")
        self.assertEqual(res_5.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Maximum OTP verification attempts exceeded", str(res_5.data))
        self.assertFalse(EmailOTP.objects.filter(email=email).exists())

    # =========================================================================
    # BACKWARD COMPATIBILITY TESTS
    # =========================================================================
    def test_backward_compatibility_registration_and_login(self):
        """Verifies that full registration and login flow remains 100% operational."""
        cache.clear()
        reg_payload = {
            "username": "new_guest_2026",
            "email": "newguest2026@example.com",
            "password": "ValidPassword123!",
            "password_confirm": "ValidPassword123!",
            "role": "CUSTOMER"
        }
        res_reg = self.client.post("/api/auth/register/", reg_payload, format="json")
        self.assertEqual(res_reg.status_code, status.HTTP_201_CREATED)
        self.assertIn("token", res_reg.data)
        self.assertIn("access", res_reg.data)
        self.assertIn("refresh", res_reg.data)

        # Login with newly registered user
        res_login = self.client.post("/api/auth/login/", {
            "identifier": "newguest2026@example.com",
            "password": "ValidPassword123!"
        }, format="json")
        self.assertEqual(res_login.status_code, status.HTTP_200_OK)
        self.assertIn("token", res_login.data)
