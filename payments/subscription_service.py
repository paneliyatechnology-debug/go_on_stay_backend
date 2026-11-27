from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from rest_framework.exceptions import PermissionDenied, ValidationError
from .models import HostSubscription

PLAN_RULES = {
    'SILVER': {
        'plan_id': 'SILVER',
        'id': 'silver',
        'name': 'Silver Partner',
        'display_name': 'Silver Partner Plan',
        'price': 1999,
        'amount': 1999,
        'currency': 'INR',
        'commission_rate': '10%',
        'commission_percentage': 10.0,
        'max_hotels': 1,
        'max_rooms_per_hotel': 5,
        'billing_cycle': 'ANNUAL',
        'badge': 'Standard',
        'popular': False,
        'priority_listing': False,
        'instant_payout': False,
        'features': [
            "List up to 1 hotel property",
            "Up to 5 room categories per hotel",
            "10% platform commission on bookings",
            "Standard search listing across GoOnStay",
            "Standard customer & host email support",
            "Basic revenue and room inventory reports"
        ]
    },
    'GOLD': {
        'plan_id': 'GOLD',
        'id': 'gold',
        'name': 'Gold Partner',
        'display_name': 'Gold Partner Plan',
        'price': 3999,
        'amount': 3999,
        'currency': 'INR',
        'commission_rate': '5%',
        'commission_percentage': 5.0,
        'max_hotels': 5,
        'max_rooms_per_hotel': 20,
        'billing_cycle': 'ANNUAL',
        'badge': 'Most Popular',
        'popular': True,
        'priority_listing': True,
        'instant_payout': False,
        'features': [
            "List up to 5 hotel properties",
            "Up to 20 room categories per hotel",
            "5% reduced platform commission on bookings",
            "Priority search placement in destination cities",
            "Verified Hotel Partner badge on listing",
            "Fast-track payout processing within 3 business days",
            "Priority email & chat host support"
        ]
    },
    'PLATINUM': {
        'plan_id': 'PLATINUM',
        'id': 'platinum',
        'name': 'Platinum Elite Partner',
        'display_name': 'Platinum Elite Partner Plan',
        'price': 7999,
        'amount': 7999,
        'currency': 'INR',
        'commission_rate': '0%',
        'commission_percentage': 0.0,
        'max_hotels': 999,
        'max_rooms_per_hotel': 999,
        'billing_cycle': 'ANNUAL',
        'badge': 'Zero Commission',
        'popular': False,
        'priority_listing': True,
        'instant_payout': True,
        'features': [
            "Unlimited hotel properties",
            "Unlimited room categories",
            "0% ZERO commission on all guest bookings",
            "Top featured placement on home & search results",
            "Dedicated Account Manager for property promotion",
            "Same-day instant payout disbursement",
            "Advanced booking analytics & dynamic pricing tools",
            "Free professional hotel photo shoot (Annual)"
        ]
    }
}


def get_plan_definition(plan_id):
    tier = str(plan_id or 'SILVER').upper()
    return PLAN_RULES.get(tier, PLAN_RULES['SILVER'])


def get_or_sync_active_subscription(user):
    """
    Retrieves the currently active subscription for a user.
    Handles automatic lifecycle transitions:
    - Marks past ACTIVE subscriptions as EXPIRED.
    - Automatically promotes any due SCHEDULED subscription to ACTIVE.
    - If no subscription exists in DB, creates default matching user's tier.
    """
    if not user or not user.is_authenticated:
        return None

    now = timezone.now()

    # 1. Expire any ACTIVE subscription whose end_date is in the past
    active_subs = HostSubscription.objects.filter(
        user=user,
        status=HostSubscription.STATUS_ACTIVE
    ).order_by('-end_date')

    for sub in active_subs:
        if sub.end_date <= now:
            sub.status = HostSubscription.STATUS_EXPIRED
            sub.save(update_fields=['status', 'updated_at'])

    # 2. Check for current valid ACTIVE subscription
    current_active = HostSubscription.objects.filter(
        user=user,
        status=HostSubscription.STATUS_ACTIVE,
        start_date__lte=now,
        end_date__gt=now
    ).order_by('-end_date').first()

    # 3. If no active subscription, check for SCHEDULED subscriptions due to start
    if not current_active:
        due_scheduled = HostSubscription.objects.filter(
            user=user,
            status=HostSubscription.STATUS_SCHEDULED,
            start_date__lte=now,
            end_date__gt=now
        ).order_by('start_date').first()

        if due_scheduled:
            due_scheduled.status = HostSubscription.STATUS_ACTIVE
            due_scheduled.save(update_fields=['status', 'updated_at'])
            current_active = due_scheduled
            if getattr(user, 'subscription_tier', '') != due_scheduled.plan_id:
                user.subscription_tier = due_scheduled.plan_id
                user.save(update_fields=['subscription_tier'])

    # 4. If still no active subscription and no subscriptions at all exist for user, create initial active record
    if not current_active:
        user_has_any = HostSubscription.objects.filter(user=user).exists()
        if not user_has_any:
            tier = str(getattr(user, 'subscription_tier', 'SILVER') or 'SILVER').upper()
            if tier not in PLAN_RULES:
                tier = 'SILVER'
            start = now
            end = now + timedelta(days=365)
            current_active = HostSubscription.objects.create(
                user=user,
                plan_id=tier,
                status=HostSubscription.STATUS_ACTIVE,
                start_date=start,
                end_date=end,
                amount_paid=Decimal(str(PLAN_RULES[tier]['price'])),
                currency='INR',
                billing_cycle='ANNUAL'
            )

    return current_active


