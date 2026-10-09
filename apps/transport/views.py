from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from .models import Route, Stop, FeeStructure, StudentAssignment, FeeCharge
from .serializers import (
    RouteSerializer,
    StopSerializer,
    FeeStructureSerializer,
    StudentAssignmentSerializer,
    FeeChargeSerializer,
    BatchChargeGenerationSerializer
)
from .services.billing import TransportBillingService

import csv
from django.http import HttpResponse

class RouteViewSet(viewsets.ModelViewSet):
    queryset = Route.objects.all()
    serializer_class = RouteSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=['get'])
    def capacity(self, request, pk=None):
        route = self.get_object()
        active_count = route.student_assignments.filter(is_active=True).count()
        percentage = 0
        if route.capacity > 0:
            percentage = round((active_count / route.capacity) * 100, 1)

        return Response({
            'route_id': route.id,
            'capacity': route.capacity,
            'active_assignments': active_count,
            'available_seats': max(0, route.capacity - active_count),
            'capacity_percentage': percentage,
            'status': 'WARNING' if percentage >= 90 and percentage < 100 else 'FULL' if percentage >= 100 else 'OK'
        })

    @action(detail=True, methods=['get'])
    def manifest(self, request, pk=None):
        route = self.get_object()
        assignments = route.student_assignments.filter(is_active=True).select_related('student', 'stop').order_by('stop__stop_order', 'student__first_name')
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="manifest_route_{route.route_code}.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['Stop Order', 'Stop Name', 'Pickup Time', 'Admission No', 'Student Name', 'Transport Type', 'Contact/Parent Phone'])
        
        for a in assignments:
            pickup = a.stop.pickup_time.strftime('%H:%M') if a.stop.pickup_time else 'N/A'
            # Assuming parent contacts or similar might be on student. We just output what's safely available.
            writer.writerow([
                a.stop.stop_order,
                a.stop.stop_name,
                pickup,
                getattr(a.student, 'admission_number', 'N/A'),
                f"{getattr(a.student, 'first_name', '')} {getattr(a.student, 'last_name', '')}".strip(),
                a.get_transport_type_display(),
                'N/A' # Parent phone would be looked up here if linked
            ])
            
        return response

class StopViewSet(viewsets.ModelViewSet):
    queryset = Stop.objects.all()
    serializer_class = StopSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['route_id', 'zone']

class FeeStructureViewSet(viewsets.ModelViewSet):
    queryset = FeeStructure.objects.all()
    serializer_class = FeeStructureSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['route_id', 'fee_type', 'academic_year', 'term']

class StudentAssignmentViewSet(viewsets.ModelViewSet):
    queryset = StudentAssignment.objects.all()
    serializer_class = StudentAssignmentSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['is_active', 'route_id', 'student_id']

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        assignment = self.get_object()
        if not assignment.is_active:
            return Response({"detail": "Assignment is already deactivated."}, status=status.HTTP_400_BAD_REQUEST)
        
        assignment.is_active = False
        assignment.end_date = timezone.now().date()
        assignment.save()
        return Response({"detail": "Assignment deactivated successfully.", "end_date": assignment.end_date})

class FeeChargeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = FeeCharge.objects.all()
    serializer_class = FeeChargeSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['student_id', 'assignment_id', 'academic_year', 'term', 'linked_to_main_fee_ledger']

    @action(detail=False, methods=['post'], url_path='generate-term-charges')
    def generate_term_charges(self, request):
        serializer = BatchChargeGenerationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            result = TransportBillingService.generate_term_charges(
                academic_year_id=serializer.validated_data['academic_year_id'],
                term_id=serializer.validated_data['term_id'],
                route_ids=serializer.validated_data.get('route_ids'),
                due_date=serializer.validated_data.get('due_date'),
                enable_prorating=serializer.validated_data.get('enable_prorating', True),
                user=request.user
            )
            return Response(result, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
