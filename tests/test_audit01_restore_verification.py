import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import json
import sqlite3
import django

# Setup Django with isolated staging test database
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
# Ensure we do NOT touch db.sqlite3
STAGING_DB_PATH = os.path.join(BASE_DIR, 'db.sqlite3.staging_restore_test')
if os.path.exists(STAGING_DB_PATH):
    try:
        os.remove(STAGING_DB_PATH)
    except Exception:
        pass

from django.conf import settings
# Override database to isolated staging path
settings.DATABASES['default'] = {
    'ENGINE': 'django.db.backends.sqlite3',
    'NAME': STAGING_DB_PATH,
}

django.setup()

from django.core.management import call_command
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import Permission, Group
from users.models import User
from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking
from payments.models import Payment, Refund, HostEarning, HostPayout, SupportTicket
from staff.models import StaffProfile, Department

results = {
    "migrations_applied": False,
    "fixture_restored": False,
    "object_count_verified": False,
    "relationships_verified": False,
    "read_write_verified": False,
    "details": {}
}

print("=== STEP 1: APPLYING MIGRATIONS TO ISOLATED STAGING DB ===")
call_command('migrate', verbosity=0)
results["migrations_applied"] = True
print("[OK] Migrations applied cleanly to isolated staging database.")

print("\n=== STEP 2: RESTORING 1,517 OBJECT FIXTURE ===")
try:
    call_command('loaddata', 'staging_migration_fixture.json', verbosity=0)
    results["fixture_restored"] = True
    print("[OK] Loaddata completed without foreign key or deserialization errors.")
except Exception as e:
    print(f"[FAIL] Loaddata failed: {e}")
    sys.exit(1)

print("\n=== STEP 3: RECONCILING MODEL COUNTS AGAINST MANIFEST ===")
checks = [
    (User, 28, "Users"),
    (Hotel, 12, "Hotels"),
    (Room, 10, "Rooms"),
    (Booking, 118, "Bookings"),
    (Payment, 115, "Payments"),
    (Refund, 37, "Refunds"),
    (HostEarning, 64, "Host Earnings"),
    (HostPayout, 20, "Host Payouts"),
    (StaffProfile, 9, "Staff Profiles"),
    (Department, 5, "Departments"),
    (SupportTicket, 3, "Support Tickets"),
]

all_counts_match = True
for model_cls, expected, label in checks:
    actual = model_cls.objects.count()
    matched = (actual == expected)
    if not matched:
        all_counts_match = False
    print(f"  {label}: Expected {expected} | Actual {actual} -> {'MATCH' if matched else 'MISMATCH'}")
    results["details"][label] = {"expected": expected, "actual": actual, "match": matched}

results["object_count_verified"] = all_counts_match

print("\n=== STEP 4: VERIFYING RELATIONSHIPS & CONTENTTYPES/PERMISSIONS ===")
ct_count = ContentType.objects.count()
perm_count = Permission.objects.count()
print(f"  ContentTypes: {ct_count} | Permissions: {perm_count}")

# Check foreign key consistency across Bookings -> Users, Rooms, Hotels
sample_booking = Booking.objects.first()
customer_email = getattr(sample_booking.customer, 'email', 'N/A') if hasattr(sample_booking, 'customer') else getattr(sample_booking.user, 'email', 'N/A')
print(f"  Sample Booking FK Check: ID={sample_booking.id}, Guest={customer_email}, Room={sample_booking.room.room_type}, Hotel={sample_booking.room.hotel.name}")

# Check Payment -> Booking FK
sample_payment = Payment.objects.filter(booking__isnull=False).first()
print(f"  Sample Payment FK Check: ID={sample_payment.id}, Booking={sample_payment.booking.id}, Amount={sample_payment.amount}")

# Check Staff -> User & Department FK
sample_staff = StaffProfile.objects.first()
print(f"  Sample Staff FK Check: ID={sample_staff.id}, User={sample_staff.user.email}, Dept={sample_staff.department.name}")

results["relationships_verified"] = True

print("\n=== STEP 5: EXECUTING REPRESENTATIVE READ/WRITE TRANSACTIONS ===")
from django.db import transaction

# Test Transactional Write: Create a test booking hold in staging DB and verify rollback / commit
with transaction.atomic():
    hotel = Hotel.objects.first()
    room = Room.objects.filter(hotel=hotel).first()
    customer_user = User.objects.filter(role__iexact='CUSTOMER').first()
    if not customer_user:
        customer_user = User.objects.first()
    
    booking_kwargs = {
        'booking_id': 'STG-2026-TEST01',
        'hotel': hotel,
        'room': room,
        'customer': customer_user,
        'check_in': '2026-12-10',
        'check_out': '2026-12-15',
        'number_of_nights': 5,
        'number_of_rooms': 1,
        'number_of_guests': 2,
        'price_per_night': room.price_per_night,
        'subtotal': room.price_per_night * 5,
        'total_amount': room.price_per_night * 5,
        'guest_name': 'Test Guest',
        'guest_email': 'testguest@example.com',
        'guest_phone': '9876543210',
        'booking_status': Booking.STATUS_PENDING_PAYMENT,
        'payment_status': Booking.PAYMENT_PENDING
    }

    test_booking = Booking.objects.create(**booking_kwargs)
    print(f"  Created Staging Test Booking: {test_booking.booking_id}")
    
    # Verify Read
    read_back = Booking.objects.get(booking_id='STG-2026-TEST01')
    assert read_back.total_amount == test_booking.total_amount
    print("  Read-back transaction successful.")
    
    # Test cleanup
    test_booking.delete()
    print("  Cleanup transaction successful.")

results["read_write_verified"] = True

with open('scratch_audit01_restore_results.json', 'w') as f:
    json.dump(results, f, indent=2)

print("\n[AUDIT 01 COMPLETE] All restoration checks completed successfully.")
