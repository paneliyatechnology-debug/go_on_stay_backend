"""
GoOnStay Enterprise Portal Architecture Registry
Provides strictly separated navigation, sidebars, layout definitions,
route permissions, and capability flags for all eight platform roles and departments:
1. ADMIN_PORTAL
2. RESERVATION_PORTAL
3. CUSTOMER_SUPPORT_PORTAL
4. REFUNDS_AND_CLAIMS_PORTAL
5. PAYOUT_AND_ESCROW_PORTAL
6. HOTEL_VERIFICATION_PORTAL
7. CUSTOMER_PORTAL
8. HOTEL_OWNER_PORTAL
"""

PORTAL_ADMIN = 'ADMIN_PORTAL'
PORTAL_RESERVATION = 'RESERVATION_PORTAL'
PORTAL_CUSTOMER_SUPPORT = 'CUSTOMER_SUPPORT_PORTAL'
PORTAL_REFUNDS_AND_CLAIMS = 'REFUNDS_AND_CLAIMS_PORTAL'
PORTAL_PAYOUT_AND_ESCROW = 'PAYOUT_AND_ESCROW_PORTAL'
PORTAL_HOTEL_VERIFICATION = 'HOTEL_VERIFICATION_PORTAL'
PORTAL_CUSTOMER = 'CUSTOMER_PORTAL'
PORTAL_HOTEL_OWNER = 'HOTEL_OWNER_PORTAL'


