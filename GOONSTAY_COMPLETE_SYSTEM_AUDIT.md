# GOONSTAY – COMPLETE SYSTEM ARCHITECTURE AUDIT, SECURITY ANALYSIS, UX EVALUATION, COMPETITOR BENCHMARKING & FUTURE ROADMAP

**Document Version:** 1.0.0-PROD-AUDIT  
**Audit Date:** November 05, 2026  
**Target Platform:** GOONSTAY (formerly BookMyRoom / BMR)  
**Workspace Path:** `D:\BookMyRoomBackend\BookMyRoomBackend`  
**Lead Audit Panel:**
- Senior Django Backend Architect
- Full-Stack Software Architect
- Lead Cybersecurity Auditor (CISSP / OSCP)
- Principal Database Architect
- API Security Specialist
- Payment & Financial Systems Architect (PCI-DSS & FinTech Specialist)
- Senior QA & Automation Testing Lead
- Principal UI/UX Researcher
- Hotel Booking Industry Product Director
- Online Travel Agency (OTA) Market Analyst

---

## EXECUTIVE COMPLIANCE CONFIRMATION (RULE ZERO)

> **STRICT COMPLIANCE DIRECTIVE CONFIRMATION:**  
> In adherence to Absolute Rule Zero, **ZERO MODIFICATIONS** have been executed upon the existing codebase, database, serializers, views, models, migrations, configurations, environment files, or third-party service credentials. This document represents a strictly non-destructive, read-only architectural inspection, static code security audit, heuristic UX evaluation, competitive market benchmark, and strategic engineering roadmap.

---

# SECTION A: EXECUTIVE SUMMARY

### 1. Project Background & Vision
GOONSTAY is an end-to-end digital hospitality and hotel booking marketplace engineered to serve three distinct customer segments:
1. **Guests (B2C Consumers):** Discovering, comparing, wishlisting, booking, upgrading meal plans, applying promo discounts, and completing secure prepaid reservations for hotels, villas, homestays, and resorts across India.
2. **Hotel Owners / Hosts (B2B Partners):** Listing multi-category hospitality properties, managing inventory, configuring room prices (base, weekend, seasonal, calendar blocks), tracking guest check-ins/check-outs, viewing earnings, and receiving bank payouts.
3. **Platform Administrators (Internal Operations):** Overseeing KYC verification, approving/suspending listings, managing promotional campaigns, monitoring payment ledgers, reconciling escrow holding periods, and handling guest-host disputes.

### 2. High-Level System Assessment
- **Architecture Maturity:** The project has made significant strides in transitioning from a basic CRUD prototype to an enterprise-style monolithic REST API built on **Django 6.1.1** and **Django REST Framework (DRF) 3.18.1**. The separation of domain concerns into discrete Django apps (`users`, `hotels`, `rooms`, `bookings`, `payments`, `coupons`, `reviews`, `wishlist`, `notifications`, `core`, `util`) demonstrates solid architectural forethought.
- **Key Strengths:**
  - Robust centralized exception handling conforming to RFC 7807 (`core/exceptions.py`).
  - Immutable financial snapshot persistence (`price_snapshot` and `cancellation_breakdown` JSON fields on `Booking`).
  - Strict server-side recalculation of room tariffs, meal plan surcharges, taxes (18% GST), and promotional discounts during payment order creation to prevent frontend tampering.
  - Automated checkout cleanup routines for past reservations.
  - Comprehensive 7-day holding period ledger architecture for hotel owner payout settlement.
