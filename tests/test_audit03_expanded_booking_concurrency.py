import os
import sys
import time
import json
import shutil
import concurrent.futures
from decimal import Decimal
from datetime import date, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# RULE ZERO: Isolated Staging Database
STAGING_DB = os.path.join(BASE_DIR, "db.sqlite3.staging_concurrency")
if os.path.exists(STAGING_DB):
    try:
        os.remove(STAGING_DB)
    except Exception:
        pass

shutil.copyfile(os.path.join(BASE_DIR, "db.sqlite3"), STAGING_DB)

os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()

from django.conf import settings
settings.DATABASES['default']['NAME'] = STAGING_DB

from django.db import connection, transaction
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from users.models import User
from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking
from rooms.utils import release_temporary_hold, cleanup_expired_payment_holds, get_available_room_count

results = {
    "scenario_1_single_room_50_users": {},
    "scenario_2_different_rooms_50_users": {},
    "scenario_3_overlapping_date_ranges": {},
    "scenario_4_expired_inventory_holds": {},
    "scenario_5_payment_failure_hold_release": {},
    "scenario_6_multi_worker_mutex": {},
    "scenario_7_interrupted_transaction_rollback": {}
}

print("================================================================================")
print("AUDIT 03: EXPANDED BOOKING CONCURRENCY & COLLISION HARNESS")
print(f"Target: Isolated Staging Database ({os.path.basename(STAGING_DB)})")
print("================================================================================")

connection.close()

# Helper to create virtual test user
def get_or_create_user(username, email):
    u, _ = User.objects.get_or_create(
        username=username,
        defaults={"email": email, "role": "CUSTOMER", "is_active": True}
    )
    return u

test_owner = get_or_create_user("owner_concurrency", "owner_conc@staging.goonstay.com")
test_owner.role = "HOTEL_OWNER"
test_owner.save()

hotel, _ = Hotel.objects.get_or_create(
    name="Concurrency Test Hotel",
    defaults={
        "owner": test_owner,
        "description": "Hotel for concurrency testing",
        "address": "100 Staging Blvd",
        "city": "Bengaluru",
        "state": "Karnataka",
        "status": Hotel.STATUS_APPROVED,
        "is_approved": True,
        "is_active": True
    }
)

# ------------------------------------------------------------------------------
# SCENARIO 1: 50 users competing for ONE room unit
# ------------------------------------------------------------------------------
print("\n--- SCENARIO 1: 50 Users Competing For 1 Single Room Unit ---")
single_room, _ = Room.objects.get_or_create(
    hotel=hotel,
    title="Single Unit Stress Room",
    defaults={
        "room_type": "DELUXE",
        "price_per_night": Decimal("3500.00"),
        "total_rooms": 1,
        "room_numbers": "SUITE-101"
    }
)
single_room.total_rooms = 1
single_room.save()

s1_users = [get_or_create_user(f"conc_user_s1_{i}", f"conc_user_s1_{i}@staging.com") for i in range(50)]
s1_tokens = [str(RefreshToken.for_user(u).access_token) for u in s1_users]

def book_single_room(idx):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {s1_tokens[idx]}")
    payload = {
        "hotel": hotel.id,
        "room": single_room.id,
        "check_in": "2026-12-01",
        "check_out": "2026-12-04",
        "number_of_guests": 2,
        "number_of_rooms": 1,
        "guest_name": f"Contender {idx}",
        "guest_email": f"conc_user_s1_{idx}@staging.com",
        "guest_phone": "9876543210"
    }
    t0 = time.perf_counter()
    resp = client.post("/api/bookings/", payload, format="json")
    elapsed = (time.perf_counter() - t0) * 1000
    return resp.status_code, elapsed

s1_statuses = {}
with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
    futures = [executor.submit(book_single_room, i) for i in range(50)]
    for f in concurrent.futures.as_completed(futures):
        code, _ = f.result()
        s1_statuses[code] = s1_statuses.get(code, 0) + 1

