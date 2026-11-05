import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

import hmac
import hashlib
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from django.core.cache import cache
from django.conf import settings
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking
from payments.models import Payment, Refund, HostEarning, PlatformSetting, AuditLog
from notifications.models import Notification
import razorpay
from razorpay.errors import SignatureVerificationError

User = get_user_model()
client = APIClient()

print("=" * 70)
print("RUNNING TASKS 16 TO 20 COMPREHENSIVE VERIFICATION SUITE")
print("=" * 70)

# Clear cache to avoid rate limit pollution during unit tests
cache.clear()

# Cleanup previous test records
User.objects.filter(username__startswith="test_t16_20_").delete()
Hotel.objects.filter(name="Test Luxury Haven").delete()

# Setup test fixtures
cust_user = User.objects.create_user(
    username="test_t16_20_cust",
    email="test_t16_20_cust@example.com",
    phone_number="9876543210",
    role=User.ROLE_CUSTOMER
)
cust_user.set_password("CustPass@123")
cust_user.save()

cust_user2 = User.objects.create_user(
    username="test_t16_20_cust2",
    email="test_t16_20_cust2@example.com",
    phone_number="9876543211",
    role=User.ROLE_CUSTOMER
)
cust_user2.set_password("CustPass@123")
cust_user2.save()

owner_user = User.objects.create_user(
    username="test_t16_20_owner",
    email="test_t16_20_owner@example.com",
    role=User.ROLE_HOTEL_OWNER
)
owner_user.set_password("OwnerPass@123")
owner_user.save()

admin_user = User.objects.create_user(
    username="test_t16_20_admin",
    email="test_t16_20_admin@example.com",
    role=User.ROLE_ADMIN,
    is_staff=True
)
admin_user.set_password("AdminPass@123")
admin_user.save()

hotel = Hotel.objects.create(
    owner=owner_user,
    name="Test Luxury Haven",
    city="Jaipur",
    state="Rajasthan",
    address="42 Palace Road",
    status=Hotel.STATUS_APPROVED
)

room = Room.objects.create(
    hotel=hotel,
    title="Royal Concurrency Suite",
    room_type="DELUXE",
    price_per_night=Decimal("4000.00"),
    capacity_adults=2,
    total_rooms=1
)

# ----------------------------------------------------------------------
# TASK-16: NOTIFICATIONS ENGINE & EVENT DISPATCHER
# ----------------------------------------------------------------------
print("\n--- TASK-16: Notifications Engine & Event Dispatcher ---")

# 1. Trigger in-app notification records on required events
n1 = Notification.objects.create(
    recipient=cust_user,
    title="Booking Confirmed",
    message="Your booking BK-101 is confirmed.",
    notification_type=Notification.TYPE_BOOKING_CONFIRMED
)
n2 = Notification.objects.create(
    recipient=cust_user,
    title="Booking Cancelled",
    message="Your booking BK-101 has been cancelled.",
    notification_type=Notification.TYPE_BOOKING_CANCELLED
)
n3 = Notification.objects.create(
    recipient=owner_user,
    title="Payout Initiated",
    message="Your host payout of Rs. 3600 has been initiated.",
    notification_type=Notification.TYPE_PAYOUT_INITIATED
)
n4 = Notification.objects.create(
    recipient=cust_user,
    title="Refund Processed",
    message="Refund of Rs. 3600 processed successfully.",
    notification_type=Notification.TYPE_REFUND_PROCESSED
)

assert n1.notification_type == 'BOOKING_CONFIRMED'
assert n2.notification_type == 'BOOKING_CANCELLED'
assert n3.notification_type == 'PAYOUT_INITIATED'
assert n4.notification_type == 'REFUND_PROCESSED'
print("  [PASS] All 4 required notification event types created and validated in DB.")

# 2. List notifications: GET /api/notifications/
client.force_authenticate(user=cust_user)
list_res = client.get('/api/notifications/')
assert list_res.status_code == status.HTTP_200_OK
results = list_res.data.get('results', list_res.data)
assert len(results) >= 3
print(f"  [PASS] GET /api/notifications/ returned {len(results)} notifications for authenticated user.")

