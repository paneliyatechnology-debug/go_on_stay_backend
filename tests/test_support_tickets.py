import datetime
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking
from payments.models import SupportTicket, TicketMessage

User = get_user_model()


class SupportTicketPhase1And2Tests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Create Customer 1
        self.customer1 = User.objects.create_user(
            username='customer1',
            email='customer1@example.com',
            password='TestPassword123!',
            first_name='Rahul',
            last_name='Patel',
            role=User.ROLE_CUSTOMER
        )

        # Create Customer 2
        self.customer2 = User.objects.create_user(
            username='customer2',
            email='customer2@example.com',
            password='TestPassword123!',
            first_name='Amit',
            last_name='Shah',
            role=User.ROLE_CUSTOMER
        )

        # Create Hotel Owner 1
        self.owner1 = User.objects.create_user(
            username='owner1',
            email='owner1@example.com',
            password='TestPassword123!',
            first_name='Hotel',
            last_name='Owner',
            role=User.ROLE_HOTEL_OWNER
        )

        # Create Hotel 1 & Room 1
        self.hotel1 = Hotel.objects.create(
            owner=self.owner1,
            name='GoOnStay Grand Palace',
            city='Mumbai',
            address='Marine Drive'
        )
        self.room1 = Room.objects.create(
            hotel=self.hotel1,
            title='Deluxe Sea View Room',
            room_type='DELUXE',
            price_per_night=3500.00,
            room_numbers='101, 102, 103',
            total_rooms=3
        )

        # Create Hotel 2 & Room 2
        self.hotel2 = Hotel.objects.create(
            owner=self.owner1,
            name='GoOnStay Mountain Resort',
            city='Manali',
            address='Mall Road'
        )
        self.room2 = Room.objects.create(
            hotel=self.hotel2,
            title='Executive Alpine Suite',
            room_type='EXECUTIVE',
            price_per_night=5500.00,
            room_numbers='201, 202',
            total_rooms=2
        )

        # Create Confirmed Booking for Customer 1
        self.booking1 = Booking.objects.create(
            booking_id='BK-202611-001',
            customer=self.customer1,
            hotel=self.hotel1,
            room=self.room1,
            check_in=datetime.date(2026, 12, 1),
            check_out=datetime.date(2026, 12, 5),
            room_number='101',
            price_per_night=3500.00,
            number_of_nights=4,
            subtotal=14000.00,
            total_amount=16520.00,
            payment_status=Booking.PAYMENT_PAID,
            booking_status=Booking.STATUS_CONFIRMED
        )

        # Create Booking for Customer 2
        self.booking2 = Booking.objects.create(
            booking_id='BK-202611-002',
            customer=self.customer2,
            hotel=self.hotel2,
            room=self.room2,
            check_in=datetime.date(2026, 12, 10),
            check_out=datetime.date(2026, 12, 12),
            room_number='201',
            price_per_night=5500.00,
            number_of_nights=2,
            subtotal=11000.00,
            total_amount=12980.00,
            payment_status=Booking.PAYMENT_PAID,
            booking_status=Booking.STATUS_CONFIRMED
        )

    # 1. General Query creation
    def test_01_general_query_creation(self):
        """Customer creates an ACCOUNT / General Query ticket without selecting a booking."""
        self.client.force_authenticate(user=self.customer1)
        payload = {
            "category": "ACCOUNT",
            "priority": "LOW",
            "subject": "Need assistance updating registered phone number",
            "description": "I would like to update my registered phone number to my new primary mobile."
        }
        response = self.client.post('/api/payments/support-tickets/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        data = response.data
        self.assertTrue(data['ticket_number'].startswith('TICK-'))
        self.assertEqual(data['status'], 'OPEN')
        self.assertEqual(data['category'], 'ACCOUNT')
        self.assertEqual(data['priority'], 'LOW')
        self.assertIsNone(data['booking'])
        self.assertIsNone(data['room'])
        self.assertIsNone(data['assigned_agent'])
        self.assertEqual(data['user'], self.customer1.id)
        self.assertEqual(data['customer']['email'], self.customer1.email)

    # 2. Booking-related ticket creation
    def test_02_booking_related_ticket_creation(self):
        """Customer creates a ticket associated with their valid booking."""
        self.client.force_authenticate(user=self.customer1)
        payload = {
            "category": "BOOKING",
            "priority": "HIGH",
            "booking": self.booking1.id,
            "subject": "Early check-in request",
            "description": "Flight lands at 9 AM, can we check-in by 11 AM?"
        }
        response = self.client.post('/api/payments/support-tickets/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        data = response.data
        self.assertEqual(data['booking'], self.booking1.id)
        self.assertEqual(data['booking_id'], self.booking1.booking_id)
        self.assertEqual(data['hotel_id'], self.hotel1.id)
        self.assertEqual(data['hotel_name'], self.hotel1.name)
        self.assertEqual(data['room_id'], self.room1.id)
        self.assertEqual(data['room_number'], '101')
        self.assertEqual(data['status'], 'OPEN')

    # 3. Valid booking selection (by string booking_id and int PK)
    def test_03_valid_booking_selection(self):
        """Ticket creation works with string booking_id reference."""
        self.client.force_authenticate(user=self.customer1)
        payload = {
            "category": "PAYMENT",
            "priority": "MEDIUM",
            "booking_id": self.booking1.booking_id,
            "subject": "Tax invoice copy requested",
            "description": "Please provide an official GST tax invoice for this reservation."
        }
        response = self.client.post('/api/payments/support-tickets/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['booking'], self.booking1.id)
        self.assertEqual(response.data['hotel_id'], self.hotel1.id)

    # 4. Invalid booking ID rejection
    def test_04_invalid_booking_id_rejection(self):
        """Backend must reject non-existent booking IDs with HTTP 400 Bad Request."""
        self.client.force_authenticate(user=self.customer1)
        
        # Test non-existent numeric PK
        payload = {
            "category": "BOOKING",
            "priority": "HIGH",
            "booking": 999999,
            "subject": "Invalid Booking Test",
            "description": "Testing non-existent booking ID."
        }
        response = self.client.post('/api/payments/support-tickets/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Test non-existent alphanumeric booking_id
        payload_str = {
            "category": "BOOKING",
            "priority": "HIGH",
            "booking_id": "BK-NONEXISTENT-999",
            "subject": "Invalid Booking Test 2",
            "description": "Testing non-existent alphanumeric booking ID."
        }
        response_str = self.client.post('/api/payments/support-tickets/', payload_str, format='json')
        self.assertEqual(response_str.status_code, status.HTTP_400_BAD_REQUEST)

    # 5. Another customer's booking ID rejection
    def test_05_another_customer_booking_id_rejection(self):
        """Customer cannot create a ticket for another customer's booking (HTTP 403 Forbidden)."""
        self.client.force_authenticate(user=self.customer1)
        payload = {
            "category": "BOOKING",
            "priority": "HIGH",
            "booking": self.booking2.id,  # Belongs to Customer 2
            "subject": "Attempting unauthorized ticket",
            "description": "Trying to create a ticket on customer 2 booking."
        }
        response = self.client.post('/api/payments/support-tickets/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # Confirm no ticket was saved for this unauthorized attempt
        self.assertFalse(SupportTicket.objects.filter(booking=self.booking2, user=self.customer1).exists())

    # 6. Hotel and Room relationship integrity (tampering prevention)
    def test_06_hotel_and_room_relationship_integrity(self):
        """Backend ignores client-provided Hotel ID and Room ID, automatically binding authoritative booking relationships."""
        self.client.force_authenticate(user=self.customer1)
        payload = {
            "category": "REFUND",
            "priority": "URGENT",
            "booking": self.booking1.id,  # Hotel 1, Room 1
            "hotel": self.hotel2.id,      # Attempted spoofing: Hotel 2
            "room": self.room2.id,        # Attempted spoofing: Room 2
            "subject": "Refund dispute",
            "description": "Authoritative relationship test."
        }
        response = self.client.post('/api/payments/support-tickets/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        data = response.data
        # Server must override spoofed IDs with real booking relationships
        self.assertEqual(data['hotel_id'], self.hotel1.id)
        self.assertEqual(data['hotel_name'], self.hotel1.name)
        self.assertEqual(data['room_id'], self.room1.id)
        self.assertNotEqual(data['hotel_id'], self.hotel2.id)
        self.assertNotEqual(data['room_id'], self.room2.id)

    # 7. Customer ticket listing
    def test_07_customer_ticket_listing(self):
        """GET /api/payments/support-tickets/ only returns authenticated customer's tickets."""
        # Create 2 tickets for Customer 1
        t1 = SupportTicket.objects.create(
            user=self.customer1,
            booking=self.booking1,
            hotel=self.hotel1,
            room=self.room1,
            category='BOOKING',
            priority='LOW',
            subject='Customer 1 Ticket 1',
            description='First ticket'
        )
        t2 = SupportTicket.objects.create(
            user=self.customer1,
            category='ACCOUNT',
            priority='MEDIUM',
            subject='Customer 1 Ticket 2',
            description='Second ticket'
        )

        # Create 1 ticket for Customer 2
        t3 = SupportTicket.objects.create(
            user=self.customer2,
            booking=self.booking2,
            hotel=self.hotel2,
            room=self.room2,
            category='PAYMENT',
            priority='HIGH',
            subject='Customer 2 Ticket',
            description='Customer 2 issue'
        )

        self.client.force_authenticate(user=self.customer1)
        response = self.client.get('/api/payments/support-tickets/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data.get('results', response.data)
        ticket_ids = [item['id'] for item in results]

        self.assertIn(t1.id, ticket_ids)
        self.assertIn(t2.id, ticket_ids)
        self.assertNotIn(t3.id, ticket_ids)
        self.assertEqual(len(ticket_ids), 2)

    # 8. Customer ownership restrictions (IDOR & unauthorized field tampering)
    def test_08_customer_ownership_restrictions(self):
        """Customer cannot view another customer's ticket or modify unauthorized fields."""
        t2 = SupportTicket.objects.create(
            user=self.customer2,
            booking=self.booking2,
            hotel=self.hotel2,
            room=self.room2,
            category='HOTEL',
            priority='MEDIUM',
            subject='Customer 2 Private Ticket',
            description='Private info'
        )

        # Customer 1 attempts direct access to Customer 2's ticket
        self.client.force_authenticate(user=self.customer1)
        response = self.client.get(f'/api/payments/support-tickets/{t2.id}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Customer 1 cannot post message on Customer 2's ticket
        msg_resp = self.client.post(
            f'/api/payments/support-tickets/{t2.id}/messages/',
            {"message": "Unauthorized message attempt"},
            format='json'
        )
        self.assertEqual(msg_resp.status_code, status.HTTP_403_FORBIDDEN)

        # Customer cannot self-assign status='RESOLVED' or agent on create
        spoof_create = self.client.post(
            '/api/payments/support-tickets/',
            {
                "category": "ACCOUNT",
                "priority": "LOW",
                "subject": "Spoof test",
                "description": "Trying to set status and agent",
                "status": "RESOLVED",
                "assigned_agent": self.owner1.id
            },
            format='json'
        )
        self.assertEqual(spoof_create.status_code, status.HTTP_201_CREATED)
        self.assertEqual(spoof_create.data['status'], 'OPEN')
        self.assertIsNone(spoof_create.data['assigned_agent'])

    # 9. GET /api/bookings/ response verification
    def test_09_customer_booking_api_verification(self):
        """Verify GET /api/bookings/ returns booking_id, hotel_id, hotel_name, room_id, room_number, check_in, check_out."""
        self.client.force_authenticate(user=self.customer1)
        response = self.client.get('/api/bookings/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 1)

        b = results[0]
        self.assertEqual(b['booking_id'], self.booking1.booking_id)
        self.assertEqual(b['hotel_id'], self.hotel1.id)
        self.assertEqual(b['hotel_name'], self.hotel1.name)
        self.assertEqual(b['room_id'], self.room1.id)
        self.assertEqual(b['room_number'], '101')
        self.assertEqual(str(b['check_in']), str(self.booking1.check_in))
        self.assertEqual(str(b['check_out']), str(self.booking1.check_out))
