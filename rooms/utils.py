import re
from django.db.models import Sum, Q
from django.utils import timezone
from bookings.models import Booking
from util.validators import parse_flexible_date


def auto_update_past_checkout_bookings():
    """
    Automatically updates any booking whose check_out date is past today
    from CONFIRMED or CHECKED_IN to CHECKED_OUT, restoring room availability.
    """
    try:
        today = timezone.now().date()
        Booking.objects.filter(
            booking_status__in=[Booking.STATUS_CONFIRMED, Booking.STATUS_CHECKED_IN],
            check_out__lt=today
        ).update(
            booking_status=Booking.STATUS_CHECKED_OUT,
            actual_check_out_at=timezone.now()
        )
    except Exception as e:
        print(f"[AutoCheckout] Error updating past checkout bookings: {e}")


def get_available_room_count(room, check_in_date, check_out_date):
    """
    Calculates remaining physical rooms available for a given date range.

    RULE: Only CONFIRMED, CHECKED_IN, and PAID bookings count as "reserved".
    PENDING_PAYMENT bookings do NOT block room availability — a room is only
    truly reserved after the customer completes payment successfully.

    Two date ranges overlap if:
    existing_check_in < requested_check_out AND existing_check_out > requested_check_in
    """
    # Auto-release rooms for past checkouts
    auto_update_past_checkout_bookings()

    all_nums = room.get_all_room_numbers() if hasattr(room, 'get_all_room_numbers') else []
    total_units = max(getattr(room, 'total_rooms', 1) or 1, len(all_nums))

    if not check_in_date or not check_out_date:
        return total_units

    cin = parse_flexible_date(check_in_date)
    cout = parse_flexible_date(check_out_date)

    if not cin or not cout or cout <= cin:
        return total_units

    # Active reservations: confirmed, checked-in, or paid (excluding cancelled, refunded, checked-out)
    overlapping_bookings = Booking.objects.filter(
        room=room,
        check_in__lt=cout,
        check_out__gt=cin
    ).filter(
        Q(booking_status__in=[Booking.STATUS_CONFIRMED, Booking.STATUS_CHECKED_IN, Booking.STATUS_COMPLETED]) |
        Q(payment_status=Booking.PAYMENT_PAID)
    ).exclude(
        booking_status__in=[
            Booking.STATUS_CANCELLED,
            Booking.STATUS_CHECKED_OUT,
            Booking.STATUS_REFUNDED,
            Booking.STATUS_EXPIRED,
        ]
    )

    booked_rooms_count = overlapping_bookings.aggregate(
        Sum('number_of_rooms')
    )['number_of_rooms__sum'] or 0

    available_count = max(0, total_units - booked_rooms_count)
    return available_count


def get_room_numbers_availability(room, check_in_date, check_out_date):
    """
    Returns a list of dicts for each physical room unit under this Room category:
    [
        {"number": "101", "is_available": False, "status": "RESERVED"},
        {"number": "102", "is_available": True, "status": "AVAILABLE"},
    ]
    """
    auto_update_past_checkout_bookings()
    all_nums = room.get_all_room_numbers()
    if not check_in_date or not check_out_date:
        return [{"number": str(n).strip(), "is_available": True, "status": "AVAILABLE"} for n in all_nums]

    cin = parse_flexible_date(check_in_date)
    cout = parse_flexible_date(check_out_date)
    if not cin or not cout or cout <= cin:
        return [{"number": str(n).strip(), "is_available": True, "status": "AVAILABLE"} for n in all_nums]

    active_bookings = Booking.objects.filter(
        room=room,
        check_in__lt=cout,
        check_out__gt=cin
    ).filter(
        Q(booking_status__in=[Booking.STATUS_CONFIRMED, Booking.STATUS_CHECKED_IN, Booking.STATUS_COMPLETED]) |
        Q(payment_status=Booking.PAYMENT_PAID)
    ).exclude(
        booking_status__in=[
            Booking.STATUS_CANCELLED,
            Booking.STATUS_CHECKED_OUT,
            Booking.STATUS_REFUNDED,
            Booking.STATUS_EXPIRED,
        ]
    )

    explicit_reserved = set()
    for b in active_bookings:
        if b.room_number:
            for num_item in str(b.room_number).split(','):
                cleaned = num_item.strip().lower()
                if cleaned:
                    explicit_reserved.add(cleaned)
                    # Also strip non-digits to match "Room 101" with "101"
                    digits_only = re.sub(r'^[a-zA-Z\s]+', '', cleaned).strip()
                    if digits_only:
                        explicit_reserved.add(digits_only)

    unassigned_count = active_bookings.filter(Q(room_number__isnull=True) | Q(room_number='')).count()

    result = []
    for num in all_nums:
        num_str = str(num).strip()
        num_lower = num_str.lower()
        num_digits = re.sub(r'^[a-zA-Z\s]+', '', num_lower).strip()

        is_reserved = (
            num_lower in explicit_reserved or
            (num_digits and num_digits in explicit_reserved) or
            num_str in explicit_reserved
        )

        if is_reserved:
            result.append({"number": num_str, "is_available": False, "status": "RESERVED"})
        elif unassigned_count > 0:
            result.append({"number": num_str, "is_available": False, "status": "RESERVED"})
            unassigned_count -= 1
        else:
            result.append({"number": num_str, "is_available": True, "status": "AVAILABLE"})

    return result


