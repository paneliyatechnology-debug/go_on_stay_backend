/**
 * GoOnStay Enterprise Portal Architecture - TypeScript Contract & Registry
 * Strictly isolates all 8 platform roles and departments.
 * Zero mixed sidebars, zero shared leaked pages.
 */

export type PlatformRole = 'ADMIN' | 'STAFF' | 'HOTEL_OWNER' | 'CUSTOMER';

export type StaffDepartmentCode = 
  | 'RESERVATION'
  | 'CUSTOMER_SUPPORT'
  | 'REFUNDS_AND_CLAIMS'
  | 'PAYOUT_AND_ESCROW'
  | 'HOTEL_VERIFICATION';

export type PortalId = 
  | 'ADMIN_PORTAL'
  | 'RESERVATION_PORTAL'
  | 'CUSTOMER_SUPPORT_PORTAL'
  | 'REFUNDS_AND_CLAIMS_PORTAL'
  | 'PAYOUT_AND_ESCROW_PORTAL'
  | 'HOTEL_VERIFICATION_PORTAL'
  | 'CUSTOMER_PORTAL'
  | 'HOTEL_OWNER_PORTAL';

export interface SidebarItem {
  id: string;
  title: string;
  path: string;
  icon: string;
  badge?: string;
  hiddenFromMenu?: boolean;
}

export interface PortalDefinition {
  portalId: PortalId;
  portalName: string;
  dashboardUrl: string;
  layout: string;
  role: PlatformRole;
  department: StaffDepartmentCode | null;
  sidebar: SidebarItem[];
  permittedRoutes: string[];
  permittedActions: string[];
}

export const PORTAL_ADMIN: PortalDefinition = {
  portalId: 'ADMIN_PORTAL',
  portalName: 'Admin Portal',
  dashboardUrl: '/admin/dashboard',
  layout: 'AdminLayout',
  role: 'ADMIN',
  department: null,
  sidebar: [
    { id: 'admin_dashboard', title: 'Admin Dashboard', path: '/admin/dashboard', icon: 'layout-dashboard' },
    { id: 'staff_management', title: 'Staff Management', path: '/admin/staff', icon: 'users-round' },
    { id: 'create_staff', title: 'Create Staff Account', path: '/admin/staff/create', icon: 'user-plus' },
    { id: 'department_assignment', title: 'Department Assignment', path: '/admin/departments', icon: 'building-2' },
    { id: 'staff_permissions', title: 'Staff Permissions', path: '/admin/permissions', icon: 'shield-check' },
    { id: 'customer_management', title: 'Customer Management', path: '/admin/customers', icon: 'user-check' },
    { id: 'hotel_owner_management', title: 'Hotel Owner Management', path: '/admin/hotel-owners', icon: 'briefcase' },
    { id: 'hotel_management', title: 'Hotel Management', path: '/admin/hotels', icon: 'hotel' },
    { id: 'booking_oversight', title: 'Booking Oversight', path: '/admin/bookings', icon: 'calendar-check' },
    { id: 'payment_management', title: 'Payment Management', path: '/admin/payments', icon: 'credit-card' },
    { id: 'refund_oversight', title: 'Refund Oversight', path: '/admin/refunds', icon: 'rotate-ccw' },
    { id: 'payout_oversight', title: 'Payout & Escrow Oversight', path: '/admin/payouts', icon: 'wallet' },
    { id: 'verification_oversight', title: 'Hotel Verification Oversight', path: '/admin/verifications', icon: 'badge-check' },
    { id: 'support_oversight', title: 'Support Oversight', path: '/admin/support', icon: 'headphones' },
    { id: 'reports_analytics', title: 'Reports and Analytics', path: '/admin/analytics', icon: 'bar-chart-3' },
    { id: 'system_settings', title: 'System Settings', path: '/admin/settings', icon: 'settings' },
    { id: 'activity_logs', title: 'Activity Logs', path: '/admin/audit-logs', icon: 'file-text' },
    { id: 'deleted_hotels', title: 'Deleted Hotels Archive', path: '/admin/deleted-hotels', icon: 'archive' },
  ],
  permittedRoutes: [
    '/admin/dashboard', '/admin/staff', '/admin/staff/create', '/admin/departments',
    '/admin/permissions', '/admin/customers', '/admin/hotel-owners', '/admin/hotels',
    '/admin/bookings', '/admin/payments', '/admin/refunds', '/admin/payouts',
    '/admin/verifications', '/admin/support', '/admin/analytics', '/admin/settings',
    '/admin/audit-logs', '/admin/deleted-hotels'
  ],
  permittedActions: ['*']
};

