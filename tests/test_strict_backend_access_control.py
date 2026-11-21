import datetime
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework import status

from staff.models import (
    Department, StaffPermission, StaffProfile, StaffNotification, StaffTicketNote
)
from staff.portals import (
    PORTAL_ADMIN, PORTAL_RESERVATION, PORTAL_CUSTOMER_SUPPORT,
    PORTAL_REFUNDS_AND_CLAIMS, PORTAL_PAYOUT_AND_ESCROW,
    PORTAL_HOTEL_VERIFICATION, PORTAL_CUSTOMER, PORTAL_HOTEL_OWNER
)
from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking
from payments.models import (
    Payment, Refund, HostPayout, HostEarning, HostPayoutAccount,
    SupportTicket, PlatformSetting
)

User = get_user_model()


class StrictBackendAccessControlTestCase(TestCase):
    """
    Exhaustive verification of GoOnStay Strict Role and Department-Based Backend Access Control.
    Enforces backend security boundary across:
    - Admin, Staff, Hotel Owner, Customer
    - All 5 Staff departments (RESERVATION, CUSTOMER_SUPPORT, REFUNDS_AND_CLAIMS, PAYOUT_AND_ESCROW, HOTEL_VERIFICATION)
    - Queryset isolation, object-level isolation, search filtering, immediate permission revocation
    """

    def setUp(self):
        cache.clear()
        self.client = APIClient()

        # 1. Platform Admin
        self.admin = User.objects.create_superuser(
            username='admin_boss',
            email='admin@goonstay.com',
            password='AdminPassword123!',
            first_name='Admin',
            last_name='Supreme',
            role=User.ROLE_ADMIN
        )

        # 2. Customer & Hotel Owner
        self.customer = User.objects.create_user(
            username='cust_neha',
            email='neha@customer.com',
            password='Password123!',
            role=User.ROLE_CUSTOMER
        )
        self.owner = User.objects.create_user(
            username='owner_manish',
            email='manish@hotelowner.com',
            password='Password123!',
            role=User.ROLE_HOTEL_OWNER
        )

        # 3. Seed Hotel & Room & Booking
        self.hotel = Hotel.objects.create(
            owner=self.owner,
            name='Grand Oberoi Palace',
            property_type='HOTEL',
            address='MG Road, Sector 14',
            city='Udaipur',
            state='Rajasthan',
            status=Hotel.STATUS_APPROVED,
            is_approved=True
        )
        self.room = Room.objects.create(
            hotel=self.hotel,
            title='Executive Lakeview Suite',
            room_type='SUITE',
            price_per_night=Decimal('4000.00'),
            total_rooms=5,
            room_numbers='301, 302, 303, 304, 305'
        )
        self.booking = Booking.objects.create(
            booking_id='GOS-BK-SEC001',
            hotel=self.hotel,
            room=self.room,
            customer=self.customer,
            check_in=timezone.now().date(),
            check_out=timezone.now().date() + datetime.timedelta(days=2),
            guest_name='Neha Verma',
            guest_email='neha@customer.com',
            guest_phone='9911223344',
            price_per_night=Decimal('4000.00'),
            subtotal=Decimal('8000.00'),
            total_amount=Decimal('8000.00'),
            room_number='301',
            booking_status=Booking.STATUS_CONFIRMED,
            payment_status='PAID'
        )

        # 4. Seed Support Ticket
        self.ticket = SupportTicket.objects.create(
            ticket_number='TKT-SEC-001',
            user=self.customer,
            booking=self.booking,
            hotel=self.hotel,
            subject='Extra pillows requested',
            description='Please arrange extra pillows for room 301',
            category='BOOKING',
            priority='LOW',
            status='OPEN'
        )

        # 5. Seed Payment, Refund, Payout
        self.payment = Payment.objects.create(
            booking=self.booking,
            user=self.customer,
            razorpay_order_id='order_sec_123',
            razorpay_payment_id='pay_sec_123',
            amount=Decimal('8000.00'),
            status=Payment.STATUS_CAPTURED
        )
        self.refund = Refund.objects.create(
            booking=self.booking,
            payment=self.payment,
            amount=Decimal('2000.00'),
            status=Refund.STATUS_REFUND_PENDING,
            reason='Customer requested early departure refund'
        )
        self.payout = HostPayout.objects.create(
            payout_id='PO-SEC-001',
            host=self.owner,
            amount=Decimal('7200.00'),
            status=HostPayout.STATUS_PENDING
        )

        # 6. Ensure 5 Departments Exist
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

        # 7. Create 5 Department Staff Members
        self.staff_res = self._create_staff('s_res', 'res@goonstay.com', self.dept_res, ['VIEW_BOOKINGS', 'ALLOCATE_ROOMS', 'MANAGE_RESERVATIONS'])
        self.staff_cs = self._create_staff('s_cs', 'cs@goonstay.com', self.dept_cs, ['MANAGE_SUPPORT', 'VIEW_TICKETS', 'RESPOND_TICKET'])
        self.staff_refund = self._create_staff('s_ref', 'ref@goonstay.com', self.dept_refund, ['VIEW_REFUNDS', 'PROCESS_REFUND'])
        self.staff_payout = self._create_staff('s_pay', 'pay@goonstay.com', self.dept_payout, ['VIEW_PAYOUTS', 'PROCESS_PAYOUT'])
        self.staff_hotel = self._create_staff('s_hot', 'hot@goonstay.com', self.dept_hotel, ['VERIFY_HOTEL', 'APPROVE_HOTEL', 'REJECT_HOTEL'])

    def _create_staff(self, username, email, department, perm_codes=None):
        user = User.objects.create_user(
            username=username,
            email=email,
            password='StaffPassword123!',
            first_name='Staff',
            last_name=department.name if department else 'NoDept',
            role=User.ROLE_STAFF,
            is_staff=True
        )
        profile = StaffProfile.objects.create(
            user=user,
            employee_id=f"EMP-{username.upper()}",
            login_id=f"gos_{username}",
            department=department,
            status='ACTIVE',
            must_change_password=False,
            phone_number='9876543210',
            created_by=self.admin
        )
        if perm_codes and department:
            for pcode in perm_codes:
                perm, _ = StaffPermission.objects.get_or_create(
                    code=pcode,
                    defaults={'name': pcode, 'department': department}
                )
                profile.permissions.add(perm)
        return user

    # =========================================================================
    # TEST 1: Admin can access Admin APIs
    # =========================================================================
    def test_01_admin_can_access_admin_apis(self):
        self.client.force_authenticate(user=self.admin)
        res_dash = self.client.get('/api/admin/dashboard/')
        self.assertEqual(res_dash.status_code, status.HTTP_200_OK)

        res_staff = self.client.get('/api/staff/')
        self.assertEqual(res_staff.status_code, status.HTTP_200_OK)

        res_audit = self.client.get('/api/admin/audit-logs/')
        self.assertEqual(res_audit.status_code, status.HTTP_200_OK)

        res_payments = self.client.get('/api/payments/admin/all/')
        self.assertEqual(res_payments.status_code, status.HTTP_200_OK)

    # =========================================================================
    # TEST 2: Staff cannot access Admin Staff Management APIs
    # =========================================================================
    def test_02_staff_cannot_access_admin_staff_management_apis(self):
        for staff_user in [self.staff_res, self.staff_cs, self.staff_refund, self.staff_payout, self.staff_hotel]:
            self.client.force_authenticate(user=staff_user)

            # Staff List
            self.assertEqual(self.client.get('/api/staff/').status_code, status.HTTP_403_FORBIDDEN)
            # Create Staff
            self.assertEqual(self.client.post('/api/staff/create/', {'email': 'hacker@test.com'}).status_code, status.HTTP_403_FORBIDDEN)
            # Admin Audit Logs
            self.assertEqual(self.client.get('/api/admin/audit-logs/').status_code, status.HTTP_403_FORBIDDEN)
            # Admin Payments
            self.assertEqual(self.client.get('/api/payments/admin/all/').status_code, status.HTTP_403_FORBIDDEN)

    # =========================================================================
    # TEST 3: Reservation Staff cannot access Support department APIs
    # =========================================================================
    def test_03_reservation_staff_cannot_access_support_apis(self):
        self.client.force_authenticate(user=self.staff_res)

        res_list = self.client.get('/api/staff/support/')
        self.assertEqual(res_list.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res_list.data.get('code'), 'DEPARTMENT_FORBIDDEN')

        res_dash = self.client.get('/api/staff/support/dashboard/')
        self.assertEqual(res_dash.status_code, status.HTTP_403_FORBIDDEN)

    # =========================================================================
    # TEST 4: Support Staff cannot access Refund APIs
    # =========================================================================
    def test_04_support_staff_cannot_access_refund_apis(self):
        self.client.force_authenticate(user=self.staff_cs)

        res_list = self.client.get('/api/staff/refunds/')
        self.assertEqual(res_list.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res_list.data.get('code'), 'DEPARTMENT_FORBIDDEN')

        res_process = self.client.post(f'/api/staff/refunds/{self.refund.id}/process/')
        self.assertEqual(res_process.status_code, status.HTTP_403_FORBIDDEN)

    # =========================================================================
    # TEST 5: Refund Staff cannot access Payout APIs
    # =========================================================================
    def test_05_refund_staff_cannot_access_payout_apis(self):
        self.client.force_authenticate(user=self.staff_refund)

        res_list = self.client.get('/api/staff/payouts/')
        self.assertEqual(res_list.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res_list.data.get('code'), 'DEPARTMENT_FORBIDDEN')

        res_dash = self.client.get('/api/staff/payouts/dashboard/')
        self.assertEqual(res_dash.status_code, status.HTTP_403_FORBIDDEN)

    # =========================================================================
    # TEST 6: Payout Staff cannot access Verification APIs
    # =========================================================================
    def test_06_payout_staff_cannot_access_verification_apis(self):
        self.client.force_authenticate(user=self.staff_payout)

        res_list = self.client.get('/api/staff/verifications/')
        self.assertEqual(res_list.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res_list.data.get('code'), 'DEPARTMENT_FORBIDDEN')

        res_approve = self.client.post(f'/api/staff/verifications/{self.hotel.id}/approve/')
        self.assertEqual(res_approve.status_code, status.HTTP_403_FORBIDDEN)

    # =========================================================================
    # TEST 7: Verification Staff cannot access Reservation APIs
    # =========================================================================
    def test_07_verification_staff_cannot_access_reservation_apis(self):
        self.client.force_authenticate(user=self.staff_hotel)

        res_list = self.client.get('/api/staff/bookings/')
        self.assertEqual(res_list.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res_list.data.get('code'), 'DEPARTMENT_FORBIDDEN')

        res_dash = self.client.get('/api/staff/reservation/dashboard/')
        self.assertEqual(res_dash.status_code, status.HTTP_403_FORBIDDEN)

    # =========================================================================
    # TEST 8: Staff cannot modify their own department
    # =========================================================================
    def test_08_staff_cannot_modify_own_department(self):
        self.client.force_authenticate(user=self.staff_res)
        profile = self.staff_res.staff_profile

        # Staff calling admin update endpoint to reassign department
        res = self.client.patch(f'/api/staff/{profile.id}/update/', {
            'department_id': self.dept_payout.id
        })
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Confirm department did not change in DB
        profile.refresh_from_db()
        self.assertEqual(profile.department.code, Department.CODE_RESERVATION)

    # =========================================================================
    # TEST 9: Staff cannot increase their own permissions
    # =========================================================================
    def test_09_staff_cannot_increase_own_permissions(self):
        self.client.force_authenticate(user=self.staff_res)
        profile = self.staff_res.staff_profile

        res = self.client.patch(f'/api/staff/{profile.id}/permissions/update/', {
            'permissions': ['PROCESS_REFUND', 'PROCESS_PAYOUT']
        })
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Confirm permissions were not added
        self.assertFalse(profile.has_perm('PROCESS_REFUND'))
        self.assertFalse(profile.has_perm('PROCESS_PAYOUT'))

    # =========================================================================
    # TEST 10: Staff cannot access another department's records through object IDs
    # =========================================================================
    def test_10_staff_cannot_access_other_dept_records_by_id(self):
        # Support staff tries to query Refund #self.refund.id
        self.client.force_authenticate(user=self.staff_cs)
        res_refund = self.client.get(f'/api/staff/refunds/{self.refund.id}/')
        self.assertEqual(res_refund.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res_refund.data.get('code'), 'DEPARTMENT_FORBIDDEN')

        # Reservation staff tries to query Support Ticket #self.ticket.id
        self.client.force_authenticate(user=self.staff_res)
        res_ticket = self.client.get(f'/api/staff/support/{self.ticket.id}/')
        self.assertEqual(res_ticket.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res_ticket.data.get('code'), 'DEPARTMENT_FORBIDDEN')

    # =========================================================================
    # TEST 11: Dashboard statistics are strictly department-filtered
    # =========================================================================
    def test_11_dashboard_statistics_department_filtered(self):
        dash_url = '/api/staff/dashboard/'

        self.client.force_authenticate(user=self.staff_res)
        res = self.client.get(dash_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        metrics = res.data.get('metrics', {})
        self.assertIn('reservation', metrics)
        self.assertNotIn('customer_support', metrics)
        self.assertNotIn('refund', metrics)
        self.assertNotIn('payout', metrics)
        self.assertNotIn('hotel_verification', metrics)

    # =========================================================================
    # TEST 12: Search and exports respect department permissions
    # =========================================================================
    def test_12_search_respects_department_permissions(self):
        # Reservation staff can search bookings
        self.client.force_authenticate(user=self.staff_res)
        res_ok = self.client.get('/api/staff/bookings/?search=Neha')
        self.assertEqual(res_ok.status_code, status.HTTP_200_OK)

        # Support staff cannot search bookings endpoint
        self.client.force_authenticate(user=self.staff_cs)
        res_block = self.client.get('/api/staff/bookings/?search=Neha')
        self.assertEqual(res_block.status_code, status.HTTP_403_FORBIDDEN)

    # =========================================================================
    # TEST 13: Notifications respect department boundaries
    # =========================================================================
    def test_13_notifications_respect_department_boundaries(self):
        # Create a notification specifically for Support department
        cs_notif = StaffNotification.objects.create(
            department=self.dept_cs,
            recipient=self.staff_cs.staff_profile,
            title='Support Ticket Alert',
            message='New ticket opened'
        )

        # Support staff can mark it read
        self.client.force_authenticate(user=self.staff_cs)
        res_ok = self.client.patch(f'/api/staff/notifications/{cs_notif.id}/read/')
        self.assertEqual(res_ok.status_code, status.HTTP_200_OK)

        # Reservation staff attempts to mark read another department's notification
        self.client.force_authenticate(user=self.staff_res)
        res_block = self.client.patch(f'/api/staff/notifications/{cs_notif.id}/read/')
        self.assertEqual(res_block.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res_block.data.get('code'), 'DEPARTMENT_FORBIDDEN')

    # =========================================================================
    # TEST 14: Inactive/suspended Staff cannot access protected APIs
    # =========================================================================
    def test_14_suspended_staff_cannot_access_apis(self):
        self.staff_res.staff_profile.status = 'SUSPENDED'
        self.staff_res.staff_profile.save()

        self.client.force_authenticate(user=self.staff_res)
        res = self.client.get('/api/staff/bookings/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.data.get('code'), 'ACCOUNT_INACTIVE')

        res_nav = self.client.get('/api/portal/navigation/')
        self.assertEqual(res_nav.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res_nav.data.get('code'), 'ACCOUNT_INACTIVE')

    # =========================================================================
    # TEST 15: Department reassignment takes effect immediately
    # =========================================================================
    def test_15_department_reassignment_takes_effect_immediately(self):
        self.client.force_authenticate(user=self.staff_res)
        # Initially in Reservation
        self.assertEqual(self.client.get('/api/staff/bookings/').status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get('/api/staff/support/').status_code, status.HTTP_403_FORBIDDEN)

        # Admin dynamically transfers employee to Customer Support in DB
        self.staff_res.staff_profile.department = self.dept_cs
        self.staff_res.staff_profile.save()
        p_cs, _ = StaffPermission.objects.get_or_create(
            code='MANAGE_SUPPORT',
            defaults={'name': 'MANAGE_SUPPORT', 'department': self.dept_cs}
        )
        self.staff_res.staff_profile.permissions.set([p_cs])
        self.staff_res.refresh_from_db()
        self.staff_res.staff_profile.refresh_from_db()

        # Immediate effect without re-login
        res_old = self.client.get('/api/staff/bookings/')
        self.assertEqual(res_old.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res_old.data.get('code'), 'DEPARTMENT_FORBIDDEN')

        res_new = self.client.get('/api/staff/support/')
        self.assertEqual(res_new.status_code, status.HTTP_200_OK)

    # =========================================================================
    # TEST 16: Permission revocation takes effect immediately
    # =========================================================================
    def test_16_permission_revocation_takes_effect_immediately(self):
        self.client.force_authenticate(user=self.staff_refund)
        p_process = StaffPermission.objects.get(code='PROCESS_REFUND', department=self.dept_refund)

        # Currently has PROCESS_REFUND
        self.assertTrue(self.staff_refund.staff_profile.has_perm('PROCESS_REFUND'))

        # Admin dynamically revokes permission
        self.staff_refund.staff_profile.permissions.remove(p_process)

        # Attempt to process refund immediately denied
        res = self.client.post(f'/api/staff/refunds/{self.refund.id}/process/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    # =========================================================================
    # TEST 17: Invalid/missing department never becomes Admin
    # =========================================================================
    def test_17_missing_department_never_becomes_admin(self):
        # Create a staff account with no department profile
        orphan_user = User.objects.create_user(
            username='s_orphan',
            email='orphan@goonstay.com',
            password='StaffPassword123!',
            role=User.ROLE_STAFF,
            is_staff=True
        )

        self.client.force_authenticate(user=orphan_user)

        # Navigation fails safely with 403 (never defaults to Admin or Customer)
        res_nav = self.client.get('/api/portal/navigation/')
        self.assertEqual(res_nav.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn(res_nav.data.get('code'), ['NO_DEPARTMENT_ASSIGNED', 'NO_STAFF_PROFILE'])

        # Admin dashboard access denied
        res_admin = self.client.get('/api/admin/dashboard/')
        self.assertEqual(res_admin.status_code, status.HTTP_403_FORBIDDEN)

    # =========================================================================
    # TEST 18: Existing Admin workflows continue working
    # =========================================================================
    def test_18_existing_admin_workflows_continue_working(self):
        self.client.force_authenticate(user=self.admin)

        # Platform Settings
        res_settings = self.client.get('/api/payments/settings/')
        self.assertEqual(res_settings.status_code, status.HTTP_200_OK)

        # Host Payout Accounts
        res_acc = self.client.get('/api/payments/payout-account/')
        self.assertEqual(res_acc.status_code, status.HTTP_200_OK)

        # Platform Audit Logs
        res_logs = self.client.get('/api/admin/audit-logs/')
        self.assertEqual(res_logs.status_code, status.HTTP_200_OK)

    # =========================================================================
    # TEST 19: Existing Customer and Hotel Owner workflows continue working
    # =========================================================================
    def test_19_customer_and_owner_workflows_continue_working(self):
        # Customer views their own booking
        self.client.force_authenticate(user=self.customer)
        res_bk = self.client.get(f'/api/bookings/{self.booking.booking_id}/')
        self.assertEqual(res_bk.status_code, status.HTTP_200_OK)

        # Customer creates a support ticket
        res_tkt = self.client.post('/api/payments/support-tickets/', {
            'subject': 'WiFi password request',
            'description': 'What is the WiFi password for 3rd floor?',
            'category': 'HOTEL'
        })
        self.assertEqual(res_tkt.status_code, status.HTTP_201_CREATED)

        # Hotel owner views their settlement ledgers
        self.client.force_authenticate(user=self.owner)
        res_earn = self.client.get('/api/host/earnings/')
        self.assertEqual(res_earn.status_code, status.HTTP_200_OK)

    # =========================================================================
    # TEST 20: Existing refund, payout, booking, payment, and verification workflows continue working
    # =========================================================================
    def test_20_existing_department_workflows_continue_working(self):
        # 1. Reservation staff views booking list
        self.client.force_authenticate(user=self.staff_res)
        res_bks = self.client.get('/api/staff/bookings/')
        self.assertEqual(res_bks.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(res_bks.data.get('results', [])), 1)

        # 2. Support staff adds internal note
        self.client.force_authenticate(user=self.staff_cs)
        res_note = self.client.post(f'/api/staff/support/{self.ticket.id}/notes/', {
            'note': 'Customer requested foam pillows; housekeeping dispatched.'
        })
        self.assertEqual(res_note.status_code, status.HTTP_201_CREATED)
        self.assertTrue(StaffTicketNote.objects.filter(ticket=self.ticket).exists())

        # 3. Verification staff approves hotel
        self.client.force_authenticate(user=self.staff_hotel)
        res_app = self.client.post(f'/api/staff/verifications/{self.hotel.id}/approve/')
        self.assertEqual(res_app.status_code, status.HTTP_200_OK)
        self.hotel.refresh_from_db()
        self.assertEqual(self.hotel.status, Hotel.STATUS_APPROVED)
        self.assertTrue(self.hotel.is_approved)

        # 4. Payout staff views payouts list
        self.client.force_authenticate(user=self.staff_payout)
        res_pay = self.client.get('/api/staff/payouts/')
        self.assertEqual(res_pay.status_code, status.HTTP_200_OK)
