import os
import sys
import django

# Setup Django environment
sys.path.append(os.path.abspath('.'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from rest_framework.exceptions import ValidationError
from util.validators import validate_hotel_name, validate_hotel_address
from hotels.serializers import HotelCreateUpdateSerializer
from hotels.models import Hotel
from users.models import User
from rest_framework.test import APIClient

print("=== STARTING HOTEL NAME & ADDRESS VALIDATION TESTS ===")

# TEST 1: Direct validate_hotel_name tests
print("\n[TEST 1] Testing validate_hotel_name...")

# 1a. Names with numbers, pure numeric, symbols, or too short -> Must FAIL
invalid_names = [
    "12345",
    "999999",
    "007",
    "Hotel 123",            # Contains numbers
    "Taj 7 Seasons",         # Contains numbers
    "Studio 54 Suites",      # Contains numbers
    "Room 101 Boutique",     # Contains numbers
    "#123-456",
    "---999---",
    "",
    "   ",
    "ab",                    # Too short
    "Hotel @ Grand",         # Invalid symbol
]

for name in invalid_names:
    try:
        validate_hotel_name(name)
        assert False, f"Expected ValidationError for invalid hotel name '{name}', but it passed!"
    except ValidationError as e:
        print(f"  [PASS] Rejected invalid name '{name}': {e.detail}")

# 1b. Valid names (ONLY letters, spaces, hyphens, dots, apostrophes, ampersands) -> Must PASS
valid_names = [
    "Hotel Taj Palace",
    "The Grand Resort",
    "ITC Rajputana Luxury Collection",
    "Ocean View Resort & Spa",
    "St. Regis Hotel",
    "Oberoi Grand",
]

for name in valid_names:
    try:
        clean = validate_hotel_name(name)
        assert clean == name.strip()
        print(f"  [PASS] Accepted valid hotel name: '{clean}'")
    except ValidationError as e:
        assert False, f"Unexpected ValidationError for valid hotel name '{name}': {e}"


# TEST 2: Direct validate_hotel_address tests
print("\n[TEST 2] Testing validate_hotel_address...")

# 2a. Invalid addresses (pure numbers, symbols only, too short) -> Must FAIL
invalid_addresses = [
    "12345",
    "999999",
    "   1234567   ",
    ",,,---...",
    "MG", # too short
    "",
    "    ",
]

for addr in invalid_addresses:
    try:
        validate_hotel_address(addr)
        assert False, f"Expected ValidationError for invalid address '{addr}', but it passed!"
    except ValidationError as e:
        print(f"  [PASS] Rejected invalid address '{addr}': {e.detail}")

# 2b. Valid addresses (both numbers and letters allowed - alphanumeric) -> Must PASS
valid_addresses = [
    "Plot 42, MG Road, Near City Mall",
    "123 Main Street, Sector 15",
    "Flat 402, Sunshine Heights, Civil Lines",
    "Opposite Central Bus Station, Station Road",
    "45/A Marine Drive, Nariman Point",
    "5/1 Fine Nagar Society, Uttamnagar Road, Nikol",
]

for addr in valid_addresses:
    try:
        clean = validate_hotel_address(addr)
        assert clean == addr.strip()
        print(f"  [PASS] Accepted valid address: '{clean}'")
    except ValidationError as e:
        assert False, f"Unexpected ValidationError for valid address '{addr}': {e}"


# TEST 3: Serializer validation (HotelCreateUpdateSerializer)
print("\n[TEST 3] Testing HotelCreateUpdateSerializer...")

# 3a. Serializer rejects hotel name with numbers
ser_bad_name1 = HotelCreateUpdateSerializer(data={
    "name": "12345678",
    "address": "Plot 42, MG Road, Near City Mall",
    "city": "Jaipur",
    "state": "Rajasthan",
    "zip_code": "302001",
    "property_type": "HOTEL",
    "description": "A wonderful stay experience in Jaipur."
})
assert not ser_bad_name1.is_valid(), "Serializer should reject numeric hotel name!"
assert 'name' in ser_bad_name1.errors, f"Expected 'name' in errors, got {ser_bad_name1.errors}"
print(f"  [PASS] Serializer rejected purely numeric hotel name: {ser_bad_name1.errors['name']}")

ser_bad_name2 = HotelCreateUpdateSerializer(data={
    "name": "Hotel 7 Seasons",
    "address": "Plot 42, MG Road, Near City Mall",
    "city": "Jaipur",
    "state": "Rajasthan",
    "zip_code": "302001",
    "property_type": "HOTEL",
    "description": "A wonderful stay experience in Jaipur."
})
assert not ser_bad_name2.is_valid(), "Serializer should reject hotel name containing numbers!"
assert 'name' in ser_bad_name2.errors, f"Expected 'name' in errors, got {ser_bad_name2.errors}"
print(f"  [PASS] Serializer rejected hotel name with numbers: {ser_bad_name2.errors['name']}")

# 3b. Serializer rejects numeric address
ser_bad_addr = HotelCreateUpdateSerializer(data={
    "name": "Hotel Royal Orchid",
    "address": "987654321",
    "city": "Jaipur",
    "state": "Rajasthan",
    "zip_code": "302001",
    "property_type": "HOTEL",
    "description": "A wonderful stay experience in Jaipur."
})
assert not ser_bad_addr.is_valid(), "Serializer should reject numeric address!"
assert 'address' in ser_bad_addr.errors, f"Expected 'address' in errors, got {ser_bad_addr.errors}"
print(f"  [PASS] Serializer rejected purely numeric address: {ser_bad_addr.errors['address']}")

# 3c. Serializer accepts valid hotel with letters-only name and alphanumeric address
ser_valid = HotelCreateUpdateSerializer(data={
    "name": "Grand Seasons Luxury Resort",
    "address": "Plot 104, Sector 29, Near City Center",
    "city": "Gurugram",
    "state": "Haryana",
    "zip_code": "122001",
    "property_type": "HOTEL",
    "description": "Luxury 4-star boutique hotel with world-class amenities."
})
assert ser_valid.is_valid(), f"Serializer should accept valid hotel, errors: {ser_valid.errors}"
print(f"  [PASS] Serializer accepted valid hotel: '{ser_valid.validated_data['name']}' at '{ser_valid.validated_data['address']}'")


# TEST 4: Full API Integration via Django Test Client across all endpoints
print("\n[TEST 4] Testing Full API Integration across endpoints...")
client = APIClient()
owner_user = User.objects.filter(role__in=['HOTEL_OWNER', 'ADMIN']).first()
if not owner_user:
    owner_user = User.objects.filter(is_superuser=True).first()
client.force_authenticate(user=owner_user)

# 4a. POST /api/hotels/owner/hotels/ with numeric name -> 400
res_api1 = client.post('/api/hotels/owner/hotels/', {
    "name": "999888777",
    "address": "Plot 55, Civil Lines",
    "city": "Jaipur",
    "state": "Rajasthan",
    "zip_code": "302006",
    "property_type": "HOTEL",
    "description": "Sample test hotel"
}, format='json')
assert res_api1.status_code == 400, f"Expected 400, got {res_api1.status_code}"
assert 'name' in res_api1.data
print(f"  [PASS] /api/hotels/owner/hotels/ rejected numeric name: {res_api1.data['name']}")

# 4b. POST /api/hotels/owner/ (new route) with name containing numbers -> 400
res_api2 = client.post('/api/hotels/owner/', {
    "name": "Hotel Taj 123",
    "address": "Plot 55, Civil Lines",
    "city": "Jaipur",
    "state": "Rajasthan",
    "zip_code": "302006",
    "property_type": "HOTEL",
    "description": "Sample test hotel"
}, format='json')
assert res_api2.status_code == 400, f"Expected 400, got {res_api2.status_code}"
assert 'name' in res_api2.data
print(f"  [PASS] /api/hotels/owner/ rejected name with numbers: {res_api2.data['name']}")

# 4c. POST /api/hotels/owner/hotels/ with numeric address -> 400
res_api3 = client.post('/api/hotels/owner/hotels/', {
    "name": "Hotel Grand Heritage",
    "address": "12345678",
    "city": "Jaipur",
    "state": "Rajasthan",
    "zip_code": "302006",
    "property_type": "HOTEL",
    "description": "Sample test hotel"
}, format='json')
assert res_api3.status_code == 400, f"Expected 400, got {res_api3.status_code}"
assert 'address' in res_api3.data
print(f"  [PASS] /api/hotels/owner/hotels/ rejected numeric address: {res_api3.data['address']}")

# 4d. POST /api/hotels/owner/hotels/ with valid hotel -> 201
res_api4 = client.post('/api/hotels/owner/hotels/', {
    "name": "Wonders Grand Heritage Haveli",
    "address": "Shop 12-14, Ground Floor, GT Road, Near Clock Tower",
    "city": "Amritsar",
    "state": "Punjab",
    "zip_code": "143001",
    "property_type": "HOTEL",
    "description": "Splendid stay near Golden Temple with modern amenities."
}, format='json')
assert res_api4.status_code == 201, f"Expected 201, got {res_api4.status_code}: {res_api4.data}"
hotel_id = res_api4.data['id']
print(f"  [PASS] Created valid hotel ID {hotel_id} with name '{res_api4.data['name']}' and alphanumeric address '{res_api4.data['address']}'")

# 4e. PATCH /api/hotels/<id>/ with numeric name -> 400
res_api5 = client.patch(f'/api/hotels/{hotel_id}/', {
    "name": "55555"
}, format='json')
assert res_api5.status_code == 400, f"Expected 400, got {res_api5.status_code}"
print(f"  [PASS] PATCH /api/hotels/{hotel_id}/ rejected numeric name: {res_api5.data['name']}")

# 4f. PATCH /api/hotels/<id>/ with numeric address -> 400
res_api6 = client.patch(f'/api/hotels/{hotel_id}/', {
    "address": "999888"
}, format='json')
assert res_api6.status_code == 400, f"Expected 400, got {res_api6.status_code}"
print(f"  [PASS] PATCH /api/hotels/{hotel_id}/ rejected numeric address: {res_api6.data['address']}")

# 4g. Clean up created hotel
Hotel.objects.filter(id=hotel_id).delete()
print(f"  [CLEANUP] Deleted test hotel ID {hotel_id}")

print("\n=== ALL HOTEL VALIDATION TESTS PASSED 100%! ===")
