import re
import logging
from django.db.models import Q

logger = logging.getLogger(__name__)

# Regular expressions for entity discovery in free-text titles and messages
RE_BOOKING_CODE = re.compile(r'\b((?:BMR|KH|GOON|BK)[-_]?\d+[A-Za-z0-9_-]*)\b', re.IGNORECASE)
RE_BOOKING_LABEL = re.compile(r'(?:booking|reservation)\s*(?:#|id:?\s*|code:?\s*)\s*([A-Za-z0-9_-]+)', re.IGNORECASE)
RE_TICKET_CODE = re.compile(r'\b(TCK-[A-Za-z0-9_-]+)\b', re.IGNORECASE)
RE_TICKET_LABEL = re.compile(r'(?:ticket|complaint)\s*(?:#|id:?\s*|no:?\s*)\s*([A-Za-z0-9_-]+)', re.IGNORECASE)
RE_REFUND_LABEL = re.compile(r'(?:refund|claim)\s*(?:#|id:?\s*|no:?\s*)\s*(\d+)', re.IGNORECASE)
RE_PAYOUT_LABEL = re.compile(r'(?:payout|settlement|escrow)\s*(?:#|id:?\s*|no:?\s*)\s*(\d+)', re.IGNORECASE)
RE_HOTEL_LABEL = re.compile(r'(?:hotel|property)\s*(?:#|id:?\s*|no:?\s*)\s*(\d+)', re.IGNORECASE)


