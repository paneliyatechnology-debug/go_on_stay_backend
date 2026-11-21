/**
 * GoOnStay Portal API Client
 * Interfaces directly with the backend centralized navigation contract
 * and department-isolated endpoints.
 * Includes hardened response parsing, error message preservation, and safe non-JSON handling.
 */

import { PortalDefinition } from '../config/portals';

export interface UserSession {
  id: number;
  email: string;
  fullName: string;
  role: string;
  isStaff: boolean;
  department?: string | null;
  departmentName?: string | null;
  employeeId?: string | null;
}

export interface NavigationResponse {
  success: boolean;
  user: UserSession;
  portal: PortalDefinition;
  dashboardUrl: string;
  layout: string;
  navigation: PortalDefinition['sidebar'];
  permittedRoutes: string[];
  permittedActions: string[];
  message?: string;
  code?: string;
}

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

function authHeaders(token: string) {
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  };
}

/**
 * Robust response handler:
 * - Safely handles application/json, text, and empty responses.
 * - Prevents SyntaxError exceptions when server returns HTML error pages (e.g. 500, 502) or 204 No Content.
 * - Preserves detailed backend error messages (data.error, data.message, data.detail, etc.).
 */
async function handleResponse<T = any>(res: Response, defaultError: string): Promise<T> {
  const contentType = res.headers.get('content-type') || '';
  let data: any = null;

  if (contentType.includes('application/json')) {
    try {
      data = await res.json();
    } catch {
      data = null;
    }
  } else {
    try {
      const text = await res.text();
      if (text) {
        try {
          data = JSON.parse(text);
        } catch {
          data = text;
        }
      }
    } catch {
      data = null;
    }
  }

  if (!res.ok) {
    let message = defaultError;
    if (data && typeof data === 'object') {
      message = data.error || data.message || data.detail || (Array.isArray(data.non_field_errors) ? data.non_field_errors[0] : null) || defaultError;
    } else if (typeof data === 'string' && data.length > 0 && data.length < 300) {
      message = data;
    }
    const err = new Error(message);
    (err as any).status = res.status;
    (err as any).code = (data && typeof data === 'object' && data.code) ? data.code : undefined;
    (err as any).data = data;
    throw err;
  }

  return (data !== null ? data : ({} as T));
}

export async function fetchPortalNavigation(token: string): Promise<NavigationResponse> {
  const response = await fetch(`${API_BASE_URL}/api/portal/navigation/`, {
    method: 'GET',
    headers: authHeaders(token)
  });
  return handleResponse<NavigationResponse>(response, 'Failed to fetch portal navigation');
}

export async function fetchAdminDashboard(token: string) {
  const response = await fetch(`${API_BASE_URL}/api/admin/dashboard/`, {
    headers: authHeaders(token)
  });
  return handleResponse(response, 'Unauthorized admin dashboard access');
}

export async function fetchStaffDepartmentDashboard(departmentCode: string, token: string) {
  const endpointMap: Record<string, string> = {
    RESERVATION: '/api/staff/reservation/dashboard/',
    CUSTOMER_SUPPORT: '/api/staff/support/dashboard/',
    REFUNDS_AND_CLAIMS: '/api/staff/refunds/dashboard/',
    PAYOUT_AND_ESCROW: '/api/staff/payouts/dashboard/',
    HOTEL_VERIFICATION: '/api/staff/verification/dashboard/'
  };

  const endpoint = endpointMap[departmentCode] || '/api/staff/dashboard/';
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    headers: authHeaders(token)
  });
  return handleResponse(response, `Failed to fetch ${departmentCode} dashboard`);
}

// =============================================================================
// 1. RESERVATION DEPARTMENT APIS
// =============================================================================

export async function fetchStaffBookings(params: Record<string, any> = {}, token: string) {
  const query = new URLSearchParams(params).toString();
  const url = `${API_BASE_URL}/api/staff/bookings/${query ? `?${query}` : ''}`;
  const res = await fetch(url, { headers: authHeaders(token) });
  return handleResponse(res, 'Failed to fetch bookings list');
}

