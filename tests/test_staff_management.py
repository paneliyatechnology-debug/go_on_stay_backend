import datetime
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from staff.models import (
    Department, StaffPermission, StaffProfile, StaffActivityLog,
    StaffNotification, StaffPasswordResetToken, StaffTicketNote
)
from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking
from payments.models import Payment, Refund, HostPayout, HostEarning, SupportTicket

User = get_user_model()


class StaffManagementBaseTestCase(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.client = APIClient()

        # 1. Admin User
        self.admin = User.objects.create_superuser(
            username='admin_boss',
            email='admin@goonstay.com',
            password='AdminPassword123!',
            first_name='System',
            last_name='Admin',
            role=User.ROLE_ADMIN
        )

        # 2. Customer User
        self.customer = User.objects.create_user(
            username='customer_jane',
            email='jane@example.com',
            password='CustomerPassword123!',
            first_name='Jane',
            last_name='Doe',
            phone_number='9876543210',
            role=User.ROLE_CUSTOMER
        )

        # 3. Hotel Owner User
        self.owner = User.objects.create_user(
            username='owner_raj',
            email='raj@hotelowner.com',
            password='OwnerPassword123!',
            first_name='Rajesh',
            last_name='Sharma',
            phone_number='9123456780',
            role=User.ROLE_HOTEL_OWNER
        )

        # 4. Hotel & Room
        self.hotel = Hotel.objects.create(
            owner=self.owner,
            name='GoOnStay Heritage Haven',
            city='Jaipur',
            address='MI Road, Jaipur',
            status=Hotel.STATUS_APPROVED,
            is_approved=True
        )
        self.room = Room.objects.create(
            hotel=self.hotel,
            title='Royal Deluxe Room',
            room_type='DELUXE',
            price_per_night=Decimal('2500.00'),
            total_rooms=5,
            room_numbers='101, 102, 103, 104, 105'
        )

        # 5. Fetch Seeded Departments & Permissions
        self.dept_reservation = Department.objects.get(code=Department.CODE_RESERVATION)
        self.dept_support = Department.objects.get(code=Department.CODE_CUSTOMER_SUPPORT)
        self.dept_refund = Department.objects.get(code=Department.CODE_REFUND)
        self.dept_payout = Department.objects.get(code=Department.CODE_PAYOUT)
        self.dept_verification = Department.objects.get(code=Department.CODE_HOTEL_VERIFICATION)

        self.perm_view_bookings = StaffPermission.objects.get(code='VIEW_BOOKINGS')
        self.perm_view_refunds = StaffPermission.objects.get(code='VIEW_REFUNDS')
        self.perm_process_refund = StaffPermission.objects.get(code='PROCESS_REFUND')
        self.perm_view_payouts = StaffPermission.objects.get(code='VIEW_PAYOUTS')
        self.perm_process_payout = StaffPermission.objects.get(code='PROCESS_PAYOUT')
        self.perm_manage_support = StaffPermission.objects.get(code='MANAGE_SUPPORT')
        self.perm_verify_hotel = StaffPermission.objects.get(code='VERIFY_HOTEL')

    def create_staff_user(self, username, email, department, permissions=None, must_change_password=False, staff_status='ACTIVE'):
        user = User.objects.create_user(
            username=username,
            email=email,
            password='StaffPassword123!',
            first_name='Test',
            last_name='Staff',
            role=User.ROLE_STAFF
        )
        profile = StaffProfile.objects.create(
            user=user,
            employee_id=f"GOS-EMP-{StaffProfile.objects.count() + 1:03d}",
            login_id=f"{username}.{department.code.lower()[:3]}",
            department=department,
            status=staff_status,
            must_change_password=must_change_password,
            created_by=self.admin
        )
        if permissions:
            profile.permissions.set(permissions)
        return user, profile

    def create_test_booking(self, **kwargs):
        defaults = {
            'booking_id': f"BKG-TEST-{Booking.objects.count() + 1:04d}",
            'customer': self.customer,
            'hotel': self.hotel,
            'room': self.room,
            'check_in': datetime.date.today() + datetime.timedelta(days=1),
            'check_out': datetime.date.today() + datetime.timedelta(days=3),
            'price_per_night': Decimal('2500.00'),
            'subtotal': Decimal('5000.00'),
            'total_amount': Decimal('5000.00'),
            'guest_name': 'Jane Doe',
            'guest_email': 'jane@example.com',
            'guest_phone': '9876543210',
            'booking_status': Booking.STATUS_CONFIRMED,
            'room_number': '101'
        }
        defaults.update(kwargs)
        return Booking.objects.create(**defaults)


class StaffAccountLifecycleTests(StaffManagementBaseTestCase):
    def test_admin_can_create_staff_member(self):
        self.client.force_authenticate(user=self.admin)
        payload = {
            'first_name': 'Amit',
            'last_name': 'Kumar',
            'email': 'amit.kumar@goonstay.com',
            'department_id': self.dept_reservation.id,
            'designation': 'Senior Reservation Officer',
            'phone_number': '9811223344',
            'permission_ids': [self.perm_view_bookings.id]
        }
        res = self.client.post('/api/staff/create/', data=payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(res.data['success'])
        data = res.data['data']

        # Verify Sequential Employee ID
        self.assertTrue(data['employee_id'].startswith('GOS-EMP-'))
        self.assertIn('amit.reservation', data['login_id'])
        # Temporary password must be returned once in plain text
        temp_pwd = data.get('temporary_password')
        self.assertIsNotNone(temp_pwd)
        self.assertGreaterEqual(len(temp_pwd), 12)
        self.assertTrue(data['must_change_password'])

        # Verify DB integrity: User created with ROLE_STAFF
        user = User.objects.get(email='amit.kumar@goonstay.com')
        self.assertEqual(user.role, User.ROLE_STAFF)
        self.assertTrue(user.check_password(temp_pwd))

        # Profile created and permission assigned
        profile = user.staff_profile
        self.assertEqual(profile.department, self.dept_reservation)
        self.assertTrue(profile.permissions.filter(code='VIEW_BOOKINGS').exists())

        # Verify Activity Logged
        self.assertTrue(StaffActivityLog.objects.filter(action='CREATE_STAFF', target_entity_id=profile.employee_id).exists())

    def test_sequential_employee_id_generation(self):
        self.client.force_authenticate(user=self.admin)
        for i in range(1, 4):
            payload = {
                'first_name': f'Staff{i}',
                'last_name': 'Member',
                'email': f'staff{i}@goonstay.com',
                'department_id': self.dept_support.id,
                'designation': 'Support Exec',
                'phone_number': f'981122334{i}',
                'permission_ids': [self.perm_manage_support.id]
            }
            res = self.client.post('/api/staff/create/', data=payload, format='json')
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)
            self.assertEqual(res.data['data']['employee_id'], f'GOS-EMP-{i:03d}')

    def test_non_admin_cannot_create_staff(self):
        # Customer attempt
        self.client.force_authenticate(user=self.customer)
        res = self.client.post('/api/staff/create/', data={'first_name': 'Hacker'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Hotel Owner attempt
        self.client.force_authenticate(user=self.owner)
        res = self.client.post('/api/staff/create/', data={'first_name': 'Hacker'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Staff attempt
        staff_user, _ = self.create_staff_user('staff_guy', 'guy@goonstay.com', self.dept_reservation)
        self.client.force_authenticate(user=staff_user)
        res = self.client.post('/api/staff/create/', data={'first_name': 'Hacker'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_update_staff_profile_and_status(self):
        _, profile = self.create_staff_user('neha_ops', 'neha@goonstay.com', self.dept_refund)
        self.client.force_authenticate(user=self.admin)

        # Update designation and phone
        res = self.client.put(f'/api/staff/{profile.id}/update/', data={
            'designation': 'Lead Refund Analyst',
            'phone_number': '9988776655'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        profile.refresh_from_db()
        self.assertEqual(profile.designation, 'Lead Refund Analyst')

        # Update status to INACTIVE
        res = self.client.patch(f'/api/staff/{profile.id}/status/', data={
            'status': 'INACTIVE',
            'reason': 'On extended leave'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        profile.refresh_from_db()
        self.assertEqual(profile.status, 'INACTIVE')
        self.assertFalse(profile.user.is_active)

    def test_admin_can_update_staff_permissions(self):
        _, profile = self.create_staff_user('vikram_pay', 'vikram@goonstay.com', self.dept_payout, permissions=[self.perm_view_payouts])
        self.client.force_authenticate(user=self.admin)

        # Add PROCESS_PAYOUT permission
        res = self.client.post(f'/api/staff/{profile.id}/permissions/update/', data={
            'permission_ids': [self.perm_view_payouts.id, self.perm_process_payout.id]
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        profile.refresh_from_db()
        self.assertTrue(profile.permissions.filter(code='PROCESS_PAYOUT').exists())


class StaffAuthenticationTests(StaffManagementBaseTestCase):
    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        cache.clear()
        self.staff_user = User.objects.create_user(
            username='arun_res',
            email='arun@goonstay.com',
            password='InitialPassword123!',
            first_name='Arun',
            last_name='Verma',
            role=User.ROLE_STAFF
        )
        self.staff_profile = StaffProfile.objects.create(
            user=self.staff_user,
            employee_id='GOS-EMP-099',
            login_id='arun.reservation001',
            department=self.dept_reservation,
            status=StaffProfile.STATUS_ACTIVE,
            must_change_password=True,
            created_by=self.admin
        )
        self.staff_profile.permissions.set([self.perm_view_bookings])

    def test_login_with_login_id_success(self):
        res = self.client.post('/api/staff/login/', data={
            'identifier': 'arun.reservation001',
            'password': 'InitialPassword123!'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['success'])
        tokens = res.data['data']['tokens']
        self.assertIn('access', tokens)
        self.assertIn('refresh', tokens)
        self.assertTrue(res.data['data']['must_change_password'])

    def test_login_with_email_success(self):
        res = self.client.post('/api/staff/login/', data={
            'identifier': 'arun@goonstay.com',
            'password': 'InitialPassword123!'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['success'])

    def test_login_with_invalid_credentials_fails(self):
        res = self.client.post('/api/staff/login/', data={
            'identifier': 'arun.reservation001',
            'password': 'WrongPassword999!'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_with_inactive_staff_fails(self):
        self.staff_profile.status = StaffProfile.STATUS_INACTIVE
        self.staff_profile.save()
        res = self.client.post('/api/staff/login/', data={
            'identifier': 'arun.reservation001',
            'password': 'InitialPassword123!'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_must_change_password_enforcement_blocks_workflows(self):
        self.client.force_authenticate(user=self.staff_user)

        # Attempting to access staff bookings must be blocked
        res = self.client.get('/api/staff/bookings/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('PASSWORD_CHANGE_REQUIRED', str(res.data))

        # But me/ and change-password/ are allowed
        res_me = self.client.get('/api/staff/me/')
        self.assertEqual(res_me.status_code, status.HTTP_200_OK)

        # Change password
        res_change = self.client.post('/api/staff/change-password/', data={
            'old_password': 'InitialPassword123!',
            'new_password': 'BrandNewSecurePassword123!',
            'confirm_password': 'BrandNewSecurePassword123!'
        }, format='json')
        self.assertEqual(res_change.status_code, status.HTTP_200_OK)

        # Verify must_change_password is now False
        self.staff_profile.refresh_from_db()
        self.assertFalse(self.staff_profile.must_change_password)

        # Now staff bookings access succeeds
        res_bookings = self.client.get('/api/staff/bookings/')
        self.assertEqual(res_bookings.status_code, status.HTTP_200_OK)

    def test_forgot_and_reset_password_flow(self):
        # 1. Request forgot password
        res = self.client.post('/api/staff/forgot-password/', data={
            'identifier': 'arun.reservation001'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Verify token created in DB
        reset_token_obj = StaffPasswordResetToken.objects.filter(staff_profile=self.staff_profile).first()
        self.assertIsNotNone(reset_token_obj)
        self.assertFalse(reset_token_obj.is_used)

        # For testing the reset endpoint, generate valid token and hash it
        import secrets
        from staff.utils import hash_token
        raw_token = secrets.token_urlsafe(32)
        reset_token_obj.token_hash = hash_token(raw_token)
        reset_token_obj.expires_at = timezone.now() + datetime.timedelta(hours=1)
        reset_token_obj.save()

        # 2. Reset password using valid raw token
        res_reset = self.client.post('/api/staff/reset-password/', data={
            'token': raw_token,
            'new_password': 'CompletelyNewPassword123!',
            'confirm_password': 'CompletelyNewPassword123!'
        }, format='json')
        self.assertEqual(res_reset.status_code, status.HTTP_200_OK)

        # Verify token marked used
        reset_token_obj.refresh_from_db()
        self.assertTrue(reset_token_obj.is_used)

        # 3. Attempting to re-use token fails
        res_reuse = self.client.post('/api/staff/reset-password/', data={
            'token': raw_token,
            'new_password': 'AnotherNewPassword123!',
            'confirm_password': 'AnotherNewPassword123!'
        }, format='json')
        self.assertEqual(res_reuse.status_code, status.HTTP_400_BAD_REQUEST)


class StaffRBACPermissionTests(StaffManagementBaseTestCase):
    def setUp(self):
        super().setUp()
        # Reservation Staff (has VIEW_BOOKINGS only)
        self.res_user, self.res_profile = self.create_staff_user(
            'res_officer', 'res@goonstay.com', self.dept_reservation, permissions=[self.perm_view_bookings]
        )
        # Refund Staff (has VIEW_REFUNDS only, NO PROCESS_REFUND)
        self.refund_viewer_user, self.refund_viewer_profile = self.create_staff_user(
            'ref_viewer', 'ref_viewer@goonstay.com', self.dept_refund, permissions=[self.perm_view_refunds]
        )
        # Refund Staff (has VIEW_REFUNDS + PROCESS_REFUND)
        self.refund_processor_user, self.refund_processor_profile = self.create_staff_user(
            'ref_processor', 'ref_proc@goonstay.com', self.dept_refund, permissions=[self.perm_view_refunds, self.perm_process_refund]
        )
        # Payout Staff (has VIEW_PAYOUTS only)
        self.payout_viewer_user, self.payout_viewer_profile = self.create_staff_user(
            'pay_viewer', 'pay_viewer@goonstay.com', self.dept_payout, permissions=[self.perm_view_payouts]
        )

    def test_cross_department_access_is_forbidden(self):
        # Reservation staff cannot access refunds, payouts, or verifications
        self.client.force_authenticate(user=self.res_user)
        self.assertEqual(self.client.get('/api/staff/refunds/').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get('/api/staff/payouts/').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get('/api/staff/verifications/').status_code, status.HTTP_403_FORBIDDEN)

    def test_granular_permission_enforcement_for_sensitive_actions(self):
        # Create a mock refund
        booking = self.create_test_booking(
            booking_id='BKG-TEST-REF-001',
            check_in=datetime.date.today() + datetime.timedelta(days=2),
            check_out=datetime.date.today() + datetime.timedelta(days=4),
            booking_status=Booking.STATUS_CANCELLED
        )
        payment = Payment.objects.create(
            booking=booking,
            user=self.customer,
            amount=Decimal('5000.00'),
            razorpay_payment_id='pay_test_granular_123',
            status='COMPLETED'
        )
        refund = Refund.objects.create(
            booking=booking,
            payment=payment,
            amount=Decimal('4500.00'),
            reason='Customer requested cancellation',
            status='REQUESTED'
        )

        # 1. Staff with VIEW_REFUNDS only can view list and detail
        self.client.force_authenticate(user=self.refund_viewer_user)
        res_view = self.client.get(f'/api/staff/refunds/{refund.id}/')
        self.assertEqual(res_view.status_code, status.HTTP_200_OK)

        # But cannot process refund (403 Forbidden)
        res_process = self.client.post(f'/api/staff/refunds/{refund.id}/process/', data={'notes': 'Approved'}, format='json')
        self.assertEqual(res_process.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Staff with PROCESS_REFUND can execute process
        self.client.force_authenticate(user=self.refund_processor_user)
        with patch('staff.views.execute_refund_with_provider') as mock_refund:
            def fake_refund(**kwargs):
                r = kwargs.get('refund_record')
                r.status = Refund.STATUS_REFUNDED
                r.razorpay_refund_id = 'rfnd_test_123'
                r.save()
                return r
            mock_refund.side_effect = fake_refund
            res_proc = self.client.post(f'/api/staff/refunds/{refund.id}/process/', data={'notes': 'Approved by staff'}, format='json')
            self.assertEqual(res_proc.status_code, status.HTTP_200_OK)
            self.assertTrue(res_proc.data['success'])

    def test_customer_and_owner_forbidden_from_staff_endpoints(self):
        # Customer blocked
        self.client.force_authenticate(user=self.customer)
        self.assertEqual(self.client.get('/api/staff/bookings/').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get('/api/staff/dashboard/').status_code, status.HTTP_403_FORBIDDEN)

        # Hotel Owner blocked
        self.client.force_authenticate(user=self.owner)
        self.assertEqual(self.client.get('/api/staff/bookings/').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get('/api/staff/dashboard/').status_code, status.HTTP_403_FORBIDDEN)


class StaffDepartmentWorkflowsTests(StaffManagementBaseTestCase):
    def test_reservation_staff_workflow(self):
        res_user, _ = self.create_staff_user('res_staff', 'res@goonstay.com', self.dept_reservation, permissions=[self.perm_view_bookings])
        booking = self.create_test_booking(
            booking_id='BKG-TEST-RES-001',
            guest_name='Jane Doe',
            check_in=datetime.date.today() + datetime.timedelta(days=5),
            check_out=datetime.date.today() + datetime.timedelta(days=7),
            booking_status=Booking.STATUS_CONFIRMED,
            room_number='101'
        )

        self.client.force_authenticate(user=res_user)
        # List bookings
        res_list = self.client.get('/api/staff/bookings/?q=Jane')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_list.data['data']['results']), 1)

        # Booking detail
        res_detail = self.client.get(f'/api/staff/bookings/{booking.id}/')
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(res_detail.data['data']['guest_name'], 'Jane Doe')
        self.assertEqual(res_detail.data['data']['hotel_name'], self.hotel.name)

    def test_payout_staff_7_day_holding_rule(self):
        payout_user, _ = self.create_staff_user('pay_staff', 'pay@goonstay.com', self.dept_payout, permissions=[self.perm_view_payouts, self.perm_process_payout])

        # Create recent checkout booking (e.g. 2 days ago)
        recent_checkout = datetime.date.today() - datetime.timedelta(days=2)
        booking = self.create_test_booking(
            booking_id='BKG-TEST-PAY-001',
            check_in=recent_checkout - datetime.timedelta(days=2),
            check_out=recent_checkout,
            booking_status=Booking.STATUS_COMPLETED
        )
        payout = HostPayout.objects.create(
            host=self.owner,
            amount=Decimal('4500.00'),
            status=HostPayout.STATUS_PENDING
        )
        earning = HostEarning.objects.create(
            host=self.owner,
            booking=booking,
            payout=payout,
            gross_amount=Decimal('5000.00'),
            platform_fee=Decimal('500.00'),
            net_amount=Decimal('4500.00'),
            holding_period_days=7,
            hold_until=timezone.now() + datetime.timedelta(days=5),
            status=HostEarning.STATUS_ON_HOLD
        )

        self.client.force_authenticate(user=payout_user)

        # 1. Immature payout attempt should fail due to holding period
        res_fail = self.client.post(f'/api/staff/payouts/{payout.id}/process/', data={'notes': 'Disburse now'}, format='json')
        self.assertEqual(res_fail.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('holding period', str(res_fail.data).lower())

        # 2. Make earning mature (checkout was 8 days ago)
        mature_checkout = datetime.date.today() - datetime.timedelta(days=8)
        booking.check_out = mature_checkout
        booking.save()
        earning.hold_until = timezone.now() - datetime.timedelta(days=1)
        earning.status = HostEarning.STATUS_AVAILABLE
        earning.save()

        # Mature payout attempt should succeed
        res_success = self.client.post(f'/api/staff/payouts/{payout.id}/process/', data={
            'notes': 'Bank NEFT disbursed',
            'transaction_id': 'NEFT_ICICI_998877'
        }, format='json')
        self.assertEqual(res_success.status_code, status.HTTP_200_OK)
        payout.refresh_from_db()
        self.assertEqual(payout.status, HostPayout.STATUS_COMPLETED)

    def test_customer_support_staff_internal_notes(self):
        support_user, _ = self.create_staff_user('supp_staff', 'supp@goonstay.com', self.dept_support, permissions=[self.perm_manage_support])
        ticket = SupportTicket.objects.create(
            ticket_number='TICK-TEST-001',
            user=self.customer,
            hotel=self.hotel,
            subject='AC not working in room 101',
            description='The AC is leaking water and not cooling.',
            status='OPEN',
            priority='HIGH'
        )

        self.client.force_authenticate(user=support_user)

        # Update ticket status
        res_update = self.client.patch(f'/api/staff/support/{ticket.id}/update/', data={
            'status': 'IN_PROGRESS',
            'priority': 'URGENT'
        }, format='json')
        self.assertEqual(res_update.status_code, status.HTTP_200_OK)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, 'IN_PROGRESS')

        # Add internal-only note
        res_note = self.client.post(f'/api/staff/support/{ticket.id}/notes/', data={
            'note': 'Contacted hotel maintenance; technician dispatched at 3 PM.'
        }, format='json')
        self.assertEqual(res_note.status_code, status.HTTP_201_CREATED)
        self.assertTrue(res_note.data['data']['is_internal_only'])

        # Verify note is flagged as internal
        note = StaffTicketNote.objects.filter(ticket=ticket).first()
        self.assertIsNotNone(note)
        self.assertTrue(note.is_internal_only)

    def test_hotel_verification_staff_workflow(self):
        verify_user, _ = self.create_staff_user('ver_staff', 'ver@goonstay.com', self.dept_verification, permissions=[self.perm_verify_hotel])
        unverified_hotel = Hotel.objects.create(
            owner=self.owner,
            name='Sunset Resort Beach',
            city='Goa',
            address='Calangute Beach Road',
            status=Hotel.STATUS_SUBMITTED,
            is_approved=False
        )

        self.client.force_authenticate(user=verify_user)

        # 1. Reject without reason must fail
        res_reject_fail = self.client.post(f'/api/staff/verifications/{unverified_hotel.id}/reject/', data={}, format='json')
        self.assertEqual(res_reject_fail.status_code, status.HTTP_400_BAD_REQUEST)

        # 2. Reject with reason succeeds
        res_reject = self.client.post(f'/api/staff/verifications/{unverified_hotel.id}/reject/', data={
            'rejection_reason': 'FSSAI certificate is expired. Please re-upload current certificate.'
        }, format='json')
        self.assertEqual(res_reject.status_code, status.HTTP_200_OK)
        unverified_hotel.refresh_from_db()
        self.assertFalse(unverified_hotel.is_approved)
        self.assertEqual(unverified_hotel.status, Hotel.STATUS_REJECTED)

        # 3. Approve hotel succeeds
        res_approve = self.client.post(f'/api/staff/verifications/{unverified_hotel.id}/approve/', data={
            'notes': 'All documents verified and physically audited.'
        }, format='json')
        self.assertEqual(res_approve.status_code, status.HTTP_200_OK)
        unverified_hotel.refresh_from_db()
        self.assertTrue(unverified_hotel.is_approved)
        self.assertEqual(unverified_hotel.status, Hotel.STATUS_APPROVED)


class StaffNotificationsAndDashboardTests(StaffManagementBaseTestCase):
    def test_staff_notifications_and_read_markers(self):
        staff_user, profile = self.create_staff_user('notif_staff', 'notif@goonstay.com', self.dept_reservation, permissions=[self.perm_view_bookings])
        n1 = StaffNotification.objects.create(
            recipient=profile,
            title='New VIP Booking Assigned',
            message='Booking #999 needs early check-in coordination.'
        )
        n2 = StaffNotification.objects.create(
            recipient=profile,
            title='System Maintenance Scheduled',
            message='Maintenance at 2 AM tonight.'
        )

        self.client.force_authenticate(user=staff_user)

        # List unread notifications
        res_list = self.client.get('/api/staff/notifications/?unread_only=true')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertEqual(res_list.data['data']['unread_count'], 2)

        # Mark single notification read
        res_read_one = self.client.post(f'/api/staff/notifications/{n1.id}/read/')
        self.assertEqual(res_read_one.status_code, status.HTTP_200_OK)
        n1.refresh_from_db()
        self.assertTrue(n1.is_read)

        # Mark all read
        res_read_all = self.client.post('/api/staff/notifications/read-all/')
        self.assertEqual(res_read_all.status_code, status.HTTP_200_OK)
        n2.refresh_from_db()
        self.assertTrue(n2.is_read)

    def test_staff_dashboard_metrics(self):
        staff_user, _ = self.create_staff_user('dash_staff', 'dash@goonstay.com', self.dept_reservation, permissions=[self.perm_view_bookings])
        self.client.force_authenticate(user=staff_user)

        res = self.client.get('/api/staff/dashboard/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['success'])
        metrics = res.data['data']['metrics']
        self.assertIn('reservation', metrics)
        self.assertIn('total_bookings', metrics['reservation'])
