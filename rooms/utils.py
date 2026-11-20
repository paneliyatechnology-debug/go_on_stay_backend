import re
import threading
import logging
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone
from bookings.models import Booking
from util.validators import parse_flexible_date

logger = logging.getLogger(__name__)

# Reentrant lock for zero-latency in-process physical room allocation synchronization
_ROOM_ALLOCATION_LOCK = threading.RLock()


def get_payment_hold_duration():
    """
    Returns configured temporary payment hold duration as a timedelta.
    Default: 15 minutes (configurable via settings.PAYMENT_HOLD_DURATION_MINUTES).
    """
    minutes = getattr(settings, 'PAYMENT_HOLD_DURATION_MINUTES', 15)
    return timedelta(minutes=int(minutes))


def release_temporary_hold(booking, reason="PAYMENT_CANCELLED", new_status=None):
    """
    Immediately releases a temporary room hold associated with a pending payment.
    - Concurrency-safe: uses _ROOM_ALLOCATION_LOCK and atomic transaction.
    - Idempotent: repeated calls safely return True without redundant mutations.
    - Safety Guard: NEVER releases, expires, or alters bookings that are already
      CONFIRMED, CHECKED_IN, CHECKED_OUT, COMPLETED, or have payment_status == PAID.
    - Sets expires_at to past (now - 1s) to immediately release inventory dynamically.
    - Updates booking_status to new_status (default: STATUS_EXPIRED or STATUS_CANCELLED).
    - Updates payment_status to PAYMENT_FAILED.
    - Clears room_number (None) so physical room is immediately freed for other guests.
    - Marks any uncaptured/draft Payment records (status=STATUS_CREATED) as STATUS_FAILED.
    Returns True if hold was released or already released, False if protected/non-releasable.
    """
    if not booking:
        return False

    with _ROOM_ALLOCATION_LOCK:
        with transaction.atomic():
            # Refresh to latest state inside write lock
            booking.refresh_from_db()

            # Critical Safety Guard: Never release paid or confirmed bookings
            if (
                booking.booking_status in [
                    Booking.STATUS_CONFIRMED,
                    Booking.STATUS_CHECKED_IN,
                    Booking.STATUS_CHECKED_OUT,
                    Booking.STATUS_COMPLETED
                ] or booking.payment_status == Booking.PAYMENT_PAID
            ):
                logger.warning(
                    f"[release_temporary_hold] Rejected attempt to release hold for booking {booking.booking_id}: "
                    f"booking is already confirmed/paid (status={booking.booking_status}, payment={booking.payment_status})."
                )
                return False

            target_status = new_status or Booking.STATUS_EXPIRED
            now = timezone.now()
            past_expiry = now - timedelta(seconds=1)

            booking.expires_at = past_expiry
            booking.booking_status = target_status
            booking.payment_status = Booking.PAYMENT_FAILED
            booking.room_number = None
            if not booking.cancellation_reason:
                booking.cancellation_reason = reason
            booking.save(update_fields=['expires_at', 'booking_status', 'payment_status', 'room_number', 'cancellation_reason', 'updated_at'])

            # Mark draft/created payments as failed
            from payments.models import Payment
            Payment.objects.filter(
                booking=booking,
                status=Payment.STATUS_CREATED
            ).update(
                status=Payment.STATUS_FAILED,
                failure_reason=reason,
                updated_at=now
            )

            logger.info(
                f"[release_temporary_hold] Successfully released temporary hold for booking {booking.booking_id}. "
                f"Room inventory restored. Reason: {reason}."
            )
            return True


def cleanup_expired_payment_holds():
    """
    Periodic/housekeeping sweep to mark stale holds as EXPIRED and release rooms.
    Finds PENDING_PAYMENT bookings where expires_at <= now and payment is NOT paid.
    Calls release_temporary_hold on each safely.
    Returns the count of released bookings.
    """
    now = timezone.now()
    expired_qs = Booking.objects.filter(
        booking_status=Booking.STATUS_PENDING_PAYMENT,
        expires_at__lte=now
    ).exclude(
        payment_status=Booking.PAYMENT_PAID
    )

    released_count = 0
    for booking in expired_qs:
        if release_temporary_hold(booking, reason="Hold expired (fallback timer)"):
            released_count += 1

    return released_count



def auto_update_past_checkout_bookings():
    """
    Automatically updates any booking whose check_out date is past today
    from CONFIRMED or CHECKED_IN to CHECKED_OUT, restoring room availability.
    Safely checks exists() before issuing a write lock update.
    """
    try:
        today = timezone.now().date()
        has_expired = Booking.objects.filter(
            booking_status__in=[Booking.STATUS_CONFIRMED, Booking.STATUS_CHECKED_IN],
            check_out__lt=today
        ).exists()
        if has_expired:
            Booking.objects.filter(
                booking_status__in=[Booking.STATUS_CONFIRMED, Booking.STATUS_CHECKED_IN],
                check_out__lt=today
            ).update(
                booking_status=Booking.STATUS_CHECKED_OUT,
                actual_check_out_at=timezone.now()
            )
    except Exception as e:
        logger.error(f"[AutoCheckout] Error updating past checkout bookings: {e}")


