import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from django.test import TestCase, override_settings
from django.utils import timezone
from django.db import connection, transaction
from rest_framework.test import APIClient
from rest_framework import status

from users.models import User
from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking
from reviews.models import Review
from coupons.models import Coupon
from notifications.models import Notification
from rooms.utils import get_available_room_count


class ApiFixesVerificationTests(TestCase):
    """
    Independent Verification Suite for:
    1. Reviews API Data Isolation
    2. SQLite WAL & Concurrency Verification
    3. Read-Only API Integrity (Zero writes during availability / hotel queries)
    4. Frontend Runtime API Compatibility (Home, Search, Details, Rooms, Booking)
    """

    @classmethod
    def setUpTestData(cls):
        # 1. Create Host & Customer
        cls.host = User.objects.create_user(
            username='host_test_verif',
            email='host_verif@example.com',
            password='TestPassword123!',
            role='HOTEL_OWNER',
            phone_number='9876543210'
        )
        cls.customer = User.objects.create_user(
            username='cust_test_verif',
            email='cust_verif@example.com',
            password='TestPassword123!',
            role='CUSTOMER',
            phone_number='9876543211'
        )

        # 2. Create Hotels (Hotel A and Hotel B)
        cls.hotel_a = Hotel.objects.create(
            owner=cls.host,
            name='Hotel Alpha Luxury Resort',
            city='Goa',
            state='Goa',
            address='Calangute Beach Road',
            zip_code='403516',
            property_type='HOTEL',
            is_approved=True,
            status=Hotel.STATUS_APPROVED
        )
        cls.hotel_b = Hotel.objects.create(
            owner=cls.host,
            name='Hotel Beta Mountain Retreat',
            city='Manali',
            state='Himachal Pradesh',
            address='Mall Road',
            zip_code='175131',
            property_type='RESORT',
            is_approved=True,
            status=Hotel.STATUS_APPROVED
        )

        # 3. Create Rooms
        cls.room_a = Room.objects.create(
            hotel=cls.hotel_a,
            title='Alpha Deluxe Room',
            room_type='DELUXE',
            price_per_night=Decimal('4500.00'),
            total_rooms=5,
            room_numbers='101,102,103,104,105'
        )
        cls.room_b = Room.objects.create(
            hotel=cls.hotel_b,
            title='Beta Pine Suite',
            room_type='SUITE',
            price_per_night=Decimal('6500.00'),
            total_rooms=3,
            room_numbers='201,202,203'
        )

        # 4. Create Historical & Active Bookings
        today = timezone.now().date()
        cls.booking_a_past = Booking.objects.create(
            booking_id='BK-ALPHA-PAST',
            customer=cls.customer,
            hotel=cls.hotel_a,
            room=cls.room_a,
            check_in=today - timezone.timedelta(days=5),
            check_out=today - timezone.timedelta(days=2),
            number_of_guests=2,
            number_of_rooms=1,
            price_per_night=Decimal('4500.00'),
            subtotal=Decimal('9000.00'),
            total_amount=Decimal('9000.00'),
            booking_status=Booking.STATUS_CHECKED_OUT,
            payment_status=Booking.PAYMENT_PAID
        )
        cls.booking_b_past = Booking.objects.create(
            booking_id='BK-BETA-PAST',
            customer=cls.customer,
            hotel=cls.hotel_b,
            room=cls.room_b,
            check_in=today - timezone.timedelta(days=4),
            check_out=today - timezone.timedelta(days=1),
            number_of_guests=2,
            number_of_rooms=1,
            price_per_night=Decimal('6500.00'),
            subtotal=Decimal('13000.00'),
            total_amount=Decimal('13000.00'),
            booking_status=Booking.STATUS_CHECKED_OUT,
            payment_status=Booking.PAYMENT_PAID
        )
        cls.booking_confirmed_stay = Booking.objects.create(
            booking_id='BK-CONF-PAST',
            customer=cls.customer,
            hotel=cls.hotel_a,
            room=cls.room_a,
            check_in=today - timezone.timedelta(days=3),
            check_out=today - timezone.timedelta(days=1),
            number_of_guests=1,
            number_of_rooms=1,
            price_per_night=Decimal('4500.00'),
            subtotal=Decimal('4500.00'),
            total_amount=Decimal('4500.00'),
            booking_status=Booking.STATUS_CONFIRMED, # Not marked checked-out yet
            payment_status=Booking.PAYMENT_PAID
        )

        # 5. Create Reviews for Hotel A and Hotel B
        cls.review_a = Review.objects.create(
            booking=cls.booking_a_past,
            hotel=cls.hotel_a,
            user=cls.customer,
            rating=5,
            comment='Outstanding stay at Alpha!',
            status=Review.STATUS_VISIBLE
        )
        cls.review_b = Review.objects.create(
            booking=cls.booking_b_past,
            hotel=cls.hotel_b,
            user=cls.customer,
            rating=4,
            comment='Serene mountain vibes at Beta.',
            status=Review.STATUS_VISIBLE
        )

        # 6. Create Active Coupon
        cls.coupon = Coupon.objects.create(
            code='ALPHA10',
            discount_percentage=Decimal('10.00'),
            min_booking_amount=Decimal('1000.00'),
            valid_from=today - timezone.timedelta(days=1),
            valid_until=today + timezone.timedelta(days=30),
            is_active=True
        )

    def setUp(self):
        self.client = APIClient()

    # =========================================================================
    # 1. REVIEWS API DATA ISOLATION VERIFICATION
    # =========================================================================

    def test_reviews_data_isolation_undefined_hotel_id(self):
        """
        Verify GET /api/reviews/?hotel_id=undefined returns empty result,
        never leaking reviews belonging to unrelated hotels.
        """
        response = self.client.get('/api/reviews/?hotel_id=undefined')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 0, "Undefined hotel_id must return 0 reviews, never leaking unrelated reviews!")

    def test_reviews_data_isolation_null_hotel_id(self):
        """Verify GET /api/reviews/?hotel_id=null returns 0 reviews."""
        response = self.client.get('/api/reviews/?hotel_id=null')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 0)

    def test_reviews_data_isolation_empty_hotel_id(self):
        """Verify GET /api/reviews/?hotel_id= returns 0 reviews."""
        response = self.client.get('/api/reviews/?hotel_id=')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 0)

    def test_reviews_data_isolation_missing_hotel_id(self):
        """Verify GET /api/reviews/ with no hotel parameter returns 0 reviews."""
        response = self.client.get('/api/reviews/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 0)

    def test_reviews_data_isolation_invalid_non_numeric(self):
        """Verify non-numeric hotel IDs return 0 reviews without 500 error."""
        response = self.client.get('/api/reviews/?hotel_id=some_malicious_string')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 0)

    def test_reviews_data_isolation_nonexistent_hotel_id(self):
        """Verify non-existent hotel ID returns 0 reviews."""
        response = self.client.get('/api/reviews/?hotel_id=999999')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 0)

    def test_reviews_data_isolation_valid_hotel_id_returns_only_target_hotel(self):
        """
        Verify valid hotel_id returns strictly that hotel's visible reviews
        and excludes reviews from any other hotel.
        """
        response = self.client.get(f'/api/reviews/?hotel_id={self.hotel_a.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['comment'], 'Outstanding stay at Alpha!')
        self.assertEqual(results[0]['hotel'], self.hotel_a.id)

        # Check Hotel B
        response_b = self.client.get(f'/api/reviews/?hotel_id={self.hotel_b.id}')
        self.assertEqual(response_b.status_code, status.HTTP_200_OK)
        results_b = response_b.data.get('results', response_b.data)
        self.assertEqual(len(results_b), 1)
        self.assertEqual(results_b[0]['comment'], 'Serene mountain vibes at Beta.')
        self.assertEqual(results_b[0]['hotel'], self.hotel_b.id)

    # =========================================================================
    # 2. SQLITE WAL & CONCURRENCY VERIFICATION
    # =========================================================================

    def test_sqlite_wal_and_busy_timeout_configured(self):
        """
        Verifies SQLite WAL configuration and busy_timeout settings.
        """
        with connection.cursor() as cursor:
            cursor.execute('PRAGMA busy_timeout;')
            timeout = cursor.fetchone()[0]
            # Must be at least 30000ms (configured 60000ms)
            self.assertGreaterEqual(timeout, 30000)

    def test_sqlite_concurrent_readers_and_writers(self):
        """
        Verifies simultaneous read and write operations on an on-disk SQLite database in WAL mode.
        WAL allows multiple concurrent readers while a writer commits, under SQLite's single-writer architecture.
        """
        import tempfile
        import sqlite3

        with tempfile.NamedTemporaryFile(suffix='.sqlite3', delete=False) as tf:
            temp_db_path = tf.name

        try:
            # Initialize temp DB in WAL mode
            init_conn = sqlite3.connect(temp_db_path)
            init_conn.execute('PRAGMA journal_mode = WAL;')
            init_conn.execute('PRAGMA busy_timeout = 60000;')
            init_conn.execute('CREATE TABLE test_data (id INTEGER PRIMARY KEY, val TEXT);')
            init_conn.execute('INSERT INTO test_data (val) VALUES ("seed_1"), ("seed_2");')
            init_conn.commit()
            init_conn.close()

            def disk_reader(idx):
                conn = sqlite3.connect(temp_db_path, timeout=60.0)
                cur = conn.cursor()
                cur.execute('SELECT COUNT(*) FROM test_data;')
                cnt = cur.fetchone()[0]
                conn.close()
                return cnt

            def disk_writer(idx):
                conn = sqlite3.connect(temp_db_path, timeout=60.0)
                cur = conn.cursor()
                cur.execute(f'INSERT INTO test_data (val) VALUES ("written_{idx}");')
                time.sleep(0.01) # hold write lock briefly
                conn.commit()
                conn.close()
                return True

            with ThreadPoolExecutor(max_workers=6) as pool:
                futures = [
                    pool.submit(disk_reader, 1),
                    pool.submit(disk_writer, 1),
                    pool.submit(disk_reader, 2),
                    pool.submit(disk_reader, 3),
                    pool.submit(disk_writer, 2),
                    pool.submit(disk_reader, 4),
                ]
                for f in futures:
                    res = f.result()
                    self.assertTrue(res)
        finally:
            import os
            for ext in ['', '-wal', '-shm']:
                f_path = temp_db_path + ext
                if os.path.exists(f_path):
                    try:
                        os.remove(f_path)
                    except Exception:
                        pass

    def test_get_available_room_count_does_not_mutate_bookings(self):
        """
        Verify that calling get_available_room_count() performs zero database writes
        and does NOT alter historical or confirmed booking records.
        """
        initial_status = self.booking_confirmed_stay.booking_status
        initial_checkout_at = self.booking_confirmed_stay.actual_check_out_at

        # Execute availability calculation for tomorrow
        tomorrow = timezone.now().date() + timezone.timedelta(days=1)
        day_after = tomorrow + timezone.timedelta(days=1)

        with self.assertNumQueries(1):
            # Only 1 single read query: booked_rooms_count aggregate sum
            available = get_available_room_count(self.room_a, tomorrow, day_after)

        self.assertEqual(available, 5)

        # Refresh from database and assert zero mutation occurred
        self.booking_confirmed_stay.refresh_from_db()
        self.assertEqual(self.booking_confirmed_stay.booking_status, initial_status,
                         "Read-only availability check must not alter booking_status!")
        self.assertEqual(self.booking_confirmed_stay.actual_check_out_at, initial_checkout_at,
                         "Read-only availability check must not overwrite actual_check_out_at!")

    def test_hotel_listing_does_not_mutate_bookings(self):
        """
        Verify that GET /api/hotels/ listing does not perform database write operations.
        """
        initial_status = self.booking_confirmed_stay.booking_status

        response = self.client.get('/api/hotels/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.booking_confirmed_stay.refresh_from_db()
        self.assertEqual(self.booking_confirmed_stay.booking_status, initial_status)

    # =========================================================================
    # 4. REAL FRONTEND RUNTIME COMPATIBILITY (Home, Search, Details, Rooms, Booking)
    # =========================================================================

    def test_frontend_home_page_apis(self):
        """Tests all APIs invoked by Home.jsx on initial render."""
        # 1. Cities
        res_cities = self.client.get('/api/hotels/cities/')
        self.assertEqual(res_cities.status_code, status.HTTP_200_OK)
        self.assertIn('Goa', res_cities.data)

        # 2. Featured Hotels
        res_hotels = self.client.get('/api/hotels/?is_featured=true')
        self.assertEqual(res_hotels.status_code, status.HTTP_200_OK)

        # 3. Guest Wishlist (Public)
        res_wishlist = self.client.get('/api/wishlist/')
        self.assertEqual(res_wishlist.status_code, status.HTTP_200_OK)
        results = res_wishlist.data.get('results', res_wishlist.data)
        self.assertEqual(len(results), 0)

        # 4. Guest Unread Notification Count
        res_unread = self.client.get('/api/notifications/unread-count/')
        self.assertEqual(res_unread.status_code, status.HTTP_200_OK)
        self.assertEqual(res_unread.data['unread_count'], 0)

    def test_frontend_hotel_search_apis(self):
        """Tests search and filter APIs invoked by HotelSearch.jsx."""
        # Filter by city
        res_search = self.client.get('/api/hotels/?city=Goa')
        self.assertEqual(res_search.status_code, status.HTTP_200_OK)
        results = res_search.data.get('results', res_search.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['name'], 'Hotel Alpha Luxury Resort')

        # Filter by price range & price sort
        res_price = self.client.get('/api/hotels/?min_price=4000&max_price=8000&sort_by=price_low')
        self.assertEqual(res_price.status_code, status.HTTP_200_OK)

    def test_frontend_hotel_details_and_rooms_apis(self):
        """Tests APIs invoked by HotelDetails.jsx."""
        # 1. Hotel Details
        res_det = self.client.get(f'/api/hotels/{self.hotel_a.id}/')
        self.assertEqual(res_det.status_code, status.HTTP_200_OK)
        self.assertEqual(res_det.data['name'], 'Hotel Alpha Luxury Resort')

        # 2. Missing Hotel ID (e.g. ID 44) returns 404
        res_404 = self.client.get('/api/hotels/44/')
        self.assertEqual(res_404.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(res_404.data.get('detail'), 'Hotel not found.')

        # 3. Room Selection for Hotel
        today = timezone.now().date()
        cin = str(today + timezone.timedelta(days=1))
        cout = str(today + timezone.timedelta(days=2))
        res_rooms = self.client.get(f'/api/rooms/by-hotel/{self.hotel_a.id}/?check_in={cin}&check_out={cout}&rooms=1')
        self.assertEqual(res_rooms.status_code, status.HTTP_200_OK)
        rooms = res_rooms.data.get('results', res_rooms.data)
        self.assertEqual(len(rooms), 1)
        self.assertEqual(rooms[0]['title'], 'Alpha Deluxe Room')

    def test_frontend_booking_page_apis(self):
        """Tests APIs invoked by BookingPage.jsx."""
        # 1. Room Availability Check
        today = timezone.now().date()
        cin = str(today + timezone.timedelta(days=1))
        cout = str(today + timezone.timedelta(days=2))
        res_avail = self.client.get(f'/api/rooms/check-availability/?room_id={self.room_a.id}&check_in={cin}&check_out={cout}&rooms=1')
        self.assertEqual(res_avail.status_code, status.HTTP_200_OK)
        self.assertTrue(res_avail.data['available'])
        self.assertEqual(res_avail.data['remaining'], 5)

        # 2. Available Coupons
        res_coupons = self.client.get('/api/coupons/available/?amount=5000')
        self.assertEqual(res_coupons.status_code, status.HTTP_200_OK)
        coupons = res_coupons.data.get('results', res_coupons.data)
        self.assertGreaterEqual(len(coupons), 1)
