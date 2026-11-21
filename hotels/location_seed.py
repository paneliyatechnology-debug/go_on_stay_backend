"""
GoOnStay Location Hierarchy Seeding and Synchronization Utility.
Populates standard Indian Country, State, City, and Area models and
safely links existing Hotel records to their normalized foreign keys.
"""

from decimal import Decimal
from hotels.models import Country, State, City, Area, Hotel

LOCATION_TREE = [
    {
        "country": "India",
        "code": "IN",
        "states": [
            {
                "name": "Gujarat",
                "code": "GJ",
                "cities": [
                    {
                        "name": "Ahmedabad",
                        "latitude": Decimal("23.022505"),
                        "longitude": Decimal("72.571362"),
                        "areas": [
                            {"name": "Satellite", "zip_code": "380015", "latitude": Decimal("23.0300"), "longitude": Decimal("72.5178")},
                            {"name": "Bodakdev", "zip_code": "380054", "latitude": Decimal("23.0373"), "longitude": Decimal("72.5120")},
                            {"name": "Navrangpura", "zip_code": "380009", "latitude": Decimal("23.0365"), "longitude": Decimal("72.5611")},
                            {"name": "SG Highway", "zip_code": "380060", "latitude": Decimal("23.0450"), "longitude": Decimal("72.5250")},
                            {"name": "Vastrapur", "zip_code": "380015", "latitude": Decimal("23.0350"), "longitude": Decimal("72.5293")},
                        ]
                    },
                    {
                        "name": "Surat",
                        "latitude": Decimal("21.170240"),
                        "longitude": Decimal("72.831061"),
                        "areas": [
                            {"name": "Athwa", "zip_code": "395007", "latitude": Decimal("21.1600"), "longitude": Decimal("72.8000")},
                            {"name": "Vesu", "zip_code": "395007", "latitude": Decimal("21.1400"), "longitude": Decimal("72.7800")},
                        ]
                    },
                    {
                        "name": "Vadodara",
                        "latitude": Decimal("22.307159"),
                        "longitude": Decimal("73.181219"),
                        "areas": [
                            {"name": "Alkapuri", "zip_code": "390007", "latitude": Decimal("22.3100"), "longitude": Decimal("73.1700")},
                        ]
                    }
                ]
            },
            {
                "name": "Maharashtra",
                "code": "MH",
                "cities": [
                    {
                        "name": "Mumbai",
                        "latitude": Decimal("19.075984"),
                        "longitude": Decimal("72.877656"),
                        "areas": [
                            {"name": "Marine Drive", "zip_code": "400020", "latitude": Decimal("18.9432"), "longitude": Decimal("72.8230")},
                            {"name": "Bandra", "zip_code": "400050", "latitude": Decimal("19.0596"), "longitude": Decimal("72.8295")},
                            {"name": "Andheri", "zip_code": "400058", "latitude": Decimal("19.1136"), "longitude": Decimal("72.8697")},
                            {"name": "Juhu", "zip_code": "400049", "latitude": Decimal("19.1075"), "longitude": Decimal("72.8263")},
                            {"name": "Colaba", "zip_code": "400005", "latitude": Decimal("18.9067"), "longitude": Decimal("72.8147")},
                        ]
                    },
                    {
                        "name": "Pune",
                        "latitude": Decimal("18.520430"),
                        "longitude": Decimal("73.856744"),
                        "areas": [
                            {"name": "Koregaon Park", "zip_code": "411001", "latitude": Decimal("18.5362"), "longitude": Decimal("73.8940")},
                            {"name": "Viman Nagar", "zip_code": "411014", "latitude": Decimal("18.5679"), "longitude": Decimal("73.9143")},
                        ]
                    }
                ]
            },
            {
                "name": "Rajasthan",
                "code": "RJ",
                "cities": [
                    {
                        "name": "Jaipur",
                        "latitude": Decimal("26.912434"),
                        "longitude": Decimal("75.787271"),
                        "areas": [
                            {"name": "Palace Road", "zip_code": "302001", "latitude": Decimal("26.9150"), "longitude": Decimal("75.7900")},
                            {"name": "C-Scheme", "zip_code": "302001", "latitude": Decimal("26.9100"), "longitude": Decimal("75.8000")},
                            {"name": "Malviya Nagar", "zip_code": "302017", "latitude": Decimal("26.8500"), "longitude": Decimal("75.8150")},
                            {"name": "Amer", "zip_code": "302028", "latitude": Decimal("26.9855"), "longitude": Decimal("75.8513")},
                            {"name": "Bani Park", "zip_code": "302016", "latitude": Decimal("26.9280"), "longitude": Decimal("75.7950")},
                        ]
                    },
                    {
                        "name": "Udaipur",
                        "latitude": Decimal("24.585445"),
                        "longitude": Decimal("73.712479"),
                        "areas": [
                            {"name": "Lake Pichola", "zip_code": "313001", "latitude": Decimal("24.5750"), "longitude": Decimal("73.6780")},
                            {"name": "Fateh Sagar", "zip_code": "313001", "latitude": Decimal("24.6020"), "longitude": Decimal("73.6730")},
                            {"name": "City Palace Road", "zip_code": "313001", "latitude": Decimal("24.5764"), "longitude": Decimal("73.6835")},
                            {"name": "Hiran Magri", "zip_code": "313002", "latitude": Decimal("24.5600"), "longitude": Decimal("73.7200")},
                        ]
                    },
                    {
                        "name": "Jodhpur",
                        "latitude": Decimal("26.238947"),
                        "longitude": Decimal("73.024309"),
                        "areas": [
                            {"name": "Ratanada", "zip_code": "342001", "latitude": Decimal("26.2700"), "longitude": Decimal("73.0300")},
                        ]
                    }
                ]
            },
            {
                "name": "Goa",
                "code": "GA",
                "cities": [
                    {
                        "name": "Goa",
                        "latitude": Decimal("15.299326"),
                        "longitude": Decimal("74.123996"),
                        "areas": [
                            {"name": "Baga Beach", "zip_code": "403516", "latitude": Decimal("15.5553"), "longitude": Decimal("73.7517")},
                            {"name": "Calangute Beach", "zip_code": "403516", "latitude": Decimal("15.5439"), "longitude": Decimal("73.7553")},
                            {"name": "Candolim", "zip_code": "403515", "latitude": Decimal("15.5173"), "longitude": Decimal("73.7661")},
                            {"name": "Anjuna", "zip_code": "403509", "latitude": Decimal("15.5800"), "longitude": Decimal("73.7400")},
                        ]
                    },
                    {
                        "name": "Panaji",
                        "latitude": Decimal("15.490930"),
                        "longitude": Decimal("73.827850"),
                        "areas": [
                            {"name": "Fontainhas", "zip_code": "403001", "latitude": Decimal("15.4980"), "longitude": Decimal("73.8320")},
                            {"name": "Miramar", "zip_code": "403001", "latitude": Decimal("15.4850"), "longitude": Decimal("73.8100")},
                        ]
                    }
                ]
            },
            {
                "name": "Delhi",
                "code": "DL",
                "cities": [
                    {
                        "name": "New Delhi",
                        "latitude": Decimal("28.613939"),
                        "longitude": Decimal("77.209021"),
                        "areas": [
                            {"name": "Connaught Place", "zip_code": "110001", "latitude": Decimal("28.6315"), "longitude": Decimal("77.2167")},
                            {"name": "Aerocity", "zip_code": "110037", "latitude": Decimal("28.5500"), "longitude": Decimal("77.1200")},
                        ]
                    }
                ]
            },
            {
                "name": "Karnataka",
                "code": "KA",
                "cities": [
                    {
                        "name": "Bengaluru",
                        "latitude": Decimal("12.971598"),
                        "longitude": Decimal("77.594562"),
                        "areas": [
                            {"name": "Koramangala", "zip_code": "560034", "latitude": Decimal("12.9352"), "longitude": Decimal("77.6245")},
                            {"name": "Indiranagar", "zip_code": "560038", "latitude": Decimal("12.9719"), "longitude": Decimal("77.6412")},
                        ]
                    }
                ]
            }
        ]
    }
]


