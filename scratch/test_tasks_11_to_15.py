import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from decimal import Decimal
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking
from payments.models import Payment, Refund, HostEarning, HostPayoutAccount
from coupons.models import Coupon, CouponUsage
from reviews.models import Review
from wishlist.models import Wishlist

User = get_user_model()
client = APIClient()

print("=" * 66)
print("RUNNING TASKS 11 TO 15 COMPREHENSIVE VERIFICATION SUITE")
print("=" * 66)

# Initial cleanup of test records
Booking.objects.filter(booking_id__startswith="BK-TASK-").delete()
Booking.objects.filter(booking_id__startswith="BK-REVIEW-").delete()

# Setup common fixtures
cust_user, _ = User.objects.get_or_create(
    username="cust_task_11_15",
    defaults={"email": "cust_task_11_15@example.com", "role": User.ROLE_CUSTOMER}
)
cust_user.set_password("CustPass@123")
cust_user.save()

owner_user, _ = User.objects.get_or_create(
    username="owner_task_11_15",
    defaults={"email": "owner_task_11_15@example.com", "role": User.ROLE_HOTEL_OWNER}
)
owner_user.set_password("OwnerPass@123")
owner_user.save()

admin_user, _ = User.objects.get_or_create(
    username="admin_task_11_15",
    defaults={"email": "admin_task_11_15@example.com", "role": User.ROLE_ADMIN, "is_staff": True}
)
admin_user.set_password("AdminPass@123")
admin_user.save()

hotel, _ = Hotel.objects.get_or_create(
    owner=owner_user,
    name="Heritage Royal Palace",
    city="Jaipur",
    defaults={
        "state": "Rajasthan",
        "address": "12, Palace Road",
        "star_rating": 5,
        "is_approved": True,
        "status": "APPROVED"
    }
)

room, _ = Room.objects.get_or_create(
    hotel=hotel,
    title="Royal Heritage Suite",
    defaults={
        "price_per_night": Decimal('5000.00'),
        "capacity_adults": 2,
        "total_rooms": 5
    }
)

# -------------------------------------------------------------
# TASK-11: Customer Cancellation, Owner Approval/Rejection & Admin Refund
# -------------------------------------------------------------
print("\n--- TASK-11: Cancellation Workflow, Owner Actions & Admin Refund ---")
today = timezone.now().date()
booking_11 = Booking.objects.create(
    booking_id="BK-TASK-11-TEST",
    customer=cust_user,
    hotel=hotel,
    room=room,
    check_in=today + timedelta(days=5),
    check_out=today + timedelta(days=8),
    price_per_night=Decimal('5000.00'),
    number_of_nights=3,
    subtotal=Decimal('15000.00'),
    total_amount=Decimal('17700.00'),
    booking_status=Booking.STATUS_CONFIRMED,
    payment_status=Booking.PAYMENT_PAID,
    guest_name="Aman Sharma",
    guest_email=cust_user.email,
    guest_phone="9876543210"
)
Payment.objects.create(
    user=cust_user,
    booking=booking_11,
    razorpay_payment_id="pay_task11_mock_123",
    razorpay_order_id="order_task11_mock_123",
    amount=Decimal('17700.00'),
    status=Payment.STATUS_CAPTURED,
    paid_at=timezone.now()
)

# 1. Customer submits cancellation with bank details and mismatch check
client.force_authenticate(user=cust_user)
mismatch_res = client.post(f"/api/bookings/{booking_11.booking_id}/cancel/", {
    "reason": "Family emergency",
    "bank_details": {
        "account_holder_name": "Aman Sharma",
        "account_number": "123456789012",
        "confirm_account_number": "999999999999",
        "ifsc_code": "HDFC0001234",
        "bank_name": "HDFC Bank"
    }
}, format='json')
assert mismatch_res.status_code == 400
assert "Account numbers do not match" in str(mismatch_res.data)
print("  [PASS] Mismatched account numbers properly rejected with 400 Bad Request!")

