from rest_framework import serializers
from decimal import Decimal
from datetime import datetime
from .models import Booking
from rooms.models import Room
from rooms.utils import get_available_room_count
from hotels.serializers import HotelSerializer
from rooms.serializers import RoomSerializer

class BookingSerializer(serializers.ModelSerializer):
    hotel_id = serializers.IntegerField(source='hotel.id', read_only=True)
    hotel_name = serializers.CharField(source='hotel.name', read_only=True)
    room_id = serializers.IntegerField(source='room.id', read_only=True)
    room_name = serializers.CharField(source='room.title', read_only=True)
    room_title = serializers.CharField(source='room.title', read_only=True)
    hotel_details = HotelSerializer(source='hotel', read_only=True)
    room_details = RoomSerializer(source='room', read_only=True)
    customer_name = serializers.CharField(source='customer.get_full_name', read_only=True)

    payment_details = serializers.SerializerMethodField()
    user_review = serializers.SerializerMethodField()
    room_number = serializers.SerializerMethodField()
    room_allocation_status = serializers.SerializerMethodField()
    room_allocation_message = serializers.SerializerMethodField()
    cancellation_fee = serializers.SerializerMethodField()
    refund_status = serializers.SerializerMethodField()
    refund_amount = serializers.SerializerMethodField()
    refund_date = serializers.SerializerMethodField()
    original_payment_source = serializers.SerializerMethodField()
    razorpay_refund_id = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = (
            'id', 'booking_id', 'customer', 'customer_name', 'hotel', 'hotel_id', 'hotel_name', 'hotel_details',
            'room', 'room_id', 'room_name', 'room_title', 'room_details', 'room_number', 'room_allocation_status', 'room_allocation_message',
            'check_in', 'check_out', 'number_of_guests',
            'number_of_rooms', 'price_per_night', 'number_of_nights', 'subtotal',
            'cleaning_fee', 'service_fee', 'taxes', 'discount', 'total_amount', 'currency',
            'payment_status', 'booking_status', 'razorpay_order_id', 'payment_details', 'user_review',
            'guest_name', 'guest_email', 'guest_phone', 'meal_plan', 'estimated_arrival_time', 'special_requests',
            'cancellation_reason', 'cancellation_fee_percentage', 'cancellation_charge', 'cancellation_fee',
            'refundable_amount', 'refund_status', 'refund_amount', 'refund_date', 'original_payment_source', 'razorpay_refund_id',
            'cancellation_calculated_at', 'cancellation_breakdown', 'applied_cancellation_policy',
            'confirmed_at', 'confirmation_email_sent', 'confirmation_email_sent_at', 'confirmation_email_error',
            'created_at', 'updated_at'
        )
        read_only_fields = (
            'id', 'booking_id', 'customer', 'cancellation_fee_percentage', 'cancellation_charge', 'cancellation_fee',
            'refundable_amount', 'refund_status', 'refund_amount', 'refund_date', 'original_payment_source', 'razorpay_refund_id',
            'cancellation_calculated_at', 'cancellation_breakdown',
            'applied_cancellation_policy', 'created_at', 'updated_at'
        )

    def get_room_number(self, obj):
        # Room number is allocated and revealed strictly after confirmed payment
        if obj.payment_status == Booking.PAYMENT_PAID or obj.booking_status in [
            Booking.STATUS_CONFIRMED, Booking.STATUS_CHECKED_IN, Booking.STATUS_CHECKED_OUT, Booking.STATUS_COMPLETED
        ]:
            return obj.room_number
        return None

    def get_room_allocation_status(self, obj):
        if (obj.payment_status == Booking.PAYMENT_PAID or obj.booking_status == Booking.STATUS_CONFIRMED) and obj.room_number:
            return "ALLOCATED"
        return "PENDING_PAYMENT_CONFIRMATION"

    def get_room_allocation_message(self, obj):
        if (obj.payment_status == Booking.PAYMENT_PAID or obj.booking_status == Booking.STATUS_CONFIRMED) and obj.room_number:
            return f"Allocated Room {obj.room_number}"
        return "Room number will be allocated immediately upon payment confirmation."

    def get_user_review(self, obj):
        if hasattr(obj, 'review') and obj.review:
            return {
                'id': obj.review.id,
                'rating': obj.review.rating,
                'comment': obj.review.comment,
                'created_at': obj.review.created_at
            }
        return None

    def _get_captured_payment(self, obj):
        if not hasattr(obj, '_cached_captured_payment'):
            if hasattr(obj, '_prefetched_objects_cache') and 'payments' in obj._prefetched_objects_cache:
                payments = list(obj._prefetched_objects_cache['payments'])
                captured = next((p for p in payments if getattr(p, 'status', None) == 'CAPTURED'), None) or (payments[0] if payments else None)
                obj._cached_captured_payment = captured
            else:
                obj._cached_captured_payment = obj.payments.filter(status='CAPTURED').first() or obj.payments.first()
        return obj._cached_captured_payment

    def _get_latest_refund(self, obj):
        if not hasattr(obj, '_cached_latest_refund'):
            if hasattr(obj, '_prefetched_objects_cache') and 'refunds' in obj._prefetched_objects_cache:
                refunds = list(obj._prefetched_objects_cache['refunds'])
                from django.utils import timezone
                refunds.sort(key=lambda r: getattr(r, 'created_at', None) or timezone.now(), reverse=True)
                obj._cached_latest_refund = refunds[0] if refunds else None
            else:
                obj._cached_latest_refund = obj.refunds.order_by('-created_at').first()
        return obj._cached_latest_refund

    def get_payment_details(self, obj):
        captured_payment = self._get_captured_payment(obj)
        if captured_payment:
            return {
                'razorpay_payment_id': captured_payment.razorpay_payment_id,
                'razorpay_order_id': captured_payment.razorpay_order_id,
                'payment_method': captured_payment.payment_method or 'Razorpay Online',
                'status': captured_payment.status,
                'paid_at': captured_payment.paid_at,
            }
        return None

    def get_cancellation_fee(self, obj):
        return obj.cancellation_charge

    def get_refund_status(self, obj):
        refund = self._get_latest_refund(obj)
        if refund:
            return refund.status
        if obj.payment_status == Booking.PAYMENT_REFUNDED:
            return 'REFUNDED'
        elif obj.payment_status == Booking.PAYMENT_REFUND_PENDING:
            return 'REFUND_PENDING'
        return None

    def get_refund_amount(self, obj):
        refund = self._get_latest_refund(obj)
        if refund:
            return refund.amount
        return obj.refundable_amount

    def get_refund_date(self, obj):
        refund = self._get_latest_refund(obj)
        if refund and refund.processed_at:
            return refund.processed_at
        elif refund:
            return refund.created_at
        return None

    def get_original_payment_source(self, obj):
        captured_payment = self._get_captured_payment(obj)
        if captured_payment:
            return captured_payment.payment_method or 'Razorpay Online'
        return None

    def get_razorpay_refund_id(self, obj):
        if hasattr(obj, '_prefetched_objects_cache') and 'refunds' in obj._prefetched_objects_cache:
            refunds = [r for r in obj._prefetched_objects_cache['refunds'] if getattr(r, 'razorpay_refund_id', None)]
            from django.utils import timezone
            refunds.sort(key=lambda r: getattr(r, 'created_at', None) or timezone.now(), reverse=True)
            return refunds[0].razorpay_refund_id if refunds else None
        refund = obj.refunds.exclude(razorpay_refund_id__isnull=True).exclude(razorpay_refund_id='').order_by('-created_at').first()
        if refund:
            return refund.razorpay_refund_id
        return None

