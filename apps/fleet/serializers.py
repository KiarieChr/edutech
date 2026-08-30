from rest_framework import serializers

from .models import (
    DriverProfile,
    FuelLog,
    MaintenanceRecord,
    TripLog,
    Vehicle,
    VehicleAssignment,
    VehicleDocument,
    VehicleExpense,
    TransportStop,
    RouteStop,
    TransportRoute,
    TransportSchedule,
)


class VehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = '__all__'


class DriverProfileSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.get_full_name', read_only=True)
    employee_no = serializers.CharField(source='employee.employee_no', read_only=True)

    class Meta:
        model = DriverProfile
        fields = '__all__'


class VehicleAssignmentSerializer(serializers.ModelSerializer):
    vehicle_registration = serializers.CharField(source='vehicle.registration_number', read_only=True)
    driver_name = serializers.CharField(source='driver.employee.get_full_name', read_only=True)

    class Meta:
        model = VehicleAssignment
        fields = '__all__'


class TripLogSerializer(serializers.ModelSerializer):
    vehicle_registration = serializers.CharField(source='vehicle.registration_number', read_only=True)
    driver_name = serializers.CharField(source='driver.employee.get_full_name', read_only=True)

    class Meta:
        model = TripLog
        fields = '__all__'


class FuelLogSerializer(serializers.ModelSerializer):
    vehicle_registration = serializers.CharField(source='vehicle.registration_number', read_only=True)
    driver_name = serializers.CharField(source='driver.employee.get_full_name', read_only=True)

    class Meta:
        model = FuelLog
        fields = '__all__'


class MaintenanceRecordSerializer(serializers.ModelSerializer):
    vehicle_registration = serializers.CharField(source='vehicle.registration_number', read_only=True)

    class Meta:
        model = MaintenanceRecord
        fields = '__all__'


class VehicleExpenseSerializer(serializers.ModelSerializer):
    vehicle_registration = serializers.CharField(source='vehicle.registration_number', read_only=True)

    class Meta:
        model = VehicleExpense
        fields = '__all__'


class VehicleDocumentSerializer(serializers.ModelSerializer):
    vehicle_registration = serializers.CharField(source='vehicle.registration_number', read_only=True)

    class Meta:
        model = VehicleDocument
        fields = '__all__'


class TransportStopSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransportStop
        fields = '__all__'


class RouteStopSerializer(serializers.ModelSerializer):
    stop_name = serializers.CharField(source='stop.name', read_only=True)

    class Meta:
        model = RouteStop
        fields = '__all__'


class TransportRouteSerializer(serializers.ModelSerializer):
    route_stops = RouteStopSerializer(many=True, read_only=True)

    class Meta:
        model = TransportRoute
        fields = '__all__'


class TransportScheduleSerializer(serializers.ModelSerializer):
    route_name = serializers.CharField(source='route.name', read_only=True)
    vehicle_registration = serializers.CharField(source='vehicle.registration_number', read_only=True)
    driver_name = serializers.CharField(source='driver.employee.get_full_name', read_only=True)

    class Meta:
        model = TransportSchedule
        fields = '__all__'
