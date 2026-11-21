from django.urls import path
from .location_views import (
    CountryListView,
    StateListView,
    CityListView,
    AreaListView,
    LocationSearchAPIView,
)

urlpatterns = [
    path('countries/', CountryListView.as_view(), name='location_countries'),
    path('states/', StateListView.as_view(), name='location_states'),
    path('cities/', CityListView.as_view(), name='location_cities'),
    path('areas/', AreaListView.as_view(), name='location_areas'),
    path('search/', LocationSearchAPIView.as_view(), name='location_search'),
]
