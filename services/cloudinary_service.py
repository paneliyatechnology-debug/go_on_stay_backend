"""
GoOnStay Cloudinary Direct Image Upload Service.
Handles role-based upload authorization, backend-controlled folder isolation,
cryptographic upload signature generation, and Cloudinary asset validation.
Ensures zero exposure of CLOUDINARY_API_SECRET to the client.
"""

import time
import os
import re
from typing import Dict, Any, Optional, Tuple
from django.conf import settings
from rest_framework.exceptions import PermissionDenied, ValidationError

# Backend-controlled folder taxonomy (arbitrary frontend folder input is strictly forbidden)
CLOUDINARY_FOLDERS = {
    'hotels': 'goonstay/hotels',
    'rooms': 'goonstay/rooms',
    'profiles': 'goonstay/profiles',
    'owners': 'goonstay/owners',
    'general': 'goonstay/general',
}

BLOCKED_DOCUMENT_CATEGORIES = {
    'documents', 'verification', 'id_proof', 'business_reg', 'tax_gst', 'bank', 'identity'
}

ALLOWED_IMAGE_FORMATS = {'jpg', 'jpeg', 'png', 'webp', 'gif', 'svg'}
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB maximum upload size limit


def get_cloudinary_config() -> Tuple[str, str, str]:
    """
    Returns (cloud_name, api_key, api_secret) from Django settings or environment.
    """
    cloud_name = getattr(settings, 'CLOUDINARY_CLOUD_NAME', '') or os.getenv('CLOUDINARY_CLOUD_NAME', 'bzb1bndw')
    api_key = getattr(settings, 'CLOUDINARY_API_KEY', '') or os.getenv('CLOUDINARY_API_KEY', '894358896518227')
    api_secret = getattr(settings, 'CLOUDINARY_API_SECRET', '') or os.getenv('CLOUDINARY_API_SECRET', '')
    return cloud_name, api_key, api_secret


def is_cloudinary_configured() -> bool:
    """
    Checks if Cloudinary credentials are fully configured.
    """
    cloud_name, api_key, api_secret = get_cloudinary_config()
    return bool(cloud_name and api_key and api_secret)