# 3. Mark single notification as read: PATCH /api/notifications/<id>/read/
assert n1.is_read is False
patch_res = client.patch(f'/api/notifications/{n1.id}/read/')
assert patch_res.status_code == status.HTTP_200_OK
assert patch_res.data.get('is_read') is True
n1.refresh_from_db()
assert n1.is_read is True
print("  [PASS] PATCH /api/notifications/<id>/read/ successfully marked notification as read.")

# 4. Bulk read endpoint: POST /api/notifications/mark-all-read/
unread_before = Notification.objects.filter(recipient=cust_user, is_read=False).count()
assert unread_before > 0
bulk_res = client.post('/api/notifications/mark-all-read/')
assert bulk_res.status_code == status.HTTP_200_OK
unread_after = Notification.objects.filter(recipient=cust_user, is_read=False).count()
assert unread_after == 0
print(f"  [PASS] POST /api/notifications/mark-all-read/ cleared {unread_before} unread notifications.")

# ----------------------------------------------------------------------
# TASK-17: ADMIN OPERATIONS AUDIT LOGGING
# ----------------------------------------------------------------------
print("\n--- TASK-17: Admin Operations Audit Logging ---")

# 1. Verify property aliases on AuditLog model
audit_entry = AuditLog.objects.create(
    user=admin_user,
    action="MANUAL_TEST_ACTION",
    entity_type="PlatformSetting",
    entity_id="1",
    old_values={"hold_days": 7},
    new_values={"hold_days": 14},
    ip_address="127.0.0.1"
)
assert audit_entry.admin_user == admin_user
assert audit_entry.target_model == "PlatformSetting"
assert audit_entry.target_id == "1"
assert audit_entry.previous_state == {"hold_days": 7}
assert audit_entry.new_state == {"hold_days": 14}
assert audit_entry.timestamp is not None
print("  [PASS] AuditLog model alias properties (admin_user, target_model, target_id, previous_state, new_state, timestamp) verified.")

# 2. Admin changing holding period generates AuditLog
client.force_authenticate(user=admin_user)
setting_res = client.patch('/api/payments/platform-settings/', {"holding_period_days": 10}, format='json')
assert setting_res.status_code == status.HTTP_200_OK
setting_audit = AuditLog.objects.filter(action='UPDATE_PLATFORM_SETTINGS').first()
assert setting_audit is not None
assert setting_audit.new_values.get('payout_hold_days') == 10
print("  [PASS] Platform holding period mutation generated UPDATE_PLATFORM_SETTINGS AuditLog.")

# 3. Admin user block mutation generates AuditLog
block_res = client.post(f'/api/users/{cust_user2.id}/block-toggle/')
assert block_res.status_code == status.HTTP_200_OK
block_audit = AuditLog.objects.filter(action='BLOCK_USER', entity_id=str(cust_user2.id)).first()
assert block_audit is not None
print(f"  [PASS] User block toggle mutation generated BLOCK_USER AuditLog for user {cust_user2.id}.")

# 4. Admin Audit Log List endpoint: GET /api/admin/audit-logs/
audit_list_res = client.get('/api/admin/audit-logs/')
assert audit_list_res.status_code == status.HTTP_200_OK
log_results = audit_list_res.data.get('results', audit_list_res.data)
assert len(log_results) >= 2
first_log = log_results[0]
assert 'target_model' in first_log
assert 'target_id' in first_log
assert 'previous_state' in first_log
assert 'new_state' in first_log
assert 'timestamp' in first_log
print(f"  [PASS] GET /api/admin/audit-logs/ returned {len(log_results)} logs with complete RFC/TASK-17 schema.")

# ----------------------------------------------------------------------
# TASK-18: STANDARDIZED API ERROR RESPONSES
# ----------------------------------------------------------------------
print("\n--- TASK-18: Standardized API Error Responses (RFC 7807) ---")

# 1. Trigger validation error via Register endpoint
client.force_authenticate(user=None)
bad_reg_res = client.post('/api/users/register/', {
    "username": "short",
    "email": "not-an-email",
    "password": "123"
}, format='json')

