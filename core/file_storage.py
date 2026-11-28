import os
import uuid
from django.utils.deconstruct import deconstructible


@deconstructible
class SecureUploadPath:
    """
    Generates non-predictable, UUID-based file paths for uploads.
    Prevents directory traversal, preserves file extensions safely,
    and stops private client filenames from leaking into storage or URLs.
    """
    def __init__(self, sub_dir):
        self.sub_dir = sub_dir.strip('/')

    def __call__(self, instance, filename):
        ext = os.path.splitext(filename)[1].lower()
        # Fallback to safe default extension if missing
        if not ext:
            if 'image' in self.sub_dir or 'avatar' in self.sub_dir:
                ext = '.jpg'
            elif 'document' in self.sub_dir:
                ext = '.pdf'
            else:
                ext = '.bin'
        
        # Clean extension: letters/numbers only, max 5 chars
        clean_ext = '.' + ''.join(c for c in ext.lstrip('.') if c.isalnum())[:5]
        if clean_ext == '.':
            clean_ext = '.bin'

        safe_filename = f"{uuid.uuid4().hex}{clean_ext}"
        return f"{self.sub_dir}/{safe_filename}"


# Callable instances for Django model upload_to
secure_avatar_upload = SecureUploadPath('users/avatars')
secure_hotel_document_upload = SecureUploadPath('hotels/documents')
secure_hotel_image_upload = SecureUploadPath('hotels/images')
secure_room_image_upload = SecureUploadPath('rooms/images')
secure_ticket_attachment_upload = SecureUploadPath('support_tickets/attachments')
secure_ticket_message_upload = SecureUploadPath('support_tickets/messages')