db_s1_bookings = Booking.objects.filter(room=single_room, check_in="2026-12-01").count()
print(f"  HTTP Responses: {s1_statuses}")
print(f"  DB Bookings Created: {db_s1_bookings}")
print(f"  Double-Booking Occurred: {db_s1_bookings > 1}")

results["scenario_1_single_room_50_users"] = {
    "status_codes": s1_statuses,
    "db_bookings_created": db_s1_bookings,
    "success": (db_s1_bookings == 1 and s1_statuses.get(201, 0) == 1 and s1_statuses.get(409, 0) == 49)
}

# ------------------------------------------------------------------------------
# SCENARIO 2: 50 users booking 50 DIFFERENT rooms simultaneously
# ------------------------------------------------------------------------------
print("\n--- SCENARIO 2: 50 Users Booking 50 Different Rooms Simultaneously ---")
diff_rooms = []
for i in range(50):
    r, _ = Room.objects.get_or_create(
        hotel=hotel,
        title=f"Parallel Distinct Room {i}",
        defaults={
            "room_type": "STANDARD",
            "price_per_night": Decimal("2000.00"),
            "total_rooms": 1,
            "room_numbers": f"PAR-{i+1}"
        }
    )
    r.total_rooms = 1
    r.save()
    diff_rooms.append(r)

s2_users = [get_or_create_user(f"conc_user_s2_{i}", f"conc_user_s2_{i}@staging.com") for i in range(50)]
s2_tokens = [str(RefreshToken.for_user(u).access_token) for u in s2_users]

def book_distinct_room(idx):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {s2_tokens[idx]}")
    payload = {
        "hotel": hotel.id,
        "room": diff_rooms[idx].id,
        "check_in": "2026-12-15",
        "check_out": "2026-12-18",
        "number_of_guests": 1,
        "number_of_rooms": 1,
        "guest_name": f"Distinct Guest {idx}",
        "guest_email": f"conc_user_s2_{idx}@staging.com",
        "guest_phone": "9876543210"
    }
    resp = client.post("/api/bookings/", payload, format="json")
    return resp.status_code

s2_statuses = {}
with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
    futures = [executor.submit(book_distinct_room, i) for i in range(50)]
    for f in concurrent.futures.as_completed(futures):
        code = f.result()
        s2_statuses[code] = s2_statuses.get(code, 0) + 1

db_s2_bookings = Booking.objects.filter(room__in=diff_rooms, check_in="2026-12-15").count()
print(f"  HTTP Responses: {s2_statuses}")
print(f"  DB Bookings Created: {db_s2_bookings} (Expected: 50)")

results["scenario_2_different_rooms_50_users"] = {
    "status_codes": s2_statuses,
    "db_bookings_created": db_s2_bookings,
    "success": (db_s2_bookings == 50 and s2_statuses.get(201, 0) == 50)
}

# ------------------------------------------------------------------------------
# SCENARIO 3: Overlapping Date Ranges
# ------------------------------------------------------------------------------
print("\n--- SCENARIO 3: Overlapping Date Ranges Validation ---")
overlap_room, _ = Room.objects.get_or_create(
    hotel=hotel,
    title="Overlap Test Room",
    defaults={
        "room_type": "DELUXE",
        "price_per_night": Decimal("3000.00"),
        "total_rooms": 1,
        "room_numbers": "OVL-101"
    }
)
overlap_room.total_rooms = 1
overlap_room.save()

client_ovl = APIClient()
u_ovl = get_or_create_user("user_overlap", "user_overlap@staging.com")
client_ovl.credentials(HTTP_AUTHORIZATION=f"Bearer {str(RefreshToken.for_user(u_ovl).access_token)}")

