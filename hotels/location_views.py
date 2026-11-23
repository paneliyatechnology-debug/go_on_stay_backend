from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Q
from django.core.cache import cache
from .models import Country, State, City, Area
from .location_serializers import (
    CountrySerializer,
    StateSerializer,
    CitySerializer,
    AreaSerializer,
)

class CountryListView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        query = request.query_params.get('q') or request.query_params.get('search')
        cache_key = f"location_countries_{query.strip().lower()}" if query else "location_countries_all"
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return Response(cached_data, status=status.HTTP_200_OK)

        qs = Country.objects.all().order_by('name')
        if query:
            qs = qs.filter(name__icontains=query.strip())
        serializer = CountrySerializer(qs, many=True)
        resp_data = {
            'success': True,
            'count': len(serializer.data),
            'data': serializer.data,
            'results': serializer.data
        }
        cache.set(cache_key, resp_data, timeout=3600)
        return Response(resp_data, status=status.HTTP_200_OK)


class StateListView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        country_id = request.query_params.get('country_id') or ''
        query = request.query_params.get('q') or request.query_params.get('search') or ''
        cache_key = f"location_states_{country_id}_{query.strip().lower()}"
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return Response(cached_data, status=status.HTTP_200_OK)

        qs = State.objects.select_related('country').all().order_by('name')
        if country_id:
            qs = qs.filter(country_id=country_id)
        if query:
            qs = qs.filter(name__icontains=query.strip())
        serializer = StateSerializer(qs, many=True)
        resp_data = {
            'success': True,
            'count': len(serializer.data),
            'data': serializer.data,
            'results': serializer.data
        }
        cache.set(cache_key, resp_data, timeout=3600)
        return Response(resp_data, status=status.HTTP_200_OK)


class CityListView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        state_id = request.query_params.get('state_id') or ''
        country_id = request.query_params.get('country_id') or ''
        query = request.query_params.get('q') or request.query_params.get('search') or ''
        cache_key = f"location_cities_{state_id}_{country_id}_{query.strip().lower()}"
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return Response(cached_data, status=status.HTTP_200_OK)

        qs = City.objects.select_related('state', 'state__country').all().order_by('name')
        if state_id:
            qs = qs.filter(state_id=state_id)
        if country_id:
            qs = qs.filter(state__country_id=country_id)
        if query:
            qs = qs.filter(name__icontains=query.strip())
        serializer = CitySerializer(qs, many=True)
        resp_data = {
            'success': True,
            'count': len(serializer.data),
            'data': serializer.data,
            'results': serializer.data
        }
        cache.set(cache_key, resp_data, timeout=3600)
        return Response(resp_data, status=status.HTTP_200_OK)
        query = request.query_params.get('q') or request.query_params.get('search')
        if query:
            qs = qs.filter(name__icontains=query.strip())
        serializer = CitySerializer(qs, many=True)
        return Response({
            'success': True,
            'count': len(serializer.data),
            'data': serializer.data,
            'results': serializer.data
        }, status=status.HTTP_200_OK)


class AreaListView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        qs = Area.objects.select_related('city', 'city__state', 'city__state__country').all().order_by('name')
        city_id = request.query_params.get('city_id')
        if city_id:
            qs = qs.filter(city_id=city_id)
        pincode = request.query_params.get('pincode') or request.query_params.get('zip_code')
        if pincode:
            qs = qs.filter(zip_code=pincode.strip())
        query = request.query_params.get('q') or request.query_params.get('search')
        if query:
            qs = qs.filter(name__icontains=query.strip())
        serializer = AreaSerializer(qs, many=True)
        return Response({
            'success': True,
            'count': len(serializer.data),
            'data': serializer.data,
            'results': serializer.data
        }, status=status.HTTP_200_OK)


class LocationSearchAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        query = (request.query_params.get('q') or request.query_params.get('query') or request.query_params.get('search') or '').strip()
        if not query:
            return Response({
                'success': True,
                'count': 0,
                'data': [],
                'results': []
            }, status=status.HTTP_200_OK)

        results = []

        # 1. Matching Cities
        cities = City.objects.filter(name__icontains=query).select_related('state', 'state__country')[:10]
        for c in cities:
            results.append({
                'id': c.id,
                'type': 'city',
                'name': c.name,
                'display_name': f"{c.name}, {c.state.name}",
                'city_id': c.id,
                'city_name': c.name,
                'state_id': c.state_id,
                'state_name': c.state.name,
                'country_name': c.state.country.name if c.state.country else 'India',
                'latitude': float(c.latitude) if c.latitude is not None else None,
                'longitude': float(c.longitude) if c.longitude is not None else None,
                'pincode': None,
            })

        # 2. Matching Areas
        areas = Area.objects.filter(
            Q(name__icontains=query) | Q(zip_code__icontains=query)
        ).select_related('city', 'city__state', 'city__state__country')[:10]
        for a in areas:
            results.append({
                'id': a.id,
                'type': 'area',
                'name': a.name,
                'display_name': f"{a.name}, {a.city.name}, {a.city.state.name}",
                'area_id': a.id,
                'city_id': a.city_id,
                'city_name': a.city.name,
                'state_id': a.city.state_id,
                'state_name': a.city.state.name,
                'country_name': a.city.state.country.name if a.city.state.country else 'India',
                'latitude': float(a.latitude) if a.latitude is not None else None,
                'longitude': float(a.longitude) if a.longitude is not None else None,
                'pincode': a.zip_code,
            })

        # 3. Matching States
        states = State.objects.filter(name__icontains=query).select_related('country')[:5]
        for s in states:
            results.append({
                'id': s.id,
                'type': 'state',
                'name': s.name,
                'display_name': f"{s.name}, {s.country.name if s.country else 'India'}",
                'state_id': s.id,
                'state_name': s.name,
                'country_name': s.country.name if s.country else 'India',
                'latitude': None,
                'longitude': None,
                'pincode': None,
            })

        return Response({
            'success': True,
            'count': len(results),
            'data': results,
            'results': results
        }, status=status.HTTP_200_OK)
