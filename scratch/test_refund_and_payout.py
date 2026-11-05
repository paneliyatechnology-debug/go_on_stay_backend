import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch, MagicMock

from users.models import User
from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking
from payments.models import Payment, Refund, HostEarning, HostPayout, HostPayoutAccount, PlatformSetting

def run_refund_payout_test_suite():
    print("==================================================================")
    print("RUNNING BACKEND REFUND & HOST PAYOUT COMPREHENSIVE VERIFICATION")
    print("==================================================================")

    client = APIClient()

    # 1. Setup Admin, Customer, and Host
    admin_user = User.objects.filter(role__in=['ADMIN', 'SUPER_ADMIN']).first()
    if not admin_user:
        admin_user = User.objects.create_superuser('admin_rf', 'admin_rf@example.com', 'admin123', role='ADMIN')

    customer, _ = User.objects.get_or_create(
        username='cust_rf_01',
        defaults={'email': 'cust_rf_01@example.com', 'phone_number': '9811200001', 'role': 'CUSTOMER'}
    )
    customer.set_password('pass1234')
    customer.save()

    host, _ = User.objects.get_or_create(
        username='host_rf_01',
        defaults={'email': 'host_rf_01@example.com', 'phone_number': '9811200002', 'role': 'HOTEL_OWNER'}
    )
    host.set_password('pass1234')
    host.save()

    payout_acc, _ = HostPayoutAccount.objects.get_or_create(
        user=host,
        defaults={
            'account_holder_name': 'Host RF Account',
            'bank_name': 'HDFC Bank',
            'account_number': '12345678901234',
            'ifsc_code': 'HDFC0001234',
            'is_verified': True,
            'verification_status': HostPayoutAccount.STATUS_VERIFIED
        }
    )

    hotel, _ = Hotel.objects.get_or_create(
        owner=host,
        name='Test Refund Grand Hotel',
        defaults={'city': 'Goa', 'state': 'Goa', 'address': 'Calangute Beach'}
    )
    room, _ = Room.objects.get_or_create(
        hotel=hotel,
        title='Refund Ocean Villa',
        defaults={'price_per_night': Decimal('2500.00'), 'total_rooms': 2}
    )

    # Clean up previous test runs for BK-REF-TEST-01
    Booking.objects.filter(booking_id='BK-REF-TEST-01').delete()

    # 2. Create Confirmed & Paid Booking
    booking = Booking.objects.create(
        booking_id='BK-REF-TEST-01',
        customer=customer,
        hotel=hotel,
        room=room,
        check_in=date.today() + timedelta(days=10),
        check_out=date.today() + timedelta(days=12),
        price_per_night=Decimal('2500.00'),
        number_of_nights=2,
        number_of_rooms=1,
        subtotal=Decimal('5000.00'),
        taxes=Decimal('900.00'),
        total_amount=Decimal('5900.00'),
        booking_status=Booking.STATUS_CONFIRMED,
        payment_status=Booking.PAYMENT_PAID,
        guest_name='Rahul Sharma',
        guest_email='rahul@example.com',
        guest_phone='9811200001',
        confirmed_at=timezone.now()
    )

    captured_payment = Payment.objects.create(
        booking=booking,
        user=customer,
        amount=Decimal('5900.00'),
        currency='INR',
        razorpay_order_id='order_rf_test_12345',
        razorpay_payment_id='pay_rf_captured_999',
        status=Payment.STATUS_CAPTURED,
        payment_method='Online UPI',
        paid_at=timezone.now()
    )

    # Host earning created during booking confirmation
    earning = HostEarning.objects.create(
        host=host,
        booking=booking,
        gross_amount=Decimal('5900.00'),
        platform_fee_percent=Decimal('10.00'),
        platform_fee=Decimal('590.00'),
        net_amount=Decimal('5310.00'),
        status=HostEarning.STATUS_ON_HOLD,
        holding_period_days=7,
        hold_until=timezone.now() + timedelta(days=7),
        hold_reason="7-Day holding period active."
    )

    print("Initial State: Booking CONFIRMED, Payment CAPTURED, HostEarning ON_HOLD (Rs. 5310 net).")

    # ----------------------------------------------------
    # TEST 1: CUSTOMER CANCELS BOOKING & HOST PAYOUT IS EXCLUDED
    # ----------------------------------------------------
    print("\n--- STEP 1: Customer Cancels Booking & Host Payout Exclusion ---")
    client.force_authenticate(user=customer)
    cancel_resp = client.post(f'/api/bookings/{booking.booking_id}/cancel/', {
        'reason': 'Change of travel plans'
    }, format='json')
    assert cancel_resp.status_code == status.HTTP_200_OK, f"Cancel failed: {cancel_resp.data}"

    booking.refresh_from_db()
    earning.refresh_from_db()

    assert booking.booking_status == Booking.STATUS_CANCELLED, f"Expected CANCELLED, got {booking.booking_status}"
    assert booking.payment_status == Booking.PAYMENT_REFUND_PENDING, f"Expected REFUND_PENDING, got {booking.payment_status}"
    assert booking.refundable_amount > Decimal('0.00'), f"Refundable amount is zero!"

    # CRITICAL: Verify Host Earning is REVERSED immediately
    assert earning.status == HostEarning.STATUS_REVERSED, f"FAILED: HostEarning status is {earning.status}, expected REVERSED!"
    assert earning.refund_amount == booking.refundable_amount, f"FAILED: Earning refund_amount mismatch!"
    
    is_eligible, reasons = earning.calculate_eligibility()
    assert is_eligible is False, f"FAILED: Cancelled booking earning still reports is_eligible=True!"
    print(f"PASS: HostEarning successfully REVERSED ({earning.status}). Payout eligibility blocked: {reasons[0]}")

    # Verify Admin Payout Batch cannot include this earning
    client.force_authenticate(user=admin_user)
    payout_init_resp = client.post('/api/payments/admin/payouts/initiate/', {
        'earning_ids': [earning.id],
        'notes': 'Attempting to payout cancelled booking'
    }, format='json')
    assert payout_init_resp.status_code == status.HTTP_400_BAD_REQUEST, f"Expected 400 Bad Request, got {payout_init_resp.status_code}: {payout_init_resp.data}"
    print(f"PASS: Payout initiation for cancelled booking strictly blocked: {payout_init_resp.data.get('details')}")

    # ----------------------------------------------------
    # TEST 2: FAILED REFUND NOT MARKED REFUNDED (NO FAKE SUCCESS)
    # ----------------------------------------------------
    print("\n--- STEP 2: Actual Provider Failure Handling (No Fake Success) ---")
    mock_rzp_fail = MagicMock()
    mock_rzp_fail.payment.refund.side_effect = Exception("BAD_REQUEST_ERROR: Payment gateway declined refund due to insufficient balance.")

    with patch('payments.views.get_platform_razorpay_client', return_value=(mock_rzp_fail, 'rzp_key')):
        fail_refund_resp = client.post('/api/payments/refund/', {
            'booking_id': booking.booking_id,
            'idempotency_key': f"ref_{booking.booking_id}"
        }, format='json')

        assert fail_refund_resp.status_code == status.HTTP_400_BAD_REQUEST, f"Expected 400 for provider failure, got {fail_refund_resp.status_code}: {fail_refund_resp.data}"
        assert fail_refund_resp.data['refund_status'] == Refund.STATUS_REFUND_FAILED, f"Expected REFUND_FAILED, got {fail_refund_resp.data['refund_status']}"
        assert "insufficient balance" in fail_refund_resp.data['failure_details'].lower()

        # Verify Database
        rf_rec = Refund.objects.get(booking=booking)
        assert rf_rec.status == Refund.STATUS_REFUND_FAILED, f"Database record is not REFUND_FAILED!"
        assert rf_rec.failure_reason is not None, "failure_reason was not recorded!"
        assert rf_rec.failed_at is not None, "failed_at timestamp was not saved!"
        booking.refresh_from_db()
        assert booking.payment_status == Booking.PAYMENT_REFUND_PENDING, f"Booking payment status should remain REFUND_PENDING, got {booking.payment_status}"
        print(f"PASS: Provider failure correctly recorded in DB as REFUND_FAILED! Not marked REFUNDED.")

    # ----------------------------------------------------
    # TEST 3: ACTUAL REFUND PROCESSING & SAFE RETRY
    # ----------------------------------------------------
    print("\n--- STEP 3: Provider Success on Safe Retry & Database Confirmation ---")
    mock_rzp_success = MagicMock()
    mock_rzp_success.payment.refund.return_value = {
        "id": "rfnd_RzpLive_987654321",
        "status": "processed",
        "amount": int(booking.refundable_amount * 100),
        "currency": "INR",
        "payment_id": captured_payment.razorpay_payment_id
    }

    with patch('payments.views.get_platform_razorpay_client', return_value=(mock_rzp_success, 'rzp_key')):
        success_refund_resp = client.post('/api/payments/refund/', {
            'booking_id': booking.booking_id,
            'idempotency_key': f"ref_{booking.booking_id}"
        }, format='json')

        assert success_refund_resp.status_code == status.HTTP_200_OK, f"Expected 200, got {success_refund_resp.status_code}: {success_refund_resp.data}"
        resp_data = success_refund_resp.data
        assert resp_data['refund_status'] == Refund.STATUS_REFUNDED, f"Expected REFUNDED, got {resp_data['refund_status']}"
        assert resp_data['provider_refund_id'] == "rfnd_RzpLive_987654321"
        assert resp_data['payout_eligibility'] is False
        assert resp_data['host_payable_amount'] == 0.00
        assert resp_data['booking_id'] == booking.booking_id
        assert resp_data['cancellation_status'] == Booking.STATUS_CANCELLED

        # Verify Database Record Reused (Retry count incremented, no duplicate row)
        all_refunds_count = Refund.objects.filter(booking=booking).count()
        assert all_refunds_count == 1, f"FAILED: Created duplicate refund records! Count: {all_refunds_count}"
        rf_rec.refresh_from_db()
        assert rf_rec.status == Refund.STATUS_REFUNDED
        assert rf_rec.retry_count >= 1, f"Expected retry_count >= 1, got {rf_rec.retry_count}"
        assert rf_rec.razorpay_refund_id == "rfnd_RzpLive_987654321"
        assert rf_rec.processed_at is not None

        booking.refresh_from_db()
        assert booking.payment_status == Booking.PAYMENT_REFUNDED
        print("PASS: Refund confirmed by provider and DB marked REFUNDED. Safe retry reused existing record!")

    # ----------------------------------------------------
    # TEST 4: DUPLICATE REFUND PROTECTION (IDEMPOTENCY)
    # ----------------------------------------------------
    print("\n--- STEP 4: Duplicate Refund Prevention (Persistent Idempotency) ---")
    mock_rzp_success.payment.refund.reset_mock()
    with patch('payments.views.get_platform_razorpay_client', return_value=(mock_rzp_success, 'rzp_key')):
        dup_refund_resp = client.post('/api/payments/refund/', {
            'booking_id': booking.booking_id,
            'idempotency_key': f"ref_{booking.booking_id}"
        }, format='json')

        assert dup_refund_resp.status_code == status.HTTP_200_OK
        assert "already" in dup_refund_resp.data.get('message', '').lower()
        # Verify provider client.payment.refund was NOT called again
        mock_rzp_success.payment.refund.assert_not_called()
        assert Refund.objects.filter(booking=booking).count() == 1
        print("PASS: Duplicate refund strictly prevented! Gateway was not called again.")

    # ----------------------------------------------------
    # TEST 5: ADMIN REFUND LIST API RETURNS ALL 8 FIELDS
    # ----------------------------------------------------
    print("\n--- STEP 5: Admin Refund List API Contract Verification ---")
    admin_refund_list_resp = client.get('/api/payments/admin/refunds/')
    assert admin_refund_list_resp.status_code == status.HTTP_200_OK

    results = admin_refund_list_resp.data.get('results', admin_refund_list_resp.data)
    target_refund = next((r for r in results if r['booking_id'] == booking.booking_id), None)
    assert target_refund is not None, f"Booking {booking.booking_id} not found in admin refund list!"

    # Verify all 8 contract fields
    assert target_refund['booking_id'] == booking.booking_id
    assert target_refund['cancellation_status'] == Booking.STATUS_CANCELLED
    assert target_refund['refund_status'] == Refund.STATUS_REFUNDED
    assert float(target_refund['refund_amount']) == float(booking.refundable_amount)
    assert target_refund['provider_refund_id'] == "rfnd_RzpLive_987654321"
    assert target_refund['payout_eligibility'] is False
    assert float(target_refund['host_payable_amount']) == 0.00
    assert target_refund['updated_timestamps'] is not None

    print("PASS: Admin Refund API returns all 8 required fields correctly:")
    for field in ['booking_id', 'cancellation_status', 'refund_status', 'refund_amount', 'provider_refund_id', 'payout_eligibility', 'host_payable_amount', 'updated_timestamps']:
        print(f"  - {field}: {target_refund[field]}")

    # ----------------------------------------------------
    # TEST 6: REFRESHING PAGE DOES NOT REVERT STATUS & HOST SETTLEMENTS EXCLUDED
    # ----------------------------------------------------
    print("\n--- STEP 6: Persistence & Host Settlements Ledger Verification ---")
    # Fresh query from DB simulating page reload
    fresh_booking = Booking.objects.get(booking_id=booking.booking_id)
    fresh_refund = Refund.objects.get(booking=fresh_booking)
    fresh_earning = HostEarning.objects.get(booking=fresh_booking)

    assert fresh_booking.booking_status == Booking.STATUS_CANCELLED
    assert fresh_booking.payment_status == Booking.PAYMENT_REFUNDED
    assert fresh_refund.status == Refund.STATUS_REFUNDED
    assert fresh_earning.status == HostEarning.STATUS_REVERSED

    # Host views their settlement ledger
    client.force_authenticate(user=host)
    settlement_resp = client.get('/api/payments/settlements/')
    assert settlement_resp.status_code == status.HTTP_200_OK

    host_results = settlement_resp.data.get('results', [])
    target_host_earning = next((e for e in host_results if e['booking_id'] == booking.booking_id), None)
    assert target_host_earning is not None
    assert target_host_earning['payout_eligibility'] is False
    assert target_host_earning['host_payable_amount'] == 0.00
    assert target_host_earning['status'] == HostEarning.STATUS_REVERSED

    print("PASS: Refreshing/re-querying maintains 100% database persistence.")
    print("PASS: Host Settlements ledger strictly reports payout_eligibility=False and host_payable_amount=0.00.")

    print("\n==================================================================")
    print("ALL 6 BACKEND REFUND & HOST PAYOUT REQUIREMENTS PASSED (100%)!")
    print("==================================================================")

if __name__ == '__main__':
    run_refund_payout_test_suite()
