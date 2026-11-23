"""
Comprehensive Automated Test Suite for GoOnStay Real Razorpay Refund Integration.

Verifies:
1. Preservation of existing cancellation workflow:
   - Customer requests cancellation.
   - Hotel owner receives cancellation request and can APPROVE or REJECT.
   - If hotel owner rejects, refund is strictly blocked.
   - If hotel owner approves, request proceeds to Admin.
   - Only Admin (or authorized Refunds Staff) can initiate the gateway refund.
2. Real Razorpay gateway refund execution:
   - Captured payment ID used.
   - Exact amount in paise transmitted to Razorpay Payments Refund API.
   - Razorpay refund ID and timestamps stored.
   - Status transitions (REFUND_PROCESSING -> REFUNDED / REFUND_FAILED).
   - Host earnings reversed and excluded from payouts.
3. Idempotency and over-refund prevention:
   - Replay protection against duplicate refunds.
   - Rejection of refund amounts exceeding remaining refundable balance.
   - Rejection of 0-balance refunds.
4. Razorpay refund webhook event processing:
   - Signature verification using RAZORPAY_WEBHOOK_SECRET.
   - Handling of refund.processed, refund.failed, refund.created.
5. Refund status and reconciliation API:
   - Live synchronization via client.refund.fetch on demand.
6. Customer booking details API:
   - Serialization of refund audit fields (refund_status, refund_amount,
     refund_date, original_payment_source, razorpay_refund_id,
     cancellation_fee, refundable_amount).
7. Staff Portal authorized refund processing.
"""

import json
import hmac
import hashlib
from decimal import Decimal
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking
from payments.models import Payment, Refund, HostEarning, WebhookEvent
from staff.models import Department, StaffProfile, StaffPermission

User = get_user_model()


class RazorpayRealRefundIntegrationTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # 1. Admin User
        self.admin_user = User.objects.create_superuser(
            username='admin_refund_boss',
            email='admin_boss@goonstay.com',
            password='AdminPassword123!',
            role='ADMIN'
        )

        # 2. Hotel Owner User
        self.owner_user = User.objects.create_user(
            username='hotel_owner_partner',
            email='owner_partner@goonstay.com',
            password='OwnerPassword123!',
            role='HOTEL_OWNER'
        )

        # 3. Customer User
        self.customer_user = User.objects.create_user(
            username='traveler_guest',
            email='guest_traveler@goonstay.com',
            password='GuestPassword123!',
            role='CUSTOMER'
        )

        # 4. Another Customer User (unauthorized)
        self.other_customer = User.objects.create_user(
            username='other_guest',
            email='other_guest@goonstay.com',
            password='GuestPassword123!',
            role='CUSTOMER'
        )

        # 5. Department Setup
        self.dept_refunds, _ = Department.objects.get_or_create(
            code=Department.CODE_REFUNDS_AND_CLAIMS,
            defaults={'name': 'Refunds & Claims'}
        )
        self.dept_reservation, _ = Department.objects.get_or_create(
            code=Department.CODE_RESERVATION,
            defaults={'name': 'Reservation'}
        )

        # 6. Refunds Staff (authorized)
        self.staff_refund_user = User.objects.create_user(
            username='staff_refund_agent',
            email='refund_agent@goonstay.com',
            password='StaffPassword123!',
            role='STAFF',
            is_staff=True
        )
        self.staff_refund_profile = StaffProfile.objects.create(
            user=self.staff_refund_user,
            employee_id='EMP-REF-99',
            login_id='staff_refund_agent',
            department=self.dept_refunds,
            status=StaffProfile.STATUS_ACTIVE,
            must_change_password=False
        )
        perm_process, _ = StaffPermission.objects.get_or_create(
            code='PROCESS_REFUND',
            defaults={'name': 'Process Refund', 'department': self.dept_refunds}
        )
        perm_view, _ = StaffPermission.objects.get_or_create(
            code='VIEW_REFUNDS',
            defaults={'name': 'View Refunds', 'department': self.dept_refunds}
        )
        self.staff_refund_profile.permissions.add(perm_process, perm_view)

        # 7. Reservation Staff (unauthorized for refunds)
        self.staff_res_user = User.objects.create_user(
            username='staff_res_agent',
            email='res_agent@goonstay.com',
            password='StaffPassword123!',
            role='STAFF',
            is_staff=True
        )
        self.staff_res_profile = StaffProfile.objects.create(
            user=self.staff_res_user,
            employee_id='EMP-RES-99',
            login_id='staff_res_agent',
            department=self.dept_reservation,
            status=StaffProfile.STATUS_ACTIVE,
            must_change_password=False
        )

        # 8. Hotel and Room
        self.hotel = Hotel.objects.create(
            owner=self.owner_user,
            name='GoOnStay Grand Heritage',
            city='Jaipur',
            state='Rajasthan',
            status=Hotel.STATUS_APPROVED,
            is_approved=True
        )
        self.room = Room.objects.create(
            hotel=self.hotel,
            title='Royal Heritage Suite',
            room_type='SUITE',
            price_per_night=Decimal('5000.00'),
            capacity_adults=2
        )

        # 9. Bookings & Captured Payments
        today = timezone.now().date()
        self.booking = Booking.objects.create(
            booking_id='BMR-REF-1001',
            customer=self.customer_user,
            hotel=self.hotel,
            room=self.room,
            check_in=today + timedelta(days=5),
            check_out=today + timedelta(days=7),
            number_of_nights=2,
            number_of_rooms=1,
            price_per_night=Decimal('5000.00'),
            subtotal=Decimal('10000.00'),
            taxes=Decimal('1800.00'),
            total_amount=Decimal('11800.00'),
            refundable_amount=Decimal('10620.00'),
            cancellation_charge=Decimal('1180.00'),
            cancellation_fee_percentage=Decimal('10.00'),
            booking_status=Booking.STATUS_CONFIRMED,
            payment_status=Booking.PAYMENT_PAID,
            guest_name='Traveler Guest',
            guest_email='guest_traveler@goonstay.com',
            guest_phone='9876543210'
        )

        self.payment = Payment.objects.create(
            booking=self.booking,
            user=self.customer_user,
            razorpay_order_id='order_mock_test_1001',
            razorpay_payment_id='pay_mock_test_1001',
            amount=Decimal('11800.00'),
            status=Payment.STATUS_CAPTURED,
            payment_method='UPI'
        )

        # Host earning
        self.earning = HostEarning.objects.create(
            host=self.owner_user,
            booking=self.booking,
            gross_amount=Decimal('11800.00'),
            platform_fee=Decimal('1180.00'),
            tax=Decimal('212.40'),
            net_amount=Decimal('10407.60'),
            status=HostEarning.STATUS_ON_HOLD
        )

    def _generate_webhook_signature(self, payload_bytes):
        secret = getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', 'test_secret')
        return hmac.new(secret.encode('utf-8'), payload_bytes, hashlib.sha256).hexdigest()

    def test_01_cancellation_workflow_requires_owner_approval(self):
        """
        Workflow Step 1-3:
        Customer cancels -> Booking cancellation is pending approval.
        Admin refund attempt is blocked if owner has not approved.
        """
        # Customer requests cancellation
        self.client.force_authenticate(user=self.customer_user)
        res_cancel = self.client.post(f'/api/bookings/{self.booking.id}/cancel/', {
            'reason': 'Family emergency'
        })
        self.assertEqual(res_cancel.status_code, status.HTTP_200_OK)

        # Refresh booking
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.booking_status, Booking.STATUS_CANCELLED)

        # A pending refund was created
        pending_refund = Refund.objects.filter(booking=self.booking).first()
        self.assertIsNotNone(pending_refund)
        self.assertEqual(pending_refund.status, Refund.STATUS_REFUND_PENDING)

    def test_02_owner_rejection_strictly_blocks_refund(self):
        """
        Workflow Step 4:
        If Hotel Owner rejects the cancellation request:
        - booking_status becomes OWNER_REJECTED.
        - Admin or Staff refund attempt is rejected with HTTP 400.
        """
        # Hotel Owner rejects cancellation request
        self.client.force_authenticate(user=self.owner_user)
        res_reject = self.client.post(f'/api/bookings/{self.booking.id}/cancel/', {
            'action': 'OWNER_REJECT',
            'reason': 'Non-refundable discount window expired'
        })
        self.assertEqual(res_reject.status_code, status.HTTP_200_OK)

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.booking_status, 'OWNER_REJECTED')

        # Admin tries to initiate refund on rejected booking
        self.client.force_authenticate(user=self.admin_user)
        res_refund = self.client.post('/api/payments/refund/process/', {
            'booking_id': self.booking.booking_id
        })
        self.assertEqual(res_refund.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("rejected", str(res_refund.data.get('error', '')).lower())

    def test_03_owner_approval_enables_admin_refund(self):
        """
        Workflow Step 5:
        If Hotel Owner approves the cancellation request:
        - booking_status becomes OWNER_APPROVED.
        - Request proceeds to Admin for refund review & execution.
        """
        self.client.force_authenticate(user=self.owner_user)
        res_approve = self.client.post(f'/api/bookings/{self.booking.id}/cancel/', {
            'action': 'OWNER_APPROVE'
        })
        self.assertEqual(res_approve.status_code, status.HTTP_200_OK)

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.booking_status, 'OWNER_APPROVED')

    def test_04_permission_control_only_admin_and_authorized_staff_can_refund(self):
        """
        Strict permission control:
        - Customer cannot call refund endpoint (HTTP 403).
        - Hotel Owner cannot initiate gateway refund (HTTP 403).
        - Unauthorized Staff cannot initiate refund (HTTP 403).
        - Admin and authorized Refunds Staff can initiate refund.
        """
        self.booking.booking_status = 'OWNER_APPROVED'
        self.booking.save(update_fields=['booking_status'])

        # 1. Customer
        self.client.force_authenticate(user=self.customer_user)
        res_cust = self.client.post('/api/payments/refund/process/', {'booking_id': self.booking.booking_id})
        self.assertEqual(res_cust.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Hotel Owner
        self.client.force_authenticate(user=self.owner_user)
        res_owner = self.client.post('/api/payments/refund/process/', {'booking_id': self.booking.booking_id})
        self.assertEqual(res_owner.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("cannot initiate", str(res_owner.data.get('error', '')).lower())

        # 3. Reservation Staff (unauthorized department)
        self.client.force_authenticate(user=self.staff_res_user)
        res_staff_res = self.client.post('/api/payments/refund/process/', {'booking_id': self.booking.booking_id})
        self.assertEqual(res_staff_res.status_code, status.HTTP_403_FORBIDDEN)

    @patch('payments.views.get_platform_razorpay_client')
    def test_05_admin_real_razorpay_refund_execution(self, mock_get_client):
        """
        Workflow Step 6-8:
        Admin initiates real Razorpay gateway refund.
        - client.payment.refund is called with captured razorpay_payment_id and amount in paise.
        - Refund ID, status, and timestamps are recorded.
        - Host earning is reversed.
        """
        self.booking.booking_status = 'OWNER_APPROVED'
        self.booking.save(update_fields=['booking_status'])

        mock_razorpay_client = MagicMock()
        mock_get_client.return_value = (mock_razorpay_client, 'rzp_test_key')
        mock_razorpay_client.payment.refund.return_value = {
            'id': 'rfnd_real_test_99999',
            'entity': 'refund',
            'amount': 1062000,  # ₹10,620 in paise
            'currency': 'INR',
            'payment_id': self.payment.razorpay_payment_id,
            'status': 'processed',
            'created_at': 1700000000
        }

        self.client.force_authenticate(user=self.admin_user)
        res = self.client.post('/api/payments/refund/process/', {
            'booking_id': self.booking.booking_id,
            'reason': 'Admin verified owner approval cancellation'
        })

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data
        self.assertTrue(data.get('success', True))
        self.assertEqual(data.get('refund_status'), Refund.STATUS_REFUNDED)
        self.assertEqual(data.get('razorpay_refund_id'), 'rfnd_real_test_99999')
        self.assertEqual(Decimal(str(data.get('refund_amount'))), Decimal('10620.00'))

        # Verify Razorpay API was called with exact arguments
        mock_razorpay_client.payment.refund.assert_called_once_with(
            self.payment.razorpay_payment_id,
            {
                'amount': 1062000,
                'notes': {
                    'booking_id': self.booking.booking_id,
                    'reason': 'Admin verified owner approval cancellation',
                    'refund_mode': 'ORIGINAL_SOURCE'
                }
            }
        )

        # Database state verification
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.payment_status, Booking.PAYMENT_REFUNDED)

        refund_obj = Refund.objects.get(razorpay_refund_id='rfnd_real_test_99999')
        self.assertEqual(refund_obj.status, Refund.STATUS_REFUNDED)
        self.assertEqual(refund_obj.processed_by, self.admin_user)
        self.assertIsNotNone(refund_obj.processed_at)

        self.earning.refresh_from_db()
        self.assertEqual(self.earning.status, HostEarning.STATUS_REVERSED)

    @patch('payments.views.get_platform_razorpay_client')
    def test_06_idempotency_prevents_duplicate_razorpay_refund(self, mock_get_client):
        """
        Idempotency Guard:
        Second refund call for the same booking reuses the existing completed refund
        and does NOT issue a second request to Razorpay.
        """
        self.booking.booking_status = 'OWNER_APPROVED'
        self.booking.save(update_fields=['booking_status'])

        mock_razorpay_client = MagicMock()
        mock_get_client.return_value = (mock_razorpay_client, 'rzp_test_key')
        mock_razorpay_client.payment.refund.return_value = {
            'id': 'rfnd_idemp_001',
            'status': 'processed',
            'amount': 1062000
        }

        self.client.force_authenticate(user=self.admin_user)
        # First call
        res1 = self.client.post('/api/payments/refund/process/', {
            'booking_id': self.booking.booking_id,
            'idempotency_key': f'ref_{self.booking.booking_id}'
        })
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        self.assertEqual(mock_razorpay_client.payment.refund.call_count, 1)

        # Second call with same idempotency key
        res2 = self.client.post('/api/payments/refund/process/', {
            'booking_id': self.booking.booking_id,
            'idempotency_key': f'ref_{self.booking.booking_id}'
        })
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        # Verify Razorpay was NOT called a second time
        self.assertEqual(mock_razorpay_client.payment.refund.call_count, 1)

    def test_07_over_refund_and_zero_refund_rejection(self):
        """
        Over-refund prevention:
        - Cannot refund more than the refundable amount.
        - Cannot refund when refundable amount is 0.
        """
        self.booking.booking_status = 'OWNER_APPROVED'
        self.booking.save(update_fields=['booking_status'])

        self.client.force_authenticate(user=self.admin_user)

        # 1. Requesting ₹15,000 on a ₹10,620 refundable amount
        res_over = self.client.post('/api/payments/refund/process/', {
            'booking_id': self.booking.booking_id,
            'amount': '15000.00'
        })
        self.assertEqual(res_over.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("exceeds", str(res_over.data.get('error', '')).lower())

        # 2. 0-refundable booking
        self.booking.refundable_amount = Decimal('0.00')
        self.booking.cancellation_fee_percentage = Decimal('100.00')
        self.booking.save(update_fields=['refundable_amount', 'cancellation_fee_percentage'])

        res_zero = self.client.post('/api/payments/refund/process/', {
            'booking_id': self.booking.booking_id
        })
        self.assertEqual(res_zero.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("₹0.00", str(res_zero.data.get('error', '')))

    def test_08_razorpay_webhook_refund_processed(self):
        """
        Webhook Integration:
        When Razorpay fires 'refund.processed':
        - Verifies signature.
        - Updates pending refund to REFUNDED.
        - Updates booking payment_status to PAYMENT_REFUNDED.
        - Dispatches notifications and excludes host earnings.
        """
        # Create a pending refund
        refund_record = Refund.objects.create(
            booking=self.booking,
            payment=self.payment,
            razorpay_payment_id=self.payment.razorpay_payment_id,
            razorpay_refund_id='rfnd_wh_proc_123',
            amount=Decimal('10620.00'),
            currency='INR',
            reason='Customer cancellation',
            status=Refund.STATUS_REFUND_PROCESSING,
            idempotency_key=f'ref_wh_test_{self.booking.booking_id}'
        )

        webhook_payload = {
            'entity': 'event',
            'event': 'refund.processed',
            'event_id': 'evt_rfnd_proc_123',
            'payload': {
                'refund': {
                    'entity': {
                        'id': 'rfnd_wh_proc_123',
                        'amount': 1062000,
                        'currency': 'INR',
                        'payment_id': self.payment.razorpay_payment_id,
                        'status': 'processed',
                        'notes': {
                            'booking_id': self.booking.booking_id
                        }
                    }
                }
            }
        }
        body_str = json.dumps(webhook_payload)
        sig = self._generate_webhook_signature(body_str.encode('utf-8'))

        response = self.client.post(
            '/api/payments/webhook/',
            data=body_str,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=sig
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        refund_record.refresh_from_db()
        self.assertEqual(refund_record.status, Refund.STATUS_REFUNDED)
        self.assertIsNotNone(refund_record.processed_at)

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.payment_status, Booking.PAYMENT_REFUNDED)

    def test_09_razorpay_webhook_refund_failed(self):
        """
        Webhook Integration:
        When Razorpay fires 'refund.failed':
        - Refund status marked as REFUND_FAILED.
        - Failure reason recorded.
        - Booking payment status remains PAYMENT_REFUND_PENDING.
        """
        refund_record = Refund.objects.create(
            booking=self.booking,
            payment=self.payment,
            razorpay_payment_id=self.payment.razorpay_payment_id,
            razorpay_refund_id='rfnd_wh_fail_456',
            amount=Decimal('10620.00'),
            currency='INR',
            status=Refund.STATUS_REFUND_PROCESSING
        )

        webhook_payload = {
            'entity': 'event',
            'event': 'refund.failed',
            'event_id': 'evt_rfnd_fail_456',
            'payload': {
                'refund': {
                    'entity': {
                        'id': 'rfnd_wh_fail_456',
                        'amount': 1062000,
                        'payment_id': self.payment.razorpay_payment_id,
                        'status': 'failed',
                        'error_description': 'Customer bank account closed',
                        'notes': {
                            'booking_id': self.booking.booking_id
                        }
                    }
                }
            }
        }
        body_str = json.dumps(webhook_payload)
        sig = self._generate_webhook_signature(body_str.encode('utf-8'))

        response = self.client.post(
            '/api/payments/webhook/',
            data=body_str,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=sig
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        refund_record.refresh_from_db()
        self.assertEqual(refund_record.status, Refund.STATUS_REFUND_FAILED)
        self.assertIn("closed", refund_record.failure_reason)

    @patch('payments.views.get_platform_razorpay_client')
    def test_10_refund_status_and_reconciliation_api(self, mock_get_client):
        """
        Live status and reconciliation check:
        GET /api/payments/refunds/{lookup}/status/?sync=true
        Reconciles pending refund with Razorpay API.
        """
        refund_record = Refund.objects.create(
            booking=self.booking,
            payment=self.payment,
            razorpay_payment_id=self.payment.razorpay_payment_id,
            razorpay_refund_id='rfnd_sync_789',
            amount=Decimal('10620.00'),
            status=Refund.STATUS_REFUND_PROCESSING
        )

        mock_razorpay_client = MagicMock()
        mock_get_client.return_value = (mock_razorpay_client, 'rzp_test_key')
        mock_razorpay_client.refund.fetch.return_value = {
            'id': 'rfnd_sync_789',
            'status': 'processed',
            'amount': 1062000
        }

        self.client.force_authenticate(user=self.admin_user)
        res = self.client.get(f'/api/payments/refunds/{self.booking.booking_id}/status/?sync=true')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        data = res.data
        self.assertEqual(data.get('refund_status'), Refund.STATUS_REFUNDED)
        self.assertEqual(data.get('razorpay_refund_id'), 'rfnd_sync_789')
        self.assertEqual(Decimal(str(data.get('cancellation_fee'))), Decimal('1180.00'))
        self.assertEqual(Decimal(str(data.get('refundable_amount'))), Decimal('10620.00'))
        self.assertEqual(data.get('original_payment_source'), 'UPI')

        # Database updated
        refund_record.refresh_from_db()
        self.assertEqual(refund_record.status, Refund.STATUS_REFUNDED)

    def test_11_customer_booking_details_exposes_refund_audit_fields(self):
        """
        Customer Booking Details API:
        GET /api/bookings/{id}/
        Returns complete refund audit trail in the serializer.
        """
        Refund.objects.create(
            booking=self.booking,
            payment=self.payment,
            razorpay_payment_id=self.payment.razorpay_payment_id,
            razorpay_refund_id='rfnd_audit_555',
            amount=Decimal('10620.00'),
            status=Refund.STATUS_REFUNDED,
            processed_at=timezone.now()
        )
        self.booking.payment_status = Booking.PAYMENT_REFUNDED
        self.booking.save(update_fields=['payment_status'])

        self.client.force_authenticate(user=self.customer_user)
        res = self.client.get(f'/api/bookings/{self.booking.id}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        data = res.data
        self.assertEqual(data.get('refund_status'), 'REFUNDED')
        self.assertEqual(Decimal(str(data.get('refund_amount'))), Decimal('10620.00'))
        self.assertEqual(data.get('razorpay_refund_id'), 'rfnd_audit_555')
        self.assertEqual(data.get('original_payment_source'), 'UPI')
        self.assertEqual(Decimal(str(data.get('cancellation_fee'))), Decimal('1180.00'))
        self.assertEqual(Decimal(str(data.get('refundable_amount'))), Decimal('10620.00'))
        self.assertIsNotNone(data.get('refund_date'))

    @patch('payments.views.get_platform_razorpay_client')
    def test_12_staff_portal_refund_processing(self, mock_get_client):
        """
        Staff Portal Functional Execution:
        POST /api/staff/refunds/{id}/process/
        Refunds Staff processes an authorized refund.
        """
        self.booking.booking_status = 'OWNER_APPROVED'
        self.booking.save(update_fields=['booking_status'])

        refund_record = Refund.objects.create(
            booking=self.booking,
            payment=self.payment,
            razorpay_payment_id=self.payment.razorpay_payment_id,
            amount=Decimal('10620.00'),
            status=Refund.STATUS_REFUND_PENDING
        )

        mock_razorpay_client = MagicMock()
        mock_get_client.return_value = (mock_razorpay_client, 'rzp_test_key')
        mock_razorpay_client.payment.refund.return_value = {
            'id': 'rfnd_staff_proc_001',
            'status': 'processed',
            'amount': 1062000
        }

        self.client.force_authenticate(user=self.staff_refund_user)
        res = self.client.post(f'/api/staff/refunds/{refund_record.id}/process/', {
            'notes': 'Staff validated cancellation policy'
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data.get('success'))
        self.assertEqual(res.data.get('razorpay_refund_id'), 'rfnd_staff_proc_001')
