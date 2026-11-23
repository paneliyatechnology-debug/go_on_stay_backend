import uuid
from decimal import Decimal
from datetime import timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework import status

from staff.models import Department, StaffPermission, StaffProfile, StaffActivityLog
from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking
from payments.models import (
    HostPayout, HostEarning, HostPayoutAccount, AuditLog, PlatformSetting
)

User = get_user_model()


class StaffPayoutEscrowAuthorizationTestCase(TestCase):
    """
    Automated regression tests verifying:
    1. Escrow Settlement Officer Ravi Patel (GOS-EMP-021) authorization for payout distribution.
    2. Recognition of 'PAYOUTS & ESCROW' permission alias across all payout endpoints.
    3. Proper recording of initiating staff in processed_by, StaffActivityLog, and AuditLog.
    4. Strict enforcement of 7-day holding period and eligibility safeguards.
    5. Denial of unauthorized staff (e.g. Reservation, Support), customers, and owners (403 Forbidden).
    6. Immediate denial upon permission revocation.
    7. Unbroken Admin payout capabilities.
    """

    def setUp(self):
        cache.clear()
        self.client = APIClient()

        # Platform Settings
        self.platform_setting, _ = PlatformSetting.objects.get_or_create(
            id=1,
            defaults={
                'payout_provider_mode': 'MANUAL_ESCROW',
                'payout_hold_days': 7,
                'commission_percentage': Decimal('10.00'),
            }
        )

        # 1. Platform Admin
        self.admin = User.objects.create_superuser(
            username='admin_chief',
            email='admin@goonstay.com',
            password='AdminPassword123!',
            first_name='Chief',
            last_name='Admin',
            role=getattr(User, 'ROLE_ADMIN', 'ADMIN')
        )

        # 2. Hotel Host / Owner
        self.host = User.objects.create_user(
            username='host_sharma',
            email='sharma@hotels.com',
            password='HostPassword123!',
            first_name='Ramesh',
            last_name='Sharma',
            role=getattr(User, 'ROLE_HOTEL_OWNER', 'HOTEL_OWNER')
        )
        self.host_payout_account = HostPayoutAccount.objects.create(
            user=self.host,
            account_holder_name='Ramesh Sharma',
            account_number='987654321098',
            ifsc_code='HDFC0001234',
            payout_method=HostPayoutAccount.METHOD_BANK,
            verification_status=HostPayoutAccount.STATUS_VERIFIED
        )

        # Hotel & Room
        self.hotel = Hotel.objects.create(
            name='Grand Royal Palace',
            owner=self.host,
            city='Jaipur',
            state='Rajasthan',
            address='101 Palace Road',
            is_approved=True
        )
        self.room = Room.objects.create(
            hotel=self.hotel,
            room_type='DELUXE',
            title='Deluxe Suite',
            price_per_night=Decimal('3000.00')
        )

        # 3. Customer
        self.customer = User.objects.create_user(
            username='guest_rahul',
            email='rahul@guest.com',
            password='GuestPassword123!',
            role=getattr(User, 'ROLE_CUSTOMER', 'CUSTOMER')
        )

        # 4. Departments
        self.dept_payout, _ = Department.objects.get_or_create(
            code=Department.CODE_PAYOUT_AND_ESCROW,
            defaults={'name': 'Payout & Escrow', 'is_active': True}
        )
        self.dept_reservation, _ = Department.objects.get_or_create(
            code=Department.CODE_RESERVATION,
            defaults={'name': 'Reservation', 'is_active': True}
        )
        self.dept_support, _ = Department.objects.get_or_create(
            code=Department.CODE_CUSTOMER_SUPPORT,
            defaults={'name': 'Customer Support', 'is_active': True}
        )

        # Permissions
        self.perm_payouts_escrow, _ = StaffPermission.objects.get_or_create(
            code='PAYOUTS & ESCROW',
            defaults={
                'name': 'Payouts & Escrow',
                'department': self.dept_payout,
                'action': StaffPermission.ACTION_PROCESS_PAYOUT
            }
        )
        self.perm_process_payout, _ = StaffPermission.objects.get_or_create(
            code='PROCESS_PAYOUT',
            defaults={
                'name': 'Process Payouts',
                'department': self.dept_payout,
                'action': StaffPermission.ACTION_PROCESS_PAYOUT
            }
        )
        self.perm_view_payouts, _ = StaffPermission.objects.get_or_create(
            code='VIEW_PAYOUTS',
            defaults={
                'name': 'View Payouts',
                'department': self.dept_payout,
                'action': StaffPermission.ACTION_VIEW
            }
        )
        self.perm_manage_escrow, _ = StaffPermission.objects.get_or_create(
            code='MANAGE_ESCROW',
            defaults={
                'name': 'Manage Escrow Ledger',
                'department': self.dept_payout,
                'action': StaffPermission.ACTION_VIEW
            }
        )
        self.perm_view_bookings, _ = StaffPermission.objects.get_or_create(
            code='VIEW_BOOKINGS',
            defaults={
                'name': 'View Bookings',
                'department': self.dept_reservation,
                'action': StaffPermission.ACTION_VIEW
            }
        )

        # 5. Target Staff: Ravi Patel (GOS-EMP-021)
        self.user_ravi = User.objects.create_user(
            username='ravi.patel',
            email='ravi.patel@goonstay.com',
            password='RaviPassword123!',
            first_name='Ravi',
            last_name='Patel',
            role=getattr(User, 'ROLE_STAFF', 'STAFF')
        )
        self.ravi_profile = StaffProfile.objects.create(
            user=self.user_ravi,
            employee_id='GOS-EMP-021',
            login_id='ravi.payout021',
            department=self.dept_payout,
            designation='Escrow Settlement Officer',
            status=StaffProfile.STATUS_ACTIVE,
            must_change_password=False
        )
        # Assigned Permission: PAYOUTS & ESCROW
        self.ravi_profile.permissions.add(self.perm_payouts_escrow)

        # 6. Unauthorized Staff (Reservation Department)
        self.user_res_staff = User.objects.create_user(
            username='priya.res',
            email='priya@goonstay.com',
            password='StaffPassword123!',
            first_name='Priya',
            last_name='Singh',
            role=getattr(User, 'ROLE_STAFF', 'STAFF')
        )
        self.res_profile = StaffProfile.objects.create(
            user=self.user_res_staff,
            employee_id='GOS-EMP-014',
            login_id='priya.res014',
            department=self.dept_reservation,
            designation='Reservation Executive',
            status=StaffProfile.STATUS_ACTIVE,
            must_change_password=False
        )
        self.res_profile.permissions.add(self.perm_view_bookings)

    def _create_matured_booking_and_earning(self, booking_ref="KH-2026-MATURE01", amount=Decimal('3000.00')):
        """Helper to create a completed, check-out passed booking with matured 7-day holding."""
        past_checkin = timezone.now().date() - timedelta(days=12)
        past_checkout = timezone.now().date() - timedelta(days=9)
        booking = Booking.objects.create(
            booking_id=booking_ref,
            hotel=self.hotel,
            room=self.room,
            customer=self.customer,
            check_in=past_checkin,
            check_out=past_checkout,
            booking_status=Booking.STATUS_CONFIRMED,
            payment_status=Booking.PAYMENT_PAID,
            price_per_night=amount,
            number_of_nights=3,
            subtotal=amount,
            total_amount=amount,
            guest_name='Rahul Guest',
            guest_email='rahul@guest.com',
            guest_phone='+919876543210'
        )
        platform_fee = amount * Decimal('0.10')
        net_payable = amount - platform_fee
        earning = HostEarning.objects.create(
            booking=booking,
            host=self.host,
            gross_amount=amount,
            platform_fee=platform_fee,
            net_amount=net_payable,
            status=HostEarning.STATUS_ELIGIBLE,
            hold_until=timezone.now() - timedelta(days=2)  # Matured
        )
        return booking, earning

    def _create_unmatured_booking_and_earning(self, booking_ref="KH-2026-UNMATURE01", amount=Decimal('4000.00')):
        """Helper to create a booking where 7-day holding period is still active."""
        recent_checkout = timezone.now().date() - timedelta(days=2)
        booking = Booking.objects.create(
            booking_id=booking_ref,
            hotel=self.hotel,
            room=self.room,
            customer=self.customer,
            check_in=recent_checkout - timedelta(days=2),
            check_out=recent_checkout,
            booking_status=Booking.STATUS_CONFIRMED,
            payment_status=Booking.PAYMENT_PAID,
            price_per_night=amount,
            number_of_nights=2,
            subtotal=amount,
            total_amount=amount,
            guest_name='Rahul Guest',
            guest_email='rahul@guest.com',
            guest_phone='+919876543210'
        )
        platform_fee = amount * Decimal('0.10')
        net_payable = amount - platform_fee
        earning = HostEarning.objects.create(
            booking=booking,
            host=self.host,
            gross_amount=amount,
            platform_fee=platform_fee,
            net_amount=net_payable,
            status=HostEarning.STATUS_ON_HOLD,
            hold_until=timezone.now() + timedelta(days=5)  # Unmatured
        )
        return booking, earning

    def test_01_ravi_patel_profile_and_department_setup(self):
        """Verify Ravi Patel's profile, role, department, and assigned permission."""
        self.assertEqual(self.ravi_profile.employee_id, 'GOS-EMP-021')
        self.assertEqual(self.ravi_profile.department.code, Department.CODE_PAYOUT_AND_ESCROW)
        self.assertEqual(self.user_ravi.role, 'STAFF')
        self.assertFalse(self.user_ravi.is_superuser)

        # Verify has_perm resolves aliases for Payouts & Escrow
        self.assertTrue(self.ravi_profile.has_perm('PAYOUTS & ESCROW'))
        self.assertTrue(self.ravi_profile.has_perm('PROCESS_PAYOUT'))
        self.assertTrue(self.ravi_profile.has_perm('VIEW_PAYOUTS'))
        self.assertTrue(self.ravi_profile.has_perm('MANAGE_ESCROW'))
        self.assertTrue(self.ravi_profile.has_perm('AUDIT_SETTLEMENT'))

    def test_02_ravi_can_view_payouts_escrow_and_settlements(self):
        """Verify Ravi can view payouts, escrow holdings, and settlement ledger without 403."""
        _, earning = self._create_matured_booking_and_earning()

        self.client.force_authenticate(user=self.user_ravi)

        # 1. Settlement Ledger
        res_ledger = self.client.get('/api/payments/settlements/')
        self.assertEqual(res_ledger.status_code, status.HTTP_200_OK)
        self.assertIn('hotels_summary', res_ledger.data)
        self.assertGreaterEqual(len(res_ledger.data['hotels_summary']), 1)

        # 2. Staff Escrow Holdings
        res_escrow = self.client.get('/api/staff/payouts/escrow/')
        self.assertEqual(res_escrow.status_code, status.HTTP_200_OK)
        self.assertTrue(res_escrow.data['success'])

        # 3. Staff Settlements
        res_settle = self.client.get('/api/staff/payouts/settlements/')
        self.assertEqual(res_settle.status_code, status.HTTP_200_OK)

        # 4. Host Payout Account (View-only for destination audit)
        res_pacc = self.client.get(f'/api/payments/payout-account/?host_id={self.host.id}')
        self.assertEqual(res_pacc.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(res_pacc.data['account'])

    def test_03_ravi_authorized_batch_payout_initiation(self):
        """Verify Ravi can initiate and disburse payouts via /api/payments/admin/payouts/initiate/."""
        booking, earning = self._create_matured_booking_and_earning(booking_ref="KH-2026-BATCH01", amount=Decimal('5000.00'))

        self.client.force_authenticate(user=self.user_ravi)

        payload = {
            'earning_ids': [earning.id],
            'notes': 'Batch disbursement initiated by Escrow Settlement Officer Ravi Patel'
        }
        response = self.client.post('/api/payments/admin/payouts/initiate/', data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('status'), 'success')

        # Verify payout record
        payout = HostPayout.objects.filter(host=self.host).latest('created_at')
        self.assertEqual(payout.status, HostPayout.STATUS_COMPLETED)
        self.assertEqual(payout.processed_by, self.user_ravi)
        self.assertIsNotNone(payout.bank_reference)

        # Verify earning status updated to PAID
        earning.refresh_from_db()
        self.assertEqual(earning.status, HostEarning.STATUS_PAID)
        self.assertEqual(earning.payout, payout)
        self.assertIsNotNone(earning.settled_at)

        # Verify AuditLog created identifying Ravi
        audit_entry = AuditLog.objects.filter(entity_id=payout.payout_id, action='PAYOUT_DISBURSED').first()
        self.assertIsNotNone(audit_entry)
        self.assertEqual(audit_entry.user, self.user_ravi)

        # Verify StaffActivityLog created identifying Ravi's employee ID
        staff_log = StaffActivityLog.objects.filter(
            staff=self.ravi_profile,
            action='PROCESS_PAYOUT'
        ).first()
        self.assertIsNotNone(staff_log)
        self.assertEqual(staff_log.employee_id, 'GOS-EMP-021')
        self.assertEqual(staff_log.actor_username, self.user_ravi.username)
        self.assertIn('GOS-EMP-021', staff_log.description)

    def test_04_ravi_authorized_payout_process_view(self):
        """Verify Ravi can process payouts via /api/staff/payouts/<pk>/process/ using ID or payout_id."""
        booking, earning = self._create_matured_booking_and_earning(booking_ref="KH-2026-STAFF01", amount=Decimal('3500.00'))

        # Create a pending HostPayout record linked to the earning
        payout = HostPayout.objects.create(
            idempotency_key=f"idem_{uuid.uuid4().hex}",
            host=self.host,
            payout_account=self.host_payout_account,
            amount=earning.net_amount,
            status=HostPayout.STATUS_PENDING,
            provider_mode='NEFT'
        )
        earning.payout = payout
        earning.save()

        self.client.force_authenticate(user=self.user_ravi)

        # Test process by integer PK
        res_process = self.client.post(f'/api/staff/payouts/{payout.id}/process/', format='json')
        self.assertEqual(res_process.status_code, status.HTTP_200_OK)
        self.assertTrue(res_process.data['success'])

        payout.refresh_from_db()
        self.assertEqual(payout.status, HostPayout.STATUS_COMPLETED)
        self.assertEqual(payout.processed_by, self.user_ravi)

        earning.refresh_from_db()
        self.assertEqual(earning.status, HostEarning.STATUS_PAID)

        # Test string payout_id lookup on detail view
        res_detail = self.client.get(f'/api/staff/payouts/{payout.payout_id}/')
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(res_detail.data['payout']['payout_id'], payout.payout_id)

    def test_05_holding_period_safeguard_enforced(self):
        """Verify staff cannot disburse unmatured earnings within the mandatory 7-day holding period."""
        booking, unmatured_earning = self._create_unmatured_booking_and_earning()

        self.client.force_authenticate(user=self.user_ravi)

        # 1. Attempt batch initiate on unmatured earning
        payload = {'earning_ids': [unmatured_earning.id]}
        res_initiate = self.client.post('/api/payments/admin/payouts/initiate/', data=payload, format='json')
        self.assertEqual(res_initiate.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('not eligible', res_initiate.data.get('error', '').lower())

        # 2. Attempt process on payout with active hold
        payout = HostPayout.objects.create(
            idempotency_key=f"idem_{uuid.uuid4().hex}",
            host=self.host,
            payout_account=self.host_payout_account,
            amount=unmatured_earning.net_amount,
            status=HostPayout.STATUS_PENDING,
            provider_mode='NEFT'
        )
        unmatured_earning.payout = payout
        unmatured_earning.save()

        res_process = self.client.post(f'/api/staff/payouts/{payout.id}/process/', format='json')
        self.assertEqual(res_process.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res_process.data.get('code'), 'HOLD_PERIOD_ACTIVE')

    def test_06_unauthorized_staff_departments_blocked(self):
        """Verify Reservation staff or Support staff are denied access to payout distribution (403)."""
        _, earning = self._create_matured_booking_and_earning()

        # Reservation Staff (Priya Singh)
        self.client.force_authenticate(user=self.user_res_staff)

        payload = {'earning_ids': [earning.id]}
        res_initiate = self.client.post('/api/payments/admin/payouts/initiate/', data=payload, format='json')
        self.assertEqual(res_initiate.status_code, status.HTTP_403_FORBIDDEN)

        # Staff payout endpoint
        res_staff_payout = self.client.get('/api/staff/payouts/')
        self.assertEqual(res_staff_payout.status_code, status.HTTP_403_FORBIDDEN)

    def test_07_customer_and_owner_blocked(self):
        """Verify Customer and Hotel Owner cannot initiate or process payouts."""
        _, earning = self._create_matured_booking_and_earning()

        payload = {'earning_ids': [earning.id]}

        # Customer
        self.client.force_authenticate(user=self.customer)
        res_cust = self.client.post('/api/payments/admin/payouts/initiate/', data=payload, format='json')
        self.assertEqual(res_cust.status_code, status.HTTP_403_FORBIDDEN)

        # Hotel Owner
        self.client.force_authenticate(user=self.host)
        res_host = self.client.post('/api/payments/admin/payouts/initiate/', data=payload, format='json')
        self.assertEqual(res_host.status_code, status.HTTP_403_FORBIDDEN)

    def test_08_revoked_permission_immediately_blocks_staff(self):
        """Verify revoking the Payout permission immediately denies Ravi's payout authorization."""
        _, earning = self._create_matured_booking_and_earning()

        # Revoke Payouts & Escrow permission from Ravi
        self.ravi_profile.permissions.clear()
        # Give unrelated permission (e.g. VIEW_BOOKINGS only)
        self.ravi_profile.permissions.add(self.perm_view_bookings)

        self.client.force_authenticate(user=self.user_ravi)

        payload = {'earning_ids': [earning.id]}
        response = self.client.post('/api/payments/admin/payouts/initiate/', data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_09_inactive_staff_blocked(self):
        """Verify suspended or inactive staff accounts are denied payout access."""
        _, earning = self._create_matured_booking_and_earning()

        self.ravi_profile.status = StaffProfile.STATUS_SUSPENDED
        self.ravi_profile.save()

        self.client.force_authenticate(user=self.user_ravi)

        payload = {'earning_ids': [earning.id]}
        response = self.client.post('/api/payments/admin/payouts/initiate/', data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_10_admin_continues_to_have_full_payout_capabilities(self):
        """Verify Platform Administrator retains full payout distribution capability."""
        booking, earning = self._create_matured_booking_and_earning(booking_ref="KH-2026-ADMIN01", amount=Decimal('6000.00'))

        self.client.force_authenticate(user=self.admin)

        payload = {
            'earning_ids': [earning.id],
            'notes': 'Admin direct payout initiation'
        }
        response = self.client.post('/api/payments/admin/payouts/initiate/', data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('status'), 'success')

        payout = HostPayout.objects.filter(host=self.host).latest('created_at')
        self.assertEqual(payout.status, HostPayout.STATUS_COMPLETED)
        self.assertEqual(payout.processed_by, self.admin)

    def test_11_verify_payout_status_and_dispute_hold(self):
        """Verify Ravi can verify payout status and toggle dispute holds."""
        _, earning = self._create_matured_booking_and_earning()

        payout = HostPayout.objects.create(
            idempotency_key=f"idem_{uuid.uuid4().hex}",
            host=self.host,
            payout_account=self.host_payout_account,
            amount=earning.net_amount,
            status=HostPayout.STATUS_COMPLETED,
            provider_mode='NEFT',
            provider_payout_id='pout_test_123'
        )

        self.client.force_authenticate(user=self.user_ravi)

        # 1. Verify Payout Status
        res_verify = self.client.post(f'/api/payments/admin/payouts/{payout.payout_id}/verify/')
        self.assertEqual(res_verify.status_code, status.HTTP_200_OK)

        # 2. Toggle Dispute Hold
        dispute_payload = {
            'earning_id': earning.id,
            'is_disputed': True,
            'dispute_reason': 'Guest complaint under investigation'
        }
        res_dispute = self.client.post('/api/payments/admin/earnings/toggle-dispute/', data=dispute_payload, format='json')
        self.assertEqual(res_dispute.status_code, status.HTTP_200_OK)

        earning.refresh_from_db()
        self.assertTrue(earning.is_disputed)