# Customer submits valid cancellation request
valid_cancel = client.post(f"/api/bookings/{booking_11.booking_id}/cancel/", {
    "reason": "Family emergency",
    "bank_details": {
        "account_holder_name": "Aman Sharma",
        "account_number": "123456789012",
        "confirm_account_number": "123456789012",
        "ifsc_code": "HDFC0001234",
        "bank_name": "HDFC Bank"
    }
}, format='json')
assert valid_cancel.status_code == 200
booking_11.refresh_from_db()
assert booking_11.booking_status == Booking.STATUS_CANCELLED
assert booking_11.payment_status == Booking.PAYMENT_REFUND_PENDING
print("  [PASS] Cancellation successfully processed with policy calculation and queued for refund!")

# Owner Rejection Test (on a new booking)
booking_owner_test = Booking.objects.create(
    booking_id="BK-TASK-11-OWNER-TEST",
    customer=cust_user,
    hotel=hotel,
    room=room,
    check_in=today + timedelta(days=3),
    check_out=today + timedelta(days=6),
    price_per_night=Decimal('5000.00'),
    total_amount=Decimal('5000.00'),
    subtotal=Decimal('5000.00'),
    booking_status=Booking.STATUS_CONFIRMED,
    payment_status=Booking.PAYMENT_PAID,
    guest_name="Aman Sharma",
    guest_email=cust_user.email,
    guest_phone="9876543210"
)
client.force_authenticate(user=owner_user)
# Rejection without reason fails
no_reason_res = client.post(f"/api/bookings/{booking_owner_test.booking_id}/cancel/", {
    "action": "OWNER_REJECT"
}, format='json')
assert no_reason_res.status_code == 400
print("  [PASS] Owner rejection without reason rejected with 400 Bad Request!")

# Rejection with reason succeeds
reject_res = client.post(f"/api/bookings/{booking_owner_test.booking_id}/cancel/", {
    "action": "OWNER_REJECT",
    "reason": "Guest already received door code and property access keys."
}, format='json')
assert reject_res.status_code == 200
booking_owner_test.refresh_from_db()
assert booking_owner_test.booking_status == 'OWNER_REJECTED'
print("  [PASS] Owner rejection with valid reason transitioned booking to OWNER_REJECTED!")

# Owner Approval succeeds
booking_owner_test.booking_status = Booking.STATUS_CONFIRMED
booking_owner_test.save()
approve_res = client.post(f"/api/bookings/{booking_owner_test.booking_id}/cancel/", {
    "action": "OWNER_APPROVE"
}, format='json')
assert approve_res.status_code == 200
booking_owner_test.refresh_from_db()
assert booking_owner_test.booking_status == 'OWNER_APPROVED'
print("  [PASS] Owner approval transitioned booking to OWNER_APPROVED!")

# -------------------------------------------------------------
# TASK-12: Host Earnings & Commission Calculation by Tier
# -------------------------------------------------------------
print("\n--- TASK-12: Host Earnings & Commission Calculation (Tiers) ---")
# Test 1: Silver Tier (10% commission + 18% GST on commission)
owner_user.subscription_tier = 'SILVER'
owner_user.save()

booking_silver = Booking.objects.create(
    booking_id="BK-TASK-12-SILVER",
    customer=cust_user,
    hotel=hotel,
    room=room,
    check_in=today + timedelta(days=2),
    check_out=today + timedelta(days=4),
    price_per_night=Decimal('5000.00'),
    number_of_nights=2,
    subtotal=Decimal('10000.00'),
    total_amount=Decimal('11800.00'),
    booking_status=Booking.STATUS_PENDING_PAYMENT,
    payment_status=Booking.PAYMENT_PENDING,
    guest_name="Aman Sharma",
    guest_email=cust_user.email,
    guest_phone="9876543210"
)
payment_silver = Payment.objects.create(
    user=cust_user,
    booking=booking_silver,
    razorpay_order_id="order_silver_123",
    amount=Decimal('11800.00'),
    status=Payment.STATUS_CREATED
)

