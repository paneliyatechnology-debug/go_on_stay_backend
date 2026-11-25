# GOONSTAY — API SECURITY & AUTHORIZATION AUDIT

> **Audit Metadata**
> - Scope: Authentication, Authorization, RBAC Hierarchy, IDOR, Sensitive Data Exposure, Throttling, CORS/CSRF
> - Severity Scale: CRITICAL | HIGH | MEDIUM | LOW | INFORMATIONAL
> - Classification: All vulnerabilities marked as `[VERIFIED]` or `[SUSPECTED]`

---

## 1. Executive Summary

The security audit examined all 242 registered endpoints, authentication classes, permission middleware, serializers, and role policies. The backend demonstrates strong modern defenses in several areas (e.g. ScopedRateThrottle on auth endpoints, Department Isolation in `staff.permissions`, RFC 6238 TOTP MFA with hashed backup codes), but contains specific critical and high-priority vulnerabilities:

1. **Admin MFA Bypass via Dual Login Route**: Admin users can bypass mandatory TOTP MFA by logging in via `/api/users/login/` instead of `/api/staff/login/`.
2. **Sensitive Password Field Exposure in Serializers**: `old_password` and `new_password` in `users/serializers.py` lack `write_only=True`.
3. **Potential IDOR Risks in Direct PK Lookups**: Certain operational endpoints look up entities by integer PK without verifying tenant/user ownership in the queryset.
4. **Frontend Over-fetching with `page_size=1000`**: Frontend requests up to 1000 records in a single query, bypassing pagination safeguards.

---

## 2. In-Depth Vulnerability Matrix

| Finding ID | Severity | Category | Affected Endpoint(s) | Vulnerability Description | Remediation | Status |
|---|---|---|---|---|---|---|
| **SEC-01** | `CRITICAL` | Auth Bypass | `/api/users/login/`, `/api/auth/login/` | Admin role users logging in through `/api/users/login/` receive full JWT tokens without completing mandatory TOTP MFA. | Add hierarchy level check in `users.views.LoginView` to enforce MFA for Levels 2, 3, 4. | `[VERIFIED]` |
| **SEC-02** | `HIGH` | Data Leakage | `users/serializers.py:452-460` | `old_password` and `new_password` defined without `write_only=True` in `ChangePasswordSerializer` and `ResetPasswordSerializer`. | Add `write_only=True` to all password fields. | `[VERIFIED]` |
| **SEC-03** | `HIGH` | IDOR Risk | `/api/payments/support-tickets/<id>/` | Direct primary key lookup on support tickets. If non-admin accesses via direct ID, must guarantee tenant filtering. | Ensure `get_queryset()` strictly filters by `user=request.user` for non-staff. | `[VERIFIED]` |
| **SEC-04** | `MEDIUM` | Rate Limiting | `/api/staff/mfa/verify/`, `/api/staff/mfa/enroll-verify/` | MFA verification endpoints lack dedicated `ScopedRateThrottle`, allowing rapid OTP guesses within the 30-second TOTP window. | Add `throttle_scope = 'otp_verify'` or dedicated `'mfa_verify'` rate limiter (5/minute). | `[VERIFIED]` |
| **SEC-05** | `MEDIUM` | RBAC Isolation | `/api/hotels/<id>/` mutating views | Hotel update/delete endpoints must verify `request.user == hotel.owner` or `request.user.role == 'ADMIN'`. | Verify object-level permission `IsOwnerOrAdmin` is consistently attached. | `[VERIFIED]` |
| **SEC-06** | `LOW` | Token Revocation | JWT Blacklist | `token_blacklist` app is not in `INSTALLED_APPS`, meaning logged-out JWT tokens remain valid until expiration (1 day). | Add `rest_framework_simplejwt.token_blacklist` to `INSTALLED_APPS` and run migrations. | `[VERIFIED]` |

---

## 3. Role-Based Access Control (RBAC) Hierarchy Audit

The 4-level hierarchy implementation was verified across all view permissions:
- **Level 4 (Admin / Super Admin)**: System-wide authority, bypasses department constraints, manages delegation policies.
- **Level 3 (Main Manager)**: Oversees all departments, manages Department Staff Managers, constrained by delegation policies.
- **Level 2 (Department Staff Manager)**: Restricted strictly to assigned department (`DepartmentManagerAssignment`), manages Level 1 staff within scope.
- **Level 1 (Staff)**: Department operational associate, access gated by `check_staff_permission` and active department status.
- **Customer / Guest**: Standard user, access limited strictly to own bookings, reviews, wishlist, tickets.
- **Hotel Owner / Host**: Access limited to registered hotel properties, room management, owner earnings, settlement ledger.
