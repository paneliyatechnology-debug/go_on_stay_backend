import os
import sys
import django
from decimal import Decimal
from unittest.mock import MagicMock, patch

sys.path.append(os.path.abspath('.'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.utils import timezone
from rest_framework.test import APIClient
from users.models import User
from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking
from payments.models import Payment, Refund, HostEarning, HostPayout, PlatformSetting
import uuid

client = APIClient()

print("==================================================================")
print("RUNNING COMPLETE REFUND SYSTEM COMPREHENSIVE TEST SUITE")
print("==================================================================")

# 0. Setup Test Users, Hotel, Room
admin_user = User.objects.filter(is_superuser=True).first()
if not admin_user:
    admin_user = User.objects.filter(role='ADMIN').first()

host_user = User.objects.filter(role='HOTEL_OWNER').first()
customer1, _ = User.objects.get_or_create(
    username="refund_cust_1",
    defaults={"email": "refund_cust_1@example.com", "phone_number": "9811122233", "role": "CUSTOMER"}
)
customer2, _ = User.objects.get_or_create(
    username="refund_cust_2",
    defaults={"email": "refund_cust_2@example.com", "phone_number": "9811122244", "role": "CUSTOMER"}
)

hotel = Hotel.objects.filter(owner=host_user).first() or Hotel.objects.first()
room = Room.objects.filter(hotel=hotel).first() or Room.objects.create(
    hotel=hotel, room_type="DELUXE", title="Deluxe Test Suite", price_per_night=5000.00, total_rooms=5
)

# -------------------------------------------------------------------------
# REQUIREMENT 1: Customer Cancellation with Bank / UPI Details
# -------------------------------------------------------------------------
print("\n--- REQUIREMENT 1: Customer Cancellation with Bank/UPI Details ---")
b1 = Booking.objects.create(
    booking_id=f"BK-SYS-REF-{uuid.uuid4().hex[:6].upper()}",
    customer=customer1,
    hotel=hotel,
    room=room,
    check_in=timezone.now().date() + timezone.timedelta(days=7),
    check_out=timezone.now().date() + timezone.timedelta(days=9),
    guest_name="Rajesh Sharma",
    guest_email="rajesh@example.com",
    guest_phone="9852226252",
    total_amount=Decimal('10000.00'),
    price_per_night=Decimal('5000.00'),
    subtotal=Decimal('10000.00'),
    taxes=Decimal('0.00'),
    booking_status=Booking.STATUS_CONFIRMED,
    payment_status=Booking.PAYMENT_PAID
)
p1 = Payment.objects.create(
    booking=b1,
    user=customer1,
    razorpay_order_id=f"order_{uuid.uuid4().hex[:10]}",
    razorpay_payment_id=f"pay_{uuid.uuid4().hex[:10]}",
    amount=Decimal('10000.00'),
    status=Payment.STATUS_CAPTURED
)
he1 = HostEarning.objects.create(
    booking=b1,
    host=hotel.owner,
    gross_amount=Decimal('10000.00'),
    platform_fee=Decimal('1000.00'),
    tax=Decimal('100.00'),
    net_amount=Decimal('8900.00'),
    status=HostEarning.STATUS_ON_HOLD
)

# Customer cancels providing direct bank details
client.force_authenticate(user=customer1)
cancel_res = client.post(f'/api/bookings/{b1.booking_id}/cancel/', {
    "reason": "Change of travel plans",
    "refund_mode": "BANK_TRANSFER",
    "account_holder_name": "Rajesh Sharma",
    "bank_name": "HDFC Bank",
    "account_number": "123456789012",
    "ifsc_code": "HDFC0001234"
}, format='json')

assert cancel_res.status_code == 200, f"Expected 200 Cancel, got {cancel_res.status_code}: {cancel_res.data}"
assert cancel_res.data.get('status') == 'CANCELLED' or cancel_res.data.get('booking_status') == 'CANCELLED'

# Verify bank details are securely associated with pending Refund record
q_refund = Refund.objects.filter(booking=b1).first()
assert q_refund is not None, "Pending refund record must be created"
assert q_refund.status == Refund.STATUS_REFUND_PENDING
assert q_refund.refund_mode == Refund.REFUND_MODE_BANK
assert q_refund.customer_account_number == "123456789012"
assert q_refund.customer_ifsc_code == "HDFC0001234"
assert q_refund.customer_bank_name == "HDFC Bank"
print(f"  [PASS] Cancellation successfully saved customer bank details to pending Refund: {q_refund.customer_bank_name} {q_refund.customer_ifsc_code}")


# -------------------------------------------------------------------------
# REQUIREMENT 2 & 6: Security, Access Restriction & Masking
# -------------------------------------------------------------------------
print("\n--- REQUIREMENT 2 & 6: Security, IDOR Protection & Masking ---")
# Customer 2 (unauthorized) tries to access Customer 1's refund details -> 403
client.force_authenticate(user=customer2)
res_idor = client.get(f'/api/payments/refunds/{b1.booking_id}/')
assert res_idor.status_code == 403, f"Expected 403 Forbidden for unauthorized user, got {res_idor.status_code}"
print("  [PASS] IDOR Protection: Customer 2 forbidden (HTTP 403) from Customer 1's refund details!")

# Customer 1 (owner) accesses own refund details -> Masked account number
client.force_authenticate(user=customer1)
res_cust = client.get(f'/api/payments/refunds/{b1.booking_id}/')
assert res_cust.status_code == 200
payout_info = res_cust.data.get('customer_payout_details') or {}
acc_masked = payout_info.get('account_number_masked')
assert acc_masked.startswith('******'), f"Customer view must mask bank account number: {acc_masked}"
assert acc_masked.endswith('9012')
print(f"  [PASS] Security Masking: Customer view masks bank account: '{acc_masked}'")

# Admin accesses refund details -> Full unmasked data
client.force_authenticate(user=admin_user)
res_adm = client.get(f'/api/payments/refunds/{b1.booking_id}/')
assert res_adm.status_code == 200
assert res_adm.data['customer_account_number'] == "123456789012"
print(f"  [PASS] Admin Authorization: Admin sees full unmasked account: '{res_adm.data['customer_account_number']}'")


# -------------------------------------------------------------------------
# REQUIREMENT 3: Actual Refund Processing - Method A: ORIGINAL_SOURCE
# -------------------------------------------------------------------------
print("\n--- REQUIREMENT 3: Process Refund via ORIGINAL_SOURCE (Razorpay Refund API) ---")
mock_rzp = MagicMock()
mock_rzp.payment.refund.return_value = {
    "id": f"rfnd_Rzp_{uuid.uuid4().hex[:8]}",
    "payment_id": p1.razorpay_payment_id,
    "amount": 1000000,
    "currency": "INR",
    "status": "processed"
}

with patch('payments.views.get_platform_razorpay_client', return_value=(mock_rzp, 'key_test')):
    client.force_authenticate(user=admin_user)
    res_proc = client.post('/api/payments/refund/process/', {
        "booking_id": b1.booking_id,
        "refund_mode": "ORIGINAL_SOURCE",
        "reason": "Platform approved cancellation refund"
    }, format='json')

assert res_proc.status_code == 200, f"Expected 200, got {res_proc.status_code}: {res_proc.data}"
assert res_proc.data['refund_status'] == Refund.STATUS_REFUNDED
assert res_proc.data['provider_refund_id'].startswith('rfnd_Rzp_')
assert res_proc.data['payout_eligibility'] == False
assert res_proc.data['host_payable_amount'] == 0.00

# Verify DB status
q_refund.refresh_from_db()
assert q_refund.status == Refund.STATUS_REFUNDED
assert q_refund.razorpay_refund_id.startswith('rfnd_Rzp_')
assert q_refund.processed_by == admin_user
print(f"  [PASS] ORIGINAL_SOURCE processed via Razorpay API: Ref ID '{q_refund.razorpay_refund_id}', Status '{q_refund.status}'")


# -------------------------------------------------------------------------
# REQUIREMENT 3: Actual Refund Processing - Method B: CUSTOMER_PAYOUT (RazorpayX)
# -------------------------------------------------------------------------
print("\n--- REQUIREMENT 3: Process Refund via BANK_TRANSFER / UPI (RazorpayX Payout API) ---")
b2 = Booking.objects.create(
    booking_id=f"BK-SYS-REF-{uuid.uuid4().hex[:6].upper()}",
    customer=customer1,
    hotel=hotel,
    room=room,
    check_in=timezone.now().date() + timezone.timedelta(days=10),
    check_out=timezone.now().date() + timezone.timedelta(days=12),
    guest_name="Vikram Singhania",
    guest_email="vikram@example.com",
    guest_phone="9876543210",
    total_amount=Decimal('5000.00'),
    price_per_night=Decimal('2500.00'),
    subtotal=Decimal('5000.00'),
    taxes=Decimal('0.00'),
    booking_status=Booking.STATUS_CANCELLED,
    payment_status=Booking.PAYMENT_REFUND_PENDING,
    refundable_amount=Decimal('5000.00')
)
p2 = Payment.objects.create(
    booking=b2,
    user=customer1,
    razorpay_order_id=f"order_{uuid.uuid4().hex[:10]}",
    razorpay_payment_id=f"pay_{uuid.uuid4().hex[:10]}",
    amount=Decimal('5000.00'),
    status=Payment.STATUS_CAPTURED
)

# 3a. When RazorpayX account is NOT configured -> Must fail gracefully with clear message
setting = PlatformSetting.objects.first() or PlatformSetting.objects.create()
old_rzpx = setting.razorpayx_account_number
setting.razorpayx_account_number = None
setting.save()

client.force_authenticate(user=admin_user)
res_rzpx_fail = client.post('/api/payments/refund/process/', {
    "booking_id": b2.booking_id,
    "refund_mode": "BANK_TRANSFER",
    "account_holder_name": "Vikram Singhania",
    "bank_name": "State Bank of India",
    "account_number": "987654321001",
    "ifsc_code": "SBIN0001234"
}, format='json')

assert res_rzpx_fail.status_code == 400
assert "RazorpayX Current Account is required" in res_rzpx_fail.data['error']
print(f"  [PASS] Unconfigured RazorpayX correctly caught without fake success: {res_rzpx_fail.data['error'][:80]}...")

# 3b. When RazorpayX account IS configured -> Executes Payout workflow
setting.razorpayx_account_number = "787878008031"
setting.save()

mock_rzpx_client = MagicMock()
mock_rzpx_client.contact.create.return_value = {"id": "cont_mock123"}
mock_rzpx_client.fund_account.create.return_value = {"id": "fa_mock456"}
pout_id = f"pout_{uuid.uuid4().hex[:10]}"
mock_rzpx_client.payout.create.return_value = {
    "id": pout_id,
    "status": "processed",
    "amount": 500000,
    "mode": "NEFT"
}

with patch('payments.views.get_platform_razorpay_client', return_value=(mock_rzpx_client, 'key_test')):
    res_rzpx_ok = client.post('/api/payments/refund/process/', {
        "booking_id": b2.booking_id,
        "refund_mode": "BANK_TRANSFER",
        "account_holder_name": "Vikram Singhania",
        "bank_name": "State Bank of India",
        "account_number": "987654321001",
        "ifsc_code": "SBIN0001234"
    }, format='json')

assert res_rzpx_ok.status_code == 200, f"Expected 200, got {res_rzpx_ok.status_code}: {res_rzpx_ok.data}"
assert res_rzpx_ok.data['refund_status'] == Refund.STATUS_REFUNDED
assert res_rzpx_ok.data['payout_reference_id'] == pout_id

ref_b2 = Refund.objects.filter(booking=b2).first()
assert ref_b2.refund_mode == Refund.REFUND_MODE_BANK
assert ref_b2.payout_reference_id == pout_id
print(f"  [PASS] BANK_TRANSFER processed via RazorpayX Payout API: Payout ID '{ref_b2.payout_reference_id}'")


# -------------------------------------------------------------------------
# REQUIREMENT 4: Check Refund Status API
# -------------------------------------------------------------------------
print("\n--- REQUIREMENT 4: Check Refund Status API ---")
client.force_authenticate(user=customer1)
res_stat = client.get(f'/api/payments/refunds/{b1.booking_id}/status/')
assert res_stat.status_code == 200
assert res_stat.data['refund_status'] == Refund.STATUS_REFUNDED
assert res_stat.data['provider_refund_id'].startswith('rfnd_Rzp_')
assert res_stat.data['payout_eligibility'] == False
assert res_stat.data['host_payable_amount'] == 0.00
print(f"  [PASS] Refund Status API returns verified status: {res_stat.data['refund_status']} (Ref: {res_stat.data['provider_refund_id']})")


# -------------------------------------------------------------------------
# REQUIREMENT 5: Host Payout Protection
# -------------------------------------------------------------------------
print("\n--- REQUIREMENT 5: Host Payout Exclusion & Double Payout Prevention ---")
he1.refresh_from_db()
assert he1.status == HostEarning.STATUS_REVERSED, "Host earning must be strictly reversed"
assert "Host payout excluded" in he1.hold_reason

# Attempting to initiate a host payout batch for this cancelled booking must strictly fail
client.force_authenticate(user=admin_user)
res_po_init = client.post('/api/payments/admin/payouts/initiate/', {
    "earning_ids": [he1.id]
}, format='json')
assert res_po_init.status_code == 400
assert "non-payable status" in str(res_po_init.data)
print("  [PASS] Host Payout Protection: Cancelled/refunded booking cannot be included in host payout batch!")


# -------------------------------------------------------------------------
# REQUIREMENT 6: Persistent Idempotency & Safe Retries
# -------------------------------------------------------------------------
print("\n--- REQUIREMENT 6: Persistent Idempotency & Safe Retry API ---")
# 6a. Idempotency Replay on already REFUNDED booking
res_idem = client.post('/api/payments/refund/process/', {
    "booking_id": b1.booking_id
}, format='json')
assert res_idem.status_code == 200
assert "already" in res_idem.data['message'].lower()
assert mock_rzp.payment.refund.call_count == 1, "Provider API must NOT be called again on replay!"
print("  [PASS] Persistent Idempotency: Replaying completed refund returned cached result without duplicate charge!")

# 6b. Safe Retry API on failed refund
b3 = Booking.objects.create(
    booking_id=f"BK-SYS-REF-{uuid.uuid4().hex[:6].upper()}",
    customer=customer1,
    hotel=hotel,
    room=room,
    check_in=timezone.now().date() + timezone.timedelta(days=15),
    check_out=timezone.now().date() + timezone.timedelta(days=17),
    guest_name="Amit Patel",
    total_amount=Decimal('3000.00'),
    price_per_night=Decimal('1500.00'),
    subtotal=Decimal('3000.00'),
    taxes=Decimal('0.00'),
    booking_status=Booking.STATUS_CANCELLED,
    payment_status=Booking.PAYMENT_REFUND_PENDING,
    refundable_amount=Decimal('3000.00')
)
p3 = Payment.objects.create(
    booking=b3,
    user=customer1,
    razorpay_order_id=f"order_{uuid.uuid4().hex[:10]}",
    razorpay_payment_id=f"pay_{uuid.uuid4().hex[:10]}",
    amount=Decimal('3000.00'),
    status=Payment.STATUS_CAPTURED
)
failed_refund = Refund.objects.create(
    booking=b3,
    payment=p3,
    razorpay_payment_id=p3.razorpay_payment_id,
    amount=Decimal('3000.00'),
    status=Refund.STATUS_REFUND_FAILED,
    failure_reason="Temporary gateway timeout",
    retry_count=0
)

# Admin calls POST /api/payments/refunds/<id>/retry/
mock_retry_rzp = MagicMock()
mock_retry_rzp.payment.refund.return_value = {
    "id": f"rfnd_Retry_{uuid.uuid4().hex[:6]}",
    "status": "processed"
}

with patch('payments.views.get_platform_razorpay_client', return_value=(mock_retry_rzp, 'key_test')):
    res_retry = client.post(f'/api/payments/refunds/{b3.booking_id}/retry/', {
        "reason": "Admin safe retry after gateway recovery"
    }, format='json')

assert res_retry.status_code == 200, f"Expected 200, got {res_retry.status_code}: {res_retry.data}"
assert res_retry.data['refund_status'] == Refund.STATUS_REFUNDED
assert res_retry.data['retry_count'] == 1

# Check that NO duplicate row was created
refund_count = Refund.objects.filter(booking=b3).count()
assert refund_count == 1, f"Expected exactly 1 refund record, got {refund_count}"
print(f"  [PASS] Safe Retry API reused existing row (retry_count=1, rows={refund_count}) and confirmed status REFUNDED!")


# -------------------------------------------------------------------------
# REQUIREMENT 7: Admin Refund List Filter Testing
# -------------------------------------------------------------------------
print("\n--- REQUIREMENT 7: Admin Refund Listing with Filters ---")
client.force_authenticate(user=admin_user)

# 7a. Filter by status=REFUNDED
res_filt1 = client.get('/api/payments/admin/refunds/?status=REFUNDED')
assert res_filt1.status_code == 200
results1 = res_filt1.data.get('results', res_filt1.data)
assert all(r['refund_status'] == 'REFUNDED' for r in results1)
print(f"  [PASS] Admin listing filtered by status=REFUNDED: {len(results1)} records found")

# 7b. Filter by booking_id
res_filt2 = client.get(f'/api/payments/admin/refunds/?booking_id={b1.booking_id}')
assert res_filt2.status_code == 200
results2 = res_filt2.data.get('results', res_filt2.data)
assert len(results2) == 1
assert results2[0]['booking_id'] == b1.booking_id
print(f"  [PASS] Admin listing filtered by booking_id={b1.booking_id}: exactly 1 matched record")

# 7c. Filter by refund_mode=BANK_TRANSFER
res_filt3 = client.get('/api/payments/admin/refunds/?refund_mode=BANK_TRANSFER')
assert res_filt3.status_code == 200
results3 = res_filt3.data.get('results', res_filt3.data)
assert all(r['refund_mode'] == 'BANK_TRANSFER' for r in results3)
print(f"  [PASS] Admin listing filtered by refund_mode=BANK_TRANSFER: {len(results3)} records matched")

# Restore setting
setting.razorpayx_account_number = old_rzpx
setting.save()

# Clean up test records
Refund.objects.filter(booking__in=[b1, b2, b3]).delete()
Payment.objects.filter(booking__in=[b1, b2, b3]).delete()
HostEarning.objects.filter(booking__in=[b1, b2, b3]).delete()
Booking.objects.filter(id__in=[b1.id, b2.id, b3.id]).delete()
print("  [CLEANUP] Deleted temporary test bookings, payments, and refund records.")

print("\n==================================================================")
print("ALL 7 REFUND SYSTEM REQUIREMENTS PASSED WITH 100% SUCCESS!")
print("==================================================================")