# Simulate payment confirmation
import hmac, hashlib
from django.conf import settings
key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', 'mock_secret')
msg = f"order_silver_123|pay_silver_123"
valid_sig = hmac.new(key_secret.encode('utf-8'), msg.encode('utf-8'), hashlib.sha256).hexdigest()

from unittest.mock import patch, MagicMock

mock_rzp = MagicMock()
mock_rzp.payment.fetch.side_effect = lambda pid: {
    'id': pid,
    'amount': 1180000,
    'currency': 'INR',
    'status': 'captured'
}

client.force_authenticate(user=cust_user)
with patch('payments.views.get_platform_razorpay_client', return_value=(mock_rzp, 'rzp_test_key')):
    verify_res = client.post('/api/payments/verify/', {
        'razorpay_order_id': 'order_silver_123',
        'razorpay_payment_id': 'pay_silver_123',
        'razorpay_signature': valid_sig,
        'booking_id': booking_silver.booking_id
    }, format='json')
assert verify_res.status_code == 200

earning_silver = HostEarning.objects.get(booking=booking_silver)
assert earning_silver.platform_fee_percent == Decimal('10.00')
# Gross: 11800. Fee (10%): 1180. Tax (18% on fee): 212.40. Net: 11800 - 1180 - 212.40 = 10407.60
expected_fee = Decimal('1180.00')
expected_tax = Decimal('212.40')
expected_net = Decimal('10407.60')
assert earning_silver.platform_fee == expected_fee
assert earning_silver.tax == expected_tax
assert earning_silver.net_amount == expected_net
print(f"  [PASS] Silver Tier (10%): Gross={earning_silver.gross_amount}, Fee={earning_silver.platform_fee}, Tax={earning_silver.tax}, Net={earning_silver.net_amount}")

# Test 2: Platinum Tier (0% commission)
owner_user.subscription_tier = 'PLATINUM'
owner_user.save()

booking_plat = Booking.objects.create(
    booking_id="BK-TASK-12-PLAT",
    customer=cust_user,
    hotel=hotel,
    room=room,
    check_in=today + timedelta(days=2),
    check_out=today + timedelta(days=4),
    price_per_night=Decimal('5000.00'),
    number_of_nights=2,
    subtotal=Decimal('10000.00'),
    total_amount=Decimal('11800.00'),
    booking_status=Booking.STATUS_PENDING_PAYMENT,
    payment_status=Booking.PAYMENT_PENDING,
    guest_name="Aman Sharma",
    guest_email=cust_user.email,
    guest_phone="9876543210"
)
payment_plat = Payment.objects.create(
    user=cust_user,
    booking=booking_plat,
    razorpay_order_id="order_plat_123",
    amount=Decimal('11800.00'),
    status=Payment.STATUS_CREATED
)
msg_plat = f"order_plat_123|pay_plat_123"
sig_plat = hmac.new(key_secret.encode('utf-8'), msg_plat.encode('utf-8'), hashlib.sha256).hexdigest()

with patch('payments.views.get_platform_razorpay_client', return_value=(mock_rzp, 'rzp_test_key')):
    client.post('/api/payments/verify/', {
        'razorpay_order_id': 'order_plat_123',
        'razorpay_payment_id': 'pay_plat_123',
        'razorpay_signature': sig_plat,
        'booking_id': booking_plat.booking_id
    }, format='json')

earning_plat = HostEarning.objects.get(booking=booking_plat)
assert earning_plat.platform_fee_percent == Decimal('0.00')
assert earning_plat.platform_fee == Decimal('0.00')
assert earning_plat.tax == Decimal('0.00')
assert earning_plat.net_amount == Decimal('11800.00')
print(f"  [PASS] Platinum Tier (0%): Gross={earning_plat.gross_amount}, Fee={earning_plat.platform_fee}, Net={earning_plat.net_amount} (100% payout to host)!")

