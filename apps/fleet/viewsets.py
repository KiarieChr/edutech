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
    TransportStop,
    RouteStop,
    TransportRoute,
    TransportSchedule,
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
    TransportStopSerializer,
    RouteStopSerializer,
    TransportRouteSerializer,
    TransportScheduleSerializer,
)


class VehicleViewSet(viewsets.ModelViewSet):
    queryset = Vehicle.objects.select_related('campus', 'assigned_department').all()
    serializer_class = VehicleSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['vehicle_type', 'status', 'campus', 'assigned_department']
    search_fields = ['registration_number', 'make', 'model']
    ordering = ['registration_number']

    @action(detail=True, methods=['post'])
    def update_location(self, request, pk=None):
        vehicle = self.get_object()
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        speed = request.data.get('speed', 0)
        
        if latitude is None or longitude is None:
            return Response({'error': 'latitude and longitude are required'}, status=400)
            
        # Broadcast to Websocket group
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f'bus_{vehicle.id}_location',
                {
                    'type': 'location_update',
                    'latitude': latitude,
                    'longitude': longitude,
                    'speed': speed,
                    'timestamp': timezone.now().isoformat()
                }
            )
            
        return Response({'status': 'Location updated'})

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

    @action(detail=False, methods=['get'])
    def financial_analytics(self, request):
        from dateutil.relativedelta import relativedelta
        from django.db.models.functions import TruncMonth
        # pyrefly: ignore [missing-import]
        from finance.models import ReceiptAllocation

        months = int(request.query_params.get('months', 6))
        end_date = timezone.now().date()
        start_date = (end_date - relativedelta(months=months - 1)).replace(day=1)

        # 1. Income (Receipt allocations for transport)
        allocations = ReceiptAllocation.objects.filter(
            allocated_at__date__gte=start_date,
            allocated_at__date__lte=end_date,
        ).filter(
            Q(invoice_item__fee_item__name__icontains='transport') |
            Q(invoice_item__vote_head__name__icontains='transport')
        ).annotate(
            month=TruncMonth('allocated_at')
        ).values('month').annotate(
            total_income=Sum('amount')
        ).order_by('month')

        # 2. Fuel Expenses
        fuel_logs = FuelLog.objects.filter(
            filled_at__date__gte=start_date,
            filled_at__date__lte=end_date
        ).annotate(
            month=TruncMonth('filled_at')
        ).values('month').annotate(
            total_cost=Sum('total_cost')
        ).order_by('month')

        # 3. Maintenance Expenses
        maintenance_logs = MaintenanceRecord.objects.filter(
            completed_date__gte=start_date,
            completed_date__lte=end_date
        ).annotate(
            month=TruncMonth('completed_date')
        ).values('month').annotate(
            total_cost=Sum('total_cost')
        ).order_by('month')

        # 4. Other Expenses
        other_expenses = VehicleExpense.objects.filter(
            expense_date__gte=start_date,
            expense_date__lte=end_date
        ).annotate(
            month=TruncMonth('expense_date')
        ).values('month').annotate(
            total_cost=Sum('amount')
        ).order_by('month')

        # Merge data into a continuous timeline
        results_by_month = {}
        curr = start_date
        while curr <= end_date:
            month_str = curr.strftime('%Y-%m')
            month_label = curr.strftime('%b %Y')
            results_by_month[month_str] = {
                'month_str': month_str,
                'month_label': month_label,
                'income': 0,
                'fuel': 0,
                'maintenance': 0,
                'other': 0,
            }
            curr += relativedelta(months=1)

        for a in allocations:
            if a['month']:
                m = a['month'].strftime('%Y-%m')
                if m in results_by_month:
                    results_by_month[m]['income'] = float(a['total_income'] or 0)
                    
        for f in fuel_logs:
            if f['month']:
                m = f['month'].strftime('%Y-%m')
                if m in results_by_month:
                    results_by_month[m]['fuel'] = float(f['total_cost'] or 0)

        for m in maintenance_logs:
            if m['month']:
                month_str = m['month'].strftime('%Y-%m')
                if month_str in results_by_month:
                    results_by_month[month_str]['maintenance'] = float(m['total_cost'] or 0)

        for o in other_expenses:
            if o['month']:
                m = o['month'].strftime('%Y-%m')
                if m in results_by_month:
                    results_by_month[m]['other'] = float(o['total_cost'] or 0)
        
        # Calculate totals
        total_income = sum(item['income'] for item in results_by_month.values())
        total_fuel = sum(item['fuel'] for item in results_by_month.values())
        total_maintenance = sum(item['maintenance'] for item in results_by_month.values())
        total_other = sum(item['other'] for item in results_by_month.values())
        total_expense = total_fuel + total_maintenance + total_other

        # KPI: Cost per km
        total_distance = TripLog.objects.filter(
            departure_time__date__gte=start_date,
            departure_time__date__lte=end_date,
            status=TripLog.Status.COMPLETED
        ).aggregate(total=Sum('distance_km'))['total'] or 0

        avg_cost_per_km = 0
        if total_distance > 0:
            avg_cost_per_km = float(total_expense) / float(total_distance)

        data = list(results_by_month.values())
        data.sort(key=lambda x: x['month_str'])

        return Response({
            'chart_data': data,
            'summary': {
                'total_income': total_income,
                'total_expense': total_expense,
                'net_profit': total_income - total_expense,
                'total_fuel': total_fuel,
                'total_maintenance': total_maintenance,
                'total_other': total_other,
                'total_distance_km': float(total_distance),
                'avg_cost_per_km': round(avg_cost_per_km, 2)
            }
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


class TransportStopViewSet(viewsets.ModelViewSet):
    queryset = TransportStop.objects.all()
    serializer_class = TransportStopSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ['name']


class RouteStopViewSet(viewsets.ModelViewSet):
    queryset = RouteStop.objects.select_related('route', 'stop').all()
    serializer_class = RouteStopSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['route', 'stop']


class TransportRouteViewSet(viewsets.ModelViewSet):
    queryset = TransportRoute.objects.prefetch_related('route_stops__stop').all()
    serializer_class = TransportRouteSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ['name']


class TransportScheduleViewSet(viewsets.ModelViewSet):
    queryset = TransportSchedule.objects.select_related('route', 'vehicle', 'driver__employee').all()
    serializer_class = TransportScheduleSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['route', 'vehicle', 'driver', 'is_active']
    ordering = ['departure_time']
