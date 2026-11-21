import datetime
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from hotels.models import Hotel, HotelImage, Amenity, HotelVerificationDocument, DeletedHotelArchive
from rooms.models import Room
from bookings.models import Booking
from staff.models import Department, StaffProfile, StaffPermission

User = get_user_model()


class DeletedHotelsArchiveTestCase(TestCase):
    """
    Comprehensive test suite verifying GoOnStay Deleted Hotel Archive and Strict Isolation:
    1. Admin & authorized staff can delete hotel (soft-delete & snapshot archive).
    2. Active reservation protection (blocks deletion if active reservations exist).
    3. Strict isolation: Deleted hotels NEVER appear anywhere except the dedicated Admin Deleted section.
    4. Only Admin can access the Admin Deleted Hotels section.
    5. Admin can view full snapshot and restore deleted hotel back to active state.
    """

    def setUp(self):
        self.client = APIClient()

        # 1. Users
        self.admin = User.objects.create_user(
            username='admin_test',
            email='admin@goonstay.com',
            password='AdminPassword123!',
            first_name='System',
            last_name='Admin',
            role=User.ROLE_ADMIN,
            is_staff=True
        )

        self.owner = User.objects.create_user(
            username='owner_test',
            email='owner@goonstay.com',
            password='OwnerPassword123!',
            first_name='Ramesh',
            last_name='Owner',
            role=User.ROLE_HOTEL_OWNER
        )

        self.customer = User.objects.create_user(
            username='cust_test',
            email='cust@goonstay.com',
            password='CustomerPassword123!',
            first_name='Ananya',
            last_name='Customer',
            role=User.ROLE_CUSTOMER
        )

        # 2. Staff: Hotel Verification Department
        self.dept_hotel, _ = Department.objects.get_or_create(
            code=Department.CODE_HOTEL_VERIFICATION,
            defaults={'name': 'Hotel Verification', 'is_active': True}
        )
        self.perm_verify, _ = StaffPermission.objects.get_or_create(
            code='VERIFY_HOTEL',
            defaults={'name': 'Verify Hotel', 'department': self.dept_hotel}
        )
        self.staff_hotel = User.objects.create_user(
            username='staff_hotel_test',
            email='staff_hotel@goonstay.com',
            password='StaffPassword123!',
            first_name='Staff',
            last_name='Verifier',
            role=User.ROLE_STAFF,
            is_staff=True
        )
        self.staff_profile = StaffProfile.objects.create(
            user=self.staff_hotel,
            employee_id='EMP-HOTEL01',
            login_id='gos_staff_hotel',
            department=self.dept_hotel,
            status='ACTIVE',
            must_change_password=False,
            created_by=self.admin
        )
        self.staff_profile.permissions.add(self.perm_verify)

        # Staff: Reservation Department
        self.dept_res, _ = Department.objects.get_or_create(
            code=Department.CODE_RESERVATION,
            defaults={'name': 'Reservation', 'is_active': True}
        )
        self.staff_res = User.objects.create_user(
            username='staff_res_test',
            email='staff_res@goonstay.com',
            password='StaffPassword123!',
            first_name='Staff',
            last_name='Reservation',
            role=User.ROLE_STAFF,
            is_staff=True
        )
        StaffProfile.objects.create(
            user=self.staff_res,
            employee_id='EMP-RES01',
            login_id='gos_staff_res',
            department=self.dept_res,
            status='ACTIVE',
            must_change_password=False,
            created_by=self.admin
        )

        # 3. Amenity
        self.amenity, _ = Amenity.objects.get_or_create(
            name='High-Speed WiFi',
            defaults={'category': 'CONNECTIVITY', 'icon_name': 'wifi'}
        )

        # 4. Hotels
        self.hotel_active = Hotel.objects.create(
            owner=self.owner,
            name='Royal Palace Hotel',
            description='Luxury heritage hotel in Jaipur.',
            property_type='HOTEL',
            address='10 Palace Road',
            city='Jaipur',
            state='Rajasthan',
            country='India',
            zip_code='302001',
            status=Hotel.STATUS_APPROVED,
            is_approved=True,
            is_active=True,
            is_deleted=False
        )
        self.hotel_active.amenities.add(self.amenity)

        # Rooms for hotel_active
        self.room_active = Room.objects.create(
            hotel=self.hotel_active,
            title='Royal Deluxe Room',
            room_type='DELUXE',
            price_per_night=Decimal('3500.00'),
            capacity_adults=2,
            capacity_children=1,
            total_rooms=5,
            room_numbers='101, 102, 103, 104, 105'
        )

        # Image for hotel_active
        HotelImage.objects.create(
            hotel=self.hotel_active,
            image_url='https://example.com/palace.jpg',
            caption='Front facade',
            is_primary=True
        )

        # Another hotel for verification tests
        self.hotel_to_delete = Hotel.objects.create(
            owner=self.owner,
            name='Sunset Resort Beachfront',
            description='Beachfront resort with sunset views in Goa.',
            property_type='RESORT',
            address='25 Baga Beach Road',
            city='Goa',
            state='Goa',
            country='India',
            zip_code='403516',
            status=Hotel.STATUS_APPROVED,
            is_approved=True,
            is_active=True,
            is_deleted=False
        )
        self.room_to_delete = Room.objects.create(
            hotel=self.hotel_to_delete,
            title='Beach Villa',
            room_type='SUITE',
            price_per_night=Decimal('6000.00'),
            capacity_adults=4,
            capacity_children=2,
            total_rooms=3,
            room_numbers='201, 202, 203'
        )

    # =========================================================================
    # TEST 1: Admin can delete hotel and it is archived
    # =========================================================================
    def test_01_admin_can_delete_hotel_and_it_is_archived(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.delete(f'/api/hotels/{self.hotel_active.id}/', {
            'reason': 'Property requested delisting by management'
        }, format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data.get('success'))

        # Check hotel DB fields
        self.hotel_active.refresh_from_db()
        self.assertTrue(self.hotel_active.is_deleted)
        self.assertEqual(self.hotel_active.status, Hotel.STATUS_DELETED)
        self.assertFalse(self.hotel_active.is_active)
        self.assertFalse(self.hotel_active.is_approved)
        self.assertIsNotNone(self.hotel_active.deleted_at)
        self.assertEqual(self.hotel_active.deleted_by, self.admin)

        # Archive record must exist
        archive = DeletedHotelArchive.objects.filter(hotel=self.hotel_active).first()
        self.assertIsNotNone(archive)
        self.assertEqual(archive.hotel_name, 'Royal Palace Hotel')
        self.assertEqual(archive.deleted_by, self.admin)
        self.assertEqual(archive.deleted_by_role, 'ADMIN')
        self.assertEqual(archive.deletion_reason, 'Property requested delisting by management')
        self.assertFalse(archive.is_restored)

        # Snapshot data must be complete
        snapshot = archive.snapshot_data
        self.assertEqual(snapshot.get('name'), 'Royal Palace Hotel')
        self.assertEqual(snapshot.get('city'), 'Jaipur')
        self.assertEqual(len(snapshot.get('rooms', [])), 1)
        self.assertEqual(len(snapshot.get('images', [])), 1)

    # =========================================================================
    # TEST 2: Hotel Verification Staff can delete hotel and it is archived
    # =========================================================================
    def test_02_verification_staff_can_delete_hotel_and_it_is_archived(self):
        self.client.force_authenticate(user=self.staff_hotel)
        res = self.client.delete(f'/api/staff/verifications/{self.hotel_to_delete.id}/', {
            'reason': 'Failed property audit verification'
        }, format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data.get('success'))

        self.hotel_to_delete.refresh_from_db()
        self.assertTrue(self.hotel_to_delete.is_deleted)
        self.assertEqual(self.hotel_to_delete.status, Hotel.STATUS_DELETED)
        self.assertEqual(self.hotel_to_delete.deleted_by, self.staff_hotel)

        archive = DeletedHotelArchive.objects.filter(hotel=self.hotel_to_delete).first()
        self.assertIsNotNone(archive)
        self.assertEqual(archive.deleted_by, self.staff_hotel)
        self.assertEqual(archive.deleted_by_role, 'STAFF')

    # =========================================================================
    # TEST 3: Deletion rejected if hotel has active upcoming reservations
    # =========================================================================
    def test_03_delete_rejected_if_hotel_has_active_upcoming_reservations(self):
        # Create an active upcoming reservation
        Booking.objects.create(
            booking_id='GOS-BK-TEST-ACT',
            hotel=self.hotel_active,
            room=self.room_active,
            customer=self.customer,
            check_in=timezone.now().date(),
            check_out=timezone.now().date() + datetime.timedelta(days=3),
            guest_name='Test Guest',
            guest_email='guest@test.com',
            guest_phone='9876543210',
            price_per_night=Decimal('3500.00'),
            subtotal=Decimal('10500.00'),
            total_amount=Decimal('10500.00'),
            booking_status=Booking.STATUS_CONFIRMED,
            payment_status='PAID'
        )

        self.client.force_authenticate(user=self.admin)
        res = self.client.delete(f'/api/hotels/{self.hotel_active.id}/')

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Cannot delete hotel with active upcoming reservations', res.data.get('error', ''))

        # Hotel remains untouched
        self.hotel_active.refresh_from_db()
        self.assertFalse(self.hotel_active.is_deleted)
        self.assertTrue(self.hotel_active.is_active)

    # =========================================================================
    # TEST 4: Deleted hotel is strictly excluded from public listings
    # =========================================================================
    def test_04_deleted_hotel_strictly_excluded_from_public_listings(self):
        # Delete hotel_active
        self.hotel_active.is_deleted = True
        self.hotel_active.status = Hotel.STATUS_DELETED
        self.hotel_active.save()

        # Anonymous public user fetches hotel list
        self.client.force_authenticate(user=None)
        res = self.client.get('/api/hotels/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        results = res.data.get('results', [])
        hotel_ids = [h['id'] for h in results]
        self.assertNotIn(self.hotel_active.id, hotel_ids)
        self.assertIn(self.hotel_to_delete.id, hotel_ids)

    # =========================================================================
    # TEST 5: Deleted hotel is strictly excluded from search
    # =========================================================================
    def test_05_deleted_hotel_strictly_excluded_from_search(self):
        self.hotel_active.is_deleted = True
        self.hotel_active.status = Hotel.STATUS_DELETED
        self.hotel_active.save()

        res = self.client.get('/api/hotels/search/?city=Jaipur')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get('results', [])
        hotel_ids = [h['id'] for h in results]
        self.assertNotIn(self.hotel_active.id, hotel_ids)

    # =========================================================================
    # TEST 6: Deleted hotel returns 404 on direct detail API
    # =========================================================================
    def test_06_deleted_hotel_returns_404_on_direct_detail_api(self):
        self.hotel_active.is_deleted = True
        self.hotel_active.status = Hotel.STATUS_DELETED
        self.hotel_active.save()

        res = self.client.get(f'/api/hotels/{self.hotel_active.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    # =========================================================================
    # TEST 7: Deleted hotel is strictly excluded from Hotel Owner portal
    # =========================================================================
    def test_07_deleted_hotel_strictly_excluded_from_hotel_owner_portal(self):
        self.hotel_active.is_deleted = True
        self.hotel_active.status = Hotel.STATUS_DELETED
        self.hotel_active.save()

        self.client.force_authenticate(user=self.owner)
        res = self.client.get('/api/hotels/my-hotels/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        hotel_ids = [h['id'] for h in res.data.get('results', [])]
        self.assertNotIn(self.hotel_active.id, hotel_ids)
        self.assertIn(self.hotel_to_delete.id, hotel_ids)

        # Dashboard excludes deleted hotel
        res_dash = self.client.get('/api/hotels/dashboard/')
        self.assertEqual(res_dash.status_code, status.HTTP_200_OK)
        stats_hotels = res_dash.data.get('statistics', {}).get('hotels', {})
        self.assertEqual(stats_hotels.get('total'), 1)  # Only hotel_to_delete

    # =========================================================================
    # TEST 8: Deleted hotel is strictly excluded from normal Admin hotel list
    # =========================================================================
    def test_08_deleted_hotel_strictly_excluded_from_normal_admin_hotel_list(self):
        self.hotel_active.is_deleted = True
        self.hotel_active.status = Hotel.STATUS_DELETED
        self.hotel_active.save()

        self.client.force_authenticate(user=self.admin)
        res = self.client.get('/api/hotels/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        hotel_ids = [h['id'] for h in res.data.get('results', [])]
        self.assertNotIn(self.hotel_active.id, hotel_ids)

    # =========================================================================
    # TEST 9: Deleted hotel is strictly excluded from Staff verification list
    # =========================================================================
    def test_09_deleted_hotel_strictly_excluded_from_staff_verification_list(self):
        self.hotel_to_delete.status = Hotel.STATUS_SUBMITTED
        self.hotel_to_delete.is_deleted = True
        self.hotel_to_delete.save()

        self.client.force_authenticate(user=self.staff_hotel)
        res = self.client.get('/api/staff/verifications/?status=SUBMITTED')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        verif_ids = [v['id'] for v in res.data.get('verifications', [])]
        self.assertNotIn(self.hotel_to_delete.id, verif_ids)

    # =========================================================================
    # TEST 10: Deleted hotel rooms cannot be retrieved or booked
    # =========================================================================
    def test_10_deleted_hotel_rooms_cannot_be_retrieved_or_booked(self):
        self.hotel_active.is_deleted = True
        self.hotel_active.status = Hotel.STATUS_DELETED
        self.hotel_active.save()

        # RoomsByHotel returns empty
        res_rooms = self.client.get(f'/api/rooms/hotel/{self.hotel_active.id}/')
        self.assertEqual(res_rooms.status_code, status.HTTP_200_OK)
        rooms_list = res_rooms.data.get('results') if isinstance(res_rooms.data, dict) else res_rooms.data
        self.assertEqual(len(rooms_list), 0)

        # Booking attempt fails
        self.client.force_authenticate(user=self.customer)
        res_book = self.client.post('/api/bookings/', {
            'hotel': self.hotel_active.id,
            'room': self.room_active.id,
            'check_in': (timezone.now().date() + datetime.timedelta(days=5)).isoformat(),
            'check_out': (timezone.now().date() + datetime.timedelta(days=7)).isoformat(),
            'guest_name': 'Test Customer',
            'guest_email': 'cust@goonstay.com',
            'guest_phone': '9876543210',
            'number_of_rooms': 1
        })
        self.assertEqual(res_book.status_code, status.HTTP_400_BAD_REQUEST)

    # =========================================================================
    # TEST 11: Admin can view Deleted Hotels Archive list
    # =========================================================================
    def test_11_admin_can_view_deleted_hotels_archive_list(self):
        # Soft-delete hotel_active via Admin
        self.client.force_authenticate(user=self.admin)
        self.client.delete(f'/api/hotels/{self.hotel_active.id}/', {'reason': 'Delisted'}, format='json')

        # Admin calls deleted hotels archive endpoint
        res = self.client.get('/api/admin/deleted-hotels/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        results = res.data.get('results', [])
        self.assertGreaterEqual(len(results), 1)
        del_item = next((item for item in results if item['hotel_id'] == self.hotel_active.id), None)
        self.assertIsNotNone(del_item)
        self.assertEqual(del_item['hotel_name'], 'Royal Palace Hotel')
        self.assertEqual(del_item['city'], 'Jaipur')
        self.assertEqual(del_item['deleted_by_role'], 'ADMIN')
        self.assertEqual(del_item['rooms_count'], 1)
        self.assertEqual(del_item['images_count'], 1)

    # =========================================================================
    # TEST 12: Admin can view full Deleted Hotel details and snapshot
    # =========================================================================
    def test_12_admin_can_view_deleted_hotel_details_and_snapshot(self):
        self.client.force_authenticate(user=self.admin)
        self.client.delete(f'/api/hotels/{self.hotel_active.id}/', {'reason': 'Audit review'}, format='json')

        archive = DeletedHotelArchive.objects.get(hotel=self.hotel_active)
        res = self.client.get(f'/api/admin/deleted-hotels/{archive.id}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        arch_data = res.data.get('archive', {})
        self.assertEqual(arch_data.get('hotel_name'), 'Royal Palace Hotel')
        self.assertEqual(arch_data.get('deletion_reason'), 'Audit review')
        snapshot = arch_data.get('snapshot_data', {})
        self.assertEqual(snapshot.get('name'), 'Royal Palace Hotel')
        self.assertIn('rooms', snapshot)
        self.assertIn('images', snapshot)
        self.assertIn('amenities', snapshot)

    # =========================================================================
    # TEST 13: Non-Admin users are strictly denied from Deleted Hotels Archive
    # =========================================================================
    def test_13_non_admin_denied_from_deleted_hotels_archive(self):
        # 1. Customer denied
        self.client.force_authenticate(user=self.customer)
        res_cust = self.client.get('/api/admin/deleted-hotels/')
        self.assertEqual(res_cust.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Hotel Owner denied
        self.client.force_authenticate(user=self.owner)
        res_owner = self.client.get('/api/admin/deleted-hotels/')
        self.assertEqual(res_owner.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Reservation staff denied
        self.client.force_authenticate(user=self.staff_res)
        res_res = self.client.get('/api/admin/deleted-hotels/')
        self.assertEqual(res_res.status_code, status.HTTP_403_FORBIDDEN)

        # 4. Hotel Verification staff denied from admin archive
        self.client.force_authenticate(user=self.staff_hotel)
        res_verif = self.client.get('/api/admin/deleted-hotels/')
        self.assertEqual(res_verif.status_code, status.HTTP_403_FORBIDDEN)

    # =========================================================================
    # TEST 14: Admin can restore a deleted hotel back to active state
    # =========================================================================
    def test_14_admin_can_restore_deleted_hotel(self):
        # Delete first
        self.client.force_authenticate(user=self.admin)
        self.client.delete(f'/api/hotels/{self.hotel_active.id}/', {'reason': 'Temporary hold'}, format='json')

        archive = DeletedHotelArchive.objects.get(hotel=self.hotel_active)
        self.assertFalse(archive.is_restored)

        # Admin restores hotel
        res_restore = self.client.post(f'/api/admin/deleted-hotels/{archive.id}/restore/')
        self.assertEqual(res_restore.status_code, status.HTTP_200_OK)
        self.assertTrue(res_restore.data.get('success'))

        # Verify hotel in DB is restored
        self.hotel_active.refresh_from_db()
        self.assertFalse(self.hotel_active.is_deleted)
        self.assertEqual(self.hotel_active.status, Hotel.STATUS_APPROVED)
        self.assertTrue(self.hotel_active.is_active)
        self.assertTrue(self.hotel_active.is_approved)
        self.assertIsNone(self.hotel_active.deleted_at)

        # Archive marked restored
        archive.refresh_from_db()
        self.assertTrue(archive.is_restored)
        self.assertIsNotNone(archive.restored_at)
        self.assertEqual(archive.restored_by, self.admin)

        # Hotel reappears in public listing
        self.client.force_authenticate(user=None)
        res_public = self.client.get('/api/hotels/')
        hotel_ids = [h['id'] for h in res_public.data.get('results', [])]
        self.assertIn(self.hotel_active.id, hotel_ids)
