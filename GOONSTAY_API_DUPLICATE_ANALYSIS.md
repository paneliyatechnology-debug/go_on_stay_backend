# GOONSTAY — API DUPLICATE, OVERLAP & ALIAS ANALYSIS

> **Document Metadata**
> - Total Duplicate Route Pairs Identified: **25**
> - Primary Drivers: Dual URL Inclusions, Redundant Service Endpoints, Overlapping Portals
> - Audit Classification: All findings strictly verified against `config/urls.py` and active URL resolver.

---

## 1. Executive Summary

The GoOnStay backend URL configuration currently exhibits significant endpoint duplication. The most critical cause is that `config/urls.py` registers the same `users.urls` module under two distinct top-level URL prefixes:
```python
# config/urls.py (lines 20-21)
path('api/auth/', include('users.urls')),
path('api/users/', include('users.urls')),
```
Because every route in `users.urls` is included twice, **24 distinct API endpoints exist at two different URLs simultaneously** (e.g., `/api/auth/login/` and `/api/users/login/`).
Additionally, image signing is exposed on both `/api/cloudinary/signature/` and `/api/media/cloudinary/signature/`, and customer support ticketing is split across `/api/payments/support-tickets/` and `/api/staff/support/`.

---

## 2. Exhaustive Duplicate Endpoint Table

| Primary Route | Alias / Duplicate Route | View Class | Business Domain | Risk / Impact | Status |
|---|---|---|---|---|---|
| `/api/users/register/` | `/api/auth/register/` | `RegisterView` | Authentication / Users | Split registration analytics and CORS ambiguity | `VERIFIED DUPLICATE` |
| `/api/users/signup/` | `/api/auth/signup/` | `RegisterView` | Authentication / Users | Maintenance overhead; documentation drift | `VERIFIED DUPLICATE` |
| `/api/users/become-host/` | `/api/auth/become-host/` | `BecomeHostView` | Authentication / Users | Maintenance overhead; documentation drift | `VERIFIED DUPLICATE` |
| `/api/users/host/register/` | `/api/auth/host/register/` | `BecomeHostView` | Authentication / Users | Split registration analytics and CORS ambiguity | `VERIFIED DUPLICATE` |
| `/api/users/login/` | `/api/auth/login/` | `LoginView` | Authentication / Users | Divergent client tokens; duplicate auth attack surface | `VERIFIED DUPLICATE` |
| `/api/users/signin/` | `/api/auth/signin/` | `LoginView` | Authentication / Users | Maintenance overhead; documentation drift | `VERIFIED DUPLICATE` |
| `/api/users/host/login/` | `/api/auth/host/login/` | `HostLoginView` | Authentication / Users | Divergent client tokens; duplicate auth attack surface | `VERIFIED DUPLICATE` |
| `/api/users/host-login/` | `/api/auth/host-login/` | `HostLoginView` | Authentication / Users | Divergent client tokens; duplicate auth attack surface | `VERIFIED DUPLICATE` |
| `/api/users/logout/` | `/api/auth/logout/` | `LogoutView` | Authentication / Users | Maintenance overhead; documentation drift | `VERIFIED DUPLICATE` |
| `/api/users/token/refresh/` | `/api/auth/token/refresh/` | `TokenRefreshView` | Authentication / Users | Maintenance overhead; documentation drift | `VERIFIED DUPLICATE` |
| `/api/users/me/` | `/api/auth/me/` | `UserProfileView` | Authentication / Users | Maintenance overhead; documentation drift | `VERIFIED DUPLICATE` |
| `/api/users/profile/` | `/api/auth/profile/` | `UserProfileView` | Authentication / Users | Maintenance overhead; documentation drift | `VERIFIED DUPLICATE` |
| `/api/users/check-email/` | `/api/auth/check-email/` | `CheckEmailView` | Authentication / Users | Maintenance overhead; documentation drift | `VERIFIED DUPLICATE` |
| `/api/users/check-phone/` | `/api/auth/check-phone/` | `CheckPhoneView` | Authentication / Users | Maintenance overhead; documentation drift | `VERIFIED DUPLICATE` |
| `/api/users/send-otp/` | `/api/auth/send-otp/` | `SendOTPView` | Authentication / Users | SMS/Email OTP brute-force bypass via dual endpoints | `VERIFIED DUPLICATE` |
| `/api/users/verify-otp/` | `/api/auth/verify-otp/` | `VerifyOTPView` | Authentication / Users | SMS/Email OTP brute-force bypass via dual endpoints | `VERIFIED DUPLICATE` |
| `/api/users/change-password/` | `/api/auth/change-password/` | `ChangePasswordView` | Authentication / Users | Maintenance overhead; documentation drift | `VERIFIED DUPLICATE` |
| `/api/users/forgot-password/` | `/api/auth/forgot-password/` | `ForgotPasswordView` | Authentication / Users | Maintenance overhead; documentation drift | `VERIFIED DUPLICATE` |
| `/api/users/reset-password/` | `/api/auth/reset-password/` | `ResetPasswordView` | Authentication / Users | Maintenance overhead; documentation drift | `VERIFIED DUPLICATE` |
| `/api/users/all/` | `/api/auth/all/` | `UserListView` | Authentication / Users | Maintenance overhead; documentation drift | `VERIFIED DUPLICATE` |
| `/api/users/<int:pk>/toggle-block/` | `/api/auth/<int:pk>/toggle-block/` | `UserBlockToggleView` | Authentication / Users | Maintenance overhead; documentation drift | `VERIFIED DUPLICATE` |
| `/api/users/<int:pk>/block-toggle/` | `/api/auth/<int:pk>/block-toggle/` | `UserBlockToggleView` | Authentication / Users | Maintenance overhead; documentation drift | `VERIFIED DUPLICATE` |
| `/api/users/<int:pk>/change-role/` | `/api/auth/<int:pk>/change-role/` | `UserRoleChangeView` | Authentication / Users | Maintenance overhead; documentation drift | `VERIFIED DUPLICATE` |
| `/api/users/<int:pk>/delete/` | `/api/auth/<int:pk>/delete/` | `UserDeleteView` | Authentication / Users | Maintenance overhead; documentation drift | `VERIFIED DUPLICATE` |
| `/api/cloudinary/signature/` | `/api/media/cloudinary/signature/` | `CloudinarySignatureView` | Authentication / Users | Confusing media upload conventions for frontends | `VERIFIED DUPLICATE` |

