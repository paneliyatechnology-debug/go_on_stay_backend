import os
import sys
import time
import shutil
import statistics
import concurrent.futures
from decimal import Decimal
from datetime import date, timedelta

base_dir = r"D:\BookMyRoomBackend\BookMyRoomBackend"
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

# RULE ZERO: Use dedicated isolated staging database file
STAGING_DB = os.path.join(base_dir, "db.sqlite3.staging_loadtest")
if os.path.exists(STAGING_DB):
    try:
        os.remove(STAGING_DB)
    except Exception:
        pass

shutil.copyfile(os.path.join(base_dir, "db.sqlite3"), STAGING_DB)

os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()

from django.conf import settings
# Override default database connection to point to staging db
settings.DATABASES['default']['NAME'] = STAGING_DB

from django.db import connection
from rest_framework.test import APIClient
from users.models import User
from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking

print("================================================================================")
print("GOONSTAY STAGING LOAD TEST & CONCURRENCY HARNESS (PHASE 4.6)")
print("Target: Isolated Staging Database (db.sqlite3.staging_loadtest)")
print("================================================================================")

# 1. Setup Staging Test Fixtures
connection.close()  # Reconnect to STAGING_DB

# Create a Pool of 50 Distinct Staging Test Users (Representing 50 Concurrent Virtual Users)
from rest_framework_simplejwt.tokens import RefreshToken

test_users = []
for i in range(50):
    u, _ = User.objects.get_or_create(
        username=f"load_user_{i}",
        defaults={
            "email": f"load_user_{i}@staging.goonstay.com",
            "role": "CUSTOMER"
        }
    )
    test_users.append(u)

# Pre-generate JWT tokens for all virtual users
user_tokens = [str(RefreshToken.for_user(u).access_token) for u in test_users]

test_owner, _ = User.objects.get_or_create(
    username="loadtest_owner",
    defaults={
        "email": "loadtest_owner@staging.goonstay.com",
        "role": "HOTEL_OWNER"
    }
)
test_owner.set_password("LoadTestPass123!")
test_owner.save()

# Create a Controlled Single-Unit Room for Concurrency Contention Testing
stress_hotel, _ = Hotel.objects.get_or_create(
    name="Staging Stress Hotel",
    defaults={
        "owner": test_owner,
        "description": "Hotel for concurrency collision load testing",
        "address": "123 Staging Ave",
        "city": "Mumbai",
        "state": "Maharashtra",
        "status": Hotel.STATUS_APPROVED,
        "is_approved": True,
        "is_active": True
    }
)

stress_room, _ = Room.objects.get_or_create(
    hotel=stress_hotel,
    title="Single Contention Suite",
    defaults={
        "room_type": "DELUXE",
        "price_per_night": Decimal("4000.00"),
        "total_rooms": 1,
        "room_numbers": "Suite-901"
    }
)
stress_room.total_rooms = 1
stress_room.room_numbers = "Suite-901"
stress_room.save()

hotel_id = stress_hotel.id
room_id = stress_room.id

def make_request(scenario_type, client_idx):
    client = APIClient()
    user_idx = client_idx % len(user_tokens)
    token = user_tokens[user_idx]
    user_obj = test_users[user_idx]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    start_t = time.perf_counter()
    status_code = 0
    success = False

    try:
        if scenario_type == "hotel_browse":
            res = client.get("/api/hotels/")
            status_code = res.status_code
            success = status_code == 200

        elif scenario_type == "hotel_detail":
            res = client.get(f"/api/hotels/{hotel_id}/")
            status_code = res.status_code
            success = status_code == 200

        elif scenario_type == "room_availability":
            cin = (date.today() + timedelta(days=30)).isoformat()
            cout = (date.today() + timedelta(days=32)).isoformat()
            res = client.get(f"/api/rooms/{room_id}/?check_in={cin}&check_out={cout}")
            status_code = res.status_code
            success = status_code == 200

        elif scenario_type == "booking_concurrency_stress":
            # 50 users simultaneously attempt to book the EXACT SAME ROOM on the EXACT SAME DATES
            cin = (date.today() + timedelta(days=40)).isoformat()
            cout = (date.today() + timedelta(days=42)).isoformat()
            res = client.post("/api/bookings/", {
                "hotel": hotel_id,
                "room": room_id,
                "check_in": cin,
                "check_out": cout,
                "number_of_rooms": 1,
                "number_of_guests": 2,
                "guest_name": f"Concurrency User {user_idx}",
                "guest_email": f"load_user_{user_idx}@staging.goonstay.com",
                "guest_phone": "9876543210"
            })
            status_code = res.status_code
            # 201 Created is the 1 winning booking; 409 Conflict is expected sold out collision response
            success = status_code in (201, 409)

        elif scenario_type == "dashboard_customer":
            res = client.get("/api/bookings/")
            status_code = res.status_code
            success = status_code == 200

    except Exception as e:
        status_code = 500
        success = False

    latency_ms = (time.perf_counter() - start_t) * 1000.0
    return {
        "scenario": scenario_type,
        "status_code": status_code,
        "success": success,
        "latency_ms": latency_ms
    }

