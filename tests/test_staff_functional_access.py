import datetime
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework import status

from staff.models import Department, StaffPermission, StaffProfile
from hotels.models import Hotel, HotelVerificationDocument
from rooms.models import Room
from bookings.models import Booking
from payments.models import Payment, Refund, HostPayout, HostEarning, SupportTicket, TicketMessage

User = get_user_model()


class StaffFunctionalAccessTestCase(TestCase):
    """
    Complete end-to-end test suite for GOONSTAY Staff Portal Functional Access:
    1. Functional operation enablement across all 5 departments
    2. Strict cross-department isolation (HTTP 403 DEPARTMENT_FORBIDDEN)
    3. Strict admin endpoint denial (HTTP 403)
    4. Immediate deactivation & suspension blocking (HTTP 403 ACCOUNT_INACTIVE)
    5. Temporary password change enforcement (HTTP 403 PASSWORD_CHANGE_REQUIRED)
    6. Centralized portal navigation contract verification
    """

    def setUp(self):
        cache.clear()
        self.client = APIClient()

        # Admin User
        self.admin = User.objects.create_superuser(
            username='admin_super',
            email='admin@goonstay.com',
            password='AdminPassword123!',
            first_name='Platform',
            last_name='Admin',
            role=User.ROLE_ADMIN
        )

        # Host User
        self.owner = User.objects.create_user(
            username='host_rahul',
            email='rahul@hotelhost.com',
            password='HostPassword123!',
            role=User.ROLE_HOTEL_OWNER
        )

        # Customer User
        self.customer = User.objects.create_user(
            username='guest_priya',
            email='priya@guest.com',
            password='GuestPassword123!',
            role=User.ROLE_CUSTOMER
        )

        # Hotels
        self.hotel = Hotel.objects.create(
            owner=self.owner,
            name='Grand Heritage Hotel',
            property_type='HOTEL',
            address='MG Road 10',
            city='Bengaluru',
            state='Karnataka',
            country='India',
            status=Hotel.STATUS_APPROVED,
            is_approved=True
        )

        self.pending_hotel = Hotel.objects.create(
            owner=self.owner,
            name='Sunset Palms Resort',
            property_type='RESORT',
            address='North Beach 4',
            city='Goa',
            state='Goa',
            country='India',
            status=Hotel.STATUS_SUBMITTED,
            is_approved=False
        )

        # Verification Document
        self.doc = HotelVerificationDocument.objects.create(
            hotel=self.pending_hotel,
            document_type=HotelVerificationDocument.DOC_BUSINESS_REG,
            document_url='https://example.com/docs/trade_license.pdf',
            status='PENDING'
        )

        # Room & Booking
        self.room = Room.objects.create(
            hotel=self.hotel,
            title='Deluxe King Suite',
            room_type='DELUXE',
            price_per_night=Decimal('3500.00'),
            total_rooms=4,
            capacity_adults=2,
            capacity_children=1,
            room_numbers='201, 202, 203, 204'
        )

        self.booking = Booking.objects.create(
            booking_id='GOS-BK-FN01',
            hotel=self.hotel,
            room=self.room,
            customer=self.customer,
            check_in=timezone.now().date(),
            check_out=timezone.now().date() + datetime.timedelta(days=3),
            guest_name='Priya Sharma',
            guest_email='priya@guest.com',
            guest_phone='9876543210',
            price_per_night=Decimal('3500.00'),
            subtotal=Decimal('10500.00'),
            total_amount=Decimal('10500.00'),
            refundable_amount=Decimal('10500.00'),
            room_number='201',
            booking_status=Booking.STATUS_CONFIRMED,
            payment_status='PAID'
        )

        # Payment & Refund
        self.payment = Payment.objects.create(
            booking=self.booking,
            user=self.customer,
            razorpay_order_id='order_fn_123',
            razorpay_payment_id='pay_fn_123',
            amount=Decimal('10500.00'),
            status=Payment.STATUS_CAPTURED
        )

        self.refund = Refund.objects.create(
            booking=self.booking,
            payment=self.payment,
            amount=Decimal('2000.00'),
            status=Refund.STATUS_REFUND_PENDING,
            reason='Partial cancellation adjustment',
            refund_mode=Refund.REFUND_MODE_ORIGINAL
        )

        # Support Ticket
        self.ticket = SupportTicket.objects.create(
            ticket_number='TKT-FN-001',
            user=self.customer,
            booking=self.booking,
            hotel=self.hotel,
            subject='Late check-in inquiry',
            description='Can I check in after 10 PM?',
            category='GENERAL',
            priority='NORMAL',
            status='OPEN'
        )

        # Host Earning & Payout
        past_hold = timezone.now() - datetime.timedelta(days=8)
        self.earning = HostEarning.objects.create(
            host=self.owner,
            booking=self.booking,
            gross_amount=Decimal('10500.00'),
            platform_fee=Decimal('1050.00'),
            net_amount=Decimal('9450.00'),
            status=HostEarning.STATUS_ON_HOLD,
            hold_until=past_hold
        )

        self.payout = HostPayout.objects.create(
            payout_id='PO-FN-001',
            host=self.owner,
            amount=Decimal('9450.00'),
            status=HostPayout.STATUS_PENDING
        )
        self.payout.earnings.add(self.earning)

        # Departments
        self.dept_res = Department.objects.get(code='RESERVATION')
        self.dept_cs = Department.objects.get(code='CUSTOMER_SUPPORT')
        self.dept_refund = Department.objects.get(code='REFUNDS_AND_CLAIMS')
        self.dept_payout = Department.objects.get(code='PAYOUT_AND_ESCROW')
        self.dept_hotel = Department.objects.get(code='HOTEL_VERIFICATION')

        # Staff Users (1 per department)
        self.staff_res = self._create_staff('emp_res', 'res@gos.com', 'EMP-RES', 'res.user', self.dept_res)
        self.staff_cs = self._create_staff('emp_cs', 'cs@gos.com', 'EMP-CS', 'cs.user', self.dept_cs)
        self.staff_refund = self._create_staff('emp_refund', 'ref@gos.com', 'EMP-REF', 'ref.user', self.dept_refund)
        self.staff_payout = self._create_staff('emp_payout', 'pay@gos.com', 'EMP-PAY', 'pay.user', self.dept_payout)
        self.staff_hotel = self._create_staff('emp_hotel', 'ver@gos.com', 'EMP-VER', 'ver.user', self.dept_hotel)

    def _create_staff(self, username, email, emp_id, login_id, department, perms=None):
        user = User.objects.create_user(
            username=username,
            email=email,
            password='StaffPassword123!',
            first_name=username.capitalize(),
            last_name='Employee',
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
        if perms:
            profile.permissions.set(perms)
        return profile

    # =========================================================================
    # 1. RESERVATION STAFF FUNCTIONAL ACCESS
    # =========================================================================

    def test_reservation_staff_dashboard(self):
        self.client.force_authenticate(user=self.staff_res.user)
        res = self.client.get('/api/staff/reservation/dashboard/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['success'])
        self.assertEqual(res.data['department'], 'RESERVATION')
        self.assertIn('total_bookings', res.data['metrics'])

    def test_reservation_staff_list_and_detail(self):
        self.client.force_authenticate(user=self.staff_res.user)
        # List bookings
        res_list = self.client.get('/api/staff/bookings/')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertTrue(res_list.data['success'])

        # Detail booking
        res_detail = self.client.get(f'/api/staff/bookings/{self.booking.booking_id}/')
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(res_detail.data['booking_id'], self.booking.booking_id)

    def test_reservation_staff_checkin_checkout_operations(self):
        self.client.force_authenticate(user=self.staff_res.user)

        # Check-in
        res_in = self.client.post(f'/api/staff/bookings/{self.booking.booking_id}/check-in/')
        self.assertEqual(res_in.status_code, status.HTTP_200_OK)
        self.assertEqual(res_in.data['status'], Booking.STATUS_CHECKED_IN)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.booking_status, Booking.STATUS_CHECKED_IN)

        # Check-out
        res_out = self.client.post(f'/api/staff/bookings/{self.booking.booking_id}/check-out/')
        self.assertEqual(res_out.status_code, status.HTTP_200_OK)
        self.assertEqual(res_out.data['status'], Booking.STATUS_CHECKED_OUT)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.booking_status, Booking.STATUS_CHECKED_OUT)

    def test_reservation_staff_rooms_and_guests(self):
        self.client.force_authenticate(user=self.staff_res.user)

        # Rooms
        res_rooms = self.client.get('/api/staff/rooms/')
        self.assertEqual(res_rooms.status_code, status.HTTP_200_OK)
        self.assertTrue(res_rooms.data['success'])

        # Guests
        res_guests = self.client.get('/api/staff/guests/')
        self.assertEqual(res_guests.status_code, status.HTTP_200_OK)
        self.assertTrue(res_guests.data['success'])

    # =========================================================================
    # 2. CUSTOMER SUPPORT STAFF FUNCTIONAL ACCESS
    # =========================================================================

    def test_customer_support_staff_dashboard(self):
        self.client.force_authenticate(user=self.staff_cs.user)
        res = self.client.get('/api/staff/support/dashboard/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['success'])
        self.assertEqual(res.data['department'], 'CUSTOMER_SUPPORT')
        self.assertIn('open_tickets', res.data['metrics'])

    def test_customer_support_staff_operations(self):
        self.client.force_authenticate(user=self.staff_cs.user)

        # List tickets
        res_list = self.client.get('/api/staff/support/')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertTrue(res_list.data['success'])

        # Ticket detail
        res_detail = self.client.get(f'/api/staff/support/{self.ticket.id}/')
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)

        # Add internal staff note
        res_note = self.client.post(f'/api/staff/support/{self.ticket.id}/notes/', {'note': 'Guest requested late check-in'})
        self.assertEqual(res_note.status_code, status.HTTP_201_CREATED)
        self.assertTrue(res_note.data['success'])

        # Send reply message to customer
        res_msg = self.client.post(f'/api/staff/support/{self.ticket.id}/messages/', {'message': 'Yes, late check-in is available.'})
        self.assertEqual(res_msg.status_code, status.HTTP_201_CREATED)

        # Update status
        res_upd = self.client.patch(f'/api/staff/support/{self.ticket.id}/update/', {'status': 'IN_PROGRESS', 'priority': 'HIGH'})
        self.assertEqual(res_upd.status_code, status.HTTP_200_OK)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'IN_PROGRESS')

    # =========================================================================
    # 3. REFUNDS & CLAIMS STAFF FUNCTIONAL ACCESS
    # =========================================================================

    def test_refunds_staff_dashboard(self):
        self.client.force_authenticate(user=self.staff_refund.user)
        res = self.client.get('/api/staff/refunds/dashboard/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['success'])
        self.assertEqual(res.data['department'], 'REFUNDS_AND_CLAIMS')
        self.assertIn('pending_refunds', res.data['metrics'])

    def test_refunds_staff_operations(self):
        self.client.force_authenticate(user=self.staff_refund.user)

        # List refunds
        res_list = self.client.get('/api/staff/refunds/')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertTrue(res_list.data['success'])

        # Detail refund
        res_detail = self.client.get(f'/api/staff/refunds/{self.refund.id}/')
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)

        # Check eligibility
        res_elig = self.client.get(f'/api/staff/refunds/{self.refund.id}/eligibility/')
        self.assertEqual(res_elig.status_code, status.HTTP_200_OK)
        self.assertTrue(res_elig.data['is_eligible'])

        # Process refund (mocking gateway call)
        with patch('staff.views.execute_refund_with_provider') as mock_exec:
            def side_effect(refund_record, booking_locked, **kwargs):
                refund_record.status = Refund.STATUS_REFUNDED
                refund_record.razorpay_refund_id = 'rfnd_fn_123'
                refund_record.save()
                return refund_record
            mock_exec.side_effect = side_effect

            res_proc = self.client.post(f'/api/staff/refunds/{self.refund.id}/process/', {'notes': 'Approved by refunds staff'})
            self.assertEqual(res_proc.status_code, status.HTTP_200_OK)
            self.refund.refresh_from_db()
            self.assertEqual(self.refund.status, Refund.STATUS_REFUNDED)

        # Refund history
        res_hist = self.client.get('/api/staff/refunds/history/')
        self.assertEqual(res_hist.status_code, status.HTTP_200_OK)

    # =========================================================================
    # 4. PAYOUT & ESCROW STAFF FUNCTIONAL ACCESS
    # =========================================================================

    def test_payout_staff_dashboard(self):
        self.client.force_authenticate(user=self.staff_payout.user)
        res = self.client.get('/api/staff/payouts/dashboard/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['success'])
        self.assertEqual(res.data['department'], 'PAYOUT_AND_ESCROW')
        self.assertIn('pending_payouts', res.data['metrics'])

    def test_payout_staff_operations(self):
        self.client.force_authenticate(user=self.staff_payout.user)

        # List payouts
        res_list = self.client.get('/api/staff/payouts/')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertTrue(res_list.data['success'])

        # Escrow holding list (7-day rule inspection)
        res_escrow = self.client.get('/api/staff/payouts/escrow/')
        self.assertEqual(res_escrow.status_code, status.HTTP_200_OK)
        self.assertTrue(res_escrow.data['success'])

        # Settlements list
        res_settle = self.client.get('/api/staff/payouts/settlements/')
        self.assertEqual(res_settle.status_code, status.HTTP_200_OK)

        # Process payout (mature holding)
        res_proc = self.client.post(f'/api/staff/payouts/{self.payout.id}/process/')
        self.assertEqual(res_proc.status_code, status.HTTP_200_OK)
        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, HostPayout.STATUS_COMPLETED)

        # Payout history
        res_hist = self.client.get('/api/staff/payouts/history/')
        self.assertEqual(res_hist.status_code, status.HTTP_200_OK)

    # =========================================================================
    # 5. HOTEL VERIFICATION STAFF FUNCTIONAL ACCESS
    # =========================================================================

    def test_verification_staff_dashboard(self):
        self.client.force_authenticate(user=self.staff_hotel.user)
        res = self.client.get('/api/staff/verification/dashboard/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['success'])
        self.assertEqual(res.data['department'], 'HOTEL_VERIFICATION')
        self.assertIn('pending_verifications', res.data['metrics'])

    def test_verification_staff_operations(self):
        self.client.force_authenticate(user=self.staff_hotel.user)

        # List pending verifications
        res_list = self.client.get('/api/staff/verifications/')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertTrue(res_list.data['success'])

        # Detail verification
        res_detail = self.client.get(f'/api/staff/verifications/{self.pending_hotel.id}/')
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)

        # Documents list
        res_docs = self.client.get('/api/staff/verifications/documents/')
        self.assertEqual(res_docs.status_code, status.HTTP_200_OK)

        # Approve hotel
        res_app = self.client.post(f'/api/staff/verifications/{self.pending_hotel.id}/approve/')
        self.assertEqual(res_app.status_code, status.HTTP_200_OK)
        self.pending_hotel.refresh_from_db()
        self.assertEqual(self.pending_hotel.status, Hotel.STATUS_APPROVED)
        self.assertTrue(self.pending_hotel.is_approved)

        # Reject hotel with mandatory reason
        res_rej = self.client.post(f'/api/staff/verifications/{self.pending_hotel.id}/reject/', {'reason': 'Trade license expired'})
        self.assertEqual(res_rej.status_code, status.HTTP_200_OK)
        self.pending_hotel.refresh_from_db()
        self.assertEqual(self.pending_hotel.status, Hotel.STATUS_REJECTED)
        self.assertFalse(self.pending_hotel.is_approved)

        # Verification history
        res_hist = self.client.get('/api/staff/verifications/history/')
        self.assertEqual(res_hist.status_code, status.HTTP_200_OK)

    def test_hotel_verification_staff_can_view_and_approve_via_hotel_endpoints(self):
        """
        Verify that:
        1. Customer cannot see unapproved hotels in GET /api/hotels/
        2. Hotel Verification staff CAN see submitted/unapproved hotels in GET /api/hotels/
        3. Reservation staff is denied 403 when attempting POST /api/hotels/<id>/approval/
        4. Hotel Verification staff CAN approve hotel via POST /api/hotels/<id>/approval/
        5. Admin CAN reject/approve hotel via POST /api/hotels/<id>/approval/
        """
        # 1. Customer cannot see unapproved hotel
        self.client.force_authenticate(user=self.customer)
        res_cust = self.client.get('/api/hotels/')
        self.assertEqual(res_cust.status_code, status.HTTP_200_OK)
        results_cust = res_cust.data.get('results', res_cust.data) if isinstance(res_cust.data, dict) else res_cust.data
        hotel_ids_cust = [h['id'] for h in results_cust]
        self.assertNotIn(self.pending_hotel.id, hotel_ids_cust)

        # 2. Hotel Verification staff CAN see unapproved hotel in GET /api/hotels/
        self.client.force_authenticate(user=self.staff_hotel.user)
        res_staff = self.client.get('/api/hotels/')
        self.assertEqual(res_staff.status_code, status.HTTP_200_OK)
        results_staff = res_staff.data.get('results', res_staff.data) if isinstance(res_staff.data, dict) else res_staff.data
        hotel_ids_staff = [h['id'] for h in results_staff]
        self.assertIn(self.pending_hotel.id, hotel_ids_staff)

        # 3. Reservation staff cannot approve hotel via POST /api/hotels/<id>/approval/
        self.client.force_authenticate(user=self.staff_res.user)
        res_denied = self.client.post(f'/api/hotels/{self.pending_hotel.id}/approval/', {'action': 'approve'})
        self.assertEqual(res_denied.status_code, status.HTTP_403_FORBIDDEN)

        # 4. Hotel Verification staff CAN approve hotel via POST /api/hotels/<id>/approval/
        self.client.force_authenticate(user=self.staff_hotel.user)
        res_approve = self.client.post(f'/api/hotels/{self.pending_hotel.id}/approval/', {'action': 'approve'})
        self.assertEqual(res_approve.status_code, status.HTTP_200_OK)
        self.pending_hotel.refresh_from_db()
        self.assertEqual(self.pending_hotel.status, Hotel.STATUS_APPROVED)
        self.assertTrue(self.pending_hotel.is_approved)

        # 5. Admin can also approve/reject via POST /api/hotels/<id>/approval/
        self.client.force_authenticate(user=self.admin)
        res_admin_reject = self.client.post(f'/api/hotels/{self.pending_hotel.id}/approval/', {'action': 'reject', 'reason': 'Audit review'})
        self.assertEqual(res_admin_reject.status_code, status.HTTP_200_OK)
        self.pending_hotel.refresh_from_db()
        self.assertEqual(self.pending_hotel.status, Hotel.STATUS_REJECTED)
        self.assertFalse(self.pending_hotel.is_approved)

    # =========================================================================
    # 6. CROSS-DEPARTMENT ACCESS DENIAL (STRICT ISOLATION)
    # =========================================================================

    def test_cross_department_isolation_enforced(self):
        # Reservation staff tries to access Refunds
        self.client.force_authenticate(user=self.staff_res.user)
        res_ref = self.client.get('/api/staff/refunds/')
        self.assertEqual(res_ref.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('DEPARTMENT_FORBIDDEN', str(res_ref.data))

        # Support staff tries to access Payouts
        self.client.force_authenticate(user=self.staff_cs.user)
        res_pay = self.client.get('/api/staff/payouts/')
        self.assertEqual(res_pay.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('DEPARTMENT_FORBIDDEN', str(res_pay.data))

        # Refunds staff tries to access Hotel Verification
        self.client.force_authenticate(user=self.staff_refund.user)
        res_ver = self.client.get('/api/staff/verifications/')
        self.assertEqual(res_ver.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('DEPARTMENT_FORBIDDEN', str(res_ver.data))

        # Payout staff tries to access Customer Support
        self.client.force_authenticate(user=self.staff_payout.user)
        res_cs = self.client.get('/api/staff/support/')
        self.assertEqual(res_cs.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('DEPARTMENT_FORBIDDEN', str(res_cs.data))

        # Hotel Verification staff tries to access Bookings
        self.client.force_authenticate(user=self.staff_hotel.user)
        res_bk = self.client.get('/api/staff/bookings/')
        self.assertEqual(res_bk.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('DEPARTMENT_FORBIDDEN', str(res_bk.data))

    # =========================================================================
    # 7. ADMIN ENDPOINT DENIAL
    # =========================================================================

    def test_staff_denied_admin_endpoints(self):
        self.client.force_authenticate(user=self.staff_res.user)

        # Admin staff creation
        res_create = self.client.post('/api/staff/create/', {'email': 'test@x.com'})
        self.assertEqual(res_create.status_code, status.HTTP_403_FORBIDDEN)

        # Admin dashboard
        res_admin_dash = self.client.get('/api/admin/dashboard/')
        self.assertEqual(res_admin_dash.status_code, status.HTTP_403_FORBIDDEN)

        # Admin deleted hotels
        res_del = self.client.get('/api/admin/deleted-hotels/')
        self.assertEqual(res_del.status_code, status.HTTP_403_FORBIDDEN)

    # =========================================================================
    # 8. ACCOUNT INACTIVE & SUSPENSION BLOCKING
    # =========================================================================

    def test_inactive_and_suspended_staff_immediately_blocked(self):
        self.staff_res.status = StaffProfile.STATUS_INACTIVE
        self.staff_res.save(update_fields=['status'])

        self.client.force_authenticate(user=self.staff_res.user)
        res = self.client.get('/api/staff/bookings/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.data.get('code'), 'ACCOUNT_INACTIVE')

        self.staff_res.status = StaffProfile.STATUS_SUSPENDED
        self.staff_res.save(update_fields=['status'])
        res_sus = self.client.get('/api/staff/bookings/')
        self.assertEqual(res_sus.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res_sus.data.get('code'), 'ACCOUNT_INACTIVE')

    # =========================================================================
    # 9. MUST CHANGE PASSWORD GUARD
    # =========================================================================

    def test_must_change_password_blocks_operational_access(self):
        self.staff_res.status = StaffProfile.STATUS_ACTIVE
        self.staff_res.must_change_password = True
        self.staff_res.save(update_fields=['status', 'must_change_password'])

        self.client.force_authenticate(user=self.staff_res.user)
        # Blocked on operational endpoint
        res = self.client.get('/api/staff/bookings/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.data.get('code'), 'PASSWORD_CHANGE_REQUIRED')

        # Allowed on password change endpoint
        res_change = self.client.post('/api/staff/change-password/', {
            'old_password': 'StaffPassword123!',
            'new_password': 'BrandNewPassword123!@#',
            'confirm_password': 'BrandNewPassword123!@#'
        })
        self.assertEqual(res_change.status_code, status.HTTP_200_OK)
        self.staff_res.refresh_from_db()
        self.assertFalse(self.staff_res.must_change_password)

        # Now operational endpoint succeeds
        res_ok = self.client.get('/api/staff/bookings/')
        self.assertEqual(res_ok.status_code, status.HTTP_200_OK)

    # =========================================================================
    # 10. CENTRALIZED PORTAL NAVIGATION CONTRACT
    # =========================================================================

    def test_portal_navigation_contract(self):
        # 1. Reservation Staff
        self.client.force_authenticate(user=self.staff_res.user)
        res_res = self.client.get('/api/portal/navigation/')
        self.assertEqual(res_res.status_code, status.HTTP_200_OK)
        self.assertEqual(res_res.data['portal']['portal_id'], 'RESERVATION_PORTAL')
        self.assertEqual(res_res.data['portal']['department'], 'RESERVATION')
        self.assertEqual(res_res.data['dashboard_url'], '/staff/reservation')

        # 2. Support Staff
        self.client.force_authenticate(user=self.staff_cs.user)
        res_cs = self.client.get('/api/portal/navigation/')
        self.assertEqual(res_cs.status_code, status.HTTP_200_OK)
        self.assertEqual(res_cs.data['portal']['portal_id'], 'CUSTOMER_SUPPORT_PORTAL')
        self.assertEqual(res_cs.data['portal']['department'], 'CUSTOMER_SUPPORT')
        self.assertEqual(res_cs.data['dashboard_url'], '/staff/support')

        # 3. Refunds Staff
        self.client.force_authenticate(user=self.staff_refund.user)
        res_ref = self.client.get('/api/portal/navigation/')
        self.assertEqual(res_ref.status_code, status.HTTP_200_OK)
        self.assertEqual(res_ref.data['portal']['portal_id'], 'REFUNDS_AND_CLAIMS_PORTAL')
        self.assertEqual(res_ref.data['portal']['department'], 'REFUNDS_AND_CLAIMS')
        self.assertEqual(res_ref.data['dashboard_url'], '/staff/refunds')

        # 4. Payout Staff
        self.client.force_authenticate(user=self.staff_payout.user)
        res_pay = self.client.get('/api/portal/navigation/')
        self.assertEqual(res_pay.status_code, status.HTTP_200_OK)
        self.assertEqual(res_pay.data['portal']['portal_id'], 'PAYOUT_AND_ESCROW_PORTAL')
        self.assertEqual(res_pay.data['portal']['department'], 'PAYOUT_AND_ESCROW')
        self.assertEqual(res_pay.data['dashboard_url'], '/staff/payouts')

        # 5. Hotel Verification Staff
        self.client.force_authenticate(user=self.staff_hotel.user)
        res_ver = self.client.get('/api/portal/navigation/')
        self.assertEqual(res_ver.status_code, status.HTTP_200_OK)
        self.assertEqual(res_ver.data['portal']['portal_id'], 'HOTEL_VERIFICATION_PORTAL')
        self.assertEqual(res_ver.data['portal']['department'], 'HOTEL_VERIFICATION')
        self.assertEqual(res_ver.data['dashboard_url'], '/staff/verification')

        # 6. Admin User
        self.client.force_authenticate(user=self.admin)
        res_adm = self.client.get('/api/portal/navigation/')
        self.assertEqual(res_adm.status_code, status.HTTP_200_OK)
        self.assertEqual(res_adm.data['portal']['portal_id'], 'ADMIN_PORTAL')
        self.assertEqual(res_adm.data['dashboard_url'], '/admin/dashboard')
