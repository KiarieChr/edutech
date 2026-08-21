from django.utils import timezone
from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response

from student_management.models.enquiry import Enquiry
from student_management.models.application import Application
from student_management.serializers.enquiry import (
    EnquirySerializer, EnquiryCreateSerializer, EnquiryConvertSerializer
)


class EnquiryViewSet(viewsets.ModelViewSet):
    """
    CRUD + convert action for pre-application enquiries.

    Endpoints:
        GET    /api/student-management/enquiries/          — list
        POST   /api/student-management/enquiries/          — create
        GET    /api/student-management/enquiries/{id}/     — retrieve
        PATCH  /api/student-management/enquiries/{id}/     — update
        DELETE /api/student-management/enquiries/{id}/     — soft delete
        POST   /api/student-management/enquiries/{id}/convert/  — convert to application
    """
    queryset = Enquiry.objects.filter(is_deleted=False).select_related(
        'intake', 'curriculum', 'grade', 'campus', 'assigned_to', 'converted_application'
    )
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['full_name', 'child_name', 'phone_number', 'email']
    ordering_fields = ['created_at', 'follow_up_date', 'status']
    ordering = ['-created_at']

    def get_permissions(self):
        if self.action == 'create':
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return EnquiryCreateSerializer
        return EnquirySerializer

    def perform_create(self, serializer):
        created_by_user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        serializer.save(created_by=created_by_user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_destroy(self, instance):
        instance.soft_delete()

    # ── Filters via query params ───────────────────────────────────────────────
    def get_queryset(self):
        qs = super().get_queryset()
        status_param = self.request.query_params.get('status')
        campus_id = self.request.query_params.get('campus_id')
        intake_id = self.request.query_params.get('intake_id')
        assigned_to_me = self.request.query_params.get('assigned_to_me')

        if status_param:
            qs = qs.filter(status=status_param)
        if campus_id:
            qs = qs.filter(campus_id=campus_id)
        if intake_id:
            qs = qs.filter(intake_id=intake_id)
        if assigned_to_me and assigned_to_me.lower() == 'true':
            qs = qs.filter(assigned_to=self.request.user)

        return qs

    # ── POST /enquiries/{id}/convert/ ─────────────────────────────────────────
    @action(detail=True, methods=['post'])
    def convert(self, request, pk=None):
        """
        Convert an enquiry into a formal Application.

        Two modes:
          1. No body / existing_application_id=null → auto-create Application from enquiry data.
          2. existing_application_id=<id>           → link enquiry to an existing Application.

        Sets the enquiry status to 'converted' and records the timestamp.
        """
        enquiry = self.get_object()

        if enquiry.status == 'converted':
            return Response(
                {'error': 'This enquiry has already been converted to an Application.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if enquiry.status == 'dropped':
            return Response(
                {'error': 'Cannot convert a dropped enquiry. Reopen it first.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        input_ser = EnquiryConvertSerializer(data=request.data)
        input_ser.is_valid(raise_exception=True)
        existing_app = input_ser.validated_data.get('existing_application_id')

        if existing_app:
            # ── Link mode ──────────────────────────────────────────────────────
            application = existing_app
        else:
            # ── Auto-create mode ───────────────────────────────────────────────
            # We can only auto-create if the enquiry has the minimum required fields
            if not enquiry.intake:
                return Response(
                    {'error': 'Enquiry must have an Intake selected before auto-creating an Application.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if not enquiry.curriculum:
                return Response(
                    {'error': 'Enquiry must have a Curriculum selected before auto-creating an Application.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Split the child_name or full_name into first/last
            name_parts = (enquiry.child_name or enquiry.full_name).split(' ', 1)
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ''

            application = Application.objects.create(
                first_name=first_name,
                last_name=last_name,
                intake=enquiry.intake,
                applying_for_curriculum=enquiry.curriculum,
                applying_for_grade=enquiry.grade,
                campus=enquiry.campus,
                guardian_name=enquiry.full_name,
                phone_number=enquiry.phone_number,
                email=enquiry.email,
                referral_source='referral',  # came via enquiry pipeline
                application_status='pending',
                created_by=request.user,
            )

        # ── Mark enquiry as converted ──────────────────────────────────────────
        enquiry.status = 'converted'
        enquiry.converted_application = application
        enquiry.converted_at = timezone.now()
        enquiry.updated_by = request.user
        enquiry.save()

        return Response({
            'success': True,
            'enquiry_id': enquiry.id,
            'application_id': application.id,
            'application_status': application.application_status,
            'message': f'Enquiry converted. Application #{application.id} created/linked.',
        }, status=status.HTTP_201_CREATED)
