from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q, Min, Max, Avg, Count, F
from .models import Hotel, HotelImage, Amenity, HotelVerificationDocument, HotelStaff
from .serializers import (
    HotelSerializer, HotelCreateUpdateSerializer,
    AmenitySerializer, HotelImageSerializer,
    HotelVerificationDocumentSerializer, HotelStaffSerializer
)

class IsOwnerOrAdminOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.owner == request.user or request.user.is_staff or request.user.role in ['ADMIN', 'SUPER_ADMIN']

from rest_framework.pagination import PageNumberPagination

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 1000

import re

COMMON_PHONETICS_AND_SYNONYMS = {
    'radison': ['radisson'],
    'radisson': ['radison'],
    'hyaat': ['hyatt'],
    'hyat': ['hyatt'],
    'hyatt': ['hyat', 'hyaat'],
    'merriot': ['marriott'],
    'mariott': ['marriott'],
    'marriot': ['marriott'],
    'marriott': ['merriot', 'mariott'],
    'lila': ['leela'],
    'leela': ['lila'],
    'obroy': ['oberoi'],
    'oberoy': ['oberoi'],
    'oberoi': ['obroy', 'oberoy'],
    'taaj': ['taj'],
    'taj': ['taaj'],
    'mahel': ['mahal'],
    'mahal': ['mahel'],
    'palace': ['heritage', 'haveli', 'fort', 'royal', 'mahal'],
    'resort': ['retreat', 'villas', 'spa'],
    'beach': ['sea', 'ocean', 'coast', 'waterfront', 'beachfront'],
    'sea': ['beach', 'ocean'],
    'lake': ['waterfront', 'udaipur'],
}

STOP_WORDS = {
    'hotel', 'hotels', 'in', 'at', 'the', 'a', 'an', 'near', 'me', 'pe', 'ke',
    'ka', 'ki', 'se', 'room', 'rooms', 'stay', 'stays', 'show', 'find', 'book',
    'best', 'good', 'mujhe', 'chahiye', 'karo', 'dikhao', 'dikhana', 'batao',
    'and', 'or', 'for', 'of', 'to'
}

def extract_search_tokens(query_str):
    if not query_str:
        return []
    words = [w.lower() for w in re.findall(r'[a-zA-Z0-9]+', str(query_str))]
    meaningful = [w for w in words if w not in STOP_WORDS and len(w) > 1]
    return meaningful if meaningful else [w for w in words if len(w) > 1]

