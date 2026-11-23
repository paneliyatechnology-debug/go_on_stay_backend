import os
import sys
import time
import json
import shutil
import ctypes
import statistics
import concurrent.futures
from decimal import Decimal
from datetime import date, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# RULE ZERO: Isolated Staging Load Test Database
STAGING_DB = os.path.join(BASE_DIR, "db.sqlite3.staging_500load")
if os.path.exists(STAGING_DB):
    try:
        os.remove(STAGING_DB)
    except Exception:
        pass

# Copy from genuine db.sqlite3 to staging loadtest DB
shutil.copyfile(os.path.join(BASE_DIR, "db.sqlite3"), STAGING_DB)

os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()

from django.conf import settings
settings.DATABASES['default']['NAME'] = STAGING_DB

from django.db import connection
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from users.models import User
from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking

# System Memory & CPU Helper
class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ('dwLength', ctypes.c_ulong),
        ('dwMemoryLoad', ctypes.c_ulong),
        ('ullTotalPhys', ctypes.c_ulonglong),
        ('ullAvailPhys', ctypes.c_ulonglong),
        ('ullTotalPageFile', ctypes.c_ulonglong),
        ('ullAvailPageFile', ctypes.c_ulonglong),
        ('ullTotalVirtual', ctypes.c_ulonglong),
        ('ullAvailVirtual', ctypes.c_ulonglong),
        ('sullAvailExtendedVirtual', ctypes.c_ulonglong),
    ]

def get_system_metrics():
    stat = MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
    ram_load_pct = stat.dwMemoryLoad
    total_ram_gb = round(stat.ullTotalPhys / (1024**3), 2)
    avail_ram_gb = round(stat.ullAvailPhys / (1024**3), 2)
    return {
        "ram_load_pct": ram_load_pct,
        "total_ram_gb": total_ram_gb,
        "avail_ram_gb": avail_ram_gb,
    }

print("================================================================================")
print("GOONSTAY 500 CONCURRENT USER LOAD TEST HARNESS (AUDIT 02)")
print(f"Target: Isolated Staging Database ({os.path.basename(STAGING_DB)})")
print("================================================================================")

connection.close()

# 1. Pre-generate 500 distinct authenticated virtual users
print("[SETUP] Creating pool of 500 distinct authenticated staging virtual users...")
users_to_create = []
existing_emails = set(User.objects.values_list('email', flat=True))

for i in range(500):
    email = f"loaduser_500_{i}@staging.goonstay.com"
    if email not in existing_emails:
        u = User(
            username=f"loaduser_500_{i}",
            email=email,
            role="CUSTOMER",
            is_active=True
        )
        u.set_password("StagingLoadPass2026!")
        users_to_create.append(u)

if users_to_create:
    User.objects.bulk_create(users_to_create)

virtual_users = list(User.objects.filter(email__startswith="loaduser_500_").order_by('id')[:500])
print(f"[SETUP] Successfully loaded {len(virtual_users)} authenticated virtual users.")

# Generate JWT tokens for each user
user_tokens = []
for u in virtual_users:
    token = str(RefreshToken.for_user(u).access_token)
    user_tokens.append(token)

print(f"[SETUP] Pre-computed {len(user_tokens)} JWT access tokens.")

# Prepare benchmark targets
sample_hotel = Hotel.objects.first()
sample_room = Room.objects.filter(hotel=sample_hotel).first()

# Scenarios to test at 500 concurrency:
# 1. Hotel Browse (/api/hotels/)
# 2. Hotel Detail (/api/hotels/<id>/)
# 3. Room Availability (/api/rooms/<id>/availability/)
# 4. Customer Dashboard (/api/bookings/my-bookings/)
# 5. Booking Workflow (/api/bookings/ hold request)

scenarios = [
    {
        "name": "hotel_browsing",
        "method": "GET",
        "url": "/api/hotels/",
        "data_builder": None,
        "auth": True
    },
    {
        "name": "hotel_detail",
        "method": "GET",
        "url": f"/api/hotels/{sample_hotel.id}/",
        "data_builder": None,
        "auth": True
    },
    {
        "name": "room_availability",
        "method": "GET",
        "url": f"/api/rooms/availability/?room_id={sample_room.id}&check_in=2026-12-10&check_out=2026-12-14",
        "data_builder": None,
        "auth": True
    },
    {
        "name": "customer_dashboard",
        "method": "GET",
        "url": "/api/bookings/",
        "data_builder": None,
        "auth": True
    },
    {
        "name": "booking_workflow",
        "method": "POST",
        "url": "/api/bookings/",
        "data_builder": lambda idx: {
            "hotel": sample_hotel.id,
            "room": sample_room.id,
            "check_in": "2026-12-20",
            "check_out": "2026-12-22",
            "number_of_guests": 2,
            "number_of_rooms": 1,
            "guest_name": f"Load Guest {idx}",
            "guest_email": f"loaduser_500_{idx}@staging.goonstay.com",
            "guest_phone": "9876543210"
        },
        "auth": True
    }
]

