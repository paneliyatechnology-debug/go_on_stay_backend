"""
Automated Test Suite for Hotel Owner Cancellation Approval/Rejection API.

Endpoint under test:
- POST /api/bookings/<str:pk>/owner-approval/
- GET /api/bookings/<str:pk>/owner-approval/

Verifies:
1. Approving with booking_id string (e.g. KH-2026-748CB7) returns 200 OK and sets OWNER_APPROVED.
2. Rejecting with booking_id string returns 200 OK and sets OWNER_REJECTED.
3. Rejecting without a reason returns 400 Bad Request.
4. Unauthorized users (guests, other hotel owners) receive 403 Forbidden.
5. Non-existent booking IDs return 404 Not Found.
6. GET preview returns cancellation breakdown and amounts.
7. Approved cancellation requests appear in Admin/Staff refund queue.
8. Rejected cancellation requests strictly block Admin gateway refunds.
9. Existing cancellation and refund endpoints continue working seamlessly.
"""

from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking
from payments.models import Payment, Refund, HostEarning
from staff.models import Department, StaffProfile, StaffPermission

User = get_user_model()


class OwnerCancellationApprovalTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # 1. Platform Admin
        self.admin_user = User.objects.create_superuser(
            username='admin_super',
            email='admin@goonstay.com',
            password='AdminPassword123!',
            role='ADMIN'
        )

        # 2. Hotel Owner 1 (Authorized owner of Hotel A)
        self.owner_user = User.objects.create_user(
            username='hotel_owner_1',
            email='owner1@goonstay.com',
            password='OwnerPassword123!',
            role='HOTEL_OWNER'
        )

        # 3. Hotel Owner 2 (Other owner - unauthorized for Hotel A)
        self.other_owner = User.objects.create_user(
            username='hotel_owner_2',
            email='owner2@goonstay.com',
            password='OwnerPassword123!',
            role='HOTEL_OWNER'
        )

        # 4. Customer
        self.customer_user = User.objects.create_user(
            username='customer_guest',
            email='guest@goonstay.com',
            password='GuestPassword123!',
            role='CUSTOMER'
        )

        # 5. Hotels
        self.hotel = Hotel.objects.create(
            owner=self.owner_user,
            name='Heritage Palace Jaipur',
            city='Jaipur',
            state='Rajasthan',
            status=Hotel.STATUS_APPROVED,
            is_approved=True
        )
        self.room = Room.objects.create(
            hotel=self.hotel,
            title='Royal Deluxe',
            room_type='DELUXE',
            price_per_night=Decimal('4000.00'),
            capacity_adults=2
        )

        # 6. Sample Booking with format KH-2026-748CB7
        today = timezone.now().date()
        self.booking = Booking.objects.create(
            booking_id='KH-2026-748CB7',
            customer=self.customer_user,
            hotel=self.hotel,
            room=self.room,
            check_in=today + timedelta(days=6),
            check_out=today + timedelta(days=8),
            number_of_nights=2,
            number_of_rooms=1,
            price_per_night=Decimal('4000.00'),
            subtotal=Decimal('8000.00'),
            taxes=Decimal('1440.00'),
            total_amount=Decimal('9440.00'),
            refundable_amount=Decimal('8496.00'),
            cancellation_charge=Decimal('944.00'),
            cancellation_fee_percentage=Decimal('10.00'),
            booking_status=Booking.STATUS_CONFIRMED,
            payment_status=Booking.PAYMENT_PAID,
            guest_name='John Doe',
            guest_email='john@example.com',
            guest_phone='9876543210'
        )

        self.payment = Payment.objects.create(
            booking=self.booking,
            user=self.customer_user,
            razorpay_order_id='order_mock_kh748',
            razorpay_payment_id='pay_mock_kh748',
            amount=Decimal('9440.00'),
            status=Payment.STATUS_CAPTURED,
            payment_method='UPI'
        )

    def test_01_owner_approval_with_booking_id_string(self):
        """
        POST /api/bookings/KH-2026-748CB7/owner-approval/
        Action: APPROVE
        - Status code 200 OK.
        - Booking status set to OWNER_APPROVED.
        - Pending refund record created/queued for Admin.
        - Relevant timestamps saved.
        """
        self.client.force_authenticate(user=self.owner_user)
        response = self.client.post('/api/bookings/KH-2026-748CB7/owner-approval/', {
            'action': 'APPROVE'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get('success'))
        self.assertEqual(response.data.get('status'), 'OWNER_APPROVED')
        self.assertEqual(response.data.get('booking_id'), 'KH-2026-748CB7')
        self.assertIn('updated_at', response.data)

        # Database verification
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.booking_status, 'OWNER_APPROVED')

        # Queued Refund record verification
        refund = Refund.objects.filter(booking=self.booking).first()
        self.assertIsNotNone(refund)
        self.assertEqual(refund.status, Refund.STATUS_REFUND_PENDING)
        self.assertEqual(refund.amount, Decimal('8496.00'))

    def test_02_owner_rejection_with_booking_id_string(self):
        """
        POST /api/bookings/KH-2026-748CB7/owner-approval/
        Action: REJECT
        - Status code 200 OK.
        - Booking status set to OWNER_REJECTED.
        - Cancellation reason records owner's explanation.
        """
        self.client.force_authenticate(user=self.owner_user)
        response = self.client.post('/api/bookings/KH-2026-748CB7/owner-approval/', {
            'action': 'REJECT',
            'reason': 'Special seasonal rate non-refundable policy'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get('success'))
        self.assertEqual(response.data.get('status'), 'OWNER_REJECTED')
        self.assertEqual(response.data.get('booking_id'), 'KH-2026-748CB7')

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.booking_status, 'OWNER_REJECTED')
        self.assertIn('Special seasonal rate', self.booking.cancellation_reason)

    def test_03_rejection_without_reason_returns_400(self):
        """
        Rejection requires a reason. If missing, returns 400 Bad Request.
        """
        self.client.force_authenticate(user=self.owner_user)
        response = self.client.post('/api/bookings/KH-2026-748CB7/owner-approval/', {
            'action': 'REJECT'
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('reason is required', str(response.data.get('error', '')).lower())

    def test_04_unauthorized_user_cannot_approve_or_reject(self):
        """
        Only the authorized hotel owner (or admin) can approve/reject.
        - Customer receives 403 Forbidden.
        - Different hotel owner receives 403 Forbidden.
        """
        # Customer
        self.client.force_authenticate(user=self.customer_user)
        res_cust = self.client.post('/api/bookings/KH-2026-748CB7/owner-approval/', {
            'action': 'APPROVE'
        })
        self.assertEqual(res_cust.status_code, status.HTTP_403_FORBIDDEN)

        # Other Hotel Owner
        self.client.force_authenticate(user=self.other_owner)
        res_other = self.client.post('/api/bookings/KH-2026-748CB7/owner-approval/', {
            'action': 'APPROVE'
        })
        self.assertEqual(res_other.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('authorized hotel owner', str(res_other.data.get('error', '')).lower())

    def test_05_invalid_booking_id_returns_404(self):
        """
        Non-existent booking ID returns 404 Not Found.
        """
        self.client.force_authenticate(user=self.owner_user)
        response = self.client.post('/api/bookings/NON-EXISTENT-ID/owner-approval/', {
            'action': 'APPROVE'
        })
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn('not found', str(response.data.get('error', '')).lower())

    def test_06_get_owner_approval_preview(self):
        """
        GET /api/bookings/KH-2026-748CB7/owner-approval/
        Returns cancellation preview and financial details.
        """
        self.client.force_authenticate(user=self.owner_user)
        response = self.client.get('/api/bookings/KH-2026-748CB7/owner-approval/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        self.assertEqual(data.get('booking_id'), 'KH-2026-748CB7')
        self.assertEqual(data.get('guest_name'), 'John Doe')
        self.assertEqual(Decimal(str(data.get('refundable_amount'))), Decimal('8496.00'))
        self.assertEqual(Decimal(str(data.get('cancellation_fee'))), Decimal('944.00'))

    def test_07_approved_request_appears_in_admin_refunds_and_can_be_refunded(self):
        """
        End-to-end integration:
        1. Owner approves cancellation.
        2. Admin views pending refund list; booking appears with OWNER_APPROVED status.
        3. Admin clicks refund; gateway refund executes successfully.
        """
        # Step 1: Owner approves
        self.client.force_authenticate(user=self.owner_user)
        res_app = self.client.post('/api/bookings/KH-2026-748CB7/owner-approval/', {
            'action': 'APPROVE'
        })
        self.assertEqual(res_app.status_code, status.HTTP_200_OK)

        # Step 2: Admin views refunds queue
        self.client.force_authenticate(user=self.admin_user)
        res_list = self.client.get('/api/payments/admin/refunds/?booking_id=KH-2026-748CB7')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        results = res_list.data.get('results', [])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].get('cancellation_status'), 'OWNER_APPROVED')
        self.assertEqual(results[0].get('status'), 'REFUND_PENDING')

        # Step 3: Admin processes refund (mocking Razorpay network)
        with patch('payments.views.get_platform_razorpay_client') as mock_client:
            mock_rzp = MagicMock()
            mock_client.return_value = (mock_rzp, 'key_123')
            mock_rzp.payment.refund.return_value = {
                'id': 'rfnd_app_748_test',
                'status': 'processed',
                'amount': 849600
            }

            res_proc = self.client.post('/api/payments/refund/process/', {
                'booking_id': 'KH-2026-748CB7'
            })
            self.assertEqual(res_proc.status_code, status.HTTP_200_OK)
            self.assertEqual(res_proc.data.get('refund_status'), 'REFUNDED')
            self.assertEqual(res_proc.data.get('razorpay_refund_id'), 'rfnd_app_748_test')

    def test_08_rejected_request_strictly_blocks_admin_refund(self):
        """
        If Owner rejected cancellation, Admin cannot process refund.
        """
        # Step 1: Owner rejects
        self.client.force_authenticate(user=self.owner_user)
        self.client.post('/api/bookings/KH-2026-748CB7/owner-approval/', {
            'action': 'REJECT',
            'reason': 'Host declined late cancellation'
        })

        # Step 2: Admin attempts refund
        self.client.force_authenticate(user=self.admin_user)
        res_ref = self.client.post('/api/payments/refund/process/', {
            'booking_id': 'KH-2026-748CB7'
        })
        self.assertEqual(res_ref.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('rejected', str(res_ref.data.get('error', '')).lower())

    def test_09_supports_both_id_and_booking_id_lookups(self):
        """
        The owner-approval endpoint supports both numeric database ID (e.g. 1)
        and custom booking_id (e.g. KH-2026-748CB7).
        """
        self.client.force_authenticate(user=self.owner_user)

        # Using numeric database PK
        res_num = self.client.get(f'/api/bookings/{self.booking.id}/owner-approval/')
        self.assertEqual(res_num.status_code, status.HTTP_200_OK)
        self.assertEqual(res_num.data.get('booking_id'), self.booking.booking_id)

        # Using string booking_id
        res_str = self.client.get(f'/api/bookings/{self.booking.booking_id}/owner-approval/')
        self.assertEqual(res_str.status_code, status.HTTP_200_OK)
        self.assertEqual(res_str.data.get('booking_id'), self.booking.booking_id)
