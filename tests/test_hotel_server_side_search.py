from decimal import Decimal
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from hotels.models import Hotel
from rooms.models import Room

User = get_user_model()


class HotelServerSideSearchTests(APITestCase):
    """
    Test suite for GoOnStay Hotel API Server-Side Search Filtering.
    Verifies that GET /api/hotels/?search=... applies strict server-side Django ORM filtering,
    case-insensitivity, partial matching, city filtering, and pagination.
    """

    @classmethod
    def setUpTestData(cls):
        # Create a verified host owner
        cls.owner = User.objects.create_user(
            username='search_test_host',
            email='search_host@goonstay.com',
            password='Password123!',
            role='HOTEL_OWNER',
            is_active=True
        )

        # Create exact test hotels from specification
        cls.oyo_ahmedabad = Hotel.objects.create(
            owner=cls.owner,
            name='OYO Ahmedabad',
            city='Ahmedabad',
            state='Gujarat',
            address='SG Highway, Ahmedabad',
            status=Hotel.STATUS_APPROVED,
            is_approved=True
        )
        Room.objects.create(hotel=cls.oyo_ahmedabad, title='Standard Room', room_type='STANDARD', price_per_night=Decimal('1500.00'), capacity_adults=2)

        cls.taj_mumbai = Hotel.objects.create(
            owner=cls.owner,
            name='Taj Hotel Mumbai',
            city='Mumbai',
            state='Maharashtra',
            address='Colaba, Mumbai',
            status=Hotel.STATUS_APPROVED,
            is_approved=True
        )
        Room.objects.create(hotel=cls.taj_mumbai, title='Luxury Suite', room_type='SUITE', price_per_night=Decimal('12000.00'), capacity_adults=2)

        cls.oyo_rajkot = Hotel.objects.create(
            owner=cls.owner,
            name='OYO Rajkot',
            city='Rajkot',
            state='Gujarat',
            address='Kalawad Road, Rajkot',
            status=Hotel.STATUS_APPROVED,
            is_approved=True
        )
        Room.objects.create(hotel=cls.oyo_rajkot, title='Standard Room', room_type='STANDARD', price_per_night=Decimal('1200.00'), capacity_adults=2)

        cls.hyatt_delhi = Hotel.objects.create(
            owner=cls.owner,
            name='Hyatt Delhi',
            city='Delhi',
            state='Delhi',
            address='Bhikaji Cama Place, Delhi',
            status=Hotel.STATUS_APPROVED,
            is_approved=True
        )
        Room.objects.create(hotel=cls.hyatt_delhi, title='Executive Club', room_type='DELUXE', price_per_night=Decimal('9000.00'), capacity_adults=2)

        cls.oyo_surat = Hotel.objects.create(
            owner=cls.owner,
            name='OYO Surat',
            city='Surat',
            state='Gujarat',
            address='Ring Road, Surat',
            status=Hotel.STATUS_APPROVED,
            is_approved=True
        )
        Room.objects.create(hotel=cls.oyo_surat, title='Budget Room', room_type='STANDARD', price_per_night=Decimal('1100.00'), capacity_adults=2)

    def test_01_search_oyo_uppercase(self):
        """1. Search OYO → only OYO matching records (Do not return Taj Hotel or Hyatt)."""
        response = self.client.get('/api/hotels/?search=OYO')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data.get('results', [])
        hotel_names = [h['name'] for h in results]

        # Must contain all 3 OYO properties
        self.assertIn('OYO Ahmedabad', hotel_names)
        self.assertIn('OYO Rajkot', hotel_names)
        self.assertIn('OYO Surat', hotel_names)

        # Must NOT contain Taj Hotel or Hyatt
        self.assertNotIn('Taj Hotel Mumbai', hotel_names)
        self.assertNotIn('Hyatt Delhi', hotel_names)

        # Exactly 3 results
        self.assertEqual(len(results), 3)
        self.assertEqual(response.data.get('count'), 3)

    def test_02_search_oyo_lowercase_case_insensitive(self):
        """2. Search oyo → same matching results (case-insensitive)."""
        response = self.client.get('/api/hotels/?search=oyo')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data.get('results', [])
        hotel_names = [h['name'] for h in results]

        self.assertIn('OYO Ahmedabad', hotel_names)
        self.assertIn('OYO Rajkot', hotel_names)
        self.assertIn('OYO Surat', hotel_names)
        self.assertNotIn('Taj Hotel Mumbai', hotel_names)
        self.assertNotIn('Hyatt Delhi', hotel_names)
        self.assertEqual(response.data.get('count'), 3)

    def test_03_search_partial_hotel_name(self):
        """3. Search partial hotel name → matching records only."""
        response = self.client.get('/api/hotels/?search=Taj')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data.get('results', [])
        hotel_names = [h['name'] for h in results]

        self.assertIn('Taj Hotel Mumbai', hotel_names)
        self.assertNotIn('Hyatt Delhi', hotel_names)
        self.assertNotIn('OYO Ahmedabad', hotel_names)
        self.assertEqual(response.data.get('count'), 1)

        # Test partial 'Hyatt'
        res_hyatt = self.client.get('/api/hotels/?search=hyatt')
        names_hyatt = [h['name'] for h in res_hyatt.data.get('results', [])]
        self.assertEqual(names_hyatt, ['Hyatt Delhi'])

    def test_04_search_city(self):
        """4. Search city → matching hotels only."""
        response = self.client.get('/api/hotels/?search=Mumbai')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data.get('results', [])
        hotel_names = [h['name'] for h in results]

        self.assertIn('Taj Hotel Mumbai', hotel_names)
        self.assertNotIn('OYO Ahmedabad', hotel_names)
        self.assertNotIn('Hyatt Delhi', hotel_names)
        self.assertEqual(response.data.get('count'), 1)

        # Search city via ?city=Ahmedabad parameter
        res_city_param = self.client.get('/api/hotels/?city=Ahmedabad')
        self.assertEqual(res_city_param.status_code, status.HTTP_200_OK)
        city_names = [h['name'] for h in res_city_param.data.get('results', [])]
        self.assertIn('OYO Ahmedabad', city_names)
        self.assertNotIn('Taj Hotel Mumbai', city_names)

    def test_05_search_nonexistent_name(self):
        """5. Search nonexistent name → empty results."""
        response = self.client.get('/api/hotels/?search=NonExistentHotelXYZ99999')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data.get('results', [])
        self.assertEqual(len(results), 0)
        self.assertEqual(response.data.get('count'), 0)

    def test_06_search_with_pagination(self):
        """6. Search + pagination → correct matching count and results."""
        # Search OYO with page_size=2
        response = self.client.get('/api/hotels/?search=OYO&page=1&page_size=2')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Total matching is 3, but page 1 has exactly 2
        self.assertEqual(response.data.get('count'), 3)
        self.assertEqual(len(response.data.get('results', [])), 2)
        self.assertIsNotNone(response.data.get('next'))
        self.assertIsNone(response.data.get('previous'))

        # Fetch page 2
        res_p2 = self.client.get('/api/hotels/?search=OYO&page=2&page_size=2')
        self.assertEqual(res_p2.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_p2.data.get('results', [])), 1)
        self.assertIsNone(res_p2.data.get('next'))
        self.assertIsNotNone(res_p2.data.get('previous'))

    def test_07_empty_search_returns_normal_complete_listing(self):
        """7. Empty search → normal complete listing with pagination."""
        response = self.client.get('/api/hotels/?search=')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # All 5 test hotels must be present
        results = response.data.get('results', [])
        hotel_names = [h['name'] for h in results]
        self.assertIn('OYO Ahmedabad', hotel_names)
        self.assertIn('Taj Hotel Mumbai', hotel_names)
        self.assertIn('OYO Rajkot', hotel_names)
        self.assertIn('Hyatt Delhi', hotel_names)
        self.assertIn('OYO Surat', hotel_names)
        self.assertGreaterEqual(response.data.get('count'), 5)
