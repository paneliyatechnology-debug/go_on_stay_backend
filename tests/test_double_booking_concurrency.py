import time
import threading
from decimal import Decimal
from datetime import date
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch, MagicMock

from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking
from payments.models import Payment, Refund
from rooms.utils import (
    get_available_room_count,
    get_room_numbers_availability,
    allocate_room_number_for_booking,
)

User = get_user_model()


class DoubleBookingConcurrencyTests(TransactionTestCase):
    """
    Test suite verifying physical room allocation, concurrency safety,
    pre-payment validation, and automatic refund on race condition overbooking.
    """

    def setUp(self):
        self.client = APIClient()

        # Hotel Owner
        self.owner = User.objects.create_user(
            username='test_hotel_owner_db',
            email='owner_db@example.com',
            password='Password123!',
            role='HOTEL_OWNER',
            phone_number='9876543210'
        )

        # Customers
        self.customer_a = User.objects.create_user(
            username='cust_a_db',
            email='customer_a@example.com',
            password='Password123!',
            role='CUSTOMER',
            phone_number='9876543211'
        )
        self.customer_b = User.objects.create_user(
            username='cust_b_db',
            email='customer_b@example.com',
            password='Password123!',
            role='CUSTOMER',
            phone_number='9876543212'
        )

        # Hotel
        self.hotel = Hotel.objects.create(
            owner=self.owner,
            name='GoOnStay Grand Heritage',
            city='Mumbai',
            address='123 Marine Drive',
            status='APPROVED',
            star_rating=5
        )

        # Room with exactly ONE physical unit (Room 101)
        self.single_unit_room = Room.objects.create(
            hotel=self.hotel,
            title='Deluxe Single Room',
            room_type='DELUXE',
            price_per_night=Decimal('2500.00'),
            total_rooms=1,
            room_numbers='101'
        )

        # Room with TWO physical units (Room 101, Room 102)
        self.dual_unit_room = Room.objects.create(
            hotel=self.hotel,
            title='Executive Double Room',
            room_type='EXECUTIVE',
            price_per_night=Decimal('2500.00'),
            total_rooms=2,
            room_numbers='101, 102'
        )

        self.stay_check_in = date(2026, 11, 18)
        self.stay_check_out = date(2026, 11, 19)

    def test_01_customer_a_books_and_pays_customer_b_cannot_get_room_101(self):
        """
        Customer A books and pays for Room 101 for 18-19 November 2026.
        Customer B attempts to book the same room for the same dates.
        Customer B must not receive Room 101; pre-payment order creation must be rejected.
        """
        # 1. Customer A creates a booking
        booking_a = Booking.objects.create(
            booking_id='KH-TEST-A101',
            customer=self.customer_a,
            hotel=self.hotel,
            room=self.single_unit_room,
            check_in=self.stay_check_in,
            check_out=self.stay_check_out,
            number_of_guests=2,
            number_of_rooms=1,
            price_per_night=Decimal('2500.00'),
            number_of_nights=1,
            subtotal=Decimal('2500.00'),
            taxes=Decimal('450.00'),
            total_amount=Decimal('2950.00'),
            booking_status=Booking.STATUS_PENDING_PAYMENT,
            payment_status=Booking.PAYMENT_PENDING
        )

        # Customer A pays and is confirmed
        allocated_a = allocate_room_number_for_booking(booking_a)
        self.assertEqual(allocated_a, '101')
        booking_a.booking_status = Booking.STATUS_CONFIRMED
        booking_a.payment_status = Booking.PAYMENT_PAID
        booking_a.save()

        # 2. Verify remaining physical room availability for 18-19 Nov is now ZERO
        avail_count = get_available_room_count(self.single_unit_room, self.stay_check_in, self.stay_check_out)
        self.assertEqual(avail_count, 0)

        # 3. Customer B attempts to create an order for the same room and dates
        booking_b = Booking.objects.create(
            booking_id='KH-TEST-B101',
            customer=self.customer_b,
            hotel=self.hotel,
            room=self.single_unit_room,
            check_in=self.stay_check_in,
            check_out=self.stay_check_out,
            number_of_guests=2,
            number_of_rooms=1,
            price_per_night=Decimal('2500.00'),
            number_of_nights=1,
            subtotal=Decimal('2500.00'),
            taxes=Decimal('450.00'),
            total_amount=Decimal('2950.00'),
            booking_status=Booking.STATUS_PENDING_PAYMENT,
            payment_status=Booking.PAYMENT_PENDING
        )

        self.client.force_authenticate(user=self.customer_b)
        response = self.client.post('/api/payments/create-order/', {
            'booking_id': booking_b.booking_id
        }, format='json')

        # Order creation must be rejected because 0 rooms are available!
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data.get('code'), 'ROOMS_SOLD_OUT')
        self.assertIn("booked", response.data.get('message', '').lower())
        self.assertEqual(response.data.get('available_rooms'), 0)

        # Attempting allocation directly on booking_b must return None (NEVER '101')
        allocated_b = allocate_room_number_for_booking(booking_b)
        self.assertIsNone(allocated_b)
        self.assertNotEqual(booking_b.room_number, '101')

    def test_02_dual_room_allocates_different_units(self):
        """
        When Room 101 is booked, Customer B booking the same category receives Room 102,
        never a duplicate Room 101.
        """
        # Customer A books dual-unit room with preference for 101
        booking_a = Booking.objects.create(
            booking_id='KH-TEST-DUAL-A',
            customer=self.customer_a,
            hotel=self.hotel,
            room=self.dual_unit_room,
            check_in=self.stay_check_in,
            check_out=self.stay_check_out,
            number_of_guests=2,
            number_of_rooms=1,
            price_per_night=Decimal('2500.00'),
            number_of_nights=1,
            subtotal=Decimal('2500.00'),
            taxes=Decimal('450.00'),
            total_amount=Decimal('2950.00'),
            booking_status=Booking.STATUS_CONFIRMED,
            payment_status=Booking.PAYMENT_PAID
        )
        allocated_a = allocate_room_number_for_booking(booking_a)
        self.assertEqual(allocated_a, '101')

        # Customer B books same room category for same dates
        booking_b = Booking.objects.create(
            booking_id='KH-TEST-DUAL-B',
            customer=self.customer_b,
            hotel=self.hotel,
            room=self.dual_unit_room,
            check_in=self.stay_check_in,
            check_out=self.stay_check_out,
            number_of_guests=2,
            number_of_rooms=1,
            price_per_night=Decimal('2500.00'),
            number_of_nights=1,
            subtotal=Decimal('2500.00'),
            taxes=Decimal('450.00'),
            total_amount=Decimal('2950.00'),
            booking_status=Booking.STATUS_PENDING_PAYMENT,
            payment_status=Booking.PAYMENT_PENDING
        )
        allocated_b = allocate_room_number_for_booking(booking_b)
        self.assertEqual(allocated_b, '102')
        self.assertNotEqual(allocated_b, '101')

    def test_03_race_condition_overbooking_triggers_automatic_refund(self):
        """
        If payment succeeds on Razorpay but room allocation fails due to a race condition:
        - Room 101 must NOT be allocated to Customer B.
        - Booking B must be cancelled with an overbooking reason.
        - An automatic refund must be initiated.
        - HTTP 409 Conflict returned with overbooked status.
        """
        # Customer A already confirmed for Room 101
        booking_a = Booking.objects.create(
            booking_id='KH-TEST-RACE-A',
            customer=self.customer_a,
            hotel=self.hotel,
            room=self.single_unit_room,
            check_in=self.stay_check_in,
            check_out=self.stay_check_out,
            number_of_rooms=1,
            price_per_night=Decimal('2500.00'),
            number_of_nights=1,
            subtotal=Decimal('2500.00'),
            taxes=Decimal('450.00'),
            total_amount=Decimal('2950.00'),
            booking_status=Booking.STATUS_CONFIRMED,
            payment_status=Booking.PAYMENT_PAID,
            room_number='101'
        )

        # Customer B also had an order created simultaneously
        booking_b = Booking.objects.create(
            booking_id='KH-TEST-RACE-B',
            customer=self.customer_b,
            hotel=self.hotel,
            room=self.single_unit_room,
            check_in=self.stay_check_in,
            check_out=self.stay_check_out,
            number_of_rooms=1,
            price_per_night=Decimal('2500.00'),
            number_of_nights=1,
            subtotal=Decimal('2500.00'),
            taxes=Decimal('450.00'),
            total_amount=Decimal('2950.00'),
            booking_status=Booking.STATUS_PENDING_PAYMENT,
            payment_status=Booking.PAYMENT_PENDING,
            razorpay_order_id='order_race_b_123'
        )
        payment_b = Payment.objects.create(
            booking=booking_b,
            user=self.customer_b,
            razorpay_order_id='order_race_b_123',
            amount=Decimal('2950.00'),
            status=Payment.STATUS_CREATED
        )

        # Mock Razorpay client methods to simulate successful payment verification & refund
        mock_client = MagicMock()
        mock_client.payment.fetch.return_value = {
            'id': 'pay_race_b_999',
            'amount': 295000,
            'currency': 'INR',
            'status': 'captured',
            'method': 'card'
        }
        mock_client.payment.refund.return_value = {
            'id': 'rfnd_race_b_001',
            'amount': 295000,
            'status': 'processed'
        }

        with patch('payments.views.get_platform_razorpay_client', return_value=(mock_client, 'rzp_test_key')):
            self.client.force_authenticate(user=self.customer_b)
            # Verify payment for booking B
            import hmac, hashlib
            from django.conf import settings
            sig = hmac.new(
                settings.RAZORPAY_KEY_SECRET.encode('utf-8'),
                f"order_race_b_123|pay_race_b_999".encode('utf-8'),
                hashlib.sha256
            ).hexdigest()

            response = self.client.post('/api/payments/verify/', {
                'booking_id': booking_b.booking_id,
                'razorpay_order_id': 'order_race_b_123',
                'razorpay_payment_id': 'pay_race_b_999',
                'razorpay_signature': sig
            }, format='json')

            # Expect HTTP 409 Conflict with overbooked_refund_initiated
            self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
            self.assertEqual(response.data.get('status'), 'overbooked_refund_initiated')

            # Verify booking B was cancelled and NOT confirmed with Room 101
            booking_b.refresh_from_db()
            self.assertEqual(booking_b.booking_status, Booking.STATUS_CANCELLED)
            self.assertIsNone(booking_b.room_number)
            self.assertIn("overbooking", booking_b.cancellation_reason.lower())

            # Verify refund was executed with Razorpay
            mock_client.payment.refund.assert_called_once()
            refund_record = Refund.objects.filter(booking=booking_b).first()
            self.assertIsNotNone(refund_record)
            self.assertEqual(refund_record.amount, Decimal('2950.00'))

    def test_04_simultaneous_concurrent_allocation_threads(self):
        """
        Simulate two simultaneous threads attempting to allocate Room 101 for the same dates.
        Only ONE thread must succeed in allocating Room 101; the second MUST receive None.
        """
        booking_1 = Booking.objects.create(
            booking_id='KH-THREAD-1',
            customer=self.customer_a,
            hotel=self.hotel,
            room=self.single_unit_room,
            check_in=self.stay_check_in,
            check_out=self.stay_check_out,
            number_of_rooms=1,
            price_per_night=Decimal('2500.00'),
            number_of_nights=1,
            subtotal=Decimal('2500.00'),
            taxes=Decimal('450.00'),
            total_amount=Decimal('2950.00'),
            booking_status=Booking.STATUS_PENDING_PAYMENT,
            payment_status=Booking.PAYMENT_PENDING
        )
        booking_2 = Booking.objects.create(
            booking_id='KH-THREAD-2',
            customer=self.customer_b,
            hotel=self.hotel,
            room=self.single_unit_room,
            check_in=self.stay_check_in,
            check_out=self.stay_check_out,
            number_of_rooms=1,
            price_per_night=Decimal('2500.00'),
            number_of_nights=1,
            subtotal=Decimal('2500.00'),
            taxes=Decimal('450.00'),
            total_amount=Decimal('2950.00'),
            booking_status=Booking.STATUS_PENDING_PAYMENT,
            payment_status=Booking.PAYMENT_PENDING
        )

        results = {}

        def allocate_worker(booking, key):
            res = allocate_room_number_for_booking(booking)
            if res:
                # Mark as confirmed to reflect actual successful allocation workflow
                booking.booking_status = Booking.STATUS_CONFIRMED
                booking.payment_status = Booking.PAYMENT_PAID
                booking.save(update_fields=['booking_status', 'payment_status'])
            results[key] = res

        t1 = threading.Thread(target=allocate_worker, args=(booking_1, 'T1'))
        t2 = threading.Thread(target=allocate_worker, args=(booking_2, 'T2'))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        allocations = [results.get('T1'), results.get('T2')]
        # Exactly one thread should have allocated '101'
        self.assertEqual(allocations.count('101'), 1)
        # The other thread must have received None
        self.assertEqual(allocations.count(None), 1)

    def test_05_non_overlapping_dates_both_succeed_with_room_101(self):
        """
        Customer A stays 18-19 Nov. Customer B stays 20-21 Nov (non-overlapping).
        Both should successfully receive Room 101.
        """
        booking_a = Booking.objects.create(
            booking_id='KH-NON-OVERLAP-A',
            customer=self.customer_a,
            hotel=self.hotel,
            room=self.single_unit_room,
            check_in=date(2026, 11, 18),
            check_out=date(2026, 11, 19),
            number_of_rooms=1,
            price_per_night=Decimal('2500.00'),
            number_of_nights=1,
            subtotal=Decimal('2500.00'),
            taxes=Decimal('450.00'),
            total_amount=Decimal('2950.00'),
            booking_status=Booking.STATUS_CONFIRMED,
            payment_status=Booking.PAYMENT_PAID
        )
        allocated_a = allocate_room_number_for_booking(booking_a)
        self.assertEqual(allocated_a, '101')

        booking_b = Booking.objects.create(
            booking_id='KH-NON-OVERLAP-B',
            customer=self.customer_b,
            hotel=self.hotel,
            room=self.single_unit_room,
            check_in=date(2026, 11, 20),
            check_out=date(2026, 11, 21),
            number_of_rooms=1,
            price_per_night=Decimal('2500.00'),
            number_of_nights=1,
            subtotal=Decimal('2500.00'),
            taxes=Decimal('450.00'),
            total_amount=Decimal('2950.00'),
            booking_status=Booking.STATUS_CONFIRMED,
            payment_status=Booking.PAYMENT_PAID
        )
        allocated_b = allocate_room_number_for_booking(booking_b)
        self.assertEqual(allocated_b, '101')


