from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Wishlist
from .serializers import WishlistSerializer
from hotels.models import Hotel

class WishlistListView(generics.ListAPIView):
    serializer_class = WishlistSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return Wishlist.objects.none()
        return Wishlist.objects.filter(user=user).order_by('-created_at')

class WishlistToggleView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, hotel_id=None):
        hid = hotel_id or request.data.get('hotel_id')
        if not hid:
            return Response({"error": "hotel_id is required in request body or URL."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            hotel = Hotel.objects.get(id=hid)
            wishlist_item = Wishlist.objects.filter(user=request.user, hotel=hotel).first()
            if wishlist_item:
                wishlist_item.delete()
                return Response({
                    "wishlisted": False,
                    "is_favorited": False,
                    "hotel_id": hotel.id,
                    "message": f"Removed {hotel.name} from wishlist."
                }, status=status.HTTP_200_OK)
            else:
                Wishlist.objects.create(user=request.user, hotel=hotel)
                return Response({
                    "wishlisted": True,
                    "is_favorited": True,
                    "hotel_id": hotel.id,
                    "message": f"Saved {hotel.name} to wishlist."
                }, status=status.HTTP_200_OK)
        except Hotel.DoesNotExist:
            return Response({"error": "Hotel not found."}, status=status.HTTP_404_NOT_FOUND)