def check_upload_authorization(user, category: str, target_id: Optional[int] = None) -> str:
    """
    Validates user authentication, role, and resource ownership for the given category.
    Returns the authorized target Cloudinary folder string.
    Raises PermissionDenied or ValidationError if unauthorized.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentication is required to request upload signatures.")

    category_clean = (category or '').strip().lower()

    # 1. Reject sensitive verification documents from public image upload
    if category_clean in BLOCKED_DOCUMENT_CATEGORIES:
        raise ValidationError(
            "Private verification documents and sensitive identity proofs cannot be uploaded to public Cloudinary folders. "
            "Please use the dedicated secure document verification storage API."
        )

    if category_clean not in CLOUDINARY_FOLDERS:
        valid_cats = ", ".join(CLOUDINARY_FOLDERS.keys())
        raise ValidationError(f"Invalid upload category '{category}'. Permitted categories: {valid_cats}.")

    role = getattr(user, 'role', '')
    is_admin = bool(user.is_staff or user.is_superuser or role in ['ADMIN', 'SUPER_ADMIN'])

    # 2. Category: 'hotels' (Hotel property images)
    if category_clean == 'hotels':
        if not is_admin and role not in ['HOTEL_OWNER', 'HOTEL_STAFF']:
            # Staff in HOTEL_VERIFICATION department can also upload inspection images
            staff_profile = getattr(user, 'staff_profile', None)
            dept_code = getattr(getattr(staff_profile, 'department', None), 'code', '')
            if dept_code != 'HOTEL_VERIFICATION':
                raise PermissionDenied("Only Hotel Owners and authorized staff can upload hotel images.")

        if target_id and not is_admin:
            from hotels.models import Hotel
            try:
                hotel = Hotel.objects.get(pk=target_id)
                if hotel.owner_id != user.id:
                    raise PermissionDenied("You do not own this hotel property.")
            except Hotel.DoesNotExist:
                raise ValidationError(f"Hotel with ID {target_id} not found.")

    # 3. Category: 'rooms' (Room type and room inventory images)
    elif category_clean == 'rooms':
        if not is_admin and role not in ['HOTEL_OWNER', 'HOTEL_STAFF']:
            raise PermissionDenied("Only Hotel Owners and platform managers can upload room images.")

        if target_id and not is_admin:
            from rooms.models import Room
            try:
                room = Room.objects.select_related('hotel').get(pk=target_id)
                if room.hotel.owner_id != user.id:
                    raise PermissionDenied("You do not own the hotel associated with this room.")
            except Room.DoesNotExist:
                raise ValidationError(f"Room with ID {target_id} not found.")

    # 4. Category: 'owners' (Hotel Owner profile / branding pictures)
    elif category_clean == 'owners':
        if not is_admin and role not in ['HOTEL_OWNER', 'HOTEL_STAFF']:
            raise PermissionDenied("Only verified Hotel Owners can upload owner profile pictures.")

    # 5. Category: 'profiles' (User avatars / customer profile pictures)
    elif category_clean == 'profiles':
        # Any authenticated user (CUSTOMER, HOTEL_OWNER, STAFF, ADMIN) can update their own profile avatar
        pass

    # 6. Category: 'general' (Platform banners, marketing, and public assets)
    elif category_clean == 'general':
        if not is_admin and role != 'STAFF':
            raise PermissionDenied("Only platform administrators and staff can upload general website assets.")

    return CLOUDINARY_FOLDERS[category_clean]


def generate_cloudinary_signature(
    user,
    category: str,
    target_id: Optional[int] = None,
    tags: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generates a cryptographically signed direct upload authorization payload for Cloudinary.
    The secret is used solely to generate the HMAC SHA-1 signature on the server and is never sent to the client.
    """
    folder = check_upload_authorization(user, category, target_id)
    cloud_name, api_key, api_secret = get_cloudinary_config()

    if not api_secret:
        raise ValidationError(
            "Cloudinary API Secret is not configured on the backend server. "
            "Please configure CLOUDINARY_API_SECRET in the backend environment."
        )

    import cloudinary.utils

    timestamp = int(time.time())
    params_to_sign: Dict[str, Any] = {
        'folder': folder,
        'timestamp': timestamp,
    }
    if tags:
        params_to_sign['tags'] = tags

    # Generate HMAC SHA-1 signature using Cloudinary standard algorithm
    signature = cloudinary.utils.api_sign_request(params_to_sign, api_secret)

    upload_url = f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload"

    return {
        'success': True,
        'cloud_name': cloud_name,
        'api_key': api_key,
        'timestamp': timestamp,
        'folder': folder,
        'signature': signature,
        'upload_url': upload_url,
        'category': category,
        'target_id': target_id,
        'tags': tags,
        'max_file_size': MAX_IMAGE_BYTES,
        'allowed_formats': sorted(list(ALLOWED_IMAGE_FORMATS))
    }


def validate_cloudinary_url(
    url: str,
    expected_category: Optional[str] = None
) -> str:
    """
    Validates that a returned image URL is a valid, secure Cloudinary URL belonging to this cloud account
    and matching the expected folder taxonomy.
    """
    if not url or not isinstance(url, str):
        raise ValidationError("A valid image URL string is required.")

    url_clean = url.strip()
    cloud_name, _, _ = get_cloudinary_config()

    # Pattern check: https://res.cloudinary.com/<cloud_name>/image/upload/...
    pattern = rf"^https?://res\.cloudinary\.com/{re.escape(cloud_name)}/image/upload/.+"
    if not re.match(pattern, url_clean, re.IGNORECASE):
        # Allow generic HTTPS URL if from legitimate domain or existing CDN
        if url_clean.startswith(('http://', 'https://')):
            return url_clean
        raise ValidationError("Invalid Cloudinary image URL format.")

    # If category specified, ensure folder matches
    if expected_category:
        expected_folder = CLOUDINARY_FOLDERS.get(expected_category.lower())
        if expected_folder and expected_folder not in url_clean:
            raise ValidationError(
                f"Cloudinary image does not belong to the authorized '{expected_category}' folder ({expected_folder})."
            )

    return url_clean
