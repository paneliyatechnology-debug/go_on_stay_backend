import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';

// Guards
import { PortalRouteGuard } from '../guards/PortalRouteGuard';

// Layouts
import { AdminLayout } from '../layouts/AdminLayout';
import { StaffPortalLayout } from '../layouts/StaffPortalLayout';
import { CustomerLayout } from '../layouts/CustomerLayout';
import { HotelOwnerLayout } from '../layouts/HotelOwnerLayout';

// Dashboards
import { AdminDashboard } from '../dashboards/AdminDashboard';
import { ReservationDashboard } from '../dashboards/ReservationDashboard';
import { CustomerSupportDashboard } from '../dashboards/CustomerSupportDashboard';
import { RefundsClaimsDashboard } from '../dashboards/RefundsClaimsDashboard';
import { PayoutEscrowDashboard } from '../dashboards/PayoutEscrowDashboard';
import { HotelVerificationDashboard } from '../dashboards/HotelVerificationDashboard';

// Reservation Functional Pages
import {
  ReservationBookingsPage,
  ReservationBookingDetailPage,
  ReservationGuestsPage,
  ReservationRoomsPage,
  ReservationOperationsPage,
  ReservationActivityPage
} from '../pages/reservation/ReservationPages';

// Customer Support Functional Pages
import {
  SupportTicketsPage,
  SupportComplaintsPage,
  SupportTicketDetailPage,
  SupportHistoryPage,
  SupportNotesPage,
  SupportActionsPage
} from '../pages/support/SupportPages';

// Refunds & Claims Functional Pages
import {
  RefundRequestsPage,
  RefundClaimsPage,
  RefundDetailPage,
  RefundEligibilityPage,
  RefundProcessPage,
  RefundHistoryPage
} from '../pages/refunds/RefundsPages';

// Payout & Escrow Functional Pages
import {
  PayoutRequestsPage,
  PayoutEscrowPage,
  PayoutDetailPage,
  PayoutSettlementsPage,
  PayoutProcessPage,
  PayoutHistoryPage
} from '../pages/payouts/PayoutsPages';

// Hotel Verification Functional Pages
import {
  VerificationPendingPage,
  VerificationDocumentsPage,
  VerificationDetailPage,
  VerificationReviewPage,
  VerificationActionsPage,
  VerificationHistoryPage
} from '../pages/verification/VerificationPages';

