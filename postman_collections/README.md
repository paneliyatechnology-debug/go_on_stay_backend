# GoOnStay – Complete Postman Collections & Setup Guide

Aapke liye saare Postman collections ko ek hi organized folder `postman_collections/` mein arrange kar diya gaya hai, taaki dekhna, import karna aur test karna behad aasan rahe!

---

## 📁 Folder Structure

```
postman_collections/
│
├── 01_GOONSTAY_COMPLETE_ALL_IN_ONE_POSTMAN_COLLECTION.json   <-- (RECOMMENDED: Sabhi APIs ek hi jagah)
├── 02_GOONSTAY_STAFF_MANAGEMENT_COLLECTION.json              <-- (Dedicated: Keval Staff Management)
├── 03_GOONSTAY_HOST_OPERATIONS_COLLECTION.json               <-- (Dedicated: Hotel Owner / Host APIs)
├── 04_GOONSTAY_POSTMAN_ENVIRONMENT.json                      <-- (Postman Environment Variables)
└── README.md                                                 <-- (Yeh Guide)
```

---

## 🚀 1. Kya Hai `01_GOONSTAY_COMPLETE_ALL_IN_ONE_POSTMAN_COLLECTION.json`?

Is collection mein GoOnStay platform ki **sabhi APIs** organized, numbered folders mein shamil hain:

| Folder # | Module Name | Endpoints Covered |
| :--- | :--- | :--- |
| **01** | `Authentication & Onboarding` | Customer registration, login, OTP verification, Google OAuth, phone checks |
| **02** | `Profile & Settings` | Profile details, KYC, password changes, notification preferences |
| **03** | `Hotels & Discovery` | City listings, hotel search, filters (price, star rating, amenities), hotel details |
| **04** | `Rooms & Inventory` | Room categories, physical inventory availability check |
| **05** | `Bookings Management` | Booking creation, pre-payment availability gate, cancellation, resend confirmation email, invoices |
| **06** | `Payments & Razorpay` | Order creation, payment verification, webhook, immediate payment hold exit / release |
| **07** | `Reviews & Ratings` | Review submission, hotel reviews (with strict data isolation filter) |
| **08** | `Customer Support Tickets & Chat` | Customer support ticket creation, message threads, live hotel chat |
| **09** | `Wishlist` | Add / remove / view favorite hotels |
| **10** | `Coupons & Offers` | Coupon validation & discount calculations |
| **11** | `Notifications` | Customer in-app alerts & read status |
| **12** | **`Hotel Host Operations (Hotel Owners)`** | **Host Registration, Profile, Hotel Listings, Room Setup, Guest Check-In/Out** |
| **13** | **`Staff Management System (GoOnStay Centralized)`** | **Complete Staff System (All 5 Departments, RBAC, 7-Day Holding Rule, & 26 endpoints)** |
| **14** | `Super Admin Control Panel` | Admin dashboard, users list, system config, refunds management |
| **15** | `Indian Rule-Based Validation Tests` | Negative test suite (invalid phone, invalid dates, unauthorized access) |

---

## 👥 Folder 13: Staff Management System Detail (9 Subfolders)

Keval Staff Management ke liye saari APIs `13. Staff Management System` ke andar categorized hain:

1. **Staff Authentication**:
   - `POST /api/staff/login/` (Login ID ya Email + Password)
   - `GET /api/staff/me/` (Profile & assigned permissions)
   - `POST /api/staff/change-password/` (First-login mandatory reset)
   - `POST /api/staff/forgot-password/` (Secure hashed token link)
   - `POST /api/staff/reset-password/` (Token hash validation)
   - `POST /api/staff/logout/` (Token blacklist)
2. **Admin Staff Management**:
   - `POST /api/staff/create/` (Auto `GOS-EMP-XXX`, login ID, one-time temporary password)
   - `GET /api/staff/` (List all employees)
   - `GET /api/staff/<id>/` (Employee detail)
   - `PATCH /api/staff/<id>/update/` (Designation, phone updates)
   - `PATCH /api/staff/<id>/status/` (Activate / Deactivate / Suspend)
   - `GET /api/staff/departments/` (List 5 departments)
   - `GET /api/staff/<id>/permissions/` (View permissions)
   - `PUT /api/staff/<id>/permissions/update/` (Update permissions immediately)
   - `POST /api/staff/<id>/reset-password/` (Admin password reset)
   - `GET /api/staff/activities/` (Immutable audit trail logs)