def run_load_tier(concurrency_level, total_requests, scenario):
    print(f"\n--- Running Tier: {concurrency_level} Concurrent Users | Scenario: {scenario} ({total_requests} requests) ---")
    start_time = time.perf_counter()

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency_level) as executor:
        futures = [executor.submit(make_request, scenario, i) for i in range(total_requests)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    total_wall_time = time.perf_counter() - start_time
    latencies = [r["latency_ms"] for r in results]
    success_count = sum(1 for r in results if r["success"])
    fail_count = len(results) - success_count
    status_codes = {}
    for r in results:
        status_codes[r["status_code"]] = status_codes.get(r["status_code"], 0) + 1

    p50 = statistics.median(latencies)
    p95 = statistics.quantiles(latencies, n=100)[94] if len(latencies) >= 100 else max(latencies)
    p99 = statistics.quantiles(latencies, n=100)[98] if len(latencies) >= 100 else max(latencies)
    rps = len(results) / total_wall_time if total_wall_time > 0 else 0

    print(f"  Wall Time:     {total_wall_time:.2f}s")
    print(f"  Throughput:    {rps:.1f} Requests/sec")
    print(f"  Success/Fail:  {success_count}/{fail_count} (Error Rate: {fail_count/len(results)*100:.1f}%)")
    print(f"  Status Codes:  {status_codes}")
    print(f"  Latency P50:   {p50:.1f} ms")
    print(f"  Latency P95:   {p95:.1f} ms")
    print(f"  Latency P99:   {p99:.1f} ms")
    print(f"  Min / Max:     {min(latencies):.1f} ms / {max(latencies):.1f} ms")

    return {
        "concurrency": concurrency_level,
        "scenario": scenario,
        "total_requests": total_requests,
        "wall_time_s": round(total_wall_time, 2),
        "rps": round(rps, 1),
        "error_rate_pct": round(fail_count / len(results) * 100, 2),
        "status_codes": status_codes,
        "p50_ms": round(p50, 1),
        "p95_ms": round(p95, 1),
        "p99_ms": round(p99, 1),
    }

# Execute Progressive Load Tiers
report_data = []

# Tier 1: 50 Users Browsing
report_data.append(run_load_tier(50, 100, "hotel_browse"))

# Tier 2: 100 Users Hotel Details
report_data.append(run_load_tier(100, 200, "hotel_detail"))

# Tier 3: 250 Users Room Availability
report_data.append(run_load_tier(250, 500, "room_availability"))

# Tier 4: 50 Concurrent Booking Stress Test on 1 Available Room!
print("\n================================================================================")
print("CONCURRENCY COLLISION STRESS TEST (Zero Double-Booking Verification)")
print("================================================================================")
stress_result = run_load_tier(50, 50, "booking_concurrency_stress")
report_data.append(stress_result)

# Verify Staging Database State Post Stress Test
cin_check = date.today() + timedelta(days=40)
cout_check = date.today() + timedelta(days=42)
confirmed_bookings = Booking.objects.filter(
    room=stress_room,
    check_in=cin_check,
    check_out=cout_check
).count()

print(f"\n[VERIFICATION] Total room units available in inventory: 1")
print(f"[VERIFICATION] Total confirmed/pending bookings created in DB: {confirmed_bookings}")
if confirmed_bookings == 1:
    print("[SUCCESS] ZERO DOUBLE BOOKINGS! Mutex lock and select_for_update prevented overselling.")
else:
    print(f"[FAILURE] OVERSELLING DETECTED! Confirmed bookings = {confirmed_bookings}")

# Clean up staging database
connection.close()
if os.path.exists(STAGING_DB):
    try:
        os.remove(STAGING_DB)
        print("\nStaging test database db.sqlite3.staging_loadtest successfully cleaned up.")
    except Exception as e:
        print("Note on cleanup:", e)

# Export summary JSON for report generation
import json
with open("scratch_load_test_results.json", "w") as f:
    json.dump({"metrics": report_data, "double_booking_prevented": confirmed_bookings == 1}, f, indent=2)

print("\nLoad test execution complete. Results saved to scratch_load_test_results.json.")