export async function fetchStaffBookingDetail(id: string | number, token: string) {
  const res = await fetch(`${API_BASE_URL}/api/staff/bookings/${id}/`, { headers: authHeaders(token) });
  return handleResponse(res, `Failed to fetch booking details for ${id}`);
}

export async function staffCheckInGuest(id: string | number, token: string) {
  const res = await fetch(`${API_BASE_URL}/api/staff/bookings/${id}/check-in/`, {
    method: 'POST',
    headers: authHeaders(token)
  });
  return handleResponse(res, 'Failed to process check-in');
}

export async function staffCheckOutGuest(id: string | number, token: string) {
  const res = await fetch(`${API_BASE_URL}/api/staff/bookings/${id}/check-out/`, {
    method: 'POST',
    headers: authHeaders(token)
  });
  return handleResponse(res, 'Failed to process check-out');
}

export async function fetchStaffRooms(params: Record<string, any> = {}, token: string) {
  const query = new URLSearchParams(params).toString();
  const res = await fetch(`${API_BASE_URL}/api/staff/rooms/${query ? `?${query}` : ''}`, { headers: authHeaders(token) });
  return handleResponse(res, 'Failed to fetch rooms list');
}

export async function fetchStaffGuests(params: Record<string, any> = {}, token: string) {
  const query = new URLSearchParams(params).toString();
  const res = await fetch(`${API_BASE_URL}/api/staff/guests/${query ? `?${query}` : ''}`, { headers: authHeaders(token) });
  return handleResponse(res, 'Failed to fetch guest directory');
}

// =============================================================================
// 2. CUSTOMER SUPPORT DEPARTMENT APIS
// =============================================================================

export async function fetchStaffSupportTickets(params: Record<string, any> = {}, token: string) {
  const query = new URLSearchParams(params).toString();
  const res = await fetch(`${API_BASE_URL}/api/staff/support/${query ? `?${query}` : ''}`, { headers: authHeaders(token) });
  return handleResponse(res, 'Failed to fetch support tickets');
}

export async function fetchStaffSupportTicketDetail(id: number | string, token: string) {
  const res = await fetch(`${API_BASE_URL}/api/staff/support/${id}/`, { headers: authHeaders(token) });
  return handleResponse(res, `Failed to fetch ticket ${id}`);
}

export async function updateStaffSupportTicket(id: number | string, payload: { status?: string; priority?: string }, token: string) {
  const res = await fetch(`${API_BASE_URL}/api/staff/support/${id}/update/`, {
    method: 'PATCH',
    headers: authHeaders(token),
    body: JSON.stringify(payload)
  });
  return handleResponse(res, 'Failed to update ticket');
}

export async function addStaffTicketNote(id: number | string, note: string, token: string) {
  const res = await fetch(`${API_BASE_URL}/api/staff/support/${id}/notes/`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify({ note })
  });
  return handleResponse(res, 'Failed to add internal note');
}

export async function sendStaffTicketMessage(id: number | string, message: string, token: string) {
  const res = await fetch(`${API_BASE_URL}/api/staff/support/${id}/messages/`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify({ message })
  });
  return handleResponse(res, 'Failed to send response message');
}

// =============================================================================
// 3. REFUNDS & CLAIMS DEPARTMENT APIS
// =============================================================================

export async function fetchStaffRefunds(params: Record<string, any> = {}, token: string) {
  const query = new URLSearchParams(params).toString();
  const res = await fetch(`${API_BASE_URL}/api/staff/refunds/${query ? `?${query}` : ''}`, { headers: authHeaders(token) });
  return handleResponse(res, 'Failed to fetch refund requests');
}

export async function fetchStaffRefundDetail(id: number | string, token: string) {
  const res = await fetch(`${API_BASE_URL}/api/staff/refunds/${id}/`, { headers: authHeaders(token) });
  return handleResponse(res, `Failed to fetch refund details for ${id}`);
}

