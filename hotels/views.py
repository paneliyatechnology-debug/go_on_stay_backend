import math
from datetime import timedelta
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q, Min, Max, Avg, Count, F
from .models import (
    Hotel, HotelImage, Amenity, HotelVerificationDocument, HotelStaff,
    DeletedHotelArchive, Country, State, City, Area
)
from .serializers import (
    HotelSerializer, HotelCreateUpdateSerializer,
    AmenitySerializer, HotelImageSerializer,
    HotelVerificationDocumentSerializer, HotelStaffSerializer,
    DeletedHotelArchiveListSerializer, DeletedHotelArchiveDetailSerializer
)
from staff.permissions import is_platform_admin, IsAdminUserRole, check_staff_permission
from staff.models import Department
from rooms.utils import get_available_room_count
from util.validators import parse_flexible_date

class IsOwnerOrAdminOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if is_platform_admin(user):
            return True
        if obj.owner == user:
            return True
        if getattr(user, 'role', '') == 'STAFF':
            profile = getattr(user, 'staff_profile', None)
            dept_code = profile.department.code if (profile and profile.department) else ''
            if Department.normalize_code(dept_code) == Department.CODE_HOTEL_VERIFICATION:
                return True
            if check_staff_permission(user, 'VERIFY_HOTEL') or check_staff_permission(user, 'DELETE_HOTEL'):
                return True
        return False

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
    # 1. Location Hierarchy IDs
    country_id = params.get('country_id')
    state_id = params.get('state_id')
    city_id = params.get('city_id')
    area_id = params.get('area_id')

    if area_id and str(area_id).isdigit():
        queryset = queryset.filter(area_rel_id=int(area_id))
    if city_id and str(city_id).isdigit():
        queryset = queryset.filter(city_rel_id=int(city_id))
    if state_id and str(state_id).isdigit():
        queryset = queryset.filter(state_rel_id=int(state_id))
    if country_id and str(country_id).isdigit():
        queryset = queryset.filter(country_rel_id=int(country_id))

    # 2. Location / Text Search with Multi-word Tokenization & Phonetic/Synonym Expansion
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

    if area and not area_id:
        queryset = queryset.filter(Q(area__icontains=area) | Q(area_rel__name__icontains=area))
    if destination:
        queryset = queryset.filter(destination__icontains=destination)
    if landmark:
        queryset = queryset.filter(landmark__icontains=landmark)

    # 3. Property Type Filter
    property_type = params.get('property_type')
    if property_type:
        types = [t.strip().upper() for t in property_type.split(',') if t.strip()]
        if len(types) > 1:
            queryset = queryset.filter(property_type__in=types)
        elif len(types) == 1:
            queryset = queryset.filter(property_type__iexact=types[0])

    # 4. Star Rating Filter
    star_rating = params.get('star_rating') or params.get('stars')
    if star_rating:
        try:
            stars_list = [int(s.strip()) for s in str(star_rating).split(',') if s.strip().isdigit()]
            if stars_list:
                queryset = queryset.filter(star_rating__in=stars_list)
        except Exception:
            pass

    # 5. Review Rating Filter
    min_rating = params.get('min_rating') or params.get('min_guest_rating')
    max_rating = params.get('max_rating')
    include_unrated = str(params.get('include_unrated', 'false')).lower() in ['true', '1', 'yes']

    if min_rating or max_rating:
        queryset = queryset.annotate(
            avg_rating=Avg('reviews__rating', filter=Q(reviews__status='VISIBLE')),
            num_reviews=Count('reviews', filter=Q(reviews__status='VISIBLE'))
        )
        if not include_unrated:
            queryset = queryset.filter(num_reviews__gt=0)

        if min_rating:
            try:
                min_r = float(min_rating)
                if include_unrated:
                    queryset = queryset.filter(Q(num_reviews=0) | Q(avg_rating__gte=min_r))
                else:
                    queryset = queryset.filter(avg_rating__gte=min_r)
            except ValueError:
                pass

        if max_rating:
            try:
                max_r = float(max_rating)
                if include_unrated:
                    queryset = queryset.filter(Q(num_reviews=0) | Q(avg_rating__lte=max_r))
                else:
                    queryset = queryset.filter(avg_rating__lte=max_r)
            except ValueError:
                pass

    # 6. Price Filtering (Min / Max Price)
    min_price = params.get('min_price')
    max_price = params.get('max_price') or params.get('price_max')

    if min_price or max_price:
        queryset = queryset.annotate(min_room_price=Min('rooms__price_per_night'))
        if min_price and str(min_price).replace('.', '', 1).isdigit():
            queryset = queryset.filter(min_room_price__gte=float(min_price))
        if max_price and str(max_price).replace('.', '', 1).isdigit():
            queryset = queryset.filter(min_room_price__lte=float(max_price))

    # 7. Booking Options (Free Cancellation, Breakfast)
    if params.get('free_cancellation') == 'true':
        queryset = queryset.filter(rooms__free_cancellation=True).distinct()
    if params.get('breakfast_included') == 'true':
        queryset = queryset.filter(rooms__breakfast_included=True).distinct()

    # 8. Status & Approval Filtering (useful for Admin and Hotel Verification Staff)
    status_filter = params.get('status')
    if status_filter:
        queryset = queryset.filter(status__iexact=status_filter.strip())

    is_approved_filter = params.get('is_approved')
    if is_approved_filter is not None and is_approved_filter != '':
        if str(is_approved_filter).lower() in ['true', '1']:
            queryset = queryset.filter(is_approved=True)
        elif str(is_approved_filter).lower() in ['false', '0']:
            queryset = queryset.filter(is_approved=False)

    # 9. Amenities Filtering
    amenities_param = params.get('amenities')
    if amenities_param:
        amenity_list = [a.strip() for a in amenities_param.split(',') if a.strip()]
        for a_name in amenity_list:
            queryset = queryset.filter(
                Q(amenities__name__icontains=a_name) | Q(rooms__amenities__name__icontains=a_name)
            ).distinct()

    # 10. Sorting Logic
    sort_by = params.get('sort_by') or params.get('sort')
    if sort_by in ['price_low', 'price_low_high', 'price_asc', 'price_low_to_high']:
        queryset = queryset.annotate(sort_price=Min('rooms__price_per_night')).order_by(F('sort_price').asc(nulls_last=True), 'id')
    elif sort_by in ['price_high', 'price_high_low', 'price_desc', 'price_high_to_low']:
        queryset = queryset.annotate(sort_price=Min('rooms__price_per_night')).order_by(F('sort_price').desc(nulls_last=True), 'id')
    elif sort_by in ['rating', 'rating_desc', 'rating_high_to_low']:
        if 'avg_rating' not in [c.name for c in queryset.query.annotations.values() if hasattr(c, 'name')]:
            queryset = queryset.annotate(
                avg_rating=Avg('reviews__rating', filter=Q(reviews__status='VISIBLE')),
                num_reviews=Count('reviews', filter=Q(reviews__status='VISIBLE'))
            )
        queryset = queryset.order_by(
            F('avg_rating').desc(nulls_last=True),
            F('guest_rating').desc(nulls_last=True),
            F('num_reviews').desc(nulls_last=True),
            '-star_rating',
            'id'
        )
    elif sort_by in ['newest', 'recent']:
        queryset = queryset.order_by('-created_at', 'id')
    else:
        # Default Recommended Sorting: Highest Rating (5★ first) -> Most Reviews -> Star Rating -> Newest
        if 'avg_rating' not in [c.name for c in queryset.query.annotations.values() if hasattr(c, 'name')]:
            queryset = queryset.annotate(
                avg_rating=Avg('reviews__rating', filter=Q(reviews__status='VISIBLE')),
                num_reviews=Count('reviews', filter=Q(reviews__status='VISIBLE'))
            )
        queryset = queryset.order_by(
            F('avg_rating').desc(nulls_last=True),
            F('guest_rating').desc(nulls_last=True),
            F('num_reviews').desc(nulls_last=True),
            '-star_rating',
            '-created_at',
            'id'
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
        is_authorized = False

        if user.is_authenticated:
            if user.is_superuser or getattr(user, 'role', '') in ['ADMIN', 'SUPER_ADMIN'] or is_platform_admin(user):
                is_authorized = True
            elif getattr(user, 'role', '') == 'STAFF' or getattr(user, 'is_staff', False):
                # Check if staff belongs to HOTEL_VERIFICATION department or has verification permissions
                staff_profile = getattr(user, 'staff_profile', None)
                dept = ''
                if staff_profile and staff_profile.is_active_account:
                    dept = getattr(staff_profile.department, 'code', '') if staff_profile.department else ''
                    norm_dept = Department.normalize_code(dept)
                    if (norm_dept == Department.CODE_HOTEL_VERIFICATION or
                        staff_profile.has_perm('VERIFY_HOTEL') or
                        staff_profile.has_perm('VERIFY_HOTELS') or
                        staff_profile.has_perm('VIEW_HOTELS') or
                        check_staff_permission(user, 'VERIFY_HOTEL')):
                        is_authorized = True

        if is_authorized:
            base_qs = Hotel.objects.filter(is_deleted=False).order_by('-created_at')
        else:
            base_qs = Hotel.objects.filter(
                Q(is_approved=True) | Q(status=Hotel.STATUS_APPROVED),
                owner__is_blocked=False,
                owner__is_active=True,
                is_deleted=False
            ).order_by('-created_at')

        return filter_hotels_queryset(base_qs, self.request.query_params)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user, status=Hotel.STATUS_SUBMITTED, is_approved=False)


