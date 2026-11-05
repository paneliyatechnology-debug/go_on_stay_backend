from datetime import timedelta
from django.utils import timezone
from bookings.models import Booking
from .models import Notification

def create_notification(recipient, title, message, notification_type=Notification.TYPE_GENERAL, booking=None):
    """
    Central helper function to create notifications cleanly across the app.
    """
    if not recipient:
        return None
    try:
        return Notification.objects.create(
            recipient=recipient,
            booking=booking,
            title=title,
            message=message,
            notification_type=notification_type
        )
    except Exception as e:
        print(f"Failed to create notification: {e}")
        return None

def check_and_create_stay_reminders(user):
    """
    Checks if user has any active/confirmed bookings where today is on or after checkin + 1 day
    (i.e. check-in was yesterday or earlier) and stay is still active.
    If no stay reminder exists for that booking, generate one automatically.
    """
    if not user or not user.is_authenticated:
        return

    today = timezone.now().date()

    # Active/confirmed/checked-in bookings for this user where today >= check_in + 1 day
    eligible_bookings = Booking.objects.filter(
        customer=user,
        booking_status__in=[Booking.STATUS_CONFIRMED, Booking.STATUS_CHECKED_IN],
        check_in__lte=today - timedelta(days=1), # Next day of check-in or later
        check_out__gte=today # Stay has not ended yet
    )

    for booking in eligible_bookings:
        already_notified = Notification.objects.filter(
            recipient=user,
            booking=booking,
            notification_type=Notification.TYPE_STAY_REMINDER
        ).exists()

        if not already_notified:
            hotel_name = booking.hotel.name if booking.hotel else "your hotel"
            room_title = booking.room.title if booking.room else "room"
            create_notification(
                recipient=user,
                title=f"🏨 Stay Reminder: Hope you're enjoying your stay at {hotel_name}!",
                message=(
                    f"Good morning! Welcome to day 2 of your stay in {room_title} (Booking Code: {booking.booking_id}). "
                    f"If you need fresh towels, room service, or local tips, feel free to contact front desk or staff."
                ),
                notification_type=Notification.TYPE_STAY_REMINDER,
                booking=booking
            )

def check_and_create_payout_notifications(user):
    """
    Checks if there are any host settlements that are due / eligible for payout today.
    (7-day escrow hold has passed or hold_until <= now).
    If user is an ADMIN or SUPER_ADMIN or staff:
    Notifies them that today is payout disbursement day.
    Also notifies relevant hotel owners that their payout has matured and is ready for disbursement.
    """
    if not user or not user.is_authenticated:
        return

    is_admin = getattr(user, 'role', '') in ['ADMIN', 'SUPER_ADMIN'] or user.is_staff
    if not is_admin:
        return

    from payments.models import HostEarning
    from decimal import Decimal

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Find pending earnings whose holding period has matured
    pending_earnings = HostEarning.objects.filter(
        status__in=[HostEarning.STATUS_ON_HOLD, HostEarning.STATUS_ELIGIBLE]
    ).select_related('booking', 'host', 'booking__hotel')

    due_earnings = []
    for e in pending_earnings:
        e.update_dynamic_status()
        if e.status == HostEarning.STATUS_ELIGIBLE or (e.hold_until and e.hold_until <= now):
            due_earnings.append(e)

    if not due_earnings:
        return

    total_amount = sum(Decimal(str(e.net_amount)) for e in due_earnings)
    count = len(due_earnings)

    # Check if this admin has already received a payout due alert today
    already_notified_today = Notification.objects.filter(
        recipient=user,
        notification_type=Notification.TYPE_PAYOUT_DUE,
        created_at__gte=today_start
    ).exists()

    if not already_notified_today:
        create_notification(
            recipient=user,
            title="💰 Payout Day Alert: Aaj Host Payout Karne Ka Din Hai!",
            message=(
                f"Aaj host payout disbursement day hai! Aapke paas {count} reservation(s) ka total "
                f"₹{total_amount:,.2f} 7-day escrow holding period pass karke ready ho chuka hai. "
                f"Kripya Host Settlements & Escrow tab me jakar payouts process karein."
            ),
            notification_type=Notification.TYPE_PAYOUT_DUE
        )

    # Also notify hotel owners whose earnings matured today
    for e in due_earnings:
        host = e.host
        if host and host.is_authenticated:
            owner_notified = Notification.objects.filter(
                recipient=host,
                booking=e.booking,
                notification_type=Notification.TYPE_PAYOUT_DUE
            ).exists()
            if not owner_notified:
                hotel_name = e.booking.hotel.name if e.booking.hotel else "your hotel property"
                create_notification(
                    recipient=host,
                    booking=e.booking,
                    title="🎉 Payout Ready: Aaj Aapka Payout Due Hai!",
                    message=(
                        f"Aapki booking #{e.booking.booking_id} ({hotel_name}) ka 7-day escrow hold period "
                        f"complete ho gaya hai. Net payout ₹{e.net_amount:,.2f} admin settlement ke liye ready hai."
                    ),
                    notification_type=Notification.TYPE_PAYOUT_DUE
                )
