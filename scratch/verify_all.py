import os
import sys
import django

sys.path.append(os.path.abspath('.'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.core.management import call_command
from rest_framework.test import APIClient
from hotels.models import Hotel
from users.models import User

print("1. Running Django system check...")
call_command('check')
print("   -> System check passed with 0 issues!")

print("\n2. Testing Hotel Name and Address Validations across endpoints...")
client = APIClient()
owner = User.objects.filter(role__in=['HOTEL_OWNER', 'ADMIN']).first()
if not owner:
    owner = User.objects.filter(is_superuser=True).first()
client.force_authenticate(user=owner)

# A: Reject hotel name with numbers
res1 = client.post('/api/hotels/owner/hotels/', {
    "name": "Hotel Taj 123",
    "address": "Plot 42, MG Road",
    "city": "Jaipur",
    "state": "Rajasthan",
    "zip_code": "302001",
    "property_type": "HOTEL",
    "description": "Test hotel with number in name"
}, format='json')
assert res1.status_code == 400, f"Expected 400, got {res1.status_code}"
assert "Numbers are not allowed in hotel name" in str(res1.data)
print("   -> Successfully rejected hotel name containing numbers ('Hotel Taj 123')")

# B: Reject purely numeric hotel name
res2 = client.post('/api/hotels/owner/hotels/', {
    "name": "999888777",
    "address": "Plot 42, MG Road",
    "city": "Jaipur",
    "state": "Rajasthan",
    "zip_code": "302001",
    "property_type": "HOTEL",
    "description": "Test numeric name"
}, format='json')
assert res2.status_code == 400, f"Expected 400, got {res2.status_code}"
assert "Numbers are not allowed in hotel name" in str(res2.data)
print("   -> Successfully rejected purely numeric hotel name ('999888777')")

# C: Reject purely numeric address
res3 = client.post('/api/hotels/owner/hotels/', {
    "name": "The Royal Orchid Palace",
    "address": "12345678",
    "city": "Jaipur",
    "state": "Rajasthan",
    "zip_code": "302001",
    "property_type": "HOTEL",
    "description": "Test numeric address"
}, format='json')
assert res3.status_code == 400, f"Expected 400, got {res3.status_code}"
assert "Address cannot be purely numeric" in str(res3.data)
print("   -> Successfully rejected purely numeric address ('12345678')")

# D: Accept valid letters-only hotel name with alphanumeric address
res4 = client.post('/api/hotels/owner/hotels/', {
    "name": "The Royal Orchid Palace",
    "address": "Plot 42, Sector 15, Near City Center",
    "city": "Jaipur",
    "state": "Rajasthan",
    "zip_code": "302001",
    "property_type": "HOTEL",
    "description": "Valid luxury boutique resort with modern facilities."
}, format='json')
assert res4.status_code == 201, f"Expected 201, got {res4.status_code}: {res4.data}"
created_hotel_id = res4.data['id']
print(f"   -> Successfully created hotel with letters-only name and alphanumeric address (ID: {created_hotel_id})")

# E: Test update via PATCH
res5 = client.patch(f'/api/hotels/{created_hotel_id}/', {
    "name": "Hotel 555"
}, format='json')
assert res5.status_code == 400
assert "Numbers are not allowed in hotel name" in str(res5.data)
print("   -> PATCH successfully rejected numeric name on existing hotel")

# Cleanup
Hotel.objects.filter(id=created_hotel_id).delete()
print("   -> Cleaned up test hotel")

print("\n3. Testing URL routes for Owner...")
# Test both /api/hotels/owner/ and /api/hotels/owner/hotels/
res_r1 = client.get('/api/hotels/owner/')
assert res_r1.status_code == 200, f"Expected 200 for /api/hotels/owner/, got {res_r1.status_code}"
res_r2 = client.get('/api/hotels/owner/hotels/')
assert res_r2.status_code == 200, f"Expected 200 for /api/hotels/owner/hotels/, got {res_r2.status_code}"
print("   -> Both '/api/hotels/owner/' and '/api/hotels/owner/hotels/' routes working perfectly (200 OK)!")

print("\n=======================================================")
print("ALL BACKEND CHECKS AND HOTEL VALIDATIONS WORKING 100%!")
print("=======================================================")