export const PORTAL_RESERVATION: PortalDefinition = {
  portalId: 'RESERVATION_PORTAL',
  portalName: 'Reservation Portal',
  dashboardUrl: '/staff/reservation',
  layout: 'StaffReservationLayout',
  role: 'STAFF',
  department: 'RESERVATION',
  sidebar: [
    { id: 'res_dashboard', title: 'Reservation Dashboard', path: '/staff/reservation', icon: 'layout-dashboard' },
    { id: 'res_bookings', title: 'Booking Management', path: '/staff/reservation/bookings', icon: 'calendar-days' },
    { id: 'res_booking_detail', title: 'Booking Details', path: '/staff/reservation/bookings/:id', icon: 'file-text', hiddenFromMenu: true },
    { id: 'res_guest_info', title: 'Customer Booking Information', path: '/staff/reservation/guests', icon: 'user' },
    { id: 'res_room_info', title: 'Hotel and Room Information', path: '/staff/reservation/rooms', icon: 'bed-double' },
    { id: 'res_operations', title: 'Authorized Reservation Operations', path: '/staff/reservation/operations', icon: 'check-circle' },
    { id: 'res_activity', title: 'Reservation Activity', path: '/staff/reservation/activity', icon: 'history' },
  ],
  permittedRoutes: [
    '/staff/reservation', '/staff/reservation/bookings', '/staff/reservation/bookings/:id',
    '/staff/reservation/guests', '/staff/reservation/rooms', '/staff/reservation/operations',
    '/staff/reservation/activity'
  ],
  permittedActions: ['VIEW_BOOKINGS', 'MANAGE_RESERVATIONS', 'ALLOCATE_ROOMS', 'CHECKIN_GUEST', 'CHECKOUT_GUEST']
};

export const PORTAL_CUSTOMER_SUPPORT: PortalDefinition = {
  portalId: 'CUSTOMER_SUPPORT_PORTAL',
  portalName: 'Customer Support Portal',
  dashboardUrl: '/staff/support',
  layout: 'StaffSupportLayout',
  role: 'STAFF',
  department: 'CUSTOMER_SUPPORT',
  sidebar: [
    { id: 'cs_dashboard', title: 'Support Dashboard', path: '/staff/support', icon: 'layout-dashboard' },
    { id: 'cs_tickets', title: 'Support Tickets', path: '/staff/support/tickets', icon: 'inbox' },
    { id: 'cs_complaints', title: 'Customer Complaints', path: '/staff/support/complaints', icon: 'alert-circle' },
    { id: 'cs_ticket_detail', title: 'Ticket Details', path: '/staff/support/tickets/:id', icon: 'message-square', hiddenFromMenu: true },
    { id: 'cs_history', title: 'Customer Support History', path: '/staff/support/history', icon: 'clock' },
    { id: 'cs_notes', title: 'Internal Notes', path: '/staff/support/notes', icon: 'sticky-note' },
    { id: 'cs_actions', title: 'Authorized Support Actions', path: '/staff/support/actions', icon: 'check-circle' },
  ],
  permittedRoutes: [
    '/staff/support', '/staff/support/tickets', '/staff/support/complaints',
    '/staff/support/tickets/:id', '/staff/support/history', '/staff/support/notes',
    '/staff/support/actions'
  ],
  permittedActions: ['MANAGE_SUPPORT', 'VIEW_TICKETS', 'RESPOND_TICKET', 'ADD_INTERNAL_NOTE', 'ESCALATE_TICKET']
};

