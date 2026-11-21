/**
 * GoOnStay Enterprise Notification Click-Through Navigation Engine
 * 
 * Implements realistic, role-aware, and record-exact navigation across
 * Customer, Hotel Owner, Admin, and all 5 Staff Departments.
 * 
 * Features:
 * - Immediate optimistic state update (bell badge & unread dot)
 * - Non-blocking asynchronous mark-as-read API execution
 * - Exact record targeting (passes ID in route / state highlight)
 * - Strict role and department isolation (Zero cross-portal leakage)
 * - Rapid duplicate click debounce & prevention
 * - Missing/deleted record fallback with user alert
 * - Expired session preservation
 */

import { UserSession } from './portalApi';

export interface NotificationItem {
  id: number;
  title: string;
  message: string;
  notification_type: string;
  booking?: number | null;
  booking_id?: string;
  hotel_name?: string;
  target_url?: string;
  target_entity_type?: string;
  target_entity_id?: string;
  fallback_url?: string;
  action?: string;
  record_exists?: boolean;
  is_read: boolean;
  read_at?: string | null;
  metadata?: Record<string, any>;
  created_at: string;
}

export interface ResolvedDestination {
  targetUrl: string;
  targetEntityType: string;
  targetEntityId: string;
  fallbackUrl: string;
  action: string;
  recordExists: boolean;
}

export interface NotificationClickOptions {
  notification: NotificationItem;
  user: UserSession | null;
  navigate: (to: string, options?: { state?: any; replace?: boolean }) => void;
  showToast?: (message: string, type?: 'info' | 'success' | 'warning' | 'error') => void;
  onMarkReadOptimistic?: (id: number) => void;
  apiBaseUrl?: string;
  token?: string;
}

// In-memory set for rapid click debounce (suppresses duplicate clicks within 1200ms)
const activeClickDebounce = new Set<number>();

/**
 * Resolves destination client-side when payload doesn't already contain pre-computed URLs,
 * or verifies that pre-computed URLs strictly adhere to role boundaries.
 */
