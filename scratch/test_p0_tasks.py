import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

import hmac
import hashlib
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone
from django.conf import settings
from rest_framework.test import APIClient
from rest_framework import status

from users.models import User
from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking
from payments.models import PlatformSetting, HostEarning, Payment, HostPayoutAccount

def run_all_p0_tests():
    print("==================================================")
    print("RUNNING P0 TASKS COMPREHENSIVE VERIFICATION SUITE")
    print("==================================================")

    client = APIClient()

    # Setup base test users
    admin_user = User.objects.filter(role__in=['ADMIN', 'SUPER_ADMIN']).first()
    if not admin_user:
        admin_user = User.objects.create_superuser('test_admin_p0', 'admin_p0@example.com', 'admin123', role='ADMIN')

    customer1, _ = User.objects.get_or_create(
        username='cust_p0_1',
        defaults={'email': 'cust_p0_1@example.com', 'phone_number': '9811100001', 'role': 'CUSTOMER'}
    )
    customer1.set_password('pass1234')
    customer1.save()

    customer2, _ = User.objects.get_or_create(
        username='cust_p0_2',
        defaults={'email': 'cust_p0_2@example.com', 'phone_number': '9811100002', 'role': 'CUSTOMER'}
    )
    customer2.set_password('pass1234')
    customer2.save()

    host1, _ = User.objects.get_or_create(
        username='host_p0_1',
        defaults={'email': 'host_p0_1@example.com', 'phone_number': '9811100003', 'role': 'HOTEL_OWNER'}
    )
    host1.set_password('pass1234')
    host1.save()

    host2, _ = User.objects.get_or_create(
        username='host_p0_2',
        defaults={'email': 'host_p0_2@example.com', 'phone_number': '9811100004', 'role': 'HOTEL_OWNER'}
    )
    host2.set_password('pass1234')
    host2.save()

    # Setup test hotel & room
    hotel, _ = Hotel.objects.get_or_create(
        owner=host1,
        name='Test Grand Palace Hotel',
        defaults={'city': 'Mumbai', 'state': 'Maharashtra', 'address': '123 Marine Drive'}
    )
    room, _ = Room.objects.get_or_create(
        hotel=hotel,
        title='P0 Deluxe King Room',
        defaults={'price_per_night': Decimal('2000.00'), 'total_rooms': 1}
    )
    room.total_rooms = 1
    room.save()

    # ----------------------------------------------------
    # TEST TASK-01: ESCROW HOLDING PERIOD NON-RETROACTIVE BUG
    # ----------------------------------------------------
    print("\n--- TEST TASK-01: Holding Period Non-Retroactivity ---")
    setting = PlatformSetting.objects.first() or PlatformSetting.objects.create()
    setting.payout_hold_days = 7
    setting.save()

    test_booking_earning, _ = Booking.objects.get_or_create(
        booking_id='BK-P0-TEST-01',
        defaults={
            'customer': customer1,
            'hotel': hotel,
            'room': room,
            'price_per_night': Decimal('2000.00'),
            'number_of_nights': 2,
            'subtotal': Decimal('4000.00'),
            'taxes': Decimal('720.00'),
            'check_in': date.today() + timedelta(days=1),
            'check_out': date.today() + timedelta(days=3),
            'total_amount': Decimal('4720.00'),
            'booking_status': Booking.STATUS_CONFIRMED,
            'guest_name': 'Test Guest',
            'guest_email': 'guest@example.com',
            'guest_phone': '9811100001'
        }
    )
    original_hold_until = timezone.now() + timedelta(days=7)
    earning, _ = HostEarning.objects.update_or_create(
        booking=test_booking_earning,
        defaults={
            'host': host1,
            'gross_amount': Decimal('4720.00'),
            'platform_fee': Decimal('472.00'),
            'net_amount': Decimal('4248.00'),
            'status': HostEarning.STATUS_ON_HOLD,
            'holding_period_days': 7,
            'hold_until': original_hold_until
        }
    )

    client.force_authenticate(user=admin_user)
    resp = client.put('/api/payments/settings/', {'holding_period_days': 15}, format='json')
    assert resp.status_code == status.HTTP_200_OK, f"Expected 200, got {resp.status_code}: {resp.data}"
    
    # Reload earning from DB
    earning.refresh_from_db()
    assert earning.holding_period_days == 7, f"FAILED: Past earning holding_period_days was mutated to {earning.holding_period_days}!"
    assert earning.hold_until == original_hold_until, f"FAILED: Past earning hold_until was mutated!"
    
    # Verify platform setting updated
    setting.refresh_from_db()
    assert setting.payout_hold_days == 15, f"Platform setting failed to update to 15!"
    print("PASS: TASK-01 Non-retroactivity verified: Setting updated to 15 days, past HostEarning preserved 7 days!")

    # ----------------------------------------------------
    # TEST TASK-02: RAZORPAY SERVER-SIDE PRICE & CONSTANT TIME VERIFICATION
    # ----------------------------------------------------
    print("\n--- TEST TASK-02: Razorpay Server Calculation & Signature Verification ---")
    Booking.objects.filter(booking_id='BK-P0-PAY-02').delete()
    booking_pay = Booking.objects.create(
        booking_id='BK-P0-PAY-02',
        customer=customer1,
        hotel=hotel,
        room=room,
        check_in=date.today() + timedelta(days=5),
        check_out=date.today() + timedelta(days=7),
        price_per_night=Decimal('2000.00'),
        number_of_nights=2,
        number_of_rooms=1,
        subtotal=Decimal('4000.00'),
        taxes=Decimal('720.00'),
        total_amount=Decimal('4720.00'),
        booking_status=Booking.STATUS_PENDING_PAYMENT,
        guest_name='Test Guest',
        guest_email='guest@example.com',
        guest_phone='9811100001'
    )

    client.force_authenticate(user=customer1)
    from unittest.mock import patch, MagicMock

    mock_rzp = MagicMock()
    mock_rzp.order.create.return_value = {"id": "order_mock123456"}

    with patch('payments.views.get_platform_razorpay_client', return_value=(mock_rzp, 'rzp_test_key')):
        # Attempt to tamper client amount to Rs 100
        create_order_resp = client.post('/api/payments/create-order/', {
            'booking_id': booking_pay.booking_id,
            'amount': 100.00 # TAMPERED CLIENT AMOUNT
        }, format='json')
        assert create_order_resp.status_code == status.HTTP_200_OK, f"Expected 200, got {create_order_resp.status_code}: {create_order_resp.data}"
        order_data = create_order_resp.data
        # 2 nights * 2000 = 4000 + 18% taxes (720) = 4720 => 472000 paise
        assert order_data['amount'] == 472000, f"FAILED: Expected 472000 paise (Rs 4720), got {order_data['amount']}!"
        print(f"PASS: TASK-02 Client price tampering ignored! Charged Rs {order_data['amount']/100} instead of client's Rs 100.")

        # Test signature verification with forged signature
        bad_verify_resp = client.post('/api/payments/verify/', {
            'booking_id': booking_pay.booking_id,
            'razorpay_order_id': order_data['order_id'],
            'razorpay_payment_id': 'pay_fake123456789',
            'razorpay_signature': 'forged_fake_signature_hash_123456'
        }, format='json')
        assert bad_verify_resp.status_code == status.HTTP_400_BAD_REQUEST, f"Expected 400 for bad signature, got {bad_verify_resp.status_code}"
        assert "Invalid payment signature" in bad_verify_resp.data.get('error', ''), f"Unexpected error: {bad_verify_resp.data}"
        print("PASS: TASK-02 Forged Razorpay signature rejected with 400 Bad Request ('Invalid payment signature')!")

        # Test signature verification with authentic HMAC signature
        correct_sig = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode('utf-8'),
            f"{order_data['order_id']}|pay_real123456789".encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        mock_rzp.payment.fetch.return_value = {
            'id': 'pay_real123456789',
            'amount': 472000,
            'currency': 'INR',
            'status': 'captured'
        }

        good_verify_resp = client.post('/api/payments/verify/', {
            'booking_id': booking_pay.booking_id,
            'razorpay_order_id': order_data['order_id'],
            'razorpay_payment_id': 'pay_real123456789',
            'razorpay_signature': correct_sig
        }, format='json')
        assert good_verify_resp.status_code == status.HTTP_200_OK, f"Expected 200 for valid signature, got {good_verify_resp.status_code}: {good_verify_resp.data}"
        print("PASS: TASK-02 Authentic constant-time HMAC signature verified and booking confirmed!")

    # ----------------------------------------------------
    # TEST TASK-03: USER MODEL EMAIL & PHONE DB UNIQUE CONSTRAINT
    # ----------------------------------------------------
    print("\n--- TEST TASK-03: Database Constraints on Email & Phone ---")
    client.logout()
    # 1. Duplicate email case-insensitive
    dup_email_resp = client.post('/api/users/register/', {
        'email': 'CUST_P0_1@EXAMPLE.COM', # exact case variation of existing cust_p0_1@example.com
        'password': 'Password123#',
        'phone_number': '9899000099'
    }, format='json')
    assert dup_email_resp.status_code == status.HTTP_400_BAD_REQUEST, f"Expected 400 for duplicate email, got {dup_email_resp.status_code}"
    assert 'email' in dup_email_resp.data, f"Expected 'email' field error in {dup_email_resp.data}"
    print("PASS: TASK-03 Case-insensitive duplicate email rejected at validation & constraint!")

    # 2. Duplicate phone
    dup_phone_resp = client.post('/api/users/register/', {
        'email': 'brandnewuser@example.com',
        'password': 'Password123#',
        'phone_number': '9811100001' # already used by customer1
    }, format='json')
    assert dup_phone_resp.status_code == status.HTTP_400_BAD_REQUEST, f"Expected 400 for duplicate phone, got {dup_phone_resp.status_code}"
    assert 'phone_number' in dup_phone_resp.data, f"Expected 'phone_number' field error in {dup_phone_resp.data}"
    print("PASS: TASK-03 Duplicate phone number rejected at validation & constraint!")

    # ----------------------------------------------------
    # TEST TASK-04: CONCURRENCY & OVERSELLING PREVENTION (select_for_update)
    # ----------------------------------------------------
    print("\n--- TEST TASK-04: Booking Concurrency & Room Overselling ---")
    # Room capacity is 1 unit.
    # Create an active confirmed booking on dates day 20 to 22
    cin = date.today() + timedelta(days=20)
    cout = date.today() + timedelta(days=22)
    Booking.objects.filter(room=room, check_in=cin, check_out=cout).delete()
    Booking.objects.filter(booking_id__startswith='BK-P0-OVERSELL').delete()

    b_confirmed = Booking.objects.create(
        booking_id='BK-P0-OVERSELL-1',
        customer=customer1,
        hotel=hotel,
        room=room,
        price_per_night=Decimal('2000.00'),
        number_of_nights=2,
        subtotal=Decimal('4000.00'),
        taxes=Decimal('720.00'),
        check_in=cin,
        check_out=cout,
        number_of_rooms=1,
        total_amount=Decimal('4720.00'),
        booking_status=Booking.STATUS_CONFIRMED,
        guest_name='Guest 1',
        guest_email='g1@example.com',
        guest_phone='9811100001'
    )

    # Now Customer 2 attempts to book the same room on overlapping dates (day 21 to 23)
    client.force_authenticate(user=customer2)
    oversell_resp = client.post('/api/bookings/', {
        'room': room.id,
        'hotel': hotel.id,
        'check_in': str(cin + timedelta(days=1)), # overlapping day 21
        'check_out': str(cout + timedelta(days=1)), # day 23
        'number_of_rooms': 1,
        'guest_name': 'Guest 2',
        'guest_email': 'g2@example.com',
        'guest_phone': '9811100002'
    }, format='json')
    assert oversell_resp.status_code == status.HTTP_409_CONFLICT, f"Expected 409 Conflict, got {oversell_resp.status_code}: {oversell_resp.data}"
    assert "no longer available" in str(oversell_resp.data.get('error', '')).lower(), f"Unexpected error message: {oversell_resp.data}"
    print(f"PASS: TASK-04 Overselling prevented with HTTP 409 Conflict: '{oversell_resp.data['error']}'")

    # ----------------------------------------------------
    # TEST TASK-05: RBAC & IDOR PREVENTION
    # ----------------------------------------------------
    print("\n--- TEST TASK-05: RBAC & IDOR Prevention ---")
    # Customer 2 attempts to cancel Customer 1's booking
    client.force_authenticate(user=customer2)
    idor_cancel_resp = client.post(f'/api/bookings/{b_confirmed.booking_id}/cancel/', {
        'reason': 'Malicious cancel attempt'
    }, format='json')
    assert idor_cancel_resp.status_code == status.HTTP_403_FORBIDDEN, f"Expected 403 Forbidden for IDOR cancel, got {idor_cancel_resp.status_code}"
    print("PASS: TASK-05 Customer 2 forbidden (HTTP 403) from cancelling Customer 1's booking!")

    # Customer 2 attempts to view Customer 1's booking receipt
    idor_view_resp = client.get(f'/api/bookings/{b_confirmed.booking_id}/')
    assert idor_view_resp.status_code == status.HTTP_403_FORBIDDEN, f"Expected 403 Forbidden for IDOR view, got {idor_view_resp.status_code}"
    print("PASS: TASK-05 Customer 2 forbidden (HTTP 403) from accessing Customer 1's booking receipt!")

    # Host 2 attempts to view Host 1's payout account
    client.force_authenticate(user=host2)
    idor_host_payout = client.get(f'/api/payments/payout-account/?host_id={host1.id}')
    assert idor_host_payout.status_code == status.HTTP_403_FORBIDDEN, f"Expected 403 for unauthorized host_id query, got {idor_host_payout.status_code}"
    print("PASS: TASK-05 Host 2 forbidden (HTTP 403) from accessing Host 1's payout account!")

    print("\n==================================================")
    print("ALL P0 TASKS (TASK-01 to TASK-05) PASSED 100%!")
    print("==================================================")

if __name__ == '__main__':
    run_all_p0_tests()
