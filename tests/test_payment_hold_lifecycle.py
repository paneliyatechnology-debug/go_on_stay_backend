import time
import hmac
import hashlib
import json
import threading
from decimal import Decimal
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from django.test import TransactionTestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.conf import settings
from rest_framework.test import APIClient
from rest_framework import status

from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking
from payments.models import Payment, Refund, WebhookEvent
from rooms.utils import (
    get_available_room_count,
    get_room_numbers_availability,
    allocate_room_number_for_booking,
    release_temporary_hold,
    cleanup_expired_payment_holds,
    get_payment_hold_duration,
)

User = get_user_model()


class PaymentHoldLifecycleTests(TransactionTestCase):
    """
    Comprehensive test suite verifying the 15 mandated scenarios for:
    'GoOnStay – Immediate Room Unlock on Payment Exit'
    Strictly isolated: runs only in Django's isolated test database.
    """

    def setUp(self):
        self.client = APIClient()

        # Hotel Owner
        self.owner = User.objects.create_user(
            username='owner_ph',
            email='owner_ph@example.com',
            password='Password123!',
            role='HOTEL_OWNER',
            phone_number='9876543000'
        )

        # Customers
        self.cust_a = User.objects.create_user(
            username='cust_a_ph',
            email='cust_a_ph@example.com',
            password='Password123!',
            role='CUSTOMER',
            phone_number='9876543001'
        )
        self.cust_b = User.objects.create_user(
            username='cust_b_ph',
            email='cust_b_ph@example.com',
            password='Password123!',
            role='CUSTOMER',
            phone_number='9876543002'
        )

        # Hotel
        self.hotel = Hotel.objects.create(
            owner=self.owner,
            name='Ocean View Palace',
            city='Goa',
            address='Baga Beach Road',
            status='APPROVED',
            star_rating=5
        )

        # Room category with exactly ONE physical unit (Room 101)
        self.room_single = Room.objects.create(
            hotel=self.hotel,
            title='Deluxe Sea Suite',
            room_type='DELUXE',
            price_per_night=Decimal('3000.00'),
            total_rooms=1,
            room_numbers='101'
        )

        self.stay_in = date(2026, 12, 1)
        self.stay_out = date(2026, 12, 2)

    # -------------------------------------------------------------------------
    # Scenario 1: Payment initiated -> temporary room hold created
    # -------------------------------------------------------------------------
    @patch('payments.views.get_platform_razorpay_client')
    def test_01_payment_initiated_creates_temporary_room_hold(self, mock_rzp_client):
        mock_client = MagicMock()
        mock_client.order.create.return_value = {"id": "order_hold_001"}
        mock_rzp_client.return_value = (mock_client, 'rzp_test_key')

        booking = Booking.objects.create(
            booking_id='KH-HOLD-001',
            customer=self.cust_a,
            hotel=self.hotel,
            room=self.room_single,
            check_in=self.stay_in,
            check_out=self.stay_out,
            number_of_rooms=1,
            price_per_night=Decimal('3000.00'),
            number_of_nights=1,
            subtotal=Decimal('3000.00'),
            taxes=Decimal('540.00'),
            total_amount=Decimal('3540.00'),
            booking_status=Booking.STATUS_PENDING_PAYMENT,
            payment_status=Booking.PAYMENT_PENDING
        )

        self.client.force_authenticate(user=self.cust_a)
        res = self.client.post('/api/payments/create-order/', {'booking_id': booking.booking_id})
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        booking.refresh_from_db()
        self.assertIsNotNone(booking.expires_at)
        self.assertGreater(booking.expires_at, timezone.now())

        # Room availability with holds included must now be 0
        avail = get_available_room_count(self.room_single, self.stay_in, self.stay_out, include_holds=True)
        self.assertEqual(avail, 0)

    # -------------------------------------------------------------------------
    # Scenario 2: Customer cancels payment -> hold released immediately
    # -------------------------------------------------------------------------
    def test_02_customer_cancels_payment_releases_hold_immediately(self):
        booking = Booking.objects.create(
            booking_id='KH-HOLD-002',
            customer=self.cust_a,
            hotel=self.hotel,
            room=self.room_single,
            check_in=self.stay_in,
            check_out=self.stay_out,
            number_of_rooms=1,
            price_per_night=Decimal('3000.00'),
            number_of_nights=1,
            subtotal=Decimal('3000.00'),
            taxes=Decimal('540.00'),
            total_amount=Decimal('3540.00'),
            booking_status=Booking.STATUS_PENDING_PAYMENT,
            payment_status=Booking.PAYMENT_PENDING,
            expires_at=timezone.now() + timedelta(minutes=15)
        )

        self.client.force_authenticate(user=self.cust_a)
        res = self.client.post('/api/payments/cancel-payment/', {
            'booking_id': booking.booking_id,
            'reason': 'Customer clicked Cancel in checkout modal'
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data.get('success'))
        self.assertTrue(res.data.get('released'))

        booking.refresh_from_db()
        self.assertEqual(booking.booking_status, Booking.STATUS_EXPIRED)
        self.assertEqual(booking.payment_status, Booking.PAYMENT_FAILED)
        self.assertLess(booking.expires_at, timezone.now())

        # Physical room must be immediately available for other customers
        avail = get_available_room_count(self.room_single, self.stay_in, self.stay_out, include_holds=True)
        self.assertEqual(avail, 1)

    # -------------------------------------------------------------------------
    # Scenario 3: Razorpay payment fails -> hold released
    # -------------------------------------------------------------------------
    def test_03_razorpay_payment_fails_releases_hold(self):
        booking = Booking.objects.create(
            booking_id='KH-HOLD-003',
            customer=self.cust_a,
            hotel=self.hotel,
            room=self.room_single,
            check_in=self.stay_in,
            check_out=self.stay_out,
            number_of_rooms=1,
            price_per_night=Decimal('3000.00'),
            number_of_nights=1,
            subtotal=Decimal('3000.00'),
            taxes=Decimal('540.00'),
            total_amount=Decimal('3540.00'),
            booking_status=Booking.STATUS_PENDING_PAYMENT,
            payment_status=Booking.PAYMENT_PENDING,
            expires_at=timezone.now() + timedelta(minutes=15)
        )

        self.client.force_authenticate(user=self.cust_a)
        res = self.client.post('/api/payments/payment-failed/', {
            'booking_id': booking.booking_id,
            'error_code': 'BAD_REQUEST_ERROR',
            'error_description': 'Payment was declined by issuing bank'
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        booking.refresh_from_db()
        self.assertEqual(booking.booking_status, Booking.STATUS_EXPIRED)
        self.assertEqual(booking.payment_status, Booking.PAYMENT_FAILED)

        # Room immediately freed
        avail = get_available_room_count(self.room_single, self.stay_in, self.stay_out, include_holds=True)
        self.assertEqual(avail, 1)

    # -------------------------------------------------------------------------
    # Scenario 4: Gateway exit event received -> hold released
    # -------------------------------------------------------------------------
    def test_04_gateway_exit_event_received_releases_hold(self):
        booking = Booking.objects.create(
            booking_id='KH-HOLD-004',
            customer=self.cust_a,
            hotel=self.hotel,
            room=self.room_single,
            check_in=self.stay_in,
            check_out=self.stay_out,
            number_of_rooms=1,
            price_per_night=Decimal('3000.00'),
            number_of_nights=1,
            subtotal=Decimal('3000.00'),
            taxes=Decimal('540.00'),
            total_amount=Decimal('3540.00'),
            booking_status=Booking.STATUS_PENDING_PAYMENT,
            payment_status=Booking.PAYMENT_PENDING,
            expires_at=timezone.now() + timedelta(minutes=15)
        )

        self.client.force_authenticate(user=self.cust_a)
        res = self.client.post('/api/payments/cancel/', {
            'booking_id': booking.booking_id,
            'reason': 'modal.ondismiss event received'
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        booking.refresh_from_db()
        self.assertEqual(booking.booking_status, Booking.STATUS_EXPIRED)

        avail = get_available_room_count(self.room_single, self.stay_in, self.stay_out, include_holds=True)
        self.assertEqual(avail, 1)

    # -------------------------------------------------------------------------
    # Scenario 5: Browser closes without event -> fallback expiry releases hold
    # -------------------------------------------------------------------------
    def test_05_browser_closes_without_event_fallback_expiry_releases_hold(self):
        # Booking created with expires_at in the past (simulating elapsed 15m without frontend callback)
        booking = Booking.objects.create(
            booking_id='KH-HOLD-005',
            customer=self.cust_a,
            hotel=self.hotel,
            room=self.room_single,
            check_in=self.stay_in,
            check_out=self.stay_out,
            number_of_rooms=1,
            price_per_night=Decimal('3000.00'),
            number_of_nights=1,
            subtotal=Decimal('3000.00'),
            taxes=Decimal('540.00'),
            total_amount=Decimal('3540.00'),
            booking_status=Booking.STATUS_PENDING_PAYMENT,
            payment_status=Booking.PAYMENT_PENDING,
            expires_at=timezone.now() - timedelta(minutes=1)  # elapsed
        )

        # Dynamic read check: room must be available even before background job runs
        avail = get_available_room_count(self.room_single, self.stay_in, self.stay_out, include_holds=True)
        self.assertEqual(avail, 1, "Expired hold must not block availability on live reads!")

    # -------------------------------------------------------------------------
    # Scenario 6: Internet disconnects -> fallback expiry works
    # -------------------------------------------------------------------------
    def test_06_internet_disconnects_fallback_expiry_works(self):
        booking = Booking.objects.create(
            booking_id='KH-HOLD-006',
            customer=self.cust_a,
            hotel=self.hotel,
            room=self.room_single,
            check_in=self.stay_in,
            check_out=self.stay_out,
            number_of_rooms=1,
            price_per_night=Decimal('3000.00'),
            number_of_nights=1,
            subtotal=Decimal('3000.00'),
            taxes=Decimal('540.00'),
            total_amount=Decimal('3540.00'),
            booking_status=Booking.STATUS_PENDING_PAYMENT,
            payment_status=Booking.PAYMENT_PENDING,
            expires_at=timezone.now() - timedelta(seconds=10)
        )

        # Run scheduled/housekeeping cleanup
        released = cleanup_expired_payment_holds()
        self.assertGreaterEqual(released, 1)

        booking.refresh_from_db()
        self.assertEqual(booking.booking_status, Booking.STATUS_EXPIRED)
        self.assertEqual(booking.payment_status, Booking.PAYMENT_FAILED)

    # -------------------------------------------------------------------------
    # Scenario 7: Successful payment -> booking confirmed & room allocated
    # -------------------------------------------------------------------------
    @patch('payments.views.get_platform_razorpay_client')
    def test_07_successful_payment_confirms_booking_and_allocates_room(self, mock_rzp_client):
        mock_client = MagicMock()
        mock_client.payment.fetch.return_value = {
            'id': 'pay_succ_007',
            'amount': 354000,
            'currency': 'INR',
            'status': 'captured',
            'method': 'card'
        }
        mock_rzp_client.return_value = (mock_client, 'rzp_test_key')

        booking = Booking.objects.create(
            booking_id='KH-HOLD-007',
            customer=self.cust_a,
            hotel=self.hotel,
            room=self.room_single,
            check_in=self.stay_in,
            check_out=self.stay_out,
            number_of_rooms=1,
            price_per_night=Decimal('3000.00'),
            number_of_nights=1,
            subtotal=Decimal('3000.00'),
            taxes=Decimal('540.00'),
            total_amount=Decimal('3540.00'),
            booking_status=Booking.STATUS_PENDING_PAYMENT,
            payment_status=Booking.PAYMENT_PENDING,
            razorpay_order_id='order_succ_007',
            expires_at=timezone.now() + timedelta(minutes=15)
        )

        order_id = 'order_succ_007'
        pay_id = 'pay_succ_007'
        sig = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode('utf-8'),
            f"{order_id}|{pay_id}".encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        self.client.force_authenticate(user=self.cust_a)
        res = self.client.post('/api/payments/verify/', {
            'booking_id': booking.booking_id,
            'razorpay_order_id': order_id,
            'razorpay_payment_id': pay_id,
            'razorpay_signature': sig
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        booking.refresh_from_db()
        self.assertEqual(booking.booking_status, Booking.STATUS_CONFIRMED)
        self.assertEqual(booking.payment_status, Booking.PAYMENT_PAID)
        self.assertEqual(booking.room_number, '101')

    # -------------------------------------------------------------------------
    # Scenario 8: Delayed callback after hold expiry -> overbooked room never confirmed
    # -------------------------------------------------------------------------
    @patch('payments.views.execute_refund_with_provider')
    @patch('payments.views.get_platform_razorpay_client')
    def test_08_delayed_callback_after_hold_expiry_unavailable_room_never_confirmed(
        self, mock_rzp_client, mock_execute_refund
    ):
        mock_client = MagicMock()
        mock_client.payment.fetch.return_value = {
            'id': 'pay_delayed_008',
            'amount': 354000,
            'currency': 'INR',
            'status': 'captured',
            'method': 'card'
        }
        mock_rzp_client.return_value = (mock_client, 'rzp_test_key')

        # Booking A had hold expire
        booking_a = Booking.objects.create(
            booking_id='KH-HOLD-008-A',
            customer=self.cust_a,
            hotel=self.hotel,
            room=self.room_single,
            check_in=self.stay_in,
            check_out=self.stay_out,
            number_of_rooms=1,
            price_per_night=Decimal('3000.00'),
            number_of_nights=1,
            subtotal=Decimal('3000.00'),
            taxes=Decimal('540.00'),
            total_amount=Decimal('3540.00'),
            booking_status=Booking.STATUS_EXPIRED,
            payment_status=Booking.PAYMENT_FAILED,
            razorpay_order_id='order_delayed_008',
            expires_at=timezone.now() - timedelta(minutes=5)
        )

        # Meanwhile, Customer B booked and acquired Room 101
        Booking.objects.create(
            booking_id='KH-HOLD-008-B',
            customer=self.cust_b,
            hotel=self.hotel,
            room=self.room_single,
            check_in=self.stay_in,
            check_out=self.stay_out,
            number_of_rooms=1,
            price_per_night=Decimal('3000.00'),
            number_of_nights=1,
            subtotal=Decimal('3000.00'),
            taxes=Decimal('540.00'),
            total_amount=Decimal('3540.00'),
            booking_status=Booking.STATUS_CONFIRMED,
            payment_status=Booking.PAYMENT_PAID,
            room_number='101'
        )

        order_id = 'order_delayed_008'
        pay_id = 'pay_delayed_008'
        sig = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode('utf-8'),
            f"{order_id}|{pay_id}".encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        # Customer A's delayed payment arrives
        self.client.force_authenticate(user=self.cust_a)
        res = self.client.post('/api/payments/verify/', {
            'booking_id': booking_a.booking_id,
            'razorpay_order_id': order_id,
            'razorpay_payment_id': pay_id,
            'razorpay_signature': sig
        })

        booking_a.refresh_from_db()
        self.assertNotEqual(booking_a.booking_status, Booking.STATUS_CONFIRMED)
        self.assertEqual(booking_a.booking_status, Booking.STATUS_CANCELLED)
        self.assertEqual(booking_a.payment_status, Booking.PAYMENT_REFUND_PENDING)
        self.assertIsNone(booking_a.room_number)
        mock_execute_refund.assert_called_once()

    # -------------------------------------------------------------------------
    # Scenario 9: Another customer books released room -> delayed callback cannot steal it
    # -------------------------------------------------------------------------
    @patch('payments.views.execute_refund_with_provider')
    @patch('payments.views.get_platform_razorpay_client')
    def test_09_another_customer_books_released_room_delayed_callback_cannot_steal_it(
        self, mock_rzp_client, mock_execute_refund
    ):
        mock_client = MagicMock()
        mock_client.payment.fetch.return_value = {
            'id': 'pay_steal_009',
            'amount': 354000,
            'currency': 'INR',
            'status': 'captured',
            'method': 'upi'
        }
        mock_rzp_client.return_value = (mock_client, 'rzp_test_key')

        booking_a = Booking.objects.create(
            booking_id='KH-HOLD-009-A',
            customer=self.cust_a,
            hotel=self.hotel,
            room=self.room_single,
            check_in=self.stay_in,
            check_out=self.stay_out,
            number_of_rooms=1,
            price_per_night=Decimal('3000.00'),
            number_of_nights=1,
            subtotal=Decimal('3000.00'),
            taxes=Decimal('540.00'),
            total_amount=Decimal('3540.00'),
            booking_status=Booking.STATUS_EXPIRED,
            payment_status=Booking.PAYMENT_FAILED,
            razorpay_order_id='order_steal_009',
            expires_at=timezone.now() - timedelta(minutes=10)
        )

        booking_b = Booking.objects.create(
            booking_id='KH-HOLD-009-B',
            customer=self.cust_b,
            hotel=self.hotel,
            room=self.room_single,
            check_in=self.stay_in,
            check_out=self.stay_out,
            number_of_rooms=1,
            price_per_night=Decimal('3000.00'),
            number_of_nights=1,
            subtotal=Decimal('3000.00'),
            taxes=Decimal('540.00'),
            total_amount=Decimal('3540.00'),
            booking_status=Booking.STATUS_CONFIRMED,
            payment_status=Booking.PAYMENT_PAID,
            room_number='101'
        )

        order_id = 'order_steal_009'
        pay_id = 'pay_steal_009'
        sig = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode('utf-8'),
            f"{order_id}|{pay_id}".encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        self.client.force_authenticate(user=self.cust_a)
        self.client.post('/api/payments/verify/', {
            'booking_id': booking_a.booking_id,
            'razorpay_order_id': order_id,
            'razorpay_payment_id': pay_id,
            'razorpay_signature': sig
        })

        booking_b.refresh_from_db()
        self.assertEqual(booking_b.room_number, '101', "Customer B's room must never be stolen!")
        self.assertEqual(booking_b.booking_status, Booking.STATUS_CONFIRMED)

    # -------------------------------------------------------------------------
    # Scenario 10: Duplicate webhook -> no duplicate allocation or refund
    # -------------------------------------------------------------------------
    @patch('payments.views.get_razorpay_client')
    def test_10_duplicate_webhook_no_duplicate_allocation_or_refund(self, mock_client_fn):
        mock_client = MagicMock()
        mock_client_fn.return_value = (mock_client, 'rzp_test_key')

        booking = Booking.objects.create(
            booking_id='KH-HOLD-010',
            customer=self.cust_a,
            hotel=self.hotel,
            room=self.room_single,
            check_in=self.stay_in,
            check_out=self.stay_out,
            number_of_rooms=1,
            price_per_night=Decimal('3000.00'),
            number_of_nights=1,
            subtotal=Decimal('3000.00'),
            taxes=Decimal('540.00'),
            total_amount=Decimal('3540.00'),
            booking_status=Booking.STATUS_PENDING_PAYMENT,
            payment_status=Booking.PAYMENT_PENDING
        )

        payment = Payment.objects.create(
            booking=booking,
            user=self.cust_a,
            razorpay_order_id='order_wh_010',
            amount=Decimal('3540.00'),
            currency='INR',
            status=Payment.STATUS_CREATED
        )

        payload = {
            "event_id": "evt_test_dup_010",
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_dup_010",
                        "order_id": "order_wh_010",
                        "amount": 354000,
                        "currency": "INR",
                        "status": "captured"
                    }
                }
            }
        }
        body_bytes = json.dumps(payload).encode('utf-8')
        sig = hmac.new(
            settings.RAZORPAY_WEBHOOK_SECRET.encode('utf-8'),
            body_bytes,
            hashlib.sha256
        ).hexdigest()

        # First webhook delivery
        res1 = self.client.post(
            '/api/payments/webhook/',
            data=body_bytes,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=sig
        )
        self.assertEqual(res1.status_code, status.HTTP_200_OK)

        booking.refresh_from_db()
        self.assertEqual(booking.booking_status, Booking.STATUS_CONFIRMED)
        self.assertEqual(booking.room_number, '101')

        # Second (duplicate) webhook delivery
        res2 = self.client.post(
            '/api/payments/webhook/',
            data=body_bytes,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=sig
        )
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(res2.data.get('status'), 'ignored')

    # -------------------------------------------------------------------------
    # Scenario 11: Concurrent customers attempt to acquire final room -> only one succeeds
    # -------------------------------------------------------------------------
    def test_11_concurrent_customers_attempt_acquire_final_room_only_one_succeeds(self):
        results = []
        lock = threading.Lock()

        def attempt_booking(user):
            client = APIClient()
            client.force_authenticate(user=user)
            res = client.post('/api/bookings/', {
                'hotel': self.hotel.id,
                'room': self.room_single.id,
                'check_in': self.stay_in.isoformat(),
                'check_out': self.stay_out.isoformat(),
                'number_of_rooms': 1,
                'guest_name': user.username,
                'guest_email': user.email,
                'guest_phone': '9876543210'
            }, format='json')
            with lock:
                results.append((user.username, res.status_code, res.data))

        t1 = threading.Thread(target=attempt_booking, args=(self.cust_a,))
        t2 = threading.Thread(target=attempt_booking, args=(self.cust_b,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        success_count = sum(1 for _, sc, _ in results if sc == status.HTTP_201_CREATED)
        conflict_count = sum(1 for _, sc, _ in results if sc == status.HTTP_409_CONFLICT)

        self.assertEqual(success_count, 1, "Exactly one customer must acquire the final room!")
        self.assertEqual(conflict_count, 1, "The competing customer must receive HTTP 409 Conflict!")

    # -------------------------------------------------------------------------
    # Scenario 12: Already confirmed booking -> never expired or unlocked
    # -------------------------------------------------------------------------
    def test_12_already_confirmed_booking_never_expired_or_unlocked(self):
        booking = Booking.objects.create(
            booking_id='KH-HOLD-012',
            customer=self.cust_a,
            hotel=self.hotel,
            room=self.room_single,
            check_in=self.stay_in,
            check_out=self.stay_out,
            number_of_rooms=1,
            price_per_night=Decimal('3000.00'),
            number_of_nights=1,
            subtotal=Decimal('3000.00'),
            taxes=Decimal('540.00'),
            total_amount=Decimal('3540.00'),
            booking_status=Booking.STATUS_CONFIRMED,
            payment_status=Booking.PAYMENT_PAID,
            room_number='101'
        )

        self.client.force_authenticate(user=self.cust_a)
        res = self.client.post('/api/payments/cancel-payment/', {
            'booking_id': booking.booking_id
        })
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        booking.refresh_from_db()
        self.assertEqual(booking.booking_status, Booking.STATUS_CONFIRMED)
        self.assertEqual(booking.room_number, '101')

        # Direct function check
        released = release_temporary_hold(booking, reason="Malicious unlock test")
        self.assertFalse(released, "release_temporary_hold must refuse to touch confirmed bookings!")
        booking.refresh_from_db()
        self.assertEqual(booking.booking_status, Booking.STATUS_CONFIRMED)

    # -------------------------------------------------------------------------
    # Scenario 13: Already paid booking -> never incorrectly marked PAYMENT_FAILED
    # -------------------------------------------------------------------------
    def test_13_already_paid_booking_never_marked_payment_failed(self):
        booking = Booking.objects.create(
            booking_id='KH-HOLD-013',
            customer=self.cust_a,
            hotel=self.hotel,
            room=self.room_single,
            check_in=self.stay_in,
            check_out=self.stay_out,
            number_of_rooms=1,
            price_per_night=Decimal('3000.00'),
            number_of_nights=1,
            subtotal=Decimal('3000.00'),
            taxes=Decimal('540.00'),
            total_amount=Decimal('3540.00'),
            booking_status=Booking.STATUS_CONFIRMED,
            payment_status=Booking.PAYMENT_PAID,
            room_number='101'
        )

        self.client.force_authenticate(user=self.cust_a)
        res = self.client.post('/api/payments/payment-failed/', {
            'booking_id': booking.booking_id,
            'error_code': 'CANCELLED',
            'error_description': 'Customer claims payment failed'
        })
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, Booking.PAYMENT_PAID)
        self.assertEqual(booking.booking_status, Booking.STATUS_CONFIRMED)

    # -------------------------------------------------------------------------
    # Scenario 14: Expired hold -> no longer blocks availability
    # -------------------------------------------------------------------------
    def test_14_expired_hold_no_longer_blocks_availability(self):
        booking = Booking.objects.create(
            booking_id='KH-HOLD-014',
            customer=self.cust_a,
            hotel=self.hotel,
            room=self.room_single,
            check_in=self.stay_in,
            check_out=self.stay_out,
            number_of_rooms=1,
            price_per_night=Decimal('3000.00'),
            number_of_nights=1,
            subtotal=Decimal('3000.00'),
            taxes=Decimal('540.00'),
            total_amount=Decimal('3540.00'),
            booking_status=Booking.STATUS_PENDING_PAYMENT,
            payment_status=Booking.PAYMENT_PENDING,
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        avail = get_available_room_count(self.room_single, self.stay_in, self.stay_out, include_holds=True)
        self.assertEqual(avail, 1, "An expired hold must immediately free room inventory on all availability checks!")

    # -------------------------------------------------------------------------
    # Scenario 15: Refund retries -> no duplicate refunds
    # -------------------------------------------------------------------------
    @patch('payments.views.get_platform_razorpay_client')
    def test_15_refund_retries_no_duplicate_refunds(self, mock_rzp_client):
        from payments.views import execute_refund_with_provider

        mock_client = MagicMock()
        mock_client.payment.refund.return_value = {
            'id': 'rfnd_test_015',
            'status': 'processed',
            'amount': 354000
        }
        mock_rzp_client.return_value = (mock_client, 'rzp_test_key')

        booking = Booking.objects.create(
            booking_id='KH-HOLD-015',
            customer=self.cust_a,
            hotel=self.hotel,
            room=self.room_single,
            check_in=self.stay_in,
            check_out=self.stay_out,
            number_of_rooms=1,
            price_per_night=Decimal('3000.00'),
            number_of_nights=1,
            subtotal=Decimal('3000.00'),
            taxes=Decimal('540.00'),
            total_amount=Decimal('3540.00'),
            booking_status=Booking.STATUS_CANCELLED,
            payment_status=Booking.PAYMENT_REFUNDED
        )

        payment = Payment.objects.create(
            booking=booking,
            user=self.cust_a,
            razorpay_order_id='order_rfnd_015',
            razorpay_payment_id='pay_rfnd_015',
            amount=Decimal('3540.00'),
            currency='INR',
            status=Payment.STATUS_CAPTURED
        )

        refund_record = Refund.objects.create(
            booking=booking,
            payment=payment,
            razorpay_payment_id='pay_rfnd_015',
            razorpay_refund_id='rfnd_existing_015',
            status=Refund.STATUS_REFUNDED,
            amount=Decimal('3540.00'),
            currency='INR',
            reason='Test refund retry'
        )

        # Call execute_refund_with_provider on an already processed refund
        execute_refund_with_provider(
            refund_record=refund_record,
            booking_locked=booking,
            captured_payment=payment,
            refund_amount=Decimal('3540.00'),
            reason='Retry attempt'
        )

        # The mock Razorpay refund API must NOT have been called again!
        mock_client.payment.refund.assert_not_called()