# Base booking: Dec 10 to Dec 15
resp1 = client_ovl.post("/api/bookings/", {
    "hotel": hotel.id,
    "room": overlap_room.id,
    "check_in": "2026-12-10",
    "check_out": "2026-12-15",
    "number_of_guests": 2,
    "number_of_rooms": 1,
    "guest_name": "Base Guest",
    "guest_email": "base@staging.com",
    "guest_phone": "9876543210"
}, format="json")
print(f"  Base Booking (Dec 10-15): Status {resp1.status_code}")

# Overlapping test 1: Dec 12 to Dec 17 (Interior overlap) -> Expect 409
resp2 = client_ovl.post("/api/bookings/", {
    "hotel": hotel.id,
    "room": overlap_room.id,
    "check_in": "2026-12-12",
    "check_out": "2026-12-17",
    "number_of_guests": 2,
    "number_of_rooms": 1,
    "guest_name": "Overlap Guest 1",
    "guest_email": "ovl1@staging.com",
    "guest_phone": "9876543210"
}, format="json")
print(f"  Interior Overlap (Dec 12-17): Status {resp2.status_code} (Expected: 409)")

# Overlapping test 2: Dec 08 to Dec 12 (Front overlap) -> Expect 409
resp3 = client_ovl.post("/api/bookings/", {
    "hotel": hotel.id,
    "room": overlap_room.id,
    "check_in": "2026-12-08",
    "check_out": "2026-12-12",
    "number_of_guests": 2,
    "number_of_rooms": 1,
    "guest_name": "Overlap Guest 2",
    "guest_email": "ovl2@staging.com",
    "guest_phone": "9876543210"
}, format="json")
print(f"  Front Overlap (Dec 08-12): Status {resp3.status_code} (Expected: 409)")

# Adjacent non-overlapping test: Dec 15 to Dec 18 (Check-in on checkout day) -> Expect 201
resp4 = client_ovl.post("/api/bookings/", {
    "hotel": hotel.id,
    "room": overlap_room.id,
    "check_in": "2026-12-15",
    "check_out": "2026-12-18",
    "number_of_guests": 2,
    "number_of_rooms": 1,
    "guest_name": "Adjacent Guest",
    "guest_email": "adj@staging.com",
    "guest_phone": "9876543210"
}, format="json")
print(f"  Adjacent Non-Overlap (Dec 15-18): Status {resp4.status_code} (Expected: 201)")

results["scenario_3_overlapping_date_ranges"] = {
    "base_status": resp1.status_code,
    "interior_overlap_status": resp2.status_code,
    "front_overlap_status": resp3.status_code,
    "adjacent_status": resp4.status_code,
    "success": (resp1.status_code == 201 and resp2.status_code == 409 and resp3.status_code == 409 and resp4.status_code == 201)
}

# ------------------------------------------------------------------------------
# SCENARIO 4: Expired Inventory Holds Cleanup
# ------------------------------------------------------------------------------
print("\n--- SCENARIO 4: Expired Inventory Holds Cleanup ---")
hold_room, _ = Room.objects.get_or_create(
    hotel=hotel,
    title="Hold Cleanup Room",
    defaults={
        "room_type": "DELUXE",
        "price_per_night": Decimal("2500.00"),
        "total_rooms": 1,
        "room_numbers": "HLD-101"
    }
)
hold_room.total_rooms = 1
hold_room.save()

# Create booking hold expired 20 minutes ago
expired_booking = Booking.objects.create(
    booking_id="EXP-HOLD-999",
    customer=u_ovl,
    hotel=hotel,
    room=hold_room,
    check_in="2026-12-25",
    check_out="2026-12-28",
    number_of_nights=3,
    number_of_rooms=1,
    number_of_guests=2,
    price_per_night=hold_room.price_per_night,
    subtotal=hold_room.price_per_night * 3,
    total_amount=hold_room.price_per_night * 3,
    guest_name="Expired Guest",
    guest_email="expired@staging.com",
    guest_phone="9876543210",
    booking_status=Booking.STATUS_PENDING_PAYMENT,
    payment_status=Booking.PAYMENT_PENDING,
    expires_at=timezone.now() - timedelta(minutes=20)
)
# Force created_at and expires_at to 30 mins ago
Booking.objects.filter(id=expired_booking.id).update(
    created_at=timezone.now() - timedelta(minutes=30),
    expires_at=timezone.now() - timedelta(minutes=20)
)

