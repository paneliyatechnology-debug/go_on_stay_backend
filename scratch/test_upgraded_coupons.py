import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking
from coupons.models import Coupon, CouponUsage
from payments.models import Payment

User = get_user_model()
client = APIClient()

print("=" * 72)
print("RUNNING ADVANCED COUPON SYSTEM UPGRADE VERIFICATION SUITE")
print("=" * 72)

# Cleanup existing test fixtures
Coupon.objects.filter(code__in=[
    "TEST_NEW_USER", "TEST_EXISTING", "TEST_SUMMER", "TEST_DIWALI", "TEST_ADMIN_TOGGLE", "TEST_PAY_REDEEM"
]).delete()
User.objects.filter(username__in=["coup_guest_new", "coup_admin_user"]).delete()

# Create test users
new_guest = User.objects.create_user(
    username="coup_guest_new",
    email="coup_guest_new@example.com",
    role=User.ROLE_CUSTOMER
)
new_guest.set_password("GuestPass@123")
new_guest.save()

admin_user = User.objects.create_user(
    username="coup_admin_user",
    email="coup_admin_user@example.com",
    role=User.ROLE_ADMIN,
    is_staff=True
)
admin_user.set_password("AdminPass@123")
admin_user.save()

owner_user, _ = User.objects.get_or_create(
    username="coup_owner_hotel",
    defaults={"email": "coup_owner_hotel@example.com", "role": User.ROLE_HOTEL_OWNER}
)

hotel, _ = Hotel.objects.get_or_create(
    owner=owner_user,
    name="Coupon Test Resort",
    defaults={"city": "Udaipur", "state": "Rajasthan", "address": "1 Lake View", "status": Hotel.STATUS_APPROVED}
)

room, _ = Room.objects.get_or_create(
    hotel=hotel,
    title="Deluxe Coupon Suite",
    defaults={"price_per_night": Decimal("4000.00"), "total_rooms": 5, "room_type": "DELUXE"}
)

today = timezone.now().date()

# ----------------------------------------------------------------------
# 1. New user vs existing user eligibility & First booking detection
# ----------------------------------------------------------------------
print("\n--- 1 & 2: New User vs Existing User Eligibility & First Booking Detection ---")

c_new = Coupon.objects.create(
    code="TEST_NEW_USER",
    discount_percentage=Decimal("20.00"),
    max_discount_amount=Decimal("1500.00"),
    min_booking_amount=Decimal("2000.00"),
    valid_from=today - timedelta(days=1),
    valid_until=today + timedelta(days=30),
    user_type_eligibility=Coupon.ELIGIBILITY_NEW_USER,
    is_first_booking_only=True,
    campaign_type=Coupon.CAMPAIGN_FIRST_BOOKING,
    title="Welcome First Booking Offer",
    is_active=True
)

c_exist = Coupon.objects.create(
    code="TEST_EXISTING",
    discount_percentage=Decimal("15.00"),
    max_discount_amount=Decimal("2000.00"),
    min_booking_amount=Decimal("2000.00"),
    valid_from=today - timedelta(days=1),
    valid_until=today + timedelta(days=30),
    user_type_eligibility=Coupon.ELIGIBILITY_EXISTING_USER,
    title="Loyal Member Exclusive",
    is_active=True
)

# Step A: new_guest currently has 0 paid bookings
client.force_authenticate(user=new_guest)

# New user applies TEST_NEW_USER -> Should Succeed
res_new_apply = client.post('/api/coupons/apply/', {"code": "TEST_NEW_USER", "amount": 5000})
assert res_new_apply.status_code == status.HTTP_200_OK
assert res_new_apply.data["valid"] is True
assert res_new_apply.data["discount_amount"] == 1000.0  # 20% of 5000 = 1000
assert res_new_apply.data["is_first_booking_only"] is True
print("  [PASS] New user successfully applied first-booking welcome coupon (HTTP 200).")

# New user applies TEST_EXISTING -> Should be Rejected (requires repeat customer)
res_exist_fail = client.post('/api/coupons/apply/', {"code": "TEST_EXISTING", "amount": 5000})
assert res_exist_fail.status_code == status.HTTP_400_BAD_REQUEST
assert "reserved for existing customers" in res_exist_fail.data.get("error", "")
print("  [PASS] New user blocked from applying existing-member-only coupon (HTTP 400).")

