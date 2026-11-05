import re
from datetime import datetime, time as dt_time
from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone


def parse_hotel_time(time_str, default_hour=12, default_minute=0):
    """
    Parses various hotel check-in time formats into a standard datetime.time object.
    Supports formats like '12:00 PM', '02:00 PM', '14:00', '12:00', etc.
    """
    if not time_str or not isinstance(time_str, str):
        return dt_time(default_hour, default_minute)

    cleaned = time_str.strip().upper()
    for fmt in ('%I:%M %p', '%I:%M%p', '%I %p', '%H:%M', '%H:%M:%S'):
        try:
            return datetime.strptime(cleaned, fmt).time()
        except ValueError:
            pass

    match = re.search(r'(\d{1,2}):(\d{2})\s*(AM|PM)?', cleaned)
    if match:
        h, m, meridiem = int(match.group(1)), int(match.group(2)), match.group(3)
        if meridiem == 'PM' and h < 12:
            h += 12
        elif meridiem == 'AM' and h == 12:
            h = 0
        return dt_time(h, m)

    return dt_time(default_hour, default_minute)


def get_booking_checkin_datetime(booking):
    """
    Combines booking.check_in (date) with hotel.check_in_time (default 12:00 PM)
    to produce a timezone-aware check-in datetime.
    """
    check_in_date = booking.check_in
    hotel = getattr(booking, 'hotel', None)
    time_str = getattr(hotel, 'check_in_time', '12:00 PM') if hotel else '12:00 PM'
    check_in_time = parse_hotel_time(time_str, 12, 0)

    tz = timezone.get_current_timezone()
    naive_dt = datetime.combine(check_in_date, check_in_time)
    if timezone.is_naive(naive_dt):
        return timezone.make_aware(naive_dt, tz)
    return naive_dt


def calculate_cancellation_details(booking, as_of_time=None):
    """
    Calculates cancellation fee and refundable amount based on user-defined tiered policy:
    1. Immediate Booking Window: If cancelled within 2 hours of booking, guest gets 100% full refund (0% fee).
    2. More than 48 hours before check-in: 0% fee, 100% refund
    3. More than 24 hours & up to 48 hours: 25% fee, 75% refund
    4. More than 2 hours & up to 24 hours: 50% fee, 50% refund
    5. 2 hours or less, before check-in / Same-day: 80% fee, 20% refund
    """
    if as_of_time is None:
        as_of_time = timezone.now()

    checkin_dt = get_booking_checkin_datetime(booking)
    diff_seconds = (checkin_dt - as_of_time).total_seconds()
    hours_remaining = diff_seconds / 3600.0

    total_amount = Decimal(str(booking.total_amount))

    # Check if booking was created recently (within last 2 hours - Immediate Booking Mistake / Grace Window)
    created_at = getattr(booking, 'created_at', None)
    is_immediate_cancellation = False
    if created_at:
        seconds_since_booking = (as_of_time - created_at).total_seconds()
        if 0 <= seconds_since_booking <= 7200:  # Within 2 hours of booking
            is_immediate_cancellation = True

    if is_immediate_cancellation:
        charge_pct = Decimal('0.00')
        refund_pct = Decimal('100.00')
        policy_label = "Free Cancellation (Booked within last 2 hours - 0% fee, 100% refund)"
        tier_id = "TIER_48H_PLUS"
    elif hours_remaining > 48.0:
        charge_pct = Decimal('0.00')
        refund_pct = Decimal('100.00')
        policy_label = "More than 48 hours before check-in (0% fee, 100% refund)"
        tier_id = "TIER_48H_PLUS"
    elif hours_remaining > 24.0:
        charge_pct = Decimal('25.00')
        refund_pct = Decimal('75.00')
        policy_label = "More than 24 hours and up to 48 hours (25% fee, 75% refund)"
        tier_id = "TIER_24H_48H"
    elif hours_remaining > 2.0:
        charge_pct = Decimal('50.00')
        refund_pct = Decimal('50.00')
        policy_label = "More than 2 hours and up to 24 hours (50% fee, 50% refund)"
        tier_id = "TIER_2H_24H"
    else:
        # 2 hours or less, before check-in (or same-day before checking in)
        charge_pct = Decimal('80.00')
        refund_pct = Decimal('20.00')
        policy_label = "2 hours or less, before check-in (80% fee, 20% refund)"
        tier_id = "TIER_UNDER_2H"

    cancellation_charge = (total_amount * (charge_pct / Decimal('100.00'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    refundable_amount = max(Decimal('0.00'), total_amount - cancellation_charge)

    slabs = [
        {
            "tier_id": "TIER_48H_PLUS",
            "time_window": "More than 48 hours" + (" (or within 2h of booking)" if is_immediate_cancellation else ""),
            "cancellation_charge_percentage": 0,
            "refund_percentage": 100,
            "is_applicable": tier_id == "TIER_48H_PLUS"
        },
        {
            "tier_id": "TIER_24H_48H",
            "time_window": "More than 24 hours and up to 48 hours",
            "cancellation_charge_percentage": 25,
            "refund_percentage": 75,
            "is_applicable": tier_id == "TIER_24H_48H"
        },
        {
            "tier_id": "TIER_2H_24H",
            "time_window": "More than 2 hours and up to 24 hours",
            "cancellation_charge_percentage": 50,
            "refund_percentage": 50,
            "is_applicable": tier_id == "TIER_2H_24H"
        },
        {
            "tier_id": "TIER_UNDER_2H",
            "time_window": "2 hours or less, before check-in",
            "cancellation_charge_percentage": 80,
            "refund_percentage": 20,
            "is_applicable": tier_id == "TIER_UNDER_2H"
        }
    ]

    # Calculate user-friendly display for remaining time
    time_display = ""
    if is_immediate_cancellation and created_at:
        mins = max(1, int((as_of_time - created_at).total_seconds() // 60))
        time_display = f"Just Booked ({mins}m ago - Grace Window)"
    elif hours_remaining > 48:
        days = round(hours_remaining / 24, 1)
        time_display = f"{days} Days ({round(hours_remaining, 1)} Hours)"
    elif hours_remaining > 1:
        time_display = f"{round(hours_remaining, 1)} Hours"
    elif hours_remaining > 0:
        mins = int(hours_remaining * 60)
        time_display = f"{mins} Minutes"
    else:
        time_display = "Check-in Day (Today)"

    return {
        "checkin_datetime": checkin_dt.isoformat(),
        "calculated_at": as_of_time.isoformat(),
        "hours_remaining": round(max(0.0, hours_remaining), 2),
        "raw_hours_remaining": round(hours_remaining, 2),
        "time_display": time_display,
        "is_immediate_cancellation": is_immediate_cancellation,
        "tier_id": tier_id,
        "policy_label": policy_label,
        "cancellation_fee_percentage": float(charge_pct),
        "refund_percentage": float(refund_pct),
        "total_amount": float(total_amount),
        "cancellation_charge": float(cancellation_charge),
        "refundable_amount": float(refundable_amount),
        "slabs": slabs
    }
