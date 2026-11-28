import os
import mimetypes
import logging
from django.conf import settings
from django.http import FileResponse, Http404
from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from staff.permissions import is_platform_admin, check_staff_permission

logger = logging.getLogger('core.media_views')

User = get_user_model()


def get_safe_content_type(file_path):
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type or 'application/octet-stream'


class SecureMediaView(APIView):
    """
    Centralized, Authenticated Media Router for all files under /media/.
    
    Security Controls:
    1. Public Content (hotels/images/, rooms/images/):
       - Freely accessible for property and room browsing.
       - Disallows directory traversal (..).
       - Enforces X-Content-Type-Options: nosniff.
    
    2. Private Content (users/avatars/, hotels/documents/, support_tickets/):
       - Requires authentication (HTTP 401 for unauthenticated access).
       - Requires strict authorization (HTTP 403 for unauthorized tenants).
       - Serves files with safe Content-Type and security headers.
       - Preserves access to all existing database records and legacy media links.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, file_path):
        return self._serve_media(request, file_path)

    def head(self, request, file_path):
        return self._serve_media(request, file_path)

    def _serve_media(self, request, file_path):
        clean_path = str(file_path or '').replace('\\', '/').strip()
        while clean_path.startswith('/'):
            clean_path = clean_path[1:]

        # Reject path traversal attempts
        parts = clean_path.split('/')
        if '..' in parts or any(p.strip() == '' for p in parts if p != parts[-1]):
            return Response(
                {"error": "Invalid file path."},
                status=status.HTTP_400_BAD_REQUEST
            )

        media_root = os.path.abspath(str(settings.MEDIA_ROOT))
        full_path = os.path.abspath(os.path.join(media_root, clean_path))

        # Enforce that path resides strictly inside MEDIA_ROOT
        try:
            if not full_path.startswith(media_root):
                return Response(
                    {"error": "Access denied."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Exception:
            return Response({"error": "Invalid storage path."}, status=status.HTTP_400_BAD_REQUEST)

        if not os.path.isfile(full_path):
            return Response(
                {"error": "Media file not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # -------------------------------------------------------------
        # 1. PUBLIC MEDIA: Hotel and Room Photos
        # -------------------------------------------------------------
        if clean_path.startswith(('hotels/images/', 'rooms/images/')):
            response = FileResponse(open(full_path, 'rb'), content_type=get_safe_content_type(full_path))
            response['X-Content-Type-Options'] = 'nosniff'
            response['Cache-Control'] = 'public, max-age=86400'
            return response

        # -------------------------------------------------------------
        # 2. PRIVATE MEDIA: Check Authentication First (401)
        # -------------------------------------------------------------
        user = request.user
        if not (user and user.is_authenticated):
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "AUTHENTICATION_REQUIRED",
                        "message": "Authentication credentials are required to access this private media resource."
                    },
                    "detail": "Authentication credentials were not provided."
                },
                status=status.HTTP_401_UNAUTHORIZED
            )

        role = str(getattr(user, 'role', '')).upper()
        admin_access = is_platform_admin(user)

        # -------------------------------------------------------------
        # 2A. PRIVATE USER AVATARS (users/avatars/)
        # -------------------------------------------------------------
        if clean_path.startswith('users/avatars/'):
            filename = os.path.basename(clean_path)
            # Find the user matching this avatar
            avatar_owner = User.objects.filter(avatar=clean_path).first()
            if not avatar_owner:
                avatar_owner = User.objects.filter(avatar__endswith=filename).first()

            # Authorized users: avatar owner, platform admin, staff, or hotel owner with booking/staff
            is_owner = bool(avatar_owner and avatar_owner.id == user.id)
            is_staff_user = bool(admin_access or role in ['ADMIN', 'SUPER_ADMIN', 'STAFF'] or user.is_staff)
            
            # Hotel owner check: can view avatars of their guests or employees
            is_authorized_host = False
            if not (is_owner or is_staff_user) and avatar_owner and role in ['HOTEL_OWNER', 'HOST', 'OWNER']:
                from bookings.models import Booking
                from hotels.models import HotelStaff
                is_authorized_host = (
                    Booking.objects.filter(hotel__owner=user, customer=avatar_owner).exists() or
                    HotelStaff.objects.filter(hotel__owner=user, user=avatar_owner).exists()
                )

            if not (is_owner or is_staff_user or is_authorized_host):
                return Response(
                    {
                        "success": False,
                        "error": {
                            "code": "PERMISSION_DENIED",
                            "message": "You do not have permission to access another user's private profile avatar."
                        },
                        "detail": "You do not have permission to view this avatar."
                    },
                    status=status.HTTP_403_FORBIDDEN
                )

            response = FileResponse(open(full_path, 'rb'), content_type=get_safe_content_type(full_path))
            response['X-Content-Type-Options'] = 'nosniff'
            response['Cache-Control'] = 'private, no-cache'
            return response

        # -------------------------------------------------------------
        # 2B. PRIVATE HOTEL VERIFICATION DOCUMENTS (hotels/documents/)
        # -------------------------------------------------------------
        if clean_path.startswith('hotels/documents/'):
            from hotels.models import HotelVerificationDocument
            filename = os.path.basename(clean_path)
            doc = HotelVerificationDocument.objects.filter(document_file=clean_path).select_related('hotel', 'hotel__owner').first()
            if not doc:
                doc = HotelVerificationDocument.objects.filter(document_file__endswith=filename).select_related('hotel', 'hotel__owner').first()

            if not doc:
                return Response({"error": "Verification document not found."}, status=status.HTTP_404_NOT_FOUND)

            is_hotel_owner = bool(doc.hotel and doc.hotel.owner_id == user.id)
            has_verification_perm = bool(
                admin_access or
                check_staff_permission(user, 'VERIFY_HOTELS') or
                check_staff_permission(user, 'VIEW_HOTELS')
            )

            if not (is_hotel_owner or has_verification_perm):
                return Response(
                    {
                        "success": False,
                        "error": {
                            "code": "PERMISSION_DENIED",
                            "message": "You do not have permission to access private hotel verification and compliance documents."
                        },
                        "detail": "You do not have permission to access this document."
                    },
                    status=status.HTTP_403_FORBIDDEN
                )

            safe_filename = f"Document_{doc.document_type}_{doc.id}{os.path.splitext(full_path)[1]}"
            response = FileResponse(open(full_path, 'rb'), content_type=get_safe_content_type(full_path))
            response['X-Content-Type-Options'] = 'nosniff'
            response['Content-Disposition'] = f'inline; filename="{safe_filename}"'
            response['Cache-Control'] = 'private, no-cache'
            return response

        # -------------------------------------------------------------
        # 2C. PRIVATE SUPPORT TICKET ATTACHMENTS (support_tickets/)
        # -------------------------------------------------------------
        if clean_path.startswith('support_tickets/'):
            from payments.models import SupportTicket, TicketMessage
            filename = os.path.basename(clean_path)
            
            ticket = SupportTicket.objects.filter(attachment=clean_path).first()
            if not ticket:
                ticket = SupportTicket.objects.filter(attachment__endswith=filename).first()
            
            if not ticket:
                msg = TicketMessage.objects.filter(attachment=clean_path).select_related('ticket').first()
                if not msg:
                    msg = TicketMessage.objects.filter(attachment__endswith=filename).select_related('ticket').first()
                if msg:
                    ticket = msg.ticket

            if not ticket:
                return Response({"error": "Attachment not found."}, status=status.HTTP_404_NOT_FOUND)

            is_ticket_creator = (ticket.user_id == user.id)
            is_assigned_agent = (ticket.assigned_agent_id == user.id)
            has_support_perm = bool(
                admin_access or
                check_staff_permission(user, 'RESOLVE_TICKETS') or
                role in ['ADMIN', 'SUPER_ADMIN', 'STAFF']
            )
            is_related_host = bool(ticket.booking and ticket.booking.hotel and ticket.booking.hotel.owner_id == user.id)

            if not (is_ticket_creator or is_assigned_agent or has_support_perm or is_related_host):
                return Response(
                    {
                        "success": False,
                        "error": {
                            "code": "PERMISSION_DENIED",
                            "message": "You do not have permission to access this private support ticket attachment."
                        },
                        "detail": "You do not have permission to view this ticket attachment."
                    },
                    status=status.HTTP_403_FORBIDDEN
                )

            safe_num = getattr(ticket, 'ticket_number', None) or getattr(ticket, 'id', 'att')
            safe_filename = f"Ticket_{safe_num}_attachment{os.path.splitext(full_path)[1]}"
            response = FileResponse(open(full_path, 'rb'), content_type=get_safe_content_type(full_path))
            response['X-Content-Type-Options'] = 'nosniff'
            response['Content-Disposition'] = f'inline; filename="{safe_filename}"'
            response['Cache-Control'] = 'private, no-cache'
            return response

        # -------------------------------------------------------------
        # 2D. ANY OTHER UNKNOWN MEDIA FILE: Admin Only
        # -------------------------------------------------------------
        if not admin_access:
            return Response(
                {"error": "Access to internal media resources is restricted."},
                status=status.HTTP_403_FORBIDDEN
            )

        response = FileResponse(open(full_path, 'rb'), content_type=get_safe_content_type(full_path))
        response['X-Content-Type-Options'] = 'nosniff'
        return response


class UserAvatarDownloadView(APIView):
    """
    Dedicated Authenticated Avatar Endpoint: /api/users/<pk>/avatar/
    - 401 if unauthenticated
    - 403 if unauthorized
    - 200 with FileResponse if authorized
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        try:
            target_user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        if not target_user.avatar:
            return Response({"error": "User has not uploaded an avatar."}, status=status.HTTP_404_NOT_FOUND)

        # Authorization: self, admin, staff, or host
        user = request.user
        role = str(getattr(user, 'role', '')).upper()
        is_self = (user.id == target_user.id)
        is_staff_user = is_platform_admin(user) or role in ['ADMIN', 'SUPER_ADMIN', 'STAFF'] or user.is_staff
        
        is_authorized_host = False
        if not (is_self or is_staff_user) and role in ['HOTEL_OWNER', 'HOST', 'OWNER']:
            from bookings.models import Booking
            from hotels.models import HotelStaff
            is_authorized_host = (
                Booking.objects.filter(hotel__owner=user, customer=target_user).exists() or
                HotelStaff.objects.filter(hotel__owner=user, user=target_user).exists()
            )

        if not (is_self or is_staff_user or is_authorized_host):
            return Response(
                {"error": "You do not have permission to view this avatar."},
                status=status.HTTP_403_FORBIDDEN
            )

        file_path = os.path.abspath(target_user.avatar.path) if hasattr(target_user.avatar, 'path') else os.path.join(settings.MEDIA_ROOT, str(target_user.avatar))
        if not os.path.isfile(file_path):
            return Response({"error": "Avatar file not found on storage."}, status=status.HTTP_404_NOT_FOUND)

        response = FileResponse(open(file_path, 'rb'), content_type=get_safe_content_type(file_path))
        response['X-Content-Type-Options'] = 'nosniff'
        response['Cache-Control'] = 'private, no-cache'
        return response


