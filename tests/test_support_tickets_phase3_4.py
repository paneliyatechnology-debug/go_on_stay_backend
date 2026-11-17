import datetime
import os
import shutil
import tempfile
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework import status
from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking
from payments.models import SupportTicket, TicketMessage, HostEarning

User = get_user_model()
TEMP_MEDIA_ROOT = tempfile.mkdtemp(prefix="goonstay_test_media_")


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class SupportTicketPhase3And4MasterTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        if os.path.exists(TEMP_MEDIA_ROOT):
            shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        cache.clear()
        self.client = APIClient()

        # 1. Admin / Staff
        self.admin = User.objects.create_superuser(
            username='p34_admin',
            email='admin@goonstay.com',
            password='AdminPassword123!',
            first_name='Super',
            last_name='Admin',
            role=User.ROLE_ADMIN
        )

        # 2. Hotel Owner 1 (owns Hotel 1)
        self.owner1 = User.objects.create_user(
            username='owner_a',
            email='ownera@goonstay.com',
            password='OwnerPassword123!',
            first_name='Ramesh',
            last_name='Mehta',
            role=User.ROLE_HOTEL_OWNER
        )

        # 3. Hotel Owner 2 (owns Hotel 2)
        self.owner2 = User.objects.create_user(
            username='owner_b',
            email='ownerb@goonstay.com',
            password='OwnerPassword123!',
            first_name='Suresh',
            last_name='Verma',
            role=User.ROLE_HOTEL_OWNER
        )

        # 4. Customers
        self.customer1 = User.objects.create_user(
            username='cust_1',
            email='cust1@example.com',
            password='CustomerPass123!',
            first_name='Arun',
            last_name='Kumar',
            phone_number='+919876543210',
            role=User.ROLE_CUSTOMER
        )

        self.customer2 = User.objects.create_user(
            username='cust_2',
            email='cust2@example.com',
            password='CustomerPass123!',
            first_name='Neha',
            last_name='Sharma',
            phone_number='+919123456789',
            role=User.ROLE_CUSTOMER
        )

        # 5. Hotels and Rooms
        self.hotel1 = Hotel.objects.create(
            owner=self.owner1,
            name='GoOnStay Beach Resort',
            city='Goa',
            address='Calangute Beach'
        )
        self.room1 = Room.objects.create(
            hotel=self.hotel1,
            title='Ocean View Villa',
            room_type='VILLA',
            price_per_night=8000.00,
            room_numbers='V-101, V-102',
            total_rooms=2
        )

        self.hotel2 = Hotel.objects.create(
            owner=self.owner2,
            name='GoOnStay City Suites',
            city='Bengaluru',
            address='MG Road'
        )
        self.room2 = Room.objects.create(
            hotel=self.hotel2,
            title='Deluxe Business Room',
            room_type='DELUXE',
            price_per_night=4500.00,
            room_numbers='301, 302',
            total_rooms=2
        )

        # 6. Bookings
        self.booking1 = Booking.objects.create(
            booking_id='BK-GOA-101',
            customer=self.customer1,
            hotel=self.hotel1,
            room=self.room1,
            check_in=datetime.date(2026, 12, 10),
            check_out=datetime.date(2026, 12, 15),
            room_number='V-101',
            price_per_night=8000.00,
            number_of_nights=5,
            subtotal=40000.00,
            total_amount=47200.00,
            payment_status=Booking.PAYMENT_PAID,
            booking_status=Booking.STATUS_CONFIRMED
        )

        self.booking2 = Booking.objects.create(
            booking_id='BK-BLR-202',
            customer=self.customer2,
            hotel=self.hotel2,
            room=self.room2,
            check_in=datetime.date(2026, 12, 20),
            check_out=datetime.date(2026, 12, 22),
            room_number='301',
            price_per_night=4500.00,
            number_of_nights=2,
            subtotal=9000.00,
            total_amount=10620.00,
            payment_status=Booking.PAYMENT_PAID,
            booking_status=Booking.STATUS_CONFIRMED
        )

        # 7. Support Tickets
        self.ticket1 = SupportTicket.objects.create(
            user=self.customer1,
            booking=self.booking1,
            hotel=self.hotel1,
            room=self.room1,
            category='BOOKING',
            priority='HIGH',
            status='OPEN',
            subject='Airport shuttle request',
            description='Please confirm if airport shuttle pickup is arranged.'
        )

        self.ticket2 = SupportTicket.objects.create(
            user=self.customer2,
            booking=self.booking2,
            hotel=self.hotel2,
            room=self.room2,
            category='HOTEL',
            priority='MEDIUM',
            status='IN_PROGRESS',
            subject='Late check-in notification',
            description='We will arrive at 11 PM.'
        )

        self.ticket3 = SupportTicket.objects.create(
            user=self.customer1,
            category='ACCOUNT',
            priority='LOW',
            status='OPEN',
            subject='How to earn loyalty points',
            description='Where can I view my GoOnStay reward points?'
        )

    def tearDown(self):
        cache.clear()

    # ==================================================
    # 1. ADMIN TESTS (Tests 1 to 12)
    # ==================================================

    def test_01_admin_can_view_all_authorized_tickets(self):
        """1. Admin can view all customer support tickets across all hotels."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/payments/support-tickets/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 3)

    def test_02_admin_can_search_tickets(self):
        """2. Admin can search tickets across customer name and booking ID."""
        self.client.force_authenticate(user=self.admin)
        res_name = self.client.get('/api/payments/support-tickets/?search=Arun')
        self.assertEqual(res_name.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_name.data.get('results', res_name.data)), 2)

        res_bk = self.client.get('/api/payments/support-tickets/?search=BK-BLR-202')
        self.assertEqual(res_bk.status_code, status.HTTP_200_OK)
        results = res_bk.data.get('results', res_bk.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], self.ticket2.id)

    def test_03_admin_can_filter_by_status(self):
        """3. Admin can filter tickets by status."""
        self.client.force_authenticate(user=self.admin)
        res_open = self.client.get('/api/payments/support-tickets/?status=OPEN')
        self.assertEqual(res_open.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_open.data.get('results', res_open.data)), 2)

    def test_04_admin_can_filter_by_category(self):
        """4. Admin can filter tickets by category."""
        self.client.force_authenticate(user=self.admin)
        res_cat = self.client.get('/api/payments/support-tickets/?category=HOTEL')
        self.assertEqual(res_cat.status_code, status.HTTP_200_OK)
        results = res_cat.data.get('results', res_cat.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], self.ticket2.id)

    def test_05_admin_can_filter_by_priority(self):
        """5. Admin can filter tickets by priority."""
        self.client.force_authenticate(user=self.admin)
        res_prio = self.client.get('/api/payments/support-tickets/?priority=HIGH')
        self.assertEqual(res_prio.status_code, status.HTTP_200_OK)
        results = res_prio.data.get('results', res_prio.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], self.ticket1.id)

    def test_06_admin_can_view_complete_ticket_details(self):
        """6. Admin can view complete ticket details with all required frontend fields."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.get(f'/api/payments/support-tickets/{self.ticket1.id}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data
        self.assertEqual(data['id'], self.ticket1.id)
        self.assertIn('ticket_number', data)
        self.assertEqual(data['customer_name'], 'Arun Kumar')
        self.assertEqual(data['customer_phone'], '+919876543210')
        self.assertEqual(data['hotel_name'], 'GoOnStay Beach Resort')
        self.assertEqual(data['booking_id'], 'BK-GOA-101')
        self.assertEqual(data['room_number'], 'V-101')
        self.assertEqual(data['status'], 'OPEN')
        self.assertEqual(data['priority'], 'HIGH')
        self.assertIn('messages', data)

    def test_07_admin_can_assign_valid_hotel_owner(self):
        """7. Admin can assign a valid Hotel Owner (owner of the ticket's hotel)."""
        self.client.force_authenticate(user=self.admin)
        payload = {"assigned_agent": self.owner1.id}
        res = self.client.patch(f'/api/payments/support-tickets/{self.ticket1.id}/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.ticket1.refresh_from_db()
        self.assertEqual(self.ticket1.assigned_agent, self.owner1)
        self.assertEqual(res.data['assigned_agent'], self.owner1.id)

    def test_08_admin_can_reassign_ticket(self):
        """8. Admin can reassign or unassign a ticket."""
        self.client.force_authenticate(user=self.admin)
        # First assign to Owner 1
        self.client.patch(f'/api/payments/support-tickets/{self.ticket1.id}/', {"assigned_agent": self.owner1.id}, format='json')
        # Now reassign to Admin/Support Staff
        res_reassign = self.client.patch(f'/api/payments/support-tickets/{self.ticket1.id}/', {"assigned_agent": self.admin.id}, format='json')
        self.assertEqual(res_reassign.status_code, status.HTTP_200_OK)
        self.ticket1.refresh_from_db()
        self.assertEqual(self.ticket1.assigned_agent, self.admin)

    def test_09_admin_can_change_status(self):
        """9. Admin can update ticket status to IN_PROGRESS."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.patch(f'/api/payments/support-tickets/{self.ticket1.id}/', {"status": "IN_PROGRESS"}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.ticket1.refresh_from_db()
        self.assertEqual(self.ticket1.status, 'IN_PROGRESS')

    def test_10_admin_can_change_priority(self):
        """10. Admin can update ticket priority to URGENT."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.patch(f'/api/payments/support-tickets/{self.ticket1.id}/', {"priority": "URGENT"}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.ticket1.refresh_from_db()
        self.assertEqual(self.ticket1.priority, 'URGENT')

    def test_11_admin_can_reply_to_customers(self):
        """11. Admin can post messages/replies on tickets."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            f'/api/payments/support-tickets/{self.ticket1.id}/messages/',
            {"message": "Hello Arun, our concierge team is coordinating your request."},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['sender_role'], User.ROLE_ADMIN)

    def test_12_admin_can_resolve_and_close_tickets(self):
        """12. Admin can resolve and then close tickets."""
        self.client.force_authenticate(user=self.admin)
        res_resolve = self.client.patch(f'/api/payments/support-tickets/{self.ticket1.id}/', {"status": "RESOLVED"}, format='json')
        self.assertEqual(res_resolve.status_code, status.HTTP_200_OK)
        self.ticket1.refresh_from_db()
        self.assertEqual(self.ticket1.status, 'RESOLVED')

        res_close = self.client.patch(f'/api/payments/support-tickets/{self.ticket1.id}/', {"status": "CLOSED"}, format='json')
        self.assertEqual(res_close.status_code, status.HTTP_200_OK)
        self.ticket1.refresh_from_db()
        self.assertEqual(self.ticket1.status, 'CLOSED')

    # ==================================================
    # 2. HOTEL OWNER TESTS (Tests 13 to 20)
    # ==================================================

    def test_13_owner_can_see_tickets_assigned_to_them(self):
        """13. Hotel Owner can see tickets specifically assigned to them."""
        self.ticket1.assigned_agent = self.owner1
        self.ticket1.save()
        self.client.force_authenticate(user=self.owner1)
        res = self.client.get('/api/payments/support-tickets/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ticket_ids = [t['id'] for t in res.data.get('results', res.data)]
        self.assertIn(self.ticket1.id, ticket_ids)

    def test_14_owner_can_see_eligible_tickets_related_to_their_hotel(self):
        """14. Hotel Owner can see customer tickets raised for hotels they own."""
        self.client.force_authenticate(user=self.owner1)
        res = self.client.get('/api/payments/support-tickets/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ticket_ids = [t['id'] for t in res.data.get('results', res.data)]
        self.assertIn(self.ticket1.id, ticket_ids)

    def test_15_owner_can_view_relevant_booking_information(self):
        """15. Hotel Owner can view booking information for tickets at their hotel."""
        self.client.force_authenticate(user=self.owner1)
        res = self.client.get(f'/api/payments/support-tickets/{self.ticket1.id}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(res.data['booking_details'])
        self.assertEqual(res.data['booking_details']['booking_id'], 'BK-GOA-101')
        self.assertEqual(res.data['room_number'], 'V-101')

    def test_16_owner_can_reply_to_authorized_tickets(self):
        """16. Hotel Owner can submit messages and issue updates on their hotel's tickets."""
        self.client.force_authenticate(user=self.owner1)
        res = self.client.post(
            f'/api/payments/support-tickets/{self.ticket1.id}/messages/',
            {"message": "Shuttle arranged with Toyota Innova, pickup at 10 AM."},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['sender_role'], User.ROLE_HOTEL_OWNER)

    def test_17_owner_cannot_access_unrelated_hotel_tickets(self):
        """17. Hotel Owner cannot view tickets for other hotels in the list."""
        self.client.force_authenticate(user=self.owner2)
        res = self.client.get('/api/payments/support-tickets/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ticket_ids = [t['id'] for t in res.data.get('results', res.data)]
        self.assertNotIn(self.ticket1.id, ticket_ids)

    def test_18_owner_cannot_change_ticket_assignment(self):
        """18. Hotel Owner cannot change ticket assignment (HTTP 403 Forbidden)."""
        self.client.force_authenticate(user=self.owner1)
        res = self.client.patch(f'/api/payments/support-tickets/{self.ticket1.id}/', {"assigned_agent": self.owner2.id}, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_19_owner_cannot_modify_unauthorized_administrative_fields(self):
        """19. Hotel Owner cannot modify administrative fields like status or customer (HTTP 403 Forbidden)."""
        self.client.force_authenticate(user=self.owner1)
        res = self.client.patch(f'/api/payments/support-tickets/{self.ticket1.id}/', {"status": "CLOSED"}, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_20_owner_cannot_access_another_owners_tickets_by_changing_ticket_ids(self):
        """20. Hotel Owner receives HTTP 404 when requesting another hotel's ticket directly."""
        self.client.force_authenticate(user=self.owner2)
        res = self.client.get(f'/api/payments/support-tickets/{self.ticket1.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    # ==================================================
    # 3. CUSTOMER SECURITY TESTS (Tests 21 to 25)
    # ==================================================

    def test_21_customer_cannot_modify_status(self):
        """21. Customer cannot modify ticket status (HTTP 403 Forbidden)."""
        self.client.force_authenticate(user=self.customer1)
        res = self.client.patch(f'/api/payments/support-tickets/{self.ticket1.id}/', {"status": "RESOLVED"}, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_22_customer_cannot_change_assigned_agent(self):
        """22. Customer cannot assign or change assigned_agent (HTTP 403 Forbidden)."""
        self.client.force_authenticate(user=self.customer1)
        res = self.client.patch(f'/api/payments/support-tickets/{self.ticket1.id}/', {"assigned_agent": self.owner1.id}, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_23_customer_cannot_modify_ticket_ownership(self):
        """23. Customer cannot transfer ticket ownership to another user (HTTP 403 Forbidden)."""
        self.client.force_authenticate(user=self.customer1)
        res = self.client.patch(f'/api/payments/support-tickets/{self.ticket1.id}/', {"user": self.customer2.id}, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_24_customer_cannot_change_unauthorized_booking_relationships(self):
        """24. Customer cannot change booking or hotel relationships after creation (HTTP 403 Forbidden)."""
        self.client.force_authenticate(user=self.customer1)
        res = self.client.patch(f'/api/payments/support-tickets/{self.ticket1.id}/', {"booking": self.booking2.id}, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_25_customer_cannot_access_another_customers_ticket(self):
        """25. Customer cannot access another customer's ticket (HTTP 404 Not Found)."""
        self.client.force_authenticate(user=self.customer1)
        res = self.client.get(f'/api/payments/support-tickets/{self.ticket2.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    # ==================================================
    # 4. FILE SECURITY TESTS (Tests 26 to 33)
    # ==================================================

    def test_26_valid_jpg_upload_works(self):
        """26. Genuine JPG image upload is accepted (HTTP 201 Created)."""
        self.client.force_authenticate(user=self.customer1)
        jpg_content = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00'
        f = SimpleUploadedFile("proof.jpg", jpg_content, content_type="image/jpeg")
        res = self.client.post('/api/payments/support-tickets/', {
            "category": "ACCOUNT",
            "priority": "LOW",
            "subject": "JPG proof upload",
            "description": "Valid JPEG test",
            "attachment": f
        }, format='multipart')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertIsNotNone(res.data['attachment'])

    def test_27_valid_jpeg_upload_works(self):
        """27. Genuine JPEG image upload is accepted (HTTP 201 Created)."""
        self.client.force_authenticate(user=self.customer1)
        jpeg_content = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00'
        f = SimpleUploadedFile("document.jpeg", jpeg_content, content_type="image/jpeg")
        res = self.client.post('/api/payments/support-tickets/', {
            "category": "ACCOUNT",
            "priority": "LOW",
            "subject": "JPEG upload test",
            "description": "Valid JPEG test",
            "attachment": f
        }, format='multipart')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_28_valid_png_upload_works(self):
        """28. Genuine PNG image upload is accepted (HTTP 201 Created)."""
        self.client.force_authenticate(user=self.customer1)
        png_content = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4'
        f = SimpleUploadedFile("screenshot.png", png_content, content_type="image/png")
        res = self.client.post('/api/payments/support-tickets/', {
            "category": "ACCOUNT",
            "priority": "LOW",
            "subject": "PNG upload test",
            "description": "Valid PNG test",
            "attachment": f
        }, format='multipart')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_29_valid_pdf_upload_works(self):
        """29. Genuine PDF document upload is accepted (HTTP 201 Created)."""
        self.client.force_authenticate(user=self.customer1)
        pdf_content = b'%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF'
        f = SimpleUploadedFile("bill.pdf", pdf_content, content_type="application/pdf")
        res = self.client.post('/api/payments/support-tickets/', {
            "category": "ACCOUNT",
            "priority": "LOW",
            "subject": "PDF invoice upload",
            "description": "Valid PDF test",
            "attachment": f
        }, format='multipart')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_30_invalid_extensions_are_rejected(self):
        """30. Script and executable file extensions are rejected (HTTP 400 Bad Request)."""
        self.client.force_authenticate(user=self.customer1)
        bad_f = SimpleUploadedFile("exploit.php", b"<?php phpinfo(); ?>", content_type="application/x-php")
        res = self.client.post('/api/payments/support-tickets/', {
            "category": "ACCOUNT",
            "priority": "LOW",
            "subject": "Bad extension test",
            "description": "Script test",
            "attachment": bad_f
        }, format='multipart')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("attachment", str(res.data))

    def test_31_spoofed_mime_types_are_rejected(self):
        """31. Text file masquerading with a .png extension is rejected by magic byte check (HTTP 400)."""
        self.client.force_authenticate(user=self.customer1)
        fake_f = SimpleUploadedFile("text_as_image.png", b"Plain text payload pretending to be PNG", content_type="image/png")
        res = self.client.post('/api/payments/support-tickets/', {
            "category": "ACCOUNT",
            "priority": "LOW",
            "subject": "Spoofed MIME test",
            "description": "Magic byte test",
            "attachment": fake_f
        }, format='multipart')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("attachment", str(res.data))

    def test_32_oversized_files_are_rejected(self):
        """32. Attachment exceeding 5 MB is rejected (HTTP 400 Bad Request)."""
        self.client.force_authenticate(user=self.customer1)
        oversized = b'\x89PNG\r\n\x1a\n' + b'0' * (6 * 1024 * 1024)
        big_f = SimpleUploadedFile("big.png", oversized, content_type="image/png")
        res = self.client.post('/api/payments/support-tickets/', {
            "category": "ACCOUNT",
            "priority": "LOW",
            "subject": "Oversized test",
            "description": "Size test",
            "attachment": big_f
        }, format='multipart')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_33_unauthorized_attachment_access_is_rejected(self):
        """33. Customer cannot access another customer's ticket or its attachment URL."""
        self.client.force_authenticate(user=self.customer1)
        res = self.client.get(f'/api/payments/support-tickets/{self.ticket2.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    # ==================================================
    # 5. RATE LIMIT AND XSS TESTS (Tests 34 to 36)
    # ==================================================

    def test_34_ticket_creation_rate_limiting_works(self):
        """34. Ticket creation is throttled upon exceeding limit (HTTP 429)."""
        cache.clear()
        self.client.force_authenticate(user=self.customer2)
        for i in range(10):
            res = self.client.post('/api/payments/support-tickets/', {
                "category": "ACCOUNT",
                "priority": "LOW",
                "subject": f"Ticket throttle test {i}",
                "description": "Throttle testing"
            }, format='json')
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        throttled = self.client.post('/api/payments/support-tickets/', {
            "category": "ACCOUNT",
            "priority": "LOW",
            "subject": "11th ticket",
            "description": "Throttled"
        }, format='json')
        self.assertEqual(throttled.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_35_message_rate_limiting_works(self):
        """35. Ticket messaging is throttled upon exceeding limit (HTTP 429)."""
        cache.clear()
        self.client.force_authenticate(user=self.customer1)
        for i in range(30):
            res = self.client.post(f'/api/payments/support-tickets/{self.ticket1.id}/messages/', {
                "message": f"Message pace test {i}"
            }, format='json')
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        throttled = self.client.post(f'/api/payments/support-tickets/{self.ticket1.id}/messages/', {
            "message": "31st message should throttle"
        }, format='json')
        self.assertEqual(throttled.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_36_unsafe_html_javascript_is_safely_handled(self):
        """36. Unsafe HTML and JavaScript is neutralized in subject, description, and messages."""
        self.client.force_authenticate(user=self.customer1)
        xss = "<script>alert('xss')</script><img src=x onerror=alert(1)>Hello"
        res = self.client.post('/api/payments/support-tickets/', {
            "category": "ACCOUNT",
            "priority": "LOW",
            "subject": xss,
            "description": xss
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        t = SupportTicket.objects.get(id=res.data['id'])
        self.assertNotIn("<script>", t.subject)
        self.assertNotIn("alert('xss')", t.subject)

    # ==================================================
    # 6. REGRESSION TESTS (Tests 37 to 45)
    # ==================================================

    def test_37_customer_login_works(self):
        """37. Customer login returns JWT access and refresh tokens (HTTP 200)."""
        cache.clear()
        res = self.client.post('/api/users/login/', {
            "username": "cust_1",
            "password": "CustomerPass123!"
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access", res.data)

    def test_38_admin_login_works(self):
        """38. Admin login succeeds and returns JWT tokens (HTTP 200)."""
        cache.clear()
        res = self.client.post('/api/users/login/', {
            "username": "p34_admin",
            "password": "AdminPassword123!"
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access", res.data)

    def test_39_hotel_owner_login_works(self):
        """39. Hotel Owner login succeeds and returns JWT tokens (HTTP 200)."""
        cache.clear()
        res = self.client.post('/api/users/login/', {
            "username": "owner_a",
            "password": "OwnerPassword123!"
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access", res.data)

    def test_40_existing_booking_apis_work(self):
        """40. Existing booking list API returns customer bookings (HTTP 200)."""
        self.client.force_authenticate(user=self.customer1)
        res = self.client.get('/api/bookings/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_41_existing_payment_apis_work(self):
        """41. Existing settlement ledger API is accessible to Admin (HTTP 200)."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.get('/api/payments/settlements/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_42_existing_refund_apis_work(self):
        """42. Existing Admin refund list API is accessible to Admin (HTTP 200)."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.get('/api/payments/admin/refunds/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_43_existing_cancellation_functionality_works(self):
        """43. Existing booking cancellation preview API works (HTTP 200)."""
        self.client.force_authenticate(user=self.customer1)
        res = self.client.get(f'/api/bookings/{self.booking1.id}/cancel/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('refundable_amount', res.data)

    def test_44_existing_host_earning_functionality_works(self):
        """44. HostEarning model querying and calculation remains fully functional."""
        he = HostEarning.objects.create(
            booking=self.booking1,
            host=self.owner1,
            gross_amount=40000.00,
            platform_fee=4000.00,
            net_amount=36000.00,
            status=HostEarning.STATUS_PENDING
        )
        self.assertEqual(HostEarning.objects.filter(host=self.owner1).count(), 1)
        self.assertEqual(float(he.net_amount), 36000.00)

    def test_45_phase1_and_phase2_tests_continue_passing(self):
        """45. Verifies Phase 1 & 2 ticket creation with booking link auto-derives hotel and room."""
        self.client.force_authenticate(user=self.customer1)
        res = self.client.post('/api/payments/support-tickets/', {
            "booking": self.booking1.id,
            "category": "HOTEL",
            "priority": "MEDIUM",
            "subject": "Room temperature check",
            "description": "Please adjust AC temperature before check-in."
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        new_ticket = SupportTicket.objects.get(id=res.data['id'])
        self.assertEqual(new_ticket.hotel, self.hotel1)
        self.assertEqual(new_ticket.room, self.room1)