export const PORTAL_REFUNDS_AND_CLAIMS: PortalDefinition = {
  portalId: 'REFUNDS_AND_CLAIMS_PORTAL',
  portalName: 'Refunds & Claims Portal',
  dashboardUrl: '/staff/refunds',
  layout: 'StaffRefundsLayout',
  role: 'STAFF',
  department: 'REFUNDS_AND_CLAIMS',
  sidebar: [
    { id: 'ref_dashboard', title: 'Refund Dashboard', path: '/staff/refunds', icon: 'layout-dashboard' },
    { id: 'ref_requests', title: 'Refund Requests', path: '/staff/refunds/requests', icon: 'receipt' },
    { id: 'ref_claims', title: 'Claims Management', path: '/staff/refunds/claims', icon: 'shield-alert' },
    { id: 'ref_detail', title: 'Refund Details', path: '/staff/refunds/:id', icon: 'file-search', hiddenFromMenu: true },
    { id: 'ref_eligibility', title: 'Refund Eligibility', path: '/staff/refunds/eligibility', icon: 'check-circle-2' },
    { id: 'ref_process', title: 'Authorized Refund Processing', path: '/staff/refunds/process', icon: 'credit-card' },
    { id: 'ref_history', title: 'Refund History', path: '/staff/refunds/history', icon: 'history' },
  ],
  permittedRoutes: [
    '/staff/refunds', '/staff/refunds/requests', '/staff/refunds/claims',
    '/staff/refunds/:id', '/staff/refunds/eligibility', '/staff/refunds/process',
    '/staff/refunds/history'
  ],
  permittedActions: ['VIEW_REFUNDS', 'PROCESS_REFUND', 'VERIFY_CLAIM', 'AUDIT_REFUND']
};

export const PORTAL_PAYOUT_AND_ESCROW: PortalDefinition = {
  portalId: 'PAYOUT_AND_ESCROW_PORTAL',
  portalName: 'Payout & Escrow Portal',
  dashboardUrl: '/staff/payouts',
  layout: 'StaffPayoutsLayout',
  role: 'STAFF',
  department: 'PAYOUT_AND_ESCROW',
  sidebar: [
    { id: 'pay_dashboard', title: 'Payout Dashboard', path: '/staff/payouts', icon: 'layout-dashboard' },
    { id: 'pay_requests', title: 'Payout Requests', path: '/staff/payouts/requests', icon: 'banknote' },
    { id: 'pay_escrow', title: 'Escrow Management', path: '/staff/payouts/escrow', icon: 'lock' },
    { id: 'pay_settlements', title: 'Settlement Management', path: '/staff/payouts/settlements', icon: 'coins' },
    { id: 'pay_detail', title: 'Payout Details', path: '/staff/payouts/:id', icon: 'file-text', hiddenFromMenu: true },
    { id: 'pay_process', title: 'Authorized Payout Processing', path: '/staff/payouts/process', icon: 'send' },
    { id: 'pay_history', title: 'Payout History', path: '/staff/payouts/history', icon: 'history' },
  ],
  permittedRoutes: [
    '/staff/payouts', '/staff/payouts/requests', '/staff/payouts/escrow',
    '/staff/payouts/settlements', '/staff/payouts/:id', '/staff/payouts/process',
    '/staff/payouts/history'
  ],
  permittedActions: ['VIEW_PAYOUTS', 'PROCESS_PAYOUT', 'MANAGE_ESCROW', 'AUDIT_SETTLEMENT']
};

export const PORTAL_HOTEL_VERIFICATION: PortalDefinition = {
  portalId: 'HOTEL_VERIFICATION_PORTAL',
  portalName: 'Hotel Verification Portal',
  dashboardUrl: '/staff/verification',
  layout: 'StaffVerificationLayout',
  role: 'STAFF',
  department: 'HOTEL_VERIFICATION',
  sidebar: [
    { id: 'ver_dashboard', title: 'Verification Dashboard', path: '/staff/verification', icon: 'layout-dashboard' },
    { id: 'ver_pending', title: 'Pending Hotel Applications', path: '/staff/verification/pending', icon: 'clipboard-list' },
    { id: 'ver_documents', title: 'Hotel Documents', path: '/staff/verification/documents', icon: 'folder-lock' },
    { id: 'ver_detail', title: 'Hotel Details', path: '/staff/verification/:id', icon: 'hotel', hiddenFromMenu: true },
    { id: 'ver_review', title: 'Verification Review', path: '/staff/verification/review', icon: 'search' },
    { id: 'ver_actions', title: 'Approve/Reject Actions', path: '/staff/verification/actions', icon: 'check-square' },
    { id: 'ver_history', title: 'Verification History', path: '/staff/verification/history', icon: 'archive' },
  ],
  permittedRoutes: [
    '/staff/verification', '/staff/verification/pending', '/staff/verification/documents',
    '/staff/verification/:id', '/staff/verification/review', '/staff/verification/actions',
    '/staff/verification/history'
  ],
  permittedActions: ['VERIFY_HOTEL', 'APPROVE_HOTEL', 'REJECT_HOTEL', 'REVIEW_DOCUMENTS']
};

