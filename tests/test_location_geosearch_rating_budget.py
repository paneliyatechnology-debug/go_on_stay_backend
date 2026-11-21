from decimal import Decimal
from datetime import timedelta
import math
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from hotels.models import Hotel, HotelImage, Amenity, Country, State, City, Area
from rooms.models import Room
from reviews.models import Review
from bookings.models import Booking

User = get_user_model()

class LocationGeosearchRatingBudgetTests(TestCase):
    """
    Comprehensive test suite for Location Hierarchy, Geosearch,
    Rating Filters, Budget & Real Inventory Availability, Sorting, and Pagination.
    Total: 20 Test Cases matching Section 10.
    """

    @classmethod
    def setUpTestData(cls):
        # 1. Owner & Users
        cls.owner = User.objects.create_user(
            username='search_owner_1',
            email='search_owner_1@example.com',
            password='Password123!',
            role='HOTEL_OWNER'
        )
        cls.customer = User.objects.create_user(
            username='search_cust_1',
            email='search_cust_1@example.com',
            password='Password123!',
            role='CUSTOMER'
        )

        # 2. Location Hierarchy
        cls.country_in = Country.objects.create(name='India', code='IN')
        
        # States
        cls.state_ka = State.objects.create(name='Karnataka', code='KA', country=cls.country_in)
        cls.state_rj = State.objects.create(name='Rajasthan', code='RJ', country=cls.country_in)
        cls.state_ga = State.objects.create(name='Goa', code='GA', country=cls.country_in)

        # Cities
        cls.city_blr = City.objects.create(name='Bengaluru', state=cls.state_ka, latitude=12.9716, longitude=77.5946)
        cls.city_mys = City.objects.create(name='Mysuru', state=cls.state_ka, latitude=12.2958, longitude=76.6394)
        cls.city_jpr = City.objects.create(name='Jaipur', state=cls.state_rj, latitude=26.9124, longitude=75.7873)
        cls.city_goa = City.objects.create(name='North Goa', state=cls.state_ga, latitude=15.5494, longitude=73.7535)

        # Areas
        cls.area_mg = Area.objects.create(name='MG Road', city=cls.city_blr, pincode='560001', latitude=12.9716, longitude=77.5946)
        cls.area_ind = Area.objects.create(name='Indiranagar', city=cls.city_blr, pincode='560038', latitude=12.9784, longitude=77.6408)
        cls.area_wfd = Area.objects.create(name='Whitefield', city=cls.city_blr, pincode='560066', latitude=12.9698, longitude=77.7499)
        cls.area_cspan = Area.objects.create(name='Civil Lines', city=cls.city_jpr, pincode='302006', latitude=26.9068, longitude=75.7878)
        cls.area_cal = Area.objects.create(name='Calangute', city=cls.city_goa, pincode='403516', latitude=15.5439, longitude=73.7553)

        # 3. Hotels
        # Hotel 1: Bengaluru MG Road (Premium, High Rating)
        cls.hotel_blr_mg = Hotel.objects.create(
            owner=cls.owner,
            name='The Oberoi MG Road',
            property_type='LUXURY_HOTEL',
            address='37-39, MG Road',
            city_rel=cls.city_blr,
            state_rel=cls.state_ka,
            country_rel=cls.country_in,
            area_rel=cls.area_mg,
            city='Bengaluru',
            state='Karnataka',
            country='India',
            area='MG Road',
            zip_code='560001',
            latitude=12.9716,
            longitude=77.5946,
            star_rating=5,
            is_approved=True,
            status=Hotel.STATUS_APPROVED
        )
        cls.room_blr_mg = Room.objects.create(
            hotel=cls.hotel_blr_mg,
            title='Deluxe Premier Room',
            room_type='DELUXE',
            price_per_night=Decimal('6000.00'),
            weekend_price=Decimal('7500.00'),
            capacity_adults=2,
            capacity_children=1,
            total_rooms=5
        )

        # Hotel 2: Bengaluru Indiranagar (~5km from MG Road, Budget/Mid, Moderate Rating)
        cls.hotel_blr_ind = Hotel.objects.create(
            owner=cls.owner,
            name='Indiranagar Boutique Stay',
            property_type='HOTEL',
            address='100 Feet Road, Indiranagar',
            city_rel=cls.city_blr,
            state_rel=cls.state_ka,
            country_rel=cls.country_in,
            area_rel=cls.area_ind,
            city='Bengaluru',
            state='Karnataka',
            country='India',
            area='Indiranagar',
            zip_code='560038',
            latitude=12.9784,
            longitude=77.6408,
            star_rating=4,
            is_approved=True,
            status=Hotel.STATUS_APPROVED
        )
        cls.room_blr_ind = Room.objects.create(
            hotel=cls.hotel_blr_ind,
            title='Executive Standard',
            room_type='STANDARD',
            price_per_night=Decimal('3000.00'),
            capacity_adults=2,
            capacity_children=0,
            total_rooms=3
        )
        cls.room_blr_ind_family = Room.objects.create(
            hotel=cls.hotel_blr_ind,
            title='Family Suite Large',
            room_type='FAMILY',
            price_per_night=Decimal('5000.00'),
            capacity_adults=4,
            capacity_children=2,
            total_rooms=2
        )

        # Hotel 3: Bengaluru Whitefield (~17km from MG Road, Unrated)
        cls.hotel_blr_wfd = Hotel.objects.create(
            owner=cls.owner,
            name='Whitefield Tech Park Suites',
            property_type='APARTHOTEL',
            address='ITPL Main Road, Whitefield',
            city_rel=cls.city_blr,
            state_rel=cls.state_ka,
            country_rel=cls.country_in,
            area_rel=cls.area_wfd,
            city='Bengaluru',
            state='Karnataka',
            country='India',
            area='Whitefield',
            zip_code='560066',
            latitude=12.9698,
            longitude=77.7499,
            star_rating=3,
            is_approved=True,
            status=Hotel.STATUS_APPROVED
        )
        cls.room_blr_wfd = Room.objects.create(
            hotel=cls.hotel_blr_wfd,
            title='Studio Apartment',
            room_type='STANDARD',
            price_per_night=Decimal('2500.00'),
            capacity_adults=2,
            capacity_children=1,
            total_rooms=4
        )

        # Hotel 4: Jaipur Palace (Far from Bengaluru, Rajasthan)
        cls.hotel_jpr = Hotel.objects.create(
            owner=cls.owner,
            name='Jaipur Heritage Palace',
            property_type='PALACE',
            address='Civil Lines',
            city_rel=cls.city_jpr,
            state_rel=cls.state_rj,
            country_rel=cls.country_in,
            area_rel=cls.area_cspan,
            city='Jaipur',
            state='Rajasthan',
            country='India',
            area='Civil Lines',
            zip_code='302006',
            latitude=26.9068,
            longitude=75.7878,
            star_rating=5,
            is_approved=True,
            status=Hotel.STATUS_APPROVED
        )
        cls.room_jpr = Room.objects.create(
            hotel=cls.hotel_jpr,
            title='Royal Heritage Suite',
            room_type='EXECUTIVE',
            price_per_night=Decimal('9000.00'),
            capacity_adults=3,
            capacity_children=2,
            total_rooms=3
        )

        # 4. Past Bookings for Reviews
        past_checkin = timezone.now().date() - timedelta(days=10)
        past_checkout = timezone.now().date() - timedelta(days=8)

        def make_test_booking(hotel, room, b_id):
            return Booking.objects.create(
                booking_id=b_id,
                customer=cls.customer,
                hotel=hotel,
                room=room,
                check_in=past_checkin,
                check_out=past_checkout,
                number_of_guests=2,
                number_of_rooms=1,
                price_per_night=room.price_per_night,
                number_of_nights=2,
                subtotal=room.price_per_night * 2,
                total_amount=room.price_per_night * 2,
                booking_status=Booking.STATUS_COMPLETED,
                payment_status=Booking.PAYMENT_PAID,
                guest_name='Test Customer',
                guest_email='cust@example.com',
                guest_phone='+919876543210'
            )

        bk_mg_1 = make_test_booking(cls.hotel_blr_mg, cls.room_blr_mg, 'BKG-REV-MG-1')
        bk_mg_2 = make_test_booking(cls.hotel_blr_mg, cls.room_blr_mg, 'BKG-REV-MG-2')
        bk_ind_1 = make_test_booking(cls.hotel_blr_ind, cls.room_blr_ind, 'BKG-REV-IND-1')
        bk_jpr_1 = make_test_booking(cls.hotel_jpr, cls.room_jpr, 'BKG-REV-JPR-1')

        # 5. Visible Reviews
        # Hotel 1 (MG Road): 5.0 and 4.0 -> Avg 4.5
        Review.objects.create(
            booking=bk_mg_1,
            hotel=cls.hotel_blr_mg,
            user=cls.customer,
            rating=5,
            comment='Impeccable service and luxury.',
            status='VISIBLE'
        )
        Review.objects.create(
            booking=bk_mg_2,
            hotel=cls.hotel_blr_mg,
            user=cls.customer,
            rating=4,
            comment='Great experience overall.',
            status='VISIBLE'
        )

        # Hotel 2 (Indiranagar): 3.0 -> Avg 3.0
        Review.objects.create(
            booking=bk_ind_1,
            hotel=cls.hotel_blr_ind,
            user=cls.customer,
            rating=3,
            comment='Decent location, basic amenities.',
            status='VISIBLE'
        )

        # Hotel 4 (Jaipur): 5.0 -> Avg 5.0
        Review.objects.create(
            booking=bk_jpr_1,
            hotel=cls.hotel_jpr,
            user=cls.customer,
            rating=5,
            comment='Magical royal experience.',
            status='VISIBLE'
        )

    def setUp(self):
        self.client = APIClient()

    # =========================================================================
    # 1. Location Hierarchy Models and Integrity
    # =========================================================================
    def test_location_hierarchy_models_and_relationships(self):
        """1. Verify Country -> State -> City -> Area foreign keys and hotel relationships."""
        self.assertEqual(self.state_ka.country, self.country_in)
        self.assertEqual(self.city_blr.state, self.state_ka)
        self.assertEqual(self.area_mg.city, self.city_blr)

        # Verify Hotel relationship sync
        self.assertEqual(self.hotel_blr_mg.country_rel, self.country_in)
        self.assertEqual(self.hotel_blr_mg.state_rel, self.state_ka)
        self.assertEqual(self.hotel_blr_mg.city_rel, self.city_blr)
        self.assertEqual(self.hotel_blr_mg.area_rel, self.area_mg)

        # Verify Hotel string sync on save
        hotel = Hotel.objects.create(
            owner=self.owner,
            name='Test Sync Hotel',
            city_rel=self.city_mys,
            state_rel=self.state_ka,
            country_rel=self.country_in,
            star_rating=3
        )
        self.assertEqual(hotel.city, 'Mysuru')
        self.assertEqual(hotel.state, 'Karnataka')
        self.assertEqual(hotel.country, 'India')

    # =========================================================================
    # 2. Cascading Locations APIs
    # =========================================================================
    def test_cascading_locations_api_countries(self):
        """2. GET /api/locations/countries/ returns list of countries."""
        response = self.client.get('/api/locations/countries/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        country_names = [c['name'] for c in response.data['data']]
        self.assertIn('India', country_names)

    def test_cascading_locations_api_states(self):
        """3. GET /api/locations/states/?country_id= returns states filtered by country."""
        response = self.client.get(f'/api/locations/states/?country_id={self.country_in.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        state_names = [s['name'] for s in response.data['data']]
        self.assertIn('Karnataka', state_names)
        self.assertIn('Rajasthan', state_names)

    def test_cascading_locations_api_cities(self):
        """4. GET /api/locations/cities/?state_id= returns cities filtered by state."""
        response = self.client.get(f'/api/locations/cities/?state_id={self.state_ka.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        city_names = [c['name'] for c in response.data['data']]
        self.assertIn('Bengaluru', city_names)
        self.assertIn('Mysuru', city_names)
        self.assertNotIn('Jaipur', city_names)

    def test_cascading_locations_api_areas(self):
        """5. GET /api/locations/areas/?city_id= returns areas filtered by city."""
        response = self.client.get(f'/api/locations/areas/?city_id={self.city_blr.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        area_names = [a['name'] for a in response.data['data']]
        self.assertIn('MG Road', area_names)
        self.assertIn('Indiranagar', area_names)
        self.assertNotIn('Civil Lines', area_names)

    def test_location_search_autocomplete(self):
        """6. GET /api/locations/search/?q= returns matching entities with display names."""
        response = self.client.get('/api/locations/search/?q=Bengaluru')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        results = response.data['data']
        self.assertGreater(len(results), 0)
        blr_match = next((item for item in results if item['name'] == 'Bengaluru'), None)
        self.assertIsNotNone(blr_match)
        self.assertEqual(blr_match['type'], 'city')
        self.assertIn('Karnataka', blr_match['display_name'])

    # =========================================================================
    # 3. Search with Location Hierarchy & Consistency Validation
    # =========================================================================
    def test_search_by_valid_hierarchy_ids(self):
        """7. Search with valid state_id and city_id returns matching hotels."""
        response = self.client.get(f'/api/hotels/search/?city_id={self.city_blr.id}&state_id={self.state_ka.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['data']['results']
        hotel_ids = [h['id'] for h in results]
        self.assertIn(self.hotel_blr_mg.id, hotel_ids)
        self.assertIn(self.hotel_blr_ind.id, hotel_ids)
        self.assertNotIn(self.hotel_jpr.id, hotel_ids)

    def test_search_hierarchy_mismatch_validation(self):
        """8. Search with mismatched city_id and area_id returns 400 Bad Request."""
        # area_cal is in North Goa, not Bengaluru
        response = self.client.get(f'/api/hotels/search/?city_id={self.city_blr.id}&area_id={self.area_cal.id}')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])
        self.assertEqual(response.data['error']['code'], 'INVALID_LOCATION_HIERARCHY')

    # =========================================================================
    # 4. Geosearch & Proximity Filtering
    # =========================================================================
    def test_geosearch_within_radius(self):
        """9. Geosearch at MG Road coordinates within 6km radius includes MG Road & Indiranagar, returns distance_km."""
        # MG Road coords: 12.9716, 77.5946; Indiranagar is ~5.06 km away
        response = self.client.get('/api/hotels/search/?latitude=12.9716&longitude=77.5946&radius_km=6')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['data']['results']
        hotel_ids = [h['id'] for h in results]
        self.assertIn(self.hotel_blr_mg.id, hotel_ids)
        self.assertIn(self.hotel_blr_ind.id, hotel_ids)
        # Whitefield is ~17km away, must NOT be included in 6km radius
        self.assertNotIn(self.hotel_blr_wfd.id, hotel_ids)

        # Check distance_km presence and accuracy
        mg_result = next(h for h in results if h['id'] == self.hotel_blr_mg.id)
        self.assertIsNotNone(mg_result['distance_km'])
        self.assertAlmostEqual(mg_result['distance_km'], 0.0, delta=0.1)

        ind_result = next(h for h in results if h['id'] == self.hotel_blr_ind.id)
        self.assertIsNotNone(ind_result['distance_km'])
        self.assertAlmostEqual(ind_result['distance_km'], 5.06, delta=0.5)

    def test_geosearch_outside_radius_excluded(self):
        """10. Hotel in Jaipur is excluded when searching Bengaluru coordinates."""
        response = self.client.get('/api/hotels/search/?latitude=12.9716&longitude=77.5946&radius_km=25')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['data']['results']
        hotel_ids = [h['id'] for h in results]
        self.assertNotIn(self.hotel_jpr.id, hotel_ids)

    def test_geosearch_invalid_coordinates_validation(self):
        """11. Lat < -90 or > 90, Lng < -180 or > 180 returns 400 Bad Request."""
        # Invalid Latitude 95.0
        res1 = self.client.get('/api/hotels/search/?latitude=95.0&longitude=77.5946')
        self.assertEqual(res1.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res1.data['error']['code'], 'COORDINATE_OUT_OF_BOUNDS')

        # Invalid Longitude -190.0
        res2 = self.client.get('/api/hotels/search/?latitude=12.9716&longitude=-190.0')
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res2.data['error']['code'], 'COORDINATE_OUT_OF_BOUNDS')

    def test_sort_nearest_first_without_coordinates_fails(self):
        """12. sort_by=nearest_first without coordinates returns 400 Bad Request."""
        response = self.client.get('/api/hotels/search/?sort_by=nearest_first')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'MISSING_COORDINATES')

    # =========================================================================
    # 5. Review-Based Rating Filters
    # =========================================================================
    def test_rating_filter_min_and_max(self):
        """13. Filter by min_rating and max_rating only returns hotels with matching visible review averages."""
        # Hotel 1 (MG Road): 4.5; Hotel 2 (Indiranagar): 3.0; Hotel 4 (Jaipur): 5.0
        response = self.client.get('/api/hotels/search/?min_rating=4.0&max_rating=4.9')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['data']['results']
        hotel_ids = [h['id'] for h in results]
        self.assertIn(self.hotel_blr_mg.id, hotel_ids)
        self.assertNotIn(self.hotel_blr_ind.id, hotel_ids) # 3.0 < 4.0
        self.assertNotIn(self.hotel_jpr.id, hotel_ids)     # 5.0 > 4.9

    def test_rating_filter_exclude_unrated_by_default(self):
        """14. Unrated hotels are excluded by default when min_rating is set, unless include_unrated=true."""
        # Hotel 3 (Whitefield) has 0 reviews
        res_default = self.client.get(f'/api/hotels/search/?city_id={self.city_blr.id}&min_rating=3.0')
        self.assertEqual(res_default.status_code, status.HTTP_200_OK)
        ids_default = [h['id'] for h in res_default.data['data']['results']]
        self.assertNotIn(self.hotel_blr_wfd.id, ids_default)

        # With include_unrated=true, Hotel 3 is included
        res_with_unrated = self.client.get(f'/api/hotels/search/?city_id={self.city_blr.id}&min_rating=3.0&include_unrated=true')
        self.assertEqual(res_with_unrated.status_code, status.HTTP_200_OK)
        ids_with_unrated = [h['id'] for h in res_with_unrated.data['data']['results']]
        self.assertIn(self.hotel_blr_wfd.id, ids_with_unrated)

    def test_rating_filter_invalid_range_validation(self):
        """15. min_rating > max_rating returns 400 Bad Request."""
        response = self.client.get('/api/hotels/search/?min_rating=4.5&max_rating=3.0')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'INVALID_RATING_RANGE')

    # =========================================================================
    # 6. Budget & Price Filters
    # =========================================================================
    def test_budget_filter_min_and_max_price(self):
        """16. Filter by min_price and max_price filters by starting price."""
        # Indiranagar starting 3000, MG Road starting 6000, Jaipur starting 9000
        response = self.client.get('/api/hotels/search/?min_price=2500&max_price=4000')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['data']['results']
        hotel_ids = [h['id'] for h in results]
        self.assertIn(self.hotel_blr_ind.id, hotel_ids)
        self.assertIn(self.hotel_blr_wfd.id, hotel_ids)
        self.assertNotIn(self.hotel_blr_mg.id, hotel_ids)
        self.assertNotIn(self.hotel_jpr.id, hotel_ids)

    def test_budget_filter_date_pricing_and_availability(self):
        """17. Dynamic date pricing (weekend rate) updates starting price and respects budget range."""
        # Find next Friday & Saturday for weekend pricing test
        today = timezone.now().date()
        days_ahead = (4 - today.weekday()) % 7 # Next Friday
        if days_ahead == 0:
            days_ahead = 7
        next_friday = today + timedelta(days=days_ahead)
        next_sunday = next_friday + timedelta(days=2)

        # MG Road base is 6000, weekend is 7500. Friday-Sunday is 2 weekend nights => avg 7500
        cin_str = next_friday.strftime('%Y-%m-%d')
        cout_str = next_sunday.strftime('%Y-%m-%d')

        # Filter max_price=7000: base price (6000) would qualify, but weekend price (7500) must EXCLUDE it!
        res_excl = self.client.get(f'/api/hotels/search/?city_id={self.city_blr.id}&check_in={cin_str}&check_out={cout_str}&max_price=7000')
        self.assertEqual(res_excl.status_code, status.HTTP_200_OK)
        ids_excl = [h['id'] for h in res_excl.data['data']['results']]
        self.assertNotIn(self.hotel_blr_mg.id, ids_excl)

        # Filter min_price=7200 & max_price=8000: weekend price (7500) must INCLUDE it!
        res_incl = self.client.get(f'/api/hotels/search/?city_id={self.city_blr.id}&check_in={cin_str}&check_out={cout_str}&min_price=7200&max_price=8000')
        self.assertEqual(res_incl.status_code, status.HTTP_200_OK)
        ids_incl = [h['id'] for h in res_incl.data['data']['results']]
        self.assertIn(self.hotel_blr_mg.id, ids_incl)
        mg_hotel = next(h for h in res_incl.data['data']['results'] if h['id'] == self.hotel_blr_mg.id)
        self.assertEqual(mg_hotel['starting_price'], 7500.00)

    def test_budget_filter_guest_and_room_capacity(self):
        """18. Guests requirement filters out hotels that have insufficient capacity per room."""
        # Search for 4 guests in 1 room.
        # Hotel 1 (MG Road) Deluxe room capacity is 2 adults + 1 child = 3 -> Excluded!
        # Hotel 2 (Indiranagar) Family Suite has capacity 4 adults + 2 children = 6 -> Included!
        response = self.client.get(f'/api/hotels/search/?city_id={self.city_blr.id}&guests=4&rooms=1')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['data']['results']
        hotel_ids = [h['id'] for h in results]
        self.assertNotIn(self.hotel_blr_mg.id, hotel_ids)
        self.assertIn(self.hotel_blr_ind.id, hotel_ids)
        # Starting price must reflect Family Suite (5000), not the 2-person standard room (3000)
        ind_hotel = next(h for h in results if h['id'] == self.hotel_blr_ind.id)
        self.assertEqual(ind_hotel['starting_price'], 5000.00)

    # =========================================================================
    # 7. Combined Search Filters & Sorting Contracts
    # =========================================================================
    def test_combined_search_filters(self):
        """19. Combined search with city, geosearch, rating, budget, and dates all working simultaneously."""
        today = timezone.now().date() + timedelta(days=10)
        cin = today.strftime('%Y-%m-%d')
        cout = (today + timedelta(days=2)).strftime('%Y-%m-%d')

        url = (
            f"/api/hotels/search/?city_id={self.city_blr.id}"
            f"&latitude=12.9716&longitude=77.5946&radius_km=10"
            f"&min_rating=4.0&min_price=5000&max_price=9000"
            f"&check_in={cin}&check_out={cout}&guests=2&rooms=1"
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['data']['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], self.hotel_blr_mg.id)
        self.assertIsNotNone(results[0]['distance_km'])
        self.assertEqual(results[0]['rating'], 4.5)

    def test_sorting_and_pagination_contracts(self):
        """20. Sorting (price_low_to_high, price_high_to_low, rating_high_to_low, nearest_first) and Section 7 pagination."""
        # 1. Price low to high
        res_price_asc = self.client.get('/api/hotels/search/?sort_by=price_low_to_high')
        self.assertEqual(res_price_asc.status_code, status.HTTP_200_OK)
        prices = [h['starting_price'] for h in res_price_asc.data['data']['results']]
        self.assertEqual(prices, sorted(prices))

        # 2. Price high to low
        res_price_desc = self.client.get('/api/hotels/search/?sort_by=price_high_to_low')
        self.assertEqual(res_price_desc.status_code, status.HTTP_200_OK)
        prices_desc = [h['starting_price'] for h in res_price_desc.data['data']['results']]
        self.assertEqual(prices_desc, sorted(prices_desc, reverse=True))

        # 3. Rating high to low
        res_rating = self.client.get('/api/hotels/search/?sort_by=rating_high_to_low')
        self.assertEqual(res_rating.status_code, status.HTTP_200_OK)
        ratings = [h['rating'] or 0.0 for h in res_rating.data['data']['results']]
        self.assertEqual(ratings, sorted(ratings, reverse=True))

        # 4. Nearest first
        res_nearest = self.client.get('/api/hotels/search/?latitude=12.9716&longitude=77.5946&sort_by=nearest_first&radius_km=25')
        self.assertEqual(res_nearest.status_code, status.HTTP_200_OK)
        distances = [h['distance_km'] for h in res_nearest.data['data']['results']]
        self.assertEqual(distances, sorted(distances))

        # 5. Section 7 Pagination & Response Contract Verification
        res_page = self.client.get('/api/hotels/search/?page=1&page_size=2')
        self.assertEqual(res_page.status_code, status.HTTP_200_OK)
        self.assertTrue(res_page.data['success'])
        self.assertIn('data', res_page.data)
        data = res_page.data['data']
        self.assertIn('count', data)
        self.assertIn('total_pages', data)
        self.assertIn('current_page', data)
        self.assertIn('results', data)
        self.assertEqual(data['current_page'], 1)
        self.assertEqual(len(data['results']), 2)

        # Inspect first item keys matching Section 7 schema
        first_item = data['results'][0]
        expected_fields = [
            'id', 'name', 'address', 'city', 'state', 'country', 'area',
            'latitude', 'longitude', 'distance_km', 'starting_price',
            'currency', 'rating', 'review_count', 'images', 'amenities',
            'available_rooms_count'
        ]
        for field in expected_fields:
            self.assertIn(field, first_item, f"Section 7 field '{field}' must be present in response result!")
        self.assertEqual(first_item['currency'], 'INR')
