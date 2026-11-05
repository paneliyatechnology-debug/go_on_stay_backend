import os
import sys
import django
import uuid
from decimal import Decimal
from datetime import date, timedelta

sys.path.append(os.path.abspath('.'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.utils import timezone
from rest_framework.test import APIClient
from users.models import User, EmailOTP
from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking

client = APIClient()

print("==================================================================")
print("RUNNING TASKS 06 TO 10 COMPREHENSIVE VERIFICATION SUITE")
print("==================================================================")

# -------------------------------------------------------------------------
# TASK-06: Safe & Standardized Login Endpoint
# -------------------------------------------------------------------------
print("\n--- TASK-06: Safe & Standardized Login Endpoint ---")
pwd = "SecurePassword123!"
User.objects.filter(username__in=["test_login_user", "test_user_other"]).delete()
User.objects.filter(email__in=["test_login_user@example.com", "other_user@example.com"]).delete()
User.objects.filter(phone_number__endswith="9700011122").delete()
User.objects.filter(phone_number__endswith="9700011199").delete()

u1 = User.objects.create(
    username="test_login_user",
    email="test_login_user@example.com",
    phone_number="+919700011122",
    first_name="Rajesh",
    last_name="Sharma",
    role=User.ROLE_CUSTOMER
)
u1.set_password(pwd)
u1.is_active = True
u1.is_blocked = False
u1.save()

# 6a. Login by username
res_user = client.post('/api/users/login/', {"username": "test_login_user", "password": pwd}, format='json')
assert res_user.status_code == 200, f"Expected 200, got {res_user.status_code}: {res_user.data}"
assert "access" in res_user.data and "refresh" in res_user.data
assert res_user.data["user"]["email"] == "test_login_user@example.com"
assert res_user.data["user"]["name"] == "Rajesh Sharma"
assert res_user.data["user"]["phone"] == "+919700011122"
print("  [PASS] Login by username returns standardized JWT tokens and user metadata!")

# 6b. Login by email (case-insensitive)
res_email = client.post('/api/users/login/', {"username": "TEST_LOGIN_USER@EXAMPLE.COM", "password": pwd}, format='json')
assert res_email.status_code == 200
assert res_email.data["user"]["id"] == u1.id
print("  [PASS] Login by case-insensitive email succeeded!")

# 6c. Generic error on bad password (no existence disclosure)
res_bad_pwd = client.post('/api/users/login/', {"username": "test_login_user", "password": "WrongPassword!"}, format='json')
assert res_bad_pwd.status_code == 401
assert res_bad_pwd.data.get("detail") == "No active account found with the given credentials"
print("  [PASS] Wrong password returned 401 generic message without disclosing account existence!")

# 6d. Inactive account check
u1.is_active = False
u1.save()
res_inactive = client.post('/api/users/login/', {"username": "test_login_user", "password": pwd}, format='json')
assert res_inactive.status_code == 403
assert "deactivated" in str(res_inactive.data)
print("  [PASS] Deactivated account returned 403 Forbidden with proper contact support message!")

# 6e. Blocked account check
u1.is_active = True
u1.is_blocked = True
u1.save()
res_blocked = client.post('/api/users/login/', {"username": "test_login_user", "password": pwd}, format='json')
assert res_blocked.status_code == 403
assert "blocked" in str(res_blocked.data)
print("  [PASS] Blocked account returned 403 Forbidden with administrator notice!")

u1.is_blocked = False
u1.save()


# -------------------------------------------------------------------------
# TASK-07: Profile Update Exclude Self in Uniqueness Checks
# -------------------------------------------------------------------------
print("\n--- TASK-07: Profile Update Exclude Self in Uniqueness ---")
u2 = User.objects.create(
    username="test_user_other",
    email="other_user@example.com",
    phone_number="+919700011199",
    role=User.ROLE_CUSTOMER
)

# 7a. User 1 updates their name and keeping their existing email and phone -> must succeed!
client.force_authenticate(user=u1)
res_prof = client.patch('/api/users/profile/', {
    "name": "Rajesh Kumar Sharma",
    "email": "test_login_user@example.com", # self email
    "phone_number": "+919700011122" # self phone
}, format='json')
assert res_prof.status_code == 200, f"Expected 200, got {res_prof.status_code}: {res_prof.data}"
u1.refresh_from_db()
assert u1.first_name == "Rajesh" and "Sharma" in u1.last_name
print("  [PASS] Profile update preserved self uniqueness on existing email & phone without conflict!")

# 7b. User 1 attempts to take User 2's email -> must fail 400
res_dup_mail = client.patch('/api/users/profile/', {"email": "other_user@example.com"}, format='json')
assert res_dup_mail.status_code == 400
assert "email" in res_dup_mail.data
print("  [PASS] Cross-user duplicate email correctly rejected with 400 Bad Request!")

# 7c. User 1 attempts to take User 2's phone -> must fail 400
res_dup_phone = client.patch('/api/users/profile/', {"phone_number": "9700011199"}, format='json')
assert res_dup_phone.status_code == 400
assert "phone_number" in res_dup_phone.data
print("  [PASS] Cross-user duplicate phone number correctly rejected with 400 Bad Request!")


# -------------------------------------------------------------------------
# TASK-08: Password Security & Recovery Token Invalidation
# -------------------------------------------------------------------------
print("\n--- TASK-08: Password Security & Token Invalidation ---")
# 8a. Change password requires valid old_password
res_chg_bad = client.post('/api/users/change-password/', {
    "old_password": "WrongOldPassword!",
    "new_password": "BrandNewPassword123!"
}, format='json')
assert res_chg_bad.status_code == 400
assert "old_password" in res_chg_bad.data
print("  [PASS] Change password rejected invalid old_password with 400 Bad Request!")

# 8b. Change password succeeds with valid old_password
res_chg_ok = client.post('/api/users/change-password/', {
    "old_password": pwd,
    "new_password": "BrandNewPassword123!"
}, format='json')
assert res_chg_ok.status_code == 200
u1.refresh_from_db()
assert u1.check_password("BrandNewPassword123!")
print("  [PASS] Change password verified old_password, updated hash, and confirmed successfully!")

# 8c. Reset password enforces strong password validation & single-use token
from users.views import hash_otp
test_otp = "842915"
EmailOTP.objects.filter(email=u1.email).delete()
otp_rec = EmailOTP.objects.create(
    email=u1.email,
    otp_hash=hash_otp(test_otp)
)

client.force_authenticate(user=None)
# Short password rejected by validate_password
res_rst_short = client.post('/api/users/reset-password/', {
    "email": u1.email,
    "otp": test_otp,
    "new_password": "123"
}, format='json')
assert res_rst_short.status_code == 400
print("  [PASS] Reset password rejected weak password via validate_password!")

# Valid password succeeds
res_rst_ok = client.post('/api/users/reset-password/', {
    "email": u1.email,
    "otp": test_otp,
    "new_password": "FinalResetPassword123!"
}, format='json')
assert res_rst_ok.status_code == 200
u1.refresh_from_db()
assert u1.check_password("FinalResetPassword123!")

# Replay attack: OTP must be invalidated/deleted
res_replay = client.post('/api/users/reset-password/', {
    "email": u1.email,
    "otp": test_otp,
    "new_password": "AnotherPassword123!"
}, format='json')
assert res_replay.status_code == 400
print("  [PASS] Single-use OTP token invalidated after reset; replay attack blocked!")


# -------------------------------------------------------------------------
# TASK-09: Room Availability Query Endpoint Alignment
# -------------------------------------------------------------------------
print("\n--- TASK-09: Room Availability Query Endpoint Alignment ---")
admin = User.objects.filter(is_superuser=True).first() or User.objects.filter(role='ADMIN').first()
hotel = Hotel.objects.filter(owner=admin).first() or Hotel.objects.first()
room1 = Room.objects.filter(hotel=hotel).first()
if not room1:
    room1 = Room.objects.create(hotel=hotel, title="Suite One", price_per_night=4000.0, total_rooms=3)
room2 = Room.objects.filter(hotel=hotel).exclude(id=room1.id).first()
if not room2:
    room2 = Room.objects.create(hotel=hotel, title="Deluxe Two", price_per_night=2500.0, total_rooms=2)

cin = (date.today() + timedelta(days=30)).strftime('%Y-%m-%d')
cout = (date.today() + timedelta(days=32)).strftime('%Y-%m-%d')

# 9a. Query by room_id
res_avail_room = client.get(f'/api/rooms/check-availability/?room_id={room1.id}&check_in={cin}&check_out={cout}')
assert res_avail_room.status_code == 200
assert res_avail_room.data.get("available") is True
assert res_avail_room.data.get("available_count") >= 1
print(f"  [PASS] Room query by room_id: available={res_avail_room.data['available']}, count={res_avail_room.data['available_count']}")

# 9b. Query by hotel_id (returns array of rooms)
res_avail_hotel = client.get(f'/api/rooms/check-availability/?hotel_id={hotel.id}&check_in={cin}&check_out={cout}')
assert res_avail_hotel.status_code == 200
assert "rooms" in res_avail_hotel.data
assert len(res_avail_hotel.data["rooms"]) >= 2
r_item = res_avail_hotel.data["rooms"][0]
assert "room_id" in r_item and "available" in r_item and "remaining" in r_item
print(f"  [PASS] Hotel query by hotel_id returned {len(res_avail_hotel.data['rooms'])} rooms with availability flags!")

# 9c. URL Alias /api/rooms/availability/ works as well
res_alias = client.get(f'/api/rooms/availability/?hotel_id={hotel.id}&check_in={cin}&check_out={cout}')
assert res_alias.status_code == 200
print("  [PASS] URL alias /api/rooms/availability/ confirmed working (200 OK)!")


# -------------------------------------------------------------------------
# TASK-10: Hotel & Room Management Validation & Deletion Protection
# -------------------------------------------------------------------------
print("\n--- TASK-10: Hotel & Room Validation & Deletion Protection ---")
client.force_authenticate(user=admin)

# 10a. Room validation: negative price or capacity 0 rejected
res_bad_rm = client.post('/api/rooms/', {
    "hotel": hotel.id,
    "title": "Invalid Room",
    "price_per_night": -50.0,
    "capacity_adults": 0,
    "total_rooms": 0
}, format='json')
assert res_bad_rm.status_code == 400
print("  [PASS] Room creation with non-positive price/capacity/total rejected with 400 Bad Request!")

# 10b. Deletion Protection: Create active booking on room1
b_active = Booking.objects.create(
    booking_id=f"BK-DEL-LOCK-{uuid.uuid4().hex[:6].upper()}",
    hotel=hotel,
    room=room1,
    customer=u1,
    check_in=date.today(),
    check_out=date.today() + timedelta(days=5),
    total_amount=Decimal('8000.00'),
    price_per_night=Decimal('4000.00'),
    subtotal=Decimal('8000.00'),
    taxes=Decimal('0.00'),
    booking_status=Booking.STATUS_CONFIRMED,
    payment_status=Booking.PAYMENT_PAID
)

# Attempt to delete room with active reservation -> MUST return 400
res_del_rm = client.delete(f'/api/rooms/{room1.id}/')
assert res_del_rm.status_code == 400, f"Expected 400 for room delete, got {res_del_rm.status_code}: {res_del_rm.data}"
assert "active upcoming reservations" in res_del_rm.data.get("error", "")
print("  [PASS] Room deletion blocked with 400: 'Cannot delete room with active upcoming reservations.'!")

# Attempt to delete hotel with active reservation -> MUST return 400
res_del_htl = client.delete(f'/api/hotels/{hotel.id}/')
assert res_del_htl.status_code == 400, f"Expected 400 for hotel delete, got {res_del_htl.status_code}: {res_del_htl.data}"
assert "active upcoming reservations" in res_del_htl.data.get("error", "")
print("  [PASS] Hotel deletion blocked with 400: 'Cannot delete hotel with active upcoming reservations.'!")

# Cleanup
b_active.delete()
u1.delete()
u2.delete()

print("\n==================================================================")
print("ALL TASKS 06 TO 10 REQUIREMENTS PASSED 100%!")
print("==================================================================")