export const PORTAL_CUSTOMER: PortalDefinition = {
  portalId: 'CUSTOMER_PORTAL',
  portalName: 'Customer Portal',
  dashboardUrl: '/customer/dashboard',
  layout: 'CustomerLayout',
  role: 'CUSTOMER',
  department: null,
  sidebar: [
    { id: 'cust_explore', title: 'Explore & Book Hotels', path: '/hotels', icon: 'search' },
    { id: 'cust_bookings', title: 'My Bookings', path: '/customer/bookings', icon: 'calendar' },
    { id: 'cust_wishlist', title: 'Saved Wishlist', path: '/customer/wishlist', icon: 'heart' },
    { id: 'cust_support', title: 'Help & Support Tickets', path: '/customer/support', icon: 'help-circle' },
    { id: 'cust_profile', title: 'My Profile & Account', path: '/customer/profile', icon: 'user' },
  ],
  permittedRoutes: [
    '/hotels', '/hotels/:id', '/customer/dashboard', '/customer/bookings',
    '/customer/bookings/:id', '/customer/wishlist', '/customer/support',
    '/customer/profile'
  ],
  permittedActions: ['BOOK_ROOM', 'CANCEL_BOOKING', 'VIEW_OWN_BOOKINGS', 'CREATE_TICKET']
};

export const PORTAL_HOTEL_OWNER: PortalDefinition = {
  portalId: 'HOTEL_OWNER_PORTAL',
  portalName: 'Hotel Owner Portal',
  dashboardUrl: '/host/dashboard',
  layout: 'HotelOwnerLayout',
  role: 'HOTEL_OWNER',
  department: null,
  sidebar: [
    { id: 'host_dashboard', title: 'Host Dashboard', path: '/host/dashboard', icon: 'layout-dashboard' },
    { id: 'host_hotels', title: 'My Hotels', path: '/host/hotels', icon: 'hotel' },
    { id: 'host_rooms', title: 'Rooms & Rates', path: '/host/rooms', icon: 'bed' },
    { id: 'host_calendar', title: 'Availability Calendar', path: '/host/calendar', icon: 'calendar' },
    { id: 'host_bookings', title: 'Guest Bookings', path: '/host/bookings', icon: 'users' },
    { id: 'host_settlements', title: 'Earnings & Settlements', path: '/host/settlements', icon: 'wallet' },
    { id: 'host_payout_account', title: 'Payout Bank Account', path: '/host/payout-account', icon: 'landmark' },
    { id: 'host_reviews', title: 'Guest Reviews', path: '/host/reviews', icon: 'star' },
  ],
  permittedRoutes: [
    '/host/dashboard', '/host/hotels', '/host/hotels/:id', '/host/rooms',
    '/host/calendar', '/host/bookings', '/host/settlements',
    '/host/payout-account', '/host/reviews'
  ],
  permittedActions: ['MANAGE_OWN_HOTELS', 'MANAGE_ROOMS', 'CHECKIN_CHECKOUT', 'VIEW_EARNINGS']
};

export const PORTAL_REGISTRY: Record<PortalId, PortalDefinition> = {
  ADMIN_PORTAL: PORTAL_ADMIN,
  RESERVATION_PORTAL: PORTAL_RESERVATION,
  CUSTOMER_SUPPORT_PORTAL: PORTAL_CUSTOMER_SUPPORT,
  REFUNDS_AND_CLAIMS_PORTAL: PORTAL_REFUNDS_AND_CLAIMS,
  PAYOUT_AND_ESCROW_PORTAL: PORTAL_PAYOUT_AND_ESCROW,
  HOTEL_VERIFICATION_PORTAL: PORTAL_HOTEL_VERIFICATION,
  CUSTOMER_PORTAL: PORTAL_CUSTOMER,
  HOTEL_OWNER_PORTAL: PORTAL_HOTEL_OWNER,
};
