"""
Automated Test Suite: GoOnStay Cloudinary Direct Image Upload Integration.
Tests signed direct upload authorization, backend-controlled folder taxonomy,
reused save APIs, zero secret exposure, and local media compatibility.
Uses strictly isolated Django test database (destroyed automatically after tests).
"""

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from hotels.models import Hotel, HotelImage
from rooms.models import Room, RoomImage
from services.cloudinary_service import (
    generate_cloudinary_signature,
    validate_cloudinary_url,
    CLOUDINARY_FOLDERS,
    BLOCKED_DOCUMENT_CATEGORIES
)

User = get_user_model()

TEST_CLOUDINARY_SECRET = "test_cloudinary_secret_key_abcdef123456"


@override_settings(
    CLOUDINARY_CLOUD_NAME="bzb1bndw",
    CLOUDINARY_API_KEY="894358896518227",
    CLOUDINARY_API_SECRET=TEST_CLOUDINARY_SECRET
)
class CloudinaryDirectUploadTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # 1. Admin User
        self.admin = User.objects.create_user(
            username='admin_cloud',
            email='admin_cloud@goonstay.com',
            password='Password123!',
            role='ADMIN',
            is_staff=True,
            is_superuser=True
        )

        # 2. Hotel Owner 1 (owns Hotel 1)
        self.owner1 = User.objects.create_user(
            username='owner1_cloud',
            email='owner1_cloud@goonstay.com',
            password='Password123!',
            role='HOTEL_OWNER'
        )

        # 3. Hotel Owner 2 (owns Hotel 2)
        self.owner2 = User.objects.create_user(
            username='owner2_cloud',
            email='owner2_cloud@goonstay.com',
            password='Password123!',
            role='HOTEL_OWNER'
        )

        # 4. Customer User
        self.customer = User.objects.create_user(
            username='customer_cloud',
            email='customer_cloud@goonstay.com',
            password='Password123!',
            role='CUSTOMER'
        )

        # 5. Hotel 1 (owned by owner1)
        self.hotel1 = Hotel.objects.create(
            name="Cloudinary Grand Resort",
            owner=self.owner1,
            city="Goa",
            state="Goa",
            status=Hotel.STATUS_APPROVED,
            is_approved=True
        )

        # 6. Room 1 (under Hotel 1)
        self.room1 = Room.objects.create(
            hotel=self.hotel1,
            title="Deluxe Ocean Suite",
            room_type='DELUXE',
            price_per_night=4500.00,
            capacity_adults=2
        )

        # 7. Hotel 2 (owned by owner2)
        self.hotel2 = Hotel.objects.create(
            name="Cloudinary Mountain Retreat",
            owner=self.owner2,
            city="Manali",
            state="Himachal Pradesh",
            status=Hotel.STATUS_APPROVED,
            is_approved=True
        )

    # =========================================================================
    # 1. SIGNATURE GENERATION & FOLDER TAXONOMY
    # =========================================================================

    def test_signature_endpoint_requires_authentication(self):
        """Unauthenticated client cannot generate upload signatures."""
        res = self.client.post('/api/cloudinary/signature/', {'category': 'hotels'})
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_owner_can_generate_signature_for_own_hotel(self):
        """Hotel owner can request upload signature for their own hotel."""
        self.client.force_authenticate(user=self.owner1)
        res = self.client.post('/api/cloudinary/signature/', {
            'category': 'hotels',
            'target_id': self.hotel1.id
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['success'])
        self.assertEqual(res.data['folder'], 'goonstay/hotels')
        self.assertEqual(res.data['cloud_name'], 'bzb1bndw')
        self.assertEqual(res.data['api_key'], '894358896518227')
        self.assertIn('signature', res.data)
        self.assertIn('timestamp', res.data)
        self.assertIn('https://api.cloudinary.com/v1_1/bzb1bndw/image/upload', res.data['upload_url'])

        # Critical Security Check: API Secret must NEVER be present in response
        self.assertNotIn('api_secret', res.data)
        self.assertNotIn(TEST_CLOUDINARY_SECRET, str(res.data))

    def test_owner_cannot_generate_signature_for_another_owners_hotel(self):
        """Owner 2 cannot generate upload signature for Hotel 1 (owned by Owner 1)."""
        self.client.force_authenticate(user=self.owner2)
        res = self.client.post('/api/cloudinary/signature/', {
            'category': 'hotels',
            'target_id': self.hotel1.id
        })
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('do not own', res.data['error'].lower())

    def test_customer_cannot_generate_signature_for_hotels_or_rooms(self):
        """Regular customer is forbidden from requesting hotel or room image signatures."""
        self.client.force_authenticate(user=self.customer)
        res_hotel = self.client.post('/api/cloudinary/signature/', {'category': 'hotels'})
        self.assertEqual(res_hotel.status_code, status.HTTP_403_FORBIDDEN)

        res_room = self.client.post('/api/cloudinary/signature/', {'category': 'rooms'})
        self.assertEqual(res_room.status_code, status.HTTP_403_FORBIDDEN)

    def test_customer_can_generate_signature_for_profile_picture(self):
        """Customer can request upload signature for their own profile picture in goonstay/profiles."""
        self.client.force_authenticate(user=self.customer)
        res = self.client.post('/api/cloudinary/signature/', {'category': 'profiles'})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['success'])
        self.assertEqual(res.data['folder'], 'goonstay/profiles')

    def test_owner_can_generate_signature_for_owner_profile(self):
        """Hotel owner can request upload signature for goonstay/owners."""
        self.client.force_authenticate(user=self.owner1)
        res = self.client.post('/api/cloudinary/signature/', {'category': 'owners'})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['folder'], 'goonstay/owners')

    def test_admin_can_generate_signature_for_general_assets(self):
        """Admin can request upload signature for goonstay/general."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.post('/api/cloudinary/signature/', {'category': 'general'})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['folder'], 'goonstay/general')

    def test_blocked_private_documents_cannot_use_public_cloudinary(self):
        """Attempting to request signature for sensitive verification documents is rejected."""
        self.client.force_authenticate(user=self.owner1)
        for doc_cat in ['documents', 'verification', 'id_proof', 'tax_gst']:
            res = self.client.post('/api/cloudinary/signature/', {'category': doc_cat})
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('verification documents', res.data['error'].lower())

    # =========================================================================
    # 2. REUSING EXISTING DJANGO SAVE APIS
    # =========================================================================

    def test_save_hotel_cloudinary_image_reference(self):
        """Save a Cloudinary secure URL reference to an existing hotel."""
        self.client.force_authenticate(user=self.owner1)
        cloud_url = "https://res.cloudinary.com/bzb1bndw/image/upload/v1732200000/goonstay/hotels/hotel_resort_front.jpg"
        res = self.client.post(f'/api/hotels/{self.hotel1.id}/upload-image/', {
            'image_url': cloud_url,
            'is_primary': True,
            'caption': 'Grand Front Entrance'
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['image_url'], cloud_url)
        self.assertEqual(res.data['display_url'], cloud_url)
        self.assertTrue(res.data['is_primary'])

        # Verify database record
        img = HotelImage.objects.get(id=res.data['id'])
        self.assertEqual(img.image_url, cloud_url)
        self.assertEqual(img.get_image_display(), cloud_url)

    def test_save_room_cloudinary_image_reference(self):
        """Save a Cloudinary secure URL reference to an existing room."""
        self.client.force_authenticate(user=self.owner1)
        cloud_url = "https://res.cloudinary.com/bzb1bndw/image/upload/v1732200000/goonstay/rooms/deluxe_suite_bedroom.jpg"
        res = self.client.post(f'/api/rooms/{self.room1.id}/upload-image/', {
            'image_url': cloud_url,
            'is_primary': True
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['image_url'], cloud_url)
        self.assertEqual(res.data['display_url'], cloud_url)

        # Verify database record
        rimg = RoomImage.objects.get(id=res.data['id'])
        self.assertEqual(rimg.image_url, cloud_url)
        self.assertEqual(rimg.get_image_display(), cloud_url)

    def test_save_customer_profile_picture_avatar(self):
        """Save a Cloudinary secure URL as user profile picture."""
        self.client.force_authenticate(user=self.customer)
        cloud_url = "https://res.cloudinary.com/bzb1bndw/image/upload/v1732200000/goonstay/profiles/customer_avatar_12.jpg"
        res = self.client.patch('/api/users/profile/', {
            'avatar': cloud_url
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['avatar'], cloud_url)

        # Verify user model
        self.customer.refresh_from_db()
        self.assertEqual(str(self.customer.avatar), cloud_url)

    def test_save_owner_profile_picture_avatar(self):
        """Save a Cloudinary secure URL as hotel owner profile picture."""
        self.client.force_authenticate(user=self.owner1)
        cloud_url = "https://res.cloudinary.com/bzb1bndw/image/upload/v1732200000/goonstay/owners/owner_portrait.jpg"
        res = self.client.patch('/api/users/profile/', {
            'avatar_url': cloud_url
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['avatar'], cloud_url)

    # =========================================================================
    # 3. EXISTING LOCAL MEDIA COMPATIBILITY
    # =========================================================================

    def test_existing_local_media_images_display_correctly(self):
        """Existing local media images continue working with /media/ prefix."""
        # Create hotel image with local path
        local_himg = HotelImage.objects.create(
            hotel=self.hotel1,
            image='hotels/images/legacy_hotel.jpg',
            is_primary=False
        )
        self.assertEqual(local_himg.get_image_display(), '/media/hotels/images/legacy_hotel.jpg')

        # Create room image with local path
        local_rimg = RoomImage.objects.create(
            room=self.room1,
            image='rooms/images/legacy_room.jpg',
            is_primary=False
        )
        self.assertEqual(local_rimg.get_image_display(), '/media/rooms/images/legacy_room.jpg')

        # User with local avatar path
        self.customer.avatar = 'users/avatars/legacy_avatar.png'
        self.customer.save()
        self.client.force_authenticate(user=self.customer)
        res = self.client.get('/api/users/me/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('/media/users/avatars/legacy_avatar.png', res.data['avatar'])

    # =========================================================================
    # 4. ADDITIONAL EDGE CASES & CONFIG CHECKS
    # =========================================================================

    def test_cloudinary_status_endpoint(self):
        """Public status check returns configuration status without credentials."""
        res = self.client.get('/api/cloudinary/status/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['configured'])
        self.assertEqual(res.data['cloud_name'], 'bzb1bndw')
        self.assertIn('hotels', res.data['supported_categories'])
        self.assertNotIn('api_secret', res.data)

    def test_primary_image_replacement_for_hotel(self):
        """When a new primary image is saved, old primary image is unset."""
        self.client.force_authenticate(user=self.owner1)
        # 1st image as primary
        res1 = self.client.post(f'/api/hotels/{self.hotel1.id}/upload-image/', {
            'image_url': 'https://res.cloudinary.com/bzb1bndw/image/upload/v1/goonstay/hotels/img1.jpg',
            'is_primary': True
        })
        img1_id = res1.data['id']
        self.assertTrue(HotelImage.objects.get(id=img1_id).is_primary)

        # 2nd image as new primary
        res2 = self.client.post(f'/api/hotels/{self.hotel1.id}/upload-image/', {
            'image_url': 'https://res.cloudinary.com/bzb1bndw/image/upload/v1/goonstay/hotels/img2.jpg',
            'is_primary': True
        })
        img2_id = res2.data['id']
        self.assertTrue(HotelImage.objects.get(id=img2_id).is_primary)

        # Old image must now have is_primary=False
        self.assertFalse(HotelImage.objects.get(id=img1_id).is_primary)

    def test_invalid_target_id_validation(self):
        """Passing non-existent target_id for hotel returns validation error."""
        self.client.force_authenticate(user=self.owner1)
        res = self.client.post('/api/cloudinary/signature/', {
            'category': 'hotels',
            'target_id': 999999
        })
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('not found', res.data['error'].lower())

    def test_missing_category_returns_400(self):
        """Omitting category returns 400 Bad Request."""
        self.client.force_authenticate(user=self.owner1)
        res = self.client.post('/api/cloudinary/signature/', {})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('required', res.data['error'].lower())

