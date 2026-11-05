from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from datetime import datetime
import re
from .models import Room, RoomImage, RoomCalendarBlock
from .serializers import RoomSerializer, RoomCreateUpdateSerializer, RoomImageSerializer, RoomCalendarBlockSerializer
from .utils import get_available_room_count, get_room_numbers_availability
from hotels.models import Hotel
from util.validators import parse_flexible_date

class RoomListView(generics.ListCreateAPIView):
    queryset = Room.objects.all().order_by('price_per_night')
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return RoomCreateUpdateSerializer
        return RoomSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['check_in'] = self.request.query_params.get('check_in')
        context['check_out'] = self.request.query_params.get('check_out')
        return context

    def perform_create(self, serializer):
        hotel = serializer.validated_data['hotel']
        if hotel.owner != self.request.user and not self.request.user.is_staff:
            raise permissions.PermissionDenied("You do not own this hotel property.")
        serializer.save()

class IsRoomOwnerOrAdminOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.hotel.owner == request.user or request.user.is_staff or getattr(request.user, 'role', '') in ['ADMIN', 'SUPER_ADMIN']

class RoomDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Room.objects.all()
    permission_classes = [IsRoomOwnerOrAdminOrReadOnly]

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return RoomCreateUpdateSerializer
        return RoomSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['check_in'] = self.request.query_params.get('check_in')
        context['check_out'] = self.request.query_params.get('check_out')
        return context

    def destroy(self, request, *args, **kwargs):
        room = self.get_object()
        from bookings.models import Booking
        from django.utils import timezone
        today = timezone.now().date()
        active_bookings = Booking.objects.filter(
            room=room,
            booking_status__in=[Booking.STATUS_CONFIRMED, Booking.STATUS_CHECKED_IN],
            check_out__gte=today
        )
        if active_bookings.exists():
            return Response(
                {"error": "Cannot delete room with active upcoming reservations."},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().destroy(request, *args, **kwargs)

class RoomsByHotelView(generics.ListAPIView):
    serializer_class = RoomSerializer
    permission_classes = [permissions.AllowAny]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['check_in'] = self.request.query_params.get('check_in')
        context['check_out'] = self.request.query_params.get('check_out')
        return context

    def get_queryset(self):
        hotel_id = self.kwargs['hotel_id']
        queryset = Room.objects.filter(hotel_id=hotel_id).order_by('price_per_night')

        check_in = self.request.query_params.get('check_in')
        check_out = self.request.query_params.get('check_out')
        requested_rooms = int(self.request.query_params.get('rooms', 1))
        available_only = self.request.query_params.get('available_only', 'false').lower() in ['true', '1']

        # Only filter out rooms if available_only=true is explicitly requested.
        # Otherwise return all rooms, with their exact availability fields computed in RoomSerializer!
        if check_in and check_out and available_only:
            cin = parse_flexible_date(check_in)
            cout = parse_flexible_date(check_out)
            if cin and cout:
                valid_room_ids = []
                for room in queryset:
                    available = get_available_room_count(room, cin, cout)
                    if available >= requested_rooms:
                        valid_room_ids.append(room.id)
                queryset = queryset.filter(id__in=valid_room_ids)

        return queryset

class CheckAvailabilityView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from bookings.models import Booking
        room_id = request.query_params.get('room_id')
        hotel_id = request.query_params.get('hotel_id')
        check_in = request.query_params.get('check_in')
        check_out = request.query_params.get('check_out')
        requested_rooms = int(request.query_params.get('rooms', 1))
        requested_room_number = request.query_params.get('room_number')

        if not check_in or not check_out or (not room_id and not hotel_id):
            return Response(
                {"error": "Either 'room_id' or 'hotel_id', along with 'check_in' and 'check_out', must be provided."},
                status=status.HTTP_400_BAD_REQUEST
            )

        cin = parse_flexible_date(check_in)
        cout = parse_flexible_date(check_out)
        if not cin or not cout:
            return Response(
                {"error": f"Invalid check_in ('{check_in}') or check_out ('{check_out}') date format. Use YYYY-MM-DD or DD-MM-YYYY."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if cout <= cin:
            return Response(
                {"error": "check_out must be strictly after check_in."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Case A: Query availability for ALL rooms under a Hotel (TASK-09 & Room-wise check)
        if hotel_id:
            try:
                hotel = Hotel.objects.get(id=hotel_id)
            except (Hotel.DoesNotExist, ValueError):
                return Response({"error": f"Hotel with id '{hotel_id}' not found."}, status=status.HTTP_404_NOT_FOUND)

            rooms_qs = Room.objects.filter(hotel=hotel).order_by('price_per_night')
            rooms_availability = []
            for r in rooms_qs:
                available_count = get_available_room_count(r, cin, cout)
                is_available = available_count >= requested_rooms
                room_nums_status = get_room_numbers_availability(r, cin, cout)

                rooms_availability.append({
                    "room_id": r.id,
                    "name": r.title,
                    "title": r.title,
                    "room_type": r.room_type,
                    "price_per_night": float(r.price_per_night),
                    "available": is_available,
                    "is_available": is_available,
                    "remaining": available_count,
                    "available_count": available_count,
                    "total_rooms": r.total_rooms,
                    "room_numbers": room_nums_status,
                })

            # Hotel-level availability is TRUE if at least ONE room is available!
            # The entire hotel is NEVER marked unavailable as long as another room is bookable.
            hotel_is_available = any(r["is_available"] for r in rooms_availability)
            total_available = sum(r["remaining"] for r in rooms_availability)

            return Response({
                "hotel_id": hotel.id,
                "hotel_name": hotel.name,
                "check_in": str(cin),
                "check_out": str(cout),
                "requested_rooms": requested_rooms,
                "available": hotel_is_available,
                "is_available": hotel_is_available,
                "total_available_rooms": total_available,
                "available_rooms_count": total_available,
                "rooms": rooms_availability,
                "message": "Rooms available for booking!" if hotel_is_available else "All rooms in this hotel are booked for requested dates."
            }, status=status.HTTP_200_OK)

        # Case B: Query availability for a specific Room
        try:
            room = Room.objects.get(id=room_id)
            available_count = get_available_room_count(room, cin, cout)
            is_available = available_count >= requested_rooms
            room_numbers_status = get_room_numbers_availability(room, cin, cout)

            resp_data = {
                "hotel_id": room.hotel_id,
                "hotel_name": room.hotel.name,
                "room_id": room.id,
                "room_title": room.title,
                "check_in": str(cin),
                "check_out": str(cout),
                "requested_rooms": requested_rooms,
                "total_physical_rooms": room.total_rooms,
                "available": is_available,
                "is_available": is_available,
                "remaining": available_count,
                "available_rooms_count": available_count,
                "available_count": available_count,
                "room_numbers": room_numbers_status,
                "message": "Room is available for requested dates!" if is_available else f"Only {available_count} room(s) available for requested dates."
            }

            if requested_room_number:
                req_clean = str(requested_room_number).strip().lower()
                req_digits = re.sub(r'^[a-zA-Z\s]+', '', req_clean).strip()
                target_status = next(
                    (
                        item for item in room_numbers_status
                        if item["number"].strip().lower() == req_clean or
                        re.sub(r'^[a-zA-Z\s]+', '', item["number"]).strip() == req_digits
                    ),
                    None
                )
                if target_status:
                    resp_data["specific_room_number"] = requested_room_number
                    resp_data["is_room_number_available"] = target_status["is_available"]

            return Response(resp_data, status=status.HTTP_200_OK)

        except Room.DoesNotExist:
            return Response({"error": "Room not found."}, status=status.HTTP_404_NOT_FOUND)

class RoomImageUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            room = Room.objects.get(pk=pk)
            if room.hotel.owner != request.user and not request.user.is_staff:
                return Response({"error": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

            image = request.FILES.get('image')
            image_url = request.data.get('image_url')
            is_primary_raw = request.data.get('is_primary', False)
            if isinstance(is_primary_raw, bool):
                is_primary = is_primary_raw
            else:
                is_primary = str(is_primary_raw).lower() in ['true', '1', 'yes']

            if not image and not image_url:
                return Response({"error": "Please provide an image file or URL."}, status=status.HTTP_400_BAD_REQUEST)

            room_image = RoomImage.objects.create(
                room=room,
                image=image,
                image_url=image_url,
                is_primary=is_primary
            )
            return Response(RoomImageSerializer(room_image).data, status=status.HTTP_201_CREATED)
        except Room.DoesNotExist:
            return Response({"error": "Room not found."}, status=status.HTTP_404_NOT_FOUND)


class RoomCalendarManageView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        try:
            room = Room.objects.get(pk=pk)
            blocks = room.calendar_blocks.all()
            return Response(RoomCalendarBlockSerializer(blocks, many=True).data)
        except Room.DoesNotExist:
            return Response({"error": "Room not found."}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request, pk):
        try:
            room = Room.objects.get(pk=pk)
            if room.hotel.owner != request.user and not request.user.is_staff:
                return Response({"error": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

            date_str = request.data.get('date')
            custom_price = request.data.get('custom_price')
            is_blocked = request.data.get('is_blocked', False)
            block_reason = request.data.get('block_reason', RoomCalendarBlock.REASON_OWNER_BLOCK)

            if not date_str:
                return Response({"error": "Date parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

            block, created = RoomCalendarBlock.objects.update_or_create(
                room=room,
                date=date_str,
                defaults={
                    'custom_price': custom_price if custom_price else None,
                    'is_blocked': is_blocked,
                    'block_reason': block_reason
                }
            )

            return Response(RoomCalendarBlockSerializer(block).data, status=status.HTTP_200_OK)

        except Room.DoesNotExist:
            return Response({"error": "Room not found."}, status=status.HTTP_404_NOT_FOUND)