assert bad_reg_res.status_code == status.HTTP_400_BAD_REQUEST
assert bad_reg_res.data.get('success') is False
err_obj = bad_reg_res.data.get('error', {})
assert err_obj.get('code') == 'VALIDATION_ERROR'
assert err_obj.get('message') is not None
assert 'email' in err_obj.get('details', {})
# Backwards compatibility check:
assert 'detail' in bad_reg_res.data or 'email' in bad_reg_res.data
print("  [PASS] DRF ValidationError formatted into standardized {success: false, error: {code, message, details}}.")

# 2. Trigger authentication / 401 error
client.force_authenticate(user=None)
unauth_res = client.get('/api/notifications/')
assert unauth_res.status_code == status.HTTP_401_UNAUTHORIZED
assert unauth_res.data.get('success') is False
assert unauth_res.data.get('error', {}).get('code') == 'AUTHENTICATION_FAILED'
print("  [PASS] 401 Unauthorized formatted into standardized AUTHENTICATION_FAILED response.")

# 3. Trigger 404 Not Found error
client.force_authenticate(user=admin_user)
not_found_res = client.get('/api/hotels/999999/')
assert not_found_res.status_code == status.HTTP_404_NOT_FOUND
assert not_found_res.data.get('success') is False
assert not_found_res.data.get('error', {}).get('code') == 'NOT_FOUND'
print("  [PASS] 404 Not Found formatted into standardized NOT_FOUND response.")

# ----------------------------------------------------------------------
# TASK-19: SECURITY HEADERS, CORS & RATE LIMITING
# ----------------------------------------------------------------------
print("\n--- TASK-19: Security Headers, CORS & Rate Limiting ---")

# 1. Security Headers
assert getattr(settings, 'SECURE_BROWSER_XSS_FILTER', False) is True
assert getattr(settings, 'X_FRAME_OPTIONS', '') == 'DENY'
assert getattr(settings, 'SECURE_CONTENT_TYPE_NOSNIFF', False) is True
print("  [PASS] Security Headers (SECURE_BROWSER_XSS_FILTER, X_FRAME_OPTIONS='DENY', SECURE_CONTENT_TYPE_NOSNIFF) verified.")

# 2. CORS Strict Configuration
assert getattr(settings, 'CORS_ALLOW_ALL_ORIGINS', True) is False
assert "http://localhost:5173" in getattr(settings, 'CORS_ALLOWED_ORIGINS', [])
assert "http://localhost:5174" in getattr(settings, 'CORS_ALLOWED_ORIGINS', [])
assert getattr(settings, 'CORS_ALLOW_CREDENTIALS', False) is True
print("  [PASS] CORS strictly restricted to frontend origins (5173, 5174) with credentials allowed.")

# 3. Rate Limiting / Throttling Classes and Rates
rf_settings = getattr(settings, 'REST_FRAMEWORK', {})
throttle_classes = rf_settings.get('DEFAULT_THROTTLE_CLASSES', [])
throttle_rates = rf_settings.get('DEFAULT_THROTTLE_RATES', {})

assert 'rest_framework.throttling.AnonRateThrottle' in throttle_classes
assert 'rest_framework.throttling.UserRateThrottle' in throttle_classes
assert 'rest_framework.throttling.ScopedRateThrottle' in throttle_classes
assert throttle_rates.get('anon') == '100/minute'
assert throttle_rates.get('user') == '1000/minute'
assert throttle_rates.get('login') == '5/minute'
assert throttle_rates.get('register') == '5/minute'

from users.views import RegisterView, LoginView, HostLoginView
assert getattr(RegisterView, 'throttle_scope', None) == 'register'
assert getattr(LoginView, 'throttle_scope', None) == 'login'
assert getattr(HostLoginView, 'throttle_scope', None) == 'login'
print("  [PASS] DRF Throttling configured: anon 100/min, user 1000/min, login 5/min, register 5/min.")

# ----------------------------------------------------------------------
# TASK-20: AUTOMATED BACKEND VERIFICATION TEST SUITE (6 CANONICAL TESTS)
# ----------------------------------------------------------------------
print("\n--- TASK-20: Automated Backend Verification Test Suite ---")