3. **Reservation Department**:
   - `GET /api/staff/bookings/` (Guest search, filters)
   - `GET /api/staff/bookings/<id>/` (Stay details, pricing; manual calls only)
4. **Refund Department**:
   - `GET /api/staff/refunds/` (Pending refund queue)
   - `GET /api/staff/refunds/<id>/` (Refund inspection & payment details)
   - `POST /api/staff/refunds/<id>/process/` (Execute gateway refund)
   - `GET /api/staff/refunds/history/` (Settled refund logs)
5. **Payout Department**:
   - `GET /api/staff/payouts/` (Host payouts list)
   - `GET /api/staff/payouts/<id>/` (Earnings breakdown)
   - `POST /api/staff/payouts/<id>/process/` (**7-Day post-checkout rule enforcement**)
   - `GET /api/staff/payouts/history/` (Settled partner disbursements)
6. **Customer Support Department**:
   - `GET /api/staff/support/` (Ticket queue)
   - `GET /api/staff/support/<id>/` (Conversation thread)
   - `PATCH /api/staff/support/<id>/update/` (Status: IN_PROGRESS, RESOLVED, etc.)
   - `POST /api/staff/support/<id>/notes/` (**Internal-only staff notes**, hidden from customer)
7. **Hotel Verification Department**:
   - `GET /api/staff/verifications/` (Pending hotels)
   - `GET /api/staff/verifications/<id>/` (Business documents & owner info)
   - `POST /api/staff/verifications/<id>/approve/` (Approve property)
   - `POST /api/staff/verifications/<id>/reject/` (Reject with mandatory reason)
8. **Staff Notifications**:
   - `GET /api/staff/notifications/` (Department & personal alerts)
   - `POST /api/staff/notifications/<id>/read/` (Mark read)
   - `POST /api/staff/notifications/read-all/` (Mark all read)
9. **Staff Dashboard**:
   - `GET /api/staff/dashboard/` (Dynamic real-time stats scoped to department permissions)

---

## ⚡ 1-Click Automatic Cloud Sync (Direct to Postman)

Aapka Postman account API key ke through backend se directly connect ho chuka hai!

Jab bhi aap koi nayi API banayein ya update karein, to Postman mein manually import karne ki zaroorat nahi hai. Bas terminal mein yeh ek command run karein:

```bash
# Option 1: Via Django Management Command
python manage.py sync_postman

# Option 2: Via Standalone Script
python sync_postman.py
```

Yeh command automatically:
1. `GOONSTAY_COMPLETE_ALL_IN_ONE_POSTMAN_COLLECTION.json` ko padhega.
2. Postman Cloud Workspace par aapke collection `GoOnStay - Combined Master API Collection (All-In-One)` ko **live update** kar dega!
3. Aapke Postman app ya browser workspace par turant latest changes dikhne lagenge.

**Linked Workspace Link**: [Open Collection on Postman Web](https://go.postman.co/workspace/31aae728-f5ae-404e-88af-c23277f808b7/collection/59112441-0b1c41f1-53bd-4b50-9665-12e7ed7c971e)

---

## 🛠️ Postman Mein Kaise Import Karein (Offline / Manual Import)?

1. **Postman Open Karein**:
   - Top-left corner mein **Import** button par click karein.
2. **Files Select Karein**:
   - `postman_collections/01_GOONSTAY_COMPLETE_ALL_IN_ONE_POSTMAN_COLLECTION.json` drag & drop karein.
   - `postman_collections/04_GOONSTAY_POSTMAN_ENVIRONMENT.json` drag & drop karein.
3. **Environment Select Karein**:
   - Postman ke top-right corner dropdown mein se `GoOnStay - Local Development Environment` select karein.
4. **Token Kaise Set Karein**:
   - **Admin Ke Liye**: `01. Authentication` -> `Admin Login` run karein. Jo `access` token mile, use environment variable `admin_token` mein daal dein.
   - **Staff Ke Liye**: `13. Staff Management` -> `1. Staff Authentication` -> `Staff Login` run karein. Jo `access` token mile, use `staff_token` mein daal dein.
   - Saari requests mein authorization header automatically `Bearer {{admin_token}}` ya `Bearer {{staff_token}}` use karega!

---

## ✅ Verified & Tested
Saare endpoints Django isolated test database mein **20/20 unit tests PASS** hain.
Live database (`db.sqlite3`) puri tarah se safe aur unmodified hai.