def get_active_overlapping_bookings(room, check_in_date, check_out_date, exclude_booking_id=None, include_holds=False):
    """
    Returns queryset of active reservations occupying inventory for a date range.
    Two date ranges overlap if: check_in < cout AND check_out > cin.
    Active bookings include:
    - Confirmed, Checked-in, or Completed stays
    - Any booking marked as PAID
    - If include_holds=True: pending payment bookings with an unexpired checkout timer (expires_at > now)
    Excludes cancelled, checked-out, refunded, or expired bookings.
    """
    cin = parse_flexible_date(check_in_date)
    cout = parse_flexible_date(check_out_date)
    if not cin or not cout or cout <= cin:
        return Booking.objects.none()

    qs = Booking.objects.filter(
        room=room,
        check_in__lt=cout,
        check_out__gt=cin
    )

    if exclude_booking_id:
        qs = qs.exclude(id=exclude_booking_id)

    now = timezone.now()
    if include_holds:
        status_filter = (
            Q(booking_status__in=[Booking.STATUS_CONFIRMED, Booking.STATUS_CHECKED_IN, Booking.STATUS_COMPLETED]) |
            Q(payment_status=Booking.PAYMENT_PAID) |
            Q(booking_status=Booking.STATUS_PENDING_PAYMENT, expires_at__gt=now)
        )
    else:
        status_filter = (
            Q(booking_status__in=[Booking.STATUS_CONFIRMED, Booking.STATUS_CHECKED_IN, Booking.STATUS_COMPLETED]) |
            Q(payment_status=Booking.PAYMENT_PAID)
        )

    qs = qs.filter(status_filter).exclude(
        booking_status__in=[
            Booking.STATUS_CANCELLED,
            Booking.STATUS_CHECKED_OUT,
            Booking.STATUS_REFUNDED,
            Booking.STATUS_EXPIRED,
            Booking.STATUS_NO_SHOW,
            Booking.STATUS_OWNER_REJECTED,
        ]
    )
    return qs


def get_available_room_count(room, check_in_date, check_out_date, exclude_booking_id=None, include_holds=False):
    """
    Calculates remaining physical rooms available for a given date range.

    RULE: Only CONFIRMED, CHECKED_IN, and PAID bookings count as "reserved".
    PENDING_PAYMENT bookings with active holds only block when include_holds=True.

    Two date ranges overlap if:
    existing_check_in < requested_check_out AND existing_check_out > requested_check_in
    NOTE: Ordinary availability queries are strictly read-only and do not mutate historical bookings.
    Past bookings are mathematically excluded by the check_out > requested_check_in condition.
    """
    all_nums = room.get_all_room_numbers() if hasattr(room, 'get_all_room_numbers') else []
    total_units = len(all_nums) if all_nums else (getattr(room, 'total_rooms', 1) or 1)

    if not check_in_date or not check_out_date:
        return total_units

    cin = parse_flexible_date(check_in_date)
    cout = parse_flexible_date(check_out_date)

    if not cin or not cout or cout <= cin:
        return total_units

    active_bookings = get_active_overlapping_bookings(
        room, cin, cout, exclude_booking_id=exclude_booking_id, include_holds=include_holds
    )

    booked_rooms_count = active_bookings.aggregate(
        Sum('number_of_rooms')
    )['number_of_rooms__sum'] or 0

    available_count = max(0, total_units - booked_rooms_count)
    return available_count