export const PortalRoutes: React.FC = () => {
  return (
    <Routes>
      {/* 1. ADMIN PORTAL (Strictly Isolated System Oversight) */}
      <Route
        path="/admin"
        element={
          <PortalRouteGuard requiredPortalId="ADMIN_PORTAL" requiredRole="ADMIN">
            <AdminLayout />
          </PortalRouteGuard>
        }
      >
        <Route index element={<Navigate to="/admin/dashboard" replace />} />
        <Route path="dashboard" element={<AdminDashboard />} />
        {/* Sub-routes for admin platform oversight */}
        <Route path="staff" element={<div className="p-6 text-white font-semibold">Staff Management Oversight</div>} />
        <Route path="staff/create" element={<div className="p-6 text-white font-semibold">Create Staff Account</div>} />
        <Route path="departments" element={<div className="p-6 text-white font-semibold">Department Assignment</div>} />
        <Route path="permissions" element={<div className="p-6 text-white font-semibold">Staff Permissions Management</div>} />
        <Route path="customers" element={<div className="p-6 text-white font-semibold">Customer Management</div>} />
        <Route path="hotel-owners" element={<div className="p-6 text-white font-semibold">Hotel Owner Management</div>} />
        <Route path="hotels" element={<div className="p-6 text-white font-semibold">Hotel Management</div>} />
        <Route path="bookings" element={<div className="p-6 text-white font-semibold">Booking Oversight</div>} />
        <Route path="payments" element={<div className="p-6 text-white font-semibold">Payment Management</div>} />
        <Route path="refunds" element={<div className="p-6 text-white font-semibold">Refund Oversight</div>} />
        <Route path="payouts" element={<div className="p-6 text-white font-semibold">Payout & Escrow Oversight</div>} />
        <Route path="verifications" element={<div className="p-6 text-white font-semibold">Hotel Verification Oversight</div>} />
        <Route path="support" element={<div className="p-6 text-white font-semibold">Support Oversight</div>} />
        <Route path="analytics" element={<div className="p-6 text-white font-semibold">Reports and Analytics</div>} />
        <Route path="settings" element={<div className="p-6 text-white font-semibold">System Settings</div>} />
        <Route path="audit-logs" element={<div className="p-6 text-white font-semibold">Activity Logs</div>} />
        <Route path="deleted-hotels" element={<div className="p-6 text-white font-semibold">Deleted Hotels Archive</div>} />
      </Route>

      {/* 2. RESERVATION STAFF PORTAL */}
      <Route
        path="/staff/reservation"
        element={
          <PortalRouteGuard requiredPortalId="RESERVATION_PORTAL" requiredDepartment="RESERVATION">
            <StaffPortalLayout department="RESERVATION" />
          </PortalRouteGuard>
        }
      >
        <Route index element={<ReservationDashboard />} />
        <Route path="bookings" element={<ReservationBookingsPage />} />
        <Route path="bookings/:id" element={<ReservationBookingDetailPage />} />
        <Route path="guests" element={<ReservationGuestsPage />} />
        <Route path="rooms" element={<ReservationRoomsPage />} />
        <Route path="operations" element={<ReservationOperationsPage />} />
        <Route path="activity" element={<ReservationActivityPage />} />
      </Route>

      {/* 3. CUSTOMER SUPPORT STAFF PORTAL */}
      <Route
        path="/staff/support"
        element={
          <PortalRouteGuard requiredPortalId="CUSTOMER_SUPPORT_PORTAL" requiredDepartment="CUSTOMER_SUPPORT">
            <StaffPortalLayout department="CUSTOMER_SUPPORT" />
          </PortalRouteGuard>
        }
      >
        <Route index element={<CustomerSupportDashboard />} />
        <Route path="tickets" element={<SupportTicketsPage />} />
        <Route path="tickets/:id" element={<SupportTicketDetailPage />} />
        <Route path="complaints" element={<SupportComplaintsPage />} />
        <Route path="history" element={<SupportHistoryPage />} />
        <Route path="notes" element={<SupportNotesPage />} />
        <Route path="actions" element={<SupportActionsPage />} />
      </Route>

      {/* 4. REFUNDS & CLAIMS STAFF PORTAL */}
      <Route
        path="/staff/refunds"
        element={
          <PortalRouteGuard requiredPortalId="REFUNDS_AND_CLAIMS_PORTAL" requiredDepartment="REFUNDS_AND_CLAIMS">
            <StaffPortalLayout department="REFUNDS_AND_CLAIMS" />
          </PortalRouteGuard>
        }
      >
        <Route index element={<RefundsClaimsDashboard />} />
        <Route path="requests" element={<RefundRequestsPage />} />
        <Route path="claims" element={<RefundClaimsPage />} />
        <Route path="eligibility" element={<RefundEligibilityPage />} />
        <Route path="process" element={<RefundProcessPage />} />
        <Route path="history" element={<RefundHistoryPage />} />
        <Route path=":id" element={<RefundDetailPage />} />
      </Route>

      {/* 5. PAYOUT & ESCROW STAFF PORTAL */}
      <Route
        path="/staff/payouts"
        element={
          <PortalRouteGuard requiredPortalId="PAYOUT_AND_ESCROW_PORTAL" requiredDepartment="PAYOUT_AND_ESCROW">
            <StaffPortalLayout department="PAYOUT_AND_ESCROW" />
          </PortalRouteGuard>
        }
      >
        <Route index element={<PayoutEscrowDashboard />} />
        <Route path="requests" element={<PayoutRequestsPage />} />
        <Route path="escrow" element={<PayoutEscrowPage />} />
        <Route path="settlements" element={<PayoutSettlementsPage />} />
        <Route path="process" element={<PayoutProcessPage />} />
        <Route path="history" element={<PayoutHistoryPage />} />
        <Route path=":id" element={<PayoutDetailPage />} />
      </Route>

      {/* 6. HOTEL VERIFICATION STAFF PORTAL */}
      <Route
        path="/staff/verification"
        element={
          <PortalRouteGuard requiredPortalId="HOTEL_VERIFICATION_PORTAL" requiredDepartment="HOTEL_VERIFICATION">
            <StaffPortalLayout department="HOTEL_VERIFICATION" />
          </PortalRouteGuard>
        }
      >
        <Route index element={<HotelVerificationDashboard />} />
        <Route path="pending" element={<VerificationPendingPage />} />
        <Route path="documents" element={<VerificationDocumentsPage />} />
        <Route path="review" element={<VerificationReviewPage />} />
        <Route path="actions" element={<VerificationActionsPage />} />
        <Route path="history" element={<VerificationHistoryPage />} />
        <Route path=":id" element={<VerificationDetailPage />} />
      </Route>

      {/* 7. CUSTOMER PORTAL */}
      <Route
        path="/customer"
        element={
          <PortalRouteGuard requiredPortalId="CUSTOMER_PORTAL" requiredRole="CUSTOMER">
            <CustomerLayout />
          </PortalRouteGuard>
        }
      >
        <Route index element={<Navigate to="/customer/dashboard" replace />} />
        <Route path="dashboard" element={<div className="p-6 text-slate-800 font-semibold">Customer Home & Recommendations</div>} />
        <Route path="bookings" element={<div className="p-6 text-slate-800 font-semibold">My Bookings</div>} />
        <Route path="wishlist" element={<div className="p-6 text-slate-800 font-semibold">Saved Wishlist</div>} />
        <Route path="support" element={<div className="p-6 text-slate-800 font-semibold">Help & Support Tickets</div>} />
        <Route path="profile" element={<div className="p-6 text-slate-800 font-semibold">My Profile & Account</div>} />
      </Route>

      {/* 8. HOTEL OWNER PORTAL */}
      <Route
        path="/host"
        element={
          <PortalRouteGuard requiredPortalId="HOTEL_OWNER_PORTAL" requiredRole="HOTEL_OWNER">
            <HotelOwnerLayout />
          </PortalRouteGuard>
        }
      >
        <Route index element={<Navigate to="/host/dashboard" replace />} />
        <Route path="dashboard" element={<div className="p-6 text-slate-800 font-semibold">Host Overview & Metrics</div>} />
        <Route path="hotels" element={<div className="p-6 text-slate-800 font-semibold">My Properties</div>} />
        <Route path="rooms" element={<div className="p-6 text-slate-800 font-semibold">Room Categories & Rates</div>} />
        <Route path="calendar" element={<div className="p-6 text-slate-800 font-semibold">Availability Calendar</div>} />
        <Route path="bookings" element={<div className="p-6 text-slate-800 font-semibold">Guest Bookings</div>} />
        <Route path="settlements" element={<div className="p-6 text-slate-800 font-semibold">Earnings & Settlement Statements</div>} />
        <Route path="payout-account" element={<div className="p-6 text-slate-800 font-semibold">Bank Account Setup</div>} />
        <Route path="reviews" element={<div className="p-6 text-slate-800 font-semibold">Guest Reviews</div>} />
      </Route>
    </Routes>
  );
};
