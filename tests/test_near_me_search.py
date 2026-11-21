from decimal import Decimal
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from hotels.models import Hotel, Country, State, City, Area
from rooms.models import Room
from reviews.models import Review
from bookings.models import Booking

User = get_user_model()

class HotelNearMeSearchTests(TestCase):
    """
    Test suite for 'Near Me' hotel search capability.
    Tests:
    1. Dedicated GET /api/hotels/near-me/ with coordinates (sorted nearest first).
    2. Missing coordinates returns HTTP 400 LOCATION_REQUIRED.
    3. City fallback when coordinates not passed in near-me request.
    4. Coordinate validation (out-of-bounds).
    5. Smart auto-expansion when 0 hotels found in initial narrow radius.
    6. Search API with near_me=true query parameter.
    7. Search API with q='near me' / 'hotels near me' text query intent detection.
    8. Search API with q='near me' without coordinates returns 400 LOCATION_REQUIRED.
    9. Near me combined with budget and rating filters.
    10. GET /api/hotels/nearby/ alias endpoint.
    """

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username='nearme_owner_1',
            email='nearme_owner_1@example.com',
            password='Password123!',
            role='HOTEL_OWNER'
        )
        cls.customer = User.objects.create_user(
            username='nearme_cust_1',
            email='nearme_cust_1@example.com',
            password='Password123!',
            role='CUSTOMER'
        )

        cls.country = Country.objects.create(name='India', code='IN')
        cls.state_ka = State.objects.create(name='Karnataka', code='KA', country=cls.country)
        cls.state_ga = State.objects.create(name='Goa', code='GA', country=cls.country)

        cls.city_blr = City.objects.create(name='Bengaluru', state=cls.state_ka, latitude=12.9716, longitude=77.5946)
        cls.city_goa = City.objects.create(name='Goa', state=cls.state_ga, latitude=15.2993, longitude=74.1240)

        cls.area_mg = Area.objects.create(name='MG Road', city=cls.city_blr, zip_code='560001', latitude=12.9716, longitude=77.5946)
        cls.area_ind = Area.objects.create(name='Indiranagar', city=cls.city_blr, zip_code='560038', latitude=12.9784, longitude=77.6408)
        cls.area_wfd = Area.objects.create(name='Whitefield', city=cls.city_blr, zip_code='560066', latitude=12.9698, longitude=77.7499)

        # Hotel 1: MG Road (coords: 12.9716, 77.5946)
        cls.hotel_mg = Hotel.objects.create(
            owner=cls.owner,
            name='The Oberoi MG Road',
            property_type='LUXURY_HOTEL',
            address='37-39 MG Road',
            city_rel=cls.city_blr,
            state_rel=cls.state_ka,
            country_rel=cls.country,
            area_rel=cls.area_mg,
            latitude=12.9716,
            longitude=77.5946,
            star_rating=5,
            is_approved=True,
            status=Hotel.STATUS_APPROVED
        )
        cls.room_mg = Room.objects.create(
            hotel=cls.hotel_mg,
            title='Deluxe Premier',
            room_type='DELUXE',
            price_per_night=Decimal('6000.00'),
            capacity_adults=2,
            total_rooms=5
        )

        # Hotel 2: Indiranagar (~5.06 km from MG Road)
        cls.hotel_ind = Hotel.objects.create(
            owner=cls.owner,
            name='Indiranagar Boutique Stay',
            property_type='HOTEL',
            address='100 Feet Road',
            city_rel=cls.city_blr,
            state_rel=cls.state_ka,
            country_rel=cls.country,
            area_rel=cls.area_ind,
            latitude=12.9784,
            longitude=77.6408,
            star_rating=4,
            is_approved=True,
            status=Hotel.STATUS_APPROVED
        )
        cls.room_ind = Room.objects.create(
            hotel=cls.hotel_ind,
            title='Executive Room',
            room_type='STANDARD',
            price_per_night=Decimal('3500.00'),
            capacity_adults=2,
            total_rooms=4
        )

        # Hotel 3: Whitefield (~17 km from MG Road)
        cls.hotel_wfd = Hotel.objects.create(
            owner=cls.owner,
            name='Whitefield Tech Park Suites',
            property_type='APARTHOTEL',
            address='ITPL Main Road',
            city_rel=cls.city_blr,
            state_rel=cls.state_ka,
            country_rel=cls.country,
            area_rel=cls.area_wfd,
            latitude=12.9698,
            longitude=77.7499,
            star_rating=3,
            is_approved=True,
            status=Hotel.STATUS_APPROVED
        )
        cls.room_wfd = Room.objects.create(
            hotel=cls.hotel_wfd,
            title='Studio Apartment',
            room_type='STANDARD',
            price_per_night=Decimal('2500.00'),
            capacity_adults=2,
            total_rooms=3
        )

        # Hotel 4: Goa (Distant, ~550 km away)
        cls.hotel_goa = Hotel.objects.create(
            owner=cls.owner,
            name='Goa Sun & Sands Resort',
            property_type='RESORT',
            address='Candolim Beach Road',
            city_rel=cls.city_goa,
            state_rel=cls.state_ga,
            country_rel=cls.country,
            latitude=15.5186,
            longitude=73.7628,
            star_rating=4,
            is_approved=True,
            status=Hotel.STATUS_APPROVED
        )
        cls.room_goa = Room.objects.create(
            hotel=cls.hotel_goa,
            title='Beach Villa',
            room_type='VILLA',
            price_per_night=Decimal('8000.00'),
            capacity_adults=2,
            total_rooms=2
        )

        # Visible reviews
        past_cin = timezone.now().date() - timedelta(days=10)
        past_cout = timezone.now().date() - timedelta(days=8)

        bk_mg = Booking.objects.create(
            booking_id='BKG-NM-MG-1',
            customer=cls.customer,
            hotel=cls.hotel_mg,
            room=cls.room_mg,
            check_in=past_cin,
            check_out=past_cout,
            number_of_guests=2,
            number_of_rooms=1,
            price_per_night=Decimal('6000.00'),
            number_of_nights=2,
            subtotal=Decimal('12000.00'),
            total_amount=Decimal('12000.00'),
            booking_status=Booking.STATUS_COMPLETED,
            payment_status=Booking.PAYMENT_PAID,
            guest_name='Near Me Guest',
            guest_email='guest@example.com',
            guest_phone='+919876543210'
        )
        Review.objects.create(
            booking=bk_mg,
            hotel=cls.hotel_mg,
            user=cls.customer,
            rating=5,
            comment='Superb near me location!',
            status='VISIBLE'
        )

    def setUp(self):
        self.client = APIClient()

    def test_01_near_me_endpoint_with_coordinates(self):
        """1. GET /api/hotels/near-me/ with coordinates returns nearest hotels with distance_km."""
        response = self.client.get('/api/hotels/near-me/?latitude=12.9716&longitude=77.5946&radius_km=10')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertIn('message', response.data)
        self.assertIn('user_location', response.data)
        self.assertEqual(response.data['user_location']['latitude'], 12.9716)
        self.assertEqual(response.data['user_location']['longitude'], 77.5946)
        self.assertEqual(response.data['search_radius_km'], 10.0)

        results = response.data['data']['results']
        self.assertGreaterEqual(len(results), 2)
        # Verify nearest first order: The Oberoi MG Road (0.0 km) then Indiranagar (~5.06 km)
        self.assertEqual(results[0]['id'], self.hotel_mg.id)
        self.assertAlmostEqual(results[0]['distance_km'], 0.0, delta=0.1)
        self.assertEqual(results[1]['id'], self.hotel_ind.id)
        self.assertAlmostEqual(results[1]['distance_km'], 5.06, delta=0.5)

        # Goa hotel must NOT be present
        result_ids = [h['id'] for h in results]
        self.assertNotIn(self.hotel_goa.id, result_ids)

    def test_02_near_me_endpoint_without_coordinates_fails(self):
        """2. GET /api/hotels/near-me/ without coordinates and without city returns 400 LOCATION_REQUIRED."""
        response = self.client.get('/api/hotels/near-me/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])
        self.assertEqual(response.data['error']['code'], 'LOCATION_REQUIRED')

    def test_03_near_me_endpoint_city_fallback(self):
        """3. GET /api/hotels/near-me/?city=Bengaluru without lat/long resolves city coordinates."""
        response = self.client.get('/api/hotels/near-me/?city=Bengaluru')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertIsNotNone(response.data.get('user_location'))
        self.assertEqual(response.data['user_location']['latitude'], 12.9716)
        results = response.data['data']['results']
        self.assertGreater(len(results), 0)

    def test_04_near_me_invalid_coordinates_validation(self):
        """4. GET /api/hotels/near-me/ with out-of-bounds coordinates returns 400 COORDINATE_OUT_OF_BOUNDS."""
        response = self.client.get('/api/hotels/near-me/?latitude=95.0&longitude=77.5946')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'COORDINATE_OUT_OF_BOUNDS')

    def test_05_near_me_auto_expansion(self):
        """5. If 0 hotels within narrow radius (e.g. 2km), auto-expands to find nearby hotels."""
        # Location in Koramangala (12.9352, 77.6245): MG Road is ~5.5 km away, Indiranagar ~6 km away
        # With radius_km=2 and auto_expand=true, initial 2km has 0 hotels, so it expands up to 25km!
        response = self.client.get('/api/hotels/near-me/?latitude=12.9352&longitude=77.6245&radius_km=2&auto_expand=true')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        results = response.data['data']['results']
        self.assertGreater(len(results), 0)
        # Search radius should have expanded
        self.assertGreater(response.data['search_radius_km'], 2.0)
        self.assertIn("Showing", response.data['message'])

    def test_06_hotel_search_api_near_me_param(self):
        """6. GET /api/hotels/search/?near_me=true activates near me search and sorts nearest first."""
        response = self.client.get('/api/hotels/search/?near_me=true&latitude=12.9716&longitude=77.5946')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        results = response.data['data']['results']
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]['id'], self.hotel_mg.id)

    def test_07_hotel_search_api_text_query_near_me(self):
        """7. GET /api/hotels/search/?q=hotels near me with coordinates triggers near me search."""
        response = self.client.get('/api/hotels/search/?q=hotels%20near%20me&latitude=12.9716&longitude=77.5946')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        results = response.data['data']['results']
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]['id'], self.hotel_mg.id)

    def test_08_hotel_search_api_text_query_near_me_missing_coords(self):
        """8. GET /api/hotels/search/?q=near me without coordinates returns 400 LOCATION_REQUIRED."""
        response = self.client.get('/api/hotels/search/?q=near%20me')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'LOCATION_REQUIRED')

    def test_09_near_me_with_filters_budget_and_rating(self):
        """9. Near me search respects budget (min_price/max_price) and rating filters."""
        # MG Road price is 6000, rating is 5.0. Indiranagar price is 3500.
        # Filter min_price=5000 & min_rating=4.5 -> Only MG Road should qualify.
        response = self.client.get('/api/hotels/near-me/?latitude=12.9716&longitude=77.5946&min_price=5000&min_rating=4.5')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['data']['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], self.hotel_mg.id)

    def test_10_nearby_alias_endpoint(self):
        """10. GET /api/hotels/nearby/ alias functions identically to /api/hotels/near-me/."""
        res_near_me = self.client.get('/api/hotels/near-me/?latitude=12.9716&longitude=77.5946')
        res_nearby = self.client.get('/api/hotels/nearby/?latitude=12.9716&longitude=77.5946')
        self.assertEqual(res_nearby.status_code, status.HTTP_200_OK)
        self.assertEqual(res_near_me.data['data']['count'], res_nearby.data['data']['count'])