benchmark_results = []

for sc in scenarios:
    sc_name = sc["name"]
    concurrency = 500
    total_requests = 500
    print(f"\n--- Running 500-User Scenario: {sc_name} (500 requests at 500 concurrency) ---")
    
    initial_sys = get_system_metrics()
    cpu_start = time.process_time()
    t_start = time.time()
    
    latencies_ms = []
    status_counts = {}
    errors = 0

    def execute_request(idx):
        client = APIClient()
        token = user_tokens[idx % len(user_tokens)]
        if sc["auth"]:
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        
        req_start = time.perf_counter()
        try:
            if sc["method"] == "GET":
                resp = client.get(sc["url"])
            else:
                payload = sc["data_builder"](idx)
                resp = client.post(sc["url"], payload, format="json")
            req_time = (time.perf_counter() - req_start) * 1000
            return resp.status_code, req_time, None
        except Exception as e:
            req_time = (time.perf_counter() - req_start) * 1000
            return 500, req_time, str(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(execute_request, i) for i in range(total_requests)]
        for f in concurrent.futures.as_completed(futures):
            status_code, req_time, err = f.result()
            latencies_ms.append(req_time)
            status_counts[status_code] = status_counts.get(status_code, 0) + 1
            if err or status_code >= 500:
                errors += 1

    wall_time = time.time() - t_start
    cpu_duration = time.process_time() - cpu_start
    final_sys = get_system_metrics()
    
    latencies_ms.sort()
    rps = round(total_requests / wall_time, 1)
    err_rate = round((errors / total_requests) * 100, 2)
    p50 = round(statistics.median(latencies_ms), 1)
    p95 = round(latencies_ms[int(len(latencies_ms) * 0.95)], 1)
    p99 = round(latencies_ms[int(len(latencies_ms) * 0.99)], 1)
    max_ms = round(max(latencies_ms), 1)
    min_ms = round(min(latencies_ms), 1)

    print(f"  Wall Time:     {wall_time:.2f}s | CPU Time: {cpu_duration:.2f}s")
    print(f"  Throughput:    {rps} req/sec")
    print(f"  Success/Fail:  {total_requests - errors}/{errors} (Error Rate: {err_rate}%)")
    print(f"  Status Codes:  {status_counts}")
    print(f"  Latency P50:   {p50} ms | P95: {p95} ms | P99: {p99} ms | Max: {max_ms} ms")
    print(f"  RAM Load:      {final_sys['ram_load_pct']}% (Avail: {final_sys['avail_ram_gb']} GB)")

    benchmark_results.append({
        "scenario": sc_name,
        "concurrency": concurrency,
        "total_requests": total_requests,
        "wall_time_s": round(wall_time, 2),
        "cpu_time_s": round(cpu_duration, 2),
        "rps": rps,
        "error_rate_pct": err_rate,
        "status_codes": status_counts,
        "p50_ms": p50,
        "p95_ms": p95,
        "p99_ms": p99,
        "min_ms": min_ms,
        "max_ms": max_ms,
        "system_metrics": {
            "initial_ram_load_pct": initial_sys["ram_load_pct"],
            "final_ram_load_pct": final_sys["ram_load_pct"],
            "avail_ram_gb": final_sys["avail_ram_gb"],
            "postgres_connections": 0, # SQLite isolation staging
            "redis_status": "in-memory-fallback"
        }
    })

# Save JSON results
output_file = os.path.join(BASE_DIR, "scratch_audit02_500_load_results.json")
with open(output_file, "w") as f:
    json.dump({"benchmark_results": benchmark_results}, f, indent=2)

print(f"\n[AUDIT 02 COMPLETE] Results written to {output_file}")

# Clean up staging db
connection.close()
if os.path.exists(STAGING_DB):
    try:
        os.remove(STAGING_DB)
        print("[CLEANUP] Isolated staging loadtest database removed cleanly.")
    except Exception as e:
        print(f"[CLEANUP NOTE] {e}")