export function resolveNotificationDestination(
  notif: NotificationItem,
  user: UserSession | null
): ResolvedDestination {
  // If pre-computed on backend, use it directly after role validation
  if (notif.target_url) {
    const safeUrl = sanitizeDestinationForRole(notif.target_url, user, notif.fallback_url || '/');
    return {
      targetUrl: safeUrl,
      targetEntityType: notif.target_entity_type || 'general',
      targetEntityId: notif.target_entity_id || notif.booking_id || '',
      fallbackUrl: notif.fallback_url || safeUrl,
      action: notif.action || 'open_record',
      recordExists: notif.record_exists !== false
    };
  }

  const role = (user?.role || 'CUSTOMER').toUpperCase();
  const isStaff = Boolean(user?.isStaff || role === 'STAFF');
  const isAdmin = Boolean(role === 'ADMIN' || role === 'SUPER_ADMIN');
  const dept = (user?.department || 'RESERVATION').toUpperCase();

  const type = (notif.notification_type || 'GENERAL').toUpperCase();
  const meta = notif.metadata || {};
  const bookingId = notif.booking_id || meta.booking_id || extractRegex(notif.title + ' ' + notif.message, /BMR[A-Za-z0-9_-]+/i);
  const ticketId = meta.ticket_id || meta.ticket_number || extractRegex(notif.title + ' ' + notif.message, /(?:ticket|complaint)\s*#?([A-Za-z0-9_-]+)/i);
  const refundId = meta.refund_id || meta.claim_id || extractRegex(notif.title + ' ' + notif.message, /(?:refund|claim)\s*#?(\d+)/i);
  const payoutId = meta.payout_id || meta.earning_id || extractRegex(notif.title + ' ' + notif.message, /(?:payout|settlement)\s*#?(\d+)/i);
  const hotelId = meta.hotel_id || extractRegex(notif.title + ' ' + notif.message, /(?:hotel|property)\s*#?(\d+)/i);

  // 1. ADMIN
  if (isAdmin) {
    if (bookingId) return { targetUrl: `/admin/bookings?booking_id=${bookingId}`, targetEntityType: 'booking', targetEntityId: bookingId, fallbackUrl: '/admin/bookings', action: 'highlight_record', recordExists: true };
    if (ticketId) return { targetUrl: `/admin/support?ticket_id=${ticketId}`, targetEntityType: 'ticket', targetEntityId: ticketId, fallbackUrl: '/admin/support', action: 'highlight_record', recordExists: true };
    if (refundId) return { targetUrl: `/admin/refunds?refund_id=${refundId}`, targetEntityType: 'refund', targetEntityId: refundId, fallbackUrl: '/admin/refunds', action: 'highlight_record', recordExists: true };
    if (payoutId) return { targetUrl: `/admin/payouts?payout_id=${payoutId}`, targetEntityType: 'payout', targetEntityId: payoutId, fallbackUrl: '/admin/payouts', action: 'highlight_record', recordExists: true };
    if (hotelId) return { targetUrl: `/admin/verifications?hotel_id=${hotelId}`, targetEntityType: 'hotel', targetEntityId: hotelId, fallbackUrl: '/admin/verifications', action: 'highlight_record', recordExists: true };
    return { targetUrl: '/admin/dashboard', targetEntityType: 'general', targetEntityId: '', fallbackUrl: '/admin/dashboard', action: 'view_dashboard', recordExists: true };
  }

  // 2. STAFF (Strict Department Isolation)
  if (isStaff) {
    if (dept === 'RESERVATION') {
      if (bookingId) return { targetUrl: `/staff/reservation/bookings/${bookingId}`, targetEntityType: 'booking', targetEntityId: bookingId, fallbackUrl: '/staff/reservation/bookings', action: 'open_record', recordExists: true };
      return { targetUrl: '/staff/reservation/bookings', targetEntityType: 'booking', targetEntityId: '', fallbackUrl: '/staff/reservation', action: 'view_list', recordExists: true };
    }
    if (dept === 'CUSTOMER_SUPPORT') {
      if (ticketId) return { targetUrl: `/staff/support/tickets/${ticketId}`, targetEntityType: 'ticket', targetEntityId: ticketId, fallbackUrl: '/staff/support/tickets', action: 'open_record', recordExists: true };
      return { targetUrl: '/staff/support/tickets', targetEntityType: 'ticket', targetEntityId: '', fallbackUrl: '/staff/support', action: 'view_list', recordExists: true };
    }
    if (dept === 'REFUNDS_AND_CLAIMS') {
      if (refundId) return { targetUrl: `/staff/refunds/${refundId}`, targetEntityType: 'refund', targetEntityId: refundId, fallbackUrl: '/staff/refunds/requests', action: 'open_record', recordExists: true };
      return { targetUrl: '/staff/refunds/requests', targetEntityType: 'refund', targetEntityId: '', fallbackUrl: '/staff/refunds', action: 'view_list', recordExists: true };
    }
    if (dept === 'PAYOUT_AND_ESCROW') {
      if (payoutId) return { targetUrl: `/staff/payouts/${payoutId}`, targetEntityType: 'payout', targetEntityId: payoutId, fallbackUrl: '/staff/payouts/requests', action: 'open_record', recordExists: true };
      if (type.includes('ESCROW')) return { targetUrl: '/staff/payouts/escrow', targetEntityType: 'payout', targetEntityId: '', fallbackUrl: '/staff/payouts', action: 'view_escrow', recordExists: true };
      return { targetUrl: '/staff/payouts/requests', targetEntityType: 'payout', targetEntityId: '', fallbackUrl: '/staff/payouts', action: 'view_list', recordExists: true };
    }
    if (dept === 'HOTEL_VERIFICATION') {
      if (hotelId) return { targetUrl: `/staff/verification/${hotelId}`, targetEntityType: 'hotel', targetEntityId: hotelId, fallbackUrl: '/staff/verification/pending', action: 'open_record', recordExists: true };
      return { targetUrl: '/staff/verification/pending', targetEntityType: 'hotel', targetEntityId: '', fallbackUrl: '/staff/verification', action: 'view_list', recordExists: true };
    }
    return { targetUrl: '/staff/reservation', targetEntityType: 'general', targetEntityId: '', fallbackUrl: '/staff/reservation', action: 'view_dashboard', recordExists: true };
  }

  // 3. HOTEL OWNER
  if (role === 'HOTEL_OWNER') {
    if (type.includes('PAYOUT') || type.includes('SETTLEMENT') || payoutId) {
      return { targetUrl: payoutId ? `/host/settlements?payout_id=${payoutId}` : '/host/settlements', targetEntityType: 'payout', targetEntityId: payoutId || '', fallbackUrl: '/host/settlements', action: 'view_list', recordExists: true };
    }
    if (type.includes('HOTEL') || hotelId) {
      return { targetUrl: hotelId ? `/host/hotels/${hotelId}` : '/host/hotels', targetEntityType: 'hotel', targetEntityId: hotelId || '', fallbackUrl: '/host/hotels', action: 'open_record', recordExists: true };
    }
    if (bookingId) {
      return { targetUrl: `/host/bookings/${bookingId}`, targetEntityType: 'booking', targetEntityId: bookingId, fallbackUrl: '/host/bookings', action: 'open_record', recordExists: true };
    }
    return { targetUrl: '/host/dashboard', targetEntityType: 'general', targetEntityId: '', fallbackUrl: '/host/dashboard', action: 'view_dashboard', recordExists: true };
  }

  // 4. CUSTOMER (Default)
  if (ticketId || type.includes('SUPPORT')) {
    return { targetUrl: ticketId ? `/customer/support?ticket_id=${ticketId}` : '/customer/support', targetEntityType: 'ticket', targetEntityId: ticketId || '', fallbackUrl: '/customer/support', action: 'open_record', recordExists: true };
  }
  if (bookingId) {
    return { targetUrl: `/customer/bookings/${bookingId}`, targetEntityType: 'booking', targetEntityId: bookingId, fallbackUrl: '/customer/bookings', action: 'open_record', recordExists: true };
  }
  if (type.includes('OFFER') || type.includes('COUPON')) {
    return { targetUrl: '/hotels', targetEntityType: 'offer', targetEntityId: '', fallbackUrl: '/hotels', action: 'explore_hotels', recordExists: true };
  }
  if (type.includes('PROFILE') || type.includes('ACCOUNT')) {
    return { targetUrl: '/customer/profile', targetEntityType: 'profile', targetEntityId: '', fallbackUrl: '/customer/profile', action: 'view_profile', recordExists: true };
  }

  return { targetUrl: '/customer/dashboard', targetEntityType: 'general', targetEntityId: '', fallbackUrl: '/customer/dashboard', action: 'view_dashboard', recordExists: true };
}

/**
 * Validates that the target path is strictly permitted for the user's role and department.
 * Prevents staff leakage into Admin, customer leakage into Host, etc.
 */
function sanitizeDestinationForRole(url: string, user: UserSession | null, fallback: string): string {
  if (!user) return fallback;
  const role = (user.role || 'CUSTOMER').toUpperCase();
  const isStaff = Boolean(user.isStaff || role === 'STAFF');
  const isAdmin = Boolean(role === 'ADMIN' || role === 'SUPER_ADMIN');
  const dept = (user.department || 'RESERVATION').toUpperCase();

  if (isAdmin) {
    if (url.startsWith('/admin')) return url;
    return '/admin/dashboard';
  }

  if (isStaff) {
    const deptPrefixMap: Record<string, string> = {
      RESERVATION: '/staff/reservation',
      CUSTOMER_SUPPORT: '/staff/support',
      REFUNDS_AND_CLAIMS: '/staff/refunds',
      PAYOUT_AND_ESCROW: '/staff/payouts',
      HOTEL_VERIFICATION: '/staff/verification'
    };
    const allowedPrefix = deptPrefixMap[dept] || '/staff/reservation';
    if (url.startsWith(allowedPrefix)) return url;
    return allowedPrefix;
  }

  if (role === 'HOTEL_OWNER') {
    if (url.startsWith('/host')) return url;
    return '/host/dashboard';
  }

  // Customer
  if (url.startsWith('/admin') || url.startsWith('/staff') || url.startsWith('/host')) {
    return '/customer/dashboard';
  }
  return url;
}

function extractRegex(text: string, regex: RegExp): string {
  const m = regex.exec(text);
  return m ? m[1] || m[0] : '';
}

/**
 * Master notification click handler.
 * Executed whenever a user clicks any notification in any portal.
 */
export async function handleNotificationClick(options: NotificationClickOptions): Promise<void> {
  const {
    notification,
    user,
    navigate,
    showToast,
    onMarkReadOptimistic,
    apiBaseUrl = process.env.REACT_APP_API_URL || 'http://localhost:8000',
    token = localStorage.getItem('access_token') || sessionStorage.getItem('access_token') || ''
  } = options;

  // 1. Debounce rapid duplicate clicks on the exact same notification
  if (activeClickDebounce.has(notification.id)) {
    return;
  }
  activeClickDebounce.add(notification.id);
  setTimeout(() => activeClickDebounce.delete(notification.id), 1200);

  // 2. Immediate optimistic state update (bell count and unread dot)
  if (!notification.is_read) {
    notification.is_read = true;
    if (onMarkReadOptimistic) {
      onMarkReadOptimistic(notification.id);
    }
  }

  // 3. Resolve role-aware destination
  const destination = resolveNotificationDestination(notification, user);

  // 4. Non-blocking asynchronous mark-as-read API execution
  triggerAsyncMarkAsRead(notification.id, user, token, apiBaseUrl);

  // 5. Handle session expiration or unauthenticated access
  if (!token && !user) {
    const loginPath = user?.isStaff ? '/staff/login' : '/login';
    if (showToast) showToast('Please sign in to view this notification.', 'info');
    navigate(`${loginPath}?returnUrl=${encodeURIComponent(destination.targetUrl)}`);
    return;
  }

  // 6. Handle deleted or missing record edge cases
  if (destination.recordExists === false) {
    if (showToast) {
      showToast(`The requested ${destination.targetEntityType} record is no longer available. Redirecting to listing.`, 'warning');
    }
    navigate(destination.fallbackUrl, {
      state: { source: 'notification', error: 'RECORD_NOT_FOUND', notifId: notification.id }
    });
    return;
  }

  // 7. Perform clean React Router navigation with highlight state
  try {
    navigate(destination.targetUrl, {
      state: {
        source: 'notification',
        highlightId: destination.targetEntityId,
        action: destination.action,
        notifId: notification.id
      }
    });
  } catch (navErr) {
    console.error('[NotificationNavigation] Failed to navigate to target:', navErr);
    navigate(destination.fallbackUrl);
  }
}

/**
 * Fire-and-forget backend mark-as-read call.
 * Navigation proceeds immediately without awaiting this HTTP call.
 */
function triggerAsyncMarkAsRead(
  notifId: number,
  user: UserSession | null,
  token: string,
  apiBaseUrl: string
): void {
  if (!token) return;

  const isStaff = Boolean(user?.isStaff || user?.role === 'STAFF');
  const endpoint = isStaff
    ? `${apiBaseUrl}/api/staff/notifications/${notifId}/read/`
    : `${apiBaseUrl}/api/notifications/${notifId}/read/`;

  const method = isStaff ? 'PATCH' : 'POST';

  fetch(endpoint, {
    method,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    }
  }).catch((err) => {
    // Non-blocking: warning only, user navigation is never interrupted
    console.warn(`[triggerAsyncMarkAsRead] Non-blocking mark-read warning for #${notifId}:`, err);
  });
}
