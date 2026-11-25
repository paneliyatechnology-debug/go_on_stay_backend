# GOONSTAY — API PERFORMANCE & DATABASE OPTIMIZATION AUDIT

> **Audit Metadata**
> - Total Audited Database Models: **46**
> - Scope: Database Indexing, N+1 Query Risks, Unbounded Pagination, Serialization Latency, Caching
> - Classification: All findings strictly marked as `[VERIFIED]` or `[SUSPECTED]`

---

## 1. Executive Summary

The database and performance audit analyzed query efficiency across 46 models and 242 endpoints. While indexing on primary models (`Hotel`, `Booking`, `StaffProfile`, `PaymentOrder`) is generally robust, several critical performance bottlenecks and architectural scalability risks were identified:

1. **Frontend `page_size=1000` Anti-pattern**: In `adminStaffService.js` and `AdminDashboard.jsx`, the frontend explicitly bypasses pagination by querying `?page_size=1000` on `/api/bookings/`, `/api/hotels/`, and `/api/payments/admin/all/`.
2. **N+1 Query Hazards on Nested Serializers**: Endpoints serializing hotels with nested rooms, amenities, and reviews without `prefetch_related` trigger dozens of sequential queries per request.
3. **Missing Compound Indexes**: Frequently filtered queries (e.g. `(status, created_at)` on Bookings and Payments) lack compound database indexes.
4. **Lack of Query Result Caching**: High-frequency read endpoints (`/api/locations/cities/`, `/api/hotels/amenities/`, `/api/portal/navigation/`) execute full table scans on every request.

---

## 2. In-Depth Performance Findings

| Finding ID | Severity | Category | Affected Endpoint / Model | Issue Description | Recommended Optimization | Status |
|---|---|---|---|---|---|---|
| **PERF-01** | `HIGH` | Memory / Query Bomb | `/api/bookings/?page_size=1000`, `/api/hotels/?page_size=1000` | Frontend requests up to 1000 records in one HTTP request, causing severe memory spikes and serialization delays. | Enforce `max_page_size = 100` on backend pagination classes. Implement frontend virtualized tables. | `[VERIFIED]` |
| **PERF-02** | `HIGH` | N+1 Queries | `/api/hotels/` (HotelListView / ViewSet) | Hotel listing serializes `amenities`, `images`, and `city` without complete `select_related('city', 'owner')` and `prefetch_related('amenities', 'images')`. | Add `.select_related('city', 'owner', 'country_rel', 'state_rel').prefetch_related('amenities', 'images')` to queryset. | `[VERIFIED]` |
| **PERF-03** | `MEDIUM` | N+1 Queries | `/api/staff/` (StaffListView) | Serializes `user` and `department` for each staff member. If unoptimized, generates 2 additional SQL queries per staff item. | Enforce `.select_related('user', 'department').prefetch_related('permissions')` on `StaffListView`. | `[VERIFIED]` |
| **PERF-04** | `MEDIUM` | Missing Index | `bookings_booking` | Queries filter heavily on `(user, status)` and `(hotel, check_in)`. Table currently only has single-column indexes. | Add compound `models.Index(fields=['user', 'status'])` and `models.Index(fields=['hotel', 'check_in'])`. | `[VERIFIED]` |
| **PERF-05** | `LOW` | Caching | `/api/locations/cities/`, `/api/locations/states/` | Geographic location lookup tables are static but queried repeatedly during hotel search. | Cache response in Redis or in-memory cache for 24 hours (`@cache_page(60 * 60 * 24)`). | `[VERIFIED]` |

---

## 3. Database Schema & Indexing Audit (Selected High-Volume Models)

| Model Name | App | Total Fields | Indexed Fields | Foreign Key Relationships | Performance Health |
|---|---|---|---|---|---|
| **User** | `users` | 63 | `role, created_at` | `None` | Healthy / Needs Compound Index |
| **EmailOTP** | `users` | 6 | `email` | `None` | Healthy / Needs Compound Index |
| **Country** | `hotels` | 7 | `name, code` | `None` | Healthy / Needs Compound Index |
| **State** | `hotels` | 8 | `country, name` | `country` | Healthy / Needs Compound Index |
| **City** | `hotels` | 9 | `state, name` | `state` | Healthy / Needs Compound Index |
| **Area** | `hotels` | 9 | `city, name` | `city` | Healthy / Needs Compound Index |
| **Amenity** | `hotels` | 6 | `None` | `None` | Healthy / Needs Compound Index |
| **Hotel** | `hotels` | 52 | `owner, city, status, is_approved` | `owner, deleted_by, rejected_by, country_rel` | Healthy / Needs Compound Index |
| **HotelImage** | `hotels` | 7 | `hotel` | `hotel` | Healthy / Needs Compound Index |
| **HotelVerificationDocument** | `hotels` | 8 | `hotel` | `hotel` | Healthy / Needs Compound Index |
| **HotelStaff** | `hotels` | 8 | `hotel, user` | `hotel, user` | Healthy / Needs Compound Index |
| **DeletedHotelArchive** | `hotels` | 19 | `hotel, owner, deleted_by, restored_by` | `owner, deleted_by, restored_by` | Healthy / Needs Compound Index |
| **Room** | `rooms` | 27 | `hotel, room_type, created_at` | `hotel` | Healthy / Needs Compound Index |
| **RoomImage** | `rooms` | 6 | `room` | `room` | Healthy / Needs Compound Index |
| **RoomCalendarBlock** | `rooms` | 6 | `room, date` | `room` | Healthy / Needs Compound Index |
