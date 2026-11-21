import datetime
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework import status

from staff.models import Department, StaffPermission, StaffProfile
from staff.portals import (
    PORTAL_ADMIN, PORTAL_RESERVATION, PORTAL_CUSTOMER_SUPPORT,
    PORTAL_REFUNDS_AND_CLAIMS, PORTAL_PAYOUT_AND_ESCROW,
    PORTAL_HOTEL_VERIFICATION, PORTAL_CUSTOMER, PORTAL_HOTEL_OWNER
)
from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking
from payments.models import Payment, Refund, HostPayout, HostEarning, SupportTicket

User = get_user_model()


class RoleWisePortalArchitectureTestCase(TestCase):
    """
    Comprehensive test suite verifying GoOnStay Complete Role-Wise Separate Portal Architecture.
    Validates:
    1. Navigation and portal contract for all 8 roles & departments.
    2. Route guards and security isolation across all dedicated dashboards.
    3. Zero metrics leak in general staff dashboard.
    4. Account status guards (inactive, password change required).
    """

    def setUp(self):
        cache.clear()
        self.client = APIClient()

        # 1. Admin
        self.admin = User.objects.create_superuser(
            username='admin_boss',
            email='admin@goonstay.com',
            password='AdminPassword123!',
            first_name='Admin',
            last_name='Boss',
            role=User.ROLE_ADMIN
        )

        # 2. Customer
        self.customer = User.objects.create_user(
            username='cust_riya',
            email='riya@customer.com',
            password='Password123!',
            role=User.ROLE_CUSTOMER
        )

        # 3. Hotel Owner
        self.owner = User.objects.create_user(
            username='owner_vikram',
            email='vikram@hotelowner.com',
            password='Password123!',
            role=User.ROLE_HOTEL_OWNER
        )

        # 4. Seed Hotels & Rooms & Bookings
        self.hotel = Hotel.objects.create(
            owner=self.owner,
            name='Royal Heritage Palace',
            property_type='HOTEL',
            address='M.G. Road',
            city='Jaipur',
            state='Rajasthan',
            status=Hotel.STATUS_APPROVED,
            is_approved=True
        )
        self.room = Room.objects.create(
            hotel=self.hotel,
            title='Royal Deluxe Suite',
            room_type='SUITE',
            price_per_night=Decimal('3500.00'),
            total_rooms=4,
            room_numbers='201, 202, 203, 204'
        )
        self.booking = Booking.objects.create(
            booking_id='GOS-BK-ROLE01',
            hotel=self.hotel,
            room=self.room,
            customer=self.customer,
            check_in=timezone.now().date(),
            check_out=timezone.now().date() + datetime.timedelta(days=2),
            guest_name='Riya Sharma',
            guest_email='riya@customer.com',
            guest_phone='9988776655',
            price_per_night=Decimal('3500.00'),
            subtotal=Decimal('7000.00'),
            total_amount=Decimal('7000.00'),
            room_number='201',
            booking_status=Booking.STATUS_CONFIRMED,
            payment_status='PAID'
        )

        # 5. Seed Support Ticket
        self.ticket = SupportTicket.objects.create(
            ticket_number='TKT-ROLE-001',
            user=self.customer,
            booking=self.booking,
            hotel=self.hotel,
            subject='Late check-in inquiry',
            description='Can I check in at 11 PM?',
            category='BOOKING',
            priority='MEDIUM',
            status='OPEN'
        )

        # 6. Seed Payment & Refund
        self.payment = Payment.objects.create(
            booking=self.booking,
            user=self.customer,
            razorpay_order_id='order_role_123',
            razorpay_payment_id='pay_role_123',
            amount=Decimal('7000.00'),
            status=Payment.STATUS_CAPTURED
        )
        self.refund = Refund.objects.create(
            booking=self.booking,
            payment=self.payment,
            amount=Decimal('1500.00'),
            status=Refund.STATUS_REFUND_PENDING,
            reason='Customer requested date modification'
        )

        # 7. Seed Payout
        self.payout = HostPayout.objects.create(
            payout_id='PO-ROLE-001',
            host=self.owner,
            amount=Decimal('6300.00'),
            status=HostPayout.STATUS_PENDING
        )

        # 8. Ensure 5 Departments Exist
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

        # 9. Create 5 Department Staff Members
        self.staff_res = self._create_staff('staff_res', 'res@goonstay.com', self.dept_res, ['VIEW_BOOKINGS', 'ALLOCATE_ROOMS'])
        self.staff_cs = self._create_staff('staff_cs', 'cs@goonstay.com', self.dept_cs, ['MANAGE_SUPPORT', 'VIEW_TICKETS'])
        self.staff_refund = self._create_staff('staff_ref', 'ref@goonstay.com', self.dept_refund, ['VIEW_REFUNDS', 'PROCESS_REFUND'])
        self.staff_payout = self._create_staff('staff_pay', 'pay@goonstay.com', self.dept_payout, ['VIEW_PAYOUTS', 'PROCESS_PAYOUT'])
        self.staff_hotel = self._create_staff('staff_hot', 'hot@goonstay.com', self.dept_hotel, ['VERIFY_HOTEL', 'APPROVE_HOTEL'])

    def _create_staff(self, username, email, department, perm_codes=None):
        user = User.objects.create_user(
            username=username,
            email=email,
            password='StaffPassword123!',
            first_name='Staff',
            last_name=department.name,
            role=User.ROLE_STAFF,
            is_staff=True
        )
        emp_id = f"EMP-{username.upper()}"
        login_id = f"gos_{username}"
        profile = StaffProfile.objects.create(
            user=user,
            employee_id=emp_id,
            login_id=login_id,
            department=department,
            status='ACTIVE',
            must_change_password=False,
            phone_number='9811223344',
            created_by=self.admin
        )
        if perm_codes:
            for pcode in perm_codes:
                perm, _ = StaffPermission.objects.get_or_create(
                    code=pcode,
                    defaults={'name': pcode, 'department': department}
                )
                profile.permissions.add(perm)
        return user

    # =========================================================================
    # TEST 1: ALL 8 ROLES RECEIVE STRICTLY ISOLATED PORTAL DEFINITIONS
    # =========================================================================
    def test_navigation_contract_for_all_8_portals(self):
        url = '/api/portal/navigation/'

        # 1. ADMIN
        self.client.force_authenticate(user=self.admin)
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['portal']['portal_id'], PORTAL_ADMIN)
        self.assertEqual(res.data['portal']['layout'], 'AdminLayout')
        self.assertEqual(res.data['portal']['dashboard_url'], '/admin/dashboard')
        self.assertEqual(len(res.data['portal']['sidebar']), 18)
        self.assertIn('/admin/deleted-hotels', res.data['portal']['permitted_routes'])
        self.assertIn('/admin/staff', res.data['portal']['permitted_routes'])

        # 2. RESERVATION STAFF
        self.client.force_authenticate(user=self.staff_res)
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['portal']['portal_id'], PORTAL_RESERVATION)
        self.assertEqual(res.data['portal']['layout'], 'StaffReservationLayout')
        self.assertEqual(res.data['portal']['dashboard_url'], '/staff/reservation')
        self.assertEqual(len(res.data['portal']['sidebar']), 7)
        self.assertNotIn('/staff/refunds', res.data['portal']['permitted_routes'])
        self.assertNotIn('/staff/payouts', res.data['portal']['permitted_routes'])

        # 3. CUSTOMER SUPPORT STAFF
        self.client.force_authenticate(user=self.staff_cs)
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['portal']['portal_id'], PORTAL_CUSTOMER_SUPPORT)
        self.assertEqual(res.data['portal']['layout'], 'StaffSupportLayout')
        self.assertEqual(res.data['portal']['dashboard_url'], '/staff/support')
        self.assertEqual(len(res.data['portal']['sidebar']), 7)
        self.assertNotIn('/staff/reservation', res.data['portal']['permitted_routes'])

        # 4. REFUNDS & CLAIMS STAFF
        self.client.force_authenticate(user=self.staff_refund)
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['portal']['portal_id'], PORTAL_REFUNDS_AND_CLAIMS)
        self.assertEqual(res.data['portal']['layout'], 'StaffRefundsLayout')
        self.assertEqual(res.data['portal']['dashboard_url'], '/staff/refunds')
        self.assertEqual(len(res.data['portal']['sidebar']), 7)
        self.assertNotIn('/staff/support', res.data['portal']['permitted_routes'])

        # 5. PAYOUT & ESCROW STAFF
        self.client.force_authenticate(user=self.staff_payout)
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['portal']['portal_id'], PORTAL_PAYOUT_AND_ESCROW)
        self.assertEqual(res.data['portal']['layout'], 'StaffPayoutsLayout')
        self.assertEqual(res.data['portal']['dashboard_url'], '/staff/payouts')
        self.assertEqual(len(res.data['portal']['sidebar']), 7)
        self.assertNotIn('/staff/verification', res.data['portal']['permitted_routes'])

        # 6. HOTEL VERIFICATION STAFF
        self.client.force_authenticate(user=self.staff_hotel)
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['portal']['portal_id'], PORTAL_HOTEL_VERIFICATION)
        self.assertEqual(res.data['portal']['layout'], 'StaffVerificationLayout')
        self.assertEqual(res.data['portal']['dashboard_url'], '/staff/verification')
        self.assertEqual(len(res.data['portal']['sidebar']), 7)
        self.assertNotIn('/staff/bookings', res.data['portal']['permitted_routes'])

        # 7. HOTEL OWNER
        self.client.force_authenticate(user=self.owner)
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['portal']['portal_id'], PORTAL_HOTEL_OWNER)
        self.assertEqual(res.data['portal']['layout'], 'HotelOwnerLayout')
        self.assertEqual(res.data['portal']['dashboard_url'], '/host/dashboard')
        self.assertEqual(len(res.data['portal']['sidebar']), 8)
        self.assertNotIn('/admin/dashboard', res.data['portal']['permitted_routes'])

        # 8. CUSTOMER
        self.client.force_authenticate(user=self.customer)
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['portal']['portal_id'], PORTAL_CUSTOMER)
        self.assertEqual(res.data['portal']['layout'], 'CustomerLayout')
        self.assertEqual(res.data['portal']['dashboard_url'], '/customer/dashboard')
        self.assertEqual(len(res.data['portal']['sidebar']), 5)
        self.assertNotIn('/staff/dashboard', res.data['portal']['permitted_routes'])

    # =========================================================================
    # TEST 2: NAVIGATION GUARDS FOR INACTIVE & PENDING PASSWORD CHANGE
    # =========================================================================
    def test_navigation_guards_inactive_and_password_change(self):
        url = '/api/portal/navigation/'

        # Anonymous request
        self.client.logout()
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        # Inactive staff account
        self.staff_res.staff_profile.status = 'SUSPENDED'
        self.staff_res.staff_profile.save()
        self.client.force_authenticate(user=self.staff_res)
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.data.get('code'), 'ACCOUNT_INACTIVE')

        # Must change password
        self.staff_res.staff_profile.status = 'ACTIVE'
        self.staff_res.staff_profile.must_change_password = True
        self.staff_res.staff_profile.save()
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.data.get('code'), 'PASSWORD_CHANGE_REQUIRED')

    # =========================================================================
    # TEST 3: DEDICATED ADMIN DASHBOARD ACCESS CONTROL
    # =========================================================================
    def test_dedicated_admin_dashboard_access_control(self):
        url = '/api/admin/dashboard/'

        # Admin succeeds
        self.client.force_authenticate(user=self.admin)
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('overview', res.data)
        self.assertIn('staff', res.data['overview'])
        self.assertIn('financials', res.data['overview'])

        # Non-admin roles are forbidden
        for non_admin in [self.staff_res, self.staff_cs, self.staff_refund, self.staff_payout, self.staff_hotel, self.owner, self.customer]:
            self.client.force_authenticate(user=non_admin)
            res = self.client.get(url)
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    # =========================================================================
    # TEST 4: DEDICATED STAFF DASHBOARDS ISOLATION
    # =========================================================================
    def test_dedicated_staff_dashboards_cross_isolation(self):
        # 1. Reservation Dashboard
        res_url = '/api/staff/reservation/dashboard/'
        self.client.force_authenticate(user=self.staff_res)
        res = self.client.get(res_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('metrics', res.data)
        self.assertIn('total_bookings', res.data['metrics'])

        # Cross-access blocked
        self.client.force_authenticate(user=self.staff_cs)
        self.assertEqual(self.client.get(res_url).status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(user=self.staff_refund)
        self.assertEqual(self.client.get(res_url).status_code, status.HTTP_403_FORBIDDEN)

        # 2. Support Dashboard
        cs_url = '/api/staff/support/dashboard/'
        self.client.force_authenticate(user=self.staff_cs)
        res = self.client.get(cs_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('open_tickets', res.data['metrics'])

        self.client.force_authenticate(user=self.staff_res)
        self.assertEqual(self.client.get(cs_url).status_code, status.HTTP_403_FORBIDDEN)

        # 3. Refunds Dashboard
        ref_url = '/api/staff/refunds/dashboard/'
        self.client.force_authenticate(user=self.staff_refund)
        res = self.client.get(ref_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('pending_refunds', res.data['metrics'])

        self.client.force_authenticate(user=self.staff_payout)
        self.assertEqual(self.client.get(ref_url).status_code, status.HTTP_403_FORBIDDEN)

        # 4. Payouts Dashboard
        pay_url = '/api/staff/payouts/dashboard/'
        self.client.force_authenticate(user=self.staff_payout)
        res = self.client.get(pay_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('pending_payouts', res.data['metrics'])

        self.client.force_authenticate(user=self.staff_hotel)
        self.assertEqual(self.client.get(pay_url).status_code, status.HTTP_403_FORBIDDEN)

        # 5. Verification Dashboard
        ver_url = '/api/staff/verification/dashboard/'
        self.client.force_authenticate(user=self.staff_hotel)
        res = self.client.get(ver_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('pending_verifications', res.data['metrics'])

        self.client.force_authenticate(user=self.staff_res)
        self.assertEqual(self.client.get(ver_url).status_code, status.HTTP_403_FORBIDDEN)

    # =========================================================================
    # TEST 5: GENERAL STAFF DASHBOARD ZERO METRICS LEAK
    # =========================================================================
    def test_general_staff_dashboard_zero_metrics_leak(self):
        dash_url = '/api/staff/dashboard/'

        # Reservation staff sees ONLY reservation metrics
        self.client.force_authenticate(user=self.staff_res)
        res = self.client.get(dash_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        metrics = res.data.get('metrics', {})
        self.assertIn('reservation', metrics)
        self.assertNotIn('customer_support', metrics)
        self.assertNotIn('refund', metrics)
        self.assertNotIn('payout', metrics)
        self.assertNotIn('hotel_verification', metrics)

        # Support staff sees ONLY customer_support metrics
        self.client.force_authenticate(user=self.staff_cs)
        res = self.client.get(dash_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        metrics = res.data.get('metrics', {})
        self.assertIn('customer_support', metrics)
        self.assertNotIn('reservation', metrics)
        self.assertNotIn('refund', metrics)
        self.assertNotIn('payout', metrics)
        self.assertNotIn('hotel_verification', metrics)

        # Refund staff sees ONLY refund metrics
        self.client.force_authenticate(user=self.staff_refund)
        res = self.client.get(dash_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        metrics = res.data.get('metrics', {})
        self.assertIn('refund', metrics)
        self.assertNotIn('reservation', metrics)
        self.assertNotIn('customer_support', metrics)
        self.assertNotIn('payout', metrics)
        self.assertNotIn('hotel_verification', metrics)

        # Payout staff sees ONLY payout metrics
        self.client.force_authenticate(user=self.staff_payout)
        res = self.client.get(dash_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        metrics = res.data.get('metrics', {})
        self.assertIn('payout', metrics)
        self.assertNotIn('reservation', metrics)
        self.assertNotIn('customer_support', metrics)
        self.assertNotIn('refund', metrics)
        self.assertNotIn('hotel_verification', metrics)

        # Verification staff sees ONLY hotel_verification metrics
        self.client.force_authenticate(user=self.staff_hotel)
        res = self.client.get(dash_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        metrics = res.data.get('metrics', {})
        self.assertIn('hotel_verification', metrics)
        self.assertNotIn('reservation', metrics)
        self.assertNotIn('customer_support', metrics)
        self.assertNotIn('refund', metrics)
        self.assertNotIn('payout', metrics)