class BookingCreateSerializer(serializers.ModelSerializer):
    coupon_code = serializers.CharField(required=False, allow_blank=True, write_only=True)
    adults = serializers.IntegerField(required=False, write_only=True)
    children = serializers.IntegerField(required=False, write_only=True)

    class Meta:
        model = Booking
        fields = (
            'hotel', 'room', 'room_number', 'check_in', 'check_out', 'number_of_guests',
            'number_of_rooms', 'adults', 'children', 'guest_name', 'guest_email', 'guest_phone',
            'meal_plan', 'estimated_arrival_time', 'special_requests', 'discount',
            'coupon_code'
        )

    def validate(self, attrs):
        check_in = attrs.get('check_in')
        check_out = attrs.get('check_out')
        room = attrs.get('room')
        room_number = attrs.get('room_number')
        requested_rooms = attrs.get('number_of_rooms', 1)
        number_of_guests = attrs.get('number_of_guests')
        adults = attrs.get('adults')
        children = attrs.get('children')

        # Indian Hotel Booking Rules: Check-in/Check-out Validation
        from util.validators import validate_check_in_out_dates, clean_indian_phone, clean_email, validate_occupancy
        validate_check_in_out_dates(check_in, check_out)

        # Occupancy Validation across all 3 parts: Adults, Children, Rooms
        cleaned_occ = validate_occupancy(
            adults=adults,
            children=children,
            rooms=requested_rooms,
            total_guests=number_of_guests,
            room=room
        )
        attrs['number_of_rooms'] = cleaned_occ['rooms']
        attrs['number_of_guests'] = cleaned_occ['total_guests']
        requested_rooms = cleaned_occ['rooms']

        # Validate Guest Indian Mobile Number
        guest_phone = attrs.get('guest_phone')
        if guest_phone:
            attrs['guest_phone'] = clean_indian_phone(guest_phone)

        # Validate Guest Email
        guest_email = attrs.get('guest_email')
        if guest_email:
            attrs['guest_email'] = clean_email(guest_email)

        # Check if hotel owner account is blocked by admin
        if room.hotel and room.hotel.owner and (room.hotel.owner.is_blocked or not room.hotel.owner.is_active):
            raise serializers.ValidationError({
                "room": "This property is temporarily unavailable for reservations because the hotel owner account has been blocked by Platform Administration."
            })

        # Check if hotel is deleted
        if room.hotel and (room.hotel.is_deleted or room.hotel.status == 'DELETED' or not room.hotel.is_active):
            raise serializers.ValidationError({
                "room": "This hotel is no longer available for reservations."
            })

        # Real-time Date Overlap Concurrency Check
        available_count = get_available_room_count(room, check_in, check_out, include_holds=True)
        if available_count < requested_rooms:
            raise serializers.ValidationError({
                "room": "All rooms are booked for your selected dates. Please select different dates or another room category."
            })

        # Specific Room Preference (Physical room allocation is deferred until successful payment)
        if room_number:
            attrs['preferred_room_number'] = str(room_number).strip()

        # Server-side coupon verification if coupon_code provided during booking creation
        coupon_code = attrs.get('coupon_code')
        if coupon_code:
            from coupons.models import Coupon
            c_code = str(coupon_code).strip().upper()
            coupon = Coupon.objects.filter(code__iexact=c_code).first()
            if not coupon:
                raise serializers.ValidationError({
                    "coupon_code": f"Coupon code '{c_code}' does not exist or is invalid."
                })
            
            nights = (check_out - check_in).days if (check_in and check_out) else 1
            if nights < 1:
                nights = 1
            meal_plan = attrs.get('meal_plan', 'ROOM_ONLY')
            price_per_night = room.price_per_night if room else Decimal('0.00')
            meal_prices_dict = {
                'ROOM_ONLY': Decimal('0.00'),
                'BREAKFAST': Decimal('350.00'),
                'HALF_BOARD': Decimal('850.00'),
                'FULL_BOARD': Decimal('1400.00'),
            }
            meal_price_per_night = meal_prices_dict.get(meal_plan, Decimal('0.00'))
            subtotal_prov = (price_per_night + meal_price_per_night) * Decimal(str(nights)) * Decimal(str(requested_rooms))

            customer = self.context['request'].user if ('request' in self.context and self.context['request'].user.is_authenticated) else None
            is_valid, err_msg, calc_discount = coupon.validate_eligibility(
                user=customer,
                amount=subtotal_prov,
                check_in_date=check_in
            )
            if not is_valid:
                raise serializers.ValidationError({
                    "coupon_code": err_msg
                })
            attrs['discount'] = calc_discount
            attrs['applied_coupon_code'] = coupon.code

        return attrs

    def create(self, validated_data):
        customer = self.context['request'].user
        room = validated_data['room']
        check_in = validated_data['check_in']
        check_out = validated_data['check_out']
        validated_data.pop('adults', None)
        validated_data.pop('children', None)
        requested_rooms = validated_data.get('number_of_rooms', 1)
        applied_coupon_code = validated_data.pop('applied_coupon_code', None) or validated_data.pop('coupon_code', None)
        discount = Decimal(str(validated_data.get('discount', 0.00)))

        # Meal Plan Pricing Dictionary (matching frontend rates)
        MEAL_PRICES = {
            'ROOM_ONLY': Decimal('0.00'),
            'BREAKFAST': Decimal('350.00'),
            'HALF_BOARD': Decimal('850.00'),
            'FULL_BOARD': Decimal('1400.00'),
        }

        # Price Calculation Logic
        nights = (check_out - check_in).days
        if nights < 1:
            nights = 1

        meal_plan = validated_data.get('meal_plan', 'ROOM_ONLY')
        price_per_night = room.price_per_night
        meal_price_per_night = MEAL_PRICES.get(meal_plan, Decimal('0.00'))

        room_subtotal = price_per_night * nights * requested_rooms
        meal_subtotal = meal_price_per_night * nights * requested_rooms
        subtotal = room_subtotal + meal_subtotal

        taxes = subtotal * Decimal('0.18') # 18% GST Tax
        total_amount = max(Decimal('0.00'), subtotal + taxes - discount)

        # Physical room number allocation is deferred until payment is confirmed
        preferred_room_number = validated_data.pop('preferred_room_number', None)
        raw_room_number = validated_data.pop('room_number', None)
        if not preferred_room_number and raw_room_number:
            preferred_room_number = raw_room_number

        # Remove keys that are explicitly supplied
        validated_data.pop('discount', None)
        validated_data.pop('price_per_night', None)
        validated_data.pop('number_of_nights', None)
        validated_data.pop('subtotal', None)
        validated_data.pop('taxes', None)
        validated_data.pop('total_amount', None)
        validated_data.pop('booking_status', None)
        validated_data.pop('payment_status', None)
        validated_data.pop('customer', None)

        booking = Booking.objects.create(
            customer=customer,
            price_per_night=price_per_night,
            number_of_nights=nights,
            subtotal=subtotal,
            taxes=taxes,
            discount=discount,
            total_amount=total_amount,
            booking_status=Booking.STATUS_PENDING_PAYMENT,
            payment_status=Booking.PAYMENT_PENDING,
            room_number=None,
            **validated_data
        )
        if preferred_room_number:
            booking.preferred_room_number = preferred_room_number
        if applied_coupon_code:
            booking.applied_coupon_code = applied_coupon_code
        return booking

