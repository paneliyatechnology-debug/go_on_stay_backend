from rest_framework import serializers
from .models import Country, State, City, Area

class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ('id', 'name', 'code')

class StateSerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source='country.name', read_only=True)

    class Meta:
        model = State
        fields = ('id', 'name', 'code', 'country', 'country_name')

class CitySerializer(serializers.ModelSerializer):
    state_name = serializers.CharField(source='state.name', read_only=True)
    country_name = serializers.CharField(source='state.country.name', read_only=True)

    class Meta:
        model = City
        fields = ('id', 'name', 'state', 'state_name', 'country_name', 'latitude', 'longitude')

class AreaSerializer(serializers.ModelSerializer):
    pincode = serializers.CharField(source='zip_code', read_only=True)
    city_name = serializers.CharField(source='city.name', read_only=True)
    state_name = serializers.CharField(source='city.state.name', read_only=True)
    country_name = serializers.CharField(source='city.state.country.name', read_only=True)

    class Meta:
        model = Area
        fields = ('id', 'name', 'pincode', 'city', 'city_name', 'state_name', 'country_name', 'latitude', 'longitude')