def queue_or_activate_subscription(user, plan_id, duration_days=365, amount_paid=None, order_id=None, payment_id=None):
    """
    Enforces subscription queuing rule:
    - A hotel owner CANNOT run two subscriptions simultaneously.
    - If an active subscription already exists, the new subscription is SCHEDULED
      in queue to start the exact moment the active/latest subscription ends.
    - If no active subscription exists, the new subscription is immediately ACTIVE.
    """
    plan_tier = str(plan_id or 'GOLD').upper()
    if plan_tier not in PLAN_RULES:
        raise ValidationError(f"Invalid subscription plan '{plan_id}'. Choose SILVER, GOLD, or PLATINUM.")

    plan_info = PLAN_RULES[plan_tier]
    if amount_paid is None:
        amount_paid = Decimal(str(plan_info['price']))
    else:
        amount_paid = Decimal(str(amount_paid))

    now = timezone.now()
    active_sub = get_or_sync_active_subscription(user)

    # Find all future/active subscriptions to determine queue positioning
    existing_future_subs = HostSubscription.objects.filter(
        user=user,
        status__in=[HostSubscription.STATUS_ACTIVE, HostSubscription.STATUS_SCHEDULED],
        end_date__gt=now
    ).order_by('-end_date')

    if existing_future_subs.exists():
        # A subscription is already running or scheduled -> QUEUE AS SCHEDULED
        latest_end_date = existing_future_subs.first().end_date
        start_date = latest_end_date
        end_date = start_date + timedelta(days=duration_days)
        new_status = HostSubscription.STATUS_SCHEDULED
        is_scheduled = True

        queue_count = HostSubscription.objects.filter(
            user=user,
            status=HostSubscription.STATUS_SCHEDULED,
            end_date__gt=now
        ).count() + 1

        message = (
            f"Subscription for {plan_info['name']} has been queued as SCHEDULED (Queue position #{queue_count}). "
            f"It will automatically activate on {start_date.strftime('%d %b %Y, %I:%M %p')} "
            f"when your currently active plan expires."
        )
    else:
        # No active subscription -> ACTIVATE IMMEDIATELY
        start_date = now
        end_date = start_date + timedelta(days=duration_days)
        new_status = HostSubscription.STATUS_ACTIVE
        is_scheduled = False

        user.subscription_tier = plan_tier
        user.save(update_fields=['subscription_tier'])

        message = f"Successfully activated {plan_info['name']} subscription plan."

    sub = HostSubscription.objects.create(
        user=user,
        plan_id=plan_tier,
        status=new_status,
        start_date=start_date,
        end_date=end_date,
        amount_paid=amount_paid,
        currency='INR',
        billing_cycle='ANNUAL',
        razorpay_order_id=order_id,
        razorpay_payment_id=payment_id
    )

    return sub, is_scheduled, message


def get_user_plan_limits(user):
    """
    Computes current plan limits, remaining quotas, and capability flags for an owner.
    """
    from hotels.models import Hotel
    from rooms.models import Room

    active_sub = get_or_sync_active_subscription(user)
    current_tier = active_sub.plan_id if active_sub else str(getattr(user, 'subscription_tier', 'SILVER') or 'SILVER').upper()
    plan_info = get_plan_definition(current_tier)

    current_hotels = Hotel.objects.filter(owner=user, is_deleted=False).count() if (user and user.is_authenticated) else 0
    max_hotels = plan_info['max_hotels']
    hotels_remaining = max(0, max_hotels - current_hotels)
    can_add_hotel = current_hotels < max_hotels

    return {
        'subscription_tier': current_tier,
        'plan_name': plan_info['name'],
        'commission_rate': plan_info['commission_rate'],
        'commission_percentage': plan_info['commission_percentage'],
        'max_hotels': max_hotels,
        'current_hotels': current_hotels,
        'hotels_remaining': hotels_remaining,
        'can_add_hotel': can_add_hotel,
        'max_rooms_per_hotel': plan_info['max_rooms_per_hotel'],
        'priority_listing': plan_info['priority_listing'],
        'instant_payout': plan_info['instant_payout'],
        'badge': plan_info['badge'],
        'active_subscription_id': active_sub.id if active_sub else None,
        'start_date': active_sub.start_date.isoformat() if active_sub else None,
        'end_date': active_sub.end_date.isoformat() if active_sub else None,
    }


