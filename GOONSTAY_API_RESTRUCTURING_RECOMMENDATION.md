# GOONSTAY — API RESTRUCTURING & TARGET ARCHITECTURE RECOMMENDATION

> **Architecture Blueprint**
> - Target Standard: RESTful Clean Architecture, Single-Gate Auth, Strict Versioning (`/api/v1/...`)
> - Standard Envelope: Uniform JSON envelope across 100% of API endpoints
> - Migration Rule: Zero-Downtime, Backward Compatibility, Rule Zero Database Preservation

---

## 1. Executive Summary
The existing GoOnStay API ecosystem contains 242 endpoints spread across 11 applications with considerable duplication (24 endpoints duplicated across `/api/auth/` and `/api/users/`). To establish a modern, scalable, and secure backend, this document outlines the target restructuring architecture.

---

## 2. Standardized JSON Response Envelope

Currently, some endpoints return flat objects (`{ id: 1, email: ... }`), others return `{ success: true, data: ... }`, and paginated endpoints return `{ count: 10, next: ..., results: [...] }`. All endpoints must be standardized under a predictable envelope:

```json
{
  "success": true,
  "code": "OK",
  "message": "Resource retrieved successfully.",
  "data": { ... },
  "error": null,
  "meta": {
    "timestamp": "2026-11-25T16:20:00Z",
    "correlation_id": "req-98f2b31a",
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total_count": 142,
      "total_pages": 8
    }
  }
}
```

---

## 3. Recommended Clean URL Taxonomy

| Current Fragmented Routes | Target Unified Route | Business Domain | Primary Consumer |
|---|---|---|---|
| `/api/auth/login/`, `/api/users/login/`, `/api/staff/login/` | `/api/v1/auth/login/` | Authentication | All Users (MFA Auto-Challenged for Levels 2-4) |
| `/api/auth/token/refresh/`, `/api/users/token/refresh/` | `/api/v1/auth/token/refresh/` | Authentication | All Clients |
| `/api/users/*` (Customer profiles) | `/api/v1/customers/profile/` | Customer | Guest Portal |
| `/api/hotels/*`, `/api/locations/*` | `/api/v1/inventory/hotels/` | Hotels / Search | Public Guest & Owner |
| `/api/rooms/*` | `/api/v1/inventory/rooms/` | Rooms | Public Guest & Owner |
| `/api/bookings/*` | `/api/v1/commerce/bookings/` | Bookings | Public Guest & Host |
| `/api/payments/*` | `/api/v1/commerce/payments/` | Payments | Payment Gateway |
| `/api/payments/support-tickets/`, `/api/staff/support/` | `/api/v1/support/tickets/` | Support | Customer & Staff |
| `/api/staff/admin/*`, `/api/staff/main-manager/*`, `/api/staff/dept-manager/*` | `/api/v1/hierarchy/*` | 4-Level Hierarchy | Admin, Main Manager, Dept Manager |

---

## 4. Phased Zero-Downtime Migration Plan

1. **Phase 1 (Preparation & Non-Breaking Aliases)**: Introduce `/api/v1/` routing alongside existing legacy routes. No legacy routes are removed or renamed.
2. **Phase 2 (Frontend Service Update)**: Update frontend `adminStaffService.js` and public client services to use `/api/v1/` endpoints.
3. **Phase 3 (Deprecation Logging)**: Log usage of legacy `/api/auth/` and `/api/users/` routes with a deprecation HTTP header (`Deprecation: true`).
4. **Phase 4 (Legacy Sunset)**: Safely remove duplicate legacy URL patterns after frontend transition is verified.