- **Primary Operational Vulnerabilities:**
  - **Critical Auth Leakage (P0):** Plaintext OTP disclosure in HTTP response payloads when `DEBUG=True` or SMTP delivery fails (`users/views.py`).
  - **Insecure Randomness (P0):** Cryptographically insecure pseudo-random OTP generation (`util/otp.py` utilizing Python's `random` module instead of `secrets`).
  - **Broken Object-Level Authorization (P0):** Missing ownership verification on review deletion (`reviews/views.py`).
  - **Multi-Tenant Privilege Escalation (P0):** Hotel staff from one hotel can check in/out guests belonging to completely unrelated properties (`bookings/views.py`).
  - **Concurrency & Database Locking (P1):** Reliance on SQLite in development/staging where `select_for_update()` is a no-op, exposing the platform to race conditions and double-bookings.
  - **Unheld Inventory During Payment Checkout (P1):** Pending payment reservations do not hold room inventory, enabling simultaneous successful payments for the last available room.

---

# SECTION B: COMPLETE PROJECT ARCHITECTURE

```
+---------------------------------------------------------------------------------------+
|                                    CLIENT LAYER                                       |
|  +---------------------------+   +---------------------------+   +-----------------+  |
|  |  Guest Web Application    |   |  Host Partner Dashboard   |   | Platform Admin  |  |
|  |  (React/Vite/Tailwind UI) |   |  (React Property Portal)  |   | (Django Admin)  |  |
+---------------------------------------------------------------------------------------+
                                           | HTTP / HTTPS (JSON REST APIs)
                                           v
+---------------------------------------------------------------------------------------+
|                                  SECURITY & GATEWAY                                   |
|  - CORS Middleware (Origin Validation)                                                |
|  - Django Security Middleware (XSS, Content-Type, Clickjacking)                       |
|  - SimpleJWT Authentication (Bearer Tokens)                                           |
|  - DRF Throttling (Anon: 100/min, User: 1000/min, Auth: 5/min)                         |
|  - RFC 7807 Standardized Custom Exception Handler                                     |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
|                                DJANGO MONOLITHIC BACKEND                              |
|  +--------------------+  +--------------------+  +--------------------+               |
|  |       users        |  |       hotels       |  |       rooms        |               |
|  | User, EmailOTP,    |  | Hotel, Amenity,    |  | Room, RoomImage,   |               |
|  | RBAC, Profiles     |  | Verification Docs  |  | RoomCalendarBlock  |               |
|  +--------------------+  +--------------------+  +--------------------+               |
|  +--------------------+  +--------------------+  +--------------------+               |
|  |      bookings      |  |      payments      |  |      coupons       |               |
|  | Booking, Status,   |  | Payment, Refund,   |  | Coupon, Usage,     |               |
|  | Cancellation Engine|  | Webhook, Payout    |  | Campaign Rules     |               |
|  +--------------------+  +--------------------+  +--------------------+               |
|  +--------------------+  +--------------------+  +--------------------+               |
|  |      reviews       |  |      wishlist      |  |   notifications    |               |
|  | Rating, Feedback,  |  | Guest Favorites    |  | In-app Alerts,     |               |
|  | Verified Stays     |  | Persistence        |  | Event Triggers     |               |
|  +--------------------+  +--------------------+  +--------------------+               |
+---------------------------------------------------------------------------------------+
                                           |
                    +----------------------+----------------------+
                    |                                             |
                    v                                             v
+---------------------------------------+     +-----------------------------------------+
|            PERSISTENCE LAYER          |     |           EXTERNAL INTEGRATIONS         |
| - SQLite (db.sqlite3) [Current Local] |     | - Razorpay Standard Checkout (PG)       |
| - PostgreSQL [Target Production]      |     | - RazorpayX Payouts & Transfers         |
| - Media Storage (Local /media/)       |     | - Google Gmail SMTP (Transactional Mail)|
+---------------------------------------+     +-----------------------------------------+
```

### Communication & Data Flow Trace: End-to-End Reservation
1. **Search & Inventory Discovery:**
   - Guest queries `/api/rooms/hotel/<hotel_id>/?check_in=2026-11-10&check_out=2026-11-12`.
   - `RoomsByHotelView` invokes `get_available_room_count()` and `get_room_numbers_availability()`.
   - The system inspects existing bookings where `check_in < requested_check_out AND check_out > requested_check_in` excluding completed/cancelled states.
2. **Reservation Draft Creation:**
   - Guest posts to `/api/bookings/`.
   - `BookingListCreateView` validates dates, guest limits, room capacity, calculates pricing tiers (nights $\times$ base tariff + meal plans + 18% GST - discount), and writes a `Booking` record in `PENDING_PAYMENT` status with a 15-minute expiration timestamp and immutable `price_snapshot`.
3. **Payment Order Initiation:**
   - Guest posts to `/api/payments/orders/create/`.
   - `CreateOrderView` performs server-side price re-verification, generates a Razorpay Order (`order_xxxx`), stores a `Payment` record in `CREATED` status, and returns the order ID to the client.
4. **Payment Processing & Verification:**
   - Guest completes Razorpay checkout modal. Client posts signature to `/api/payments/verify/` (or Razorpay triggers `/api/payments/webhook/`).
   - Signature is validated using HMAC-SHA256 (`RAZORPAY_KEY_SECRET`).
   - Status updates: `Payment` $\rightarrow$ `CAPTURED`, `Booking` $\rightarrow$ `CONFIRMED` and `PAID`.
   - Post-payment allocation: `allocate_room_number_for_booking()` assigns a concrete physical room number (e.g., "101") and persists it to the booking.
   - Financial ledger entries: A `HostEarning` record is initialized with an eligible settlement date equal to `check_out + 7 days`.
   - Notifications: Guest and Hotel Owner receive instant in-app alerts and confirmation emails.

---

# SECTION C: BACKEND MODULE ANALYSIS

| Django Application | Core Models | Primary Purpose & Responsibilities | Critical Internal & Cross-App Dependencies |
| :--- | :--- | :--- | :--- |
| **`users`** | `User`, `EmailOTP` | Custom user model supporting 4 primary roles (`CUSTOMER`, `HOTEL_OWNER`, `HOTEL_STAFF`, `ADMIN`), registration, email OTP verification, password recovery, profile management. | Relies on `util.otp` for codes, `util.validators` for sanitization; references all apps via foreign keys. |
| **`hotels`** | `Hotel`, `Amenity`, `HotelImage`, `HotelVerificationDocument` | Property listings, geo-coordinates, amenities, dynamic policies (cancellation, rules, children, pets), admin approval lifecycle, owner dashboard metrics. | Dependent on `users.User` for owner; referenced by `rooms.Room`, `bookings.Booking`, `reviews.Review`. |
| **`rooms`** | `Room`, `RoomImage`, `RoomCalendarBlock` | Room category definitions, room numbers list, seasonal/weekend/custom pricing overrides, calendar blackouts, unit-level availability queries. | Foreign key to `hotels.Hotel`; referenced by `bookings.Booking`. |
| **`bookings`** | `Booking` | Central transaction state machine, stay dates, guest counts, room allocation, cancellation policy engine, invoice generation, staff check-in/out. | Deep coupling with `rooms.Room`, `hotels.Hotel`, `users.User`, `payments.Payment`, `coupons.Coupon`. |
| **`payments`** | `Payment`, `Refund`, `WebhookEvent`, `HostPayoutAccount`, `HostEarning`, `HostPayout`, `PlatformSetting`, `SupportTicket`, `AuditLog` | Razorpay order generation, HMAC signature verification, webhook deduplication, multi-mode customer refunds (Original, NEFT, UPI), host escrow holding ledger, admin audit logging. | Strongly coupled with `bookings.Booking`, `users.User`, and Razorpay external APIs. |
| **`coupons`** | `Coupon`, `CouponUsage` | Campaign management (General, Seasonal, Festive, First-Booking), multi-tier eligibility validation, per-user redemption caps, global budget limits. | Checked during booking creation and order checkout; foreign keys to `users.User` and `bookings.Booking`. |
| **`reviews`** | `Review` | 1-to-5 star ratings, textual feedback, owner responses, verified-stay enforcement, automatic recalculation of hotel aggregate rating. | Foreign keys to `hotels.Hotel`, `users.User`, `bookings.Booking`. |
| **`wishlist`** | `Wishlist` | Guest favorites bookmarking, toggling, and retrieval. | Links `users.User` and `hotels.Hotel` with unique composite constraint. |
| **`notifications`** | `Notification` | Event-driven in-app notifications for bookings, check-in, check-out, cancellations, refunds, and property approvals. | Generic relationships to `users.User` and optional `bookings.Booking`. |
| **`core`** | N/A (Utility Layer) | Global RFC 7807 exception handler (`custom_exception_handler`), reusable DRF permission classes (`IsCustomer`, `IsHostOrOwner`, `IsPlatformAdmin`, `IsOwnerOrAdmin`). | Intercepts all DRF view execution across all apps. |
| **`util`** | N/A (Helper Layer) | OTP hashing/generation, strict Indian financial validators (IFSC, Bank Account, UPI ID, Phone, Email, Dates). | Invoked across `users`, `bookings`, `payments`, and `rooms`. |

---

# SECTION D: CONFIRMED CRITICAL FLAWS – P0 (VULNERABILITY DOSSIER)

```
========================================================================================
CRITICAL FLAW DOSSIER: SEC-P0-01 | PLAINTEXT OTP LEAKAGE IN PASSWORD RESET RESPONSE
========================================================================================
- Priority: P0 (CRITICAL / IMMEDIATE EXPLOITABLE VULNERABILITY)
- File Path: D:\BookMyRoomBackend\BookMyRoomBackend\users\views.py
- Component: ForgotPasswordView (lines 454-455)
- Code Evidence:
      return Response({
          "message": f"6-digit verification code sent to {masked}.",
          "email": user.email,
          "username": user.username,
          "masked_email": masked,
          "mail_sent": mail_sent,
          **({"dev_hint_otp": otp} if (not mail_sent or getattr(settings, 'DEBUG', False)) else {})
      }, status=status.HTTP_200_OK)

- Flaw Analysis:
  The API unconditionally injects the raw, plaintext 6-digit verification OTP into the JSON response
  body whenever `DEBUG=True` OR whenever SMTP email transmission fails (`not mail_sent`).
  Because `DEBUG` defaults to `True` in `config/settings.py`, every single password reset request
  leaks the valid OTP directly back to the HTTP client. Even in production, an attacker who targets
  an email that causes an SMTP bounce or timeout will trigger `mail_sent = False` and receive the OTP.

- Potential Exploitation Scenario:
  1. Attacker calls `POST /api/auth/forgot-password/` with payload `{"identifier": "admin@goonstay.com"}`.
  2. The server responds with `200 OK` containing:
     `{"email": "admin@goonstay.com", "dev_hint_otp": "749281", ...}`.
  3. Attacker immediately posts `{"email": "admin@goonstay.com", "otp": "749281", "new_password": "HackedPassword123!"}`
     to `POST /api/auth/reset-password/`.
  4. Platform Administrator account is instantly compromised in under 2 seconds without inbox access.

- Business Impact:
  Complete account takeover (ATO) across all user roles: Super Admins, Hotel Owners, and Customers.
  Severe regulatory violation (CERT-In, GDPR, DPDP Act 2023), resulting in catastrophic brand damage
  and total loss of customer and hotelier trust.

- Recommended Solution:
  Remove `dev_hint_otp` entirely from production code. Never expose authentication secrets in responses.
  Return a generic timing-safe response: "If an account exists, a code has been dispatched."

- Required Test Case:
  Send `POST /api/auth/forgot-password/` across all environment states (`DEBUG=True`, `DEBUG=False`,
  SMTP mock failure); assert that `"dev_hint_otp"` is NEVER present in `response.data`.
========================================================================================
```

```
========================================================================================
CRITICAL FLAW DOSSIER: SEC-P0-02 | BROKEN OBJECT-LEVEL AUTHORIZATION IN REVIEW DELETION
========================================================================================
- Priority: P0 (CRITICAL / OWASP API1:2023 BOLA)
- File Path: D:\BookMyRoomBackend\BookMyRoomBackend\reviews\views.py
- Component: ReviewDetailView (lines 90-99)
- Code Evidence:
      class ReviewDetailView(generics.RetrieveDestroyAPIView):
          queryset = Review.objects.all()
          serializer_class = ReviewSerializer
          permission_classes = [permissions.IsAuthenticated]

          def perform_destroy(self, instance):
              hotel = instance.hotel
              instance.delete()
              update_hotel_guest_rating(hotel)

- Flaw Analysis:
  `ReviewDetailView` enforces only `permissions.IsAuthenticated`. It does not define an object-level
  permission (such as `core.permissions.IsOwnerOrAdmin`) nor does it verify that `instance.user == request.user`.
  Any logged-in user with a valid JWT token can issue a `DELETE` request against ANY review ID.

- Potential Exploitation Scenario:
  1. A malicious hotel owner registers a regular customer account.
  2. The owner inspects negative reviews on their property or positive reviews on competing properties.
  3. The owner issues automated `DELETE /api/reviews/<id>/` requests for review IDs 1 through 10,000.
  4. All target reviews are permanently purged from the database, and hotel aggregate star ratings
     are artificially manipulated.

- Business Impact:
  Malicious destruction of platform review integrity, anti-competitive sabotage among hotel owners,
  and distortion of public hotel reputation metrics.

- Recommended Solution:
  Bind `core.permissions.IsOwnerOrAdmin` to `permission_classes`. In `perform_destroy`, ensure
  `if instance.user != self.request.user and not self.request.user.is_staff: raise PermissionDenied(...)`.

- Required Test Case:
  Create Review A as User 1. Authenticate as User 2. Issue `DELETE /api/reviews/<review_a_id>/`.
  Assert HTTP 403 Forbidden is returned and Review A remains intact in the database.
========================================================================================
```

```
========================================================================================
CRITICAL FLAW DOSSIER: SEC-P0-03 | CROSS-TENANT HOTEL STAFF PRIVILEGE ESCALATION
========================================================================================
- Priority: P0 (CRITICAL / BROKEN ACCESS CONTROL & MULTI-TENANCY LEAK)
- File Path: D:\BookMyRoomBackend\BookMyRoomBackend\bookings\views.py
- Component: StaffCheckInView & StaffCheckOutView (lines 478-480, 514-516)
- Code Evidence:
      if (
          request.user != booking.hotel.owner 
          and not request.user.is_staff 
          and request.user.role not in ['ADMIN', 'SUPER_ADMIN', 'HOTEL_STAFF']
      ):
          return Response({"error": "Permission denied to perform check-in."}, status=status.HTTP_403_FORBIDDEN)

- Flaw Analysis:
  The authorization check uses a flawed boolean clause: if `request.user.role == 'HOTEL_STAFF'`, the condition
  `request.user.role not in [...]` evaluates to `False`. Consequently, the entire `if` block evaluates to `False`,
  granting immediate execution permission.
  The code NEVER verifies whether the `HOTEL_STAFF` user is employed by or affiliated with `booking.hotel`!

- Potential Exploitation Scenario:
  1. User A is registered as staff at a budget lodge in Delhi.
  2. User A discovers or enumerates a booking ID belonging to a 5-star resort in Goa.
  3. User A issues `POST /api/bookings/<booking_id>/check-in/`.
  4. The guest at the Goa resort is marked as "Checked In", altering operational stay records,
     triggering guest push notifications, and corrupting the audit trail.

- Business Impact:
  Severe multi-tenant operational security failure. Host liability disputes, fake check-ins,
  fraudulent stay confirmations, and corruption of stay compliance records.

- Recommended Solution:
  Introduce an explicit relationship between staff and properties (e.g. `HotelStaff` membership table).
  Validate: `if request.user.role == 'HOTEL_STAFF' and not booking.hotel.staff_members.filter(user=request.user).exists(): raise PermissionDenied(...)`.

- Required Test Case:
  Authenticate as Staff member belonging to Hotel 1. Attempt `POST /api/bookings/<id>/check-in/`
  on a booking belonging to Hotel 2. Assert HTTP 403 Forbidden.
========================================================================================
```

```
========================================================================================
CRITICAL FLAW DOSSIER: SEC-P0-04 | CRYPTOGRAPHICALLY INSECURE PSEUDO-RANDOM OTP ENGINE
========================================================================================
- Priority: P0 (HIGH-SEVERITY SECURITY DEFECT)
- File Path: D:\BookMyRoomBackend\BookMyRoomBackend\util\otp.py
- Component: generate_otp (lines 1-7)
- Code Evidence:
      import random

      def generate_otp():
          """Generates a 6-digit random numeric OTP string."""
          return str(random.randint(100000, 999999))

- Flaw Analysis:
  Python's standard `random` module implements the Mersenne Twister algorithm (MT19937).
  The Python Standard Library documentation explicitly warns:
  "The pseudo-random generators of this module should not be used for security purposes."
  MT19937 is fully deterministic. By observing 624 successive 32-bit random outputs (or by leveraging
  symbolic execution tools), an adversary can reconstruct the PRNG's internal state matrix and predict
  every subsequent OTP generated by the server worker.

- Potential Exploitation Scenario:
  An attacker triggers multiple registration or password reset OTPs, logs the values, reconstructs
  the internal state of the server process, and successfully predicts the next OTP generated for a
  high-value administrator or hotel owner account.

- Business Impact:
  Platform-wide authentication bypass and predictability of all 2FA / password reset tokens.

- Recommended Solution:
  Replace `import random` with Python's cryptographically secure `secrets` module:
  `import secrets; return f"{secrets.randbelow(900000) + 100000:06d}"`.

- Required Test Case:
  Verify statistical entropy and ensure that `util.otp.generate_otp` utilizes `secrets.SystemRandom`
  derived from `/dev/urandom` or Windows `CryptGenRandom`.
========================================================================================
```

```
========================================================================================
CRITICAL FLAW DOSSIER: SEC-P0-05 | NO ATTEMPT THROTTLING OR LOCKOUT ON OTP VERIFICATION
========================================================================================
- Priority: P0 (AUTHENTICATION BRUTE-FORCE VULNERABILITY)
- File Path: D:\BookMyRoomBackend\BookMyRoomBackend\users\views.py
- Component: VerifyOTPView (lines 741-766) & ResetPasswordView (lines 458-491)
- Code Evidence:
      if record.otp_hash != otp_hashed:
          return Response({"error": "Invalid 6-digit OTP code. Please check and try again."}, status=status.HTTP_400_BAD_REQUEST)

- Flaw Analysis:
  Neither `VerifyOTPView` nor `ResetPasswordView` increments a failure counter (`attempts += 1`)
  or invalidates the OTP after 3 or 5 unsuccessful attempts. Furthermore, neither view attaches
  scoped rate limiting classes (`throttle_classes = [ScopedRateThrottle]`).
  A 6-digit OTP has exactly $1,000,000$ possible combinations. Within the 5-minute (or 15-minute)
  validity window, a distributed botnet sending 3,500 requests per second can exhaust the keyspace
  and verify or reset an account with 100% mathematical certainty.

- Potential Exploitation Scenario:
  Attacker triggers a password reset for `victim@gmail.com`. Attacker runs a multi-threaded Python
  script with `ThreadPoolExecutor` cycling OTPs from `000000` to `999999` against `/api/auth/reset-password/`.
  The OTP is accepted, changing the victim's password.

- Business Impact:
  Targeted account takeover of any user on the platform via automated brute-force attacks.

- Recommended Solution:
  1. Add an `attempts` integer field to `EmailOTP`.
  2. If `record.otp_hash != otp_hashed`: increment `record.attempts += 1`.
  3. If `record.attempts >= 5`: delete or invalidate the OTP record immediately and return HTTP 429 Too Many Requests.
  4. Enforce strict DRF IP/User throttling (`throttle_scope = 'otp_verify'` at 5 requests/minute).

- Required Test Case:
  Send 5 incorrect OTP requests for a single email. Assert that on the 6th attempt, the OTP is destroyed,
  and the endpoint returns HTTP 429 / 400 with "Too many failed attempts. Code invalidated."
========================================================================================
```

---

# SECTION E: HIGH PRIORITY FLAWS – P1 (SYSTEM INTEGRITY & COMMERCE)

| Issue ID | File & Method | Flaw Description | Exploit Scenario / Business Risk | Remediation Blueprint |
| :--- | :--- | :--- | :--- | :--- |
| **SEC-P1-01** | `bookings/views.py`<br>`BookingListCreateView.create` | **Unheld Inventory During Payment Checkout (Ghost Overbooking):**<br>Availability calculation excludes `PENDING_PAYMENT` bookings. Two users booking the last room simultaneously both see it available, both create orders, and both pay. | Two guests arrive at the hotel on the same night having both paid full tariff for the same single room. Severe customer distress, hotel operational friction, and chargeback penalties. | Implement a 10-minute temporary inventory reservation lock (using Redis or DB `hold_expires_at`). Count held reservations in availability queries. If payment succeeds, convert to confirmed; if expired, release back to pool. |
| **SEC-P1-02** | `rooms/utils.py`<br>`allocate_room_number_for_booking` | **Non-Atomic Room Allocation Without Row Locks:**<br>Room allocation reads available units and updates the booking row without wrapping the physical unit in a database row-level lock (`select_for_update`). | Concurrent Razorpay webhook callbacks or payment verifications simultaneously allocate "Room 101" to two separate bookings. | Wrap unit allocation inside `transaction.atomic()`, execute `select_for_update()` on the room and booking rows, and normalize physical room units into a relational table. |
| **SEC-P1-03** | `config/settings.py`<br>`DATABASES` | **SQLite Engine Incompatibility with High Concurrency:**<br>Default development config relies on `db.sqlite3`. SQLite uses file-level locking. `select_for_update()` is silently ignored. | Under concurrent booking load, SQLite throws `sqlite3.OperationalError: database is locked`. Transactions fail, and row-level locks fail to prevent race conditions. | Force PostgreSQL deployment in staging and production. Ensure `USE_POSTGRES=True` is verified in deployment pipelines. |
| **SEC-P1-04** | `payments/models.py`<br>`HostPayoutAccount` | **Plaintext Storage of Banking Information:**<br>Host bank account numbers, IFSC codes, and UPI IDs are stored in plaintext `CharField` columns. | Database dump or unauthorized SQL read exposes all hotel owner banking credentials and financial payout destinations. | Enforce field-level encryption (AES-256 via `django-cryptography` or KMS-backed Fernet keys). Store only masked representations for display. |
| **SEC-P1-05** | `hotels/views.py`<br>`HotelImageUploadView` & `HotelDocumentUploadView` | **Unrestricted File Upload Vulnerability:**<br>Files received via `request.FILES.get('image')` are saved directly without MIME validation, extension whitelisting, or file size limits. | Attacker uploads an executable `.html` (stored XSS), `.svg` containing malicious scripts, or a 10GB file to exhaust server disk space. | Validate MIME type using `python-magic`, enforce extension whitelist (`.jpg`, `.jpeg`, `.png`, `.webp`, `.pdf`), cap file size at 5MB, and sanitize filenames. |
| **SEC-P1-06** | `config/settings.py`<br>`SIMPLE_JWT` | **Stateless JWT Tokens with No Revocation / Blacklist:**<br>JWT access tokens have a 24-hour lifetime. `BLACKLIST_AFTER_ROTATION = False`. `rest_framework_simplejwt.token_blacklist` is NOT in `INSTALLED_APPS`. | If a user clicks Logout or an access token is stolen, the token remains fully operational for 24 hours. The platform cannot revoke compromised tokens. | Install `token_blacklist` app, shorten `ACCESS_TOKEN_LIFETIME` to 15 minutes, enable refresh token blacklisting, and implement a Redis token revocation cache for immediate logouts. |
| **SEC-P1-07** | `payments/views.py`<br>`WebhookView` | **Fragile Webhook Deduplication & Event ID Fallback:**<br>Line 572 uses `event_data.get('event_id') or event_data.get('id') or f"evt_{timestamp}"`. Razorpay delivers the event ID in header `X-Razorpay-Event-Id`. | When Razorpay retries webhook delivery due to network latency, the timestamp fallback generates a new ID, bypassing the deduplication check and executing duplicate handlers. | Extract event ID directly from `request.headers.get('X-Razorpay-Event-Id')`. If missing or invalid, reject immediately with HTTP 400. |

---

# SECTION F: MEDIUM PRIORITY FLAWS – P2 (LOGIC & COMPLIANCE)

```
+---------------------------------------------------------------------------------------+
| P2 ISSUE: UNCONSTRAINED UNAUTHENTICATED ACCOUNT ENUMERATION                           |
| Location: users/views.py (CheckEmailView line 625, CheckPhoneView line 656)           |
+---------------------------------------------------------------------------------------+
| Evidence:                                                                             |
|   class CheckEmailView(APIView):                                                      |
|       permission_classes = [permissions.AllowAny]                                     |
|       def post(self, request):                                                        |
|           exists = User.objects.filter(email__iexact=email).exists()                  |
|           return Response({"exists": exists, "is_available": not exists})             |
|                                                                                       |
| Flaw & Risk:                                                                          |
|   Provides unauthenticated threat actors with a dedicated oracle to enumerate valid   |
|   email addresses and mobile numbers registered on the platform without rate limits.  |
|   Facilitates targeted phishing and password-spraying attacks against users.          |
|                                                                                       |
| Fix:                                                                                  |
|   Apply strict rate limiting (e.g. 5 requests/minute per IP) and CAPTCHA challenge    |
|   on public existence checks, or combine validation directly into registration steps. |
+---------------------------------------------------------------------------------------+
```

```
+---------------------------------------------------------------------------------------+
| P2 ISSUE: DENORMALIZED COMMA-SEPARATED ROOM NUMBERS (1NF VIOLATION)                   |
| Location: rooms/models.py (Room.room_numbers = CharField(max_length=500))             |
+---------------------------------------------------------------------------------------+
| Evidence:                                                                             |
|   room_numbers = models.CharField(max_length=500, help_text="Comma-separated...")   |
|   def get_all_room_numbers(self):                                                     |
|       return [r.strip() for r in self.room_numbers.split(',') if r.strip()]          |
|                                                                                       |
| Flaw & Risk:                                                                          |
|   Violates First Normal Form (1NF). Limits property inventory to ~100 room numbers.   |
|   Prevents relational queries on individual physical units (e.g., Room 101 status:    |
|   CLEAN, DIRTY, OUT_OF_ORDER, INSPECTED, UNDER_MAINTENANCE). String parsing via      |
|   regex in Python creates query overhead and race conditions during high concurrency. |
|                                                                                       |
| Fix:                                                                                  |
|   Create a normalized `PhysicalRoom` / `RoomUnit` model:                              |
|   `RoomUnit(room_type=ForeignKey(Room), unit_number="101", floor=1, status=...)`.    |
+---------------------------------------------------------------------------------------+
```

```
+---------------------------------------------------------------------------------------+
| P2 ISSUE: CALENDAR BLOCK OVERRIDES ENTIRE ROOM TYPE INSTEAD OF SPECIFIC UNITS         |
| Location: rooms/models.py (RoomCalendarBlock, unique_together = ('room', 'date'))     |
+---------------------------------------------------------------------------------------+
| Evidence:                                                                             |
|   class RoomCalendarBlock(models.Model):                                              |
|       room = models.ForeignKey(Room, related_name='calendar_blocks')                 |
|       date = models.DateField(db_index=True)                                         |
|       is_blocked = models.BooleanField(default=False)                                 |
|                                                                                       |
| Flaw & Risk:                                                                          |
|   If a hotel owner has 10 Deluxe Rooms and takes Room 104 offline for painting,       |
|   marking `is_blocked = True` on `RoomCalendarBlock` blocks the ENTIRE category      |
|   (all 10 rooms) on that date!                                                        |
|                                                                                       |
| Fix:                                                                                  |
|   Link `RoomCalendarBlock` to specific `RoomUnit` instances or add an integer         |
|   `blocked_quantity` field to decrement available count rather than full closure.     |
+---------------------------------------------------------------------------------------+
```

```
+---------------------------------------------------------------------------------------+
| P2 ISSUE: HOTEL OWNER UNCONTROLLED REFUND TRIGGERING (PLATFORM CAPITAL RISK)          |
| Location: payments/views.py (RefundView lines 1140-1145)                              |
+---------------------------------------------------------------------------------------+
| Evidence:                                                                             |
|   is_hotel_owner = (booking.hotel.owner == user)                                      |
|   if not (is_admin or is_hotel_owner): return Response({"error": "Permission denied"})|
|                                                                                       |
| Flaw & Risk:                                                                          |
|   Hotel owners can trigger refunds via Razorpay API directly from the platform's      |
|   central merchant account. If the host has already received a payout for that stay  |
|   or holds a zero ledger balance, the refund drains the platform's bank funds.        |
|                                                                                       |
| Fix:                                                                                  |
|   Owner refund actions must create an "Owner Approved Refund Request" subject to      |
|   automated ledger balance verification or Platform Admin financial approval.         |
+---------------------------------------------------------------------------------------+
```

---

# SECTION G: LOW PRIORITY IMPROVEMENTS – P3 (HYGIENE & CODE QUALITY)

1. **Dead Code / Redundant Imports (`payments/views.py`):**  
   `payments/views.py` spans over 3,149 lines with repeated local imports (`import razorpay`, `from decimal import Decimal`, `from django.db import transaction`) inside individual view methods rather than at module level.
2. **Missing `related_name` Optimization:**  
   Several foreign keys in `payments` and `notifications` use default or generic reverse accessors, risking attribute collisions during complex query joins.
3. **Hardcoded Strings & Status Magic Values:**  
   Status strings like `'PENDING'`, `'CONFIRMED'`, and `'CAPTURED'` are occasionally compared as raw literals rather than referencing model class constants (`Booking.STATUS_CONFIRMED`, `Payment.STATUS_CAPTURED`).
4. **Console `print()` Statements in Core Workflows:**  
   Found `print(f"[AutoCheckout] Error...")` in `rooms/utils.py` and `print(f"[OTP FALLBACK LOG]...")` in `users/views.py`. All output should utilize Python's structured `logging` module (`logger.info()`, `logger.error()`).

---

# SECTION H: COMPLETE SECURITY AUDIT (OWASP TOP 10 & API SECURITY TOP 10)

```
+----------------------------------------------------------------------------------------------------------+
| OWASP TOP 10 (2021) & API SECURITY TOP 10 (2023) EVALUATION MATRIX                                       |
+----------------------------------------------------------------------------------------------------------+
| Threat Category                      | Current Status | Audit Finding & Vector                           |
+----------------------------------------------------------------------------------------------------------+
| A01:2021 - Broken Access Control     | FAIL (CRITICAL)| BOLA in review deletion (SEC-P0-02);            |
| (API1:2023 / API5:2023)              |                | Cross-hotel check-in by staff (SEC-P0-03).       |
+--------------------------------------+----------------+--------------------------------------------------+
| A02:2021 - Cryptographic Failures    | FAIL (CRITICAL)| Insecure PRNG in OTP generation (SEC-P0-04);     |
| (API2:2023 Broken Authentication)    |                | Plaintext bank accounts in DB (SEC-P1-04).       |
+--------------------------------------+----------------+--------------------------------------------------+
| A03:2021 - Injection                 | PASS           | Django ORM parameterizes all SQL queries;        |
|                                      |                | No raw SQL queries found.                        |
+--------------------------------------+----------------+--------------------------------------------------+
| A04:2021 - Insecure Design           | WARN           | Unheld inventory race condition during           |
|                                      |                | payment checkout allows double-booking.          |
+--------------------------------------+----------------+--------------------------------------------------+
| A05:2021 - Security Misconfiguration | WARN           | Default settings have DEBUG=True, fallback       |
|                                      |                | secret keys, and permissive CORS regexes.        |
+--------------------------------------+----------------+--------------------------------------------------+
| A06:2021 - Vulnerable Components     | PASS           | Dependencies up to date (Django 6.1.1, DRF 3.18, |
|                                      |                | SimpleJWT 5.5.1, razorpay 2.0.1).                |
+--------------------------------------+----------------+--------------------------------------------------+
| A07:2021 - Auth Identification Flaws | FAIL (CRITICAL)| Plaintext OTP leakage in API (SEC-P0-01);        |
|                                      |                | No brute-force lock on OTP verify (SEC-P0-05).   |
+--------------------------------------+----------------+--------------------------------------------------+
| A08:2021 - Software & Data Integrity | FAIL (HIGH)    | Unvalidated file uploads in hotels app           |
|                                      |                | (SEC-P1-05); Webhook ID deduplication (SEC-P1-07)|
+--------------------------------------+----------------+--------------------------------------------------+
| A09:2021 - Security Logging Failures | WARN           | Console prints used instead of logging; AuditLog |
|                                      |                | exists for admin, but missing for auth events.   |
+--------------------------------------+----------------+--------------------------------------------------+
| A10:2021 - Server-Side Req Forgery   | PASS           | No user-controlled outbound HTTP requests        |
|                                      |                | allowed without platform domain whitelisting.    |
+----------------------------------------------------------------------------------------------------------+
```

---

# SECTION I: AUTHENTICATION AND AUTHORIZATION AUDIT

### 1. Role-Based Access Control (RBAC) Architecture
The platform defines four logical user roles in `users.models.User`:
- `CUSTOMER`: End-user guest who searches, books, pays, cancels, reviews, and wishlists properties.
- `HOTEL_OWNER`: Host partner managing property profiles, room tariffs, photos, staff, and reviewing earnings.
- `HOTEL_STAFF`: Property-level operational personnel authorized to check in and check out guests.
- `ADMIN` / `SUPER_ADMIN`: Internal platform operators with full permissions over hotels, users, refunds, and financial ledgers.

### 2. Identified RBAC Gaps
1. **Ambiguous Host Role Check:** In `hotels/views.py`, authorization checks use both `getattr(user, 'role', '') == 'HOTEL_OWNER'` and `user.hotels.exists()`. A user whose role was downgraded by an admin can still access host dashboards if orphaned hotel records exist.
2. **Missing Superuser Deletion Guard:** In `users/views.py` (`UserDeleteView`), an `ADMIN` cannot delete a `SUPER_ADMIN`, but an `ADMIN` can delete another `ADMIN` or their own account.
3. **No Session-Wide Invalidation on Password Change:** Changing passwords in `ChangePasswordView` does not invalidate existing JWT refresh tokens or active sessions.

---

# SECTION J: BOOKING ENGINE AND INVENTORY AUDIT

### 1. Availability Calculation Logic
The availability algorithm resides in `rooms/utils.py` (`get_available_room_count`):
$$\text{Overlapping Criteria: } (\text{CheckIn}_{\text{existing}} < \text{CheckOut}_{\text{requested}}) \land (\text{CheckOut}_{\text{existing}} > \text{CheckIn}_{\text{requested}})$$
$$\text{Reserved Units} = \sum_{\text{overlapping}} \text{number\_of\_rooms}$$
$$\text{Available Count} = \max(0, \text{total\_rooms} - \text{Reserved Units})$$

### 2. Flaws in Booking State Transitions
```
Current State Transition Flow:
[PENDING_PAYMENT] -----(Payment Succeeded)-----> [CONFIRMED] -----> [CHECKED_IN] -----> [CHECKED_OUT]
       |                                              |
(15 min timeout)                                (Cancellation)
       v                                              v
   [EXPIRED]                                 [CANCELLED] / [REFUND_PENDING]
```
- **Vulnerability:** `PENDING_PAYMENT` bookings are **excluded** from `Reserved Units`. Because an online payment transaction on Razorpay can take 2 to 5 minutes, two customers can initiate payment for the identical inventory. When both complete payments, the system marks both as `CONFIRMED`.
- **Mitigation Requirement:** Implement a transitional `HELD` status with an automatic Redis TTL (e.g. 10 minutes). Count `HELD` bookings in availability checks. If payment is verified, transition `HELD` $\rightarrow$ `CONFIRMED`. If the timer expires, release the inventory back to the pool.

---

# SECTION K: PAYMENT AND FINANCIAL AUDIT

### 1. Centralized Escrow Architecture
GOONSTAY enforces a platform-mediated escrow model:
- All guest room charges and meal plan fees are collected directly into GOONSTAY's central Razorpay merchant account.
- Funds are never paid directly to individual hotel owner Razorpay accounts.
- For each completed booking, a `HostEarning` record is created:
  $$\text{Gross Amount} = \text{Tariff} + \text{Meal Plans}$$
  $$\text{Platform Commission} = \text{Gross Amount} \times \text{Commission Rate (e.g., 10\%)}$$
  $$\text{Net Host Payable} = \text{Gross Amount} - \text{Platform Commission}$$
  $$\text{Eligible Settlement Date} = \text{CheckOut Date} + 7 \text{ Days Holding Period}$$

### 2. Multi-Mode Refund System
`payments/views.py` supports three customer refund destination channels:
1. `ORIGINAL_SOURCE`: Automated reversal via Razorpay API (`/v1/payments/{payment_id}/refund`).
2. `BANK_TRANSFER`: Direct payout to customer's savings/current account via RazorpayX (NEFT/IMPS/RTGS).
3. `UPI`: Direct instant payout to customer's Virtual Payment Address (VPA) via RazorpayX.

### 3. Financial Vulnerabilities & Fixes
- **Double Refund Exploit Guard:** The system correctly validates `(already_refunded + refund_amount) <= max_eligible_refund`.
- **Missing Webhook Event Deduplication Lock:** In `WebhookView`, the event check does not use `select_for_update()`, risking simultaneous execution of duplicate webhook deliveries during high network concurrency.

---

# SECTION L: DATABASE AND ARCHITECTURE AUDIT

```
+---------------------------------------------------------------------------------------+
| CURRENT STATE: DEVELOPMENT ENGINE (SQLite) vs TARGET: PRODUCTION ENGINE (PostgreSQL)  |
+---------------------------------------------------------------------------------------+
| Feature                     | SQLite (Current Local)     | PostgreSQL (Target Prod)   |
+---------------------------------------------------------------------------------------+
| Concurrency Model           | Database-level lock (WAL)  | Row-level MVCC             |
| `select_for_update()`       | Silently Ignored           | Fully Enforced Locks       |
| High-Throughput Writes      | Locks on heavy concurrency | Scales across connections  |
| Connection Pooling          | Not supported              | Supported (PgBouncer)      |
| Production Suitability      | Zero (Unacceptable)        | Industry Standard          |
+---------------------------------------------------------------------------------------+
```

### Schema & Indexing Recommendations
1. **Add Missing Indexes:**
   - `bookings_booking(customer_id, booking_status)`
   - `bookings_booking(hotel_id, check_in, check_out)`
   - `hotels_hotel(city, is_approved, is_active)`
   - `payments_payment(razorpay_order_id, status)`
2. **Normalize Physical Rooms:**
   - Deprecate `rooms_room.room_numbers` comma-separated text.
   - Introduce `rooms_roomunit(id, room_type_id, unit_number, floor, status)`.

---

# SECTION M, N, O: USER EXPERIENCE (UX) EVALUATION

### Section M: Customer (Guest) UX
- **Strengths:** Intuitive reservation flow, clean meal plan upgrade toggles, transparent price breakdown showing GST and applied promo discounts.
- **Pain Points:**
  - Lack of interactive map-based property exploration.
  - Absence of real-time inventory count ("Only 1 room left at this price!").
  - Inability to book multiple distinct room categories within a single checkout session.

### Section N: Hotel Owner (Host) UX
- **Strengths:** Clear dashboard displaying total earnings, pending payouts, recent bookings, and room category setup.
- **Pain Points:**
  - Inability to block specific physical room units for maintenance (currently blocks the entire room category).
  - Lack of a visual monthly occupancy calendar grid (Gantt-style room matrix).
  - No exportable monthly GST settlement invoices in PDF/Excel format.

### Section O: Platform Admin UX
- **Strengths:** Comprehensive Django Admin integration with dedicated filters for hotel approvals, dispute holds, and payment ledgers.
- **Pain Points:**
  - No unified visual dashboard for platform-wide metrics (Daily Gross Booking Value, Refund Rates, Commission Revenue).
  - Manual approval required for hotel documents without automated OCR/validation checks.

---

# SECTION P: REAL COMPETITOR BENCHMARKING MATRIX

*Publicly verified platform standards as of November 2026:*

| Feature / Dimension | MakeMyTrip (MMT) | Goibibo | Booking.com | Agoda | OYO Rooms | **GOONSTAY (Current)** |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Inventory Hold During Checkout** | 10-minute cart lock with timer | 10-minute hold with timer | 15-minute hold during payment | 10-minute hold with timer | Real-time hold on payment step | **Missing (Ghost Overbooking Risk)** |
| **Room Allocation Timing** | Post-payment or at check-in | Post-payment or at check-in | At check-in by front desk | At check-in by front desk | Post-payment instant assignment | **Post-payment auto-allocation (Functional)** |
| **Meal Plan Upgrades** | Room Only / CP / MAP / AP options | Room Only / Breakfast / Dinner | Rate plans linked to room types | Add breakfast/dinner options | Complimentary breakfast toggle | **Full 4-tier plan upgrade (Functional)** |
| **Tiered Cancellation Policy** | Automated refund slabs based on hours | Automated refund slabs based on hours | Strict / Flexible / Non-refundable | Free cancel until 24-48 hrs | Free cancel up to check-in hour | **Automated tiered slabs (Functional)** |
| **Loyalty / Rewards Currency** | MyCash / MMT Black | GoCash / GoCash+ | Genius VIP Tiers (10-20% off) | AgodaVIP Cash & Points | OYO Rupee / Wizard Membership | **Missing (Promotional Coupons Only)** |
| **Map-Based Discovery** | Interactive Leaflet/Google Maps | Google Maps with landmark filters | Full Map view with price pins | High-performance Map search | Map view with radius slider | **Missing (City/Area text filter only)** |
| **Pay-at-Hotel Option** | Supported on select hotels | Supported on select hotels | Core global value proposition | Supported on select hotels | Supported on most budget hotels | **Missing (Online Prepaid Only)** |
| **Multi-Room Booking** | Up to 8 rooms per booking | Up to 8 rooms per booking | Up to 30 rooms per booking | Up to 9 rooms per booking | Up to 5 rooms per booking | **Single room-type multi-unit only** |
| **Guest Messaging / Chat** | In-app host/hotel direct messaging | In-app chat support | Built-in Extranet guest chat | In-app messaging system | In-app customer support chat | **Support tickets & host chat (Functional)** |

---

# SECTION Q: MISSING STRATEGIC FEATURES & OPPORTUNITIES

1. **Interactive Map-Based Hotel Search:**  
   Integrate Leaflet.js / Mapbox with spatial PostgreSQL PostGIS coordinates (`ST_DWithin`) to allow guests to browse hotels by visual map boundaries and proximity to transit hubs.
2. **GOONSTAY Wallet & Loyalty System ("StayCoins"):**  
   Implement a closed-loop digital wallet. Reward repeat guests with 5% cashback on completed stays, usable on future bookings.
3. **Pay-at-Hotel with Credit Card Guarantee:**  
   Allow guests to reserve without immediate prepayment, securing the reservation with card pre-authorization or a nominal guarantee deposit.
4. **Hourly / Day-Use Micro-Stays (OYO / ByHours Model):**  
   Introduce 3-hour, 6-hour, and 12-hour booking options for transit travelers near airports and railway stations to monetize idle daytime room capacity.
5. **Automated Dynamic Pricing Engine:**  
   Algorithmic price surging based on real-time hotel occupancy rates (e.g. automatically increase room rate by 15% once property occupancy crosses 80%).

---

# SECTION R: PERFORMANCE, SCALABILITY, AND CACHING

```
+---------------------------------------------------------------------------------------+
| TARGET HIGH-PERFORMANCE PRODUCTION SCALING INFRASTRUCTURE                             |
+---------------------------------------------------------------------------------------+
|                                  AWS CloudFront / Cloudflare                          |
|                               (Global Edge CDN & DDoS Defense)                        |
|                                              |                                        |
|                                              v                                        |
|                                     NGINX Reverse Proxy                              |
|                          (SSL Termination, Gzip/Brotli, Static Cache)                 |
|                                              |                                        |
|                                              v                                        |
|                                  Gunicorn / Uvicorn Cluster                           |
|                             (Django REST Framework Monolith)                          |
|                                        /           \                                  |
|                                       /             \                                 |
|                                      v               v                                |
|                           PostgreSQL 16 (Primary)   Redis 7 Cluster                   |
|                            - PgBouncer Pooling       - Session / JWT Revocation       |
|                            - Read Replicas           - 10-Min Inventory Hold Locks    |
|                                                      - Celery Async Task Broker       |
|                                                              |                        |
|                                                              v                        |
|                                                       Celery Workers                  |
|                                                  - Async Transactional Emails         |
|                                                  - RazorpayX Payout Disbursals        |
|                                                  - Daily Auto-Checkout Sweeper        |
+---------------------------------------------------------------------------------------+
```

---

# SECTION S: AUTOMATED TESTING PLAN

### Current Testing Deficiencies
- Core apps (`users`, `bookings`, `hotels`, `rooms`, `coupons`, `reviews`) lack formal Django test suites (`tests.py` files are empty or missing).
- Reliance on standalone scripts in `scratch/` prevents integration into automated GitHub Actions CI/CD pipelines.

### Recommended Test Suite Matrix (Pytest / Django TestCase)

```python
# Sample Blueprint: tests/test_concurrency_booking.py
import pytest
from concurrent.futures import ThreadPoolExecutor
from rest_framework.test import APIClient
from bookings.models import Booking

@pytest.mark.django_db(transaction=True)
def test_simultaneous_booking_concurrency_prevents_double_booking():
    """Verifies that 2 users racing for the last room cannot both succeed."""
    hotel, room = setup_hotel_with_single_room()
    client1, client2 = APIClient(), APIClient()
    client1.force_authenticate(user=user_a)
    client2.force_authenticate(user=user_b)

    payload = {
        "room": room.id,
        "check_in": "2026-12-01",
        "check_out": "2026-12-03",
        "number_of_rooms": 1
    }

    def book(client):
        return client.post("/api/bookings/", payload, format="json")

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(book, client1)
        f2 = executor.submit(book, client2)
        r1, r2 = f1.result(), f2.result()

    statuses = [r1.status_code, r2.status_code]
    assert 201 in statuses, "At least one booking must succeed"
    assert 409 in statuses, "The concurrent booking must receive HTTP 409 Conflict"
    assert Booking.objects.filter(room=room).count() == 1
```

---

# SECTION T: PRODUCTION READINESS CHECKLIST

```
+---------------------------------------------------------------------------------------+
| PRE-FLIGHT PRODUCTION HARDENING CHECKLIST                                             |
+---------------------------------------------------------------------------------------+
| [ ] Set `DEBUG = False` unconditionally in production environment.                   |
| [ ] Generate a cryptographically random 64-character `SECRET_KEY` via KMS/Vault.      |
| [ ] Configure explicit `ALLOWED_HOSTS = ['api.goonstay.com', 'goonstay.com']`.        |
| [ ] Migrate from SQLite to PostgreSQL with PgBouncer connection pooling.              |
| [ ] Configure Redis for cache, inventory holds, and Celery background task queue.     |
| [ ] Enforce HTTPS: `SECURE_SSL_REDIRECT = True`, `SECURE_HSTS_SECONDS = 31536000`.   |
| [ ] Secure Cookies: `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True`.      |
| [ ] Configure production Razorpay live keys (`rzp_live_...`) and webhook secrets.     |
| [ ] Enable field-level AES-256 encryption on host bank accounts and payout data.      |
| [ ] Remove `dev_hint_otp` from all password recovery endpoints.                       |
| [ ] Implement 5-attempt rate-limiting lockout on all OTP verification endpoints.      |
| [ ] Add object-level ownership check to Review deletion endpoint.                     |
| [ ] Restrict staff check-in/out permissions strictly to affiliated hotel properties.  |
| [ ] Integrate Sentry / Datadog for real-time error tracking and APM monitoring.       |
| [ ] Establish automated daily database backups with offsite S3 retention.             |
+---------------------------------------------------------------------------------------+
```

---

# SECTION U: PRIORITIZED 13-PHASE IMPLEMENTATION ROADMAP

```
Phase 1: Critical Security Hardening (P0 Immediate Fixes)
├── Patch SEC-P0-01 (Remove dev_hint_otp from password recovery)
├── Patch SEC-P0-02 (Add IsOwnerOrAdmin to review deletion)
├── Patch SEC-P0-03 (Add hotel affiliation check to staff check-in)
├── Patch SEC-P0-04 (Migrate util/otp.py to secrets module)
└── Patch SEC-P0-05 (Add attempt counter and lockout to OTP verification)
[Estimated Effort: 2 Days]

Phase 2: Authentication & Token Lifecycle Upgrade
├── Install rest_framework_simplejwt.token_blacklist
├── Shorten access token lifetime to 15 mins (refresh token 7 days)
└── Implement Redis-backed token revocation on logout & password reset
[Estimated Effort: 2 Days]

Phase 3: Database Migration & Schema Hardening
├── Provision PostgreSQL 16 on staging & production
├── Migrate db.sqlite3 records to PostgreSQL
├── Add database indexes on bookings, hotels, and payments
└── Enforce field-level encryption on HostPayoutAccount banking data
[Estimated Effort: 3 Days]

Phase 4: Concurrency & Booking Engine Inventory Locks
├── Implement 10-minute temporary inventory hold on checkout initiation
├── Update availability calculations to respect active holds
└── Add select_for_update() row-locking on room inventory allocation
[Estimated Effort: 4 Days]

Phase 5: File Upload Security & Media Architecture
├── Add MIME-type verification using python-magic
├── Enforce file extension whitelist & 5MB file size limits
└── Migrate static/media file serving to Amazon S3 / Cloudflare R2
[Estimated Effort: 2 Days]

Phase 6: Webhook Hardening & Idempotency Lock
├── Extract event ID directly from X-Razorpay-Event-Id header
├── Enforce database row lock on WebhookEvent creation
└── Eliminate fallback timestamp-based event generation
[Estimated Effort: 2 Days]

Phase 7: Relational Room Unit Normalization
├── Create physical RoomUnit model (unit_number, floor, housekeeping status)
├── Migrate comma-separated room_numbers to RoomUnit records
└── Update RoomCalendarBlock to support unit-level maintenance blocks
[Estimated Effort: 5 Days]

Phase 8: Financial Safeguards & Host Payout Governance
├── Restrict hotel owner direct refunds; convert to Owner Approval workflow
├── Add automated ledger balance reconciliation before refund execution
└── Implement automated RazorpayX payout disbursement via Celery tasks
[Estimated Effort: 4 Days]

Phase 9: Comprehensive Automated Test Suite & CI/CD
├── Write Pytest test suites for users, bookings, hotels, and payments
├── Build automated concurrency and double-booking race condition tests
└── Integrate GitHub Actions CI pipeline with test coverage threshold (>85%)
[Estimated Effort: 5 Days]

Phase 10: Production Environment & Observability Setup
├── Configure Gunicorn with NGINX reverse proxy
├── Set up Sentry error monitoring and Celery worker health checks
└── Enforce SSL/TLS, HSTS, and secure cookie headers
[Estimated Effort: 3 Days]

Phase 11: Hotel Search & Map-Based Discovery (B2C Enhancement)
├── Integrate PostGIS / Leaflet.js map-based property search
└── Add price pin markers and landmark proximity filters
[Estimated Effort: 6 Days]

Phase 12: Host Management & Occupancy Grid (B2B Enhancement)
├── Build interactive Gantt-style monthly room occupancy calendar
└── Add exportable GST-compliant monthly settlement statements
[Estimated Effort: 5 Days]

Phase 13: Customer Loyalty & Advanced Features
├── Launch GOONSTAY "StayCoins" wallet and cashback engine
└── Implement hourly / day-use stay booking modes for airport hotels
[Estimated Effort: 7 Days]
```

---

# PART 12: FINAL SAFETY & PRESERVATION REPORT

| Verification Checkpoint | Status | Observations & Evidence |
| :--- | :--- | :--- |
| **Existing Source Files Modified?** | **NO (100% UNCHANGED)** | Zero edits applied to Python files, models, views, or configs. |
| **Database Records Altered or Deleted?** | **NO (100% UNCHANGED)** | No records created, updated, or removed in `db.sqlite3`. |
| **Migrations Generated or Applied?** | **NO (100% UNCHANGED)** | No `makemigrations` or `migrate` commands executed. |
| **Dependencies Installed or Upgraded?** | **NO (100% UNCHANGED)** | `requirements.txt` and `venv` left completely intact. |
| **Configuration or Environment Modified?** | **NO (100% UNCHANGED)** | `.env` and `settings.py` remain untouched. |
| **New Files Created Outside Authorization?** | **NO (100% COMPLIANT)** | Exactly ONE new report file created: `GOONSTAY_COMPLETE_SYSTEM_AUDIT.md`. |

---
*End of Master Audit Report. Awaiting stakeholder review and authorization before proceeding to Phase 1 implementation.*

