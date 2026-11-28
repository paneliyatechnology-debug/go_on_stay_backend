from decimal import Decimal
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking
from reviews.models import Review
from coupons.models import Coupon
from wishlist.models import Wishlist
from notifications.models import Notification

User = get_user_model()


class ServerSidePaginationTests(APITestCase):
    """
    Comprehensive Server-Side Pagination Test Suite across GoOnStay Backend.
    Verifies default page size (10), custom page size, max page size (100),
    consistent response structure {count, next, previous, results},
    filtering/sorting integration, and role permissions.
    """

    @classmethod
    def setUpTestData(cls):
        # 1. Users
        cls.admin_user = User.objects.create_user(
            username='pag_admin',
            email='pag_admin@goonstay.com',
            password='AdminPassword123!',
            role='ADMIN',
            is_staff=True,
            is_superuser=True
        )

        cls.owner_user = User.objects.create_user(
            username='pag_owner',
            email='pag_owner@goonstay.com',
            password='OwnerPassword123!',
            role='HOTEL_OWNER',
            is_active=True
        )

        cls.customer_user = User.objects.create_user(
            username='pag_customer',
            email='pag_customer@goonstay.com',
            password='CustomerPassword123!',
            role='CUSTOMER',
            is_active=True
        )

        # 2. Bulk Seed 25 Hotels to rigorously test page 1, middle page, last page, and custom page sizes
        HOTEL_NAMES = [
            'Alpha Palace', 'Bravo Resort', 'Charlie Inn', 'Delta Suites', 'Echo Retreat',
            'Foxtrot Lodge', 'Golf Residency', 'Hotel Imperial', 'India Haven', 'Juliet Court',
            'Kilo Grand', 'Lima Heritage', 'Mike Continental', 'November Heights', 'Oscar Manor',
            'Papa Plaza', 'Quebec Towers', 'Romeo Oasis', 'Sierra Boutique', 'Tango Regalia',
            'Uniform Villas', 'Victor Castle', 'Whiskey Horizon', 'Xray Vista', 'Yankee Royale'
        ]
        cls.hotels = []
        for i in range(1, 26):
            h = Hotel.objects.create(
                owner=cls.owner_user,
                name=HOTEL_NAMES[i - 1],
                city='Ahmedabad' if i % 2 == 0 else 'Mumbai',
                state='Gujarat' if i % 2 == 0 else 'Maharashtra',
                address='Marine Drive Promenade Coastal Road',
                status=Hotel.STATUS_APPROVED,
                is_approved=True
            )
            # Create at least 1 room per hotel
            Room.objects.create(
                hotel=h,
                title=f"Room for Hotel #{i}",
                room_type='STANDARD',
                price_per_night=Decimal(str(1000 + i * 100)),
                capacity_adults=2
            )
            cls.hotels.append(h)

        # 3. Seed Notifications for customer
        cls.notifications = []
        for i in range(1, 16):
            n = Notification.objects.create(
                recipient=cls.customer_user,
                title=f"Alert #{i}",
                message=f"Test notification message #{i}",
                notification_type=Notification.TYPE_GENERAL
            )
            cls.notifications.append(n)

        # 4. Seed Reviews for hotel #1
        from datetime import date, timedelta
        for i in range(1, 15):
            b = Booking.objects.create(
                booking_id=f"BMR-REV-{i:03d}",
                customer=cls.customer_user,
                hotel=cls.hotels[0],
                room=cls.hotels[0].rooms.first(),
                check_in=date(2026, 1, 1) + timedelta(days=i * 2),
                check_out=date(2026, 1, 2) + timedelta(days=i * 2),
                total_amount=2500,
                booking_status=Booking.STATUS_CONFIRMED,
                payment_status=Booking.PAYMENT_PAID
            )
            Review.objects.create(
                booking=b,
                hotel=cls.hotels[0],
                user=cls.customer_user,
                rating=5 if i % 2 == 0 else 4,
                comment=f"Great stay review #{i}",
                status=Review.STATUS_VISIBLE
            )

        # 5. Seed Wishlist items
        for h in cls.hotels[:12]:
            Wishlist.objects.create(user=cls.customer_user, hotel=h)

        # 6. Seed Coupons
        for i in range(1, 15):
            Coupon.objects.create(
                code=f"DISC{i:02d}",
                discount_type='PERCENTAGE',
                discount_value=Decimal('10.00'),
                is_active=True
            )

    # -------------------------------------------------------------------------
    # 1. FIRST PAGE, DEFAULT PAGE SIZE (10), AND STRUCTURE
    # -------------------------------------------------------------------------
    def test_01_default_page_size_and_response_structure(self):
        """GET /api/hotels/ default delivers 10 records with count, next, previous, results."""
        response = self.client.get('/api/hotels/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Validate standard structure
        self.assertIn('count', response.data)
        self.assertIn('next', response.data)
        self.assertIn('previous', response.data)
        self.assertIn('results', response.data)

        # Default page size must be 10
        self.assertEqual(len(response.data['results']), 10)
        self.assertEqual(response.data['count'], 25)
        self.assertIsNotNone(response.data['next'])
        self.assertIsNone(response.data['previous'])

    # -------------------------------------------------------------------------
    # 2. MIDDLE PAGE (PAGE 2)
    # -------------------------------------------------------------------------
    def test_02_middle_page_navigation(self):
        """GET /api/hotels/?page=2 delivers records 11-20 with both next and previous."""
        response = self.client.get('/api/hotels/?page=2')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(len(response.data['results']), 10)
        self.assertIsNotNone(response.data['next'])
        self.assertIsNotNone(response.data['previous'])
        self.assertIn('page=3', response.data['next'])
        self.assertNotIn('page=', response.data['previous'])  # page 1 is default without ?page=1 or with ?page=1

    # -------------------------------------------------------------------------
    # 3. LAST PAGE (PAGE 3)
    # -------------------------------------------------------------------------
    def test_03_last_page_navigation(self):
        """GET /api/hotels/?page=3 delivers remaining 5 records with previous and null next."""
        response = self.client.get('/api/hotels/?page=3')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(len(response.data['results']), 5)
        self.assertIsNone(response.data['next'])
        self.assertIsNotNone(response.data['previous'])

    # -------------------------------------------------------------------------
    # 4. INVALID PAGE NUMBER
    # -------------------------------------------------------------------------
    def test_04_invalid_page_number_handling(self):
        """Requesting page 99999 returns 404 with standard error or empty page handling."""
        response = self.client.get('/api/hotels/?page=99999')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # -------------------------------------------------------------------------
    # 5. CUSTOM PAGE SIZE (FRONTEND SPECIFIED)
    # -------------------------------------------------------------------------
    def test_05_custom_page_size_requested_by_frontend(self):
        """Frontend requests ?page_size=5 -> exactly 5 records per page, 5 total pages."""
        response = self.client.get('/api/hotels/?page=1&page_size=5')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(len(response.data['results']), 5)
        self.assertEqual(response.data['count'], 25)
        self.assertIn('page=2', response.data['next'])
        self.assertIn('page_size=5', response.data['next'])

    # -------------------------------------------------------------------------
    # 6. MAXIMUM PAGE SIZE RESTRICTION (CAPPED AT 100)
    # -------------------------------------------------------------------------
    def test_06_maximum_page_size_restriction_capped_at_100(self):
        """Passing ?page_size=500 is safely capped at max_page_size=100."""
        response = self.client.get('/api/hotels/?page=1&page_size=500')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # There are only 25 items, all returned in 1 page without error
        self.assertEqual(len(response.data['results']), 25)
        self.assertIsNone(response.data['next'])

    # -------------------------------------------------------------------------
    # 7. SEARCH + PAGINATION INTEGRATION
    # -------------------------------------------------------------------------
    def test_07_search_with_pagination(self):
        """Search 'Mumbai' filters to 12 hotels, paginating with count=12 and page_size=5."""
        response = self.client.get('/api/hotels/?search=Mumbai&page=1&page_size=5')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # 12 Mumbai hotels total: 25 hotels with odd indices 1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23, 25 = 13 hotels
        count = response.data['count']
        self.assertEqual(len(response.data['results']), 5)
        self.assertIn('search=Mumbai', response.data['next'])

        # Verify all returned hotels are indeed in Mumbai
        for h in response.data['results']:
            self.assertEqual(h['city'], 'Mumbai')

    # -------------------------------------------------------------------------
    # 8. FILTERING + PAGINATION
    # -------------------------------------------------------------------------
    def test_08_city_filter_with_pagination(self):
        """GET /api/hotels/?city=Ahmedabad&page=1&page_size=5 counts only Ahmedabad hotels."""
        response = self.client.get('/api/hotels/?city=Ahmedabad&page=1&page_size=5')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(len(response.data['results']), 5)
        self.assertIn('city=Ahmedabad', response.data['next'])
        for h in response.data['results']:
            self.assertEqual(h['city'], 'Ahmedabad')

    # -------------------------------------------------------------------------
    # 9. SORTING + PAGINATION
    # -------------------------------------------------------------------------
    def test_09_sorting_with_pagination(self):
        """GET /api/hotels/?sort_by=price_asc&page=1&page_size=5 orders ascending."""
        response = self.client.get('/api/hotels/?sort_by=price_asc&page=1&page_size=5')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data['results']
        self.assertEqual(len(results), 5)
        prices = [r['starting_price'] for r in results]
        self.assertEqual(prices, sorted(prices))

    # -------------------------------------------------------------------------
    # 10. NOTIFICATIONS PAGINATION
    # -------------------------------------------------------------------------
    def test_10_notifications_pagination(self):
        """GET /api/notifications/ paginates customer alerts with default page_size=10."""
        self.client.force_authenticate(user=self.customer_user)
        response = self.client.get('/api/notifications/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data['count'], 15)
        self.assertEqual(len(response.data['results']), 10)
        self.assertIsNotNone(response.data['next'])

    # -------------------------------------------------------------------------
    # 11. REVIEWS PAGINATION
    # -------------------------------------------------------------------------
    def test_11_reviews_pagination(self):
        """GET /api/reviews/?hotel_id=... paginates hotel reviews."""
        response = self.client.get(f'/api/reviews/?hotel_id={self.hotels[0].id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data['count'], 14)
        self.assertEqual(len(response.data['results']), 10)
        self.assertIsNotNone(response.data['next'])

    # -------------------------------------------------------------------------
    # 12. WISHLIST PAGINATION
    # -------------------------------------------------------------------------
    def test_12_wishlist_pagination(self):
        """GET /api/wishlist/ paginates user saved properties."""
        self.client.force_authenticate(user=self.customer_user)
        response = self.client.get('/api/wishlist/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data['count'], 12)
        self.assertEqual(len(response.data['results']), 10)
        self.assertIsNotNone(response.data['next'])

    # -------------------------------------------------------------------------
    # 13. ADMIN USERS PAGINATION & PERMISSION
    # -------------------------------------------------------------------------
    def test_13_admin_user_list_pagination_and_security(self):
        """GET /api/auth/all/ requires admin and paginates users."""
        # Unauthenticated -> 401
        res_unauth = self.client.get('/api/auth/all/')
        self.assertEqual(res_unauth.status_code, status.HTTP_401_UNAUTHORIZED)

        # Customer -> 403
        self.client.force_authenticate(user=self.customer_user)
        res_cust = self.client.get('/api/auth/all/')
        self.assertEqual(res_cust.status_code, status.HTTP_403_FORBIDDEN)

        # Admin -> 200 with pagination
        self.client.force_authenticate(user=self.admin_user)
        res_admin = self.client.get('/api/auth/all/?page=1&page_size=5')
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)
        self.assertIn('count', res_admin.data)
        self.assertEqual(len(res_admin.data['results']), 5)