# Step B: Now new_guest completes a successful booking
b_completed = Booking.objects.create(
    booking_id="BK-COUP-COMPLETED-01",
    customer=new_guest,
    hotel=hotel,
    room=room,
    check_in=today + timedelta(days=5),
    check_out=today + timedelta(days=7),
    number_of_nights=2,
    subtotal=Decimal("8000.00"),
    total_amount=Decimal("8000.00"),
    price_per_night=Decimal("4000.00"),
    guest_name="Guest Test",
    guest_email=new_guest.email,
    guest_phone="9876543210",
    booking_status=Booking.STATUS_CONFIRMED,
    payment_status=Booking.PAYMENT_PAID
)

# Now new_guest has 1 paid booking -> Is now an Existing User
# Applying TEST_NEW_USER again should now be REJECTED
res_new_now_fail = client.post('/api/coupons/apply/', {"code": "TEST_NEW_USER", "amount": 5000})
assert res_new_now_fail.status_code == status.HTTP_400_BAD_REQUEST
assert "exclusively for new users" in res_new_now_fail.data.get("error", "")
print("  [PASS] Once user has a paid booking, first-booking coupon is strictly rejected (HTTP 400).")

# Applying TEST_EXISTING should now SUCCEED
res_exist_success = client.post('/api/coupons/apply/', {"code": "TEST_EXISTING", "amount": 5000})
assert res_exist_success.status_code == status.HTTP_200_OK
assert res_exist_success.data["valid"] is True
assert res_exist_success.data["discount_amount"] == 750.0  # 15% of 5000 = 750
print("  [PASS] Existing user with prior completed stay successfully applied repeat customer coupon (HTTP 200).")

# ----------------------------------------------------------------------
# 3. Seasonal campaign validity
# ----------------------------------------------------------------------
print("\n--- 3: Seasonal Campaign Validity ---")

season_start = today + timedelta(days=30)
season_end = today + timedelta(days=60)

c_summer = Coupon.objects.create(
    code="TEST_SUMMER",
    discount_percentage=Decimal("25.00"),
    max_discount_amount=Decimal("2500.00"),
    min_booking_amount=Decimal("3000.00"),
    valid_from=today - timedelta(days=1),
    valid_until=today + timedelta(days=90),
    campaign_type=Coupon.CAMPAIGN_SEASONAL,
    campaign_name="Summer Vacation 2026",
    stay_checkin_from=season_start,
    stay_checkin_until=season_end,
    title="Summer Getaway 25% OFF",
    is_active=True
)

# Apply with stay check-in before the seasonal window -> Should be Rejected
bad_stay_date = str(today + timedelta(days=10))
res_season_bad = client.post('/api/coupons/apply/', {
    "code": "TEST_SUMMER",
    "amount": 6000,
    "check_in": bad_stay_date
})
assert res_season_bad.status_code == status.HTTP_400_BAD_REQUEST
assert "check-in from" in str(res_season_bad.data)
print("  [PASS] Stay date outside seasonal campaign window correctly rejected (HTTP 400).")

# Apply with stay check-in inside the seasonal window -> Should Succeed
good_stay_date = str(today + timedelta(days=40))
res_season_good = client.post('/api/coupons/apply/', {
    "code": "TEST_SUMMER",
    "amount": 6000,
    "check_in": good_stay_date
})
assert res_season_good.status_code == status.HTTP_200_OK
assert res_season_good.data["valid"] is True
assert res_season_good.data["discount_amount"] == 1500.0  # 25% of 6000 = 1500
assert res_season_good.data["campaign_type"] == "SEASONAL"
print("  [PASS] Stay date within seasonal campaign window successfully applied (HTTP 200).")

# ----------------------------------------------------------------------
# 4. Festive / event-based campaign validity
# ----------------------------------------------------------------------
print("\n--- 4: Festive / Event-Based Campaign Validity ---")

c_diwali = Coupon.objects.create(
    code="TEST_DIWALI",
    discount_percentage=Decimal("30.00"),
    max_discount_amount=Decimal("3000.00"),
    min_booking_amount=Decimal("4000.00"),
    valid_from=today - timedelta(days=2),
    valid_until=today + timedelta(days=10),
    campaign_type=Coupon.CAMPAIGN_FESTIVE,
    campaign_name="Diwali Dhamaka Celebration",
    title="Grand Festive 30% Savings",
    description="Celebrate with family and enjoy 30% OFF up to Rs 3000 on luxury hotels.",
    is_active=True
)