export async function fetchStaffRefundEligibility(id: number | string, token: string) {
  const res = await fetch(`${API_BASE_URL}/api/staff/refunds/${id}/eligibility/`, { headers: authHeaders(token) });
  return handleResponse(res, 'Failed to check refund eligibility');
}

export async function processStaffRefund(id: number | string, payload: { notes?: string } = {}, token: string) {
  const res = await fetch(`${API_BASE_URL}/api/staff/refunds/${id}/process/`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify(payload)
  });
  return handleResponse(res, 'Failed to process refund');
}

export async function fetchStaffRefundHistory(token: string) {
  const res = await fetch(`${API_BASE_URL}/api/staff/refunds/history/`, { headers: authHeaders(token) });
  return handleResponse(res, 'Failed to fetch refund history');
}

// =============================================================================
// 4. PAYOUT & ESCROW DEPARTMENT APIS
// =============================================================================

export async function fetchStaffPayouts(params: Record<string, any> = {}, token: string) {
  const query = new URLSearchParams(params).toString();
  const res = await fetch(`${API_BASE_URL}/api/staff/payouts/${query ? `?${query}` : ''}`, { headers: authHeaders(token) });
  return handleResponse(res, 'Failed to fetch payout requests');
}

export async function fetchStaffPayoutDetail(id: number | string, token: string) {
  const res = await fetch(`${API_BASE_URL}/api/staff/payouts/${id}/`, { headers: authHeaders(token) });
  return handleResponse(res, `Failed to fetch payout details for ${id}`);
}

export async function processStaffPayout(id: number | string, payload: { override_hold?: boolean } = {}, token: string) {
  const res = await fetch(`${API_BASE_URL}/api/staff/payouts/${id}/process/`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify(payload)
  });
  return handleResponse(res, 'Failed to process payout');
}

export async function fetchStaffEscrow(token: string) {
  const res = await fetch(`${API_BASE_URL}/api/staff/payouts/escrow/`, { headers: authHeaders(token) });
  return handleResponse(res, 'Failed to fetch escrow ledger');
}

export async function fetchStaffSettlements(params: Record<string, any> = {}, token: string) {
  const query = new URLSearchParams(params).toString();
  const res = await fetch(`${API_BASE_URL}/api/staff/payouts/settlements/${query ? `?${query}` : ''}`, { headers: authHeaders(token) });
  return handleResponse(res, 'Failed to fetch settlements');
}

export async function fetchStaffPayoutHistory(token: string) {
  const res = await fetch(`${API_BASE_URL}/api/staff/payouts/history/`, { headers: authHeaders(token) });
  return handleResponse(res, 'Failed to fetch payout history');
}

// =============================================================================
// 5. HOTEL VERIFICATION DEPARTMENT APIS
// =============================================================================

export async function fetchStaffVerifications(params: Record<string, any> = {}, token: string) {
  const query = new URLSearchParams(params).toString();
  const res = await fetch(`${API_BASE_URL}/api/staff/verifications/${query ? `?${query}` : ''}`, { headers: authHeaders(token) });
  return handleResponse(res, 'Failed to fetch pending verifications');
}

export async function fetchStaffVerificationDetail(id: number | string, token: string) {
  const res = await fetch(`${API_BASE_URL}/api/staff/verifications/${id}/`, { headers: authHeaders(token) });
  return handleResponse(res, `Failed to fetch verification details for ${id}`);
}

export async function approveStaffHotel(id: number | string, token: string) {
  const res = await fetch(`${API_BASE_URL}/api/staff/verifications/${id}/approve/`, {
    method: 'POST',
    headers: authHeaders(token)
  });
  return handleResponse(res, 'Failed to approve hotel');
}

export async function rejectStaffHotel(id: number | string, reason: string, token: string) {
  const res = await fetch(`${API_BASE_URL}/api/staff/verifications/${id}/reject/`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify({ reason })
  });
  return handleResponse(res, 'Failed to reject hotel');
}

export async function fetchStaffVerificationHistory(token: string) {
  const res = await fetch(`${API_BASE_URL}/api/staff/verifications/history/`, { headers: authHeaders(token) });
  return handleResponse(res, 'Failed to fetch verification history');
}