def filter_hotels_queryset(queryset, params):
    # 1. Location / Text Search with Multi-word Tokenization & Phonetic/Synonym Expansion
    search = params.get('search') or params.get('query') or params.get('q')
    city = params.get('city')
    area = params.get('area')
    destination = params.get('destination')
    landmark = params.get('landmark')

    text_query = search or city
    if text_query:
        clean_query = text_query.split(',')[0].strip()
        tokens = extract_search_tokens(clean_query)

        search_q = Q()
        # Direct exact or partial phrase match
        search_q |= Q(name__icontains=clean_query)
        search_q |= Q(city__icontains=clean_query)
        search_q |= Q(state__icontains=clean_query)
        search_q |= Q(address__icontains=clean_query)
        search_q |= Q(area__icontains=clean_query)
        search_q |= Q(landmark__icontains=clean_query)
        search_q |= Q(destination__icontains=clean_query)
        search_q |= Q(description__icontains=clean_query)

        # Word-by-word (token) matching & phonetic/synonym expansions
        for token in tokens:
            token_q = (
                Q(name__icontains=token) |
                Q(city__icontains=token) |
                Q(state__icontains=token) |
                Q(address__icontains=token) |
                Q(area__icontains=token) |
                Q(landmark__icontains=token) |
                Q(destination__icontains=token) |
                Q(description__icontains=token) |
                Q(property_type__icontains=token) |
                Q(amenities__name__icontains=token)
            )
            synonyms = COMMON_PHONETICS_AND_SYNONYMS.get(token, [])
            for syn in synonyms:
                token_q |= (
                    Q(name__icontains=syn) |
                    Q(city__icontains=syn) |
                    Q(state__icontains=syn) |
                    Q(landmark__icontains=syn) |
                    Q(description__icontains=syn) |
                    Q(property_type__icontains=syn) |
                    Q(amenities__name__icontains=syn)
                )
            search_q |= token_q

        queryset = queryset.filter(search_q).distinct()

    if area:
        queryset = queryset.filter(area__icontains=area)
    if destination:
        queryset = queryset.filter(destination__icontains=destination)
    if landmark:
        queryset = queryset.filter(landmark__icontains=landmark)

    # 2. Property Type Filter
    property_type = params.get('property_type')
    if property_type:
        types = [t.strip().upper() for t in property_type.split(',') if t.strip()]
        if len(types) > 1:
            queryset = queryset.filter(property_type__in=types)
        elif len(types) == 1:
            queryset = queryset.filter(property_type__iexact=types[0])

    # 3. Star Rating Filter
    star_rating = params.get('star_rating') or params.get('stars')
    if star_rating:
        try:
            stars_list = [int(s.strip()) for s in str(star_rating).split(',') if s.strip().isdigit()]
            if stars_list:
                queryset = queryset.filter(star_rating__in=stars_list)
        except Exception:
            pass

    # 4. Guest Rating Filter
    min_guest_rating = params.get('min_guest_rating') or params.get('min_rating')
    if min_guest_rating:
        try:
            queryset = queryset.filter(guest_rating__gte=float(min_guest_rating))
        except ValueError:
            pass

    # 5. Price Filtering (Min / Max Price)
    min_price = params.get('min_price')
    max_price = params.get('max_price') or params.get('price_max')

    if min_price or max_price:
        queryset = queryset.annotate(min_room_price=Min('rooms__price_per_night'))
        if min_price and str(min_price).replace('.', '', 1).isdigit():
            queryset = queryset.filter(min_room_price__gte=float(min_price))
        if max_price and str(max_price).replace('.', '', 1).isdigit():
            queryset = queryset.filter(min_room_price__lte=float(max_price))

    # 6. Booking Options (Free Cancellation, Breakfast)
    if params.get('free_cancellation') == 'true':
        queryset = queryset.filter(rooms__free_cancellation=True).distinct()
    if params.get('breakfast_included') == 'true':
        queryset = queryset.filter(rooms__breakfast_included=True).distinct()

    # 7. Amenities Filtering
    amenities_param = params.get('amenities')
    if amenities_param:
        amenity_list = [a.strip() for a in amenities_param.split(',') if a.strip()]
        for a_name in amenity_list:
            queryset = queryset.filter(
                Q(amenities__name__icontains=a_name) | Q(rooms__amenities__name__icontains=a_name)
            ).distinct()

    # 8. Sorting Logic
    sort_by = params.get('sort_by') or params.get('sort')
    if sort_by in ['price_low', 'price_low_high', 'price_asc']:
        queryset = queryset.annotate(sort_price=Min('rooms__price_per_night')).order_by(F('sort_price').asc(nulls_last=True))
    elif sort_by in ['price_high', 'price_high_low', 'price_desc']:
        queryset = queryset.annotate(sort_price=Min('rooms__price_per_night')).order_by(F('sort_price').desc(nulls_last=True))
    elif sort_by in ['rating', 'rating_desc']:
        queryset = queryset.annotate(
            avg_rating=Avg('reviews__rating', filter=Q(reviews__status='VISIBLE')),
            num_reviews=Count('reviews', filter=Q(reviews__status='VISIBLE'))
        ).order_by(
            F('avg_rating').desc(nulls_last=True),
            F('guest_rating').desc(nulls_last=True),
            F('num_reviews').desc(nulls_last=True),
            '-star_rating'
        )
    elif sort_by in ['newest', 'recent']:
        queryset = queryset.order_by('-created_at')
    else:
        # Default Recommended Sorting: Highest Rating (5★ first) -> Most Reviews -> Star Rating -> Newest
        queryset = queryset.annotate(
            avg_rating=Avg('reviews__rating', filter=Q(reviews__status='VISIBLE')),
            num_reviews=Count('reviews', filter=Q(reviews__status='VISIBLE'))
        ).order_by(
            F('avg_rating').desc(nulls_last=True),
            F('guest_rating').desc(nulls_last=True),
            F('num_reviews').desc(nulls_last=True),
            '-star_rating',
            '-created_at'
        )

    return queryset.distinct()



