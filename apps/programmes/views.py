from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Count, Q

from .models import (
    Faculty, Department, Programme, Specialization,
    ProgrammeUnit, UnitOffering, ProgrammeEnrollment, UnitRegistration
)
from .serializers import (
    FacultySerializer, DepartmentSerializer,
    ProgrammeSerializer, ProgrammeCreateSerializer, SpecializationSerializer,
    ProgrammeUnitSerializer, UnitOfferingSerializer,
    ProgrammeEnrollmentSerializer, UnitRegistrationSerializer
)


class FacultyViewSet(viewsets.ModelViewSet):
    queryset = Faculty.objects.filter(is_deleted=False).prefetch_related('departments')
    serializer_class = FacultySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'code']
    ordering = ['name']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.filter(is_deleted=False).select_related('faculty')
    serializer_class = DepartmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'code']
    ordering = ['name']

    def get_queryset(self):
        qs = super().get_queryset()
        faculty_id = self.request.query_params.get('faculty_id')
        if faculty_id:
            qs = qs.filter(faculty_id=faculty_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


class ProgrammeViewSet(viewsets.ModelViewSet):
    queryset = Programme.objects.filter(is_deleted=False).select_related('department')
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'code', 'description']
    ordering_fields = ['name', 'level', 'created_at']
    ordering = ['level', 'name']

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ProgrammeCreateSerializer
        return ProgrammeSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        level = self.request.query_params.get('level')
        dept_id = self.request.query_params.get('department_id')
        is_active = self.request.query_params.get('is_active')
        if level:
            qs = qs.filter(level=level)
        if dept_id:
            qs = qs.filter(department_id=dept_id)
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == 'true')
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=['get'])
    def units(self, request, pk=None):
        programme = self.get_object()
        year = request.query_params.get('year')
        qs = programme.units.filter(is_active=True, is_deleted=False)
        if year:
            qs = qs.filter(year_of_study=year)
        return Response(ProgrammeUnitSerializer(qs, many=True).data)

    @action(detail=True, methods=['get'])
    def specializations(self, request, pk=None):
        programme = self.get_object()
        qs = programme.specializations.filter(is_active=True, is_deleted=False)
        return Response(SpecializationSerializer(qs, many=True).data)

    @action(detail=True, methods=['get'])
    def enrollments(self, request, pk=None):
        programme = self.get_object()
        qs = programme.enrollments.filter(is_deleted=False).select_related('student', 'intake')
        return Response(ProgrammeEnrollmentSerializer(qs, many=True).data)

    @action(detail=False, methods=['get'])
    def dashboard_stats(self, request):
        total = Programme.objects.filter(is_active=True, is_deleted=False).count()
        by_level = list(
            Programme.objects.filter(is_active=True, is_deleted=False)
            .values('level')
            .annotate(count=Count('id'))
        )
        active_enrollments = ProgrammeEnrollment.objects.filter(
            status='active', is_deleted=False
        ).count()
        return Response({
            'total_programmes': total,
            'by_level': by_level,
            'active_enrollments': active_enrollments,
        })


class SpecializationViewSet(viewsets.ModelViewSet):
    queryset = Specialization.objects.filter(is_deleted=False).select_related('programme')
    serializer_class = SpecializationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        programme_id = self.request.query_params.get('programme')
        if programme_id:
            qs = qs.filter(programme_id=programme_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


class ProgrammeUnitViewSet(viewsets.ModelViewSet):
    queryset = ProgrammeUnit.objects.filter(is_deleted=False).select_related('programme', 'specialization')
    serializer_class = ProgrammeUnitSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'code']
    ordering = ['year_of_study', 'code']

    def get_queryset(self):
        qs = super().get_queryset()
        programme_id = self.request.query_params.get('programme')
        year = self.request.query_params.get('year')
        unit_type = self.request.query_params.get('unit_type')
        if programme_id:
            qs = qs.filter(programme_id=programme_id)
        if year:
            qs = qs.filter(year_of_study=year)
        if unit_type:
            qs = qs.filter(unit_type=unit_type)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


class UnitOfferingViewSet(viewsets.ModelViewSet):
    queryset = UnitOffering.objects.filter(is_deleted=False).select_related(
        'unit', 'intake', 'semester', 'lecturer'
    )
    serializer_class = UnitOfferingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        intake_id = self.request.query_params.get('intake')
        semester_id = self.request.query_params.get('semester')
        unit_id = self.request.query_params.get('unit')
        if intake_id:
            qs = qs.filter(intake_id=intake_id)
        if semester_id:
            qs = qs.filter(semester_id=semester_id)
        if unit_id:
            qs = qs.filter(unit_id=unit_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


class ProgrammeEnrollmentViewSet(viewsets.ModelViewSet):
    queryset = ProgrammeEnrollment.objects.filter(is_deleted=False).select_related(
        'student', 'programme', 'specialization', 'intake'
    )
    serializer_class = ProgrammeEnrollmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['registration_number', 'student__student__first_name', 'student__student__last_name']
    ordering = ['-enrollment_date']

    def get_queryset(self):
        qs = super().get_queryset()
        programme_id = self.request.query_params.get('programme')
        intake_id = self.request.query_params.get('intake')
        status_param = self.request.query_params.get('status')
        if programme_id:
            qs = qs.filter(programme_id=programme_id)
        if intake_id:
            qs = qs.filter(intake_id=intake_id)
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


class UnitRegistrationViewSet(viewsets.ModelViewSet):
    queryset = UnitRegistration.objects.filter(is_deleted=False).select_related(
        'programme_enrollment', 'offering__unit'
    )
    serializer_class = UnitRegistrationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        enrollment_id = self.request.query_params.get('enrollment')
        offering_id = self.request.query_params.get('offering')
        if enrollment_id:
            qs = qs.filter(programme_enrollment_id=enrollment_id)
        if offering_id:
            qs = qs.filter(offering_id=offering_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)
