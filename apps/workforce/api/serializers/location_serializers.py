# accounts/api/serializers/location_serializers.py
from rest_framework import serializers
from ...core_models import Country, County, SubCounty, Village


class CountrySerializer(serializers.ModelSerializer):
    """Serializer for Country model with nested counties"""
    county_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Country
        fields = [
            'id', 'name', 'code', 'iso3_code', 'phone_code',
            'currency', 'currency_symbol', 'is_active',
            'county_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'county_count']


class CountySerializer(serializers.ModelSerializer):
    """Serializer for County model with nested subcounties"""
    subcounty_count = serializers.IntegerField(read_only=True)
    country_name = serializers.CharField(source='country.name', read_only=True)
    
    class Meta:
        model = County
        fields = [
            'id', 'name', 'code', 'country', 'country_name',
            'is_active', 'subcounty_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'subcounty_count', 'country_name']


class SubCountySerializer(serializers.ModelSerializer):
    """Serializer for SubCounty model with nested villages"""
    village_count = serializers.IntegerField(read_only=True)
    county_name = serializers.CharField(source='county.name', read_only=True)
    country_name = serializers.CharField(source='county.country.name', read_only=True)
    
    class Meta:
        model = SubCounty
        fields = [
            'id', 'name', 'code', 'county', 'county_name',
            'country_name', 'is_active', 'village_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'village_count', 'county_name', 'country_name']


class VillageSerializer(serializers.ModelSerializer):
    """Serializer for Village model"""
    subcounty_name = serializers.CharField(source='subcounty.name', read_only=True)
    county_name = serializers.CharField(source='subcounty.county.name', read_only=True)
    country_name = serializers.CharField(source='subcounty.county.country.name', read_only=True)
    
    class Meta:
        model = Village
        fields = [
            'id', 'name', 'subcounty', 'subcounty_name',
            'county_name', 'country_name', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'subcounty_name', 'county_name', 'country_name']