def extract_entity_details(notification=None, notification_type=None, booking=None, metadata=None, title='', message=''):
    """
    Extracts candidate target entity type and entity ID from notification objects,
    metadata dictionaries, FK relationships, or text bodies.
    """
    meta = metadata or {}
    if notification and hasattr(notification, 'metadata') and isinstance(notification.metadata, dict):
        meta = {**meta, **notification.metadata}

    n_type = (notification_type or getattr(notification, 'notification_type', '') or 'GENERAL').upper()
    n_title = title or getattr(notification, 'title', '') or ''
    n_msg = message or getattr(notification, 'message', '') or ''
    text_content = f"{n_title} {n_msg}"

    # 1. Booking Resolution
    booking_obj = booking or getattr(notification, 'booking', None)
    booking_id = None
    if booking_obj:
        booking_id = getattr(booking_obj, 'booking_id', None) or str(getattr(booking_obj, 'id', ''))
    if not booking_id and 'booking_id' in meta:
        booking_id = str(meta['booking_id'])
    if not booking_id:
        m = RE_BOOKING_CODE.search(text_content)
        if m:
            booking_id = m.group(1)
        else:
            m2 = RE_BOOKING_LABEL.search(text_content)
            if m2 and m2.group(1).lower() not in ['alert', 'update', 'details', 'system']:
                booking_id = m2.group(1)

    # 2. Hotel Resolution
    hotel_id = None
    if booking_obj and getattr(booking_obj, 'hotel_id', None):
        hotel_id = str(booking_obj.hotel_id)
    if not hotel_id and 'hotel_id' in meta:
        hotel_id = str(meta['hotel_id'])
    if not hotel_id:
        m = RE_HOTEL_LABEL.search(text_content)
        if m:
            hotel_id = m.group(1)

    # 3. Ticket Resolution
    ticket_id = None
    if 'ticket_id' in meta or 'ticket_number' in meta:
        ticket_id = str(meta.get('ticket_id') or meta.get('ticket_number'))
    if not ticket_id:
        m_tck = RE_TICKET_CODE.search(text_content)
        if m_tck:
            ticket_id = m_tck.group(1)
        else:
            m = RE_TICKET_LABEL.search(text_content)
            if m and m.group(1).lower() not in ['system', 'alert', 'message', 'updated', 'created']:
                ticket_id = m.group(1)

    # 4. Refund Resolution
    refund_id = None
    if 'refund_id' in meta or 'claim_id' in meta:
        refund_id = str(meta.get('refund_id') or meta.get('claim_id'))
    if not refund_id:
        m = RE_REFUND_LABEL.search(text_content)
        if m:
            refund_id = m.group(1)

    # 5. Payout Resolution
    payout_id = None
    if 'payout_id' in meta or 'earning_id' in meta or 'settlement_id' in meta:
        payout_id = str(meta.get('payout_id') or meta.get('earning_id') or meta.get('settlement_id'))
    if not payout_id:
        m = RE_PAYOUT_LABEL.search(text_content)
        if m:
            payout_id = m.group(1)

    # Determine primary entity type
    explicit_type = meta.get('target_entity_type') or meta.get('entity_type')
    if explicit_type:
        entity_type = explicit_type.lower()
        entity_id = meta.get('target_entity_id') or meta.get('entity_id')
        if not entity_id:
            if entity_type == 'booking': entity_id = booking_id
            elif entity_type == 'hotel': entity_id = hotel_id
            elif entity_type == 'ticket': entity_id = ticket_id
            elif entity_type == 'refund': entity_id = refund_id
            elif entity_type == 'payout': entity_id = payout_id
        return entity_type, (str(entity_id) if entity_id else ''), booking_obj

    # Derive from notification_type
    if n_type in [
        'STAY_REMINDER', 'BOOKING_CONFIRMED', 'NEW_BOOKING_OWNER',
        'CHECKED_IN', 'CHECKED_OUT', 'BOOKING_CANCELLED', 'CHECKOUT_REMINDER',
        'BOOKING_CREATED', 'BOOKING_MODIFIED'
    ]:
        return 'booking', (booking_id or ''), booking_obj

    if n_type in ['HOTEL_APPROVED', 'HOTEL_REJECTED', 'VERIFICATION_REQUIRED', 'HOTEL_SUBMITTED']:
        return 'hotel', (hotel_id or ''), booking_obj

    if n_type in ['PAYOUT_DUE', 'PAYOUT_INITIATED', 'PAYOUT_DISBURSED', 'PAYOUT_HOLD', 'ESCROW_RELEASE']:
        return 'payout', (payout_id or booking_id or ''), booking_obj

    if n_type in ['REFUND_PROCESSED', 'REFUND_REQUESTED', 'REFUND_APPROVED', 'REFUND_REJECTED', 'CLAIM_FILED']:
        return 'refund', (refund_id or booking_id or ''), booking_obj

    if n_type in ['SUPPORT_TICKET', 'SUPPORT_TICKET_CREATED', 'SUPPORT_TICKET_UPDATED', 'SUPPORT_MESSAGE', 'SUPPORT_RESPONSE']:
        return 'ticket', (ticket_id or ''), booking_obj

    if n_type in ['PAYMENT_SUCCESSFUL', 'PAYMENT_FAILED', 'PAYMENT_PENDING']:
        return ('booking' if booking_id else 'payment'), (booking_id or ''), booking_obj

    if n_type in ['COUPON_OFFER', 'PROMO_CODE', 'OFFER']:
        return 'offer', '', booking_obj

    if n_type in ['SUBSCRIPTION', 'HOST_SUBSCRIPTION', 'PLAN_UPGRADE', 'PLAN_SCHEDULED', 'SUBSCRIPTION_RENEWAL']:
        return 'subscription', '', booking_obj

    if n_type in ['ACCOUNT_SECURITY', 'PROFILE_UPDATE', 'PASSWORD_RESET']:
        return 'profile', '', booking_obj

    # Fallback to detected identifiers in text
    if booking_id:
        return 'booking', booking_id, booking_obj
    if ticket_id:
        return 'ticket', ticket_id, booking_obj
    if refund_id:
        return 'refund', refund_id, booking_obj
    if payout_id:
        return 'payout', payout_id, booking_obj
    if hotel_id:
        return 'hotel', hotel_id, booking_obj

    return 'general', '', booking_obj