res_diwali = client.post('/api/coupons/apply/', {"code": "TEST_DIWALI", "amount": 8000})
assert res_diwali.status_code == status.HTTP_200_OK
assert res_diwali.data["valid"] is True
assert res_diwali.data["campaign_type"] == "FESTIVE"
assert res_diwali.data["campaign_name"] == "Diwali Dhamaka Celebration"
assert res_diwali.data["discount_amount"] == 2400.0  # 30% of 8000 = 2400
print("  [PASS] Festive campaign applied returning festival metadata, campaign name & calculated discount.")

# ----------------------------------------------------------------------
# 5. Admin-controlled coupon activation
# ----------------------------------------------------------------------
print("\n--- 5: Admin-Controlled Coupon Activation ---")

c_admin = Coupon.objects.create(
    code="TEST_ADMIN_TOGGLE",
    discount_percentage=Decimal("10.00"),
    max_discount_amount=Decimal("500.00"),
    min_booking_amount=Decimal("1000.00"),
    valid_from=today - timedelta(days=1),
    valid_until=today + timedelta(days=30),
    is_active=True
)

# Non-admin user attempts to toggle status -> 403 Forbidden
client.force_authenticate(user=new_guest)
res_toggle_forbidden = client.post(f'/api/coupons/{c_admin.id}/toggle-status/')
assert res_toggle_forbidden.status_code == status.HTTP_403_FORBIDDEN
print("  [PASS] Non-admin user forbidden (HTTP 403) from toggling coupon status.")

# Admin toggles coupon to DEACTIVATED
client.force_authenticate(user=admin_user)
res_toggle_deactivate = client.post(f'/api/coupons/{c_admin.id}/toggle-status/')
assert res_toggle_deactivate.status_code == status.HTTP_200_OK
assert res_toggle_deactivate.data["is_active"] is False
c_admin.refresh_from_db()
assert c_admin.is_active is False
print("  [PASS] Admin successfully deactivated coupon via POST /api/coupons/<id>/toggle-status/.")

# User tries to apply deactivated coupon -> 400 Bad Request
client.force_authenticate(user=new_guest)
res_apply_deactivated = client.post('/api/coupons/apply/', {"code": "TEST_ADMIN_TOGGLE", "amount": 2000})
assert res_apply_deactivated.status_code == status.HTTP_400_BAD_REQUEST
assert "deactivated" in res_apply_deactivated.data.get("error", "").lower()
print("  [PASS] Deactivated coupon rejected at application endpoint (HTTP 400).")

# Admin toggles coupon back to ACTIVATED
client.force_authenticate(user=admin_user)
res_toggle_activate = client.post(f'/api/coupons/{c_admin.id}/toggle-status/')
assert res_toggle_activate.status_code == status.HTTP_200_OK
assert res_toggle_activate.data["is_active"] is True
c_admin.refresh_from_db()
assert c_admin.is_active is True
print("  [PASS] Admin successfully re-activated coupon.")

# ----------------------------------------------------------------------
# 6. Available coupons API
# ----------------------------------------------------------------------
print("\n--- 6: Available Coupons API (Personalized & Filtered) ---")

client.force_authenticate(user=new_guest)
res_avail = client.get('/api/coupons/available/?amount=5000')
assert res_avail.status_code == status.HTTP_200_OK
coupons_list = res_avail.data.get("available_coupons", [])
assert len(coupons_list) >= 3

# Verify each returned item has is_eligible, campaign_type, potential_discount
for coup_item in coupons_list:
    assert "code" in coup_item
    assert "is_eligible" in coup_item
    assert "campaign_type" in coup_item
    assert "potential_discount" in coup_item
    if coup_item["code"] == "TEST_NEW_USER":
        # new_guest has a paid booking, so this should be ineligible
        assert coup_item["is_eligible"] is False
        assert coup_item["reason_ineligible"] is not None
    elif coup_item["code"] == "TEST_EXISTING":
        # new_guest is an existing user, so this should be eligible
        assert coup_item["is_eligible"] is True
        assert coup_item["reason_ineligible"] is None

print(f"  [PASS] GET /api/coupons/available/ returned {len(coupons_list)} personalized coupons with eligibility tags.")

# ----------------------------------------------------------------------
# 7 & 8: Payment success redemption & duplicate/concurrent prevention
# ----------------------------------------------------------------------
print("\n--- 7 & 8: Payment Success Redemption & Duplicate Prevention ---")

c_pay = Coupon.objects.create(
    code="TEST_PAY_REDEEM",
    discount_percentage=Decimal("10.00"),
    max_discount_amount=Decimal("1000.00"),
    min_booking_amount=Decimal("2000.00"),
    valid_from=today - timedelta(days=1),
    valid_until=today + timedelta(days=30),
    max_uses_per_user=1,
    times_used=0,
    is_active=True
)