export async function fetchStaffHotelDocuments(params: Record<string, any> = {}, token: string) {
  const query = new URLSearchParams(params).toString();
  const res = await fetch(`${API_BASE_URL}/api/staff/verifications/documents/${query ? `?${query}` : ''}`, { headers: authHeaders(token) });
  return handleResponse(res, 'Failed to fetch verification documents');
}

// =============================================================================
// 6. CLOUDINARY SIGNED DIRECT UPLOAD APIS
// =============================================================================

export interface CloudinarySignatureResponse {
  success: boolean;
  cloud_name: string;
  api_key: string;
  timestamp: number;
  folder: string;
  signature: string;
  upload_url: string;
  category: string;
  target_id?: number;
  max_file_size: number;
  allowed_formats: string[];
}

export interface CloudinaryUploadResult {
  public_id: string;
  version: number;
  width: number;
  height: number;
  format: string;
  resource_type: string;
  created_at: string;
  bytes: number;
  url: string;
  secure_url: string;
}

export async function fetchCloudinarySignature(
  category: 'hotels' | 'rooms' | 'profiles' | 'owners' | 'general',
  targetId?: number | string,
  token?: string
): Promise<CloudinarySignatureResponse> {
  const t = token || localStorage.getItem('access_token') || sessionStorage.getItem('access_token') || '';
  const res = await fetch(`${API_BASE_URL}/api/cloudinary/signature/`, {
    method: 'POST',
    headers: authHeaders(t),
    body: JSON.stringify({ category, target_id: targetId })
  });
  return handleResponse<CloudinarySignatureResponse>(res, 'Failed to obtain Cloudinary upload signature');
}

export async function uploadDirectToCloudinary(
  file: File,
  signData: CloudinarySignatureResponse,
  onProgress?: (percent: number) => void
): Promise<CloudinaryUploadResult> {
  if (file.size > signData.max_file_size) {
    throw new Error(`File size ${(file.size / (1024 * 1024)).toFixed(1)}MB exceeds allowed limit of ${(signData.max_file_size / (1024 * 1024))}MB.`);
  }

  const ext = file.name.split('.').pop()?.toLowerCase();
  if (ext && signData.allowed_formats && signData.allowed_formats.length > 0 && !signData.allowed_formats.includes(ext)) {
    throw new Error(`File format .${ext} is not supported. Allowed formats: ${signData.allowed_formats.join(', ')}.`);
  }

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', signData.upload_url);

    if (xhr.upload && onProgress) {
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          const percent = Math.round((event.loaded / event.total) * 100);
          onProgress(percent);
        }
      };
    }

    xhr.onload = () => {
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(data as CloudinaryUploadResult);
        } else {
          reject(new Error(data.error?.message || `Cloudinary upload failed with status ${xhr.status}`));
        }
      } catch (err) {
        reject(new Error(`Failed to parse Cloudinary response: ${xhr.statusText}`));
      }
    };

    xhr.onerror = () => {
      reject(new Error('Network error occurred during Cloudinary upload.'));
    };

    const formData = new FormData();
    formData.append('file', file);
    formData.append('api_key', signData.api_key);
    formData.append('timestamp', String(signData.timestamp));
    formData.append('signature', signData.signature);
    formData.append('folder', signData.folder);

    xhr.send(formData);
  });
}

export async function saveHotelCloudinaryImage(
  hotelId: number | string,
  imageUrl: string,
  isPrimary: boolean = false,
  caption: string = '',
  token?: string
) {
  const t = token || localStorage.getItem('access_token') || sessionStorage.getItem('access_token') || '';
  const res = await fetch(`${API_BASE_URL}/api/hotels/${hotelId}/upload-image/`, {
    method: 'POST',
    headers: authHeaders(t),
    body: JSON.stringify({ image_url: imageUrl, is_primary: isPrimary, caption })
  });
  return handleResponse(res, 'Failed to save hotel image reference');
}

