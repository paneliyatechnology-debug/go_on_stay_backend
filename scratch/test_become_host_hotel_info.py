import os
import sys
import django

sys.path.append(os.path.abspath('.'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from rest_framework.test import APIClient
from users.models import User
from hotels.models import Hotel
import uuid

client = APIClient()

print("=== TESTING BECOME A HOST WITH HOTEL PROPERTY INFO (SCREENSHOT MATCH) ===")

# TEST 1: Become a host with NUMBERS in hotel name -> MUST FAIL (400)
print("\n[TEST 1] Registering host with numbers in hotel_name ('Royal Palace 123')...")
rand_id = uuid.uuid4().hex[:6]
res1 = client.post('/api/users/become-host/', {
    "first_name": "Rajesh",
    "last_name": "Sharma",
    "email": f"host_test_{rand_id}@example.com",
    "password": "Password123!",
    "phone_number": f"98522{uuid.uuid4().int % 100000:05d}",
    "property_type": "Hotel",
    "hotel_name": "Royal Palace 123", # contains numbers!
    "destination_city": "Udaipur, Rajasthan",
    "full_property_address": "Plot 45, Pichola Lake Road, Udaipur"
}, format='json')

assert res1.status_code == 400, f"Expected 400, got {res1.status_code}: {res1.data}"
assert 'hotel_name' in res1.data, f"Expected 'hotel_name' in errors: {res1.data}"
print(f"  [PASS] Rejected numbers in hotel_name: {res1.data['hotel_name']}")


# TEST 2: Become a host with purely numeric address -> MUST FAIL (400)
print("\n[TEST 2] Registering host with purely numeric address ('123456')...")
rand_id2 = uuid.uuid4().hex[:6]
res2 = client.post('/api/users/become-host/', {
    "first_name": "Rajesh",
    "last_name": "Sharma",
    "email": f"host_test_{rand_id2}@example.com",
    "password": "Password123!",
    "phone_number": f"98522{uuid.uuid4().int % 100000:05d}",
    "property_type": "Hotel",
    "hotel_name": "Royal Heritage Palace & Resort",
    "destination_city": "Udaipur, Rajasthan",
    "full_property_address": "123456" # purely numeric address!
}, format='json')

assert res2.status_code == 400, f"Expected 400, got {res2.status_code}: {res2.data}"
assert 'address' in res2.data, f"Expected 'address' in errors: {res2.data}"
print(f"  [PASS] Rejected numeric address: {res2.data['address']}")


# TEST 3: Become a host with exact details from Screenshot -> MUST SUCCEED (201)
print("\n[TEST 3] Registering host with exact data from screenshot...")
rand_id3 = uuid.uuid4().hex[:6]
phone_clean = f"98522{uuid.uuid4().int % 100000:05d}"
user_email = f"rajesh.sharma.{rand_id3}@example.com"
res3 = client.post('/api/users/become-host/', {
    "first_name": "Rajesh",
    "last_name": "Sharma",
    "email": user_email,
    "password": "Password123!",
    "phone_number": phone_clean,
    "property_type": "Hotel",
    "hotel_name": "Royal Heritage Palace & Resort",
    "destination_city": "Udaipur, Rajasthan",
    "full_property_address": "Plot 45, Pichola Lake Road, Udaipur"
}, format='json')

assert res3.status_code == 201, f"Expected 201 Created, got {res3.status_code}: {res3.data}"
assert 'user' in res3.data, f"Response should contain 'user': {res3.data}"
assert 'hotel' in res3.data, f"Response should contain 'hotel': {res3.data}"

user_data = res3.data['user']
hotel_data = res3.data['hotel']

print(f"  [PASS] Successfully registered host: {user_data['first_name']} {user_data['last_name']} (Role: {user_data['role']})")
print(f"  [PASS] Successfully created Hotel: '{hotel_data['name']}' in '{hotel_data['city']}', '{hotel_data['state']}'")
print(f"         Address: '{hotel_data['address']}' | Status: '{hotel_data['status']}'")

# Clean up
Hotel.objects.filter(id=hotel_data['id']).delete()
User.objects.filter(id=user_data['id']).delete()
print("  [CLEANUP] Deleted test host and hotel records.")

print("\n=== ALL BECOME A HOST TESTS PASSED 100%! ===")