PORTAL_DEFINITIONS = {
    PORTAL_ADMIN: {
        "portal_id": PORTAL_ADMIN,
        "portal_name": "Admin Portal",
        "dashboard_url": "/admin/dashboard",
        "layout": "AdminLayout",
        "role": "ADMIN",
        "department": None,
        "sidebar": [
            {"id": "admin_dashboard", "title": "Admin Dashboard", "path": "/admin/dashboard", "icon": "layout-dashboard"},
            {"id": "staff_management", "title": "Staff Management", "path": "/admin/staff", "icon": "users-round"},
            {"id": "create_staff", "title": "Create Staff Account", "path": "/admin/staff/create", "icon": "user-plus"},
            {"id": "department_assignment", "title": "Department Assignment", "path": "/admin/departments", "icon": "building-2"},
            {"id": "staff_permissions", "title": "Staff Permissions", "path": "/admin/permissions", "icon": "shield-check"},
            {"id": "customer_management", "title": "Customer Management", "path": "/admin/customers", "icon": "user-check"},
            {"id": "hotel_owner_management", "title": "Hotel Owner Management", "path": "/admin/hotel-owners", "icon": "briefcase"},
            {"id": "hotel_management", "title": "Hotel Management", "path": "/admin/hotels", "icon": "hotel"},
            {"id": "booking_oversight", "title": "Booking Oversight", "path": "/admin/bookings", "icon": "calendar-check"},
            {"id": "payment_management", "title": "Payment Management", "path": "/admin/payments", "icon": "credit-card"},
            {"id": "refund_oversight", "title": "Refund Oversight", "path": "/admin/refunds", "icon": "rotate-ccw"},
            {"id": "payout_oversight", "title": "Payout & Escrow Oversight", "path": "/admin/payouts", "icon": "wallet"},
            {"id": "verification_oversight", "title": "Hotel Verification Oversight", "path": "/admin/verifications", "icon": "badge-check"},
            {"id": "support_oversight", "title": "Support Oversight", "path": "/admin/support", "icon": "headphones"},
            {"id": "reports_analytics", "title": "Reports and Analytics", "path": "/admin/analytics", "icon": "bar-chart-3"},
            {"id": "system_settings", "title": "System Settings", "path": "/admin/settings", "icon": "settings"},
            {"id": "activity_logs", "title": "Activity Logs", "path": "/admin/audit-logs", "icon": "file-text"},
            {"id": "deleted_hotels", "title": "Deleted Hotels Archive", "path": "/admin/deleted-hotels", "icon": "archive"},
        ],
        "permitted_routes": [
            "/admin/dashboard", "/admin/staff", "/admin/staff/create", "/admin/departments",
            "/admin/permissions", "/admin/customers", "/admin/hotel-owners", "/admin/hotels",
            "/admin/bookings", "/admin/payments", "/admin/refunds", "/admin/payouts",
            "/admin/verifications", "/admin/support", "/admin/analytics", "/admin/settings",
            "/admin/audit-logs", "/admin/deleted-hotels"
        ],
        "permitted_actions": ["*"]
    },

    PORTAL_RESERVATION: {
        "portal_id": PORTAL_RESERVATION,
        "portal_name": "Reservation Portal",
        "dashboard_url": "/staff/reservation",
        "layout": "StaffReservationLayout",
        "role": "STAFF",
        "department": "RESERVATION",
        "sidebar": [
            {"id": "res_dashboard", "title": "Reservation Dashboard", "path": "/staff/reservation", "icon": "layout-dashboard"},
            {"id": "res_bookings", "title": "Booking Management", "path": "/staff/reservation/bookings", "icon": "calendar-days"},
            {"id": "res_booking_detail", "title": "Booking Details", "path": "/staff/reservation/bookings/:id", "icon": "file-text", "hidden_from_menu": True},
            {"id": "res_guest_info", "title": "Customer Booking Information", "path": "/staff/reservation/guests", "icon": "user"},
            {"id": "res_room_info", "title": "Hotel and Room Information", "path": "/staff/reservation/rooms", "icon": "bed-double"},
            {"id": "res_operations", "title": "Authorized Reservation Operations", "path": "/staff/reservation/operations", "icon": "check-circle"},
            {"id": "res_activity", "title": "Reservation Activity", "path": "/staff/reservation/activity", "icon": "history"},
        ],
        "permitted_routes": [
            "/staff/reservation", "/staff/reservation/bookings", "/staff/reservation/bookings/:id",
            "/staff/reservation/guests", "/staff/reservation/rooms", "/staff/reservation/operations",
            "/staff/reservation/activity"
        ],
        "permitted_actions": ["VIEW_BOOKINGS", "MANAGE_RESERVATIONS", "ALLOCATE_ROOMS", "CHECKIN_GUEST", "CHECKOUT_GUEST"]
    },

    PORTAL_CUSTOMER_SUPPORT: {
        "portal_id": PORTAL_CUSTOMER_SUPPORT,
        "portal_name": "Customer Support Portal",
        "dashboard_url": "/staff/support",
        "layout": "StaffSupportLayout",
        "role": "STAFF",
        "department": "CUSTOMER_SUPPORT",
        "sidebar": [
            {"id": "cs_dashboard", "title": "Support Dashboard", "path": "/staff/support", "icon": "layout-dashboard"},
            {"id": "cs_tickets", "title": "Support Tickets", "path": "/staff/support/tickets", "icon": "inbox"},
            {"id": "cs_complaints", "title": "Customer Complaints", "path": "/staff/support/complaints", "icon": "alert-circle"},
            {"id": "cs_ticket_detail", "title": "Ticket Details", "path": "/staff/support/tickets/:id", "icon": "message-square", "hidden_from_menu": True},
            {"id": "cs_history", "title": "Customer Support History", "path": "/staff/support/history", "icon": "clock"},
            {"id": "cs_notes", "title": "Internal Notes", "path": "/staff/support/notes", "icon": "sticky-note"},
            {"id": "cs_actions", "title": "Authorized Support Actions", "path": "/staff/support/actions", "icon": "check-circle"},
        ],
        "permitted_routes": [
            "/staff/support", "/staff/support/tickets", "/staff/support/complaints",
            "/staff/support/tickets/:id", "/staff/support/history", "/staff/support/notes",
            "/staff/support/actions"
        ],
        "permitted_actions": ["MANAGE_SUPPORT", "VIEW_TICKETS", "RESPOND_TICKET", "ADD_INTERNAL_NOTE", "ESCALATE_TICKET"]
    },

    PORTAL_REFUNDS_AND_CLAIMS: {
        "portal_id": PORTAL_REFUNDS_AND_CLAIMS,
        "portal_name": "Refunds & Claims Portal",
        "dashboard_url": "/staff/refunds",
        "layout": "StaffRefundsLayout",
        "role": "STAFF",
        "department": "REFUNDS_AND_CLAIMS",
        "sidebar": [
            {"id": "ref_dashboard", "title": "Refund Dashboard", "path": "/staff/refunds", "icon": "layout-dashboard"},
            {"id": "ref_requests", "title": "Refund Requests", "path": "/staff/refunds/requests", "icon": "receipt"},
            {"id": "ref_claims", "title": "Claims Management", "path": "/staff/refunds/claims", "icon": "shield-alert"},
            {"id": "ref_detail", "title": "Refund Details", "path": "/staff/refunds/:id", "icon": "file-search", "hidden_from_menu": True},
            {"id": "ref_eligibility", "title": "Refund Eligibility", "path": "/staff/refunds/eligibility", "icon": "check-circle-2"},
            {"id": "ref_process", "title": "Authorized Refund Processing", "path": "/staff/refunds/process", "icon": "credit-card"},
            {"id": "ref_history", "title": "Refund History", "path": "/staff/refunds/history", "icon": "history"},
        ],
        "permitted_routes": [
            "/staff/refunds", "/staff/refunds/requests", "/staff/refunds/claims",
            "/staff/refunds/:id", "/staff/refunds/eligibility", "/staff/refunds/process",
            "/staff/refunds/history"
        ],
        "permitted_actions": ["VIEW_REFUNDS", "PROCESS_REFUND", "VERIFY_CLAIM", "AUDIT_REFUND"]
    },

    PORTAL_PAYOUT_AND_ESCROW: {
        "portal_id": PORTAL_PAYOUT_AND_ESCROW,
        "portal_name": "Payout & Escrow Portal",
        "dashboard_url": "/staff/payouts",
        "layout": "StaffPayoutsLayout",
        "role": "STAFF",
        "department": "PAYOUT_AND_ESCROW",
        "sidebar": [
            {"id": "pay_dashboard", "title": "Payout Dashboard", "path": "/staff/payouts", "icon": "layout-dashboard"},
            {"id": "pay_requests", "title": "Payout Requests", "path": "/staff/payouts/requests", "icon": "banknote"},
            {"id": "pay_escrow", "title": "Escrow Management", "path": "/staff/payouts/escrow", "icon": "lock"},
            {"id": "pay_settlements", "title": "Settlement Management", "path": "/staff/payouts/settlements", "icon": "coins"},
            {"id": "pay_detail", "title": "Payout Details", "path": "/staff/payouts/:id", "icon": "file-text", "hidden_from_menu": True},
            {"id": "pay_process", "title": "Authorized Payout Processing", "path": "/staff/payouts/process", "icon": "send"},
            {"id": "pay_history", "title": "Payout History", "path": "/staff/payouts/history", "icon": "history"},
        ],
        "permitted_routes": [
            "/staff/payouts", "/staff/payouts/requests", "/staff/payouts/escrow",
            "/staff/payouts/settlements", "/staff/payouts/:id", "/staff/payouts/process",
            "/staff/payouts/history"
        ],
        "permitted_actions": ["VIEW_PAYOUTS", "PROCESS_PAYOUT", "MANAGE_ESCROW", "AUDIT_SETTLEMENT"]
    },

    PORTAL_HOTEL_VERIFICATION: {
        "portal_id": PORTAL_HOTEL_VERIFICATION,
        "portal_name": "Hotel Verification Portal",
        "dashboard_url": "/staff/verification",
        "layout": "StaffVerificationLayout",
        "role": "STAFF",
        "department": "HOTEL_VERIFICATION",
        "sidebar": [
            {"id": "ver_dashboard", "title": "Verification Dashboard", "path": "/staff/verification", "icon": "layout-dashboard"},
            {"id": "ver_pending", "title": "Pending Hotel Applications", "path": "/staff/verification/pending", "icon": "clipboard-list"},
            {"id": "ver_documents", "title": "Hotel Documents", "path": "/staff/verification/documents", "icon": "folder-lock"},
            {"id": "ver_detail", "title": "Hotel Details", "path": "/staff/verification/:id", "icon": "hotel", "hidden_from_menu": True},
            {"id": "ver_review", "title": "Verification Review", "path": "/staff/verification/review", "icon": "search"},
            {"id": "ver_actions", "title": "Approve/Reject Actions", "path": "/staff/verification/actions", "icon": "check-square"},
            {"id": "ver_history", "title": "Verification History", "path": "/staff/verification/history", "icon": "archive"},
        ],
        "permitted_routes": [
            "/staff/verification", "/staff/verification/pending", "/staff/verification/documents",
            "/staff/verification/:id", "/staff/verification/review", "/staff/verification/actions",
            "/staff/verification/history"
        ],
        "permitted_actions": ["VERIFY_HOTEL", "APPROVE_HOTEL", "REJECT_HOTEL", "REVIEW_DOCUMENTS"]
    },

    PORTAL_CUSTOMER: {
        "portal_id": PORTAL_CUSTOMER,
        "portal_name": "Customer Portal",
        "dashboard_url": "/customer/dashboard",
        "layout": "CustomerLayout",
        "role": "CUSTOMER",
        "department": None,
        "sidebar": [
            {"id": "cust_explore", "title": "Explore & Book Hotels", "path": "/hotels", "icon": "search"},
            {"id": "cust_bookings", "title": "My Bookings", "path": "/customer/bookings", "icon": "calendar"},
            {"id": "cust_wishlist", "title": "Saved Wishlist", "path": "/customer/wishlist", "icon": "heart"},
            {"id": "cust_support", "title": "Help & Support Tickets", "path": "/customer/support", "icon": "help-circle"},
            {"id": "cust_profile", "title": "My Profile & Account", "path": "/customer/profile", "icon": "user"},
        ],
        "permitted_routes": [
            "/hotels", "/hotels/:id", "/customer/dashboard", "/customer/bookings",
            "/customer/bookings/:id", "/customer/wishlist", "/customer/support",
            "/customer/profile"
        ],
        "permitted_actions": ["BOOK_ROOM", "CANCEL_BOOKING", "VIEW_OWN_BOOKINGS", "CREATE_TICKET"]
    },

    PORTAL_HOTEL_OWNER: {
        "portal_id": PORTAL_HOTEL_OWNER,
        "portal_name": "Hotel Owner Portal",
        "dashboard_url": "/host/dashboard",
        "layout": "HotelOwnerLayout",
        "role": "HOTEL_OWNER",
        "department": None,
        "sidebar": [
            {"id": "host_dashboard", "title": "Host Dashboard", "path": "/host/dashboard", "icon": "layout-dashboard"},
            {"id": "host_hotels", "title": "My Hotels", "path": "/host/hotels", "icon": "hotel"},
            {"id": "host_rooms", "title": "Rooms & Rates", "path": "/host/rooms", "icon": "bed"},
            {"id": "host_calendar", "title": "Availability Calendar", "path": "/host/calendar", "icon": "calendar"},
            {"id": "host_bookings", "title": "Guest Bookings", "path": "/host/bookings", "icon": "users"},
            {"id": "host_settlements", "title": "Earnings & Settlements", "path": "/host/settlements", "icon": "wallet"},
            {"id": "host_payout_account", "title": "Payout Bank Account", "path": "/host/payout-account", "icon": "landmark"},
            {"id": "host_reviews", "title": "Guest Reviews", "path": "/host/reviews", "icon": "star"},
        ],
        "permitted_routes": [
            "/host/dashboard", "/host/hotels", "/host/hotels/:id", "/host/rooms",
            "/host/calendar", "/host/bookings", "/host/settlements",
            "/host/payout-account", "/host/reviews"
        ],
        "permitted_actions": ["MANAGE_OWN_HOTELS", "MANAGE_ROOMS", "CHECKIN_CHECKOUT", "VIEW_EARNINGS"]
    }
}