export async function saveRoomCloudinaryImage(
  roomId: number | string,
  imageUrl: string,
  isPrimary: boolean = false,
  token?: string
) {
  const t = token || localStorage.getItem('access_token') || sessionStorage.getItem('access_token') || '';
  const res = await fetch(`${API_BASE_URL}/api/rooms/${roomId}/upload-image/`, {
    method: 'POST',
    headers: authHeaders(t),
    body: JSON.stringify({ image_url: imageUrl, is_primary: isPrimary })
  });
  return handleResponse(res, 'Failed to save room image reference');
}

export async function saveUserCloudinaryAvatar(
  avatarUrl: string,
  token?: string
) {
  const t = token || localStorage.getItem('access_token') || sessionStorage.getItem('access_token') || '';
  const res = await fetch(`${API_BASE_URL}/api/users/profile/`, {
    method: 'PATCH',
    headers: authHeaders(t),
    body: JSON.stringify({ avatar: avatarUrl, avatar_url: avatarUrl })
  });
  return handleResponse(res, 'Failed to update user profile picture');
}

// =============================================================================
// 7. SMART NOTIFICATIONS CLIENT APIS
// =============================================================================

export async function fetchNotifications(token?: string) {
  const t = token || localStorage.getItem('access_token') || sessionStorage.getItem('access_token') || '';
  const res = await fetch(`${API_BASE_URL}/api/notifications/`, {
    headers: authHeaders(t)
  });
  return handleResponse(res, 'Failed to fetch user notifications');
}

export async function fetchStaffNotifications(token?: string, unreadOnly: boolean = false) {
  const t = token || localStorage.getItem('access_token') || sessionStorage.getItem('access_token') || '';
  const query = unreadOnly ? '?unread_only=true' : '';
  const res = await fetch(`${API_BASE_URL}/api/staff/notifications/${query}`, {
    headers: authHeaders(t)
  });
  return handleResponse(res, 'Failed to fetch staff notifications');
}

export async function markNotificationRead(id: number | string, token?: string) {
  const t = token || localStorage.getItem('access_token') || sessionStorage.getItem('access_token') || '';
  const res = await fetch(`${API_BASE_URL}/api/notifications/${id}/read/`, {
    method: 'POST',
    headers: authHeaders(t)
  });
  return handleResponse(res, `Failed to mark notification ${id} as read`);
}

export async function markStaffNotificationRead(id: number | string, token?: string) {
  const t = token || localStorage.getItem('access_token') || sessionStorage.getItem('access_token') || '';
  const res = await fetch(`${API_BASE_URL}/api/staff/notifications/${id}/read/`, {
    method: 'PATCH',
    headers: authHeaders(t)
  });
  return handleResponse(res, `Failed to mark staff notification ${id} as read`);
}

export async function clickNotification(id: number | string, isStaff: boolean = false, token?: string) {
  const t = token || localStorage.getItem('access_token') || sessionStorage.getItem('access_token') || '';
  const endpoint = isStaff ? `/api/staff/notifications/${id}/click/` : `/api/notifications/${id}/click/`;
  const res = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: 'POST',
    headers: authHeaders(t)
  });
  return handleResponse(res, `Failed to process notification click for ${id}`);
}

export async function markAllNotificationsRead(isStaff: boolean = false, token?: string) {
  const t = token || localStorage.getItem('access_token') || sessionStorage.getItem('access_token') || '';
  const endpoint = isStaff ? `/api/staff/notifications/read-all/` : `/api/notifications/mark-all-read/`;
  const res = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: 'POST',
    headers: authHeaders(t)
  });
  return handleResponse(res, 'Failed to mark all notifications as read');
}

export async function fetchUnreadNotificationCount(token?: string) {
  const t = token || localStorage.getItem('access_token') || sessionStorage.getItem('access_token') || '';
  const res = await fetch(`${API_BASE_URL}/api/notifications/unread-count/`, {
    headers: authHeaders(t)
  });
  return handleResponse(res, 'Failed to fetch unread notification count');
}
