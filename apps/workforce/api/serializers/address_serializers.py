# accounts/api/serializers/address_serializers.py
from rest_framework import serializers
from django.db import transaction
from ...core_models import EmployeeAddress, EmergencyContact, Employee
from .location_serializers import CountrySerializer, CountySerializer, SubCountySerializer, VillageSerializer


class EmployeeAddressSerializer(serializers.ModelSerializer):
    """Serializer for EmployeeAddress with nested location details"""
    country_detail = CountrySerializer(source='country', read_only=True)
    county_detail = CountySerializer(source='county', read_only=True)
    subcounty_detail = SubCountySerializer(source='subcounty', read_only=True)
    village_detail = VillageSerializer(source='village', read_only=True)
    
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    
    # Write-only fields for ID-based input
    country_id = serializers.PrimaryKeyRelatedField(
        queryset=Country.objects.all(),
        source='country',
        write_only=True
    )
    county_id = serializers.PrimaryKeyRelatedField(
        queryset=County.objects.all(),
        source='county',
        write_only=True,
        required=False,
        allow_null=True
    )
    subcounty_id = serializers.PrimaryKeyRelatedField(
        queryset=SubCounty.objects.all(),
        source='subcounty',
        write_only=True,
        required=False,
        allow_null=True
    )
    village_id = serializers.PrimaryKeyRelatedField(
        queryset=Village.objects.all(),
        source='village',
        write_only=True,
        required=False,
        allow_null=True
    )
    employee_id = serializers.PrimaryKeyRelatedField(
        queryset=Employee.objects.all(),
        source='employee',
        write_only=True
    )
    
    class Meta:
        model = EmployeeAddress
        fields = [
            'id', 'employee', 'employee_id', 'employee_name',
            'address_type', 'address_line_1', 'address_line_2',
            'postal_code', 'city', 'country', 'country_id', 'country_detail',
            'county', 'county_id', 'county_detail',
            'subcounty', 'subcounty_id', 'subcounty_detail',
            'village', 'village_id', 'village_detail',
            'is_primary', 'is_active', 'created_at', 'updated_at',
            'created_by', 'updated_by'
        ]
        read_only_fields = [
            'created_at', 'updated_at', 'created_by', 'updated_by',
            'country_detail', 'county_detail', 'subcounty_detail', 'village_detail',
            'employee_name'
        ]
    
    def validate(self, data):
        """Validate address constraints and location hierarchy"""
        employee = data.get('employee')
        address_type = data.get('address_type')
        is_primary = data.get('is_primary', False)
        
        # Validate location hierarchy
        country = data.get('country')
        county = data.get('county')
        subcounty = data.get('subcounty')
        village = data.get('village')
        
        if county and county.country != country:
            raise serializers.ValidationError({
                'county': 'Selected county does not belong to the selected country.'
            })
        
        if subcounty and subcounty.county != county:
            raise serializers.ValidationError({
                'subcounty': 'Selected subcounty does not belong to the selected county.'
            })
        
        if village and village.subcounty != subcounty:
            raise serializers.ValidationError({
                'village': 'Selected village does not belong to the selected subcounty.'
            })
        
        # Validate primary address uniqueness
        if is_primary and employee:
            # Check if another primary address of same type exists
            existing_primary = EmployeeAddress.objects.filter(
                employee=employee,
                address_type=address_type,
                is_primary=True,
                is_active=True
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if existing_primary.exists():
                raise serializers.ValidationError({
                    'is_primary': f'A primary {address_type} address already exists for this employee.'
                })
        
        return data
    
    @transaction.atomic
    def update(self, instance, validated_data):
        """Handle update with primary address logic"""
        # If setting as primary, demote existing primary
        if validated_data.get('is_primary', False) and instance.is_primary == False:
            EmployeeAddress.objects.filter(
                employee=instance.employee,
                address_type=instance.address_type,
                is_primary=True,
                is_active=True
            ).update(is_primary=False)
        
        # If demoting from primary, ensure at least one primary remains
        if instance.is_primary and validated_data.get('is_primary', False) == False:
            # Check if this is the only primary address
            other_primaries = EmployeeAddress.objects.filter(
                employee=instance.employee,
                address_type=instance.address_type,
                is_primary=True,
                is_active=True
            ).exclude(pk=instance.pk)
            
            if not other_primaries.exists():
                raise serializers.ValidationError({
                    'is_primary': 'Cannot remove primary status. At least one primary address is required.'
                })
        
        return super().update(instance, validated_data)


class EmergencyContactSerializer(serializers.ModelSerializer):
    """Serializer for EmergencyContact model"""
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    employee_id = serializers.PrimaryKeyRelatedField(
        queryset=Employee.objects.all(),
        source='employee',
        write_only=True
    )
    
    class Meta:
        model = EmergencyContact
        fields = [
            'id', 'employee', 'employee_id', 'employee_name',
            'full_name', 'relationship', 'phone_1', 'phone_2',
            'email', 'address', 'city', 'country', 'county',
            'postal_code', 'is_active', 'created_at', 'updated_at',
            'created_by', 'updated_by'
        ]
        read_only_fields = [
            'created_at', 'updated_at', 'created_by', 'updated_by',
            'employee_name'
        ]
    
    def validate(self, data):
        """Validate emergency contact data"""
        # Ensure at least one contact method is provided
        phone_1 = data.get('phone_1')
        email = data.get('email')
        
        if not phone_1 and not email:
            raise serializers.ValidationError({
                'phone_1': 'Either phone or email must be provided.',
                'email': 'Either phone or email must be provided.'
            })
        
        return data