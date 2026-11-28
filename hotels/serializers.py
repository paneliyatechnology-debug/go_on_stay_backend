from rest_framework import serializers
from .models import Hotel, HotelImage, Amenity, HotelVerificationDocument, HotelStaff, DeletedHotelArchive
from django.db.models import Min
from users.serializers import UserSerializer
from util.validators import (
    validate_hotel_name,
    validate_hotel_address,
    validate_indian_pincode,
    validate_city_or_state,
)

class AmenitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Amenity
        fields = ('id', 'name', 'icon_name', 'category')

class HotelImageSerializer(serializers.ModelSerializer):
    display_url = serializers.SerializerMethodField()

    class Meta:
        model = HotelImage
        fields = ('id', 'image', 'image_url', 'display_url', 'caption', 'is_primary')

    def get_display_url(self, obj):
        return obj.get_image_display()

class HotelVerificationDocumentSerializer(serializers.ModelSerializer):
    document_display_type = serializers.CharField(source='get_document_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    document_file = serializers.SerializerMethodField()

    class Meta:
        model = HotelVerificationDocument
        fields = ('id', 'hotel', 'document_type', 'document_display_type', 'document_url', 'document_file', 'status', 'status_display', 'rejection_reason', 'created_at')
        read_only_fields = ('id', 'created_at')

    def get_document_file(self, obj):
        if not obj.document_file:
            return None
        # Return secure authenticated download endpoint rather than internal disk path
        return f"/api/hotels/{obj.hotel_id}/documents/{obj.id}/download/"

class HotelStaffSerializer(serializers.ModelSerializer):
    user_details = UserSerializer(source='user', read_only=True)

    class Meta:
        model = HotelStaff
        fields = ('id', 'hotel', 'user', 'user_details', 'role_title', 'can_manage_bookings', 'can_manage_rooms', 'can_checkin_checkout', 'created_at')
        read_only_fields = ('id', 'created_at')

class HotelSerializer(serializers.ModelSerializer):
    images = HotelImageSerializer(many=True, read_only=True)
    amenities = AmenitySerializer(many=True, read_only=True)
    owner_name = serializers.SerializerMethodField()
    owner_email = serializers.SerializerMethodField()
    owner_phone = serializers.SerializerMethodField()
    owner_is_blocked = serializers.SerializerMethodField()
    starting_price = serializers.SerializerMethodField()
    primary_image = serializers.SerializerMethodField()
    verification_documents = HotelVerificationDocumentSerializer(many=True, read_only=True)
    guest_rating = serializers.SerializerMethodField()
    reviews_count = serializers.SerializerMethodField()
    is_available = serializers.SerializerMethodField()
    available_rooms_count = serializers.SerializerMethodField()

    class Meta:
        model = Hotel
        fields = (
            'id', 'owner', 'owner_name', 'owner_email', 'owner_phone', 'owner_is_blocked', 'name', 'description', 'property_type',
            'address', 'city', 'state', 'zip_code', 'country', 'area', 'landmark',
            'destination', 'latitude', 'longitude', 'star_rating', 'guest_rating', 'reviews_count',
            'check_in_time', 'check_out_time', 'rules', 'cancellation_policy',
            'child_policy', 'pet_policy', 'smoking_policy', 'payment_policy',
            'safety_info', 'nearby_attractions', 'status', 'rejection_reason',
            'amenities', 'images', 'starting_price', 'primary_image', 'is_approved',
            'is_available', 'available_rooms_count',
            'verification_documents', 'created_at', 'updated_at'
        )
        read_only_fields = ('id', 'owner', 'created_at', 'updated_at')

    def _get_hotel_room_availabilities(self, obj):
        check_in = self.context.get('check_in')
        check_out = self.context.get('check_out')
        cache_attr = f"_hotel_room_avails_{check_in}_{check_out}"
        if not hasattr(obj, cache_attr):
            from rooms.utils import get_available_room_count
            if hasattr(obj, '_prefetched_objects_cache') and 'rooms' in obj._prefetched_objects_cache:
                rooms = list(obj._prefetched_objects_cache['rooms'])
            else:
                rooms = list(obj.rooms.all())
            if not rooms:
                setattr(obj, cache_attr, (True, 0))
            elif not check_in or not check_out:
                total_units = sum(getattr(r, 'total_rooms', getattr(r, 'total_units', 1)) for r in rooms)
                setattr(obj, cache_attr, (total_units > 0, total_units))
            else:
                counts = [get_available_room_count(r, check_in, check_out) for r in rooms]
                total_avail = sum(counts)
                is_avail = any(c > 0 for c in counts)
                setattr(obj, cache_attr, (is_avail, total_avail))
        return getattr(obj, cache_attr)

    def get_is_available(self, obj):
        is_avail, _ = self._get_hotel_room_availabilities(obj)
        return is_avail

    def get_available_rooms_count(self, obj):
        _, total_avail = self._get_hotel_room_availabilities(obj)
        return total_avail

    def get_owner_is_blocked(self, obj):
        return bool(obj.owner and obj.owner.is_blocked)

    def get_guest_rating(self, obj):
        if hasattr(obj, 'avg_rating') and obj.avg_rating is not None:
            return round(float(obj.avg_rating), 1)
        if hasattr(obj, 'calculated_rating') and obj.calculated_rating is not None:
            return round(float(obj.calculated_rating), 1)
        if hasattr(obj, '_prefetched_objects_cache') and 'reviews' in obj._prefetched_objects_cache:
            visible_revs = [r for r in obj._prefetched_objects_cache['reviews'] if getattr(r, 'status', '') == 'VISIBLE']
            if visible_revs:
                ratings = [r.rating for r in visible_revs if getattr(r, 'rating', None) is not None]
                if ratings:
                    return round(float(sum(ratings) / len(ratings)), 1)
            return None
        from django.db.models import Avg
        avg_val = obj.reviews.filter(status='VISIBLE').aggregate(Avg('rating'))['rating__avg']
        if avg_val is not None:
            return round(float(avg_val), 1)
        return None

    def get_reviews_count(self, obj):
        if hasattr(obj, 'num_reviews') and obj.num_reviews is not None:
            return int(obj.num_reviews)
        if hasattr(obj, 'calculated_review_count') and obj.calculated_review_count is not None:
            return int(obj.calculated_review_count)
        if hasattr(obj, '_prefetched_objects_cache') and 'reviews' in obj._prefetched_objects_cache:
            return sum(1 for r in obj._prefetched_objects_cache['reviews'] if getattr(r, 'status', '') == 'VISIBLE')
        return obj.reviews.filter(status='VISIBLE').count()

    def get_owner_name(self, obj):
        if not obj.owner:
            return "N/A"
        full_name = obj.owner.get_full_name().strip()
        if full_name:
            return full_name
        return obj.owner.first_name or obj.owner.username or f"Owner #{obj.owner.id}"

    def get_owner_email(self, obj):
        return obj.owner.email if obj.owner else ""

    def get_owner_phone(self, obj):
        return obj.owner.phone_number if obj.owner else ""

    def get_starting_price(self, obj):
        if hasattr(obj, 'starting_price') and obj.starting_price is not None:
            return float(obj.starting_price)
        if hasattr(obj, '_prefetched_objects_cache') and 'rooms' in obj._prefetched_objects_cache:
            rooms = obj._prefetched_objects_cache['rooms']
            if rooms:
                prices = [r.price_per_night for r in rooms if r.price_per_night is not None]
                if prices:
                    return float(min(prices))
        min_price = obj.rooms.aggregate(Min('price_per_night'))['price_per_night__min']
        return min_price or 2500.00

    def get_primary_image(self, obj):
        if hasattr(obj, '_prefetched_objects_cache') and 'images' in obj._prefetched_objects_cache:
            images = obj._prefetched_objects_cache['images']
            primary = next((img for img in images if getattr(img, 'is_primary', False)), None) or (images[0] if images else None)
            if primary:
                return primary.get_image_display()
        else:
            primary = obj.images.filter(is_primary=True).first() or obj.images.first()
            if primary:
                return primary.get_image_display()
        
        DEFAULT_HOTEL_IMAGES = [
            'https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=800&q=80',
            'https://images.unsplash.com/photo-1582719478250-c89cae4dc85b?auto=format&fit=crop&w=800&q=80',
            'https://images.unsplash.com/photo-1571896349842-33c89424de2d?auto=format&fit=crop&w=800&q=80',
            'https://images.unsplash.com/photo-1542314831-068cd1dbfeeb?auto=format&fit=crop&w=800&q=80',
            'https://images.unsplash.com/photo-1520250497591-112f2f40a3f4?auto=format&fit=crop&w=800&q=80',
            'https://images.unsplash.com/photo-1512343879784-a960bf40e7f2?auto=format&fit=crop&w=800&q=80',
            'https://images.unsplash.com/photo-1571003123894-1f0594d2b5d9?auto=format&fit=crop&w=800&q=80',
            'https://images.unsplash.com/photo-1566665797739-1674de7a421a?auto=format&fit=crop&w=800&q=80',
        ]
        img_idx = (obj.id or 0) % len(DEFAULT_HOTEL_IMAGES)
        return DEFAULT_HOTEL_IMAGES[img_idx]

    def validate_name(self, value):
        if value:
            return validate_hotel_name(value)
        return value

    def validate_address(self, value):
        if value:
            return validate_hotel_address(value)
        return value

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        request = self.context.get('request')
        user = getattr(request, 'user', None) if request else None

        # Determine authorization: owner, platform admin, or assigned staff
        is_owner = bool(user and user.is_authenticated and instance.owner_id == user.id)
        role = str(getattr(user, 'role', '')).upper() if user else ''
        is_admin_or_staff = bool(
            user and user.is_authenticated and (
                getattr(user, 'is_superuser', False) or
                getattr(user, 'is_staff', False) or
                role in ['ADMIN', 'SUPER_ADMIN', 'STAFF']
            )
        )

        # Least-privilege PII redaction: Anonymous visitors and other customers
        # must never receive the owner's private email, phone, or internal verification documents
        if not (is_owner or is_admin_or_staff):
            ret['owner_email'] = ''
            ret['owner_phone'] = ''
            ret['verification_documents'] = []
            ret['rejection_reason'] = None
            ret['owner_is_blocked'] = False

        return ret

class HotelCreateUpdateSerializer(serializers.ModelSerializer):
    amenity_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False
    )

    class Meta:
        model = Hotel
        fields = (
            'id', 'name', 'description', 'property_type', 'address', 'city', 'state',
            'zip_code', 'country', 'area', 'landmark', 'destination',
            'latitude', 'longitude', 'star_rating', 'check_in_time', 'check_out_time',
            'rules', 'cancellation_policy', 'child_policy', 'pet_policy',
            'smoking_policy', 'payment_policy', 'safety_info', 'nearby_attractions',
            'amenity_ids', 'status',
        )
        read_only_fields = ('id',)
        extra_kwargs = {
            'property_type': {'required': False},
            'zip_code': {'required': False, 'allow_blank': True, 'allow_null': True},
            'country': {'required': False},
            'area': {'required': False, 'allow_blank': True, 'allow_null': True},
            'landmark': {'required': False, 'allow_blank': True, 'allow_null': True},
            'destination': {'required': False, 'allow_blank': True, 'allow_null': True},
            'latitude': {'required': False},
            'longitude': {'required': False},
            'star_rating': {'required': False},
            'check_in_time': {'required': False},
            'check_out_time': {'required': False},
            'rules': {'required': False, 'allow_blank': True, 'allow_null': True},
            'cancellation_policy': {'required': False, 'allow_blank': True, 'allow_null': True},
            'child_policy': {'required': False, 'allow_blank': True, 'allow_null': True},
            'pet_policy': {'required': False, 'allow_blank': True, 'allow_null': True},
            'smoking_policy': {'required': False, 'allow_blank': True, 'allow_null': True},
            'payment_policy': {'required': False, 'allow_blank': True, 'allow_null': True},
            'safety_info': {'required': False, 'allow_blank': True, 'allow_null': True},
            'nearby_attractions': {'required': False, 'allow_blank': True, 'allow_null': True},
            'status': {'required': False},
        }

    def validate_name(self, value):
        return validate_hotel_name(value)

    def validate_address(self, value):
        return validate_hotel_address(value)

    def validate_city(self, value):
        if value:
            return validate_city_or_state(value, "City")
        return value

    def validate_state(self, value):
        if value:
            return validate_city_or_state(value, "State")
        return value

    def validate_zip_code(self, value):
        if value:
            return validate_indian_pincode(value)
        return value

    def validate(self, attrs):
        if not self.instance:
            if not attrs.get('name'):
                raise serializers.ValidationError({"name": "Hotel name is required."})
            if not attrs.get('city'):
                raise serializers.ValidationError({"city": "City is required."})
            if not attrs.get('address'):
                raise serializers.ValidationError({"address": "Property address is required."})
            star_rating = attrs.get('star_rating')
            if star_rating is not None and (star_rating < 1 or star_rating > 5):
                raise serializers.ValidationError({"star_rating": "Star rating must be between 1 and 5."})
        return attrs

    def create(self, validated_data):
        amenity_ids = validated_data.pop('amenity_ids', [])
        hotel = Hotel.objects.create(**validated_data)
        if amenity_ids:
            hotel.amenities.set(amenity_ids)
        return hotel

    def update(self, instance, validated_data):
        amenity_ids = validated_data.pop('amenity_ids', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if amenity_ids is not None:
            instance.amenities.set(amenity_ids)
        return instance


class DeletedHotelArchiveListSerializer(serializers.ModelSerializer):
    rooms_count = serializers.SerializerMethodField()
    images_count = serializers.SerializerMethodField()

    class Meta:
        model = DeletedHotelArchive
        fields = [
            'id', 'hotel_id', 'hotel_name', 'city', 'address', 'property_type',
            'owner_name', 'owner_email', 'owner_phone',
            'deleted_by_name', 'deleted_by_role', 'deleted_at', 'deletion_reason',
            'is_restored', 'restored_at', 'rooms_count', 'images_count'
        ]

    def get_rooms_count(self, obj):
        snapshot_rooms = obj.snapshot_data.get('rooms', [])
        if snapshot_rooms:
            return len(snapshot_rooms)
        if obj.hotel:
            return obj.hotel.rooms.count()
        return 0

    def get_images_count(self, obj):
        snapshot_images = obj.snapshot_data.get('images', [])
        if snapshot_images:
            return len(snapshot_images)
        if obj.hotel:
            return obj.hotel.images.count()
        return 0


class DeletedHotelArchiveDetailSerializer(serializers.ModelSerializer):
    rooms_count = serializers.SerializerMethodField()
    images_count = serializers.SerializerMethodField()

    class Meta:
        model = DeletedHotelArchive
        fields = [
            'id', 'hotel_id', 'hotel_name', 'city', 'address', 'property_type',
            'owner_name', 'owner_email', 'owner_phone',
            'deleted_by_name', 'deleted_by_role', 'deleted_at', 'deletion_reason',
            'snapshot_data', 'is_restored', 'restored_at', 'rooms_count', 'images_count'
        ]

    def get_rooms_count(self, obj):
        snapshot_rooms = obj.snapshot_data.get('rooms', [])
        if snapshot_rooms:
            return len(snapshot_rooms)
        if obj.hotel:
            return obj.hotel.rooms.count()
        return 0

    def get_images_count(self, obj):
        snapshot_images = obj.snapshot_data.get('images', [])
        if snapshot_images:
            return len(snapshot_images)
        if obj.hotel:
            return obj.hotel.images.count()
        return 0

