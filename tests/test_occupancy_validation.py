import json
from decimal import Decimal
from datetime import timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status, serializers

from util.validators import validate_occupancy
from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking

User = get_user_model()


class OccupancyValidationUnitTests(TestCase):
    """
    Unit tests for validate_occupancy function across all 3 parts:
      Part 1: Adults (Ages 13+)
      Part 2: Children (Ages 2-12)
      Part 3: Rooms Required (Number of rooms needed)
    """

    def test_part1_valid_adults_single_room(self):
        """1 adult in 1 room is valid."""
        res = validate_occupancy(adults=1, rooms=1)
        self.assertEqual(res['adults'], 1)
        self.assertEqual(res['children'], 0)
        self.assertEqual(res['rooms'], 1)
        self.assertEqual(res['total_guests'], 1)

    def test_part1_one_person_two_rooms_rejected(self):
        """1 adult cannot book 2 rooms (1 person 1 room rule)."""
        with self.assertRaises(serializers.ValidationError) as ctx:
            validate_occupancy(adults=1, rooms=2)
        err = ctx.exception.detail
        self.assertIn('rooms', err)
        self.assertIn('cannot book 2 room(s)', str(err['rooms']))

    def test_part1_zero_adults_rejected(self):
        """0 adults must be rejected because minors cannot stay alone."""
        with self.assertRaises(serializers.ValidationError) as ctx:
            validate_occupancy(adults=0, rooms=1)
        err = ctx.exception.detail
        self.assertIn('adults', err)

    def test_part1_negative_adults_rejected(self):
        """Negative adults must be rejected."""
        with self.assertRaises(serializers.ValidationError) as ctx:
            validate_occupancy(adults=-1, rooms=1)
        err = ctx.exception.detail
        self.assertIn('adults', err)

    def test_part2_children_accompanied_by_adults_accepted(self):
        """Children accompanied by adults are valid."""
        res = validate_occupancy(adults=2, children=2, rooms=1)
        self.assertEqual(res['adults'], 2)
        self.assertEqual(res['children'], 2)
        self.assertEqual(res['total_guests'], 4)
        self.assertEqual(res['rooms'], 1)

    def test_part2_unaccompanied_children_rejected(self):
        """Children without any adult must be rejected."""
        with self.assertRaises(serializers.ValidationError) as ctx:
            validate_occupancy(adults=0, children=2, rooms=1)
        err = ctx.exception.detail
        self.assertTrue('adults' in err or 'children' in err)

    def test_part2_negative_children_rejected(self):
        """Negative children count must be rejected."""
        with self.assertRaises(serializers.ValidationError) as ctx:
            validate_occupancy(adults=1, children=-1, rooms=1)
        err = ctx.exception.detail
        self.assertIn('children', err)

    def test_part3_zero_or_negative_rooms_rejected(self):
        """Rooms < 1 must be rejected."""
        with self.assertRaises(serializers.ValidationError) as ctx:
            validate_occupancy(adults=1, rooms=0)
        self.assertIn('rooms', ctx.exception.detail)

        with self.assertRaises(serializers.ValidationError) as ctx2:
            validate_occupancy(adults=1, rooms=-2)
        self.assertIn('rooms', ctx2.exception.detail)

    def test_part3_rooms_exceeding_total_guests_rejected(self):
        """Cannot book more rooms than total guests (e.g. 2 guests for 3 rooms)."""
        with self.assertRaises(serializers.ValidationError) as ctx:
            validate_occupancy(adults=2, children=0, rooms=3)
        self.assertIn('rooms', ctx.exception.detail)

    def test_part3_two_adults_two_rooms_accepted(self):
        """2 adults in 2 rooms (1 adult per room) is valid."""
        res = validate_occupancy(adults=2, rooms=2)
        self.assertEqual(res['adults'], 2)
        self.assertEqual(res['rooms'], 2)
        self.assertEqual(res['total_guests'], 2)

    def test_part3_maximum_rooms_limit(self):
        """Rooms > 30 must be rejected."""
        with self.assertRaises(serializers.ValidationError) as ctx:
            validate_occupancy(adults=40, rooms=35)
        self.assertIn('rooms', ctx.exception.detail)

    def test_room_physical_capacity_check(self):
        """When a Room object is passed, total guests cannot exceed room physical capacity."""
        class MockRoom:
            title = 'Standard Deluxe'
            capacity_adults = 2
            capacity_children = 1
            extra_guest_price = 500

        mock_rm = MockRoom()

        # 2 adults + 1 child in 1 room = 3 guests (Capacity: 3) -> OK
        res = validate_occupancy(adults=2, children=1, rooms=1, room=mock_rm)
        self.assertEqual(res['total_guests'], 3)

        # 4 adults in 1 room (Capacity: 2 adults + 1 child) -> Rejected!
        with self.assertRaises(serializers.ValidationError) as ctx:
            validate_occupancy(adults=4, children=0, rooms=1, room=mock_rm)
        err = ctx.exception.detail
        self.assertTrue('number_of_guests' in err or 'adults' in err)

        # 4 adults in 2 rooms (2 adults per room) -> OK
        res2 = validate_occupancy(adults=4, children=0, rooms=2, room=mock_rm)
        self.assertEqual(res2['rooms'], 2)