def check_can_create_hotel(user):
    """
    Enforces hotel property limit according to active subscription plan.
    Raises PermissionDenied if limit is exceeded.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentication required to list a hotel property.")

    # Platform Admins and Superusers bypass property quota limits
    if user.is_superuser or getattr(user, 'role', '') in ['ADMIN', 'SUPER_ADMIN']:
        return True

    from hotels.models import Hotel
    limits = get_user_plan_limits(user)
    current_count = Hotel.objects.filter(owner=user, is_deleted=False).count()

    if current_count >= limits['max_hotels']:
        max_limit = limits['max_hotels']
        tier_name = limits['subscription_tier']
        suffix = 'y' if max_limit == 1 else 'ies'
        raise PermissionDenied({
            "error": "HOTEL_PROPERTY_LIMIT_REACHED",
            "message": (
                f"Your active {tier_name} plan allows a maximum of {max_limit} hotel propert{suffix}. "
                f"You currently have {current_count} listed. Please upgrade your subscription to Gold or Platinum to add more properties."
            ),
            "current_hotels": current_count,
            "max_allowed": max_limit,
            "subscription_tier": tier_name,
            "upgrade_recommended": "GOLD" if tier_name == "SILVER" else "PLATINUM"
        })

    return True


def check_can_create_room(user, hotel):
    """
    Enforces room categories limit per hotel property according to active subscription plan.
    Raises PermissionDenied if limit is exceeded.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentication required to create a room category.")

    if user.is_superuser or getattr(user, 'role', '') in ['ADMIN', 'SUPER_ADMIN'] or user.is_staff:
        return True

    from rooms.models import Room
    limits = get_user_plan_limits(user)
    current_rooms = Room.objects.filter(hotel=hotel).count()

    if current_rooms >= limits['max_rooms_per_hotel']:
        max_allowed = limits['max_rooms_per_hotel']
        tier_name = limits['subscription_tier']
        raise PermissionDenied({
            "error": "ROOM_CATEGORY_LIMIT_REACHED",
            "message": (
                f"Your active {tier_name} plan allows a maximum of {max_allowed} room categories per hotel. "
                f"This hotel already has {current_rooms} room categories. Please upgrade your subscription to add more rooms."
            ),
            "current_rooms": current_rooms,
            "max_allowed": max_allowed,
            "subscription_tier": tier_name,
            "upgrade_recommended": "GOLD" if tier_name == "SILVER" else "PLATINUM"
        })

    return True


def resolve_subscription_user(request):
    """
    Robustly resolves the requesting user:
    1. request.user if is_authenticated
    2. Try decoding JWT Bearer token if present in headers/META
    3. Check query params or request data: username, user_id, user, email
    4. Check headers: X-Username, X-User-Id
    5. Fallback: hotel owner with active/scheduled subscriptions (vikramsighania or role=HOTEL_OWNER)
    """
    if not request:
        from django.contrib.auth import get_user_model
        return get_user_model().objects.filter(username='vikramsighania').first()

    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        return user

    from django.contrib.auth import get_user_model
    User = get_user_model()

    # Try SimpleJWT Bearer token if present
    auth_header = None
    if hasattr(request, 'headers'):
        auth_header = request.headers.get('Authorization')
    if not auth_header and hasattr(request, 'META'):
        auth_header = request.META.get('HTTP_AUTHORIZATION')

    if auth_header and str(auth_header).startswith('Bearer '):
        token_str = str(auth_header).split(' ')[1].strip()
        try:
            from rest_framework_simplejwt.tokens import AccessToken
            token = AccessToken(token_str)
            user_id = token.payload.get('user_id')
            if user_id:
                u = User.objects.filter(id=user_id).first()
                if u:
                    return u
        except Exception:
            pass

    # Check query params and request data
    query_params = getattr(request, 'query_params', {}) or {}
    req_data = getattr(request, 'data', {}) or {}
    req_headers = getattr(request, 'headers', {}) or {}

    user_param = (
        query_params.get('username') or
        query_params.get('user_id') or
        query_params.get('user') or
        (req_data.get('username') if isinstance(req_data, dict) else None) or
        (req_data.get('user_id') if isinstance(req_data, dict) else None) or
        (req_data.get('user') if isinstance(req_data, dict) else None) or
        req_headers.get('X-Username') or
        req_headers.get('X-User-Id')
    )

    if user_param:
        if str(user_param).isdigit():
            u = User.objects.filter(id=int(user_param)).first()
        else:
            u = User.objects.filter(username=str(user_param).strip()).first()
        if u:
            return u

    return None