# Applying in cart does NOT increment times_used (Rule 7)
client.force_authenticate(user=new_guest)
res_cart_apply = client.post('/api/coupons/apply/', {"code": "TEST_PAY_REDEEM", "amount": 5000})
assert res_cart_apply.status_code == status.HTTP_200_OK
c_pay.refresh_from_db()
assert c_pay.times_used == 0
assert CouponUsage.objects.filter(coupon=c_pay).count() == 0
print("  [PASS] Cart application validates coupon but DOES NOT increment times_used (0 redemptions).")

# Create a booking with this coupon in price_snapshot
b_pay = Booking.objects.create(
    booking_id="BK-COUP-PAY-VERIFY-01",
    customer=new_guest,
    hotel=hotel,
    room=room,
    check_in=today + timedelta(days=15),
    check_out=today + timedelta(days=18),
    number_of_nights=3,
    subtotal=Decimal("12000.00"),
    discount=Decimal("1000.00"),
    total_amount=Decimal("11000.00"),
    price_per_night=Decimal("4000.00"),
    guest_name="Guest Pay Test",
    guest_email=new_guest.email,
    guest_phone="9876543210",
    price_snapshot={"coupon_code": "TEST_PAY_REDEEM", "discount": 1000.0},
    booking_status=Booking.STATUS_PENDING_PAYMENT,
    payment_status=Booking.PAYMENT_PENDING
)

# Simulate payment success in VerifyPaymentView
import hmac, hashlib
from django.conf import settings
from unittest.mock import patch, MagicMock

order_id = "order_test_coup_101"
payment_id = "pay_test_coup_202"
secret = getattr(settings, 'RAZORPAY_KEY_SECRET', 'test_secret')
msg = f"{order_id}|{payment_id}".encode('utf-8')
valid_sig = hmac.new(secret.encode('utf-8'), msg, hashlib.sha256).hexdigest()

b_pay.razorpay_order_id = order_id
b_pay.save()

mock_rzp = MagicMock()
mock_rzp.payment.fetch.side_effect = lambda pid: {
    'id': pid,
    'amount': 1100000,
    'currency': 'INR',
    'status': 'captured'
}

with patch('payments.views.get_platform_razorpay_client', return_value=(mock_rzp, 'rzp_test_key')):
    res_verify = client.post('/api/payments/verify/', {
        "booking_id": b_pay.booking_id,
        "razorpay_order_id": order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": valid_sig
    }, format='json')
assert res_verify.status_code == status.HTTP_200_OK

# Check that times_used incremented by 1 AFTER payment confirmation
c_pay.refresh_from_db()
assert c_pay.times_used == 1
usage_rec = CouponUsage.objects.filter(coupon=c_pay, booking=b_pay).first()
assert usage_rec is not None
assert usage_rec.user == new_guest
assert usage_rec.discount_applied == Decimal("1000.00")
print("  [PASS] Payment verification confirmed: times_used incremented to 1 & CouponUsage created.")

# Rule 8: Replay attack / duplicate webhook arrival for same booking -> Must NOT increment times_used again
with patch('payments.views.get_platform_razorpay_client', return_value=(mock_rzp, 'rzp_test_key')):
    res_verify_replay = client.post('/api/payments/verify/', {
        "booking_id": b_pay.booking_id,
        "razorpay_order_id": order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": valid_sig
    }, format='json')

c_pay.refresh_from_db()
assert c_pay.times_used == 1, f"Expected times_used=1 on replay, but got {c_pay.times_used}"
assert CouponUsage.objects.filter(coupon=c_pay, booking=b_pay).count() == 1
print("  [PASS] Duplicate payment confirmation replayed: times_used remained 1 without double-counting.")

# User attempts to use coupon on a 2nd new booking -> Must be blocked by max_uses_per_user=1
res_second_booking = client.post('/api/coupons/apply/', {"code": "TEST_PAY_REDEEM", "amount": 5000})
assert res_second_booking.status_code == status.HTTP_400_BAD_REQUEST
assert "maximum usage limit" in res_second_booking.data.get("error", "").lower()
print("  [PASS] User subsequent redemption on 2nd booking blocked by max_uses_per_user limit (HTTP 400).")

print("\n" + "=" * 72)
print("ALL 8 ADVANCED COUPON RULES PASSED COMPLETELY & FLAWLESSLY!")
print("=" * 72)