class HotelListView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    pagination_class = StandardResultsSetPagination

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return HotelCreateUpdateSerializer
        return HotelSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['check_in'] = self.request.query_params.get('check_in')
        context['check_out'] = self.request.query_params.get('check_out')
        return context

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and (user.is_staff or user.is_superuser or getattr(user, 'role', '') in ['ADMIN', 'SUPER_ADMIN']):
            base_qs = Hotel.objects.all().order_by('-created_at')
        else:
            base_qs = Hotel.objects.filter(
                Q(is_approved=True) | Q(status=Hotel.STATUS_APPROVED),
                owner__is_blocked=False,
                owner__is_active=True
            ).order_by('-created_at')

        return filter_hotels_queryset(base_qs, self.request.query_params)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user, status=Hotel.STATUS_SUBMITTED, is_approved=False)


class HotelSearchAPIView(generics.ListAPIView):
    serializer_class = HotelSerializer
    permission_classes = [permissions.AllowAny]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['check_in'] = self.request.query_params.get('check_in')
        context['check_out'] = self.request.query_params.get('check_out')
        return context

    def get_queryset(self):
        base_qs = Hotel.objects.filter(
            is_approved=True, 
            status=Hotel.STATUS_APPROVED,
            owner__is_blocked=False,
            owner__is_active=True
        )
        return filter_hotels_queryset(base_qs, self.request.query_params)


class HotelDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Hotel.objects.all()
    permission_classes = [IsOwnerOrAdminOrReadOnly]

    def get_object(self):
        pk = self.kwargs.get('pk')
        hotel = Hotel.objects.filter(pk=pk).first()
        if not hotel:
            from rest_framework.exceptions import NotFound
            raise NotFound("Hotel not found.")
        self.check_object_permissions(self.request, hotel)
        return hotel

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['check_in'] = self.request.query_params.get('check_in')
        context['check_out'] = self.request.query_params.get('check_out')
        return context

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return HotelCreateUpdateSerializer
        return HotelSerializer

    def destroy(self, request, *args, **kwargs):
        hotel = self.get_object()
        from bookings.models import Booking
        from django.utils import timezone
        today = timezone.now().date()
        active_bookings = Booking.objects.filter(
            hotel=hotel,
            booking_status__in=[Booking.STATUS_CONFIRMED, Booking.STATUS_CHECKED_IN],
            check_out__gte=today
        )
        if active_bookings.exists():
            return Response(
                {"error": "Cannot delete hotel with active upcoming reservations."},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().destroy(request, *args, **kwargs)


class OwnerHotelListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return HotelCreateUpdateSerializer
        return HotelSerializer

    def get_queryset(self):
        return Hotel.objects.filter(owner=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        user = self.request.user
        if getattr(user, 'role', '') == 'CUSTOMER':
            user.role = 'HOTEL_OWNER'
            user.save(update_fields=['role'])
        serializer.save(owner=user, status=Hotel.STATUS_SUBMITTED, is_approved=False)

# Backward-compatible alias
OwnerHotelListView = OwnerHotelListCreateView


class OwnerDashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        from bookings.models import Booking
        from rooms.models import Room
        from django.utils import timezone

        # 1. Properties Overview
        owner_hotels = Hotel.objects.filter(owner=user)
        total_hotels = owner_hotels.count()
        approved_hotels = owner_hotels.filter(status=Hotel.STATUS_APPROVED, is_approved=True).count()
        pending_hotels = owner_hotels.filter(status__in=[Hotel.STATUS_SUBMITTED, Hotel.STATUS_UNDER_REVIEW, Hotel.STATUS_DRAFT]).count()
        rejected_hotels = owner_hotels.filter(status=Hotel.STATUS_REJECTED).count()

        # 2. Rooms Overview
        owner_rooms = Room.objects.filter(hotel__owner=user)
        total_rooms = owner_rooms.count()
        total_inventory = sum(r.total_rooms for r in owner_rooms)

        # 3. Bookings Overview
        owner_bookings = Booking.objects.filter(hotel__owner=user)
        total_bookings = owner_bookings.count()
        confirmed_bookings = owner_bookings.filter(booking_status=Booking.STATUS_CONFIRMED).count()
        checked_in_bookings = owner_bookings.filter(booking_status=Booking.STATUS_CHECKED_IN).count()
        completed_bookings = owner_bookings.filter(booking_status=Booking.STATUS_CHECKED_OUT).count()
        cancelled_bookings = owner_bookings.filter(booking_status=Booking.STATUS_CANCELLED).count()

        # 4. Revenue Overview (excludes cancelled, refund-pending, and refunded bookings)
        revenue_qs = owner_bookings.filter(
            booking_status__in=[Booking.STATUS_CONFIRMED, Booking.STATUS_CHECKED_IN, Booking.STATUS_CHECKED_OUT]
        ).exclude(
            payment_status__in=[Booking.PAYMENT_REFUND_PENDING, Booking.PAYMENT_REFUNDED, Booking.PAYMENT_PARTIALLY_REFUNDED]
        )
        total_revenue = sum(float(b.total_amount or 0) for b in revenue_qs)

        # Current Month Revenue
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_bookings = revenue_qs.filter(created_at__gte=start_of_month)
        monthly_revenue = sum(float(b.total_amount or 0) for b in month_bookings)

        # 5. Recent 10 Bookings
        recent_bookings = []
        for b in owner_bookings.order_by('-created_at')[:10]:
            recent_bookings.append({
                "id": b.id,
                "booking_id": b.booking_id,
                "guest_name": b.guest_name,
                "guest_phone": b.guest_phone,
                "guest_email": b.guest_email,
                "hotel_id": b.hotel.id,
                "hotel_name": b.hotel.name,
                "room_title": b.room.title if b.room else "",
                "room_number": b.room_number,
                "check_in": str(b.check_in),
                "check_out": str(b.check_out),
                "number_of_nights": b.number_of_nights,
                "number_of_rooms": b.number_of_rooms,
                "total_amount": float(b.total_amount or 0),
                "payment_status": b.payment_status,
                "booking_status": b.booking_status,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            })

        # 6. Hotels Summary List
        hotels_summary = []
        for h in owner_hotels.order_by('-created_at'):
            primary_img = h.images.filter(is_primary=True).first() or h.images.first()
            img_url = primary_img.get_image_display() if primary_img else None
            hotels_summary.append({
                "id": h.id,
                "name": h.name,
                "city": h.city,
                "state": h.state,
                "property_type": h.property_type,
                "status": h.status,
                "is_approved": h.is_approved,
                "is_active": h.is_active,
                "star_rating": h.star_rating,
                "guest_rating": float(h.guest_rating or 0),
                "rooms_count": h.rooms.count(),
                "image": img_url,
                "created_at": h.created_at.isoformat() if h.created_at else None,
            })

        return Response({
            "owner": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "full_name": user.get_full_name() or user.username,
                "role": user.role,
                "phone_number": user.phone_number,
            },
            "statistics": {
                "hotels": {
                    "total": total_hotels,
                    "approved": approved_hotels,
                    "pending": pending_hotels,
                    "rejected": rejected_hotels,
                },
                "rooms": {
                    "total_types": total_rooms,
                    "total_physical_inventory": total_inventory,
                },
                "bookings": {
                    "total": total_bookings,
                    "confirmed": confirmed_bookings,
                    "active_guests": checked_in_bookings,
                    "completed": completed_bookings,
                    "cancelled": cancelled_bookings,
                },
                "revenue": {
                    "total_revenue": round(total_revenue, 2),
                    "this_month_revenue": round(monthly_revenue, 2),
                    "currency": getattr(user, 'preferred_currency', 'INR') or 'INR',
                }
            },
            "hotels": hotels_summary,
            "recent_bookings": recent_bookings,
        }, status=status.HTTP_200_OK)


class HotelSubmitApprovalView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            hotel = Hotel.objects.get(pk=pk)
            if hotel.owner != request.user and not request.user.is_staff:
                return Response({"error": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

            hotel.status = Hotel.STATUS_SUBMITTED
            hotel.is_approved = False
            hotel.save()
            return Response({"message": f"Hotel '{hotel.name}' submitted for Admin review & approval.", "status": hotel.status}, status=status.HTTP_200_OK)
        except Hotel.DoesNotExist:
            return Response({"error": "Hotel not found."}, status=status.HTTP_404_NOT_FOUND)


class IsAdminOrSuperAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            (request.user.is_staff or request.user.is_superuser or getattr(request.user, 'role', '') in ['ADMIN', 'SUPER_ADMIN'])
        )

class AdminHotelApprovalView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def post(self, request, pk):
        action = request.data.get('action') # 'approve', 'reject', 'suspend'
        reason = request.data.get('reason', '')

        try:
            hotel = Hotel.objects.get(pk=pk)
            if action == 'approve':
                hotel.status = Hotel.STATUS_APPROVED
                hotel.is_approved = True
                hotel.rejection_reason = None
            elif action == 'reject':
                hotel.status = Hotel.STATUS_REJECTED
                hotel.is_approved = False
                hotel.rejection_reason = reason
            elif action == 'suspend':
                hotel.status = Hotel.STATUS_SUSPENDED
                hotel.is_approved = False
                hotel.rejection_reason = reason
            else:
                return Response({"error": "Invalid action. Use 'approve', 'reject', or 'suspend'."}, status=status.HTTP_400_BAD_REQUEST)

            hotel.save()

            # Push Notification to Hotel Owner
            from notifications.utils import create_notification
            from notifications.models import Notification
            if action == 'approve':
                create_notification(
                    recipient=hotel.owner,
                    title=f"✅ Hotel Approved & Live: {hotel.name}",
                    message=f"Great news! Your property '{hotel.name}' has been approved by Super Admin and is now live for guest bookings.",
                    notification_type=Notification.TYPE_HOTEL_APPROVED
                )
            else:
                create_notification(
                    recipient=hotel.owner,
                    title=f"⚠️ Hotel {action.capitalize()}ed: {hotel.name}",
                    message=f"Your property '{hotel.name}' status was updated to {action.upper()}. Reason: {reason or 'Compliance check required.'}",
                    notification_type=Notification.TYPE_HOTEL_REJECTED
                )

            return Response({
                "message": f"Hotel '{hotel.name}' status updated to {hotel.status}.",
                "status": hotel.status,
                "is_approved": hotel.is_approved
            }, status=status.HTTP_200_OK)

        except Hotel.DoesNotExist:
            return Response({"error": "Hotel not found."}, status=status.HTTP_404_NOT_FOUND)


class HotelDocumentUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            hotel = Hotel.objects.get(pk=pk)
            if hotel.owner != request.user and not request.user.is_staff:
                return Response({"error": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

            doc_type = request.data.get('document_type', HotelVerificationDocument.DOC_BUSINESS_REG)
            doc_url = request.data.get('document_url')
            doc_file = request.FILES.get('document_file')

            doc = HotelVerificationDocument.objects.create(
                hotel=hotel,
                document_type=doc_type,
                document_url=doc_url,
                document_file=doc_file,
                status=HotelVerificationDocument.STATUS_PENDING
            )
            return Response(HotelVerificationDocumentSerializer(doc).data, status=status.HTTP_201_CREATED)

        except Hotel.DoesNotExist:
            return Response({"error": "Hotel not found."}, status=status.HTTP_404_NOT_FOUND)


class AmenityListView(generics.ListCreateAPIView):
    queryset = Amenity.objects.all().order_by('category', 'name')
    serializer_class = AmenitySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class HotelImageUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            hotel = Hotel.objects.get(pk=pk)
            if hotel.owner != request.user and not request.user.is_staff:
                return Response({"error": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

            image = request.FILES.get('image')
            image_url = request.data.get('image_url')
            is_primary_raw = request.data.get('is_primary', False)
            if isinstance(is_primary_raw, bool):
                is_primary = is_primary_raw
            else:
                is_primary = str(is_primary_raw).lower() in ['true', '1', 'yes']

            if not image and not image_url:
                return Response({"error": "Please provide an image file or image URL."}, status=status.HTTP_400_BAD_REQUEST)

            hotel_image = HotelImage.objects.create(
                hotel=hotel,
                image=image,
                image_url=image_url,
                is_primary=is_primary
            )
            return Response(HotelImageSerializer(hotel_image).data, status=status.HTTP_201_CREATED)
        except Hotel.DoesNotExist:
            return Response({"error": "Hotel not found."}, status=status.HTTP_404_NOT_FOUND)


class HotelCitiesView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        try:
            cities_qs = Hotel.objects.exclude(city__isnull=True).exclude(city__exact='').values_list('city', flat=True)
            unique_cities = sorted(list(set(str(c).strip().title() for c in cities_qs if c and str(c).strip())))
            return Response(unique_cities, status=status.HTTP_200_OK)
        except Exception as e:
            return Response([], status=status.HTTP_200_OK)