def seed_locations():
    """Populates normalized Countries, States, Cities, and Areas."""
    for c_data in LOCATION_TREE:
        country, _ = Country.objects.get_or_create(
            name=c_data["country"],
            defaults={"code": c_data["code"], "is_active": True}
        )

        for s_data in c_data.get("states", []):
            state, _ = State.objects.get_or_create(
                country=country,
                name=s_data["name"],
                defaults={"code": s_data.get("code", ""), "is_active": True}
            )

            for ci_data in s_data.get("cities", []):
                city, _ = City.objects.get_or_create(
                    state=state,
                    name=ci_data["name"],
                    defaults={
                        "latitude": ci_data.get("latitude"),
                        "longitude": ci_data.get("longitude"),
                        "is_active": True
                    }
                )

                for a_data in ci_data.get("areas", []):
                    Area.objects.get_or_create(
                        city=city,
                        name=a_data["name"],
                        defaults={
                            "zip_code": a_data.get("zip_code", ""),
                            "latitude": a_data.get("latitude"),
                            "longitude": a_data.get("longitude"),
                            "is_active": True
                        }
                    )


def sync_existing_hotels():
    """Safely links existing Hotel records to their normalized location foreign keys."""
    for hotel in Hotel.objects.all():
        updated = False

        # 1. Match or link Country
        if not hotel.country_rel and hotel.country:
            c = Country.objects.filter(name__iexact=hotel.country.strip()).first()
            if not c:
                c, _ = Country.objects.get_or_create(name="India", defaults={"code": "IN"})
            hotel.country_rel = c
            updated = True

        # 2. Match or link State
        if not hotel.state_rel and hotel.state and hotel.country_rel:
            s = State.objects.filter(country=hotel.country_rel, name__iexact=hotel.state.strip()).first()
            if not s:
                s, _ = State.objects.get_or_create(
                    country=hotel.country_rel,
                    name=hotel.state.strip().title()
                )
            hotel.state_rel = s
            updated = True

        # 3. Match or link City
        if not hotel.city_rel and hotel.city and hotel.state_rel:
            ci = City.objects.filter(state=hotel.state_rel, name__iexact=hotel.city.strip()).first()
            if not ci:
                ci, _ = City.objects.get_or_create(
                    state=hotel.state_rel,
                    name=hotel.city.strip().title(),
                    defaults={"latitude": hotel.latitude, "longitude": hotel.longitude}
                )
            hotel.city_rel = ci
            updated = True

        # 4. Match or link Area
        if not hotel.area_rel and hotel.city_rel:
            if hotel.area:
                a = Area.objects.filter(city=hotel.city_rel, name__iexact=hotel.area.strip()).first()
                if not a:
                    a, _ = Area.objects.get_or_create(
                        city=hotel.city_rel,
                        name=hotel.area.strip().title(),
                        defaults={"latitude": hotel.latitude, "longitude": hotel.longitude}
                    )
                hotel.area_rel = a
                updated = True
            else:
                # Assign default area for city if available
                first_area = hotel.city_rel.areas.first()
                if first_area:
                    hotel.area_rel = first_area
                    hotel.area = first_area.name
                    updated = True

        # 5. Fix coordinate accuracy if hotel had duplicate default Mumbai coords in another city
        if hotel.city_rel and hotel.city_rel.name != "Mumbai" and hotel.latitude == Decimal("19.076000") and hotel.longitude == Decimal("72.877700"):
            if hotel.area_rel and hotel.area_rel.latitude:
                hotel.latitude = hotel.area_rel.latitude
                hotel.longitude = hotel.area_rel.longitude
                updated = True
            elif hotel.city_rel.latitude:
                hotel.latitude = hotel.city_rel.latitude
                hotel.longitude = hotel.city_rel.longitude
                updated = True

        if updated:
            hotel.save(update_fields=['country_rel', 'state_rel', 'city_rel', 'area_rel', 'area', 'latitude', 'longitude'])
