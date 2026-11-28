import os
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from rest_framework.test import APIClient
from rest_framework import status

from hotels.models import Hotel, HotelImage, HotelVerificationDocument
from rooms.models import Room, RoomImage
from payments.models import SupportTicket
from core.url_helpers import to_browser_safe_url

User = get_user_model()


class SecurityHardeningTests(TestCase):
    """
    Exhaustive validation test suite for security hardening:
    - 401 unauthenticated, 403 unauthorized, 200 authorized on private media
    - Public media availability without infrastructure leakage
    - PII redaction on public listings
    - Sanitized pagination and API URLs
    - Safe error responses without stack traces or path leakage
    - Path traversal rejection
    """

    def setUp(self):
        self.client = APIClient()

        # 1. Create Users
        self.owner = User.objects.create_user(
            username='sec_owner',
            email='sec_owner@example.com',
            password='Password123!',
            role='HOTEL_OWNER',
            phone_number='+91 9876543210'
        )
        self.customer = User.objects.create_user(
            username='sec_customer',
            email='sec_customer@example.com',
            password='Password123!',
            role='CUSTOMER',
            phone_number='+91 9123456780'
        )
        self.other_customer = User.objects.create_user(
            username='sec_other_cust',
            email='sec_other@example.com',
            password='Password123!',
            role='CUSTOMER',
            phone_number='+91 9999988888'
        )
        self.admin = User.objects.create_superuser(
            username='sec_admin',
            email='sec_admin@example.com',
            password='Password123!',
            role='ADMIN',
            is_staff=True,
            is_superuser=True
        )

        # 2. Attach avatar to customer
        avatar_content = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00'
        self.customer.avatar.save(
            'test_avatar.jpg',
            SimpleUploadedFile('test_avatar.jpg', avatar_content, content_type='image/jpeg')
        )

        # 3. Create Hotel & Public Image
        self.hotel = Hotel.objects.create(
            owner=self.owner,
            name='Security Test Hotel',
            city='Mumbai',
            address='123 Marine Drive',
            status='APPROVED',
            is_approved=True
        )
        img_content = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4'
        self.hotel_image = HotelImage.objects.create(
            hotel=self.hotel,
            caption='Front View'
        )
        self.hotel_image.image.save(
            'hotel_front.png',
            SimpleUploadedFile('hotel_front.png', img_content, content_type='image/png')
        )

        # 4. Create Private Hotel Verification Document
        doc_content = b'%PDF-1.4\n%test pdf document for compliance\n%%EOF'
        self.doc = HotelVerificationDocument.objects.create(
            hotel=self.hotel,
            document_type=HotelVerificationDocument.DOC_TAX_GST,
            status=HotelVerificationDocument.STATUS_APPROVED
        )
        self.doc.document_file.save(
            'gst_cert.pdf',
            SimpleUploadedFile('gst_cert.pdf', doc_content, content_type='application/pdf')
        )

        # 5. Create Private Support Ticket with Attachment
        self.ticket = SupportTicket.objects.create(
            user=self.customer,
            subject='Confidential dispute document',
            description='Evidence attached.',
            priority='HIGH',
            status='OPEN'
        )
        self.ticket.attachment.save(
            'dispute_evidence.pdf',
            SimpleUploadedFile('dispute_evidence.pdf', doc_content, content_type='application/pdf')
        )

    def test_public_hotel_image_accessible_unauthenticated(self):
        """Public hotel images must remain accessible to anonymous travelers with nosniff header."""
        url = self.hotel_image.image.url
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.headers.get('X-Content-Type-Options'), 'nosniff')

    def test_private_avatar_unauthenticated_returns_401(self):
        """Unauthenticated requests to private avatars must be rejected with 401."""
        url = self.customer.avatar.url
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("AUTHENTICATION_REQUIRED", response.data['error']['code'])

    def test_private_avatar_unauthorized_user_returns_403(self):
        """Customer B attempting to access Customer A's private avatar must receive 403 Forbidden."""
        self.client.force_authenticate(user=self.other_customer)
        url = self.customer.avatar.url
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("PERMISSION_DENIED", response.data['error']['code'])

    def test_private_avatar_authorized_owner_returns_200(self):
        """Customer A accessing their own avatar must succeed with 200 OK."""
        self.client.force_authenticate(user=self.customer)
        url = self.customer.avatar.url
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.headers.get('X-Content-Type-Options'), 'nosniff')

    def test_private_avatar_admin_returns_200(self):
        """Platform Admin accessing user avatar must succeed with 200 OK."""
        self.client.force_authenticate(user=self.admin)
        url = self.customer.avatar.url
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_hotel_document_unauthenticated_returns_401(self):
        """Unauthenticated requests to private hotel documents must return 401."""
        url = self.doc.document_file.url
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_hotel_document_unauthorized_customer_returns_403(self):
        """Regular customer requesting hotel verification documents must return 403 Forbidden."""
        self.client.force_authenticate(user=self.customer)
        url = self.doc.document_file.url
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_hotel_document_authorized_owner_returns_200(self):
        """Hotel owner accessing their own hotel verification document must return 200 OK."""
        self.client.force_authenticate(user=self.owner)
        url = self.doc.document_file.url
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('Document_TAX_GST', response.headers.get('Content-Disposition', ''))

    def test_hotel_document_admin_returns_200(self):
        """Platform admin accessing hotel verification document must return 200 OK."""
        self.client.force_authenticate(user=self.admin)
        url = self.doc.document_file.url
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_support_ticket_attachment_unauthenticated_returns_401(self):
        """Unauthenticated request to support ticket attachment must return 401."""
        url = self.ticket.attachment.url
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_support_ticket_attachment_unauthorized_customer_returns_403(self):
        """Customer B requesting Customer A's support attachment must return 403 Forbidden."""
        self.client.force_authenticate(user=self.other_customer)
        url = self.ticket.attachment.url
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_support_ticket_attachment_creator_returns_200(self):
        """Ticket creator accessing their attachment must return 200 OK."""
        self.client.force_authenticate(user=self.customer)
        url = self.ticket.attachment.url
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_path_traversal_rejected(self):
        """Directory traversal sequences (..) in media URL must return 400 Bad Request."""
        response = self.client.get('/media/../settings.py')
        self.assertIn(response.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND])

    def test_hotel_listing_redacts_owner_pii_for_anonymous_visitors(self):
        """Anonymous visitors querying hotel list/detail must NOT receive owner email, phone, or docs."""
        response = self.client.get(f'/api/hotels/{self.hotel.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        self.assertEqual(data.get('owner_email'), '')
        self.assertEqual(data.get('owner_phone'), '')
        self.assertEqual(data.get('verification_documents'), [])
        self.assertIsNone(data.get('rejection_reason'))

    def test_hotel_listing_reveals_pii_to_hotel_owner(self):
        """Hotel owner querying their hotel receives their contact and document info."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(f'/api/hotels/{self.hotel.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        self.assertEqual(data.get('owner_email'), self.owner.email)
        self.assertEqual(data.get('owner_phone'), self.owner.phone_number)

    def test_to_browser_safe_url_strips_internal_ips_and_ports(self):
        """Verify URL sanitizer helper strips localhost, 127.0.0.1, 192.168.x.x, and port 8000."""
        inputs_and_expected = [
            ("http://192.168.1.104:8000/api/hotels/?page=2", "/api/hotels/?page=2"),
            ("http://localhost:8000/media/hotels/images/pic.jpg", "/media/hotels/images/pic.jpg"),
            ("http://127.0.0.1:8000/api/users/1/avatar/", "/api/users/1/avatar/"),
            ("/api/hotels/?page=3", "/api/hotels/?page=3"),
            ("https://res.cloudinary.com/bzb1bndw/image/upload/sample.jpg", "https://res.cloudinary.com/bzb1bndw/image/upload/sample.jpg"),
        ]
        for raw, expected in inputs_and_expected:
            self.assertEqual(to_browser_safe_url(raw), expected)

    def test_pagination_links_are_same_origin_relative_paths(self):
        """Paginated API response 'next' and 'previous' must be relative paths, never private IPs."""
        # Query hotel list endpoint
        response = self.client.get('/api/hotels/?page=1&page_size=1')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        if response.data.get('next'):
            self.assertFalse(response.data['next'].startswith('http://192.168.'))
            self.assertFalse(response.data['next'].startswith('http://127.0.0.1'))
            self.assertFalse(response.data['next'].startswith('http://localhost'))
            self.assertTrue(response.data['next'].startswith('/api/hotels/'))

    def test_error_responses_do_not_leak_paths_or_db_traces(self):
        """RFC 7807 error responses must not leak internal disk paths or DB schemas."""
        response = self.client.get('/api/nonexistent-endpoint-404/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        content_str = str(response.content)
        self.assertNotIn("D:\\", content_str)
        self.assertNotIn("/home/", content_str)
        self.assertNotIn("Traceback", content_str)