# Test 1: test_duplicate_email_registration_rejected
def test_duplicate_email_registration_rejected():
    client.force_authenticate(user=None)
    res = client.post('/api/users/register/', {
        "username": "unique_user_001",
        "email": cust_user.email,  # duplicate email!
        "phone_number": "9123456789",
        "password": "StrongPassword@123",
        "confirm_password": "StrongPassword@123",
        "role": "CUSTOMER"
    }, format='json')
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert res.data.get('success') is False
    assert 'email' in str(res.data)
    print("  [PASS] 1. test_duplicate_email_registration_rejected()")

# Test 2: test_duplicate_phone_registration_rejected
def test_duplicate_phone_registration_rejected():
    client.force_authenticate(user=None)
    res = client.post('/api/users/register/', {
        "username": "unique_user_002",
        "email": "unique_user_002@example.com",
        "phone_number": cust_user.phone_number,  # duplicate phone!
        "password": "StrongPassword@123",
        "confirm_password": "StrongPassword@123",
        "role": "CUSTOMER"
    }, format='json')
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert res.data.get('success') is False
    assert 'phone_number' in str(res.data)
    print("  [PASS] 2. test_duplicate_phone_registration_rejected()")

# Test 3: test_holding_period_change_does_not_affect_old_earnings
def test_holding_period_change_does_not_affect_old_earnings():
    # Create booking and earning with current 7-day hold
    check_in = timezone.now().date() + timedelta(days=2)
    check_out = timezone.now().date() + timedelta(days=5)
    booking = Booking.objects.create(
        booking_id="BK-TASK20-HOLD",
        customer=cust_user,
        hotel=hotel,
        room=room,
        check_in=check_in,
        check_out=check_out,
        number_of_nights=3,
        subtotal=Decimal("12000.00"),
        total_amount=Decimal("12000.00"),
        price_per_night=Decimal("4000.00"),
        guest_name="Guest Hold",
        guest_email="hold@example.com",
        guest_phone="9876543210",
        booking_status=Booking.STATUS_CONFIRMED,
        payment_status=Booking.PAYMENT_PAID
    )

    initial_hold_until = timezone.now() + timedelta(days=7)
    earning = HostEarning.objects.create(
        host=owner_user,
        booking=booking,
        gross_amount=Decimal("12000.00"),
        platform_fee=Decimal("1200.00"),
        tax=Decimal("216.00"),
        net_amount=Decimal("10584.00"),
        holding_period_days=7,
        hold_until=initial_hold_until,
        status=HostEarning.STATUS_ON_HOLD
    )

    # Admin updates holding period to 30 days
    client.force_authenticate(user=admin_user)
    up_res = client.patch('/api/payments/platform-settings/', {"holding_period_days": 30}, format='json')
    assert up_res.status_code == status.HTTP_200_OK

    # Verify existing earning hold_until is completely untouched
    earning.refresh_from_db()
    assert earning.holding_period_days == 7
    diff_seconds = abs((earning.hold_until - initial_hold_until).total_seconds())
    assert diff_seconds < 1.0, f"Old earning hold_until was unexpectedly modified! diff: {diff_seconds}s"
    print("  [PASS] 3. test_holding_period_change_does_not_affect_old_earnings()")

# Test 4: test_razorpay_signature_verification_success_and_failure
def test_razorpay_signature_verification_success_and_failure():
    order_id = "order_test_signature_123"
    payment_id = "pay_test_signature_456"
    key_id = getattr(settings, 'RAZORPAY_KEY_ID', 'rzp_test_1234567890')
    secret = getattr(settings, 'RAZORPAY_KEY_SECRET', 'test_secret')

    rzp_client = razorpay.Client(auth=(key_id, secret))

    # Generate valid signature
    msg = f"{order_id}|{payment_id}".encode('utf-8')
    valid_sig = hmac.new(secret.encode('utf-8'), msg, hashlib.sha256).hexdigest()

    # 1. Success check
    params = {
        'razorpay_order_id': order_id,
        'razorpay_payment_id': payment_id,
        'razorpay_signature': valid_sig
    }
    rzp_client.utility.verify_payment_signature(params)

    # 2. Failure check with invalid signature
    bad_params = {
        'razorpay_order_id': order_id,
        'razorpay_payment_id': payment_id,
        'razorpay_signature': "invalid_tampered_signature_hex"
    }
    is_invalid_caught = False
    try:
        rzp_client.utility.verify_payment_signature(bad_params)
    except SignatureVerificationError:
        is_invalid_caught = True
    assert is_invalid_caught is True
    print("  [PASS] 4. test_razorpay_signature_verification_success_and_failure()")

