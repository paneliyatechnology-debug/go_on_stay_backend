import uuid
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.cache import cache
from django.db.models import ProtectedError
from rest_framework.test import APIClient
from rest_framework import status

from staff.models import Department, StaffPermission, StaffProfile
from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking
from payments.models import (
    Payment, Refund, PlatformSetting, HostEarning
)
from notifications.models import Notification
from users.serializers import UserSerializer

User = get_user_model()


class P0P1SecurityFixesTestCase(TestCase):
    """
    Automated security verification test suite for verified P0 and P1 audit findings:
    - ISSUE-01 (P0): Customer Payout Disbursal authorization & workflow lockdown
    - ISSUE-02 (P0): Cascade deletion prevention (models.PROTECT & API destroy guards)
    - ISSUE-03 (P1): Razorpay merchant key secret redaction & write-only enforcement
    - ISSUE-04 (P1): Corporate RazorpayX banking details protection in PlatformSettingsView
    - ISSUE-05 (P1): Unauthenticated test notification injection prevention
    """

    def setUp(self):
        cache.clear()
        self.client = APIClient()

        # 1. Platform Settings
        self.platform_setting, _ = PlatformSetting.objects.get_or_create(
            id=1,
            defaults={
                'payout_provider_mode': 'RAZORPAYX',
                'payout_hold_days': 7,
                'commission_percentage': Decimal('12.00'),
                'gst_tax_percentage': Decimal('18.00'),
                'razorpayx_account_number': '2323230012345678',
                'default_currency': 'INR',
                'support_email': 'support@goonstay.com',
                'support_phone': '+911412345678'
            }
        )

        # 2. Platform Admin
        self.admin = User.objects.create_superuser(
            username='sec_admin',
            email='admin@goonstay.com',
            password='AdminPassword123!',
            first_name='Admin',
            last_name='User',
            role='ADMIN'
        )

        # 3. Hotel Host / Owner
        self.host = User.objects.create_user(
            username='sec_host',
            email='host@goonstay.com',
            password='HostPassword123!',
            first_name='Rajesh',
            last_name='Host',
            role='HOTEL_OWNER',
            razorpay_key_id='rzp_live_custom123',
            razorpay_key_secret='super_secret_merchant_key_999'
        )

        # 4. Customer
        self.customer = User.objects.create_user(
            username='sec_customer',
            email='customer@goonstay.com',
            password='CustomerPassword123!',
            first_name='Aarav',
            last_name='Customer',
            role='CUSTOMER'
        )

        # 5. Unauthorized User
        self.stranger = User.objects.create_user(
            username='sec_stranger',
            email='stranger@goonstay.com',
            password='StrangerPassword123!',
            first_name='Stranger',
            last_name='User',
            role='CUSTOMER'
        )

        # 6. Refunds & Claims Staff Member
        self.dept_refunds, _ = Department.objects.get_or_create(
            code=Department.CODE_REFUNDS_AND_CLAIMS,
            defaults={'name': 'Refunds & Claims', 'is_active': True}
        )
        self.perm_refund, _ = StaffPermission.objects.get_or_create(
            code='PROCESS_REFUND',
            defaults={
                'name': 'Process Refund',
                'department': self.dept_refunds,
                'action': StaffPermission.ACTION_PROCESS_REFUND
            }
        )
        self.perm_view_refund, _ = StaffPermission.objects.get_or_create(
            code='VIEW_REFUND',
            defaults={
                'name': 'View Refund',
                'department': self.dept_refunds,
                'action': StaffPermission.ACTION_VIEW
            }
        )
        self.refund_staff_user = User.objects.create_user(
            username='staff_refunds',
            email='staff.refunds@goonstay.com',
            password='StaffPassword123!',
            role='STAFF'
        )
        self.refund_profile = StaffProfile.objects.create(
            user=self.refund_staff_user,
            employee_id='GOS-STF-REF01',
            login_id='gos_ref_01',
            department=self.dept_refunds,
            status=StaffProfile.STATUS_ACTIVE
        )
        self.refund_profile.permissions.add(self.perm_refund, self.perm_view_refund)

        # 7. Hotel & Room
        self.hotel = Hotel.objects.create(
            owner=self.host,
            name='Royal Heritage Palace',
            property_type='HOTEL',
            city='Jaipur',
            state='Rajasthan',
            address='Station Road',
            zip_code='302001',
            status=Hotel.STATUS_APPROVED,
            is_approved=True
        )
        self.room = Room.objects.create(
            hotel=self.hotel,
            title='Royal Deluxe Suite',
            room_type='DELUXE',
            price_per_night=Decimal('4000.00'),
            total_rooms=5
        )

        # 8. Booking with Payment
        today = timezone.now().date()
        self.booking = Booking.objects.create(
            booking_id='BK-SEC-001',
            customer=self.customer,
            hotel=self.hotel,
            room=self.room,
            check_in=today + timedelta(days=2),
            check_out=today + timedelta(days=4),
            number_of_guests=2,
            number_of_rooms=1,
            number_of_nights=2,
            price_per_night=Decimal('4000.00'),
            subtotal=Decimal('8000.00'),
            total_amount=Decimal('8000.00'),
            refundable_amount=Decimal('8000.00'),
            cancellation_fee_percentage=Decimal('0.00'),
            guest_name='Aarav Customer',
            guest_email='customer@goonstay.com',
            guest_phone='9876543210',
            booking_status=Booking.STATUS_CONFIRMED,
            payment_status=Booking.PAYMENT_PAID
        )
        self.payment = Payment.objects.create(
            booking=self.booking,
            user=self.customer,
            razorpay_order_id='order_sec_001',
            razorpay_payment_id='pay_sec_001',
            amount=Decimal('8000.00'),
            status=Payment.STATUS_CAPTURED
        )

    # =========================================================================
    # ISSUE-01 (P0): Customer Payout Disbursal Security & Workflow Lockdown
    # =========================================================================

    def test_issue01_customer_cannot_initiate_payout_disbursal(self):
        """Customers must receive 403 Forbidden when calling customer payout endpoint."""
        self.client.force_authenticate(user=self.customer)
        res = self.client.post('/api/payments/payouts/customer/', {
            'booking_id': self.booking.booking_id,
            'payout_mode': 'UPI',
            'upi_id': 'customer@okhdfcbank',
            'amount': 8000.00
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Permission denied", res.data.get('error', ''))

    def test_issue01_hotel_owner_cannot_initiate_payout_disbursal(self):
        """Hotel Owners must receive 403 Forbidden when calling customer payout endpoint."""
        self.client.force_authenticate(user=self.host)
        res = self.client.post('/api/payments/payouts/customer/', {
            'booking_id': self.booking.booking_id,
            'payout_mode': 'UPI',
            'upi_id': 'host@okhdfcbank',
            'amount': 8000.00
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Permission denied", res.data.get('error', ''))

    def test_issue01_payout_blocked_if_owner_rejected_cancellation(self):
        """Disbursal must be blocked if cancellation was rejected by owner."""
        self.booking.booking_status = Booking.STATUS_OWNER_REJECTED
        self.booking.save(update_fields=['booking_status'])

        self.client.force_authenticate(user=self.admin)
        res = self.client.post('/api/payments/payouts/customer/', {
            'booking_id': self.booking.booking_id,
            'payout_mode': 'UPI',
            'upi_id': 'customer@okhdfcbank'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("rejected the cancellation request", res.data.get('error', ''))

    def test_issue01_payout_blocked_if_booking_not_owner_approved(self):
        """Disbursal must be blocked if booking has not reached OWNER_APPROVED or CANCELLED."""
        self.booking.booking_status = Booking.STATUS_CONFIRMED
        self.booking.save(update_fields=['booking_status'])

        self.client.force_authenticate(user=self.refund_staff_user)
        res = self.client.post('/api/payments/payouts/customer/', {
            'booking_id': self.booking.booking_id,
            'payout_mode': 'UPI',
            'upi_id': 'customer@okhdfcbank'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("must be approved by the hotel owner", res.data.get('error', ''))

    def test_issue01_custom_amount_exceeding_refundable_balance_rejected(self):
        """Disbursal with custom_amount exceeding remaining balance must be rejected."""
        self.booking.booking_status = Booking.STATUS_OWNER_APPROVED
        self.booking.refundable_amount = Decimal('5000.00')
        self.booking.save(update_fields=['booking_status', 'refundable_amount'])

        self.client.force_authenticate(user=self.admin)
        res = self.client.post('/api/payments/payouts/customer/', {
            'booking_id': self.booking.booking_id,
            'payout_mode': 'UPI',
            'upi_id': 'customer@okhdfcbank',
            'amount': 99999.00
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("exceeds remaining eligible refundable balance", res.data.get('error', ''))

    def test_issue01_payout_lookup_idor_prevention(self):
        """Unauthorized stranger cannot view payout details for another user's booking."""
        refund = Refund.objects.create(
            booking=self.booking,
            payment=self.payment,
            amount=Decimal('8000.00'),
            payout_reference_id='pout_test_idor_01',
            status=Refund.STATUS_REFUNDED
        )

        # Stranger attempts lookup
        self.client.force_authenticate(user=self.stranger)
        res = self.client.get(f'/api/payments/payouts/customer/?booking_id={self.booking.booking_id}')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Legitimate customer can lookup
        self.client.force_authenticate(user=self.customer)
        res_cust = self.client.get(f'/api/payments/payouts/customer/?booking_id={self.booking.booking_id}')
        self.assertEqual(res_cust.status_code, status.HTTP_200_OK)

    # =========================================================================
    # ISSUE-02 (P0): Cascade Deletion Prevention (models.PROTECT & API Guards)
    # =========================================================================

    def test_issue02_user_delete_endpoint_blocks_deletion_with_active_bookings(self):
        """UserDeleteView must reject deleting a user who has bookings or financial records."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.delete(f'/api/users/{self.customer.id}/delete/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Cannot permanently delete user account", res.data.get('error', ''))
        # Ensure user still exists
        self.assertTrue(User.objects.filter(id=self.customer.id).exists())

    def test_issue02_room_delete_endpoint_blocks_deletion_with_bookings(self):
        """RoomDetailView must reject deleting a room that has active or past booking history."""
        self.client.force_authenticate(user=self.admin)
        
        # Test 1: Active upcoming reservation
        res_active = self.client.delete(f'/api/rooms/{self.room.id}/')
        self.assertEqual(res_active.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Cannot delete room with active upcoming reservations", res_active.data.get('error', ''))

        # Test 2: Historical past reservation (check_out in past)
        today = timezone.now().date()
        past_room = Room.objects.create(
            hotel=self.hotel,
            title='Historical Suite',
            room_type='STANDARD',
            price_per_night=Decimal('2000.00'),
            total_rooms=2
        )
        Booking.objects.create(
            booking_id='BK-SEC-HIST-01',
            customer=self.customer,
            hotel=self.hotel,
            room=past_room,
            check_in=today - timedelta(days=10),
            check_out=today - timedelta(days=8),
            number_of_guests=2,
            number_of_rooms=1,
            number_of_nights=2,
            price_per_night=Decimal('2000.00'),
            subtotal=Decimal('4000.00'),
            total_amount=Decimal('4000.00'),
            guest_name='Past Guest',
            guest_email='past@guest.com',
            guest_phone='9998887776',
            booking_status=Booking.STATUS_COMPLETED,
            payment_status=Booking.PAYMENT_PAID
        )
        res_hist = self.client.delete(f'/api/rooms/{past_room.id}/')
        self.assertEqual(res_hist.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Cannot delete room with existing booking history", res_hist.data.get('error', ''))

    def test_issue02_orm_level_protected_error_on_customer_or_room_deletion(self):
        """Direct ORM deletion of customer, room, or hotel with bookings must raise ProtectedError."""
        with self.assertRaises(ProtectedError):
            self.customer.delete()

        with self.assertRaises(ProtectedError):
            self.room.delete()

        with self.assertRaises(ProtectedError):
            self.hotel.delete()

    # =========================================================================
    # ISSUE-03 (P1): Razorpay Key Secret Redaction
    # =========================================================================

    def test_issue03_user_serializer_redacts_razorpay_secret(self):
        """UserSerializer must never include razorpay_key_secret in serialized representation."""
        serializer = UserSerializer(self.host)
        data = serializer.data
        self.assertNotIn('razorpay_key_secret', data)
        self.assertTrue(data.get('has_custom_razorpay_keys'))
        self.assertEqual(data.get('razorpay_key_id'), 'rzp_live_custom123')

    def test_issue03_profile_update_accepts_secret_without_exposing(self):
        """UserProfileUpdateSerializer accepts razorpay_key_secret as write-only."""
        self.client.force_authenticate(user=self.host)
        new_secret = 'new_rotated_secret_99999'
        res = self.client.patch('/api/users/profile/', {
            'first_name': 'Rajesh Kumar',
            'razorpay_key_secret': new_secret,
            'current_password': 'HostPassword123!'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # Secret must not be in response
        self.assertNotIn('razorpay_key_secret', str(res.data))
        # Secret must be updated on model
        self.host.refresh_from_db()
        self.assertEqual(self.host.razorpay_key_secret, new_secret)

    # =========================================================================
    # ISSUE-04 (P1): Corporate RazorpayX Banking Details Protection
    # =========================================================================

    def test_issue04_anonymous_platform_settings_redacts_banking_data(self):
        """Anonymous callers querying platform settings must not receive razorpayx_account_number."""
        res = self.client.get('/api/payments/settings/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertNotIn('razorpayx_account_number', res.data)
        self.assertNotIn('payout_provider_mode', res.data)
        # Public fields must be present
        self.assertEqual(Decimal(str(res.data['commission_percentage'])), Decimal('12.00'))
        self.assertEqual(Decimal(str(res.data['gst_tax_percentage'])), Decimal('18.00'))

    def test_issue04_customer_platform_settings_redacts_banking_data(self):
        """Customer querying platform settings must not receive corporate banking details."""
        self.client.force_authenticate(user=self.customer)
        res = self.client.get('/api/payments/settings/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertNotIn('razorpayx_account_number', res.data)
        self.assertNotIn('payout_provider_mode', res.data)

    def test_issue04_admin_platform_settings_receives_full_details(self):
        """Platform Admin querying platform settings must receive full configuration."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.get('/api/payments/settings/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data.get('razorpayx_account_number'), '2323230012345678')
        self.assertEqual(res.data.get('payout_provider_mode'), 'RAZORPAYX')

    # =========================================================================
    # ISSUE-05 (P1): Send Test Notification Injection Restriction
    # =========================================================================

    def test_issue05_anonymous_cannot_send_test_notification(self):
        """Unauthenticated caller must receive 401 Unauthorized on test notification endpoint."""
        res = self.client.post('/api/notifications/send-test/', {
            'title': 'Hacked Alert',
            'message': 'Injected notification'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_issue05_non_admin_forbidden_to_send_test_notification(self):
        """Non-admin authenticated user must receive 403 Forbidden."""
        self.client.force_authenticate(user=self.customer)
        res = self.client.post('/api/notifications/send-test/', {
            'title': 'Unauthorized Alert',
            'message': 'Attempted injection'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Permission denied", res.data.get('error', ''))

    def test_issue05_admin_can_send_test_notification_to_target_recipient(self):
        """Admin can dispatch test notification and it is properly assigned without User.objects.first()."""
        self.client.force_authenticate(user=self.admin)
        initial_count = Notification.objects.filter(recipient=self.admin).count()
        res = self.client.post('/api/notifications/send-test/', {
            'title': 'Admin Test Alert',
            'message': 'Testing platform notification dispatch.'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            Notification.objects.filter(recipient=self.admin).count(),
            initial_count + 1
        )