print("  Executing cleanup_expired_payment_holds()...")
released_count = cleanup_expired_payment_holds()
expired_booking.refresh_from_db()
print(f"  Holds Released: {released_count} | Booking Status: {expired_booking.booking_status}")

# Verify room can now be booked by another user
avail_count = get_available_room_count(hold_room, "2026-12-25", "2026-12-28")
print(f"  Available Room Inventory After Hold Release: {avail_count} (Expected: 1)")

results["scenario_4_expired_inventory_holds"] = {
    "holds_released": released_count,
    "final_booking_status": expired_booking.booking_status,
    "restored_inventory": avail_count,
    "success": (expired_booking.booking_status in [Booking.STATUS_EXPIRED, Booking.STATUS_CANCELLED] and avail_count == 1)
}

# ------------------------------------------------------------------------------
# SCENARIO 5: Payment Failure During Temporary Hold
# ------------------------------------------------------------------------------
print("\n--- SCENARIO 5: Payment Failure During Temporary Hold ---")
fail_booking = Booking.objects.create(
    booking_id="FAIL-HOLD-888",
    customer=u_ovl,
    hotel=hotel,
    room=hold_room,
    check_in="2027-01-05",
    check_out="2027-01-08",
    number_of_nights=3,
    number_of_rooms=1,
    number_of_guests=2,
    price_per_night=hold_room.price_per_night,
    subtotal=hold_room.price_per_night * 3,
    total_amount=hold_room.price_per_night * 3,
    guest_name="Failed Payment Guest",
    guest_email="failpay@staging.com",
    guest_phone="9876543210",
    booking_status=Booking.STATUS_PENDING_PAYMENT,
    payment_status=Booking.PAYMENT_PENDING
)

print("  Invoking release_temporary_hold(reason='Payment Failed')...")
release_temporary_hold(fail_booking, reason="Payment Failed")
fail_booking.refresh_from_db()

avail_after_failure = get_available_room_count(hold_room, "2027-01-05", "2027-01-08")
print(f"  Booking Status After Payment Failure: {fail_booking.booking_status}")
print(f"  Available Inventory Restored: {avail_after_failure} (Expected: 1)")

results["scenario_5_payment_failure_hold_release"] = {
    "booking_status": fail_booking.booking_status,
    "restored_inventory": avail_after_failure,
    "success": (fail_booking.booking_status in [Booking.STATUS_EXPIRED, Booking.STATUS_CANCELLED] and avail_after_failure == 1)
}

# ------------------------------------------------------------------------------
# SCENARIO 6: Multi-Worker Mutex Contention
# ------------------------------------------------------------------------------
print("\n--- SCENARIO 6: Multi-Worker Mutex Contention ---")
# Verify that select_for_update() properly serializes transactions without deadlock
mutex_room, _ = Room.objects.get_or_create(
    hotel=hotel,
    title="Mutex Room",
    defaults={
        "room_type": "DELUXE",
        "price_per_night": Decimal("3000.00"),
        "total_rooms": 1,
        "room_numbers": "MTX-101"
    }
)
mutex_room.total_rooms = 1
mutex_room.save()