def get_portal_for_user(user):
    """
    Determines and returns the strict, isolated portal definition
    for any authenticated user based on role and department.
    """
    if not (user and user.is_authenticated):
        return None

    role = str(getattr(user, 'role', '')).upper()

    # 1. Platform Administrator
    from staff.permissions import is_platform_admin
    if is_platform_admin(user):
        return PORTAL_DEFINITIONS[PORTAL_ADMIN]

    # 2. Staff Member (segregated strictly by department)
    if role == 'STAFF':
        if not hasattr(user, 'staff_profile'):
            return None

        profile = user.staff_profile
        try:
            profile.refresh_from_db(fields=['department', 'status', 'must_change_password'])
        except Exception:
            pass

        if not profile.department:
            return None

        dept_code = profile.department.code
        c = str(dept_code).strip().upper()
        if c in ['RESERVATION', 'RESERVATIONS', 'BOOKING', 'BOOKINGS']:
            return PORTAL_DEFINITIONS[PORTAL_RESERVATION]
        elif c in ['CUSTOMER_SUPPORT', 'SUPPORT', 'CS']:
            return PORTAL_DEFINITIONS[PORTAL_CUSTOMER_SUPPORT]
        elif c in ['REFUNDS_AND_CLAIMS', 'REFUND', 'REFUNDS', 'CLAIMS']:
            return PORTAL_DEFINITIONS[PORTAL_REFUNDS_AND_CLAIMS]
        elif c in ['PAYOUT_AND_ESCROW', 'PAYOUT', 'PAYOUTS', 'ESCROW']:
            return PORTAL_DEFINITIONS[PORTAL_PAYOUT_AND_ESCROW]
        elif c in ['HOTEL_VERIFICATION', 'HOTEL', 'VERIFICATION']:
            return PORTAL_DEFINITIONS[PORTAL_HOTEL_VERIFICATION]
        return None

    # 3. Hotel Owner
    if role in ['HOTEL_OWNER', 'HOTEL_STAFF']:
        return PORTAL_DEFINITIONS[PORTAL_HOTEL_OWNER]

    # 4. Customer
    if role == 'CUSTOMER':
        return _format_portal_dict(PORTAL_DEFINITIONS[PORTAL_CUSTOMER])

    return None


def _format_portal_dict(d):
    """Ensures both snake_case and camelCase keys are available for frontend compatibility."""
    if not d:
        return d
    res = dict(d)
    res["portalId"] = d.get("portal_id", "")
    res["portalName"] = d.get("portal_name", "")
    res["dashboardUrl"] = d.get("dashboard_url", "")
    res["permittedRoutes"] = d.get("permitted_routes", [])
    res["permittedActions"] = d.get("permitted_actions", [])
    return res


# Inject camelCase properties into all definitions for direct registry access
for _k, _v in PORTAL_DEFINITIONS.items():
    _v["portalId"] = _v.get("portal_id")
    _v["portalName"] = _v.get("portal_name")
    _v["dashboardUrl"] = _v.get("dashboard_url")
    _v["permittedRoutes"] = _v.get("permitted_routes")
    _v["permittedActions"] = _v.get("permitted_actions")