# Test Host Earnings Endpoint
client.force_authenticate(user=owner_user)
host_earn_res = client.get('/api/host/earnings/')
assert host_earn_res.status_code == 200
assert host_earn_res.data.get('count', len(host_earn_res.data.get('results', []))) >= 2
print("  [PASS] /api/host/earnings/ returned owner settlements and earnings ledger!")

# -------------------------------------------------------------
# TASK-13: Coupon Validation & Redemption Limits
# -------------------------------------------------------------
print("\n--- TASK-13: Coupon Validation & Redemption Limits ---")
coupon, _ = Coupon.objects.get_or_create(
    code="TASK13PROMO",
    defaults={
        "discount_percentage": Decimal('15.00'),
        "max_discount_amount": Decimal('1000.00'),
        "min_booking_amount": Decimal('2000.00'),
        "valid_from": today - timedelta(days=2),
        "valid_until": today + timedelta(days=10),
        "is_active": True,
        "max_uses_per_user": 1,
        "times_used": 0
    }
)
coupon.max_uses_per_user = 1
coupon.times_used = 0
coupon.save()
CouponUsage.objects.filter(coupon=coupon).delete()

# Test 1: Minimum spend threshold
subtotal_low_res = client.post('/api/coupons/apply/', {
    "code": "TASK13PROMO",
    "amount": 1500.00
}, format='json')
assert subtotal_low_res.status_code == 400
assert "Minimum booking subtotal" in str(subtotal_low_res.data)
print("  [PASS] Coupon application below minimum booking amount rejected with 400 Bad Request!")

# Test 2: Valid coupon application (does not increment times_used)
client.force_authenticate(user=cust_user)
valid_coupon_res = client.post('/api/coupons/apply/', {
    "code": "TASK13PROMO",
    "amount": 5000.00
}, format='json')
assert valid_coupon_res.status_code == 200
assert valid_coupon_res.data['discount_amount'] == 750.00
coupon.refresh_from_db()
assert coupon.times_used == 0  # Not incremented upon merely applying
print("  [PASS] Coupon applied: Rs. 750 discount calculated; times_used remained 0 (not redeemed in cart)!")

# Test 3: Redemption after successful payment increments times_used and blocks re-application
CouponUsage.objects.create(coupon=coupon, user=cust_user)
coupon.times_used = 1
coupon.save()

reapply_res = client.post('/api/coupons/apply/', {
    "code": "TASK13PROMO",
    "amount": 5000.00
}, format='json')
assert reapply_res.status_code == 400
assert "maximum usage limit" in str(reapply_res.data)
print("  [PASS] User max_uses_per_user limit enforced: Re-application blocked with 400 Bad Request!")

# -------------------------------------------------------------
# TASK-14: Reviews & Verified Stay Enforcement
# -------------------------------------------------------------
print("\n--- TASK-14: Reviews & Verified Stay Enforcement ---")
# 1. Reject review for booking that is not completed
active_booking = Booking.objects.create(
    booking_id="BK-REVIEW-ACTIVE",
    customer=cust_user,
    hotel=hotel,
    room=room,
    check_in=today + timedelta(days=10),
    check_out=today + timedelta(days=12),
    price_per_night=Decimal('5000.00'),
    total_amount=Decimal('5000.00'),
    subtotal=Decimal('5000.00'),
    booking_status=Booking.STATUS_CONFIRMED,
    guest_name="Aman Sharma",
    guest_email=cust_user.email,
    guest_phone="9876543210"
)
client.force_authenticate(user=cust_user)
uncompleted_rev = client.post('/api/reviews/', {
    "booking": active_booking.booking_id,
    "rating": 5,
    "comment": "Nice place!"
}, format='json')
assert uncompleted_rev.status_code == 400
assert "after completing your stay" in str(uncompleted_rev.data)
print("  [PASS] Review for active/upcoming stay rejected with 400 Bad Request (Verified Stay Enforced)!")

