import os
import sys
import django
import uuid
from decimal import Decimal

sys.path.append(os.path.abspath('.'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.utils import timezone
from rest_framework.test import APIClient
from users.models import User
from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking
from payments.models import Payment, Refund, HostEarning, PlatformSetting, WebhookEvent

client = APIClient()

print("==================================================================")
print("RUNNING RAZORPAYX TEST MODE CUSTOMER PAYOUT COMPREHENSIVE SUITE")
print("==================================================================")

# Setup Test Users
admin_user = User.objects.filter(is_superuser=True).first() or User.objects.filter(role='ADMIN').first()
host_user = User.objects.filter(role='HOTEL_OWNER').first()
customer, _ = User.objects.get_or_create(
    username="test_rzpx_customer",
    defaults={"email": "rzpx_cust@example.com", "phone_number": "+919876543210", "role": "CUSTOMER"}
)
unauthorized_user, _ = User.objects.get_or_create(
    username="test_rzpx_unauth",
    defaults={"email": "rzpx_unauth@example.com", "phone_number": "+919876543211", "role": "CUSTOMER"}
)

hotel = Hotel.objects.filter(owner=host_user).first() or Hotel.objects.first()
room = Room.objects.filter(hotel=hotel).first() or Room.objects.create(
    hotel=hotel, room_type="DELUXE", title="Test Room", price_per_night=3000.00, total_rooms=5
)

# Test Booking 1
b1 = Booking.objects.create(
    booking_id=f"BK-RZPX-{uuid.uuid4().hex[:6].upper()}",
    hotel=hotel,
    room=room,
    customer=customer,
    guest_name="Rajesh Sharma",
    guest_email="rajesh.sharma@example.com",
    guest_phone="+919876543210",
    check_in=timezone.now().date(),
    check_out=timezone.now().date() + timezone.timedelta(days=2),
    total_amount=Decimal('6000.00'),
    price_per_night=Decimal('3000.00'),
    subtotal=Decimal('6000.00'),
    taxes=Decimal('0.00'),
    booking_status=Booking.STATUS_CONFIRMED,
    payment_status=Booking.PAYMENT_PAID
)
p1 = Payment.objects.create(
    booking=b1,
    user=customer,
    razorpay_order_id=f"order_{uuid.uuid4().hex[:10]}",
    razorpay_payment_id=f"pay_{uuid.uuid4().hex[:10]}",
    amount=Decimal('6000.00'),
    status=Payment.STATUS_CAPTURED
)
he1 = HostEarning.objects.create(
    booking=b1,
    host=hotel.owner,
    gross_amount=Decimal('6000.00'),
    platform_fee=Decimal('600.00'),
    tax=Decimal('0.00'),
    net_amount=Decimal('5400.00'),
    status=HostEarning.STATUS_ON_HOLD
)

# -------------------------------------------------------------------------
# TEST 1: Indian Validation Checks on Bank & UPI Destination
# -------------------------------------------------------------------------
print("\n--- TEST 1: Destination Validation Checks ---")
client.force_authenticate(user=admin_user)

# Bad IFSC
res_bad_ifsc = client.post('/api/payments/payouts/customer/', {
    "booking_id": b1.booking_id,
    "payout_mode": "NEFT",
    "account_number": "123456789012",
    "ifsc_code": "INVALID_IFSC"
}, format='json')
assert res_bad_ifsc.status_code == 400
assert "ifsc_code" in res_bad_ifsc.data
print("  [PASS] Invalid IFSC code properly rejected with 400 Bad Request!")

# Bad Account Number
res_bad_acc = client.post('/api/payments/payouts/customer/', {
    "booking_id": b1.booking_id,
    "payout_mode": "NEFT",
    "account_number": "123", # too short
    "ifsc_code": "HDFC0001234"
}, format='json')
assert res_bad_acc.status_code == 400
assert "account_number" in res_bad_acc.data
print("  [PASS] Invalid Bank Account number rejected with 400 Bad Request!")

# Bad UPI ID
res_bad_upi = client.post('/api/payments/payouts/customer/', {
    "booking_id": b1.booking_id,
    "payout_mode": "UPI",
    "upi_id": "invalid_upi_no_handle"
}, format='json')
assert res_bad_upi.status_code == 400
assert "upi_id" in res_bad_upi.data
print("  [PASS] Invalid UPI handle rejected with 400 Bad Request!")


# -------------------------------------------------------------------------
# TEST 2: Successful RazorpayX NEFT Bank Payout
# -------------------------------------------------------------------------
print("\n--- TEST 2: Successful RazorpayX NEFT Bank Payout ---")
neft_idempotency = f"idem_{uuid.uuid4().hex[:12]}"
res_neft = client.post('/api/payments/payouts/customer/', {
    "booking_id": b1.booking_id,
    "amount": 6000.00,
    "payout_mode": "NEFT",
    "account_holder_name": "Rajesh Sharma",
    "bank_name": "HDFC Bank",
    "account_number": "123456789012",
    "ifsc_code": "HDFC0001234",
    "narration": "Customer Stay Refund",
    "idempotency_key": neft_idempotency
}, format='json')

assert res_neft.status_code in [200, 201], f"Expected 200/201, got {res_neft.status_code}: {res_neft.data}"
assert res_neft.data.get("payout_id") is not None
assert res_neft.data.get("payout_id").startswith("pout_")
assert res_neft.data.get("mode") == "NEFT"
assert res_neft.data.get("status") in ["processing", "processed", "queued"]
assert res_neft.data.get("contact_id") is not None
assert res_neft.data.get("fund_account_id") is not None
print(f"  [PASS] RazorpayX NEFT Payout initiated successfully! Payout ID: {res_neft.data['payout_id']} (Status: {res_neft.data['status']})")

# Verify Database Refund Record
rf_neft = Refund.objects.filter(booking=b1).first()
assert rf_neft is not None
assert rf_neft.payout_reference_id == res_neft.data['payout_id']
assert rf_neft.contact_id == res_neft.data['contact_id']
assert rf_neft.fund_account_id == res_neft.data['fund_account_id']
assert rf_neft.payout_mode == "NEFT"
print("  [PASS] Database Refund record correctly populated with RazorpayX contact_id and fund_account_id!")

# Verify Host Earning Reversal
he1.refresh_from_db()
assert he1.status == HostEarning.STATUS_REVERSED
assert "Customer received bank payout" in he1.hold_reason
print("  [PASS] Host Earning strictly REVERSED! Double payout prevented.")


# -------------------------------------------------------------------------
# TEST 3: Persistent Idempotency (Prevent Duplicate Payout)
# -------------------------------------------------------------------------
print("\n--- TEST 3: Persistent Idempotency Protection ---")
res_idem = client.post('/api/payments/payouts/customer/', {
    "booking_id": b1.booking_id,
    "amount": 6000.00,
    "payout_mode": "NEFT",
    "account_holder_name": "Rajesh Sharma",
    "bank_name": "HDFC Bank",
    "account_number": "123456789012",
    "ifsc_code": "HDFC0001234",
    "idempotency_key": neft_idempotency
}, format='json')

assert res_idem.status_code == 200
assert res_idem.data.get("is_duplicate_prevented") is True
assert res_idem.data.get("payout_id") == res_neft.data["payout_id"]
print("  [PASS] Idempotent replay returned existing payout ID without creating duplicate payout!")


# -------------------------------------------------------------------------
# TEST 4: Successful RazorpayX UPI Payout on Booking 2
# -------------------------------------------------------------------------
print("\n--- TEST 4: RazorpayX UPI Payout ---")
b2 = Booking.objects.create(
    booking_id=f"BK-RZPX-{uuid.uuid4().hex[:6].upper()}",
    hotel=hotel,
    room=room,
    customer=customer,
    guest_name="Rajesh Sharma",
    guest_email="rajesh.sharma@example.com",
    guest_phone="+919876543210",
    check_in=timezone.now().date(),
    check_out=timezone.now().date() + timezone.timedelta(days=1),
    total_amount=Decimal('3000.00'),
    price_per_night=Decimal('3000.00'),
    subtotal=Decimal('3000.00'),
    taxes=Decimal('0.00'),
    booking_status=Booking.STATUS_CONFIRMED,
    payment_status=Booking.PAYMENT_PAID
)
p2 = Payment.objects.create(
    booking=b2,
    user=customer,
    razorpay_order_id=f"order_{uuid.uuid4().hex[:10]}",
    razorpay_payment_id=f"pay_{uuid.uuid4().hex[:10]}",
    amount=Decimal('3000.00'),
    status=Payment.STATUS_CAPTURED
)

res_upi = client.post('/api/payments/payouts/customer/', {
    "booking_id": b2.booking_id,
    "amount": 3000.00,
    "payout_mode": "UPI",
    "upi_id": "rajesh@okhdfcbank",
    "narration": "UPI Stay Refund"
}, format='json')

assert res_upi.status_code in [200, 201]
assert res_upi.data.get("payout_id").startswith("pout_")
assert res_upi.data.get("mode") == "UPI"
print(f"  [PASS] RazorpayX UPI Payout initiated successfully! Payout ID: {res_upi.data['payout_id']} (Mode: UPI)")


# -------------------------------------------------------------------------
# TEST 5: Payout Status Webhook Handling (payout.processed)
# -------------------------------------------------------------------------
print("\n--- TEST 5: Payout Webhook Handling (payout.processed) ---")
from unittest.mock import patch

webhook_payload = {
    "entity": "event",
    "account_id": "acc_mock123",
    "event": "payout.processed",
    "contains": ["payout"],
    "payload": {
        "payout": {
            "entity": {
                "id": res_neft.data["payout_id"],
                "entity": "payout",
                "fund_account_id": res_neft.data["fund_account_id"],
                "amount": 600000,
                "currency": "INR",
                "status": "processed",
                "purpose": "refund",
                "utr": "HDFCN12345678901",
                "mode": "NEFT"
            }
        }
    }
}

with patch('razorpay.utility.Utility.verify_webhook_signature', return_value=True):
    wh_res = client.post(
        '/api/payments/webhook/',
        data=webhook_payload,
        format='json',
        HTTP_X_RAZORPAY_SIGNATURE='test_sig_mock'
    )
    assert wh_res.status_code == 200, f"Expected 200, got {wh_res.status_code}: {wh_res.data}"

rf_neft.refresh_from_db()
assert rf_neft.status == Refund.STATUS_REFUNDED
assert rf_neft.provider_status == "processed"
assert rf_neft.processed_at is not None
print("  [PASS] Webhook payout.processed updated Refund to REFUNDED with processed_at timestamp!")


# -------------------------------------------------------------------------
# TEST 6: Fetch Payout Status via GET API
# -------------------------------------------------------------------------
print("\n--- TEST 6: Fetch Payout Details & Status API ---")
res_get = client.get(f"/api/payments/payouts/customer/{b1.booking_id}/")
assert res_get.status_code == 200
assert res_get.data.get("payout_id") == res_neft.data["payout_id"]
assert res_get.data.get("status") in ["processed", "REFUNDED"]
print("  [PASS] GET /api/payments/payouts/customer/<lookup>/ successfully fetched payout status!")

# -------------------------------------------------------------------------
# CLEANUP
# -------------------------------------------------------------------------
Refund.objects.filter(booking__in=[b1, b2]).delete()
Payment.objects.filter(booking__in=[b1, b2]).delete()
HostEarning.objects.filter(booking__in=[b1, b2]).delete()
Booking.objects.filter(id__in=[b1.id, b2.id]).delete()
customer.delete()
unauthorized_user.delete()

print("\n==================================================================")
print("ALL RAZORPAYX TEST MODE CUSTOMER PAYOUT TESTS PASSED 100%!")
print("==================================================================")

