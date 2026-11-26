import datetime
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking

User = get_user_model()


class BookingIdempotencyAndPendingReuseTests(APITestCase):
    def setUp(self):
        # 1. Hotel Owner
        self.owner = User.objects.create_user(
            username="owner_user",
            email="owner@example.com",
            password="OwnerPassword123!",
            role=User.ROLE_HOTEL_OWNER
        )

        # 2. Hotel
        self.hotel = Hotel.objects.create(
            name="Grand Idempotency Resort",
            owner=self.owner,
            city="Goa",
            address="Beach Road",
            status=Hotel.STATUS_APPROVED,
            is_approved=True
        )

        # 3. Room with exactly 1 unit
        self.single_unit_room = Room.objects.create(
            hotel=self.hotel,
            title="Single Exclusive Suite",
            room_type="SUITE",
            price_per_night=5000.00,
            total_rooms=1,
            capacity_adults=2,
            capacity_children=1
        )

        # 4. Customers
        self.customer_a = User.objects.create_user(
            username="guest_a",
            email="guesta@example.com",
            password="GuestPassword123!",
            role=User.ROLE_CUSTOMER
        )
        self.customer_b = User.objects.create_user(
            username="guest_b",
            email="guestb@example.com",
            password="GuestPassword123!",
            role=User.ROLE_CUSTOMER
        )

        self.stay_in = timezone.now().date() + datetime.timedelta(days=10)
        self.stay_out = timezone.now().date() + datetime.timedelta(days=12)

        self.payload = {
            "hotel": self.hotel.id,
            "room": self.single_unit_room.id,
            "check_in": self.stay_in.isoformat(),
            "check_out": self.stay_out.isoformat(),
            "number_of_rooms": 1,
            "adults": 2,
            "children": 0,
            "guest_name": "Guest A",
            "guest_email": "guesta@example.com",
            "guest_phone": "9876543210"
        }

    def test_01_first_booking_attempt_creates_pending_reservation(self):
        """First valid attempt creates a 201 CREATED pending reservation."""
        self.client.force_authenticate(user=self.customer_a)
        response = self.client.post("/api/bookings/", self.payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("booking_id", response.data)
        self.assertEqual(response.data["booking_status"], Booking.STATUS_PENDING_PAYMENT)
        self.assertEqual(response.data["payment_status"], Booking.PAYMENT_PENDING)

    def test_02_browser_refresh_or_retry_reuses_existing_pending_booking(self):
        """
        When the same customer makes a second attempt (e.g. browser refresh / network lag),
        the system reuses the existing pending booking instead of throwing HTTP 409 Conflict.
        """
        self.client.force_authenticate(user=self.customer_a)

        # First request
        res1 = self.client.post("/api/bookings/", self.payload, format="json")
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)
        first_booking_id = res1.data["booking_id"]

        # Second request (simulating browser refresh / double click)
        res2 = self.client.post("/api/bookings/", self.payload, format="json")
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(res2.headers.get("X-Idempotent-Replay"), "true")
        self.assertEqual(res2.data["booking_id"], first_booking_id)

        # Ensure database count of bookings for Customer A is STILL 1 (no duplicate row)
        self.assertEqual(Booking.objects.filter(customer=self.customer_a).count(), 1)

    def test_03_explicit_idempotency_key_header_replays_matching_booking(self):
        """
        When an Idempotency-Key HTTP header is sent, identical requests return the original booking.
        """
        self.client.force_authenticate(user=self.customer_a)
        custom_headers = {"HTTP_IDEMPOTENCY_KEY": "unique-client-key-998877"}

        # First request with header
        res1 = self.client.post("/api/bookings/", self.payload, format="json", **custom_headers)
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)
        booking_id = res1.data["booking_id"]

        # Retry with same header
        res2 = self.client.post("/api/bookings/", self.payload, format="json", **custom_headers)
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(res2.headers.get("X-Idempotent-Replay"), "true")
        self.assertEqual(res2.data["booking_id"], booking_id)

    def test_04_different_customer_is_blocked_by_competing_hold(self):
        """
        While Customer A holds the single unit, Customer B attempting to book receives HTTP 409 CONFLICT.
        Pending booking reuse is strictly scoped to the SAME customer.
        """
        # Customer A holds the room
        self.client.force_authenticate(user=self.customer_a)
        res_a = self.client.post("/api/bookings/", self.payload, format="json")
        self.assertEqual(res_a.status_code, status.HTTP_201_CREATED)

        # Customer B tries to book the same room for the same dates
        self.client.force_authenticate(user=self.customer_b)
        res_b = self.client.post("/api/bookings/", self.payload, format="json")

        self.assertEqual(res_b.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res_b.data["code"], "ROOMS_SOLD_OUT")
