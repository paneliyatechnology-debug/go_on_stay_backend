import json
import uuid
import hashlib
from decimal import Decimal
from django.test import TestCase, override_settings
from django.urls import reverse
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from rest_framework.test import APIClient
from rest_framework import status, serializers

from users.models import User
from hotels.models import Hotel, Country, State, City, Area
from rooms.models import Room
from bookings.models import Booking
from payments.models import Payment, Refund, WebhookEvent, SupportTicket
from reviews.models import Review
from notifications.models import Notification
from util.validators import validate_upload_image, validate_upload_document
from config.settings import SensitiveDataLogFilter
import logging


class P3ReliabilityAndObservabilityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

        # Create test customer
        self.customer = User.objects.create_user(
            username='p3customer',
            email='p3customer@example.com',
            password='TestPassword123!',
            role='CUSTOMER'
        )

        # Create test country, state, city
        self.country = Country.objects.create(name='TestIndia', code='TI')
        self.state = State.objects.create(country=self.country, name='TestState')
        self.city = City.objects.create(state=self.state, name='TestCity')

    def tearDown(self):
        cache.clear()

    # 1. DATABASE INDEX VERIFICATION (P3-FINDING-01)
    def test_database_indexes_configured(self):
        """Verifies that high-frequency query columns have db_index=True."""
        # Hotels
        self.assertTrue(Hotel._meta.get_field('status').db_index)
        self.assertTrue(Hotel._meta.get_field('is_approved').db_index)
        self.assertTrue(Hotel._meta.get_field('is_active').db_index)
        self.assertTrue(Hotel._meta.get_field('created_at').db_index)

        # Rooms
        self.assertTrue(Room._meta.get_field('room_type').db_index)
        self.assertTrue(Room._meta.get_field('created_at').db_index)

        # Bookings
        self.assertTrue(Booking._meta.get_field('booking_status').db_index)
        self.assertTrue(Booking._meta.get_field('payment_status').db_index)
        self.assertTrue(Booking._meta.get_field('created_at').db_index)

        # Payments & Refunds
        self.assertTrue(Payment._meta.get_field('created_at').db_index)
        self.assertTrue(Refund._meta.get_field('created_at').db_index)
        self.assertTrue(SupportTicket._meta.get_field('status').db_index)
        self.assertTrue(SupportTicket._meta.get_field('created_at').db_index)

        # Users, Reviews, Notifications
        self.assertTrue(User._meta.get_field('role').db_index)
        self.assertTrue(User._meta.get_field('created_at').db_index)
        self.assertTrue(Review._meta.get_field('status').db_index)
        self.assertTrue(Review._meta.get_field('created_at').db_index)
        self.assertTrue(Notification._meta.get_field('is_read').db_index)
        self.assertTrue(Notification._meta.get_field('created_at').db_index)

    # 2. HEALTH & READINESS PROBES (P3-FINDING-04)
    def test_health_check_endpoint(self):
        """Tests /api/health/ returns HTTP 200 with database and cache status."""
        response = self.client.get('/api/health/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data.get('status'), 'healthy')
        self.assertEqual(data.get('service'), 'goonstay-backend')
        self.assertEqual(data.get('checks', {}).get('database'), 'connected')
        self.assertEqual(data.get('checks', {}).get('cache'), 'connected')

    def test_readiness_check_endpoint(self):
        """Tests /api/health/ready/ returns HTTP 200 with readiness status."""
        response = self.client.get('/api/health/ready/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data.get('ready'))
        self.assertEqual(data.get('status'), 'ready_for_traffic')

    # 3. REQUEST CORRELATION ID MIDDLEWARE (P3-FINDING-04)
    def test_request_correlation_id_generated_and_preserved(self):
        """Verifies X-Request-ID is generated if missing and preserved if supplied."""
        # Test 1: Generated automatically
        resp1 = self.client.get('/api/health/')
        req_id1 = resp1.headers.get('X-Request-ID')
        self.assertIsNotNone(req_id1)
        self.assertTrue(len(req_id1) >= 8)

        # Test 2: Upstream supplied correlation ID preserved
        custom_trace = "upstream-trace-uuid-999888777"
        resp2 = self.client.get('/api/health/', HTTP_X_REQUEST_ID=custom_trace)
        self.assertEqual(resp2.headers.get('X-Request-ID'), custom_trace)

    # 4. SENSITIVE DATA LOG FILTER (P3-FINDING-04)
    def test_sensitive_data_log_filter(self):
        """Verifies credentials, secrets and tokens are masked in log records."""
        filter_obj = SensitiveDataLogFilter()
        
        record1 = logging.LogRecord(
            name='test', level=logging.INFO, pathname='', lineno=0,
            msg='User login attempt with password="MySecretPassword123" failed',
            args=(), exc_info=None
        )
        filter_obj.filter(record1)
        self.assertNotIn('MySecretPassword123', record1.msg)
        self.assertIn('password=********', record1.msg)

        record2 = logging.LogRecord(
            name='test', level=logging.INFO, pathname='', lineno=0,
            msg='Razorpay client initialized with secret: "rzp_secret_key_abcdef"',
            args=(), exc_info=None
        )
        filter_obj.filter(record2)
        self.assertNotIn('rzp_secret_key_abcdef', record2.msg)
        self.assertIn('secret=********', record2.msg)

    # 5. WEBHOOK DETERMINISTIC IDEMPOTENCY (P3-FINDING-05)
    def test_webhook_deterministic_idempotency(self):
        """Verifies duplicate webhook deliveries with nested entity IDs are idempotent."""
        import hmac
        payload_dict = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_test_p3_unique_99",
                        "order_id": "order_test_p3_99",
                        "amount": 500000,
                        "status": "captured"
                    }
                }
            }
        }
        body_str = json.dumps(payload_dict)
        sig = hmac.new(
            settings.RAZORPAY_WEBHOOK_SECRET.encode('utf-8'),
            body_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        # First delivery
        resp1 = self.client.post(
            '/api/payments/webhook/',
            data=body_str,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=sig
        )
        self.assertEqual(resp1.status_code, status.HTTP_200_OK)

        # Verify WebhookEvent created with deterministic event_id
        expected_event_id = "payment.captured_pay_test_p3_unique_99"
        event = WebhookEvent.objects.filter(event_id=expected_event_id).first()
        self.assertIsNotNone(event)

        # Mark processed
        event.processed = True
        event.save()

        # Second delivery (duplicate retry)
        resp2 = self.client.post(
            '/api/payments/webhook/',
            data=body_str,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=sig
        )
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        self.assertEqual(resp2.json().get('status'), 'ignored')

    # 6. RATE LIMITING SCOPES & EXEMPTIONS (P3-FINDING-03)
    def test_view_throttle_scopes_and_exemptions(self):
        """Verifies that sensitive endpoints define appropriate throttle scopes and webhook is exempt."""
        from bookings.views import BookingListCreateView
        from payments.views import CreateOrderView, WebhookView
        from coupons.views import ValidateCouponView
        from django.test.client import RequestFactory

        rf = RequestFactory()

        # 1. BookingListCreateView
        booking_view = BookingListCreateView()
        booking_view.request = rf.post('/api/bookings/')
        booking_view.get_throttles()
        self.assertEqual(booking_view.throttle_scope, 'booking_create')

        booking_view.request = rf.get('/api/bookings/')
        booking_view.get_throttles()
        self.assertIsNone(booking_view.throttle_scope)

        # 2. CreateOrderView
        self.assertEqual(CreateOrderView.throttle_scope, 'order_create')

        # 3. ValidateCouponView
        self.assertEqual(ValidateCouponView.throttle_scope, 'coupon_apply')

        # 4. WebhookView (cryptographic HMAC replaces rate throttling)
        self.assertEqual(WebhookView.throttle_classes, [])

    # 7. UPLOAD FILE VALIDATORS (P3-FINDING-08)
    def test_upload_image_validation(self):
        """Tests validate_upload_image enforces 5MB size limit and valid image formats."""
        # Valid small image
        valid_img = SimpleUploadedFile("photo.jpg", b"fake jpeg data", content_type="image/jpeg")
        self.assertEqual(validate_upload_image(valid_img), valid_img)

        # Invalid extension
        invalid_ext = SimpleUploadedFile("exploit.exe", b"binary", content_type="application/octet-stream")
        with self.assertRaises(serializers.ValidationError):
            validate_upload_image(invalid_ext)

        # Oversized image (> 5MB)
        oversized_data = b"x" * (6 * 1024 * 1024)
        oversized_img = SimpleUploadedFile("big.png", oversized_data, content_type="image/png")
        with self.assertRaises(serializers.ValidationError):
            validate_upload_image(oversized_img)

    def test_upload_document_validation(self):
        """Tests validate_upload_document enforces 10MB size limit and allowed formats."""
        # Valid PDF
        valid_doc = SimpleUploadedFile("registration.pdf", b"%PDF-1.4 sample", content_type="application/pdf")
        self.assertEqual(validate_upload_document(valid_doc), valid_doc)

        # Invalid extension
        invalid_doc = SimpleUploadedFile("script.sh", b"#!/bin/bash", content_type="text/plain")
        with self.assertRaises(serializers.ValidationError):
            validate_upload_document(invalid_doc)

        # Oversized document (> 10MB)
        oversized_doc_data = b"x" * (11 * 1024 * 1024)
        oversized_doc = SimpleUploadedFile("huge.pdf", oversized_doc_data, content_type="application/pdf")
        with self.assertRaises(serializers.ValidationError):
            validate_upload_document(oversized_doc)

    # 8. LOCATION CACHING (P3-FINDING-07)
    def test_location_caching(self):
        """Verifies location endpoints cache responses and reuse cached data."""
        cache.clear()

        # First hit
        resp1 = self.client.get('/api/locations/countries/')
        self.assertEqual(resp1.status_code, status.HTTP_200_OK)
        self.assertIn('data', resp1.json())

        # Verify stored in cache
        cached = cache.get("location_countries_all")
        self.assertIsNotNone(cached)
        self.assertEqual(cached['count'], resp1.json()['count'])

        # Second hit served from cache
        resp2 = self.client.get('/api/locations/countries/')
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        self.assertEqual(resp2.json(), cached)

    # 9. DEPLOYMENT SECURITY SETTINGS (P3-FINDING-06)
    def test_deployment_security_settings_in_dev_vs_prod(self):
        """Verifies development environment keeps debug-friendly flags, while security headers are enforced."""
        self.assertFalse(settings.SECURE_SSL_REDIRECT)
        self.assertFalse(settings.SESSION_COOKIE_SECURE)
        self.assertFalse(settings.CSRF_COOKIE_SECURE)
        self.assertEqual(settings.SECURE_HSTS_SECONDS, 0)
        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertEqual(settings.X_FRAME_OPTIONS, 'DENY')
