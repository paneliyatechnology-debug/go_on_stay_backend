from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers
from django.utils import timezone
from django.db.models import Avg
from decimal import Decimal
from .models import Review
from .serializers import ReviewSerializer
from bookings.models import Booking

def update_hotel_guest_rating(hotel):
    if not hotel:
        return
    visible_reviews = hotel.reviews.filter(status=Review.STATUS_VISIBLE)
    count = visible_reviews.count()
    if count > 0:
        avg = visible_reviews.aggregate(Avg('rating'))['rating__avg']
        hotel.guest_rating = Decimal(str(round(float(avg), 1)))
    else:
        hotel.guest_rating = Decimal('5.0')
    hotel.save(update_fields=['guest_rating'])

class ReviewListCreateView(generics.ListCreateAPIView):
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        user = self.request.user
        hotel_id = self.request.query_params.get('hotel_id')

        # If requested by a Hotel Owner, return reviews for their hotels
        if user.is_authenticated and (getattr(user, 'role', '') == 'HOTEL_OWNER' or self.request.query_params.get('owner') == 'true'):
            if getattr(user, 'role', '') in ['ADMIN', 'SUPER_ADMIN'] and not Review.objects.filter(hotel__owner=user).exists():
                qs = Review.objects.all()
            else:
                qs = Review.objects.filter(hotel__owner=user)
            if hotel_id:
                qs = qs.filter(hotel_id=hotel_id)
            return qs.order_by('-created_at')

        # Public guest listing
        if hotel_id:
            return Review.objects.filter(hotel_id=hotel_id, status=Review.STATUS_VISIBLE).order_by('-created_at')
        return Review.objects.filter(status=Review.STATUS_VISIBLE).order_by('-created_at')

    def perform_create(self, serializer):
        booking_lookup = self.request.data.get('booking')
        if not booking_lookup:
            raise serializers.ValidationError({"booking": "Reservation booking identifier is required."})

        booking = None
        if str(booking_lookup).isdigit():
            booking = Booking.objects.filter(id=int(booking_lookup)).first()
        
        if not booking:
            booking = Booking.objects.filter(booking_id=str(booking_lookup)).first()

        if not booking:
            raise serializers.ValidationError({
                "booking": "Reservation booking not found."
            })

        is_admin = getattr(self.request.user, 'role', '') in ['ADMIN', 'SUPER_ADMIN'] or self.request.user.is_staff
        if booking.customer != self.request.user and not is_admin:
            raise serializers.ValidationError({
                "booking": "You can only review hotels where you have a valid reservation under your account."
            })

        # Verified Stay Enforcement (TASK-14)
        today = timezone.now().date()
        is_completed = (
            booking.booking_status in [Booking.STATUS_COMPLETED, Booking.STATUS_CHECKED_OUT] or
            (booking.booking_status == Booking.STATUS_CONFIRMED and booking.check_out <= today)
        )
        if not is_completed:
            raise serializers.ValidationError({
                "booking": "You can only review a hotel after completing your stay."
            })

        if hasattr(booking, 'review') or Review.objects.filter(booking=booking).exists():
            raise serializers.ValidationError({
                "booking": "You have already submitted a rating for this stay reservation."
            })

        review = serializer.save(user=self.request.user, hotel=booking.hotel, booking=booking)
        update_hotel_guest_rating(booking.hotel)


class IsReviewAuthorOrAdmin(permissions.BasePermission):
    """
    Object-level permission allowing:
    - Safe methods (GET, HEAD, OPTIONS): Authenticated users.
    - Write/Delete methods: Strictly the author of the review or a platform administrator.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        if not (request.user and request.user.is_authenticated):
            return False
        user_role = str(getattr(request.user, 'role', '')).upper()
        if request.user.is_staff or request.user.is_superuser or user_role in ['ADMIN', 'SUPER_ADMIN']:
            return True
        return obj.user == request.user


class ReviewDetailView(generics.RetrieveDestroyAPIView):
    queryset = Review.objects.all()
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticated, IsReviewAuthorOrAdmin]

    def perform_destroy(self, instance):
        user = self.request.user
        user_role = str(getattr(user, 'role', '')).upper()
        is_admin = user.is_staff or user.is_superuser or user_role in ['ADMIN', 'SUPER_ADMIN']
        is_author = (instance.user == user)

        if not (is_admin or is_author):
            raise permissions.PermissionDenied("You do not have permission to delete this review.")

        hotel = instance.hotel
        instance.delete()
        update_hotel_guest_rating(hotel)


class OwnerReviewResponseView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            review = Review.objects.get(pk=pk)
        except Review.DoesNotExist:
            return Response({"error": "Review record not found."}, status=status.HTTP_404_NOT_FOUND)

        is_admin = getattr(request.user, 'role', None) in ['ADMIN', 'SUPER_ADMIN'] or request.user.is_staff
        if review.hotel.owner != request.user and not is_admin:
            return Response({"error": "Unauthorized. Only the hotel owner can reply to this guest review."}, status=status.HTTP_403_FORBIDDEN)

        response_text = request.data.get('response', '').strip()
        if not response_text:
            return Response({"error": "Response text cannot be empty."}, status=status.HTTP_400_BAD_REQUEST)

        review.owner_response = response_text
        review.owner_responded_at = timezone.now()
        review.save(update_fields=['owner_response', 'owner_responded_at'])

        return Response({
            "message": "Response posted successfully to guest review.",
            "review": ReviewSerializer(review).data
        }, status=status.HTTP_200_OK)