class OccupancyAPIIntegrationTests(TestCase):
    """
    Integration tests for hotel search, room availability check, and booking creation APIs.
    """

    def setUp(self):
        self.client = APIClient()

        # Create Owner
        self.owner = User.objects.create_user(
            username='hotel_owner_occ',
            email='owner_occ@example.com',
            password='Password123!',
            role='HOTEL_OWNER',
            phone_number='9876543210'
        )

        # Create Customer
        self.customer = User.objects.create_user(
            username='customer_occ',
            email='customer_occ@example.com',
            password='Password123!',
            role='CUSTOMER',
            phone_number='9876543211'
        )

        # Create Hotel
        self.hotel = Hotel.objects.create(
            owner=self.owner,
            name='GoOnStay Grand Residency',
            city='Bengaluru',
            state='Karnataka',
            country='India',
            status=Hotel.STATUS_APPROVED,
            is_approved=True,
            is_deleted=False,
            is_active=True
        )

        # Create Room (capacity: 2 adults, 1 child)
        self.room = Room.objects.create(
            hotel=self.hotel,
            room_type='DELUXE',
            title='Deluxe King Room',
            price_per_night=Decimal('2500.00'),
            capacity_adults=2,
            capacity_children=1,
            total_rooms=5,
            breakfast_included=True,
            free_cancellation=True
        )

        self.check_in = (timezone.now().date() + timedelta(days=5)).strftime('%Y-%m-%d')
        self.check_out = (timezone.now().date() + timedelta(days=7)).strftime('%Y-%m-%d')

    # --- 1. HOTEL SEARCH API OCCUPANCY VALIDATION ---
    def test_search_api_one_person_two_rooms_rejected(self):
        """Search API returns 400 INVALID_OCCUPANCY when 1 adult tries to search 2 rooms."""
        response = self.client.get(f'/api/hotels/search/?adults=1&rooms=2')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data.get('error', {}).get('code'), 'INVALID_OCCUPANCY')
        self.assertIn('cannot book 2 room(s)', response.data['error']['message'])

    def test_search_api_legacy_guests_param_one_person_two_rooms_rejected(self):
        """Search API returns 400 INVALID_OCCUPANCY when guests=1&rooms=2."""
        response = self.client.get(f'/api/hotels/search/?guests=1&rooms=2')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data.get('error', {}).get('code'), 'INVALID_OCCUPANCY')

    def test_search_api_zero_adults_rejected(self):
        """Search API returns 400 when adults=0."""
        response = self.client.get(f'/api/hotels/search/?adults=0&children=2&rooms=1')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data.get('error', {}).get('code'), 'INVALID_OCCUPANCY')

    def test_search_api_valid_occupancy_returns_200(self):
        """Search API succeeds with 200 OK for valid occupancy."""
        response = self.client.get(
            f'/api/hotels/search/?city=Bengaluru&adults=2&children=1&rooms=1&check_in={self.check_in}&check_out={self.check_out}'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('search_criteria', response.data)
        self.assertEqual(response.data['search_criteria']['adults'], 2)
        self.assertEqual(response.data['search_criteria']['rooms'], 1)

    # --- 2. ROOM CHECK-AVAILABILITY API OCCUPANCY VALIDATION ---
    def test_room_availability_one_person_two_rooms_rejected(self):
        """Check-availability API rejects 1 adult for 2 rooms."""
        response = self.client.get(
            f'/api/rooms/check-availability/?room_id={self.room.id}&check_in={self.check_in}&check_out={self.check_out}&adults=1&rooms=2'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('cannot book 2 room(s)', str(response.data.get('error', '')))

    def test_room_availability_exceeds_physical_capacity_rejected(self):
        """Check-availability API rejects guests exceeding room capacity (e.g. 6 guests in 1 room)."""
        response = self.client.get(
            f'/api/rooms/check-availability/?room_id={self.room.id}&check_in={self.check_in}&check_out={self.check_out}&adults=5&rooms=1'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('exceed', str(response.data.get('error', '')).lower())

    def test_room_availability_valid_returns_200(self):
        """Check-availability API succeeds with 200 for valid occupancy."""
        response = self.client.get(
            f'/api/rooms/check-availability/?room_id={self.room.id}&check_in={self.check_in}&check_out={self.check_out}&adults=2&children=1&rooms=1'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get('available'))
        self.assertEqual(response.data.get('requested_rooms'), 1)
        self.assertEqual(response.data.get('requested_adults'), 2)

    # --- 3. BOOKING CREATION API OCCUPANCY VALIDATION ---
    def test_booking_creation_one_person_two_rooms_rejected(self):
        """Booking creation API returns 400 when 1 person tries to book 2 rooms."""
        self.client.force_authenticate(user=self.customer)
        payload = {
            'hotel': self.hotel.id,
            'room': self.room.id,
            'check_in': self.check_in,
            'check_out': self.check_out,
            'adults': 1,
            'children': 0,
            'number_of_rooms': 2,
            'guest_name': 'Test Customer',
            'guest_email': 'customer_occ@example.com',
            'guest_phone': '9876543211',
            'meal_plan': 'ROOM_ONLY'
        }
        response = self.client.post('/api/bookings/', data=payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('cannot book 2 room(s)', str(response.data))

    def test_booking_creation_number_of_guests_less_than_rooms_rejected(self):
        """Booking creation API returns 400 when number_of_guests=1 and number_of_rooms=2."""
        self.client.force_authenticate(user=self.customer)
        payload = {
            'hotel': self.hotel.id,
            'room': self.room.id,
            'check_in': self.check_in,
            'check_out': self.check_out,
            'number_of_guests': 1,
            'number_of_rooms': 2,
            'guest_name': 'Test Customer',
            'guest_email': 'customer_occ@example.com',
            'guest_phone': '9876543211',
            'meal_plan': 'ROOM_ONLY'
        }
        response = self.client.post('/api/bookings/', data=payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('cannot book 2 room(s)', str(response.data))

    def test_booking_creation_valid_occupancy_succeeds(self):
        """Booking creation succeeds with valid occupancy (2 adults, 2 rooms)."""
        self.client.force_authenticate(user=self.customer)
        payload = {
            'hotel': self.hotel.id,
            'room': self.room.id,
            'check_in': self.check_in,
            'check_out': self.check_out,
            'adults': 2,
            'children': 0,
            'number_of_rooms': 2,
            'guest_name': 'Test Customer',
            'guest_email': 'customer_occ@example.com',
            'guest_phone': '9876543211',
            'meal_plan': 'ROOM_ONLY'
        }
        response = self.client.post('/api/bookings/', data=payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['number_of_rooms'], 2)
        self.assertEqual(response.data['number_of_guests'], 2)
