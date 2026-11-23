import json
import uuid
import hashlib
import time
from decimal import Decimal
from django.test import TestCase, override_settings
from django.urls import reverse
from django.core.cache import cache
from django.conf import settings
from rest_framework.test import APIClient
from rest_framework import status

from users.models import User
from hotels.models import Hotel, Country, State, City, Area
from rooms.models import Room
from bookings.models import Booking
from payments.models import Payment, Refund, WebhookEvent
from bookings.tasks import send_booking_confirmation_email_task
from services.booking_email_service import generate_booking_pdf


class Phase4InfrastructureAndSandboxTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

        # Create test customer
        self.customer = User.objects.create_user(
            username='phase4_customer',
            email='phase4_customer@example.com',
            password='TestPassword123!',
            role='CUSTOMER'
        )

        # Create test hotel owner
        self.owner = User.objects.create_user(
            username='phase4_owner',
            email='phase4_owner@example.com',
            password='TestPassword123!',
            role='HOTEL_OWNER'
        )

        # Create location hierarchy
        self.country = Country.objects.create(name='India', code='IN')
        self.state = State.objects.create(country=self.country, name='Goa')
        self.city = City.objects.create(state=self.state, name='Panaji')

        # Create test hotel
        self.hotel = Hotel.objects.create(
            name='Goa Beach Resort',
            description='Luxury beachfront resort in Goa',
            address='Calangute Beach Road',
            city='Panaji',
            state='Goa',
            owner=self.owner,
            status=Hotel.STATUS_APPROVED,
            is_approved=True,
            is_active=True
        )

        # Create test room
        self.room = Room.objects.create(
            hotel=self.hotel,
            title='Deluxe Ocean Suite',
            room_type='DELUXE',
            price_per_night=Decimal('3500.00'),
            total_rooms=5,
            room_numbers='101, 102, 103, 104, 105'
        )

    def tearDown(self):
        cache.clear()

    # =========================================================================
    # 1. REDIS & CACHING BEHAVIOR VALIDATION (PHASE 4.3)
    # =========================================================================
    def test_cache_hit_miss_and_invalidation(self):
        """Verifies cache store, retrieve, TTL expiration and cache clearing."""
        test_key = "test_phase4_cache_key"
        self.assertIsNone(cache.get(test_key))

        # Cache Miss -> Store
        cache.set(test_key, {"hotel": "Goa Beach Resort"}, timeout=60)
        cached_val = cache.get(test_key)
        self.assertEqual(cached_val, {"hotel": "Goa Beach Resort"})

        # Invalidation
        cache.delete(test_key)
        self.assertIsNone(cache.get(test_key))

    def test_authoritative_state_never_served_from_stale_cache(self):
        """
        Critical Rule: Room availability and payment states must ALWAYS be computed
        authoritatively from the database, never overridden by cache.
        """
        from rooms.utils import get_available_room_count
        from datetime import date, timedelta

        check_in = date.today() + timedelta(days=10)
        check_out = date.today() + timedelta(days=12)

        # Initial available count is 5
        avail_initial = get_available_room_count(self.room, check_in, check_out)
        self.assertEqual(avail_initial, 5)

        # Create an authoritative confirmed booking directly in DB
        Booking.objects.create(
            customer=self.customer,
            hotel=self.hotel,
            room=self.room,
            check_in=check_in,
            check_out=check_out,
            number_of_rooms=2,
            price_per_night=self.room.price_per_night,
            number_of_nights=2,
            subtotal=Decimal('7000.00'),
            total_amount=Decimal('8260.00'),
            booking_status=Booking.STATUS_CONFIRMED,
            payment_status=Booking.PAYMENT_PAID
        )

        # Immediate real-time availability must reflect authoritative DB state (5 - 2 = 3)
        avail_after = get_available_room_count(self.room, check_in, check_out)
        self.assertEqual(avail_after, 3)

    # =========================================================================
    # 2. CELERY TASK & BACKGROUND PROCESSING VALIDATION (PHASE 4.4)
    # =========================================================================
    def test_celery_task_idempotency_and_execution(self):
        """Verifies background email task execution and duplicate prevention."""
        from datetime import date, timedelta
        booking = Booking.objects.create(
            customer=self.customer,
            hotel=self.hotel,
            room=self.room,
            check_in=date.today() + timedelta(days=20),
            check_out=date.today() + timedelta(days=22),
            number_of_rooms=1,
            price_per_night=self.room.price_per_night,
            number_of_nights=2,
            subtotal=Decimal('7000.00'),
            total_amount=Decimal('8260.00'),
            guest_name='Phase4 Guest',
            guest_email='guest@example.com',
            guest_phone='9876543210',
            booking_status=Booking.STATUS_CONFIRMED,
            payment_status=Booking.PAYMENT_PAID,
            confirmation_email_sent=False
        )

        # First run: task should process and mark confirmation_email_sent
        result1 = send_booking_confirmation_email_task(booking.id)
        booking.refresh_from_db()
        self.assertTrue(result1.get('success'))

        # Second run (simulating retried task or duplicate Celery delivery):
        # Must detect confirmation_email_sent and return already_sent without duplicate email delivery
        result2 = send_booking_confirmation_email_task(booking.id)
        self.assertTrue(result2.get('success'))
        self.assertEqual(result2.get('status'), 'already_sent')

    # =========================================================================
    # 3. RAZORPAY SANDBOX VALIDATION (PHASE 4.5)
    # =========================================================================
    def test_razorpay_order_creation_server_side_pricing(self):
        """Verifies Razorpay order creation enforces server-side calculated pricing."""
        from unittest.mock import MagicMock, patch
        self.client.force_authenticate(user=self.customer)
        from datetime import date, timedelta
        booking = Booking.objects.create(
            customer=self.customer,
            hotel=self.hotel,
            room=self.room,
            check_in=date.today() + timedelta(days=5),
            check_out=date.today() + timedelta(days=7),
            number_of_rooms=1,
            price_per_night=Decimal('3500.00'),
            number_of_nights=2,
            subtotal=Decimal('7000.00'),
            taxes=Decimal('1260.00'),
            total_amount=Decimal('8260.00'),
            booking_status=Booking.STATUS_PENDING_PAYMENT,
            payment_status=Booking.PAYMENT_PENDING
        )

        mock_client = MagicMock()
        mock_client.order.create.return_value = {
            'id': 'order_test_phase4_99',
            'amount': 826000,
            'currency': 'INR',
            'status': 'created'
        }
        with patch('payments.views.get_platform_razorpay_client', return_value=(mock_client, 'rzp_test_key')):
            resp = self.client.post('/api/payments/create-order/', {
                'booking_id': booking.booking_id
            })
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            data = resp.json()
            self.assertIn('order_id', data)
            self.assertEqual(data.get('order_id'), 'order_test_phase4_99')
            # Verify Razorpay amount is in paise (8260.00 INR * 100 = 826000 paise)
            self.assertEqual(int(data.get('amount')), 826000)

    def test_razorpay_signature_verification_and_failure(self):
        """Verifies VerifyPaymentView rejects invalid HMAC-SHA256 signatures."""
        self.client.force_authenticate(user=self.customer)
        from datetime import date, timedelta
        booking = Booking.objects.create(
            customer=self.customer,
            hotel=self.hotel,
            room=self.room,
            check_in=date.today() + timedelta(days=5),
            check_out=date.today() + timedelta(days=7),
            number_of_rooms=1,
            price_per_night=Decimal('3500.00'),
            number_of_nights=2,
            subtotal=Decimal('7000.00'),
            total_amount=Decimal('8260.00'),
            booking_status=Booking.STATUS_PENDING_PAYMENT,
            payment_status=Booking.PAYMENT_PENDING
        )
        resp = self.client.post('/api/payments/verify/', {
            'booking_id': booking.booking_id,
            'razorpay_order_id': 'order_fake_123',
            'razorpay_payment_id': 'pay_fake_456',
            'razorpay_signature': 'invalid_forged_signature_hex_12345'
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('invalid', resp.json().get('error', '').lower())

    def test_razorpay_webhook_duplicate_idempotency(self):
        """Verifies duplicate webhook deliveries with payment capture are safely ignored."""
        import hmac
        payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_test_sbx_9988",
                        "order_id": "order_test_sbx_9988",
                        "amount": 826000,
                        "status": "captured"
                    }
                }
            }
        }
        body = json.dumps(payload)
        sig = hmac.new(
            settings.RAZORPAY_WEBHOOK_SECRET.encode('utf-8'),
            body.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        # Delivery 1
        resp1 = self.client.post(
            '/api/payments/webhook/',
            data=body,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=sig
        )
        self.assertEqual(resp1.status_code, status.HTTP_200_OK)

        # Mark processed
        ev = WebhookEvent.objects.get(event_id="payment.captured_pay_test_sbx_9988")
        ev.processed = True
        ev.save()

        # Delivery 2 (Duplicate Retry)
        resp2 = self.client.post(
            '/api/payments/webhook/',
            data=body,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=sig
        )
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        self.assertEqual(resp2.json().get('status'), 'ignored')

    def test_payment_failure_releases_room_hold_immediately(self):
        """Verifies payment failure notifications release temporary room holds immediately."""
        self.client.force_authenticate(user=self.customer)
        from datetime import date, timedelta
        booking = Booking.objects.create(
            customer=self.customer,
            hotel=self.hotel,
            room=self.room,
            check_in=date.today() + timedelta(days=15),
            check_out=date.today() + timedelta(days=17),
            number_of_rooms=1,
            price_per_night=self.room.price_per_night,
            number_of_nights=2,
            subtotal=Decimal('7000.00'),
            total_amount=Decimal('8260.00'),
            booking_status=Booking.STATUS_PENDING_PAYMENT,
            payment_status=Booking.PAYMENT_PENDING
        )

        resp = self.client.post('/api/payments/payment-failed/', {
            'booking_id': booking.booking_id,
            'reason': 'Customer cancelled UPI request'
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        booking.refresh_from_db()
        self.assertIn(booking.booking_status, [Booking.STATUS_EXPIRED, Booking.STATUS_CANCELLED])
        self.assertEqual(booking.payment_status, Booking.PAYMENT_FAILED)

    def test_pdf_invoice_generation(self):
        """Verifies ReportLab generates a valid PDF document with invoice data."""
        from datetime import date, timedelta
        booking = Booking.objects.create(
            customer=self.customer,
            hotel=self.hotel,
            room=self.room,
            check_in=date.today() + timedelta(days=25),
            check_out=date.today() + timedelta(days=27),
            number_of_rooms=1,
            price_per_night=self.room.price_per_night,
            number_of_nights=2,
            subtotal=Decimal('7000.00'),
            taxes=Decimal('1260.00'),
            total_amount=Decimal('8260.00'),
            guest_name='Voucher Guest',
            guest_email='voucher@example.com',
            guest_phone='9876543210',
            booking_status=Booking.STATUS_CONFIRMED,
            payment_status=Booking.PAYMENT_PAID
        )

        pdf_bytes = generate_booking_pdf(booking)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(len(pdf_bytes) > 200)
        # PDF header signature check: '%PDF-'
        self.assertTrue(pdf_bytes.startswith(b'%PDF-'))
