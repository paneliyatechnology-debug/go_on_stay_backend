"""
Cloudinary Direct Upload Signature and Asset Verification API Views.
Provides signed authorization endpoints allowing the frontend to upload images directly
to Cloudinary without routing bulky binaries through Django.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from services.cloudinary_service import (
    generate_cloudinary_signature,
    validate_cloudinary_url,
    is_cloudinary_configured,
    CLOUDINARY_FOLDERS
)


class CloudinarySignatureView(APIView):
    """
    POST /api/cloudinary/signature/
    POST /api/media/cloudinary/signature/
    Generates a secure, cryptographically signed direct upload payload for Cloudinary.
    Checks user role and ownership permissions before issuing signatures.
    Never exposes API Secret to the frontend.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        category = request.data.get('category') or request.query_params.get('category')
        if not category:
            valid_cats = list(CLOUDINARY_FOLDERS.keys())
            return Response({
                "success": False,
                "error": f"Parameter 'category' is required. Allowed values: {valid_cats}."
            }, status=status.HTTP_400_BAD_REQUEST)

        target_id = request.data.get('target_id') or request.query_params.get('target_id')
        if target_id is not None:
            try:
                target_id = int(target_id)
            except (ValueError, TypeError):
                return Response({
                    "success": False,
                    "error": "Parameter 'target_id' must be a valid integer ID."
                }, status=status.HTTP_400_BAD_REQUEST)

        tags = request.data.get('tags')

        try:
            sign_data = generate_cloudinary_signature(
                user=request.user,
                category=str(category),
                target_id=target_id,
                tags=tags
            )
            return Response(sign_data, status=status.HTTP_200_OK)
        except Exception as e:
            status_code = getattr(e, 'status_code', status.HTTP_400_BAD_REQUEST)
            detail = getattr(e, 'detail', str(e))
            if isinstance(detail, list):
                detail = detail[0] if detail else str(e)
            return Response({
                "success": False,
                "error": str(detail)
            }, status=status_code)


class CloudinaryConfigCheckView(APIView):
    """
    GET /api/cloudinary/status/
    Returns whether Cloudinary is configured on the backend without exposing any credentials.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        configured = is_cloudinary_configured()
        return Response({
            "success": True,
            "configured": configured,
            "cloud_name": getattr(request, 'cloud_name', 'bzb1bndw'),
            "supported_categories": list(CLOUDINARY_FOLDERS.keys())
        }, status=status.HTTP_200_OK)