---

## 3. Structural Domain Overlaps

### 3.1 Dual Support Ticket Systems
- **Route Set A (`payments.urls`)**: `/api/payments/support-tickets/` (CustomerSupportTicketViewSet). Handles guest ticket creation, messaging, resolution.
- **Route Set B (`staff.urls`)**: `/api/staff/support/` (StaffSupportTicketListView, StaffSupportTicketDetailView, StaffSupportTicketUpdateView, StaffSupportTicketNotesView, StaffSupportTicketMessageView). Handles staff operational ticket resolution and internal notes.
- **Audit Finding**: Both systems operate on the exact same underlying model (`SupportTicket` / `CustomerSupportTicket`), but expose completely different serializer representations, pagination, and filter parameters.
- **Frontend Impact**: Frontend `AdminDashboard.jsx` and `SupportTicketsManagement.jsx` currently consume `/api/payments/support-tickets/` directly, bypassing the dedicated `/api/staff/support/` portal endpoints.

### 3.2 Dual Login & Authentication Gates
- **Customer/Platform Login**: `/api/users/login/` and `/api/auth/login/` (handled by `users.views.LoginView`).
- **Staff Hierarchy Login**: `/api/staff/login/` (handled by `staff.views.StaffLoginView`).
- **Audit Finding**: Platform Administrators (Role `ADMIN`) can log in through both endpoints, but only `/api/staff/login/` enforces mandatory TOTP MFA challenges for Level 2, 3, and 4 accounts. If an Admin logs in through `/api/users/login/`, MFA is completely bypassed!
- **Security Classification**: `[VERIFIED CRITICAL]` — MFA bypass risk.

### 3.3 Redundant Cloudinary Signature Endpoints
- `/api/cloudinary/signature/` (View: `CloudinarySignatureView`)
- `/api/media/cloudinary/signature/` (View: `CloudinarySignatureView`)
- **Audit Finding**: Both routes point to the identical view class in `core.cloudinary_views`. One is completely redundant.

---

## 4. Remediation & Deprecation Roadmap

1. **Deprecate `/api/auth/` Alias**: Keep `/api/users/` as the single canonical path, or introduce unified `/api/v1/auth/`.
2. **Unify Support Ticket Endpoints**: Consolidate `/api/payments/support-tickets/` into `/api/support/` with clear role-based serializer outputs.
3. **Remove Redundant Cloudinary Route**: Standardize on `/api/cloudinary/signature/`.
4. **Enforce Unified Login Gate**: Integrate TOTP MFA check into `users.views.LoginView` for any user with `role in ['ADMIN', 'MAIN_MANAGER', 'DEPARTMENT_STAFF_MANAGER']`.