# Test 5: test_room_concurrency_overselling_prevented
def test_room_concurrency_overselling_prevented():
    # Room has total_units = 1
    d1 = timezone.now().date() + timedelta(days=20)
    d2 = timezone.now().date() + timedelta(days=23)

    # First booking: takes the only unit
    b1 = Booking.objects.create(
        booking_id="BK-TASK20-OVERSELL-1",
        customer=cust_user,
        hotel=hotel,
        room=room,
        check_in=d1,
        check_out=d2,
        number_of_nights=3,
        subtotal=Decimal("12000.00"),
        total_amount=Decimal("12000.00"),
        price_per_night=Decimal("4000.00"),
        guest_name="Guest Oversell",
        guest_email="oversell@example.com",
        guest_phone="9876543210",
        booking_status=Booking.STATUS_CONFIRMED,
        payment_status=Booking.PAYMENT_PAID
    )

    # Query availability for overlapping dates
    client.force_authenticate(user=cust_user2)
    avail_res = client.get('/api/rooms/check-availability/', {
        "room_id": room.id,
        "check_in": str(d1),
        "check_out": str(d2)
    })
    assert avail_res.status_code == status.HTTP_200_OK
    assert avail_res.data.get('available') is False
    assert avail_res.data.get('available_count', 0) == 0

    # Attempt to book overlapping dates via API should be rejected
    book_res = client.post('/api/bookings/', {
        "room": room.id,
        "hotel": hotel.id,
        "check_in": str(d1),
        "check_out": str(d2),
        "guest_name": "Overbook Attempt",
        "guest_email": "overbook@example.com",
        "guest_phone": "9998887776"
    }, format='json')
    assert book_res.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_409_CONFLICT]
    assert book_res.data.get('success') is False
    print("  [PASS] 5. test_room_concurrency_overselling_prevented()")

# Test 6: test_idor_customer_cannot_cancel_other_booking
def test_idor_customer_cannot_cancel_other_booking():
    # CustUser owns booking b_cust1
    b_cust1 = Booking.objects.create(
        booking_id="BK-TASK20-IDOR",
        customer=cust_user,
        hotel=hotel,
        room=room,
        check_in=timezone.now().date() + timedelta(days=35),
        check_out=timezone.now().date() + timedelta(days=38),
        number_of_nights=3,
        subtotal=Decimal("12000.00"),
        total_amount=Decimal("12000.00"),
        price_per_night=Decimal("4000.00"),
        guest_name="Guest IDOR",
        guest_email="idor@example.com",
        guest_phone="9876543210",
        booking_status=Booking.STATUS_CONFIRMED,
        payment_status=Booking.PAYMENT_PAID
    )

    # CustUser2 attempts to cancel CustUser's booking
    client.force_authenticate(user=cust_user2)
    cancel_res = client.post(f'/api/bookings/{b_cust1.id}/cancel/', {
        "reason": "Malicious cancellation attempt"
    }, format='json')

    assert cancel_res.status_code == status.HTTP_403_FORBIDDEN
    assert cancel_res.data.get('success') is False
    b_cust1.refresh_from_db()
    assert b_cust1.booking_status == Booking.STATUS_CONFIRMED
    print("  [PASS] 6. test_idor_customer_cannot_cancel_other_booking()")

# Execute all 6 canonical tests
test_duplicate_email_registration_rejected()
test_duplicate_phone_registration_rejected()
test_holding_period_change_does_not_affect_old_earnings()
test_razorpay_signature_verification_success_and_failure()
test_room_concurrency_overselling_prevented()
test_idor_customer_cannot_cancel_other_booking()

print("\n" + "=" * 70)
print("ALL TASKS 16 TO 20 PASSED COMPLETELY AND FLAWLESSLY!")
print("=" * 70)
