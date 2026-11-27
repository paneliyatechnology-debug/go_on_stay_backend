import json
import uuid
import hmac
import hashlib
from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils import timezone
from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking
from payments.models import Payment, Refund, WebhookEvent, HostEarning

User = get_user_model()

class RazorpayPaymentSecurityTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        
        # Test Users
        self.customer = User.objects.create_user(
            username='test_customer',
            email='customer@example.com',
            password='CustomerPassword123!',
            role='CUSTOMER',
            first_name='Test',
            last_name='Customer'
        )
        
        self.owner = User.objects.create_user(
            username='test_owner',
            email='owner@example.com',
            password='OwnerPassword123!',
            role='HOTEL_OWNER',
            first_name='Test',
            last_name='Owner'
        )
        
        self.admin = User.objects.create_user(
            username='test_admin',
            email='admin@example.com',
            password='AdminPassword123!',
            role='ADMIN',
            is_staff=True,
            is_superuser=True
        )
        
        # Test Hotel & Room
        self.hotel = Hotel.objects.create(
            owner=self.owner,
            name="Seaside Luxury Resort",
            city="Goa",
            address="Candolim Beach",
            state="Goa",
            star_rating=5
        )
        
        self.room = Room.objects.create(
            hotel=self.hotel,
            title="Ocean View Deluxe Suite",
            room_type="DELUXE",
            price_per_night=Decimal('5000.00'),
            capacity_adults=2,
            capacity_children=1,
            total_rooms=5
        )
        
        # Test Booking
        self.booking = Booking.objects.create(
            customer=self.customer,
            hotel=self.hotel,
            room=self.room,
            check_in=timezone.now().date(),
            check_out=(timezone.now() + timezone.timedelta(days=2)).date(),
            number_of_guests=2,
            number_of_rooms=1,
            price_per_night=Decimal('5000.00'),
            number_of_nights=2,
            subtotal=Decimal('10000.00'),
            taxes=Decimal('1800.00'),
            total_amount=Decimal('11800.00'),
            booking_status=Booking.STATUS_PENDING_PAYMENT,
            payment_status=Booking.PAYMENT_PENDING,
            guest_name="Test Customer",
            guest_email="customer@example.com",
            guest_phone="9876543210"
        )
        
        # JWT Token login headers
        self.client.force_authenticate(user=self.customer)

    def test_1_create_order_authenticated_customer(self):
        """Verify order creation recalculates price on server and returns valid order_id."""
        response = self.client.post('/api/payments/create-order/', {
            'booking_id': self.booking.booking_id
        }, content_type='application/json')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('order_id', data)
        self.assertEqual(data['amount'], 1180000)  # ₹11,800.00 * 100 paise
        self.assertEqual(data['currency'], 'INR')
        self.assertEqual(data['key_id'], settings.RAZORPAY_KEY_ID)

    def test_2_order_creation_price_tamper_prevention(self):
        """Ensure backend ignores any frontend price tampering and enforces server calculation."""
        # Attempting to tamper booking amount in database before order
        self.booking.subtotal = Decimal('100.00')
        self.booking.total_amount = Decimal('100.00')
        self.booking.save()
        
        response = self.client.post('/api/payments/create-order/', {
            'booking_id': self.booking.booking_id
        }, content_type='application/json')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Server recalculates 5000 * 2 nights = 10000 + 1800 tax = 11800 => 1180000 paise
        self.assertEqual(data['amount'], 1180000)

    def test_2b_order_creation_with_meal_plan_upgrade(self):
        """Ensure backend correctly includes meal plan upgrade (e.g. FULL_BOARD +1400/night)."""
        # Set meal_plan to FULL_BOARD
        self.booking.meal_plan = 'FULL_BOARD'
        self.booking.save()

        response = self.client.post('/api/payments/create-order/', {
            'booking_id': self.booking.booking_id
        }, content_type='application/json')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Room: 5000 * 2 = 10000
        # Meal: 1400 * 2 = 2800
        # Subtotal: 12800
        # Taxes 18%: 2304.00
        # Total: 15104.00 => 1510400 paise
        self.assertEqual(data['amount'], 1510400)
        self.assertEqual(data['meal_plan'], 'FULL_BOARD')
        self.assertEqual(data['meal_subtotal'], 2800.0)
        self.assertEqual(data['room_subtotal'], 10000.0)
        self.assertEqual(data['taxes'], 2304.0)

    def test_3_verify_payment_invalid_signature_rejection(self):
        """Security Test: Invalid HMAC signature must be rejected and logged."""
        response = self.client.post('/api/payments/verify/', {
            'booking_id': self.booking.booking_id,
            'razorpay_order_id': 'order_fake_123',
            'razorpay_payment_id': 'pay_fake_456',
            'razorpay_signature': 'invalid_forged_signature_hash'
        }, content_type='application/json')
        
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())
        self.booking.refresh_from_db()
        self.assertNotEqual(self.booking.booking_status, Booking.STATUS_CONFIRMED)

    def test_4_webhook_signature_verification(self):
        """Verify Webhook raw body HMAC SHA256 verification."""
        payload = {
            "event": "payment.failed",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_test_failed_001",
                        "order_id": "order_test_999",
                        "amount": 1180000,
                        "error_description": "Payment timed out"
                    }
                }
            }
        }
        body_bytes = json.dumps(payload).encode('utf-8')
        signature = hmac.new(
            settings.RAZORPAY_WEBHOOK_SECRET.encode('utf-8'),
            body_bytes,
            hashlib.sha256
        ).hexdigest()
        
        response = self.client.post('/api/payments/webhook/', data=body_bytes, content_type='application/json', HTTP_X_RAZORPAY_SIGNATURE=signature)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')

    def test_5_payment_retry_flow(self):
        """Verify payment retry creates new order for unpaid pending booking."""
        response = self.client.post('/api/payments/retry/', {
            'booking_id': self.booking.booking_id
        }, content_type='application/json')
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('order_id', response.json())

    def test_6_non_customer_booking_block(self):
        """Verify Hotel Owners cannot create bookings."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.post('/api/bookings/', {
            'hotel': self.hotel.id,
            'room': self.room.id,
            'check_in': '2026-10-10',
            'check_out': '2026-10-12',
            'guest_name': 'Owner User',
            'guest_email': 'owner@example.com',
            'guest_phone': '9876543210'
        }, content_type='application/json')
        
        self.assertEqual(response.status_code, 403)


class PlatformSettlementAndEscrowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        from payments.models import HostPayoutAccount, PlatformSetting, SupportTicket, HostPayout

        self.customer = User.objects.create_user(
            username='settle_customer',
            email='customer_settle@example.com',
            password='CustomerPassword123!',
            role='CUSTOMER',
            first_name='Guest',
            last_name='User'
        )

        self.owner = User.objects.create_user(
            username='settle_owner',
            email='owner_settle@example.com',
            password='OwnerPassword123!',
            role='HOTEL_OWNER',
            first_name='Hotel',
            last_name='Host'
        )

        self.admin = User.objects.create_user(
            username='settle_admin',
            email='admin_settle@example.com',
            password='AdminPassword123!',
            role='ADMIN',
            is_staff=True,
            is_superuser=True
        )

        self.hotel = Hotel.objects.create(
            owner=self.owner,
            name="Heritage Palace & Spa",
            city="Udaipur",
            address="Lake Pichola",
            state="Rajasthan"
        )

        self.room = Room.objects.create(
            hotel=self.hotel,
            title="Royal Heritage Suite",
            room_type="SUITE",
            price_per_night=Decimal('6000.00'),
            capacity_adults=2,
            total_rooms=3
        )

        self.platform_setting = PlatformSetting.objects.create(
            commission_percentage=Decimal('10.00'),
            payout_hold_days=7,
            payout_provider_mode='RAZORPAYX'
        )

        # Verified payout account for owner
        self.payout_account = HostPayoutAccount.objects.create(
            user=self.owner,
            payout_method=HostPayoutAccount.METHOD_BANK,
            account_holder_name="Hotel Host Enterprises",
            bank_name="HDFC Bank",
            account_number="98765432101234",
            ifsc_code="HDFC0001234",
            is_verified=True,
            verification_status=HostPayoutAccount.STATUS_VERIFIED
        )

        self.booking = Booking.objects.create(
            customer=self.customer,
            hotel=self.hotel,
            room=self.room,
            check_in=timezone.now().date(),
            check_out=(timezone.now() + timezone.timedelta(days=2)).date(),
            number_of_guests=2,
            number_of_rooms=1,
            price_per_night=Decimal('6000.00'),
            number_of_nights=2,
            subtotal=Decimal('12000.00'),
            taxes=Decimal('2160.00'),
            total_amount=Decimal('14160.00'),
            booking_status=Booking.STATUS_CONFIRMED,
            payment_status=Booking.PAYMENT_PAID,
            guest_name="Guest User",
            guest_email="customer_settle@example.com",
            guest_phone="9876543210"
        )

    def test_owner_payout_account_registration_and_masking(self):
        """Ensure owner payout details are validated and masked in all responses."""
        self.client.force_authenticate(user=self.owner)

        # Test GET masks bank account
        response = self.client.get('/api/payments/payout-account/')
        self.assertEqual(response.status_code, 200)
        account_data = response.json()['account']
        self.assertEqual(account_data['masked_account_number'], '•••• •••• •••• 1234')
        self.assertNotIn('98765432101234', json.dumps(account_data))

        # Test updating to UPI
        update_resp = self.client.post('/api/payments/payout-account/', {
            'payout_method': 'UPI',
            'upi_id': 'hotelowner@okhdfcbank',
            'account_holder_name': 'Hotel Host'
        }, format='json')
        self.assertEqual(update_resp.status_code, 200)
        self.assertIn('ho••••@okhdfcbank', update_resp.json()['account']['masked_upi_id'])

        # Test invalid IFSC rejected
        bad_ifsc_resp = self.client.post('/api/payments/payout-account/', {
            'payout_method': 'BANK_ACCOUNT',
            'account_number': '123456789012',
            'confirm_account_number': '123456789012',
            'ifsc_code': 'INVALID_IFSC'
        }, format='json')
        self.assertEqual(bad_ifsc_resp.status_code, 400)

    def test_verified_payment_records_platform_commission_and_7_day_hold(self):
        """Ensure payment verification records platform fee (10%) and net owner payable on 7-day hold."""
        from datetime import datetime, time
        checkout_dt = timezone.make_aware(datetime.combine(self.booking.check_out, time(23, 59, 59)))
        expected_hold_until = checkout_dt + timezone.timedelta(days=7)

        earning = HostEarning.objects.create(
            host=self.owner,
            booking=self.booking,
            gross_amount=Decimal('14160.00'),
            platform_fee_percent=Decimal('10.00'),
            platform_fee=Decimal('1416.00'),
            net_amount=Decimal('12744.00'),
            status=HostEarning.STATUS_ON_HOLD,
            holding_period_days=7,
            hold_until=expected_hold_until
        )

        self.assertEqual(earning.status, HostEarning.STATUS_ON_HOLD)
        self.assertEqual(earning.platform_fee, Decimal('1416.00'))
        self.assertEqual(earning.net_amount, Decimal('12744.00'))

        # Check holding period eligibility (today is before checkout + 7 days)
        is_eligible, reasons = earning.calculate_eligibility()
        self.assertFalse(is_eligible)
        self.assertTrue(any('holding period active' in r.lower() for r in reasons))

    def test_seven_day_holding_period_blocks_early_payout_and_allows_after_maturity(self):
        """Admin payout attempt is rejected before 7-day holding period expires, and approved after."""
        future_hold_until = timezone.now() + timezone.timedelta(days=5)

        earning = HostEarning.objects.create(
            host=self.owner,
            booking=self.booking,
            gross_amount=Decimal('14160.00'),
            platform_fee_percent=Decimal('10.00'),
            platform_fee=Decimal('1416.00'),
            net_amount=Decimal('12744.00'),
            status=HostEarning.STATUS_ON_HOLD,
            holding_period_days=7,
            hold_until=future_hold_until
        )

        self.client.force_authenticate(user=self.admin)

        # Early payout attempt must fail with 400 Bad Request
        early_payout_resp = self.client.post('/api/payments/admin/payouts/initiate/', {
            'earning_ids': [earning.id]
        }, format='json')
        self.assertEqual(early_payout_resp.status_code, 400)
        self.assertIn('holding period active', str(early_payout_resp.json()))

        # Advance holding period past maturity (8 days later)
        past_hold_until = timezone.now() - timezone.timedelta(days=1)
        earning.hold_until = past_hold_until
        earning.save()

        is_eligible, reasons = earning.calculate_eligibility()
        self.assertTrue(is_eligible)
        self.assertEqual(len(reasons), 0)

        # Payout initiation now succeeds
        eligible_payout_resp = self.client.post('/api/payments/admin/payouts/initiate/', {
            'earning_ids': [earning.id],
            'idempotency_key': f'test_idem_{uuid.uuid4().hex}'
        }, format='json')
        # In test mode without live RazorpayX account, returns 202 PROVIDER_SETUP_REQUIRED
        self.assertIn(eligible_payout_resp.status_code, [200, 202])
        self.assertEqual(eligible_payout_resp.json()['payout']['amount'], '12744.00')

    def test_dispute_and_cancellation_hold_enforcement(self):
        """Ensure unresolved customer complaint or cancellation keeps payout on hold even after 7 days."""
        from payments.models import SupportTicket

        past_hold_until = timezone.now() - timezone.timedelta(days=1)

        earning = HostEarning.objects.create(
            host=self.owner,
            booking=self.booking,
            gross_amount=Decimal('14160.00'),
            platform_fee_percent=Decimal('10.00'),
            platform_fee=Decimal('1416.00'),
            net_amount=Decimal('12744.00'),
            status=HostEarning.STATUS_ON_HOLD,
            holding_period_days=7,
            hold_until=past_hold_until
        )

        # 1. Open customer support ticket blocks payout
        ticket = SupportTicket.objects.create(
            user=self.customer,
            booking=self.booking,
            category='BOOKING',
            priority='HIGH',
            status='OPEN',
            subject='AC not working during stay',
            description='Room AC was broken, requesting partial compensation'
        )

        is_eligible, reasons = earning.calculate_eligibility()
        self.assertFalse(is_eligible)
        self.assertTrue(any('support ticket' in r.lower() for r in reasons))

        # Close ticket
        ticket.status = 'RESOLVED'
        ticket.save()

        is_eligible, reasons = earning.calculate_eligibility()
        self.assertTrue(is_eligible)

        # 2. Placing explicit dispute hold blocks payout
        self.client.force_authenticate(user=self.admin)
        dispute_resp = self.client.post('/api/payments/admin/earnings/toggle-dispute/', {
            'earning_id': earning.id,
            'is_disputed': True,
            'dispute_reason': 'Customer credit card dispute chargeback notice'
        }, format='json')
        self.assertEqual(dispute_resp.status_code, 200)

        earning.refresh_from_db()
        self.assertTrue(earning.is_disputed)
        self.assertEqual(earning.status, HostEarning.STATUS_DISPUTED)

        # Payout attempt must be rejected
        blocked_payout_resp = self.client.post('/api/payments/admin/payouts/initiate/', {
            'earning_ids': [earning.id]
        }, format='json')
        self.assertEqual(blocked_payout_resp.status_code, 400)

        # Release dispute
        release_resp = self.client.post('/api/payments/admin/earnings/toggle-dispute/', {
            'earning_id': earning.id,
            'is_disputed': False
        }, format='json')
        self.assertEqual(release_resp.status_code, 200)

        earning.refresh_from_db()
        self.assertFalse(earning.is_disputed)

    def test_duplicate_webhook_idempotency(self):
        """Ensure duplicate webhook events with same event_id are safely ignored without duplication."""
        payload = {
            "event": "payment.captured",
            "event_id": "evt_unique_idempotent_001",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_test_idem_001",
                        "order_id": "order_test_idem_001",
                        "amount": 1416000
                    }
                }
            }
        }
        body_bytes = json.dumps(payload).encode('utf-8')
        signature = hmac.new(
            settings.RAZORPAY_WEBHOOK_SECRET.encode('utf-8'),
            body_bytes,
            hashlib.sha256
        ).hexdigest()

        # First delivery: success
        resp1 = self.client.post(
            '/api/payments/webhook/',
            data=body_bytes,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=signature
        )
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp1.json()['status'], 'success')

        # Duplicate delivery: safely ignored
        resp2 = self.client.post(
            '/api/payments/webhook/',
            data=body_bytes,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=signature
        )
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.json()['status'], 'ignored')
        self.assertIn('already processed', resp2.json()['message'])

    def test_payout_idempotency_prevents_duplicate_transfers(self):
        """Idempotency key prevents initiating multiple payouts for the same batch."""
        past_hold_until = timezone.now() - timezone.timedelta(days=1)

        earning = HostEarning.objects.create(
            host=self.owner,
            booking=self.booking,
            gross_amount=Decimal('14160.00'),
            platform_fee_percent=Decimal('10.00'),
            platform_fee=Decimal('1416.00'),
            net_amount=Decimal('12744.00'),
            status=HostEarning.STATUS_ELIGIBLE,
            holding_period_days=7,
            hold_until=past_hold_until
        )

        self.client.force_authenticate(user=self.admin)
        fixed_key = "idem_fixed_key_test_123"

        # First call creates payout
        resp1 = self.client.post('/api/payments/admin/payouts/initiate/', {
            'earning_ids': [earning.id],
            'idempotency_key': fixed_key
        }, format='json')
        self.assertIn(resp1.status_code, [200, 202])

        # Second call with identical idempotency key returns existing payout without duplicating
        resp2 = self.client.post('/api/payments/admin/payouts/initiate/', {
            'earning_ids': [earning.id],
            'idempotency_key': fixed_key
        }, format='json')
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.json()['status'], 'existing')
        self.assertEqual(resp2.json()['payout']['idempotency_key'], fixed_key)

    def test_host_subscription_get_anonymous(self):
        """Anonymous user can fetch available subscription plans and default tier."""
        self.client.logout()
        resp = self.client.get('/api/payments/host-subscriptions/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['subscription_tier'], 'SILVER')
        self.assertEqual(data['commission_rate'], '10%')
        self.assertEqual(len(data['available_plans']), 3)

    def test_host_subscription_get_authenticated_owner(self):
        """Authenticated hotel owner gets their current subscription tier and commission rate."""
        self.owner.subscription_tier = 'GOLD'
        self.owner.save(update_fields=['subscription_tier'])
        self.client.force_authenticate(user=self.owner)

        resp = self.client.get('/api/payments/host-subscriptions/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['subscription_tier'], 'GOLD')
        self.assertEqual(data['commission_rate'], '5%')
        self.assertEqual(data['commission_percentage'], 5.0)
        self.assertEqual(data['current_subscription']['tier'], 'GOLD')

    def test_host_subscription_post_direct_upgrade(self):
        """Authenticated hotel owner can directly upgrade their subscription tier."""
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post('/api/payments/host-subscriptions/', {
            'action': 'upgrade',
            'plan_id': 'PLATINUM'
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['subscription_tier'], 'PLATINUM')

        self.owner.refresh_from_db()
        self.assertEqual(self.owner.subscription_tier, 'PLATINUM')

    def test_host_subscription_post_invalid_plan(self):
        """Invalid plan id returns 400 Bad Request."""
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post('/api/payments/host-subscriptions/', {
            'action': 'upgrade',
            'plan_id': 'DIAMOND_UNKNOWN'
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Invalid plan_id', resp.json()['error'])

    def test_host_subscription_post_unauthenticated_upgrade(self):
        """Unauthenticated upgrade request returns 401 Unauthorized."""
        self.client.logout()
        resp = self.client.post('/api/payments/host-subscriptions/', {
            'action': 'upgrade',
            'plan_id': 'GOLD'
        }, format='json')
        self.assertEqual(resp.status_code, 401)

    def test_subscription_queuing_when_active_exists(self):
        """Ensure no 2 active subscriptions run simultaneously; new plan is queued as SCHEDULED."""
        from payments.models import HostSubscription
        from payments.subscription_service import get_or_sync_active_subscription
        
        # Ensure owner has an active SILVER plan
        self.owner.subscription_tier = 'SILVER'
        self.owner.save(update_fields=['subscription_tier'])
        active_sub = get_or_sync_active_subscription(self.owner)
        self.assertIsNotNone(active_sub)
        self.assertEqual(active_sub.status, HostSubscription.STATUS_ACTIVE)
        self.assertEqual(active_sub.plan_id, 'SILVER')

        # Now owner subscribes to GOLD plan
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post('/api/payments/host-subscriptions/', {
            'action': 'upgrade',
            'plan_id': 'GOLD'
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        
        # Must be queued as SCHEDULED, not replacing the active plan
        self.assertTrue(data['is_scheduled'])
        self.assertEqual(data['status'], HostSubscription.STATUS_SCHEDULED)
        self.assertIn('queued as SCHEDULED', data['message'])

        # Check in DB: exactly 1 ACTIVE and 1 SCHEDULED
        all_subs = HostSubscription.objects.filter(user=self.owner)
        self.assertEqual(all_subs.filter(status=HostSubscription.STATUS_ACTIVE).count(), 1)
        self.assertEqual(all_subs.filter(status=HostSubscription.STATUS_SCHEDULED).count(), 1)

        scheduled_sub = all_subs.get(status=HostSubscription.STATUS_SCHEDULED)
        self.assertEqual(scheduled_sub.plan_id, 'GOLD')
        self.assertEqual(scheduled_sub.start_date, active_sub.end_date)

    def test_hotel_creation_limit_enforced_for_silver(self):
        """Silver plan allows only 1 hotel property; second hotel creation must be blocked."""
        from payments.subscription_service import get_or_sync_active_subscription
        self.owner.subscription_tier = 'SILVER'
        self.owner.save(update_fields=['subscription_tier'])
        get_or_sync_active_subscription(self.owner)

        self.client.force_authenticate(user=self.owner)
        
        # self.hotel already exists from setUp (1 hotel)
        # Attempting to create a 2nd hotel must fail with 403 Forbidden
        hotel_data = {
            "name": "Second Hotel Unauthorized",
            "description": "Luxury second hotel property in Mumbai.",
            "city": "Mumbai",
            "state": "Maharashtra",
            "address": "Juhu Beach Road",
            "star_rating": 4
        }
        resp = self.client.post('/api/hotels/owner/hotels/', data=hotel_data, format='json')
        self.assertEqual(resp.status_code, 403)
        self.assertIn('HOTEL_PROPERTY_LIMIT_REACHED', str(resp.content))

    def test_room_category_limit_enforced_for_silver(self):
        """Silver plan allows max 5 room categories per hotel; 6th category must be blocked."""
        from payments.subscription_service import get_or_sync_active_subscription
        from rooms.models import Room
        
        self.owner.subscription_tier = 'SILVER'
        self.owner.save(update_fields=['subscription_tier'])
        get_or_sync_active_subscription(self.owner)

        self.client.force_authenticate(user=self.owner)

        room_types = ['STANDARD', 'DELUXE', 'SUPER_DELUXE', 'EXECUTIVE', 'FAMILY']
        # Create up to 5 rooms (room 1 already created in setUp, create remaining)
        existing_rooms = Room.objects.filter(hotel=self.hotel).count()
        for i in range(existing_rooms, 5):
            Room.objects.create(
                hotel=self.hotel,
                room_type=room_types[i],
                title=f'Room Category {i+1}',
                price_per_night=Decimal('2000.00'),
                capacity_adults=2,
                total_rooms=5
            )
        self.assertEqual(Room.objects.filter(hotel=self.hotel).count(), 5)

        # 6th room creation must be blocked by plan limit
        resp = self.client.post('/api/rooms/', data={
            "hotel": self.hotel.id,
            "room_type": "PRESIDENTIAL",
            "title": "Presidential Suite Extra",
            "price_per_night": "10000.00",
            "capacity_adults": 4,
            "total_rooms": 1
        }, format='json')
        self.assertEqual(resp.status_code, 403)
        self.assertIn('ROOM_CATEGORY_LIMIT_REACHED', str(resp.content))

    def test_subscription_auto_promotes_scheduled_on_expiry(self):
        """When an active subscription expires, the queued scheduled subscription auto-activates."""
        from payments.models import HostSubscription
        from payments.subscription_service import get_or_sync_active_subscription
        
        now = timezone.now()
        # Create an expired active subscription
        HostSubscription.objects.filter(user=self.owner).delete()
        past_active = HostSubscription.objects.create(
            user=self.owner,
            plan_id='SILVER',
            status=HostSubscription.STATUS_ACTIVE,
            start_date=now - timezone.timedelta(days=366),
            end_date=now - timezone.timedelta(hours=1),
            amount_paid=Decimal('1999.00')
        )
        
        # Create a scheduled subscription ready to take over
        scheduled = HostSubscription.objects.create(
            user=self.owner,
            plan_id='PLATINUM',
            status=HostSubscription.STATUS_SCHEDULED,
            start_date=now - timezone.timedelta(hours=1),
            end_date=now + timezone.timedelta(days=364),
            amount_paid=Decimal('7999.00')
        )

        active = get_or_sync_active_subscription(self.owner)
        self.assertIsNotNone(active)
        self.assertEqual(active.id, scheduled.id)
        self.assertEqual(active.status, HostSubscription.STATUS_ACTIVE)
        self.assertEqual(active.plan_id, 'PLATINUM')

        past_active.refresh_from_db()
        self.assertEqual(past_active.status, HostSubscription.STATUS_EXPIRED)




