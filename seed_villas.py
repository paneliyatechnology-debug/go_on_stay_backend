import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from hotels.models import Hotel, HotelImage
from rooms.models import Room, RoomImage

User = get_user_model()
owner = User.objects.filter(role='HOTEL_OWNER').first() or User.objects.filter(is_superuser=True).first()

villas_data = [
    {
        'name': 'The Palm Serenity Private Pool Villa',
        'property_type': 'VILLA',
        'city': 'Goa',
        'state': 'Goa',
        'address': 'Sunset Road, Candolim Beach, North Goa',
        'description': 'Ultra-luxury 4BHK private villa featuring a sparkling private swimming pool, landscaped tropical gardens, full modular kitchen, private chef on request, and direct beach access within 200 meters.',
        'star_rating': 5,
        'guest_rating': 4.9,
        'image': 'https://images.unsplash.com/photo-1580587771525-78b9dba3b914?auto=format&fit=crop&w=1200&q=80',
        'price': 14500,
        'room_title': 'Entire 4BHK Private Pool Villa',
        'capacity_adults': 8,
        'capacity_children': 4,
    },
    {
        'name': 'Lakeview Heritage Villa & Homestay',
        'property_type': 'HOMESTAY',
        'city': 'Udaipur',
        'state': 'Rajasthan',
        'address': 'Fateh Sagar Lake Promenade, Udaipur',
        'description': 'Authentic Rajasthani heritage homestay with uninterrupted lake views, traditional jharokha balconies, homecooked royal Mewari breakfast, and rooftop dinner under the stars.',
        'star_rating': 5,
        'guest_rating': 4.8,
        'image': 'https://images.unsplash.com/photo-1564013799919-ab600027ffc6?auto=format&fit=crop&w=1200&q=80',
        'price': 6800,
        'room_title': 'Heritage Lakeview Royal Suite',
        'capacity_adults': 4,
        'capacity_children': 2,
    },
    {
        'name': 'Whispering Pines Forest Villa',
        'property_type': 'VILLA',
        'city': 'Mumbai',
        'state': 'Maharashtra',
        'address': 'Tungarli Hills, Lonavala-Khandala Valley',
        'description': 'Serene 3BHK mountain villa surrounded by dense pine trees with private lawn, heated infinity plunge pool, indoor games room, BBQ deck, and bonfire setups.',
        'star_rating': 4,
        'guest_rating': 4.7,
        'image': 'https://images.unsplash.com/photo-1613490493576-7fde63acd811?auto=format&fit=crop&w=1200&q=80',
        'price': 11200,
        'room_title': 'Exclusive Mountainview Pine Villa',
        'capacity_adults': 6,
        'capacity_children': 3,
    },
    {
        'name': 'The Royal Courtyard Traditional Homestay',
        'property_type': 'HOMESTAY',
        'city': 'Jaipur',
        'state': 'Rajasthan',
        'address': 'Civil Lines, Heritage Quarter, Jaipur',
        'description': 'Charming restored colonial homestay offering personalized hospitality, peaceful central courtyard, homemade organic Rajasthani thali, and curated local walking tours.',
        'star_rating': 4,
        'guest_rating': 4.9,
        'image': 'https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=1200&q=80',
        'price': 4200,
        'room_title': 'Courtyard Deluxe Suite Room',
        'capacity_adults': 3,
        'capacity_children': 1,
    }
]

created_count = 0
for v in villas_data:
    hotel, created = Hotel.objects.get_or_create(
        name=v['name'],
        defaults={
            'owner': owner,
            'property_type': v['property_type'],
            'city': v['city'],
            'state': v['state'],
            'address': v['address'],
            'description': v['description'],
            'star_rating': v['star_rating'],
            'guest_rating': v['guest_rating'],
            'status': 'APPROVED',
            'is_approved': True,
        }
    )
    if created or not hotel.images.exists():
        HotelImage.objects.get_or_create(
            hotel=hotel,
            image_url=v['image'],
            defaults={'is_primary': True, 'caption': v['name']}
        )
    if not hotel.rooms.exists():
        room = Room.objects.create(
            hotel=hotel,
            room_type='VILLA' if v['property_type'] == 'VILLA' else 'DELUXE',
            title=v['room_title'],
            price_per_night=v['price'],
            capacity_adults=v['capacity_adults'],
            capacity_children=v['capacity_children'],
            breakfast_included=True,
            free_cancellation=True,
            total_rooms=3,
            room_numbers='V1, V2, V3'
        )
        RoomImage.objects.create(
            room=room,
            image_url=v['image'],
            is_primary=True
        )
    created_count += 1

print(f"Successfully processed {created_count} Villas and Homestays!")