class PrePaymentInventoryBlockingTests(TransactionTestCase):
    """
    Automated verification of Strict Pre-Payment Room Inventory Blocking.
    Tests all 10 required inventory scenarios:
    1. All 3 of 3 rooms booked -> fourth customer blocked before payment (HTTP 409, ROOMS_SOLD_OUT).
    2. 2 of 3 rooms booked -> one room remains available.
    3. One room remains but customer requests 2 -> blocked.
    4. Active temporary hold on the last room -> another customer blocked.
    5. Expired temporary hold -> room becomes available.
    6. Non-overlapping dates -> booking is allowed.
    7. Cancelled booking -> does not block availability.
    8. Two customers simultaneously attempt to reserve the final room -> only one succeeds.
    9. Sold-out Create Order request -> Razorpay API is never called.
    10. Successful availability check -> existing payment flow continues correctly.
    """

    def setUp(self):
        from datetime import timedelta
        self.client = APIClient()

        # Hotel Owner
        self.owner = User.objects.create_user(
            username='inv_owner',
            email='inv_owner@example.com',
            password='Password123!',
            role='HOTEL_OWNER',
            phone_number='9876543200'
        )

        # 4 Customers: A, B, C, D
        self.cust_a = User.objects.create_user(
            username='cust_a_inv', email='cust_a@example.com', password='Password123!', role='CUSTOMER', phone_number='9876543201'
        )
        self.cust_b = User.objects.create_user(
            username='cust_b_inv', email='cust_b@example.com', password='Password123!', role='CUSTOMER', phone_number='9876543202'
        )
        self.cust_c = User.objects.create_user(
            username='cust_c_inv', email='cust_c@example.com', password='Password123!', role='CUSTOMER', phone_number='9876543203'
        )
        self.cust_d = User.objects.create_user(
            username='cust_d_inv', email='cust_d@example.com', password='Password123!', role='CUSTOMER', phone_number='9876543204'
        )

        # Hotel
        self.hotel = Hotel.objects.create(
            owner=self.owner,
            name='Inventory Gate Luxury Hotel',
            city='Goa',
            address='Calangute Beach Road',
            status='APPROVED',
            star_rating=5
        )

        # Room Category with exactly THREE physical units: 101, 102, 103
        self.deluxe_room = Room.objects.create(
            hotel=self.hotel,
            title='Deluxe Sea View Suite',
            room_type='DELUXE',
            price_per_night=Decimal('3000.00'),
            total_rooms=3,
            room_numbers='101, 102, 103'
        )

        # Overlapping stay dates
        self.check_in = date(2026, 12, 1)
        self.check_out = date(2026, 12, 5)

        # Mock Razorpay Client
        self.mock_rzp_client = MagicMock()
        self.mock_rzp_client.order.create.return_value = {
            'id': 'order_rzp_mock_123',
            'amount': 1416000,
            'currency': 'INR',
            'status': 'created'
        }

    def _create_confirmed_booking(self, customer, booking_id, room_num='101'):
        booking = Booking.objects.create(
            booking_id=booking_id,
            customer=customer,
            hotel=self.hotel,
            room=self.deluxe_room,
            check_in=self.check_in,
            check_out=self.check_out,
            number_of_guests=2,
            number_of_rooms=1,
            price_per_night=Decimal('3000.00'),
            number_of_nights=4,
            subtotal=Decimal('12000.00'),
            taxes=Decimal('2160.00'),
            total_amount=Decimal('14160.00'),
            booking_status=Booking.STATUS_CONFIRMED,
            payment_status=Booking.PAYMENT_PAID,
            room_number=room_num
        )
        return booking

    def _create_pending_booking(self, customer, booking_id, num_rooms=1, expires_in_minutes=15):
        from datetime import timedelta
        booking = Booking.objects.create(
            booking_id=booking_id,
            customer=customer,
            hotel=self.hotel,
            room=self.deluxe_room,
            check_in=self.check_in,
            check_out=self.check_out,
            number_of_guests=2,
            number_of_rooms=num_rooms,
            price_per_night=Decimal('3000.00'),
            number_of_nights=4,
            subtotal=Decimal('12000.00') * Decimal(str(num_rooms)),
            taxes=Decimal('2160.00') * Decimal(str(num_rooms)),
            total_amount=Decimal('14160.00') * Decimal(str(num_rooms)),
            booking_status=Booking.STATUS_PENDING_PAYMENT,
            payment_status=Booking.PAYMENT_PENDING,
            expires_at=timezone.now() + timedelta(minutes=expires_in_minutes)
        )
        return booking

    def test_01_all_3_rooms_booked_fourth_customer_blocked_before_payment(self):
        """Scenario 1: All 3 of 3 rooms booked -> fourth customer blocked before payment."""
        self._create_confirmed_booking(self.cust_a, 'BK-CONF-A', '101')
        self._create_confirmed_booking(self.cust_b, 'BK-CONF-B', '102')
        self._create_confirmed_booking(self.cust_c, 'BK-CONF-C', '103')

        booking_d = self._create_pending_booking(self.cust_d, 'BK-PEND-D')

        with patch('payments.views.get_platform_razorpay_client', return_value=(self.mock_rzp_client, 'rzp_test_key')):
            self.client.force_authenticate(user=self.cust_d)
            response = self.client.post('/api/payments/create-order/', {'booking_id': booking_d.booking_id}, format='json')

            self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
            self.assertEqual(response.data.get('code'), 'ROOMS_SOLD_OUT')
            self.assertEqual(
                response.data.get('message'),
                "All rooms are booked for your selected dates. Please select different dates or another room category."
            )
            self.assertEqual(response.data.get('available_rooms'), 0)
            self.assertEqual(response.data.get('requested_rooms'), 1)
            self.assertFalse(response.data.get('success'))
            # Prove Razorpay API was NEVER called
            self.mock_rzp_client.order.create.assert_not_called()

    def test_02_two_of_three_rooms_booked_one_room_remains_available(self):
        """Scenario 2: 2 of 3 rooms booked -> one room remains available."""
        self._create_confirmed_booking(self.cust_a, 'BK-CONF-A2', '101')
        self._create_confirmed_booking(self.cust_b, 'BK-CONF-B2', '102')

        avail_count = get_available_room_count(self.deluxe_room, self.check_in, self.check_out, include_holds=True)
        self.assertEqual(avail_count, 1)

        booking_c = self._create_pending_booking(self.cust_c, 'BK-PEND-C2')
        with patch('payments.views.get_platform_razorpay_client', return_value=(self.mock_rzp_client, 'rzp_test_key')):
            self.client.force_authenticate(user=self.cust_c)
            response = self.client.post('/api/payments/create-order/', {'booking_id': booking_c.booking_id}, format='json')

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.mock_rzp_client.order.create.assert_called_once()

    def test_03_one_room_remains_customer_requests_two_blocked(self):
        """Scenario 3: One room remains but customer requests 2 -> blocked."""
        self._create_confirmed_booking(self.cust_a, 'BK-CONF-A3', '101')
        self._create_confirmed_booking(self.cust_b, 'BK-CONF-B3', '102')

        # Customer C requests 2 rooms
        booking_c = self._create_pending_booking(self.cust_c, 'BK-PEND-C3', num_rooms=2)

        with patch('payments.views.get_platform_razorpay_client', return_value=(self.mock_rzp_client, 'rzp_test_key')):
            self.client.force_authenticate(user=self.cust_c)
            response = self.client.post('/api/payments/create-order/', {'booking_id': booking_c.booking_id}, format='json')

            self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
            self.assertEqual(response.data.get('code'), 'ROOMS_SOLD_OUT')
            self.assertEqual(response.data.get('available_rooms'), 1)
            self.assertEqual(response.data.get('requested_rooms'), 2)
            self.mock_rzp_client.order.create.assert_not_called()

    def test_04_active_temporary_hold_on_last_room_blocks_another_customer(self):
        """Scenario 4: Active temporary hold on the last room -> another customer blocked."""
        self._create_confirmed_booking(self.cust_a, 'BK-CONF-A4', '101')
        self._create_confirmed_booking(self.cust_b, 'BK-CONF-B4', '102')

        # Customer C creates a pending booking with active 15-minute checkout hold
        booking_c = self._create_pending_booking(self.cust_c, 'BK-PEND-C4', num_rooms=1, expires_in_minutes=15)

        # Customer D also has a pending booking and tries to create order for the same room
        booking_d = self._create_pending_booking(self.cust_d, 'BK-PEND-D4', num_rooms=1, expires_in_minutes=15)

        with patch('payments.views.get_platform_razorpay_client', return_value=(self.mock_rzp_client, 'rzp_test_key')):
            self.client.force_authenticate(user=self.cust_d)
            response = self.client.post('/api/payments/create-order/', {'booking_id': booking_d.booking_id}, format='json')

            self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
            self.assertEqual(response.data.get('code'), 'ROOMS_SOLD_OUT')
            self.assertEqual(response.data.get('available_rooms'), 0)
            self.mock_rzp_client.order.create.assert_not_called()

    def test_05_expired_temporary_hold_room_becomes_available(self):
        """Scenario 5: Expired temporary hold -> room becomes available."""
        self._create_confirmed_booking(self.cust_a, 'BK-CONF-A5', '101')
        self._create_confirmed_booking(self.cust_b, 'BK-CONF-B5', '102')

        # Customer C had a hold that is now EXPIRED (e.g. 5 minutes ago)
        booking_c = self._create_pending_booking(self.cust_c, 'BK-PEND-C5', num_rooms=1, expires_in_minutes=-5)

        # Customer D attempts order creation for the same room
        booking_d = self._create_pending_booking(self.cust_d, 'BK-PEND-D5', num_rooms=1, expires_in_minutes=15)

        with patch('payments.views.get_platform_razorpay_client', return_value=(self.mock_rzp_client, 'rzp_test_key')):
            self.client.force_authenticate(user=self.cust_d)
            response = self.client.post('/api/payments/create-order/', {'booking_id': booking_d.booking_id}, format='json')

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.mock_rzp_client.order.create.assert_called_once()

    def test_06_non_overlapping_dates_booking_is_allowed(self):
        """Scenario 6: Non-overlapping dates -> booking is allowed."""
        # Rooms 101, 102, 103 booked for 2026-12-01 to 2026-12-05
        self._create_confirmed_booking(self.cust_a, 'BK-CONF-A6', '101')
        self._create_confirmed_booking(self.cust_b, 'BK-CONF-B6', '102')
        self._create_confirmed_booking(self.cust_c, 'BK-CONF-C6', '103')

        # Customer D books for non-overlapping stay: 2026-12-05 to 2026-12-08
        booking_d = Booking.objects.create(
            booking_id='BK-NON-OVERLAP-D',
            customer=self.cust_d,
            hotel=self.hotel,
            room=self.deluxe_room,
            check_in=date(2026, 12, 5),
            check_out=date(2026, 12, 8),
            number_of_rooms=1,
            price_per_night=Decimal('3000.00'),
            number_of_nights=3,
            subtotal=Decimal('9000.00'),
            taxes=Decimal('1620.00'),
            total_amount=Decimal('10620.00'),
            booking_status=Booking.STATUS_PENDING_PAYMENT,
            payment_status=Booking.PAYMENT_PENDING
        )

        with patch('payments.views.get_platform_razorpay_client', return_value=(self.mock_rzp_client, 'rzp_test_key')):
            self.client.force_authenticate(user=self.cust_d)
            response = self.client.post('/api/payments/create-order/', {'booking_id': booking_d.booking_id}, format='json')

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.mock_rzp_client.order.create.assert_called_once()

    def test_07_cancelled_booking_does_not_block_availability(self):
        """Scenario 7: Cancelled booking -> does not block availability, according to existing rules."""
        self._create_confirmed_booking(self.cust_a, 'BK-CONF-A7', '101')
        self._create_confirmed_booking(self.cust_b, 'BK-CONF-B7', '102')

        # Booking C was cancelled
        booking_c = self._create_confirmed_booking(self.cust_c, 'BK-CONF-C7', '103')
        booking_c.booking_status = Booking.STATUS_CANCELLED
        booking_c.payment_status = Booking.PAYMENT_REFUNDED
        booking_c.save()

        # Customer D attempts to book the freed up room
        booking_d = self._create_pending_booking(self.cust_d, 'BK-PEND-D7')

        with patch('payments.views.get_platform_razorpay_client', return_value=(self.mock_rzp_client, 'rzp_test_key')):
            self.client.force_authenticate(user=self.cust_d)
            response = self.client.post('/api/payments/create-order/', {'booking_id': booking_d.booking_id}, format='json')

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.mock_rzp_client.order.create.assert_called_once()

    def test_08_two_customers_simultaneously_attempt_reserve_final_room_only_one_succeeds(self):
        """Scenario 8: Two customers simultaneously attempt to reserve the final room -> only one succeeds."""
        # 2 of 3 rooms confirmed
        self._create_confirmed_booking(self.cust_a, 'BK-CONF-A8', '101')
        self._create_confirmed_booking(self.cust_b, 'BK-CONF-B8', '102')

        results = {}

        def attempt_reservation(user, key):
            client = APIClient()
            client.force_authenticate(user=user)
            resp = client.post('/api/bookings/', {
                'hotel': self.hotel.id,
                'room': self.deluxe_room.id,
                'check_in': str(self.check_in),
                'check_out': str(self.check_out),
                'number_of_rooms': 1,
                'number_of_guests': 2,
                'guest_name': user.username,
                'guest_email': user.email,
                'guest_phone': '9876543210'
            }, format='json')
            results[key] = resp

        t1 = threading.Thread(target=attempt_reservation, args=(self.cust_c, 'C'))
        t2 = threading.Thread(target=attempt_reservation, args=(self.cust_d, 'D'))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        statuses = [results['C'].status_code, results['D'].status_code]
        # Exactly one customer must succeed (201 Created), and the other must be blocked (409 Conflict)
        self.assertEqual(statuses.count(status.HTTP_201_CREATED), 1)
        self.assertEqual(statuses.count(status.HTTP_409_CONFLICT), 1)

        blocked_resp = results['C'] if results['C'].status_code == status.HTTP_409_CONFLICT else results['D']
        self.assertEqual(blocked_resp.data.get('code'), 'ROOMS_SOLD_OUT')
        self.assertEqual(blocked_resp.data.get('available_rooms'), 0)

    def test_09_sold_out_create_order_request_razorpay_api_never_called(self):
        """Scenario 9: Sold-out Create Order request -> Razorpay API is never called."""
        self._create_confirmed_booking(self.cust_a, 'BK-CONF-A9', '101')
        self._create_confirmed_booking(self.cust_b, 'BK-CONF-B9', '102')
        self._create_confirmed_booking(self.cust_c, 'BK-CONF-C9', '103')

        booking_d = self._create_pending_booking(self.cust_d, 'BK-PEND-D9')

        with patch('payments.views.get_platform_razorpay_client', return_value=(self.mock_rzp_client, 'rzp_test_key')):
            self.client.force_authenticate(user=self.cust_d)
            response = self.client.post('/api/payments/create-order/', {'booking_id': booking_d.booking_id}, format='json')

            self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
            self.mock_rzp_client.order.create.assert_not_called()

    def test_10_successful_availability_check_existing_payment_flow_continues(self):
        """Scenario 10: Successful availability check -> existing payment flow continues correctly."""
        # 1 of 3 rooms confirmed -> 2 rooms available
        self._create_confirmed_booking(self.cust_a, 'BK-CONF-A10', '101')

        booking_b = self._create_pending_booking(self.cust_b, 'BK-PEND-B10')

        with patch('payments.views.get_platform_razorpay_client', return_value=(self.mock_rzp_client, 'rzp_test_key')):
            self.client.force_authenticate(user=self.cust_b)
            response = self.client.post('/api/payments/create-order/', {'booking_id': booking_b.booking_id}, format='json')

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data.get('order_id'), 'order_rzp_mock_123')
            self.assertEqual(response.data.get('amount'), 1416000)
            self.assertEqual(response.data.get('currency'), 'INR')
            self.mock_rzp_client.order.create.assert_called_once()