def verify_record_exists(entity_type, entity_id, booking_obj=None):
    """
    Safely verifies whether the target entity record currently exists in the database.
    Prevents broken navigation when a record was cancelled, deleted, or purged.
    """
    if not entity_id and not booking_obj:
        return False
    if booking_obj:
        return True

    try:
        if entity_type == 'booking':
            from bookings.models import Booking
            return Booking.objects.filter(Q(booking_id=entity_id) | Q(id__iexact=str(entity_id))).exists()
        elif entity_type == 'hotel':
            from hotels.models import Hotel
            return Hotel.objects.filter(id=entity_id, is_deleted=False).exists()
        elif entity_type == 'ticket':
            from payments.models import SupportTicket
            return SupportTicket.objects.filter(Q(ticket_number=entity_id) | Q(id__iexact=str(entity_id))).exists()
        elif entity_type == 'refund':
            from payments.models import Refund
            return Refund.objects.filter(id=entity_id).exists()
        elif entity_type == 'payout':
            from payments.models import HostEarning
            return HostEarning.objects.filter(id=entity_id).exists()
    except Exception as exc:
        logger.debug(f"[verify_record_exists] Error checking existence for {entity_type} #{entity_id}: {exc}")
        return True

    return True


def resolve_notification_navigation(
    notification=None,
    user=None,
    notification_type=None,
    booking=None,
    metadata=None,
    title='',
    message=''
):
    """
    Central destination resolver for GoOnStay smart notification click-through.
    Returns:
    {
        "target_url": str,
        "target_entity_type": str,
        "target_entity_id": str,
        "fallback_url": str,
        "action": str,
        "record_exists": bool,
    }
    """
    # 1. Resolve User and Role
    target_user = user
    if not target_user and notification:
        target_user = getattr(notification, 'recipient', None)
        # If recipient is StaffProfile instance:
        if target_user and hasattr(target_user, 'user'):
            target_user = target_user.user

    user_role = getattr(target_user, 'role', '') if target_user else 'CUSTOMER'
    is_staff = getattr(target_user, 'is_staff', False) or user_role == 'STAFF'
    is_admin = getattr(target_user, 'is_superuser', False) or user_role in ['ADMIN', 'SUPER_ADMIN']

    # 2. Extract Staff Department if applicable
    staff_department = None
    if is_staff and not is_admin:
        profile = getattr(target_user, 'staff_profile', None) if target_user else None
        if profile and profile.department:
            staff_department = profile.department.code
        elif notification and hasattr(notification, 'department') and notification.department:
            staff_department = notification.department.code

        if staff_department:
            from staff.models import Department
            staff_department = Department.normalize_code(staff_department)

    # 3. Extract Entity Details
    entity_type, entity_id, booking_obj = extract_entity_details(
        notification=notification,
        notification_type=notification_type,
        booking=booking,
        metadata=metadata,
        title=title,
        message=message
    )

    record_exists = verify_record_exists(entity_type, entity_id, booking_obj)

    # 4. Resolve Target & Fallback URLs strictly by Authenticated Role

    # -------------------------------------------------------------------------
    # A. ADMIN ROLE
    # -------------------------------------------------------------------------
    if is_admin:
        if entity_type == 'booking':
            fallback = '/admin/bookings'
            target = f"/admin/bookings?booking_id={entity_id}" if (record_exists and entity_id) else fallback
            action = 'highlight_record' if entity_id else 'view_list'
        elif entity_type == 'hotel':
            fallback = '/admin/verifications'
            target = f"/admin/verifications?hotel_id={entity_id}" if (record_exists and entity_id) else fallback
            action = 'highlight_record' if entity_id else 'view_list'
        elif entity_type == 'refund':
            fallback = '/admin/refunds'
            target = f"/admin/refunds?refund_id={entity_id}" if (record_exists and entity_id) else fallback
            action = 'highlight_record' if entity_id else 'view_list'
        elif entity_type == 'payout':
            fallback = '/admin/payouts'
            target = f"/admin/payouts?payout_id={entity_id}" if (record_exists and entity_id) else fallback
            action = 'highlight_record' if entity_id else 'view_list'
        elif entity_type == 'ticket':
            fallback = '/admin/support'
            target = f"/admin/support?ticket_id={entity_id}" if (record_exists and entity_id) else fallback
            action = 'highlight_record' if entity_id else 'view_list'
        elif entity_type == 'payment':
            fallback = '/admin/payments'
            target = '/admin/payments'
            action = 'view_list'
        elif entity_type == 'profile':
            fallback = '/admin/settings'
            target = '/admin/settings'
            action = 'view_settings'
        else:
            fallback = '/admin/dashboard'
            target = '/admin/dashboard'
            action = 'view_dashboard'

        return {
            "target_url": target,
            "url": target,
            "link": target,
            "path": target,
            "route": target,
            "target_entity_type": entity_type,
            "target_entity_id": entity_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "fallback_url": fallback,
            "action": action,
            "record_exists": record_exists
        }

    # -------------------------------------------------------------------------
    # B. STAFF ROLE (Strict Department Isolation)
    # -------------------------------------------------------------------------
    if is_staff:
        dept = staff_department or 'RESERVATION'

        if dept == 'RESERVATION':
            fallback = '/staff/reservation/bookings'
            if entity_type == 'booking':
                target = f"/staff/reservation/bookings/{entity_id}" if (record_exists and entity_id) else fallback
                action = 'open_record' if entity_id else 'view_list'
            else:
                target = '/staff/reservation'
                fallback = '/staff/reservation'
                action = 'view_dashboard'

        elif dept == 'CUSTOMER_SUPPORT':
            fallback = '/staff/support/tickets'
            if entity_type == 'ticket':
                target = f"/staff/support/tickets/{entity_id}" if (record_exists and entity_id) else fallback
                action = 'open_record' if entity_id else 'view_list'
            else:
                target = '/staff/support'
                fallback = '/staff/support'
                action = 'view_dashboard'

        elif dept == 'REFUNDS_AND_CLAIMS':
            fallback = '/staff/refunds/requests'
            if entity_type in ['refund', 'claim']:
                target = f"/staff/refunds/{entity_id}" if (record_exists and entity_id) else fallback
                action = 'open_record' if entity_id else 'view_list'
            else:
                target = '/staff/refunds'
                fallback = '/staff/refunds'
                action = 'view_dashboard'

        elif dept == 'PAYOUT_AND_ESCROW':
            fallback = '/staff/payouts/requests'
            if entity_type in ['payout', 'settlement']:
                target = f"/staff/payouts/{entity_id}" if (record_exists and entity_id) else fallback
                action = 'open_record' if entity_id else 'view_list'
            elif entity_type == 'escrow':
                target = '/staff/payouts/escrow'
                fallback = '/staff/payouts/escrow'
                action = 'view_escrow'
            else:
                target = '/staff/payouts'
                fallback = '/staff/payouts'
                action = 'view_dashboard'

        elif dept == 'HOTEL_VERIFICATION':
            fallback = '/staff/verification/pending'
            if entity_type in ['hotel', 'verification']:
                target = f"/staff/verification/{entity_id}" if (record_exists and entity_id) else fallback
                action = 'open_record' if entity_id else 'view_list'
            else:
                target = '/staff/verification'
                fallback = '/staff/verification'
                action = 'view_dashboard'

        else:
            fallback = '/staff/reservation'
            target = '/staff/reservation'
            action = 'view_dashboard'

        return {
            "target_url": target,
            "url": target,
            "link": target,
            "path": target,
            "route": target,
            "target_entity_type": entity_type,
            "target_entity_id": entity_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "fallback_url": fallback,
            "action": action,
            "record_exists": record_exists
        }

    # -------------------------------------------------------------------------
    # C. HOTEL OWNER ROLE
    # -------------------------------------------------------------------------
    if user_role == 'HOTEL_OWNER':
        if entity_type == 'booking':
            fallback = '/host/bookings'
            target = f"/host/bookings/{entity_id}" if (record_exists and entity_id) else fallback
            owner_target = f"/owner/dashboard/guest-reservations?booking_id={entity_id}" if (record_exists and entity_id) else '/owner/dashboard/guest-reservations'
            action = 'open_record' if entity_id else 'view_list'
        elif entity_type == 'hotel':
            fallback = '/host/hotels'
            target = f"/host/hotels/{entity_id}" if (record_exists and entity_id) else fallback
            owner_target = f"/owner/dashboard/hotel-properties?hotel_id={entity_id}" if (record_exists and entity_id) else '/owner/dashboard/hotel-properties'
            action = 'open_record' if entity_id else 'view_list'
        elif entity_type in ['payout', 'settlement', 'escrow']:
            fallback = '/host/settlements'
            target = f"/host/settlements?payout_id={entity_id}" if entity_id else fallback
            owner_target = f"/owner/dashboard/settlement-escrow?payout_id={entity_id}" if entity_id else '/owner/dashboard/settlement-escrow'
            action = 'highlight_record' if entity_id else 'view_list'
        elif entity_type == 'subscription':
            fallback = '/owner/dashboard/manage-plan'
            target = '/owner/dashboard/manage-plan'
            owner_target = '/owner/dashboard/manage-plan'
            action = 'view_subscription'
        elif entity_type == 'account':
            fallback = '/host/settlements'
            target = '/host/settlements'
            owner_target = '/owner/dashboard/settlement-escrow'
            action = 'view_account'
        elif entity_type == 'review':
            fallback = '/owner/dashboard/reviews'
            target = '/owner/dashboard/reviews'
            owner_target = '/owner/dashboard/reviews'
            action = 'view_reviews'
        elif entity_type == 'refund':
            fallback = '/host/bookings'
            target = f"/host/bookings/{entity_id}" if (record_exists and entity_id) else fallback
            owner_target = f"/owner/dashboard/guest-reservations?booking_id={entity_id}" if (record_exists and entity_id) else '/owner/dashboard/guest-reservations'
            action = 'open_record' if entity_id else 'view_list'
        else:
            fallback = '/host/dashboard'
            target = '/host/dashboard'
            owner_target = '/owner/dashboard'
            action = 'view_dashboard'

        return {
            "target_url": target,
            "url": target,
            "link": target,
            "path": target,
            "route": target,
            "owner_dashboard_url": owner_target,
            "target_entity_type": entity_type,
            "target_entity_id": entity_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "fallback_url": fallback,
            "action": action,
            "record_exists": record_exists
        }

    # -------------------------------------------------------------------------
    # D. CUSTOMER ROLE (Default)
    # -------------------------------------------------------------------------
    if entity_type == 'booking':
        fallback = '/customer/bookings'
        target = f"/customer/bookings/{entity_id}" if (record_exists and entity_id) else fallback
        action = 'open_record' if entity_id else 'view_list'
    elif entity_type == 'ticket':
        fallback = '/customer/support'
        target = f"/customer/support?ticket_id={entity_id}" if entity_id else fallback
        action = 'highlight_record' if entity_id else 'view_list'
    elif entity_type == 'payment':
        fallback = '/customer/bookings'
        target = f"/customer/bookings/{entity_id}" if (record_exists and entity_id) else fallback
        action = 'open_record' if entity_id else 'view_list'
    elif entity_type == 'refund':
        fallback = '/customer/bookings'
        target = f"/customer/bookings/{entity_id}" if (record_exists and entity_id) else fallback
        action = 'open_record' if entity_id else 'view_list'
    elif entity_type == 'offer':
        fallback = '/hotels'
        target = '/hotels'
        action = 'explore_hotels'
    elif entity_type == 'profile':
        fallback = '/customer/profile'
        target = '/customer/profile'
        action = 'view_profile'
    else:
        fallback = '/customer/dashboard'
        target = '/customer/dashboard'
        action = 'view_dashboard'

    return {
        "target_url": target,
        "target_entity_type": entity_type,
        "target_entity_id": entity_id,
        "fallback_url": fallback,
        "action": action,
        "record_exists": record_exists
    }