def simulate_worker_transaction(worker_id):
    connection.close()
    try:
        with transaction.atomic():
            # In PostgreSQL this acquires row-level mutex; in SQLite it serializes on database lock
            r = Room.objects.select_for_update().get(id=mutex_room.id)
            count = Booking.objects.filter(room=r, check_in="2027-02-01").count()
            if count < r.total_rooms:
                Booking.objects.create(
                    booking_id=f"MTX-BOOK-{worker_id}",
                    customer=u_ovl,
                    hotel=hotel,
                    room=r,
                    check_in="2027-02-01",
                    check_out="2027-02-04",
                    number_of_nights=3,
                    number_of_rooms=1,
                    number_of_guests=2,
                    price_per_night=r.price_per_night,
                    subtotal=r.price_per_night * 3,
                    total_amount=r.price_per_night * 3,
                    guest_name=f"Worker Guest {worker_id}",
                    guest_email=f"w{worker_id}@staging.com",
                    guest_phone="9876543210",
                    booking_status=Booking.STATUS_CONFIRMED,
                    payment_status=Booking.PAYMENT_PAID
                )
                return "BOOKED"
            return "REJECTED_SOLD_OUT"
    except Exception as e:
        return f"REJECTED_LOCK_{type(e).__name__}"

worker_results = []
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
    futures = [executor.submit(simulate_worker_transaction, i) for i in range(10)]
    for f in concurrent.futures.as_completed(futures):
        worker_results.append(f.result())

mtx_bookings = Booking.objects.filter(room=mutex_room, check_in="2027-02-01").count()
print(f"  Worker Results: {dict((x, worker_results.count(x)) for x in set(worker_results))}")
print(f"  Total Mutex Bookings in DB: {mtx_bookings} (Expected: exactly 1)")

results["scenario_6_multi_worker_mutex"] = {
    "worker_outcomes": dict((x, worker_results.count(x)) for x in set(worker_results)),
    "db_bookings": mtx_bookings,
    "success": (mtx_bookings == 1 and worker_results.count("BOOKED") == 1)
}

# ------------------------------------------------------------------------------
# SCENARIO 7: Interrupted Transaction Rollback
# ------------------------------------------------------------------------------
print("\n--- SCENARIO 7: Interrupted Transaction Atomic Rollback ---")
initial_booking_count = Booking.objects.count()

try:
    with transaction.atomic():
        Booking.objects.create(
            booking_id="CRASH-BOOKING-999",
            customer=u_ovl,
            hotel=hotel,
            room=mutex_room,
            check_in="2027-03-01",
            check_out="2027-03-04",
            number_of_nights=3,
            number_of_rooms=1,
            number_of_guests=2,
            price_per_night=mutex_room.price_per_night,
            subtotal=mutex_room.price_per_night * 3,
            total_amount=mutex_room.price_per_night * 3,
            guest_name="Crash Guest",
            guest_email="crash@staging.com",
            guest_phone="9876543210",
            booking_status=Booking.STATUS_PENDING_PAYMENT,
            payment_status=Booking.PAYMENT_PENDING
        )
        # Simulate unexpected crash / application termination
        raise RuntimeError("SIMULATED_WORKER_SIGKILL_CRASH")
except RuntimeError:
    pass

post_crash_booking_count = Booking.objects.count()
crashed_exists = Booking.objects.filter(booking_id="CRASH-BOOKING-999").exists()
print(f"  Initial Booking Count: {initial_booking_count}")
print(f"  Post-Crash Booking Count: {post_crash_booking_count}")
print(f"  Crashed Booking Exists in DB: {crashed_exists} (Expected: False)")

results["scenario_7_interrupted_transaction_rollback"] = {
    "initial_count": initial_booking_count,
    "post_crash_count": post_crash_booking_count,
    "crashed_exists": crashed_exists,
    "success": (not crashed_exists and initial_booking_count == post_crash_booking_count)
}

# Output Results
output_file = os.path.join(BASE_DIR, "scratch_audit03_concurrency_results.json")
with open(output_file, "w") as f:
    json.dump(results, f, indent=2)

print(f"\n[AUDIT 03 COMPLETE] Results saved to {output_file}")

connection.close()
if os.path.exists(STAGING_DB):
    try:
        os.remove(STAGING_DB)
        print("[CLEANUP] Staging concurrency DB removed cleanly.")
    except Exception as e:
        print(f"[CLEANUP NOTE] {e}")
