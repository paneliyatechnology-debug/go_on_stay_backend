import os
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.cache import cache
from django.core.management import call_command
from django.core.exceptions import ImproperlyConfigured
from django.test.utils import CaptureQueriesContext
from django.db import connection
from rest_framework.test import APIClient
from rest_framework import status

from hotels.models import Hotel, HotelImage, Amenity, HotelVerificationDocument
from rooms.models import Room, RoomImage
from bookings.models import Booking
from payments.models import Payment, Refund
from notifications.models import Notification
from staff.models import Department
from hotels.serializers import HotelSerializer
from bookings.serializers import BookingSerializer

User = get_user_model()


class P2StabilityPerformanceConfigurationTestCase(TestCase):
    """
    Automated verification test suite for verified P2 audit issues:
    - ISSUE-06: Database Migration Drift & Model Schema Consistency
    - ISSUE-07: N+1 Query Performance & ORM Prefetch Optimization
    - ISSUE-08: Insecure Default Configuration Fallbacks & Production Hardening
    """

    def setUp(self):
        cache.clear()
        self.client = APIClient()

        # 1. Platform Admin
        self.admin = User.objects.create_superuser(
            username='p2_admin',
            email='admin.p2@goonstay.com',
            password='AdminPassword123!',
            first_name='Admin',
            last_name='P2',
            role='ADMIN'
        )

        # 2. Hotel Host
        self.host = User.objects.create_user(
            username='p2_host',
            email='host.p2@goonstay.com',
            password='HostPassword123!',
            first_name='Vikram',
            last_name='Rathore',
            role='HOTEL_OWNER'
        )

        # 3. Customer
        self.customer = User.objects.create_user(
            username='p2_customer',
            email='customer.p2@goonstay.com',
            password='CustomerPassword123!',
            first_name='Neha',
            last_name='Sharma',
            role='CUSTOMER'
        )

        # 4. Amenities
        self.wifi = Amenity.objects.create(name='Free WiFi', icon_name='wifi', category='BASIC')
        self.pool = Amenity.objects.create(name='Swimming Pool', icon_name='pool', category='LEISURE')

        # 5. Populate Representative Hotels with Images, Amenities, Documents, and Rooms
        self.hotels = []
        today = timezone.now().date()
        hotel_names = [
            'Hotel Grand Palace', 'The Royal Retreat', 'Heritage Haveli Palace',
            'Taj Lakeview Manor', 'Oberoi Luxury Resort', 'Marriott Executive Suites',
            'Radisson Blu Resort', 'Leela Palace Haveli', 'Hyatt Regency Palace',
            'Fortune Park Retreat'
        ]

        for i, name in enumerate(hotel_names):
            h = Hotel.objects.create(
                owner=self.host,
                name=name,
                property_type='HOTEL',
                city='Jaipur',
                state='Rajasthan',
                address=f'Station Road Sector {i+1}',
                zip_code='302001',
                status=Hotel.STATUS_APPROVED,
                is_approved=True
            )
            h.amenities.add(self.wifi, self.pool)

            HotelImage.objects.create(
                hotel=h,
                image_url=f'https://images.example.com/hotel_{i}_1.jpg',
                is_primary=True,
                caption='Primary Exterior'
            )
            HotelImage.objects.create(
                hotel=h,
                image_url=f'https://images.example.com/hotel_{i}_2.jpg',
                is_primary=False,
                caption='Lobby'
            )
            HotelVerificationDocument.objects.create(
                hotel=h,
                document_type='GST_CERTIFICATE',
                document_url=f'https://docs.example.com/gst_{i}.pdf',
                status='APPROVED'
            )

            r = Room.objects.create(
                hotel=h,
                title=f'Deluxe Suite {i}',
                room_type='DELUXE',
                price_per_night=Decimal('3500.00'),
                total_rooms=5
            )

            self.hotels.append(h)

        # 6. Populate Representative Bookings with Payments and Refunds
        self.bookings = []
        for i, h in enumerate(self.hotels):
            r = h.rooms.first()
            b = Booking.objects.create(
                booking_id=f'BK-P2-00{i+1}',
                customer=self.customer,
                hotel=h,
                room=r,
                check_in=today + timedelta(days=i + 1),
                check_out=today + timedelta(days=i + 3),
                number_of_guests=2,
                number_of_rooms=1,
                number_of_nights=2,
                price_per_night=Decimal('3500.00'),
                subtotal=Decimal('7000.00'),
                total_amount=Decimal('7000.00'),
                refundable_amount=Decimal('7000.00'),
                guest_name=f'Guest {i+1}',
                guest_email=f'guest{i+1}@example.com',
                guest_phone='9876543210',
                booking_status=Booking.STATUS_CONFIRMED,
                payment_status=Booking.PAYMENT_PAID
            )
            p = Payment.objects.create(
                booking=b,
                user=self.customer,
                razorpay_order_id=f'order_p2_{i+1}',
                razorpay_payment_id=f'pay_p2_{i+1}',
                amount=Decimal('7000.00'),
                status=Payment.STATUS_CAPTURED
            )
            if i % 3 == 0:
                Refund.objects.create(
                    booking=b,
                    payment=p,
                    amount=Decimal('3500.00'),
                    status=Refund.STATUS_REFUNDED,
                    razorpay_refund_id=f'rfnd_p2_{i+1}'
                )
            self.bookings.append(b)

    # =========================================================================
    # ISSUE-06: Database Migration Drift & Model Schema Consistency
    # =========================================================================

    def test_issue06_zero_migration_drift_check(self):
        """Verifies makemigrations --check detects zero pending schema or choices drift."""
        # call_command('makemigrations', check=True, dry_run=True) raises SystemExit(1) if drift exists
        try:
            call_command('makemigrations', check=True, dry_run=True)
            drift_detected = False
        except SystemExit:
            drift_detected = True
        self.assertFalse(drift_detected, "Migration drift detected! Models out of sync with migration history.")

    def test_issue06_notification_types_accessibility(self):
        """Verifies Notification model accepts newly added choices and retrieves successfully."""
        notif = Notification.objects.create(
            recipient=self.customer,
            title='Escrow Matured Alert',
            message='Your 7-day holding period has matured.',
            notification_type=Notification.TYPE_PAYOUT_DUE,
            booking=self.bookings[0]
        )
        self.assertEqual(notif.notification_type, 'PAYOUT_DUE')
        fetched = Notification.objects.get(id=notif.id)
        self.assertEqual(fetched.notification_type, Notification.TYPE_PAYOUT_DUE)

    def test_issue06_department_codes_accessibility(self):
        """Verifies Department model preserves all canonical department codes."""
        codes = [
            Department.CODE_RESERVATION,
            Department.CODE_CUSTOMER_SUPPORT,
            Department.CODE_REFUNDS_AND_CLAIMS,
            Department.CODE_PAYOUT_AND_ESCROW,
            Department.CODE_HOTEL_VERIFICATION,
        ]
        for c in codes:
            dept, _ = Department.objects.get_or_create(code=c, defaults={'name': c.title()})
            self.assertEqual(dept.code, c)

    # =========================================================================
    # ISSUE-07: N+1 Query Reduction & ORM Performance Benchmarking
    # =========================================================================

    def test_issue07_hotel_listing_query_count_benchmark(self):
        """
        Measures hotel listing SQL query counts with prefetching vs unoptimized queries.
        Verifies query count does not scale linearly with the number of returned hotels.
        """
        self.client.force_authenticate(user=self.admin)

        # 1. Unoptimized baseline query count (raw queryset without select/prefetch)
        with CaptureQueriesContext(connection) as unoptimized_ctx:
            unoptimized_qs = list(Hotel.objects.filter(is_deleted=False)[:10])
            _ = HotelSerializer(unoptimized_qs, many=True).data
        unoptimized_count = len(unoptimized_ctx)

        # 2. Optimized API endpoint query count
        with CaptureQueriesContext(connection) as optimized_ctx:
            res = self.client.get('/api/hotels/?page_size=10')
            self.assertEqual(res.status_code, status.HTTP_200_OK)
        optimized_count = len(optimized_ctx)

        # Print benchmarking evidence
        print(f"\n[BENCHMARK] Hotel Listing (10 hotels): Unoptimized = {unoptimized_count} queries | Optimized = {optimized_count} queries")

        # Optimized count must be substantially lower than unoptimized count
        self.assertLess(optimized_count, unoptimized_count)
        self.assertLessEqual(optimized_count, 18)

    def test_issue07_hotel_detail_query_count_benchmark(self):
        """Measures hotel detail SQL query counts."""
        self.client.force_authenticate(user=self.customer)
        hotel_id = self.hotels[0].id

        with CaptureQueriesContext(connection) as ctx:
            res = self.client.get(f'/api/hotels/{hotel_id}/')
            self.assertEqual(res.status_code, status.HTTP_200_OK)
        detail_query_count = len(ctx)

        print(f"\n[BENCHMARK] Hotel Detail: Query Count = {detail_query_count} queries")
        self.assertLessEqual(detail_query_count, 12)

    def test_issue07_booking_listing_query_count_benchmark(self):
        """
        Measures booking listing SQL query counts with prefetching vs unoptimized queries.
        Verifies query count does not scale linearly with 10 listed bookings.
        """
        self.client.force_authenticate(user=self.admin)

        # 1. Unoptimized baseline query count
        with CaptureQueriesContext(connection) as unoptimized_ctx:
            unoptimized_qs = list(Booking.objects.all()[:10])
            _ = BookingSerializer(unoptimized_qs, many=True).data
        unoptimized_count = len(unoptimized_ctx)

        # 2. Optimized API endpoint query count
        with CaptureQueriesContext(connection) as optimized_ctx:
            res = self.client.get('/api/bookings/?page_size=10')
            self.assertEqual(res.status_code, status.HTTP_200_OK)
        optimized_count = len(optimized_ctx)

        print(f"\n[BENCHMARK] Booking Listing (10 bookings): Unoptimized = {unoptimized_count} queries | Optimized = {optimized_count} queries")

        self.assertLess(optimized_count, unoptimized_count)
        self.assertLessEqual(optimized_count, 35)

    def test_issue07_booking_detail_query_count_benchmark(self):
        """Measures booking detail SQL query count."""
        self.client.force_authenticate(user=self.customer)
        booking_pk = self.bookings[0].id

        with CaptureQueriesContext(connection) as ctx:
            res = self.client.get(f'/api/bookings/{booking_pk}/')
            self.assertEqual(res.status_code, status.HTTP_200_OK)
        detail_query_count = len(ctx)

        print(f"\n[BENCHMARK] Booking Detail: Query Count = {detail_query_count} queries")
        self.assertLessEqual(detail_query_count, 18)

    def test_issue07_response_integrity_preserved(self):
        """Ensures optimized querysets return complete, identical serializer representations."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.get(f'/api/hotels/{self.hotels[0].id}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data

        # Verify all expected relationships are fully populated without regression
        self.assertEqual(data['id'], self.hotels[0].id)
        self.assertEqual(data['name'], self.hotels[0].name)
        self.assertEqual(len(data['images']), 2)
        self.assertEqual(len(data['amenities']), 2)
        self.assertEqual(len(data['verification_documents']), 1)
        self.assertEqual(Decimal(str(data['starting_price'])), Decimal('3500.00'))
        self.assertIsNotNone(data['primary_image'])

    # =========================================================================
    # ISSUE-08: Insecure Default Configuration Fallbacks
    # =========================================================================

    def test_issue08_production_missing_secret_key_raises_error(self):
        """Verifies ImproperlyConfigured is raised when SECRET_KEY is missing in production."""
        with patch.dict(os.environ, {'DJANGO_ENV': 'production', 'SECRET_KEY': '', 'DEBUG': 'False'}):
            import importlib
            import config.settings as app_settings
            with self.assertRaises(ImproperlyConfigured) as cm:
                importlib.reload(app_settings)
            self.assertIn("SECRET_KEY environment variable is missing", str(cm.exception))

    def test_issue08_production_insecure_secret_key_raises_error(self):
        """Verifies ImproperlyConfigured is raised when an insecure placeholder SECRET_KEY is used in production."""
        with patch.dict(os.environ, {
            'DJANGO_ENV': 'production',
            'SECRET_KEY': 'django-insecure-bookmyroom-super-secret-key-production-2026',
            'DEBUG': 'False'
        }):
            import importlib
            import config.settings as app_settings
            with self.assertRaises(ImproperlyConfigured) as cm:
                importlib.reload(app_settings)
            self.assertIn("An insecure or well-known placeholder SECRET_KEY", str(cm.exception))

    def test_issue08_production_debug_true_raises_error(self):
        """Verifies ImproperlyConfigured is raised when DEBUG=True in production."""
        with patch.dict(os.environ, {
            'DJANGO_ENV': 'production',
            'SECRET_KEY': 'strong-cryptographically-secure-production-key-998877',
            'DEBUG': 'True'
        }):
            import importlib
            import config.settings as app_settings
            with self.assertRaises(ImproperlyConfigured) as cm:
                importlib.reload(app_settings)
            self.assertIn("DEBUG cannot be set to True in a production environment", str(cm.exception))

    def test_issue08_production_wildcard_allowed_hosts_raises_error(self):
        """Verifies ImproperlyConfigured is raised when ALLOWED_HOSTS='*' with DEBUG=False."""
        with patch.dict(os.environ, {
            'DJANGO_ENV': 'production',
            'SECRET_KEY': 'strong-cryptographically-secure-production-key-998877',
            'DEBUG': 'False',
            'ALLOWED_HOSTS': '*'
        }):
            import importlib
            import config.settings as app_settings
            with self.assertRaises(ImproperlyConfigured) as cm:
                importlib.reload(app_settings)
            self.assertIn("ALLOWED_HOSTS cannot be empty or wildcard", str(cm.exception))

    def test_issue08_live_payment_mode_insecure_keys_raises_error(self):
        """Verifies ImproperlyConfigured is raised when PAYMENT_MODE=live without real production Razorpay keys."""
        with patch.dict(os.environ, {
            'DJANGO_ENV': 'production',
            'SECRET_KEY': 'strong-cryptographically-secure-production-key-998877',
            'DEBUG': 'False',
            'ALLOWED_HOSTS': 'goonstay.com',
            'PAYMENT_MODE': 'live',
            'RAZORPAY_KEY_ID': 'rzp_test_bookmyroom_key_2026',
            'RAZORPAY_KEY_SECRET': ''
        }):
            import importlib
            import config.settings as app_settings
            with self.assertRaises(ImproperlyConfigured) as cm:
                importlib.reload(app_settings)
            self.assertIn("Production Payment Gateway Error", str(cm.exception))

    def test_issue08_valid_production_configuration_loads_cleanly(self):
        """Verifies valid production configuration with strong credentials loads successfully."""
        with patch.dict(os.environ, {
            'DJANGO_ENV': 'production',
            'SECRET_KEY': 'a-valid-production-secret-key-32-bytes-long-random-string',
            'DEBUG': 'False',
            'ALLOWED_HOSTS': 'goonstay.com,api.goonstay.com',
            'PAYMENT_MODE': 'test',
            'RAZORPAY_KEY_ID': 'rzp_test_valid_key',
            'RAZORPAY_KEY_SECRET': 'valid_secret',
            'RAZORPAY_WEBHOOK_SECRET': 'valid_webhook_sec'
        }):
            import importlib
            import config.settings as app_settings
            importlib.reload(app_settings)
            self.assertFalse(app_settings.DEBUG)
            self.assertEqual(app_settings.ALLOWED_HOSTS, ['goonstay.com', 'api.goonstay.com'])
            self.assertEqual(app_settings.SECRET_KEY, 'a-valid-production-secret-key-32-bytes-long-random-string')

    def tearDown(self):
        # Reset settings reload to current environment
        import importlib
        import config.settings as app_settings
        importlib.reload(app_settings)
        super().tearDown()
