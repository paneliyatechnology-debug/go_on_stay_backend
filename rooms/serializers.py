from rest_framework import serializers
from .models import Room, RoomImage, RoomCalendarBlock
from hotels.serializers import AmenitySerializer
from .utils import get_available_room_count, get_room_numbers_availability

class RoomImageSerializer(serializers.ModelSerializer):
    display_url = serializers.SerializerMethodField()

    class Meta:
        model = RoomImage
        fields = ('id', 'image', 'image_url', 'display_url', 'is_primary')

    def get_display_url(self, obj):
        return obj.get_image_display()

class RoomCalendarBlockSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoomCalendarBlock
        fields = ('id', 'room', 'date', 'custom_price', 'is_blocked', 'block_reason')

class RoomSerializer(serializers.ModelSerializer):
    images = RoomImageSerializer(many=True, read_only=True)
    amenities = AmenitySerializer(many=True, read_only=True)
    hotel_name = serializers.CharField(source='hotel.name', read_only=True)
    hotel_city = serializers.CharField(source='hotel.city', read_only=True)
    primary_image = serializers.SerializerMethodField()
    available_count = serializers.SerializerMethodField()
    remaining = serializers.SerializerMethodField()
    is_available = serializers.SerializerMethodField()
    available = serializers.SerializerMethodField()
    all_room_numbers = serializers.SerializerMethodField()
    room_numbers_status = serializers.SerializerMethodField()
    calendar_blocks = RoomCalendarBlockSerializer(many=True, read_only=True)

    class Meta:
        model = Room
        fields = (
            'id', 'hotel', 'hotel_name', 'hotel_city', 'room_type', 'meal_plan',
            'title', 'description', 'price_per_night', 'weekend_price', 'seasonal_price',
            'extra_guest_price', 'child_price', 'capacity_adults', 'capacity_children',
            'room_size_sqft', 'bed_type', 'number_of_beds', 'breakfast_included',
            'free_cancellation', 'total_rooms', 'room_numbers', 'all_room_numbers',
            'available_count', 'remaining', 'is_available', 'available', 'room_numbers_status',
            'amenities', 'images', 'primary_image', 'calendar_blocks',
            'created_at', 'updated_at'
        )

    def get_primary_image(self, obj):
        primary = obj.images.filter(is_primary=True).first() or obj.images.first()
        if primary:
            return primary.get_image_display()
        return "https://images.unsplash.com/photo-1611892440504-42a792e24d32?auto=format&fit=crop&w=800&q=80"

    def _get_avail(self, obj):
        check_in = self.context.get('check_in')
        check_out = self.context.get('check_out')
        cache_attr = f"_avail_{check_in}_{check_out}"
        if not hasattr(obj, cache_attr):
            setattr(obj, cache_attr, get_available_room_count(obj, check_in, check_out))
        return getattr(obj, cache_attr)

    def get_available_count(self, obj):
        return self._get_avail(obj)

    def get_remaining(self, obj):
        return self._get_avail(obj)

    def get_is_available(self, obj):
        check_in = self.context.get('check_in')
        check_out = self.context.get('check_out')
        if check_in and check_out:
            return self._get_avail(obj) > 0
        total = getattr(obj, 'total_rooms', getattr(obj, 'total_units', 1))
        return total > 0

    def get_available(self, obj):
        return self.get_is_available(obj)

    def get_all_room_numbers(self, obj):
        return obj.get_all_room_numbers()

    def get_room_numbers_status(self, obj):
        check_in = self.context.get('check_in')
        check_out = self.context.get('check_out')
        return get_room_numbers_availability(obj, check_in, check_out)

class RoomCreateUpdateSerializer(serializers.ModelSerializer):
    amenity_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False
    )

    class Meta:
        model = Room
        fields = (
            'id', 'hotel', 'room_type', 'meal_plan', 'title', 'description',
            'price_per_night', 'weekend_price', 'seasonal_price',
            'extra_guest_price', 'child_price', 'capacity_adults',
            'capacity_children', 'room_size_sqft', 'bed_type', 'number_of_beds',
            'breakfast_included', 'free_cancellation', 'total_rooms',
            'room_numbers', 'amenity_ids'
        )
        read_only_fields = ('id',)
        extra_kwargs = {
            'room_type': {'required': False},
            'meal_plan': {'required': False},
            'description': {'required': False, 'allow_blank': True, 'allow_null': True},
            'weekend_price': {'required': False, 'allow_null': True},
            'seasonal_price': {'required': False, 'allow_null': True},
            'extra_guest_price': {'required': False},
            'child_price': {'required': False},
            'capacity_adults': {'required': False},
            'capacity_children': {'required': False},
            'room_size_sqft': {'required': False},
            'bed_type': {'required': False},
            'number_of_beds': {'required': False},
            'breakfast_included': {'required': False},
            'free_cancellation': {'required': False},
            'total_rooms': {'required': False},
            'room_numbers': {'required': False, 'allow_blank': True, 'allow_null': True},
        }

    def to_internal_value(self, data):
        data = data.copy() if hasattr(data, 'copy') else dict(data)
        if 'name' in data and not data.get('title'):
            data['title'] = data['name']
        if 'total_units' in data and not data.get('total_rooms'):
            data['total_rooms'] = data['total_units']
        if 'capacity' in data and not data.get('capacity_adults'):
            data['capacity_adults'] = data['capacity']
        if 'hotel_id' in data and not data.get('hotel'):
            data['hotel'] = data['hotel_id']
        return super().to_internal_value(data)

    def validate(self, attrs):
        if not self.instance:
            if not attrs.get('hotel'):
                raise serializers.ValidationError({"hotel": "Hotel is required."})
            if not attrs.get('title'):
                raise serializers.ValidationError({"title": "Room name / title is required."})
        
        price = attrs.get('price_per_night')
        if price is not None and price <= 0:
            raise serializers.ValidationError({"price_per_night": "Price per night must be greater than zero."})

        capacity = attrs.get('capacity_adults')
        if capacity is not None and capacity < 1:
            raise serializers.ValidationError({"capacity_adults": "Capacity must be at least 1 guest."})

        total = attrs.get('total_rooms')
        if total is not None and total < 1:
            raise serializers.ValidationError({"total_rooms": "Total rooms must be at least 1."})

        return attrs

    def create(self, validated_data):
        amenity_ids = validated_data.pop('amenity_ids', [])
        room = Room.objects.create(**validated_data)
        if amenity_ids:
            room.amenities.set(amenity_ids)
        return room

    def update(self, instance, validated_data):
        amenity_ids = validated_data.pop('amenity_ids', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if amenity_ids is not None:
            instance.amenities.set(amenity_ids)
        return instance