def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Computes distance in kilometers between two lat/long points using the Haversine formula.
    """
    R = 6371.0  # Earth radius in kilometers
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    delta_phi = math.radians(float(lat2) - float(lat1))
    delta_lambda = math.radians(float(lon2) - float(lon1))

    a = math.sin(delta_phi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0)**2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return R * c


def execute_hotel_search(params, request=None, is_near_me=False, default_radius_km=5.0, auto_expand=False):
    # Detect near me intent from query params or search queries
    near_me_param = str(params.get('near_me', '')).strip().lower()
    if near_me_param in ['true', '1', 'yes']:
        is_near_me = True

    raw_search_query = (params.get('search') or params.get('query') or params.get('q') or '').strip()
    is_near_me_text_query = False
    if raw_search_query.lower() in ['near me', 'hotels near me', 'hotel near me', 'near by', 'nearby', 'hotels near by']:
        is_near_me = True
        is_near_me_text_query = True

    if is_near_me:
        default_sort_by = 'nearest_first'
        default_radius_km = float(params.get('radius_km') or params.get('radius') or 10.0)
        if 'auto_expand' in params:
            auto_expand = str(params.get('auto_expand')).strip().lower() in ['true', '1', 'yes']
        else:
            auto_expand = True
    else:
        default_sort_by = 'recommended'
        default_radius_km = float(params.get('radius_km') or params.get('radius') or 5.0)
        if 'auto_expand' in params:
            auto_expand = str(params.get('auto_expand')).strip().lower() in ['true', '1', 'yes']
        else:
            auto_expand = False

    lat_str = params.get('latitude') or params.get('lat')
    lng_str = params.get('longitude') or params.get('lng') or params.get('lon')

    # If near me and coordinates missing, attempt city fallback
    if is_near_me and (not lat_str or not lng_str):
        city_param = params.get('city')
        if city_param:
            city_obj = City.objects.filter(Q(name__iexact=city_param.strip()) | Q(name__icontains=city_param.strip())).first()
            if city_obj and city_obj.latitude is not None and city_obj.longitude is not None:
                lat_str = str(city_obj.latitude)
                lng_str = str(city_obj.longitude)

    # If near me is requested and coordinates could not be resolved, return 400 LOCATION_REQUIRED
    if is_near_me and (not lat_str or not lng_str):
        return Response({
            "success": False,
            "error": {
                "code": "LOCATION_REQUIRED",
                "message": "Latitude and longitude are required to find hotels near you. Please enable location services on your device or specify a city."
            }
        }, status=status.HTTP_400_BAD_REQUEST)

    # 1. Location Hierarchy Validation
    area_id = params.get('area_id')
    city_id = params.get('city_id')
    state_id = params.get('state_id')
    country_id = params.get('country_id')

    try:
        area_id_int = int(area_id) if area_id else None
        city_id_int = int(city_id) if city_id else None
        state_id_int = int(state_id) if state_id else None
        country_id_int = int(country_id) if country_id else None
    except ValueError:
        return Response({
            "success": False,
            "error": {
                "code": "INVALID_LOCATION_ID",
                "message": "Location IDs must be valid integers."
            }
        }, status=status.HTTP_400_BAD_REQUEST)

    if area_id_int and city_id_int:
        if not Area.objects.filter(id=area_id_int, city_id=city_id_int).exists():
            return Response({
                "success": False,
                "error": {
                    "code": "INVALID_LOCATION_HIERARCHY",
                    "message": f"Area ID {area_id_int} does not belong to City ID {city_id_int}."
                }
            }, status=status.HTTP_400_BAD_REQUEST)

    if city_id_int and state_id_int:
        if not City.objects.filter(id=city_id_int, state_id=state_id_int).exists():
            return Response({
                "success": False,
                "error": {
                    "code": "INVALID_LOCATION_HIERARCHY",
                    "message": f"City ID {city_id_int} does not belong to State ID {state_id_int}."
                }
            }, status=status.HTTP_400_BAD_REQUEST)

    if state_id_int and country_id_int:
        if not State.objects.filter(id=state_id_int, country_id=country_id_int).exists():
            return Response({
                "success": False,
                "error": {
                    "code": "INVALID_LOCATION_HIERARCHY",
                    "message": f"State ID {state_id_int} does not belong to Country ID {country_id_int}."
                }
            }, status=status.HTTP_400_BAD_REQUEST)

    # 2. Coordinates & Geosearch Validation
    has_lat = lat_str is not None and str(lat_str).strip() != ''
    has_lng = lng_str is not None and str(lng_str).strip() != ''

    if has_lat != has_lng:
        return Response({
            "success": False,
            "error": {
                "code": "INVALID_COORDINATES",
                "message": "Both latitude and longitude must be provided together."
            }
        }, status=status.HTTP_400_BAD_REQUEST)

    latitude = None
    longitude = None
    radius_km = default_radius_km
    if has_lat and has_lng:
        try:
            latitude = float(lat_str)
            longitude = float(lng_str)
            radius_km = float(params.get('radius_km') or params.get('radius') or default_radius_km)
        except ValueError:
            return Response({
                "success": False,
                "error": {
                    "code": "INVALID_COORDINATES",
                    "message": "Latitude, longitude, and radius_km must be valid floating point numbers."
                }
            }, status=status.HTTP_400_BAD_REQUEST)

        if latitude < -90.0 or latitude > 90.0:
            return Response({
                "success": False,
                "error": {
                    "code": "COORDINATE_OUT_OF_BOUNDS",
                    "message": "Latitude must be between -90.0 and 90.0 degrees."
                }
            }, status=status.HTTP_400_BAD_REQUEST)

        if longitude < -180.0 or longitude > 180.0:
            return Response({
                "success": False,
                "error": {
                    "code": "COORDINATE_OUT_OF_BOUNDS",
                    "message": "Longitude must be between -180.0 and 180.0 degrees."
                }
            }, status=status.HTTP_400_BAD_REQUEST)

        if radius_km <= 0:
            return Response({
                "success": False,
                "error": {
                    "code": "INVALID_RADIUS",
                    "message": "radius_km must be greater than zero."
                }
            }, status=status.HTTP_400_BAD_REQUEST)

    # 3. Sort Validation
    sort_by = (params.get('sort_by') or params.get('sort') or default_sort_by).strip().lower()
    if sort_by in ['nearest_first', 'distance', 'nearest', 'near_me'] and (latitude is None or longitude is None):
        return Response({
            "success": False,
            "error": {
                "code": "MISSING_COORDINATES",
                "message": "Sorting by nearest_first requires latitude and longitude parameters."
            }
        }, status=status.HTTP_400_BAD_REQUEST)

    # 4. Rating Filter Validation
    min_rating_str = params.get('min_rating')
    max_rating_str = params.get('max_rating')
    min_rating = None
    max_rating = None

    if min_rating_str is not None and str(min_rating_str).strip() != '':
        try:
            min_rating = float(min_rating_str)
        except ValueError:
            return Response({
                "success": False,
                "error": {
                    "code": "INVALID_RATING",
                    "message": "min_rating must be a valid number."
                }
            }, status=status.HTTP_400_BAD_REQUEST)
        if min_rating < 0.0 or min_rating > 5.0:
            return Response({
                "success": False,
                "error": {
                    "code": "INVALID_RATING_RANGE",
                    "message": "min_rating must be between 0.0 and 5.0."
                }
            }, status=status.HTTP_400_BAD_REQUEST)

    if max_rating_str is not None and str(max_rating_str).strip() != '':
        try:
            max_rating = float(max_rating_str)
        except ValueError:
            return Response({
                "success": False,
                "error": {
                    "code": "INVALID_RATING",
                    "message": "max_rating must be a valid number."
                }
            }, status=status.HTTP_400_BAD_REQUEST)
        if max_rating < 0.0 or max_rating > 5.0:
            return Response({
                "success": False,
                "error": {
                    "code": "INVALID_RATING_RANGE",
                    "message": "max_rating must be between 0.0 and 5.0."
                }
            }, status=status.HTTP_400_BAD_REQUEST)

    if min_rating is not None and max_rating is not None and min_rating > max_rating:
        return Response({
            "success": False,
            "error": {
                "code": "INVALID_RATING_RANGE",
                "message": "min_rating cannot be greater than max_rating."
            }
        }, status=status.HTTP_400_BAD_REQUEST)

    include_unrated = str(params.get('include_unrated', 'false')).strip().lower() in ['true', '1', 'yes']

    # 5. Price Filter Validation
    min_price_str = params.get('min_price')
    max_price_str = params.get('max_price') or params.get('price_max')
    min_price = None
    max_price = None

    if min_price_str is not None and str(min_price_str).strip() != '':
        try:
            min_price = float(min_price_str)
        except ValueError:
            return Response({
                "success": False,
                "error": {
                    "code": "INVALID_PRICE",
                    "message": "min_price must be a valid number."
                }
            }, status=status.HTTP_400_BAD_REQUEST)
        if min_price < 0:
            return Response({
                "success": False,
                "error": {
                    "code": "INVALID_PRICE_RANGE",
                    "message": "min_price cannot be negative."
                }
            }, status=status.HTTP_400_BAD_REQUEST)

    if max_price_str is not None and str(max_price_str).strip() != '':
        try:
            max_price = float(max_price_str)
        except ValueError:
            return Response({
                "success": False,
                "error": {
                    "code": "INVALID_PRICE",
                    "message": "max_price must be a valid number."
                }
            }, status=status.HTTP_400_BAD_REQUEST)
        if max_price < 0:
            return Response({
                "success": False,
                "error": {
                    "code": "INVALID_PRICE_RANGE",
                    "message": "max_price cannot be negative."
                }
            }, status=status.HTTP_400_BAD_REQUEST)

    if min_price is not None and max_price is not None and min_price > max_price:
        return Response({
            "success": False,
            "error": {
                "code": "INVALID_PRICE_RANGE",
                "message": "min_price cannot be greater than max_price."
            }
        }, status=status.HTTP_400_BAD_REQUEST)

    # 6. Dates & Occupancy Validation
    check_in_str = params.get('check_in')
    check_out_str = params.get('check_out')
    cin = None
    cout = None

    if check_in_str or check_out_str:
        if not check_in_str or not check_out_str:
            return Response({
                "success": False,
                "error": {
                    "code": "INVALID_DATES",
                    "message": "Both check_in and check_out dates must be provided."
                }
            }, status=status.HTTP_400_BAD_REQUEST)

        cin = parse_flexible_date(check_in_str)
        cout = parse_flexible_date(check_out_str)
        if not cin or not cout:
            return Response({
                "success": False,
                "error": {
                    "code": "INVALID_DATE_FORMAT",
                    "message": "Dates must be in YYYY-MM-DD format."
                }
            }, status=status.HTTP_400_BAD_REQUEST)

        if cout <= cin:
            return Response({
                "success": False,
                "error": {
                    "code": "INVALID_DATES",
                    "message": "check_out must be strictly after check_in."
                }
            }, status=status.HTTP_400_BAD_REQUEST)

    try:
        guests = int(params.get('guests', 1))
        rooms = int(params.get('rooms', 1))
        if guests < 1 or rooms < 1:
            raise ValueError()
    except ValueError:
        return Response({
            "success": False,
            "error": {
                "code": "INVALID_OCCUPANCY",
                "message": "guests and rooms must be positive integers."
            }
        }, status=status.HTTP_400_BAD_REQUEST)

    # Base QuerySet: only active, approved, non-deleted hotels
    base_qs = Hotel.objects.filter(
        is_deleted=False,
        is_approved=True,
        status=Hotel.STATUS_APPROVED,
        owner__is_blocked=False,
        owner__is_active=True
    ).select_related(
        'country_rel', 'state_rel', 'city_rel', 'area_rel', 'owner'
    ).prefetch_related(
        'rooms', 'rooms__amenities', 'rooms__calendar_blocks', 'images', 'amenities', 'reviews'
    )

    # Hierarchy Filters
    if area_id_int:
        base_qs = base_qs.filter(area_rel_id=area_id_int)
    if city_id_int:
        base_qs = base_qs.filter(city_rel_id=city_id_int)
    if state_id_int:
        base_qs = base_qs.filter(state_rel_id=state_id_int)
    if country_id_int:
        base_qs = base_qs.filter(country_rel_id=country_id_int)

    # Text search (city, area, destination, q, search)
    if not is_near_me_text_query:
        city_name = params.get('city')
        if city_name:
            base_qs = base_qs.filter(Q(city__icontains=city_name) | Q(city_rel__name__icontains=city_name))
        area_name = params.get('area')
        if area_name:
            base_qs = base_qs.filter(Q(area__icontains=area_name) | Q(area_rel__name__icontains=area_name))
        destination_name = params.get('destination')
        if destination_name:
            base_qs = base_qs.filter(destination__icontains=destination_name)
        if raw_search_query:
            clean_q = raw_search_query.split(',')[0].strip()
            tokens = extract_search_tokens(clean_q)
            sq = Q()
            sq |= Q(name__icontains=clean_q) | Q(city__icontains=clean_q) | Q(address__icontains=clean_q) | Q(area__icontains=clean_q)
            for t in tokens:
                sq |= Q(name__icontains=t) | Q(city__icontains=t) | Q(address__icontains=t) | Q(area__icontains=t)
            base_qs = base_qs.filter(sq)

    # Property Type
    property_type = params.get('property_type')
    if property_type:
        types = [t.strip().upper() for t in property_type.split(',') if t.strip()]
        if types:
            base_qs = base_qs.filter(property_type__in=types)

    # Amenities
    amenities_param = params.get('amenities')
    if amenities_param:
        amenity_list = [a.strip() for a in amenities_param.split(',') if a.strip()]
        for a_name in amenity_list:
            base_qs = base_qs.filter(
                Q(amenities__name__icontains=a_name) | Q(rooms__amenities__name__icontains=a_name)
            )

    # Radii to attempt: if auto_expand is True, expand up to 25km, 50km, 100km if 0 results
    radii_to_attempt = [radius_km]
    if auto_expand and latitude is not None and longitude is not None:
        for r_cand in [25.0, 50.0, 100.0]:
            if r_cand > radius_km:
                radii_to_attempt.append(r_cand)

    matching_hotels = []
    effective_radius_km = radius_km

    for current_radius in radii_to_attempt:
        current_qs = base_qs
        if latitude is not None and longitude is not None:
            current_qs = current_qs.filter(latitude__isnull=False, longitude__isnull=False)
            delta_lat = current_radius / 111.0
            cos_lat = math.cos(math.radians(latitude))
            delta_lng = current_radius / (111.0 * max(0.01, abs(cos_lat)))
            current_qs = current_qs.filter(
                latitude__gte=latitude - delta_lat,
                latitude__lte=latitude + delta_lat,
                longitude__gte=longitude - delta_lng,
                longitude__lte=longitude + delta_lng
            )

        candidate_hotels = list(current_qs.distinct())
        attempt_matches = []

        for h in candidate_hotels:
            # 1. Geosearch precise Haversine distance
            if latitude is not None and longitude is not None:
                if h.latitude is None or h.longitude is None:
                    continue
                dist = haversine_distance(latitude, longitude, h.latitude, h.longitude)
                if dist > current_radius:
                    continue
                h.distance_km = round(dist, 2)
            else:
                h.distance_km = None

            # 2. Rating & Review calculation
            vis_reviews = [r for r in h.reviews.all() if r.status == 'VISIBLE']
            h.calculated_review_count = len(vis_reviews)
            if h.calculated_review_count > 0:
                h.calculated_rating = round(sum(r.rating for r in vis_reviews) / h.calculated_review_count, 1)
            else:
                h.calculated_rating = None

            # Rating Filtering
            if min_rating is not None or max_rating is not None:
                if h.calculated_rating is None:
                    if not include_unrated:
                        continue
                else:
                    if min_rating is not None and h.calculated_rating < min_rating:
                        continue
                    if max_rating is not None and h.calculated_rating > max_rating:
                        continue

            # 3. Budget, Dynamic Date Pricing, Capacity & Real Inventory
            hotel_rooms = list(h.rooms.all())
            if not hotel_rooms:
                continue

            req_cap_per_room = max(1, (guests + rooms - 1) // rooms)

            if cin and cout:
                eligible_rooms = []
                for rm in hotel_rooms:
                    total_cap = (rm.capacity_adults or 0) + (rm.capacity_children or 0)
                    if total_cap < req_cap_per_room:
                        continue

                    avail_count = get_available_room_count(rm, cin, cout, include_holds=True)
                    if avail_count < rooms:
                        continue

                    stay_cost = 0.0
                    cur = cin
                    while cur < cout:
                        stay_cost += float(rm.get_price_for_date(cur))
                        cur += timedelta(days=1)
                    nights = (cout - cin).days
                    avg_nightly_price = round(stay_cost / max(1, nights), 2)
                    eligible_rooms.append((rm, avg_nightly_price, avail_count))

                if not eligible_rooms:
                    continue

                h.starting_price = min(item[1] for item in eligible_rooms)
                h.available_rooms_count = sum(item[2] for item in eligible_rooms)
            else:
                if guests > 1 or rooms > 1:
                    eligible_rooms = [
                        rm for rm in hotel_rooms
                        if ((rm.capacity_adults or 0) + (rm.capacity_children or 0)) >= req_cap_per_room
                        and (getattr(rm, 'total_rooms', 1) or 1) >= rooms
                    ]
                    if not eligible_rooms:
                        continue
                    h.starting_price = float(min(rm.price_per_night for rm in eligible_rooms))
                    h.available_rooms_count = sum(getattr(rm, 'total_rooms', 1) or 1 for rm in eligible_rooms)
                else:
                    h.starting_price = float(min(rm.price_per_night for rm in hotel_rooms))
                    h.available_rooms_count = sum(getattr(rm, 'total_rooms', 1) or 1 for rm in hotel_rooms)

            # Price Budget Filter
            if min_price is not None and h.starting_price < min_price:
                continue
            if max_price is not None and h.starting_price > max_price:
                continue

            attempt_matches.append(h)

        if attempt_matches:
            matching_hotels = attempt_matches
            effective_radius_km = current_radius
            break

    # Sorting
    if sort_by in ['price_low_to_high', 'price_low', 'price_asc']:
        matching_hotels.sort(key=lambda x: (x.starting_price, x.id))
    elif sort_by in ['price_high_to_low', 'price_high', 'price_desc']:
        matching_hotels.sort(key=lambda x: (-x.starting_price, x.id))
    elif sort_by in ['rating_high_to_low', 'rating', 'rating_desc']:
        matching_hotels.sort(key=lambda x: (-(x.calculated_rating or 0.0), -x.calculated_review_count, x.id))
    elif sort_by in ['nearest_first', 'distance', 'nearest', 'near_me']:
        matching_hotels.sort(key=lambda x: (x.distance_km if x.distance_km is not None else float('inf'), x.id))
    else:
        matching_hotels.sort(key=lambda x: (
            -(x.calculated_rating or 0.0),
            -x.calculated_review_count,
            -(x.star_rating or 0),
            -x.id
        ))

    total_count = len(matching_hotels)
    try:
        page = max(1, int(params.get('page', 1)))
    except ValueError:
        page = 1
    try:
        page_size = max(1, min(100, int(params.get('page_size', 10))))
    except ValueError:
        page_size = 10

    total_pages = max(1, math.ceil(total_count / page_size)) if total_count > 0 else 1
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paged_hotels = matching_hotels[start_idx:end_idx]

    results = []
    for h in paged_hotels:
        images_data = HotelImageSerializer(h.images.all(), many=True, context={'request': request}).data
        amenities_data = AmenitySerializer(h.amenities.all(), many=True).data
        results.append({
            "id": h.id,
            "name": h.name,
            "address": h.address or "",
            "city": h.city or (h.city_rel.name if h.city_rel else ""),
            "state": h.state or (h.state_rel.name if h.state_rel else ""),
            "country": h.country or (h.country_rel.name if h.country_rel else "India"),
            "area": h.area or (h.area_rel.name if h.area_rel else ""),
            "latitude": float(h.latitude) if h.latitude is not None else None,
            "longitude": float(h.longitude) if h.longitude is not None else None,
            "distance_km": h.distance_km,
            "starting_price": float(h.starting_price),
            "currency": "INR",
            "rating": h.calculated_rating,
            "review_count": h.calculated_review_count,
            "images": images_data,
            "amenities": amenities_data,
            "available_rooms_count": h.available_rooms_count
        })

    response_payload = {
        "success": True,
        "data": {
            "count": total_count,
            "total_pages": total_pages,
            "current_page": page,
            "results": results
        },
        "count": total_count,
        "results": results
    }

    if is_near_me:
        if total_count > 0:
            if effective_radius_km > radius_km:
                response_payload["message"] = f"No hotels found within {radius_km:.1f} km. Showing {total_count} hotels within {effective_radius_km:.1f} km of your location."
            else:
                response_payload["message"] = f"Found {total_count} hotels near your location (within {effective_radius_km:.1f} km)"
        else:
            response_payload["message"] = f"No hotels found near your location (within {effective_radius_km:.1f} km)."

    if latitude is not None and longitude is not None:
        response_payload["user_location"] = {
            "latitude": latitude,
            "longitude": longitude
        }
        response_payload["search_radius_km"] = effective_radius_km

    return Response(response_payload, status=status.HTTP_200_OK)


class HotelSearchAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return execute_hotel_search(request.query_params, request=request, is_near_me=False)


class HotelNearMeAPIView(APIView):
    """
    GET /api/hotels/near-me/
    Dedicated Near Me search endpoint for location-based hotel discovery.
    Automatically resolves coordinates, defaults to sorting by nearest first,
    and supports auto-expanding radius if no hotels are found within the initial radius.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return execute_hotel_search(
            request.query_params,
            request=request,
            is_near_me=True,
            default_radius_km=10.0,
            auto_expand=True
        )


class HotelDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Hotel.objects.all()
    permission_classes = [IsOwnerOrAdminOrReadOnly]

    def get_object(self):
        pk = self.kwargs.get('pk')
        hotel = Hotel.objects.filter(pk=pk, is_deleted=False).first()
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

        reason = request.data.get('reason') if hasattr(request, 'data') else None
        if not reason:
            reason = request.query_params.get('reason') or f"Deleted by {request.user.username}"

        # Capture complete snapshot of hotel and related entities before deletion
        snapshot_data = {
            "hotel_id": hotel.id,
            "name": hotel.name,
            "description": hotel.description,
            "property_type": hotel.property_type,
            "address": hotel.address,
            "city": hotel.city,
            "state": hotel.state,
            "country": hotel.country,
            "zip_code": hotel.zip_code,
            "star_rating": hotel.star_rating,
            "guest_rating": str(hotel.guest_rating),
            "check_in_time": hotel.check_in_time,
            "check_out_time": hotel.check_out_time,
            "rules": hotel.rules,
            "cancellation_policy": hotel.cancellation_policy,
            "child_policy": hotel.child_policy,
            "pet_policy": hotel.pet_policy,
            "payment_policy": hotel.payment_policy,
            "safety_info": hotel.safety_info,
            "nearby_attractions": hotel.nearby_attractions,
            "owner": {
                "id": hotel.owner.id if hotel.owner else None,
                "username": hotel.owner.username if hotel.owner else '',
                "email": hotel.owner.email if hotel.owner else '',
                "full_name": hotel.owner.get_full_name() if hotel.owner else '',
                "phone": getattr(hotel.owner, 'phone_number', '') if hotel.owner else ''
            },
            "amenities": [a.name for a in hotel.amenities.all()],
            "rooms": [
                {
                    "id": r.id,
                    "title": r.title,
                    "room_type": r.room_type,
                    "price_per_night": str(r.price_per_night),
                    "capacity": (r.capacity_adults or 0) + (r.capacity_children or 0),
                    "capacity_adults": r.capacity_adults,
                    "capacity_children": r.capacity_children,
                    "total_rooms": r.total_rooms,
                    "room_numbers": r.room_numbers,
                    "is_active": getattr(r, 'is_active', True),
                }
                for r in hotel.rooms.all()
            ],
            "images": [
                {
                    "id": img.id,
                    "image_url": img.get_image_display(),
                    "caption": img.caption,
                    "is_primary": img.is_primary
                }
                for img in hotel.images.all()
            ],
            "verification_documents": [
                {
                    "id": doc.id,
                    "document_type": doc.document_type,
                    "status": doc.status,
                    "document_url": doc.document_url or (doc.document_file.url if doc.document_file else ''),
                }
                for doc in hotel.verification_documents.all()
            ],
            "stats": {
                "total_past_bookings": hotel.bookings.count(),
                "total_rooms_count": hotel.rooms.count()
            }
        }

        # Safe Soft-Delete: Never cascade-delete historical bookings or payments
        hotel.is_deleted = True
        hotel.status = Hotel.STATUS_DELETED
        hotel.is_active = False
        hotel.is_approved = False
        hotel.deleted_at = timezone.now()
        hotel.deleted_by = request.user
        hotel.rejection_reason = reason
        # Hotel status and is_deleted govern active state for all associated rooms
        hotel.save(update_fields=['is_deleted', 'status', 'is_active', 'is_approved', 'deleted_at', 'deleted_by', 'rejection_reason', 'updated_at'])

        # Store in dedicated DeletedHotelArchive section
        archive, _ = DeletedHotelArchive.objects.update_or_create(
            hotel=hotel,
            defaults={
                "hotel_name": hotel.name,
                "city": hotel.city,
                "address": hotel.address,
                "property_type": hotel.property_type,
                "owner": hotel.owner,
                "owner_name": hotel.owner.get_full_name() or hotel.owner.username if hotel.owner else '',
                "owner_email": hotel.owner.email if hotel.owner else '',
                "owner_phone": getattr(hotel.owner, 'phone_number', '') if hotel.owner else '',
                "deleted_by": request.user,
                "deleted_by_name": request.user.get_full_name() or request.user.username,
                "deleted_by_role": str(getattr(request.user, 'role', '')).upper(),
                "deletion_reason": reason,
                "snapshot_data": snapshot_data,
                "is_restored": False,
            }
        )

        # Audit logging for Staff and Admin
        actor_role = str(getattr(request.user, 'role', '')).upper()
        if actor_role == 'STAFF':
            from staff.views import log_staff_activity
            profile = getattr(request.user, 'staff_profile', None)
            log_staff_activity(
                request=request,
                staff_profile=profile,
                actor_user=request.user,
                action="DELETE_HOTEL",
                entity_type="Hotel",
                entity_id=str(hotel.id),
                description=f"Staff deleted hotel '{hotel.name}' (ID {hotel.id}). Archived to Admin Deleted section."
            )

        return Response({
            "success": True,
            "message": f"Hotel '{hotel.name}' has been successfully deleted and archived to Admin Deleted section.",
            "hotel_id": hotel.id,
            "archive_id": archive.id,
            "deleted_at": hotel.deleted_at.isoformat()
        }, status=status.HTTP_200_OK)


class OwnerHotelListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return HotelCreateUpdateSerializer
        return HotelSerializer

    def get_queryset(self):
        return Hotel.objects.filter(owner=self.request.user, is_deleted=False).order_by('-created_at')

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
        owner_hotels = Hotel.objects.filter(owner=user, is_deleted=False)
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
            if hotel.owner != request.user and not is_platform_admin(request.user):
                return Response({"error": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

            hotel.status = Hotel.STATUS_SUBMITTED
            hotel.is_approved = False
            hotel.save()

            # Dispatch smart notification to Hotel Verification Department
            try:
                from staff.models import Department
                from staff.utils import create_staff_notification
                ver_dept = Department.objects.filter(code=Department.CODE_HOTEL_VERIFICATION).first()
                if ver_dept:
                    create_staff_notification(
                        department=ver_dept,
                        title=f"🏨 Hotel Verification Pending: {hotel.name}",
                        message=f"Hotel '{hotel.name}' was submitted by {request.user.username} for onboarding verification.",
                        notification_type='HOTEL_SUBMITTED',
                        metadata={'hotel_id': hotel.id}
                    )
            except Exception as notif_err:
                logger.warning(f"Failed to notify hotel verification department: {notif_err}")

            return Response({"message": f"Hotel '{hotel.name}' submitted for Admin review & approval.", "status": hotel.status}, status=status.HTTP_200_OK)
        except Hotel.DoesNotExist:
            return Response({"error": "Hotel not found."}, status=status.HTTP_404_NOT_FOUND)


class IsAdminOrHotelVerificationStaff(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if is_platform_admin(user) or user.is_superuser or getattr(user, 'role', '') in ['ADMIN', 'SUPER_ADMIN']:
            return True
        if getattr(user, 'role', '') == 'STAFF' or getattr(user, 'is_staff', False):
            profile = getattr(user, 'staff_profile', None)
            if profile and profile.is_active_account:
                dept_code = profile.department.code if profile.department else ''
                norm_dept = Department.normalize_code(dept_code)
                if norm_dept == Department.CODE_HOTEL_VERIFICATION:
                    return True
                if (profile.has_perm('VERIFY_HOTEL') or
                    profile.has_perm('VERIFY_HOTELS') or
                    profile.has_perm('APPROVE_HOTEL') or
                    check_staff_permission(user, 'VERIFY_HOTEL') or
                    check_staff_permission(user, 'APPROVE_HOTEL')):
                    return True
        return False

# Alias for backwards compatibility
IsAdminOrSuperAdmin = IsAdminOrHotelVerificationStaff

class AdminHotelApprovalView(APIView):
    permission_classes = [IsAdminOrHotelVerificationStaff]

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
            if hotel.owner != request.user and not is_platform_admin(request.user):
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
            is_admin_or_verification = is_platform_admin(request.user) or (
                getattr(request.user, 'role', '') == 'STAFF' and 
                getattr(getattr(request.user, 'staff_profile', None), 'department', None) and 
                getattr(request.user.staff_profile.department, 'code', '') == 'HOTEL_VERIFICATION'
            )
            if hotel.owner != request.user and not is_admin_or_verification:
                return Response({"error": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

            image = request.FILES.get('image')
            image_url = request.data.get('image_url') or request.data.get('url')
            caption = request.data.get('caption', '')
            is_primary_raw = request.data.get('is_primary', False)
            if isinstance(is_primary_raw, bool):
                is_primary = is_primary_raw
            else:
                is_primary = str(is_primary_raw).lower() in ['true', '1', 'yes']

            if not image and not image_url:
                return Response({"error": "Please provide an image file or image URL."}, status=status.HTTP_400_BAD_REQUEST)

            if is_primary:
                hotel.images.filter(is_primary=True).update(is_primary=False)

            hotel_image = HotelImage.objects.create(
                hotel=hotel,
                image=image,
                image_url=image_url,
                caption=caption,
                is_primary=is_primary
            )
            return Response(HotelImageSerializer(hotel_image).data, status=status.HTTP_201_CREATED)
        except Hotel.DoesNotExist:
            return Response({"error": "Hotel not found."}, status=status.HTTP_404_NOT_FOUND)


class HotelCitiesView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        try:
            cities_qs = Hotel.objects.filter(is_deleted=False).exclude(city__isnull=True).exclude(city__exact='').values_list('city', flat=True)
            unique_cities = sorted(list(set(str(c).strip().title() for c in cities_qs if c and str(c).strip())))
            return Response(unique_cities, status=status.HTTP_200_OK)
        except Exception as e:
            return Response([], status=status.HTTP_200_OK)


# =============================================================================
# ADMIN DELETED HOTELS SECTION (ISOLATED TO PLATFORM ADMIN)
# =============================================================================

class AdminDeletedHotelListView(generics.ListAPIView):
    """
    GET /api/admin/deleted-hotels/
    Platform Admin views all soft-deleted hotels in the dedicated archive section.
    Deleted hotels are strictly excluded from all public, owner, and staff portals.
    """
    permission_classes = [IsAdminUserRole]
    serializer_class = DeletedHotelArchiveListSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = DeletedHotelArchive.objects.all().order_by('-deleted_at')
        
        search = self.request.query_params.get('search') or self.request.query_params.get('q')
        if search:
            s = search.strip()
            qs = qs.filter(
                Q(hotel_name__icontains=s) |
                Q(city__icontains=s) |
                Q(owner_name__icontains=s) |
                Q(owner_email__icontains=s) |
                Q(deleted_by_name__icontains=s)
            )

        city = self.request.query_params.get('city')
        if city:
            qs = qs.filter(city__iexact=city.strip())

        prop_type = self.request.query_params.get('property_type')
        if prop_type:
            qs = qs.filter(property_type__iexact=prop_type.strip())

        is_restored = self.request.query_params.get('is_restored')
        if is_restored is not None:
            val = is_restored.lower() in ['true', '1', 'yes']
            qs = qs.filter(is_restored=val)

        return qs


class AdminDeletedHotelDetailView(APIView):
    """
    GET /api/admin/deleted-hotels/{id}/
    Platform Admin inspects full details and snapshot of a deleted hotel.
    Lookup supports either DeletedHotelArchive pk or original hotel_id.
    """
    permission_classes = [IsAdminUserRole]

    def get(self, request, pk):
        archive = DeletedHotelArchive.objects.filter(Q(pk=pk) | Q(hotel_id=pk)).first()
        if not archive:
            return Response(
                {"error": f"Deleted hotel record '{pk}' not found in archive."},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = DeletedHotelArchiveDetailSerializer(archive)
        return Response({
            "success": True,
            "archive": serializer.data,
            "data": serializer.data
        }, status=status.HTTP_200_OK)


class AdminDeletedHotelRestoreView(APIView):
    """
    POST /api/admin/deleted-hotels/{id}/restore/
    Platform Admin restores a deleted hotel back to active state.
    """
    permission_classes = [IsAdminUserRole]

    def post(self, request, pk):
        archive = DeletedHotelArchive.objects.filter(Q(pk=pk) | Q(hotel_id=pk)).first()
        if not archive:
            return Response(
                {"error": f"Deleted hotel record '{pk}' not found in archive."},
                status=status.HTTP_404_NOT_FOUND
            )

        hotel = archive.hotel
        from django.utils import timezone

        # Restore hotel
        hotel.is_deleted = False
        hotel.status = Hotel.STATUS_APPROVED
        hotel.is_active = True
        hotel.is_approved = True
        hotel.deleted_at = None
        hotel.deleted_by = None
        hotel.save(update_fields=['is_deleted', 'status', 'is_active', 'is_approved', 'deleted_at', 'deleted_by', 'updated_at'])

        # Update archive
        archive.is_restored = True
        archive.restored_at = timezone.now()
        archive.restored_by = request.user
        archive.save(update_fields=['is_restored', 'restored_at', 'restored_by'])

        return Response({
            "success": True,
            "message": f"Hotel '{hotel.name}' has been successfully restored to active status.",
            "hotel_id": hotel.id,
            "status": hotel.status,
            "is_active": hotel.is_active
        }, status=status.HTTP_200_OK)


