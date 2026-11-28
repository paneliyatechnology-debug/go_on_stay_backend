"""
Comprehensive Automated Test Suite for GoOnStay Smart Notification Click-Through Navigation.

Verifies:
1. Destination mapping across all 8 platform roles/departments:
   - Customer
   - Hotel Owner
   - Admin
   - Staff (Reservation, Customer Support, Refunds & Claims, Payout & Escrow, Hotel Verification)
2. Exact record identifier resolution and linking
3. Strict department and cross-role isolation (Zero Admin or cross-department leakage for Staff)
4. Non-existent and deleted record fallback handling
5. Mark-as-read and click-through API behavior
6. Backward compatibility with existing notification formats
"""

from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from notifications.models import Notification
from notifications.navigation import resolve_notification_navigation, extract_entity_details
from staff.models import Department, StaffProfile, StaffNotification, StaffPermission
from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking
from payments.models import SupportTicket, Payment, Refund, HostEarning

User = get_user_model()


class SmartNotificationClickthroughTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # 1. Platform Admin
        self.admin_user = User.objects.create_superuser(
            username='admin_boss',
            email='admin@goonstay.com',
            password='AdminPassword123!',
            role='ADMIN'
        )

        # 2. Hotel Owner
        self.owner_user = User.objects.create_user(
            username='host_partner',
            email='host@goonstay.com',
            password='HostPassword123!',
            role='HOTEL_OWNER'
        )

        # 3. Customer
        self.customer_user = User.objects.create_user(
            username='guest_traveler',
            email='guest@goonstay.com',
            password='GuestPassword123!',
            role='CUSTOMER'
        )

        # 4. Department Setup
        self.dept_reservation, _ = Department.objects.get_or_create(
            code=Department.CODE_RESERVATION,
            defaults={'name': 'Reservation'}
        )
        self.dept_support, _ = Department.objects.get_or_create(
            code=Department.CODE_CUSTOMER_SUPPORT,
            defaults={'name': 'Customer Support'}
        )
        self.dept_refunds, _ = Department.objects.get_or_create(
            code=Department.CODE_REFUNDS_AND_CLAIMS,
            defaults={'name': 'Refunds & Claims'}
        )
        self.dept_payouts, _ = Department.objects.get_or_create(
            code=Department.CODE_PAYOUT_AND_ESCROW,
            defaults={'name': 'Payout & Escrow'}
        )
        self.dept_verification, _ = Department.objects.get_or_create(
            code=Department.CODE_HOTEL_VERIFICATION,
            defaults={'name': 'Hotel Verification'}
        )

        # 5. Staff Users for each department
        self.staff_res_user = User.objects.create_user(username='res_staff', email='res@goonstay.com', password='Password123!', role='STAFF', is_staff=True)
        self.staff_res_profile = StaffProfile.objects.create(user=self.staff_res_user, employee_id='EMP-RES-01', login_id='res_staff', department=self.dept_reservation, must_change_password=False)

        self.staff_cs_user = User.objects.create_user(username='cs_staff', email='cs@goonstay.com', password='Password123!', role='STAFF', is_staff=True)
        self.staff_cs_profile = StaffProfile.objects.create(user=self.staff_cs_user, employee_id='EMP-CS-01', login_id='cs_staff', department=self.dept_support, must_change_password=False)

        self.staff_ref_user = User.objects.create_user(username='ref_staff', email='ref@goonstay.com', password='Password123!', role='STAFF', is_staff=True)
        self.staff_ref_profile = StaffProfile.objects.create(user=self.staff_ref_user, employee_id='EMP-REF-01', login_id='ref_staff', department=self.dept_refunds, must_change_password=False)

        self.staff_pay_user = User.objects.create_user(username='pay_staff', email='pay@goonstay.com', password='Password123!', role='STAFF', is_staff=True)
        self.staff_pay_profile = StaffProfile.objects.create(user=self.staff_pay_user, employee_id='EMP-PAY-01', login_id='pay_staff', department=self.dept_payouts, must_change_password=False)

        self.staff_ver_user = User.objects.create_user(username='ver_staff', email='ver@goonstay.com', password='Password123!', role='STAFF', is_staff=True)
        self.staff_ver_profile = StaffProfile.objects.create(user=self.staff_ver_user, employee_id='EMP-VER-01', login_id='ver_staff', department=self.dept_verification, must_change_password=False)

        # 6. Sample Hotel & Room
        self.hotel = Hotel.objects.create(
            owner=self.owner_user,
            name='Ocean View Resort',
            city='Goa',
            state='Goa',
            status=Hotel.STATUS_APPROVED,
            is_approved=True
        )
        self.room = Room.objects.create(
            hotel=self.hotel,
            title='Deluxe Sea Suite',
            room_type='DELUXE',
            price_per_night=Decimal('4500.00'),
            capacity_adults=2
        )

        # 7. Sample Booking
        self.booking = Booking.objects.create(
            booking_id='BMR20261121001',
            customer=self.customer_user,
            hotel=self.hotel,
            room=self.room,
            check_in='2026-12-01',
            check_out='2026-12-05',
            number_of_nights=4,
            number_of_guests=2,
            number_of_rooms=1,
            price_per_night=Decimal('4500.00'),
            subtotal=Decimal('18000.00'),
            total_amount=Decimal('18000.00'),
            guest_name='Guest Traveler',
            guest_email='guest@goonstay.com',
            guest_phone='9876543210',
            booking_status=Booking.STATUS_CONFIRMED,
            payment_status=Booking.PAYMENT_PAID
        )

        # 8. Sample Payment
        self.payment = Payment.objects.create(
            booking=self.booking,
            user=self.customer_user,
            razorpay_order_id='order_notif_001',
            razorpay_payment_id='pay_notif_001',
            amount=Decimal('18000.00'),
            status=Payment.STATUS_CAPTURED
        )

    # =========================================================================
    # 1. CUSTOMER ROLE DESTINATIONS
    # =========================================================================

    def test_customer_booking_notification_destination(self):
        """Customer confirmed booking notification points to customer booking detail."""
        notif = Notification.objects.create(
            recipient=self.customer_user,
            booking=self.booking,
            title='Booking Confirmed',
            message=f'Your booking {self.booking.booking_id} is confirmed.',
            notification_type=Notification.TYPE_BOOKING_CONFIRMED
        )
        dest = resolve_notification_navigation(notification=notif, user=self.customer_user)
        self.assertEqual(dest['target_url'], f"/customer/bookings/{self.booking.booking_id}")
        self.assertEqual(dest['target_entity_type'], 'booking')
        self.assertEqual(dest['target_entity_id'], self.booking.booking_id)
        self.assertTrue(dest['record_exists'])

    def test_customer_support_ticket_destination(self):
        """Customer support notification routes to support ticket."""
        ticket = SupportTicket.objects.create(
            ticket_number='TCK-1001',
            user=self.customer_user,
            subject='Need late check-in',
            description='Please confirm late check-in'
        )
        notif = Notification.objects.create(
            recipient=self.customer_user,
            title='Support Ticket Updated',
            message=f'Agent replied to ticket #{ticket.ticket_number}',
            notification_type='SUPPORT_MESSAGE'
        )
        dest = resolve_notification_navigation(notification=notif, user=self.customer_user)
        self.assertEqual(dest['target_url'], f"/customer/support?ticket_id={ticket.ticket_number}")
        self.assertEqual(dest['target_entity_type'], 'ticket')

    def test_customer_general_and_offer_destinations(self):
        """Offer notifications navigate to /hotels; general notifications to /customer/dashboard."""
        offer_notif = Notification.objects.create(
            recipient=self.customer_user,
            title='Weekend Flash Sale!',
            message='Get 20% off on beachfront resorts this weekend.',
            notification_type='COUPON_OFFER'
        )
        dest_offer = resolve_notification_navigation(notification=offer_notif, user=self.customer_user)
        self.assertEqual(dest_offer['target_url'], '/hotels')

        gen_notif = Notification.objects.create(
            recipient=self.customer_user,
            title='Welcome to GoOnStay',
            message='Thank you for creating an account with GoOnStay!',
            notification_type=Notification.TYPE_GENERAL
        )
        dest_gen = resolve_notification_navigation(notification=gen_notif, user=self.customer_user)
        self.assertEqual(dest_gen['target_url'], '/customer/dashboard')

    # =========================================================================
    # 2. HOTEL OWNER DESTINATIONS
    # =========================================================================

    def test_hotel_owner_booking_notification_destination(self):
        """Hotel Owner booking alert routes to /host/bookings/<id>."""
        notif = Notification.objects.create(
            recipient=self.owner_user,
            booking=self.booking,
            title='New Booking Alert',
            message=f'New booking received {self.booking.booking_id}',
            notification_type=Notification.TYPE_NEW_BOOKING_OWNER
        )
        dest = resolve_notification_navigation(notification=notif, user=self.owner_user)
        self.assertEqual(dest['target_url'], f"/host/bookings/{self.booking.booking_id}")
        self.assertEqual(dest['target_entity_type'], 'booking')
        self.assertEqual(dest['fallback_url'], '/host/bookings')

    def test_hotel_owner_payout_due_destination(self):
        """Hotel Owner payout due notification routes to host settlements."""
        notif = Notification.objects.create(
            recipient=self.owner_user,
            booking=self.booking,
            title='Payout Ready',
            message=f'Escrow matured for booking {self.booking.booking_id}',
            notification_type=Notification.TYPE_PAYOUT_DUE
        )
        dest = resolve_notification_navigation(notification=notif, user=self.owner_user)
        self.assertTrue('/host/settlements' in dest['target_url'])
        self.assertEqual(dest['target_entity_type'], 'payout')

    def test_hotel_owner_verification_status_destination(self):
        """Hotel Owner verification notification routes to /host/hotels/<id>."""
        notif = Notification.objects.create(
            recipient=self.owner_user,
            title='Hotel Approved',
            message=f'Property {self.hotel.name} (hotel #{self.hotel.id}) has been approved!',
            notification_type=Notification.TYPE_HOTEL_APPROVED
        )
        dest = resolve_notification_navigation(notification=notif, user=self.owner_user)
        self.assertEqual(dest['target_url'], f"/host/hotels/{self.hotel.id}")
        self.assertEqual(dest['target_entity_type'], 'hotel')

    # =========================================================================
    # 3. ADMIN DESTINATIONS
    # =========================================================================

    def test_admin_oversight_destinations(self):
        """Admin routes to administrative platform oversight pages with search/highlight params."""
        notif_booking = Notification.objects.create(
            recipient=self.admin_user,
            booking=self.booking,
            title='Booking Alert',
            message=f'Booking {self.booking.booking_id}',
            notification_type=Notification.TYPE_GENERAL
        )
        dest_booking = resolve_notification_navigation(notification=notif_booking, user=self.admin_user)
        self.assertEqual(dest_booking['target_url'], f"/admin/bookings?booking_id={self.booking.booking_id}")

        notif_hotel = Notification.objects.create(
            recipient=self.admin_user,
            title='Hotel Submission',
            message=f'New hotel #{self.hotel.id} submitted for review',
            notification_type='HOTEL_SUBMITTED'
        )
        dest_hotel = resolve_notification_navigation(notification=notif_hotel, user=self.admin_user)
        self.assertEqual(dest_hotel['target_url'], f"/admin/verifications?hotel_id={self.hotel.id}")

    # =========================================================================
    # 4. STAFF DEPARTMENT ISOLATION DESTINATIONS
    # =========================================================================

    def test_reservation_staff_isolated_destination(self):
        """Reservation staff routes to /staff/reservation/bookings/<id>."""
        notif = StaffNotification.objects.create(
            recipient=self.staff_res_profile,
            department=self.dept_reservation,
            title='Guest Check-In Due',
            message=f'Guest check-in for booking {self.booking.booking_id}',
            notification_type='BOOKING_CONFIRMED',
            metadata={'booking_id': self.booking.booking_id}
        )
        dest = resolve_notification_navigation(notification=notif, user=self.staff_res_user)
        self.assertEqual(dest['target_url'], f"/staff/reservation/bookings/{self.booking.booking_id}")
        self.assertEqual(dest['fallback_url'], '/staff/reservation/bookings')

    def test_customer_support_staff_isolated_destination(self):
        """Customer Support staff routes to /staff/support/tickets/<id>."""
        ticket = SupportTicket.objects.create(
            ticket_number='TCK-2002',
            user=self.customer_user,
            subject='Room AC Issue',
            description='AC not cooling'
        )
        notif = StaffNotification.objects.create(
            recipient=self.staff_cs_profile,
            department=self.dept_support,
            title='Urgent Ticket',
            message=f'Ticket {ticket.ticket_number} requires attention',
            notification_type='SUPPORT_TICKET_CREATED',
            metadata={'ticket_id': ticket.ticket_number}
        )
        dest = resolve_notification_navigation(notification=notif, user=self.staff_cs_user)
        self.assertEqual(dest['target_url'], f"/staff/support/tickets/{ticket.ticket_number}")
        self.assertEqual(dest['fallback_url'], '/staff/support/tickets')

    def test_refunds_claims_staff_isolated_destination(self):
        """Refunds & Claims staff routes to /staff/refunds/<id>."""
        refund = Refund.objects.create(
            booking=self.booking,
            payment=self.payment,
            razorpay_payment_id='pay_notif_001',
            amount=Decimal('4500.00'),
            reason='Cancellation refund',
            status=Refund.STATUS_REFUND_PENDING
        )
        notif = StaffNotification.objects.create(
            recipient=self.staff_ref_profile,
            department=self.dept_refunds,
            title='Refund Requested',
            message=f'Refund #{refund.id} pending review',
            notification_type='REFUND_REQUESTED',
            metadata={'refund_id': refund.id}
        )
        dest = resolve_notification_navigation(notification=notif, user=self.staff_ref_user)
        self.assertEqual(dest['target_url'], f"/staff/refunds/{refund.id}")
        self.assertEqual(dest['fallback_url'], '/staff/refunds/requests')

    def test_payout_escrow_staff_isolated_destination(self):
        """Payout & Escrow staff routes to /staff/payouts/<id>."""
        earning = HostEarning.objects.create(
            booking=self.booking,
            host=self.owner_user,
            gross_amount=Decimal('18000.00'),
            platform_fee=Decimal('1800.00'),
            net_amount=Decimal('16200.00'),
            status=HostEarning.STATUS_ELIGIBLE
        )
        notif = StaffNotification.objects.create(
            recipient=self.staff_pay_profile,
            department=self.dept_payouts,
            title='Payout Due Alert',
            message=f'Payout #{earning.id} ready for execution',
            notification_type='PAYOUT_DUE',
            metadata={'payout_id': earning.id}
        )
        dest = resolve_notification_navigation(notification=notif, user=self.staff_pay_user)
        self.assertEqual(dest['target_url'], f"/staff/payouts/{earning.id}")
        self.assertEqual(dest['fallback_url'], '/staff/payouts/requests')

    def test_hotel_verification_staff_isolated_destination(self):
        """Hotel Verification staff routes to /staff/verification/<id>."""
        notif = StaffNotification.objects.create(
            recipient=self.staff_ver_profile,
            department=self.dept_verification,
            title='Hotel Application Pending',
            message=f'Verification required for hotel #{self.hotel.id}',
            notification_type='HOTEL_SUBMITTED',
            metadata={'hotel_id': self.hotel.id}
        )
        dest = resolve_notification_navigation(notification=notif, user=self.staff_ver_user)
        self.assertEqual(dest['target_url'], f"/staff/verification/{self.hotel.id}")
        self.assertEqual(dest['fallback_url'], '/staff/verification/pending')

    # =========================================================================
    # 5. ZERO CROSS-ROLE / CROSS-DEPARTMENT LEAKAGE
    # =========================================================================

    def test_staff_cannot_leak_to_admin_or_foreign_departments(self):
        """Staff receiving a notification never gets an Admin URL or other department URL."""
        # Support staff receives notification mentioning a booking
        notif = StaffNotification.objects.create(
            recipient=self.staff_cs_profile,
            department=self.dept_support,
            title='Guest Inquired About Booking',
            message=f'Booking {self.booking.booking_id}',
            notification_type=Notification.TYPE_GENERAL
        )
        dest = resolve_notification_navigation(notification=notif, user=self.staff_cs_user)
        # Must stay strictly inside Customer Support workspace!
        self.assertTrue(dest['target_url'].startswith('/staff/support'))
        self.assertFalse(dest['target_url'].startswith('/admin'))
        self.assertFalse(dest['target_url'].startswith('/staff/reservation'))

    # =========================================================================
    # 6. NON-EXISTENT AND DELETED RECORD FALLBACK HANDLING
    # =========================================================================

    def test_deleted_record_fallback(self):
        """Non-existent or deleted record sets record_exists=False and points to safe fallback."""
        notif = Notification.objects.create(
            recipient=self.customer_user,
            title='Old Booking Update',
            message='Booking BMR99999999 was archived',
            notification_type=Notification.TYPE_BOOKING_CANCELLED
        )
        dest = resolve_notification_navigation(notification=notif, user=self.customer_user)
        self.assertFalse(dest['record_exists'])
        self.assertEqual(dest['target_url'], '/customer/bookings')
        self.assertEqual(dest['fallback_url'], '/customer/bookings')

    # =========================================================================
    # 7. MARK AS READ & CLICK API ENDPOINTS
    # =========================================================================

    def test_customer_notification_list_serializes_smart_navigation(self):
        """GET /api/notifications/ includes target_url and navigation_metadata."""
        notif = Notification.objects.create(
            recipient=self.customer_user,
            booking=self.booking,
            title='Stay Confirmed',
            message=f'Booking {self.booking.booking_id}',
            notification_type=Notification.TYPE_BOOKING_CONFIRMED
        )
        self.client.force_authenticate(user=self.customer_user)
        res = self.client.get('/api/notifications/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data['results'] if isinstance(res.data, dict) and 'results' in res.data else res.data
        self.assertTrue(len(results) > 0)
        item = [n for n in results if n['id'] == notif.id][0]
        self.assertEqual(item['target_url'], f"/customer/bookings/{self.booking.booking_id}")
        self.assertEqual(item['target_entity_type'], 'booking')
        self.assertEqual(item['target_entity_id'], self.booking.booking_id)

    def test_customer_notification_mark_read_and_click(self):
        """POST /api/notifications/<id>/click/ marks read and returns destination."""
        notif = Notification.objects.create(
            recipient=self.customer_user,
            booking=self.booking,
            title='Reminder',
            message='Tomorrow is check-in',
            notification_type=Notification.TYPE_STAY_REMINDER,
            is_read=False
        )
        self.client.force_authenticate(user=self.customer_user)

        res = self.client.post(f'/api/notifications/{notif.id}/click/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['is_read'])
        self.assertEqual(res.data['target_url'], f"/customer/bookings/{self.booking.booking_id}")

        notif.refresh_from_db()
        self.assertTrue(notif.is_read)

    def test_staff_notification_click_department_enforced(self):
        """POST /api/staff/notifications/<id>/click/ marks read and stays in staff department."""
        notif = StaffNotification.objects.create(
            recipient=self.staff_res_profile,
            department=self.dept_reservation,
            title='New Booking',
            message=f'Booking {self.booking.booking_id}',
            notification_type='BOOKING_CONFIRMED',
            metadata={'booking_id': self.booking.booking_id},
            is_read=False
        )
        self.client.force_authenticate(user=self.staff_res_user)
        res = self.client.post(f'/api/staff/notifications/{notif.id}/click/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['is_read'])
        self.assertEqual(res.data['target_url'], f"/staff/reservation/bookings/{self.booking.booking_id}")

        notif.refresh_from_db()
        self.assertTrue(notif.is_read)