class HotelDocumentDownloadView(APIView):
    """
    Dedicated Authenticated Document Download Endpoint:
    /api/hotels/<hotel_pk>/documents/<pk>/download/ or /api/hotel-documents/<pk>/download/
    - 401 if unauthenticated
    - 403 if unauthorized
    - 200 with FileResponse if authorized
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk, hotel_pk=None):
        from hotels.models import HotelVerificationDocument
        doc = HotelVerificationDocument.objects.filter(pk=pk).select_related('hotel', 'hotel__owner').first()
        if not doc:
            return Response({"error": "Document not found."}, status=status.HTTP_404_NOT_FOUND)

        if hotel_pk and doc.hotel_id != int(hotel_pk):
            return Response({"error": "Document does not belong to specified hotel."}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        is_owner = bool(doc.hotel and doc.hotel.owner_id == user.id)
        has_perm = is_platform_admin(user) or check_staff_permission(user, 'VERIFY_HOTELS') or check_staff_permission(user, 'VIEW_HOTELS')

        if not (is_owner or has_perm):
            return Response(
                {"error": "You do not have permission to view or download this verification document."},
                status=status.HTTP_403_FORBIDDEN
            )

        if not doc.document_file:
            return Response({"error": "Document file is not stored locally."}, status=status.HTTP_404_NOT_FOUND)

        file_path = os.path.abspath(doc.document_file.path) if hasattr(doc.document_file, 'path') else os.path.join(settings.MEDIA_ROOT, str(doc.document_file))
        if not os.path.isfile(file_path):
            return Response({"error": "Physical document file not found."}, status=status.HTTP_404_NOT_FOUND)

        ext = os.path.splitext(file_path)[1]
        safe_filename = f"Document_{doc.document_type}_{doc.id}{ext}"
        response = FileResponse(open(file_path, 'rb'), content_type=get_safe_content_type(file_path))
        response['X-Content-Type-Options'] = 'nosniff'
        response['Content-Disposition'] = f'inline; filename="{safe_filename}"'
        response['Cache-Control'] = 'private, no-cache'
        return response


class SupportTicketAttachmentDownloadView(APIView):
    """
    Dedicated Authenticated Ticket Attachment Endpoint:
    /api/payments/support-tickets/<pk>/attachment/
    - 401 if unauthenticated
    - 403 if unauthorized
    - 200 with FileResponse if authorized
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        from payments.models import SupportTicket
        ticket = SupportTicket.objects.filter(pk=pk).select_related('user', 'assigned_agent', 'booking', 'booking__hotel').first()
        if not ticket or not ticket.attachment:
            return Response({"error": "Attachment not found."}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        role = str(getattr(user, 'role', '')).upper()
        is_creator = (ticket.user_id == user.id)
        is_assigned = (ticket.assigned_agent_id == user.id)
        has_perm = is_platform_admin(user) or check_staff_permission(user, 'RESOLVE_TICKETS') or role in ['ADMIN', 'SUPER_ADMIN', 'STAFF']
        is_host = bool(ticket.booking and ticket.booking.hotel and ticket.booking.hotel.owner_id == user.id)

        if not (is_creator or is_assigned or has_perm or is_host):
            return Response(
                {"error": "You do not have permission to view or download this attachment."},
                status=status.HTTP_403_FORBIDDEN
            )

        file_path = os.path.abspath(ticket.attachment.path) if hasattr(ticket.attachment, 'path') else os.path.join(settings.MEDIA_ROOT, str(ticket.attachment))
        if not os.path.isfile(file_path):
            return Response({"error": "Physical attachment not found."}, status=status.HTTP_404_NOT_FOUND)

        ext = os.path.splitext(file_path)[1]
        safe_num = getattr(ticket, 'ticket_number', None) or getattr(ticket, 'id', 'att')
        safe_filename = f"Ticket_{safe_num}_attachment{ext}"
        response = FileResponse(open(file_path, 'rb'), content_type=get_safe_content_type(file_path))
        response['X-Content-Type-Options'] = 'nosniff'
        response['Content-Disposition'] = f'inline; filename="{safe_filename}"'
        response['Cache-Control'] = 'private, no-cache'
        return response