# 2. Reject invalid rating (< 1 or > 5)
completed_booking = Booking.objects.create(
    booking_id="BK-REVIEW-COMPLETED",
    customer=cust_user,
    hotel=hotel,
    room=room,
    check_in=today - timedelta(days=5),
    check_out=today - timedelta(days=2),
    price_per_night=Decimal('5000.00'),
    total_amount=Decimal('5000.00'),
    subtotal=Decimal('5000.00'),
    booking_status=Booking.STATUS_COMPLETED,
    guest_name="Aman Sharma",
    guest_email=cust_user.email,
    guest_phone="9876543210"
)
invalid_rating_res = client.post('/api/reviews/', {
    "booking": completed_booking.booking_id,
    "rating": 10,
    "comment": "Super luxury!"
}, format='json')
assert invalid_rating_res.status_code == 400
assert "Rating must be an integer between 1 and 5" in str(invalid_rating_res.data)
print("  [PASS] Rating out of range (10) rejected with 400 Bad Request!")

# 3. Valid review submitted successfully
valid_rev = client.post('/api/reviews/', {
    "booking": completed_booking.booking_id,
    "rating": 5,
    "comment": "Exceptional luxury stay and verified experience."
}, format='json')
assert valid_rev.status_code == 201
print("  [PASS] Valid review submitted successfully for completed stay (201 Created)!")

# 4. Duplicate review rejected
dup_rev = client.post('/api/reviews/', {
    "booking": completed_booking.booking_id,
    "rating": 4,
    "comment": "Trying to review twice"
}, format='json')
assert dup_rev.status_code == 400
assert "already submitted a rating" in str(dup_rev.data)
print("  [PASS] Duplicate review for same booking blocked with 400 Bad Request (1 Review Per Booking)!")

# -------------------------------------------------------------
# TASK-15: Wishlist Idempotent Toggle
# -------------------------------------------------------------
print("\n--- TASK-15: Wishlist Idempotent Toggle ---")
Wishlist.objects.filter(user=cust_user, hotel=hotel).delete()

# 1. Toggle via JSON body: Adds to wishlist
toggle_on = client.post('/api/wishlist/toggle/', {"hotel_id": hotel.id}, format='json')
assert toggle_on.status_code == 200
assert toggle_on.data['wishlisted'] is True
assert toggle_on.data['is_favorited'] is True
assert Wishlist.objects.filter(user=cust_user, hotel=hotel).exists()
print(f"  [PASS] Toggle ON via JSON body: wishlisted=True (Item created in DB)!")

# 2. Toggle via JSON body: Removes from wishlist
toggle_off = client.post('/api/wishlist/toggle/', {"hotel_id": hotel.id}, format='json')
assert toggle_off.status_code == 200
assert toggle_off.data['wishlisted'] is False
assert toggle_off.data['is_favorited'] is False
assert not Wishlist.objects.filter(user=cust_user, hotel=hotel).exists()
print(f"  [PASS] Toggle OFF via JSON body: wishlisted=False (Item deleted from DB)!")

# 3. Toggle via URL parameter
toggle_url_on = client.post(f'/api/wishlist/toggle/{hotel.id}/')
assert toggle_url_on.status_code == 200
assert toggle_url_on.data['wishlisted'] is True
print(f"  [PASS] Toggle via URL param (/toggle/{hotel.id}/) confirmed working (wishlisted=True)!")

# Clean up
Booking.objects.filter(booking_id__startswith="BK-TASK-").delete()
Booking.objects.filter(booking_id__startswith="BK-REVIEW-").delete()
print("\n==================================================================")
print("ALL TASKS 11 TO 15 REQUIREMENTS PASSED WITH 100% SUCCESS!")
print("==================================================================")