def allocate_room_number_for_booking(booking):
    """
    Allocates physical room number(s) to a booking upon confirmed payment.
    - Physical room numbers are allocated strictly AFTER successful payment.
    - Queries live availability for the booking's room category and stay dates.
    - Respects user preference if available, otherwise assigns the best available physical unit(s).
    - Updates booking.room_number and booking.price_snapshot['allocated_room_number'].
    Returns: allocated_room_numbers string (e.g. "101" or "101, 102").
    """
    if not booking or not booking.room:
        return None

    # If already allocated and confirmed, return existing allocation
    if booking.room_number and str(booking.room_number).strip():
        return str(booking.room_number).strip()

    room = booking.room
    cin = booking.check_in
    cout = booking.check_out
    needed_count = int(booking.number_of_rooms or 1)

    # 1. Fetch live availability for all physical room units under this category
    status_list = get_room_numbers_availability(room, cin, cout)
    available_units = [item["number"].strip() for item in status_list if item.get("is_available", True)]

    # 2. Check if a preferred room number was noted during booking creation
    preferred_raw = ""
    if booking.price_snapshot and isinstance(booking.price_snapshot, dict):
        preferred_raw = booking.price_snapshot.get('preferred_room_number') or ""

    preferred_list = [p.strip() for p in str(preferred_raw).split(',') if p.strip()]

    allocated = []
    # Try to honor customer preferred room numbers first if they are currently available
    for pref in preferred_list:
        clean_pref = pref.lower()
        pref_digits = re.sub(r'^[a-zA-Z\s]+', '', clean_pref).strip()
        matched_unit = next(
            (u for u in available_units if u.lower() == clean_pref or (pref_digits and re.sub(r'^[a-zA-Z\s]+', '', u.lower()).strip() == pref_digits)),
            None
        )
        if matched_unit and matched_unit not in allocated:
            allocated.append(matched_unit)
            available_units.remove(matched_unit)
            if len(allocated) >= needed_count:
                break

    # Fill remaining rooms from available units
    while len(allocated) < needed_count and available_units:
        allocated.append(available_units.pop(0))

    # Fallback if inventory is tracked by count rather than explicit comma-separated room numbers
    if len(allocated) < needed_count:
        all_nums = room.get_all_room_numbers()
        prefix = "Room"
        for i in range(1, (room.total_rooms or needed_count) + 1):
            fallback_unit = str(all_nums[i - 1]) if i <= len(all_nums) else f"{prefix}-{i}"
            if fallback_unit not in allocated:
                allocated.append(fallback_unit)
                if len(allocated) >= needed_count:
                    break

    final_allocated_str = ", ".join(allocated) if allocated else f"Room-{booking.id}"

    booking.room_number = final_allocated_str
    if not booking.price_snapshot or not isinstance(booking.price_snapshot, dict):
        booking.price_snapshot = {}
    booking.price_snapshot['allocated_room_number'] = final_allocated_str
    booking.save(update_fields=['room_number', 'price_snapshot'])

    return final_allocated_str


