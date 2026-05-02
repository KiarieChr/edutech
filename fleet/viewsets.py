from datetime import timedelta

from django.db.models import F, Q, Sum
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    DriverProfile,
    FuelLog,
    MaintenanceRecord,
    TripLog,
    Vehicle,
    VehicleAssignment,
    VehicleDocument,
    VehicleExpense,
)
from .serializers import (
    DriverProfileSerializer,
    FuelLogSerializer,
    MaintenanceRecordSerializer,
    TripLogSerializer,
    VehicleAssignmentSerializer,
    VehicleDocumentSerializer,
    VehicleExpenseSerializer,
    VehicleSerializer,
)


class VehicleViewSet(viewsets.ModelViewSet):
    queryset = Vehicle.objects.select_related('campus', 'assigned_department').all()
    serializer_class = VehicleSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['vehicle_type', 'status', 'campus', 'assigned_department']
    search_fields = ['registration_number', 'make', 'model']
    ordering = ['registration_number']

    @action(detail=False, methods=['get'])
    def dashboard_summary(self, request):
        today = timezone.now().date()
        total_vehicles = Vehicle.objects.count()
        active_vehicles = Vehicle.objects.filter(status=Vehicle.Status.ACTIVE).count()
        maintenance_vehicles = Vehicle.objects.filter(status=Vehicle.Status.MAINTENANCE).count()
        grounded_vehicles = Vehicle.objects.filter(status=Vehicle.Status.GROUNDED).count()

        month_start = today.replace(day=1)
        fuel_cost = FuelLog.objects.filter(filled_at__date__gte=month_start).aggregate(total=Sum('total_cost'))['total'] or 0
        maintenance_cost = MaintenanceRecord.objects.filter(completed_date__gte=month_start).aggregate(total=Sum('total_cost'))['total'] or 0
        expense_cost = VehicleExpense.objects.filter(expense_date__gte=month_start).aggregate(total=Sum('amount'))['total'] or 0

        trips_this_month = TripLog.objects.filter(departure_time__date__gte=month_start).count()
        completed_trips = TripLog.objects.filter(departure_time__date__gte=month_start, status=TripLog.Status.COMPLETED).count()

        due_service = Vehicle.objects.filter(
            Q(next_service_date__isnull=False, next_service_date__lte=today) |
            Q(next_service_odometer_km__isnull=False, current_odometer_km__gte=F('next_service_odometer_km'))
        ).count()

        expiring_docs = VehicleDocument.objects.filter(
            expiry_date__isnull=False,
            expiry_date__lte=today + timedelta(days=30)
        ).count()

        return Response({
            'total_vehicles': total_vehicles,
            'active_vehicles': active_vehicles,
            'maintenance_vehicles': maintenance_vehicles,
            'grounded_vehicles': grounded_vehicles,
            'trips_this_month': trips_this_month,
            'completed_trips': completed_trips,
            'month_fuel_cost': fuel_cost,
            'month_maintenance_cost': maintenance_cost,
            'month_other_expense_cost': expense_cost,
            'month_total_cost': fuel_cost + maintenance_cost + expense_cost,
            'due_service': due_service,
            'expiring_documents_30_days': expiring_docs,
        })


class DriverProfileViewSet(viewsets.ModelViewSet):
    queryset = DriverProfile.objects.select_related('employee').all()
    serializer_class = DriverProfileSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status']
    search_fields = ['employee__employee_no', 'employee__first_name', 'employee__last_name', 'license_number']
    ordering = ['employee__employee_no']


class VehicleAssignmentViewSet(viewsets.ModelViewSet):
    queryset = VehicleAssignment.objects.select_related('vehicle', 'driver__employee').all()
    serializer_class = VehicleAssignmentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['vehicle', 'driver', 'is_active', 'is_primary']
    ordering = ['-start_date']


class TripLogViewSet(viewsets.ModelViewSet):
    queryset = TripLog.objects.select_related('vehicle', 'driver__employee', 'department', 'requested_by').all()
    serializer_class = TripLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['vehicle', 'driver', 'status', 'department']
    search_fields = ['reference_number', 'purpose', 'origin', 'destination']
    ordering = ['-departure_time']


class FuelLogViewSet(viewsets.ModelViewSet):
    queryset = FuelLog.objects.select_related('vehicle', 'driver__employee', 'trip').all()
    serializer_class = FuelLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['vehicle', 'driver', 'payment_method']
    ordering = ['-filled_at']


class MaintenanceRecordViewSet(viewsets.ModelViewSet):
    queryset = MaintenanceRecord.objects.select_related('vehicle', 'service_provider').all()
    serializer_class = MaintenanceRecordSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['vehicle', 'maintenance_type', 'status', 'service_provider']
    search_fields = ['description']
    ordering = ['-scheduled_date', '-created_at']


class VehicleExpenseViewSet(viewsets.ModelViewSet):
    queryset = VehicleExpense.objects.select_related('vehicle', 'vendor', 'trip', 'finance_account').all()
    serializer_class = VehicleExpenseSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['vehicle', 'expense_type', 'vendor']
    ordering = ['-expense_date', '-created_at']


class VehicleDocumentViewSet(viewsets.ModelViewSet):
    queryset = VehicleDocument.objects.select_related('vehicle').all()
    serializer_class = VehicleDocumentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['vehicle', 'document_type']
    ordering = ['-expiry_date']