def get_room_numbers_availability(room, check_in_date, check_out_date, exclude_booking_id=None, include_holds=False):
    """
    Returns a list of dicts for each physical room unit under this Room category:
    [
        {"number": "101", "is_available": False, "status": "RESERVED"},
        {"number": "102", "is_available": True, "status": "AVAILABLE"},
    ]
    NOTE: Read-only query. Does not mutate database records.
    """
    all_nums = room.get_all_room_numbers()
    if not check_in_date or not check_out_date:
        return [{"number": str(n).strip(), "is_available": True, "status": "AVAILABLE"} for n in all_nums]

    cin = parse_flexible_date(check_in_date)
    cout = parse_flexible_date(check_out_date)
    if not cin or not cout or cout <= cin:
        return [{"number": str(n).strip(), "is_available": True, "status": "AVAILABLE"} for n in all_nums]

    active_bookings = get_active_overlapping_bookings(
        room, cin, cout, exclude_booking_id=exclude_booking_id, include_holds=include_holds
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
    - Concurrency-safe: uses threading.RLock() and database write lock escalation.
    - Physical room numbers are allocated strictly AFTER successful payment.
    - Queries live availability for the booking's room category and stay dates.
    - Respects user preference if available, otherwise assigns the best available physical unit(s).
    - NEVER duplicates or over-allocates an occupied room number.
    - If no physical room is available, returns None (caller must trigger refund).
    Returns: allocated_room_numbers string (e.g. "101" or "101, 102"), or None if overbooked.
    """
    if not booking or not booking.room:
        return None

    room = booking.room
    cin = booking.check_in
    cout = booking.check_out
    needed_count = int(booking.number_of_rooms or 1)

    with _ROOM_ALLOCATION_LOCK:
        with transaction.atomic():
            # In SQLite, issue an immediate update on Room to acquire the database write lock,
            # serializing any concurrent transactions attempting to allocate for the same room.
            from rooms.models import Room
            Room.objects.filter(id=room.id).update(updated_at=timezone.now())

            # Re-fetch the fresh booking record inside the transaction
            booking.refresh_from_db()

            # If already allocated, verify it does not conflict with another confirmed booking
            if booking.room_number and str(booking.room_number).strip():
                existing_allocated = str(booking.room_number).strip()
                # Check for conflict with other confirmed bookings
                conflict = Booking.objects.filter(
                    room=room,
                    check_in__lt=cout,
                    check_out__gt=cin,
                    room_number__icontains=existing_allocated
                ).filter(
                    Q(booking_status__in=[Booking.STATUS_CONFIRMED, Booking.STATUS_CHECKED_IN, Booking.STATUS_COMPLETED]) |
                    Q(payment_status=Booking.PAYMENT_PAID)
                ).exclude(
                    booking_status__in=[Booking.STATUS_CANCELLED, Booking.STATUS_CHECKED_OUT, Booking.STATUS_REFUNDED, Booking.STATUS_EXPIRED]
                ).exclude(
                    id=booking.id
                ).exists()

                if not conflict:
                    return existing_allocated

            # 1. Fetch live availability for all physical room units under this category
            # exclude_booking_id=booking.id ensures this booking's own records don't self-block
            status_list = get_room_numbers_availability(room, cin, cout, exclude_booking_id=booking.id, include_holds=False)
            available_units = [item["number"].strip() for item in status_list if item.get("is_available", True)]

            # 2. Check if a preferred room number was noted during booking creation
            preferred_raw = ""
            if booking.price_snapshot and isinstance(booking.price_snapshot, dict):
                preferred_raw = booking.price_snapshot.get('preferred_room_number') or ""
            if not preferred_raw and getattr(booking, 'preferred_room_number', None):
                preferred_raw = booking.preferred_room_number

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

            # CRITICAL CONCURRENCY SAFEGUARD:
            # If available units are insufficient, DO NOT allocate occupied rooms!
            # Return None to signal overbooking race condition so caller can initiate an automatic refund.
            if len(allocated) < needed_count:
                logger.error(
                    f"[RoomAllocation] OVERBOOKING DETECTED for booking {booking.booking_id}: "
                    f"Requested {needed_count} room(s), but only {len(allocated)} unit(s) available for {cin} to {cout}. "
                    f"Refusing to double-allocate occupied rooms."
                )
                return None

            # Double-check that none of the allocated units are occupied by another active booking
            for unit in list(allocated):
                unit_clean = unit.strip().lower()
                unit_digits = re.sub(r'^[a-zA-Z\s]+', '', unit_clean).strip()

                active_overlapping = Booking.objects.filter(
                    room=room,
                    check_in__lt=cout,
                    check_out__gt=cin,
                ).filter(
                    Q(booking_status__in=[Booking.STATUS_CONFIRMED, Booking.STATUS_CHECKED_IN, Booking.STATUS_COMPLETED]) |
                    Q(payment_status=Booking.PAYMENT_PAID)
                ).exclude(
                    booking_status__in=[Booking.STATUS_CANCELLED, Booking.STATUS_CHECKED_OUT, Booking.STATUS_REFUNDED, Booking.STATUS_EXPIRED]
                ).exclude(
                    id=booking.id
                ).exclude(
                    room_number__isnull=True
                ).exclude(
                    room_number=''
                )

                for active_b in active_overlapping:
                    assigned_nums = [str(x).strip().lower() for x in str(active_b.room_number).split(',') if str(x).strip()]
                    assigned_digits = [re.sub(r'^[a-zA-Z\s]+', '', x).strip() for x in assigned_nums if re.sub(r'^[a-zA-Z\s]+', '', x).strip()]
                    if unit_clean in assigned_nums or (unit_digits and unit_digits in assigned_digits):
                        logger.error(
                            f"[RoomAllocation] Conflict detected: Unit {unit} is already assigned to Booking {active_b.booking_id}. "
                            f"Aborting double-allocation."
                        )
                        return None

            final_allocated_str = ", ".join(allocated)
            booking.room_number = final_allocated_str
            if not booking.price_snapshot or not isinstance(booking.price_snapshot, dict):
                booking.price_snapshot = {}
            booking.price_snapshot['allocated_room_number'] = final_allocated_str
            booking.save(update_fields=['room_number', 'price_snapshot'])

            logger.info(
                f"[RoomAllocation] Successfully allocated Room {final_allocated_str} "
                f"to Booking {booking.booking_id} for {cin} to {cout}."
            )
            return final_allocated_str
