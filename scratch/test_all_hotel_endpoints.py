import os
import sys
import django

sys.path.append(os.path.abspath('.'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from rest_framework.test import APIClient
from users.models import User
from hotels.models import Hotel

client = APIClient()

# Get or create an owner user
owner = User.objects.filter(role__in=['HOTEL_OWNER', 'ADMIN']).first()
if not owner:
    owner = User.objects.filter(is_superuser=True).first()

client.force_authenticate(user=owner)

print(f"Testing with user: {owner.username} (role: {owner.role})")

# Test URL 1: /api/hotels/owner/hotels/
print("\n--- TEST 1: POST /api/hotels/owner/hotels/ ---")
res1 = client.post('/api/hotels/owner/hotels/', {
    "name": "123456",
    "address": "Plot 42, MG Road",
    "city": "Jaipur",
    "state": "Rajasthan",
    "zip_code": "302001",
    "property_type": "HOTEL",
    "description": "Test numeric name"
}, format='json')
print(f"Status: {res1.status_code}")
print(f"Response: {res1.data}")

# Test URL 2: /api/hotels/owner/
print("\n--- TEST 2: POST /api/hotels/owner/ ---")
res2 = client.post('/api/hotels/owner/', {
    "name": "123456",
    "address": "Plot 42, MG Road",
    "city": "Jaipur",
    "state": "Rajasthan"
}, format='json')
print(f"Status: {res2.status_code}")
print(f"Response: {res2.data if hasattr(res2, 'data') else res2.content}")

# Test URL 3: /api/hotels/
print("\n--- TEST 3: POST /api/hotels/ ---")
res3 = client.post('/api/hotels/', {
    "name": "123456",
    "address": "Plot 42, MG Road",
    "city": "Jaipur",
    "state": "Rajasthan",
    "zip_code": "302001",
    "property_type": "HOTEL",
    "description": "Test numeric name"
}, format='json')
print(f"Status: {res3.status_code}")
print(f"Response: {res3.data}")

# Test URL 4: PATCH /api/hotels/<id>/
hotel = Hotel.objects.first()
if hotel:
    print(f"\n--- TEST 4: PATCH /api/hotels/{hotel.id}/ ---")
    res4 = client.patch(f'/api/hotels/{hotel.id}/', {
        "name": "999999"
    }, format='json')
    print(f"Status: {res4.status_code}")
    print(f"Response: {res4.data}")

    print(f"\n--- TEST 5: PATCH /api/hotels/{hotel.id}/ with numeric address ---")
    res5 = client.patch(f'/api/hotels/{hotel.id}/', {
        "address": "123456"
    }, format='json')
    print(f"Status: {res5.status_code}")
    print(f"Response: {res5.data}")

