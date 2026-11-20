import datetime
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework import status

from staff.models import Department, StaffPermission, StaffProfile
from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking
from payments.models import Payment, Refund, HostPayout, HostEarning, SupportTicket

User = get_user_model()


class StaffDepartmentIsolationTestCase(TestCase):
    """
    Comprehensive verification for:
    1. Exact 5 staff departments (RESERVATION, CUSTOMER_SUPPORT, REFUNDS_AND_CLAIMS, PAYOUT_AND_ESCROW, HOTEL_VERIFICATION).
    2. Department-based login & portal assignment.
    3. Strict backend portal isolation (cross-department blocking with 403 DEPARTMENT_FORBIDDEN).
    4. Anti-tampering: staff cannot choose or change department.
    5. Admin-controlled dynamic department reassignment taking effect immediately.
    6. Granular action permission enforcement within allowed department.
    """

    def setUp(self):
        cache.clear()
        self.client = APIClient()

        # Admin
        self.admin = User.objects.create_superuser(
            username='admin_boss',
            email='admin@goonstay.com',
            password='AdminPassword123!',
            first_name='System',
            last_name='Admin',
            role=User.ROLE_ADMIN
        )

        # Customer & Hotel Owner
        self.customer = User.objects.create_user(
            username='cust_alex',
            email='alex@customer.com',
            password='Password123!',
            role=User.ROLE_CUSTOMER
        )
        self.owner = User.objects.create_user(
            username='owner_rajesh',
            email='rajesh@hotelowner.com',
            password='Password123!',
            role=User.ROLE_HOTEL_OWNER
        )

        # Seed Hotel & Room & Booking
        self.hotel = Hotel.objects.create(
            owner=self.owner,
            name='Ocean Breeze Resort',
            property_type='HOTEL',
            address='123 Beach Road',
            city='Goa',
            state='Goa',
            country='India',
            status=Hotel.STATUS_APPROVED,
            is_approved=True
        )
        self.room = Room.objects.create(
            hotel=self.hotel,
            title='Deluxe Sea View Room',
            room_type='DELUXE',
            price_per_night=Decimal('2500.00'),
            total_rooms=5,
            room_numbers='101, 102, 103, 104, 105'
        )
        self.booking = Booking.objects.create(
            booking_id='GOS-BK-TEST01',
            hotel=self.hotel,
            room=self.room,
            customer=self.customer,
            check_in=timezone.now().date(),
            check_out=timezone.now().date() + datetime.timedelta(days=2),
            guest_name='Alex Customer',
            guest_email='alex@customer.com',
            guest_phone='9876543210',
            price_per_night=Decimal('2500.00'),
            subtotal=Decimal('5000.00'),
            total_amount=Decimal('5000.00'),
            room_number='101',
            booking_status=Booking.STATUS_CONFIRMED,
            payment_status='PAID'
        )

        # Seed Support Ticket
        self.ticket = SupportTicket.objects.create(
            ticket_number='TKT-TEST-001',
            user=self.customer,
            booking=self.booking,
            hotel=self.hotel,
            subject='AC not working',
            description='Room 101 AC issue',
            category='ROOM_ISSUE',
            priority='HIGH',
            status='OPEN'
        )

        # Seed Payment
        self.payment = Payment.objects.create(
            booking=self.booking,
            user=self.customer,
            razorpay_order_id='order_test_123',
            razorpay_payment_id='pay_test_123',
            amount=Decimal('5000.00'),
            status=Payment.STATUS_CAPTURED
        )

        # Seed Refund
        self.refund = Refund.objects.create(
            booking=self.booking,
            payment=self.payment,
            amount=Decimal('1000.00'),
            status='PENDING',
            reason='Customer requested partial refund'
        )

        # Seed Payout
        self.payout = HostPayout.objects.create(
            payout_id='PO-TEST-001',
            host=self.owner,
            amount=Decimal('4500.00'),
            status=HostPayout.STATUS_PENDING
        )

        # Ensure the 5 Departments exist
        self.dept_res, _ = Department.objects.get_or_create(
            code=Department.CODE_RESERVATION,
            defaults={'name': 'Reservation', 'is_active': True}
        )
        self.dept_cs, _ = Department.objects.get_or_create(
            code=Department.CODE_CUSTOMER_SUPPORT,
            defaults={'name': 'Customer Support', 'is_active': True}
        )
        self.dept_refund, _ = Department.objects.get_or_create(
            code=Department.CODE_REFUNDS_AND_CLAIMS,
            defaults={'name': 'Refunds & Claims', 'is_active': True}
        )
        self.dept_payout, _ = Department.objects.get_or_create(
            code=Department.CODE_PAYOUT_AND_ESCROW,
            defaults={'name': 'Payout & Escrow', 'is_active': True}
        )
        self.dept_hotel, _ = Department.objects.get_or_create(
            code=Department.CODE_HOTEL_VERIFICATION,
            defaults={'name': 'Hotel Verification', 'is_active': True}
        )

        # Permissions
        self.p_view_b, _ = StaffPermission.objects.get_or_create(
            code='VIEW_BOOKINGS', defaults={'name': 'View Bookings', 'department': self.dept_res}
        )
        self.p_manage_sup, _ = StaffPermission.objects.get_or_create(
            code='MANAGE_SUPPORT', defaults={'name': 'Manage Support', 'department': self.dept_cs}
        )
        self.p_view_ref, _ = StaffPermission.objects.get_or_create(
            code='VIEW_REFUNDS', defaults={'name': 'View Refunds', 'department': self.dept_refund}
        )
        self.p_proc_ref, _ = StaffPermission.objects.get_or_create(
            code='PROCESS_REFUND', defaults={'name': 'Process Refund', 'department': self.dept_refund}
        )
        self.p_view_pay, _ = StaffPermission.objects.get_or_create(
            code='VIEW_PAYOUTS', defaults={'name': 'View Payouts', 'department': self.dept_payout}
        )
        self.p_proc_pay, _ = StaffPermission.objects.get_or_create(
            code='PROCESS_PAYOUT', defaults={'name': 'Process Payout', 'department': self.dept_payout}
        )
        self.p_verify_h, _ = StaffPermission.objects.get_or_create(
            code='VERIFY_HOTEL', defaults={'name': 'Verify Hotel', 'department': self.dept_hotel}
        )

        # Create 1 employee for each of the 5 departments
        self.staff_res = self._create_staff('emp_res', 'res@goonstay.com', 'EMP-RES-1', 'res.login', self.dept_res, [self.p_view_b])
        self.staff_cs = self._create_staff('emp_cs', 'cs@goonstay.com', 'EMP-CS-1', 'cs.login', self.dept_cs, [self.p_manage_sup])
        self.staff_refund = self._create_staff('emp_refund', 'refund@goonstay.com', 'EMP-REF-1', 'refund.login', self.dept_refund, [self.p_view_ref, self.p_proc_ref])
        self.staff_payout = self._create_staff('emp_payout', 'payout@goonstay.com', 'EMP-PAY-1', 'payout.login', self.dept_payout, [self.p_view_pay, self.p_proc_pay])
        self.staff_hotel = self._create_staff('emp_hotel', 'hotel@goonstay.com', 'EMP-HOT-1', 'hotel.login', self.dept_hotel, [self.p_verify_h])

    def _create_staff(self, username, email, emp_id, login_id, department, perms):
        user = User.objects.create_user(
            username=username,
            email=email,
            password='StaffPassword123!',
            first_name=username.capitalize(),
            last_name='Staff',
            role=User.ROLE_STAFF,
            is_staff=True
        )
        profile = StaffProfile.objects.create(
            user=user,
            employee_id=emp_id,
            login_id=login_id,
            department=department,
            status=StaffProfile.STATUS_ACTIVE,
            must_change_password=False,
            created_by=self.admin
        )
        profile.permissions.set(perms)
        return profile

    # =========================================================================
    # 1. TEST DEPARTMENT-BASED LOGIN & PORTAL ROUTING
    # =========================================================================

    def test_reservation_staff_login_returns_reservation_portal(self):
        cache.clear()
        res = self.client.post('/api/staff/login/', data={
            'login_id': 'res.login',
            'password': 'StaffPassword123!'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['department'], 'RESERVATION')
        self.assertEqual(res.data['portal'], 'RESERVATION')
        self.assertEqual(res.data['portal_url'], '/staff/reservation')
        self.assertEqual(res.data['portal_name'], 'Reservation Portal')

    def test_customer_support_staff_login_returns_support_portal(self):
        cache.clear()
        res = self.client.post('/api/staff/login/', data={
            'login_id': 'cs.login',
            'password': 'StaffPassword123!'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['department'], 'CUSTOMER_SUPPORT')
        self.assertEqual(res.data['portal'], 'CUSTOMER_SUPPORT')
        self.assertEqual(res.data['portal_url'], '/staff/support')
        self.assertEqual(res.data['portal_name'], 'Customer Support Portal')

    def test_refunds_and_claims_staff_login_returns_refunds_portal(self):
        cache.clear()
        res = self.client.post('/api/staff/login/', data={
            'login_id': 'refund.login',
            'password': 'StaffPassword123!'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['department'], 'REFUNDS_AND_CLAIMS')
        self.assertEqual(res.data['portal'], 'REFUNDS_AND_CLAIMS')
        self.assertEqual(res.data['portal_url'], '/staff/refunds')
        self.assertEqual(res.data['portal_name'], 'Refunds & Claims Portal')

    def test_payout_and_escrow_staff_login_returns_payout_portal(self):
        cache.clear()
        res = self.client.post('/api/staff/login/', data={
            'login_id': 'payout.login',
            'password': 'StaffPassword123!'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['department'], 'PAYOUT_AND_ESCROW')
        self.assertEqual(res.data['portal'], 'PAYOUT_AND_ESCROW')
        self.assertEqual(res.data['portal_url'], '/staff/payouts')
        self.assertEqual(res.data['portal_name'], 'Payout & Escrow Portal')

    def test_hotel_verification_staff_login_returns_verification_portal(self):
        cache.clear()
        res = self.client.post('/api/staff/login/', data={
            'login_id': 'hotel.login',
            'password': 'StaffPassword123!'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['department'], 'HOTEL_VERIFICATION')
        self.assertEqual(res.data['portal'], 'HOTEL_VERIFICATION')
        self.assertEqual(res.data['portal_url'], '/staff/verification')
        self.assertEqual(res.data['portal_name'], 'Hotel Verification Portal')

    def test_me_api_returns_verified_portal_info(self):
        self.client.force_authenticate(user=self.staff_res.user)
        res = self.client.get('/api/staff/me/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['department'], 'RESERVATION')
        self.assertEqual(res.data['portal'], 'RESERVATION')
        self.assertEqual(res.data['portal_url'], '/staff/reservation')

    # =========================================================================
    # 2. STRICT BACKEND DEPARTMENT ACCESS CONTROL & ISOLATION
    # =========================================================================

    def test_reservation_staff_access_success_on_bookings(self):
        self.client.force_authenticate(user=self.staff_res.user)
        res = self.client.get('/api/staff/bookings/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_reservation_staff_strictly_forbidden_from_other_departments(self):
        self.client.force_authenticate(user=self.staff_res.user)

        # Cross-access 1: Refunds
        res = self.client.get('/api/staff/refunds/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('DEPARTMENT_FORBIDDEN', str(res.data))

        # Cross-access 2: Payouts
        res = self.client.get('/api/staff/payouts/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('DEPARTMENT_FORBIDDEN', str(res.data))

        # Cross-access 3: Customer Support
        res = self.client.get('/api/staff/support/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('DEPARTMENT_FORBIDDEN', str(res.data))

        # Cross-access 4: Hotel Verification
        res = self.client.get('/api/staff/verifications/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('DEPARTMENT_FORBIDDEN', str(res.data))

    def test_customer_support_staff_strictly_forbidden_from_financial_and_booking_apis(self):
        self.client.force_authenticate(user=self.staff_cs.user)

        # Allowed
        res = self.client.get('/api/staff/support/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Blocked: Bookings
        res = self.client.get('/api/staff/bookings/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('DEPARTMENT_FORBIDDEN', str(res.data))

        # Blocked: Refunds
        res = self.client.get('/api/staff/refunds/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('DEPARTMENT_FORBIDDEN', str(res.data))

        # Blocked: Payouts
        res = self.client.get('/api/staff/payouts/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('DEPARTMENT_FORBIDDEN', str(res.data))

        # Blocked: Hotel Verifications
        res = self.client.get('/api/staff/verifications/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('DEPARTMENT_FORBIDDEN', str(res.data))

    def test_refund_staff_strictly_forbidden_from_payouts_and_verifications(self):
        self.client.force_authenticate(user=self.staff_refund.user)

        # Allowed
        res = self.client.get('/api/staff/refunds/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Blocked: Payouts
        res = self.client.get('/api/staff/payouts/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('DEPARTMENT_FORBIDDEN', str(res.data))

        # Blocked: Hotel Verifications
        res = self.client.get('/api/staff/verifications/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('DEPARTMENT_FORBIDDEN', str(res.data))

    def test_payout_staff_strictly_forbidden_from_refunds_and_bookings(self):
        self.client.force_authenticate(user=self.staff_payout.user)

        # Allowed
        res = self.client.get('/api/staff/payouts/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Blocked: Refunds
        res = self.client.get('/api/staff/refunds/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('DEPARTMENT_FORBIDDEN', str(res.data))

        # Blocked: Bookings
        res = self.client.get('/api/staff/bookings/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('DEPARTMENT_FORBIDDEN', str(res.data))

    def test_hotel_verification_staff_strictly_forbidden_from_financial_apis(self):
        self.client.force_authenticate(user=self.staff_hotel.user)

        # Allowed
        res = self.client.get('/api/staff/verifications/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Blocked: Refunds
        res = self.client.get('/api/staff/refunds/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('DEPARTMENT_FORBIDDEN', str(res.data))

        # Blocked: Payouts
        res = self.client.get('/api/staff/payouts/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('DEPARTMENT_FORBIDDEN', str(res.data))

    # =========================================================================
    # 3. ANTI-TAMPERING & ADMIN EXCLUSIVE DEPARTMENT CONTROL
    # =========================================================================

    def test_staff_cannot_change_own_department(self):
        self.client.force_authenticate(user=self.staff_res.user)
        # Attempt to change department via update API
        res = self.client.patch(f'/api/staff/{self.staff_res.id}/update/', data={
            'department': 'HOTEL_VERIFICATION'
        }, format='json')
        # Blocked by IsAdminUserRole
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Department must remain unchanged
        self.staff_res.refresh_from_db()
        self.assertEqual(self.staff_res.department.code, 'RESERVATION')

    def test_admin_updates_staff_department_takes_effect_immediately(self):
        # 1. Verify staff initially has access to Reservation
        self.client.force_authenticate(user=self.staff_res.user)
        res1 = self.client.get('/api/staff/bookings/')
        self.assertEqual(res1.status_code, status.HTTP_200_OK)

        # 2. Admin transfers staff to HOTEL_VERIFICATION department
        self.client.force_authenticate(user=self.admin)
        res_admin = self.client.patch(f'/api/staff/{self.staff_res.id}/update/', data={
            'department': 'HOTEL_VERIFICATION'
        }, format='json')
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)

        # Admin also gives the appropriate permission for the new department
        self.staff_res.permissions.add(self.p_verify_h)

        # 3. Staff immediately attempts to access bookings again -> MUST BE BLOCKED
        self.client.force_authenticate(user=self.staff_res.user)
        res_blocked = self.client.get('/api/staff/bookings/')
        self.assertEqual(res_blocked.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('DEPARTMENT_FORBIDDEN', str(res_blocked.data))

        # 4. Staff immediately has access to new department (Hotel Verification)
        res_new_dept = self.client.get('/api/staff/verifications/')
        self.assertEqual(res_new_dept.status_code, status.HTTP_200_OK)

        # 5. /api/staff/me/ immediately reflects new portal
        res_me = self.client.get('/api/staff/me/')
        self.assertEqual(res_me.status_code, status.HTTP_200_OK)
        self.assertEqual(res_me.data['department'], 'HOTEL_VERIFICATION')
        self.assertEqual(res_me.data['portal'], 'HOTEL_VERIFICATION')
        self.assertEqual(res_me.data['portal_url'], '/staff/verification')

    # =========================================================================
    # 4. GRANULAR ACTION PERMISSION ENFORCEMENT
    # =========================================================================

    def test_missing_granular_action_permission_denies_action(self):
        # Create a refund staff who only has VIEW_REFUNDS, not PROCESS_REFUND
        user_refund_viewer = User.objects.create_user(
            username='viewer_refund',
            email='viewer_refund@goonstay.com',
            password='StaffPassword123!',
            role=User.ROLE_STAFF,
            is_staff=True
        )
        profile_viewer = StaffProfile.objects.create(
            user=user_refund_viewer,
            employee_id='EMP-REF-VIEWER',
            login_id='viewer.refund',
            department=self.dept_refund,
            status=StaffProfile.STATUS_ACTIVE,
            must_change_password=False,
            created_by=self.admin
        )
        profile_viewer.permissions.set([self.p_view_ref])

        self.client.force_authenticate(user=user_refund_viewer)

        # Can view refunds
        res_view = self.client.get('/api/staff/refunds/')
        self.assertEqual(res_view.status_code, status.HTTP_200_OK)

        # Cannot process refund (missing PROCESS_REFUND)
        res_proc = self.client.post(f'/api/staff/refunds/{self.refund.id}/process/', data={}, format='json')
        self.assertEqual(res_proc.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('PERMISSION_DENIED', str(res_proc.data))
