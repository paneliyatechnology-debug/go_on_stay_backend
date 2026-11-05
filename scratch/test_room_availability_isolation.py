import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import django
from decimal import Decimal
from datetime import date, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking

User = get_user_model()

def run_tests():
    print("\n" + "="*80)
    print("RUNNING ROOM AVAILABILITY ISOLATION & DATE-WISE PERSISTENCE TEST SUITE")
    print("="*80)

    client = APIClient()

    # 1. Setup Users
    owner, _ = User.objects.get_or_create(
        username="owner_avail_test",
        defaults={
            "email": "owner_avail@example.com",
            "role": "HOTEL_OWNER",
            "is_active": True,
            "is_blocked": False
        }
    )
    cust1, _ = User.objects.get_or_create(
        username="cust1_avail_test",
        defaults={"email": "cust1_avail@example.com", "role": "CUSTOMER", "is_active": True}
    )
    cust2, _ = User.objects.get_or_create(
        username="cust2_avail_test",
        defaults={"email": "cust2_avail@example.com", "role": "CUSTOMER", "is_active": True}
    )

    # 2. Setup Hotel with 3 distinct Rooms
    hotel, _ = Hotel.objects.get_or_create(
        name="The Grand Palace Hotel",
        defaults={
            "owner": owner,
            "city": "Jaipur",
            "address": "MI Road, Jaipur",
            "star_rating": 5,
            "is_approved": True,
            "status": Hotel.STATUS_APPROVED
        }
    )

    # Room 101
    room_101, _ = Room.objects.get_or_create(
        hotel=hotel,
        title="Room 101",
        defaults={
            "price_per_night": Decimal('3000.00'),
            "capacity_adults": 2,
            "total_rooms": 1,
            "room_numbers": "101"
        }
    )

    # Room 102
    room_102, _ = Room.objects.get_or_create(
        hotel=hotel,
        title="Room 102",
        defaults={
            "price_per_night": Decimal('3500.00'),
            "capacity_adults": 2,
            "total_rooms": 1,
            "room_numbers": "102"
        }
    )

    # Room 103 (Multi-unit category)
    room_suite, _ = Room.objects.get_or_create(
        hotel=hotel,
        title="Royal Executive Suite",
        defaults={
            "price_per_night": Decimal('5000.00'),
            "capacity_adults": 3,
            "total_rooms": 2,
            "room_numbers": "Suite 201, Suite 202"
        }
    )

    # Cleanup old test bookings for these rooms
    Booking.objects.filter(hotel=hotel).delete()

    # Dates as specified in user prompt: 05-11-2026 to 06-11-2026
    cin_str = "2026-11-05"
    cout_str = "2026-11-06"
    cin_indian = "05-11-2026"
    cout_indian = "06-11-2026"

    # Step A: Before any booking, both rooms and hotel are available
    res_initial = client.get(f'/api/rooms/check-availability/?hotel_id={hotel.id}&check_in={cin_indian}&check_out={cout_indian}')
    assert res_initial.status_code == 200, f"Failed initial hotel check: {res_initial.data}"
    assert res_initial.data["available"] is True
    assert res_initial.data["total_available_rooms"] == 4
    print("[PASS] Step A: Before booking, Hotel is AVAILABLE with all 4 physical rooms free.")

    # Step B: Customer 1 books Room 101 for 05-11-2026 to 06-11-2026
    booking_101 = Booking.objects.create(
        booking_id="TEST-BK-101-AVAIL",
        customer=cust1,
        hotel=hotel,
        room=room_101,
        room_number="101",
        check_in=date(2026, 11, 5),
        check_out=date(2026, 11, 6),
        number_of_rooms=1,
        number_of_guests=2,
        price_per_night=Decimal('3000.00'),
        number_of_nights=1,
        subtotal=Decimal('3000.00'),
        total_amount=Decimal('3540.00'),
        booking_status=Booking.STATUS_CONFIRMED,
        payment_status=Booking.PAYMENT_PAID,
        guest_name="Guest Alpha",
        guest_email="alpha@example.com",
        guest_phone="9876543210"
    )
    print(f"[PASS] Step B: Room 101 booked & confirmed for {cin_indian} to {cout_indian}.")

    # Step C: Verify Hotel Availability Endpoint (Case A: hotel_id)
    # Both YYYY-MM-DD and DD-MM-YYYY formats should work identically
    for c_in, c_out, fmt_name in [(cin_str, cout_str, "ISO YYYY-MM-DD"), (cin_indian, cout_indian, "Indian DD-MM-YYYY")]:
        res_hotel = client.get(f'/api/rooms/check-availability/?hotel_id={hotel.id}&check_in={c_in}&check_out={c_out}')
        assert res_hotel.status_code == 200
        data = res_hotel.data
        
        # 1. ENTIRE HOTEL IS NOT UNAVAILABLE:
        assert data["available"] is True, f"Entire hotel was falsely marked unavailable ({fmt_name})!"
        assert data["is_available"] is True
        assert data["total_available_rooms"] == 3

        # 2. Room 101 is UNAVAILABLE:
        r101_item = next(r for r in data["rooms"] if r["room_id"] == room_101.id)
        assert r101_item["available"] is False, f"Room 101 should be unavailable ({fmt_name})!"
        assert r101_item["is_available"] is False
        assert r101_item["remaining"] == 0

        # 3. Room 102 in same hotel is AVAILABLE:
        r102_item = next(r for r in data["rooms"] if r["room_id"] == room_102.id)
        assert r102_item["available"] is True, f"Room 102 should be available ({fmt_name})!"
        assert r102_item["is_available"] is True
        assert r102_item["remaining"] == 1

        # 4. Room Suite in same hotel is AVAILABLE:
        rsuite_item = next(r for r in data["rooms"] if r["room_id"] == room_suite.id)
        assert rsuite_item["available"] is True
        assert rsuite_item["remaining"] == 2

        print(f"[PASS] Step C ({fmt_name}): Hotel is AVAILABLE, Room 101 is UNAVAILABLE (0), Room 102 is AVAILABLE (1), Suite is AVAILABLE (2).")

    # Step D: Verify Specific Room Availability Endpoint (Case B: room_id)
    res_r101 = client.get(f'/api/rooms/check-availability/?room_id={room_101.id}&check_in={cin_indian}&check_out={cout_indian}')
    assert res_r101.status_code == 200
    assert res_r101.data["available"] is False
    assert res_r101.data["remaining"] == 0
    assert res_r101.data["room_numbers"][0]["is_available"] is False
    assert res_r101.data["room_numbers"][0]["status"] == "RESERVED"
    print("[PASS] Step D1: Specific room_id query for Room 101 returns available=False, remaining=0, status=RESERVED.")

    res_r102 = client.get(f'/api/rooms/check-availability/?room_id={room_102.id}&check_in={cin_indian}&check_out={cout_indian}')
    assert res_r102.status_code == 200
    assert res_r102.data["available"] is True
    assert res_r102.data["remaining"] == 1
    assert res_r102.data["room_numbers"][0]["is_available"] is True
    assert res_r102.data["room_numbers"][0]["status"] == "AVAILABLE"
    print("[PASS] Step D2: Specific room_id query for Room 102 returns available=True, remaining=1, status=AVAILABLE.")

    # Step E: Date-Wise Independence (Room 101 on different dates)
    # Next day: 07-11-2026 to 08-11-2026
    res_r101_next = client.get(f'/api/rooms/check-availability/?room_id={room_101.id}&check_in=2026-11-07&check_out=2026-11-08')
    assert res_r101_next.status_code == 200
    assert res_r101_next.data["available"] is True
    assert res_r101_next.data["remaining"] == 1
    print("[PASS] Step E: Date-wise isolation verified! Room 101 is freely AVAILABLE on non-overlapping dates (07-11-2026 to 08-11-2026).")

    # Step F: RoomsByHotelView list contract
    res_by_hotel = client.get(f'/api/rooms/by-hotel/{hotel.id}/?check_in={cin_indian}&check_out={cout_indian}')
    assert res_by_hotel.status_code == 200
    hotel_rooms = res_by_hotel.data.get('results', res_by_hotel.data)
    assert len(hotel_rooms) == 3, f"Expected all 3 room categories returned, got {len(hotel_rooms)}"
    r101_ser = next(r for r in hotel_rooms if r["id"] == room_101.id)
    r102_ser = next(r for r in hotel_rooms if r["id"] == room_102.id)
    assert r101_ser["is_available"] is False
    assert r101_ser["available_count"] == 0
    assert r102_ser["is_available"] is True
    assert r102_ser["available_count"] == 1
    print("[PASS] Step F1: RoomsByHotelView returns all rooms with accurate room-wise is_available flags.")

    # With ?available_only=true
    res_avail_only = client.get(f'/api/rooms/by-hotel/{hotel.id}/?check_in={cin_indian}&check_out={cout_indian}&available_only=true')
    avail_rooms = res_avail_only.data.get('results', res_avail_only.data)
    assert len(avail_rooms) == 2
    assert not any(r["id"] == room_101.id for r in avail_rooms)
    print("[PASS] Step F2: RoomsByHotelView with ?available_only=true safely filters out only the booked room.")

    # Step G: Concurrency & Overlapping Booking Prevention via API
    # Customer 2 attempts to book the booked Room 101 on overlapping dates
    client.force_authenticate(user=cust2)
    res_conflict = client.post('/api/bookings/', {
        "hotel": hotel.id,
        "room": room_101.id,
        "room_number": "101",
        "check_in": "2026-11-05",
        "check_out": "2026-11-06",
        "number_of_rooms": 1,
        "number_of_guests": 2,
        "guest_name": "Guest Beta",
        "guest_email": "beta@example.com",
        "guest_phone": "9811122233"
    }, format='json')
    assert res_conflict.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_409_CONFLICT], f"Expected rejection, got {res_conflict.status_code}: {res_conflict.data}"
    print(f"[PASS] Step G1: Overlapping booking on Room 101 successfully rejected ({res_conflict.status_code}).")

    # Customer 2 books Room 102 on those exact same dates -> SUCCEEDS!
    res_book_102 = client.post('/api/bookings/', {
        "hotel": hotel.id,
        "room": room_102.id,
        "room_number": "102",
        "check_in": "2026-11-05",
        "check_out": "2026-11-06",
        "number_of_rooms": 1,
        "number_of_guests": 2,
        "guest_name": "Guest Beta",
        "guest_email": "beta@example.com",
        "guest_phone": "9811122233"
    }, format='json')
    assert res_book_102.status_code == status.HTTP_201_CREATED, f"Booking Room 102 should succeed: {res_book_102.data}"
    bk_102_id = res_book_102.data["booking_id"]
    print("[PASS] Step G2: Booking Room 102 on the same dates succeeded with HTTP 201 Created!")

    # Complete payment/confirmation on Room 102 booking to reserve it in DB
    bk_102_obj = Booking.objects.get(booking_id=bk_102_id)
    bk_102_obj.booking_status = Booking.STATUS_CONFIRMED
    bk_102_obj.payment_status = Booking.PAYMENT_PAID
    bk_102_obj.save(update_fields=['booking_status', 'payment_status'])
    print("[PASS] Step G3: Room 102 booking payment verified & confirmed in database.")

    # Step H: Logout & Login Persistence Verification
    # Log out
    client.logout()
    res_anon = client.get(f'/api/rooms/check-availability/?hotel_id={hotel.id}&check_in={cin_indian}&check_out={cout_indian}')
    assert res_anon.status_code == 200
    assert res_anon.data["available"] is True # Room 103 Suite is still available!
    anon_r101 = next(r for r in res_anon.data["rooms"] if r["room_id"] == room_101.id)
    anon_r102 = next(r for r in res_anon.data["rooms"] if r["room_id"] == room_102.id)
    anon_suite = next(r for r in res_anon.data["rooms"] if r["room_id"] == room_suite.id)
    assert anon_r101["available"] is False
    assert anon_r102["available"] is False # confirmed in Step G3
    assert anon_suite["available"] is True
    print("[PASS] Step H1: Unauthenticated (Logged out) client receives correct database-driven availability.")

    # Log in as a completely different user
    client.force_authenticate(user=cust1)
    res_reauth = client.get(f'/api/rooms/check-availability/?hotel_id={hotel.id}&check_in={cin_indian}&check_out={cout_indian}')
    assert res_reauth.status_code == 200
    reauth_r101 = next(r for r in res_reauth.data["rooms"] if r["room_id"] == room_101.id)
    reauth_r102 = next(r for r in res_reauth.data["rooms"] if r["room_id"] == room_102.id)
    assert reauth_r101["available"] is False
    assert reauth_r102["available"] is False
    print("[PASS] Step H2: After re-login, database persistence confirms identical accurate date-wise availability.")

    print("\n" + "="*80)
    print("ALL ROOM AVAILABILITY ISOLATION TESTS PASSED 100%!")
    print("="*80 + "\n")

if __name__ == '__main__':
    run_tests()
