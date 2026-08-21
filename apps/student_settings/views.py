from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.utils import timezone
from django.db.models import Count, Q
from .models import (
    AcademicYear, Term, Curriculum, GradeStructure, Stream,
    AdmissionConfig, AdmissionWorkflowConfig, StudentStatus,
    PromotionRule, DemographicConfig, SchoolCalendar, Intake,
    CurriculumLevel, LearningArea
)
from .serializers import (
    AcademicYearSerializer, TermSerializer, CurriculumSerializer,
    GradeStructureSerializer, StreamSerializer,
    AdmissionConfigSerializer, AdmissionWorkflowConfigSerializer,
    StudentStatusSerializer, PromotionRuleSerializer, DemographicConfigSerializer,
    SchoolCalendarSerializer, IntakeSerializer, IntakeCreateSerializer,
    CurriculumLevelSerializer, LearningAreaSerializer
)

class SoftDeleteViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    def perform_destroy(self, instance):
        instance.soft_delete()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

class AcademicYearViewSet(SoftDeleteViewSet):
    queryset = AcademicYear.objects.all()
    serializer_class = AcademicYearSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None

class IntakeViewSet(SoftDeleteViewSet):
    """ViewSet for managing student intake cohorts"""
    queryset = Intake.objects.all()
    serializer_class = IntakeSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return IntakeCreateSerializer
        return IntakeSerializer





class TermViewSet(SoftDeleteViewSet):
    queryset = Term.objects.all()
    serializer_class = TermSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    @action(detail=False, methods=['post'])
    def auto_sync_status(self, request):
        """
        Auto-syncs all terms' status based on dates and sets the current term.
        Restricted to superusers or those with 'can_set_current_term' permission.
        """
        if not (request.user.is_superuser or request.user.has_perm('student_settings.can_set_current_term')):
            return Response({'detail': 'You do not have permission to perform this action.'}, status=status.HTTP_403_FORBIDDEN)
            
        from django.utils import timezone
        today = timezone.now().date()
        
        # Sync all statuses
        all_terms = Term.objects.all()
        updated_count = 0
        for term in all_terms:
            correct_status = 'active' if term.start_date <= today <= term.end_date else 'closed'
            if term.status != correct_status:
                term.status = correct_status
                # Use update to avoid triggering save() signals recursively
                Term.objects.filter(pk=term.pk).update(status=correct_status)
                updated_count += 1
                
        # Find the term that should be current (active today)
        current_candidate = Term.objects.filter(start_date__lte=today, end_date__gte=today, is_deleted=False).order_by('-start_date').first()
        
        if current_candidate:
            Term.objects.exclude(pk=current_candidate.pk).update(is_current=False)
            current_candidate.is_current = True
            current_candidate.save() # This triggers the save method which handles any other logic
            msg = f"Synced {updated_count} term(s). '{current_candidate.name}' is now the current term."
        else:
            Term.objects.all().update(is_current=False)
            msg = f"Synced {updated_count} term(s). No term is currently active based on today's date."
            
        return Response({'success': True, 'message': msg})


class CurriculumViewSet(SoftDeleteViewSet):
    """
    ViewSet for Curriculum management with dashboard statistics.
    """
    queryset = Curriculum.objects.all()
    serializer_class = CurriculumSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None
    
    @action(detail=False, methods=['get'])
    def dashboard_stats(self, request):
        """
        Aggregates statistics for the Curriculum Dashboard.
        
        Returns metrics on:
        - Total and active curricula
        - Total subjects
        - Classes/grades covered
        - Learning areas
        - Subject distribution by curriculum
        """
        from timetable.models import Subject
        
        # 1. Curriculum Metrics
        total_curricula = Curriculum.objects.filter(is_deleted=False).count()
        active_curricula = Curriculum.objects.filter(is_deleted=False, status='active').count()
        
        # 2. Subject Metrics
        total_subjects = Subject.objects.filter(is_active=True).count()
        
        # 3. Classes Covered
        classes_covered = GradeStructure.objects.filter(is_deleted=False, is_active=True).count()
        
        # 4. Learning Areas
        learning_areas_count = LearningArea.objects.filter(is_deleted=False, is_active=True).count()
        
        # 5. Subject Distribution by Curriculum (for chart)
        subject_distribution = (
            Subject.objects.filter(is_active=True)
            .values('curriculum__name', 'curriculum__code')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        
        subject_chart = []
        for item in subject_distribution:
            subject_chart.append({
                'name': item['curriculum__name'] or item['curriculum__code'],
                'count': item['count']
            })
        
        # 6. Class Coverage by Curriculum Level
        class_coverage = (
            GradeStructure.objects.filter(is_deleted=False, is_active=True)
            .values('curriculum__name', 'curriculum_level__name')
            .annotate(count=Count('id'))
            .order_by('curriculum__name', 'curriculum_level__order')
        )
        
        coverage_chart = []
        for item in class_coverage:
            coverage_chart.append({
                'curriculum': item['curriculum__name'],
                'level': item['curriculum_level__name'] or 'All Levels',
                'classes': item['count']
            })
        
        # 7. Subject Type Distribution
        type_distribution = (
            Subject.objects.filter(is_active=True)
            .values('subject_type')
            .annotate(count=Count('id'))
        )
        
        type_chart = []
        type_colors = {
            'compulsory': '#16a34a',
            'optional': '#ca8a04',
            'elective': '#6366f1'
        }
        for item in type_distribution:
            stype = item['subject_type']
            type_chart.append({
                'name': stype.title(),
                'value': item['count'],
                'color': type_colors.get(stype, '#6b7280')
            })
        
        # 8. Learning Area Distribution
        area_distribution = (
            Subject.objects.filter(is_active=True, learning_area__isnull=False)
            .values('learning_area__name', 'learning_area__color_hex')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        
        area_chart = []
        for item in area_distribution:
            area_chart.append({
                'name': item['learning_area__name'],
                'count': item['count'],
                'color': item['learning_area__color_hex'] or '#6366f1'
            })
        
        return Response({
            'metrics': {
                'total_curricula': total_curricula,
                'active_curricula': active_curricula,
                'total_subjects': total_subjects,
                'classes_covered': classes_covered,
                'learning_areas': learning_areas_count,
            },
            'subject_distribution': subject_chart,
            'class_coverage': coverage_chart,
            'type_distribution': type_chart,
            'area_distribution': area_chart,
        })

    @action(detail=True, methods=['post'])
    def phase_out(self, request, pk=None):
        """
        Mark a curriculum as phased_out and deactivate all its grades.
        Optionally deactivate only specific grade levels by name:
          Body: { "grade_names": ["Class 1", "Class 2", ...], "deactivate_grades": true }
        """
        curriculum = self.get_object()
        grade_names = request.data.get('grade_names', [])
        deactivate_grades = request.data.get('deactivate_grades', True)

        # Mark curriculum as phased_out
        curriculum.status = 'phased_out'
        curriculum.is_active = False
        curriculum.save()

        grades_updated = 0
        if deactivate_grades:
            grade_qs = GradeStructure.objects.filter(
                curriculum=curriculum, is_deleted=False
            )
            if grade_names:
                grade_qs = grade_qs.filter(name__in=grade_names)
            grades_updated = grade_qs.update(is_active=False)

        return Response({
            'success': True,
            'curriculum': curriculum.name,
            'status': 'phased_out',
            'grades_deactivated': grades_updated,
            'message': f'"{curriculum.name}" marked as phased out. {grades_updated} grade(s) deactivated.'
        })

    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        """Re-activate a previously phased-out curriculum and its grades."""
        curriculum = self.get_object()
        grade_names = request.data.get('grade_names', [])

        curriculum.status = 'active'
        curriculum.is_active = True
        curriculum.save()

        grade_qs = GradeStructure.objects.filter(
            curriculum=curriculum, is_deleted=False
        )
        if grade_names:
            grade_qs = grade_qs.filter(name__in=grade_names)
        grades_updated = grade_qs.update(is_active=True)

        return Response({
            'success': True,
            'curriculum': curriculum.name,
            'status': 'active',
            'grades_activated': grades_updated,
            'message': f'"{curriculum.name}" restored. {grades_updated} grade(s) re-activated.'
        })


class LearningAreaViewSet(SoftDeleteViewSet):
    """ViewSet for managing Learning Areas (subject categories)"""
    queryset = LearningArea.objects.all()
    serializer_class = LearningAreaSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None


class CurriculumLevelViewSet(SoftDeleteViewSet):
    queryset = CurriculumLevel.objects.all()
    serializer_class = CurriculumLevelSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset().select_related('curriculum')
        from core.models import InstitutionProfile
        try:
            inst = InstitutionProfile.get_instance()
        except Exception:
            return qs

        itype = inst.institution_type

        # Map institution types to the curriculum level names they include
        LEVEL_MAP = {
            'lower_primary': {
                'CBC': ['Pre-Primary', 'Lower Primary'],
                '844': ['Primary'],
            },
            'upper_primary': {
                'CBC': ['Upper Primary'],
                '844': ['Primary'],
            },
            'primary': {
                'CBC': ['Pre-Primary', 'Lower Primary', 'Upper Primary'],
                '844': ['Primary'],
            },
            'secondary': {
                'CBC': ['Junior Secondary', 'Senior Secondary'],
                '844': ['Secondary'],
            },
            'mixed': None,  # all levels
        }

        if itype in LEVEL_MAP:
            mapping = LEVEL_MAP[itype]
            if mapping is not None:
                level_q = Q()
                for curr_code, level_names in mapping.items():
                    level_q |= Q(curriculum__code=curr_code, name__in=level_names)
                qs = qs.filter(level_q)

        return qs

class GradeStructureViewSet(SoftDeleteViewSet):
    queryset = GradeStructure.objects.all()
    serializer_class = GradeStructureSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset().select_related('curriculum', 'curriculum_level')
        from core.models import InstitutionProfile
        try:
            inst = InstitutionProfile.get_instance()
        except Exception:
            return qs

        itype = inst.institution_type

        # Map institution types to the CBC curriculum level names they include
        CBC_LEVELS = {
            'lower_primary': ['Pre-Primary', 'Lower Primary'],
            'upper_primary': ['Upper Primary'],
            'primary':       ['Pre-Primary', 'Lower Primary', 'Upper Primary'],
            'secondary':     ['Junior Secondary', 'Senior Secondary'],
            'mixed':         None,  # all CBC levels
        }

        # Map institution types to the 8-4-4 curriculum level names they include
        EIGHT_FOUR_LEVELS = {
            'lower_primary': ['Primary'],   # Class 1-3 (level_order <= 3)
            'upper_primary': ['Primary'],   # Class 4-8 (level_order 4-8)
            'primary':       ['Primary'],
            'secondary':     ['Secondary'],
            'mixed':         ['Secondary'], # only Form 3 & Form 4 for mixed
        }

        if itype in CBC_LEVELS:
            cbc_levels = CBC_LEVELS[itype]
            eight_four_levels = EIGHT_FOUR_LEVELS[itype]

            # Build CBC filter
            if cbc_levels is None:
                cbc_q = Q(curriculum__code='CBC')
            else:
                cbc_q = Q(curriculum__code='CBC', curriculum_level__name__in=cbc_levels)

            # Build 8-4-4 filter (with extra range constraints for sub-primary)
            if itype == 'mixed':
                eight_four_q = Q(curriculum__code='844', code__in=['F3', 'F4'])
            elif itype == 'lower_primary':
                eight_four_q = Q(
                    curriculum__code='844',
                    curriculum_level__name='Primary',
                    level_order__lte=3
                )
            elif itype == 'upper_primary':
                eight_four_q = Q(
                    curriculum__code='844',
                    curriculum_level__name='Primary',
                    level_order__gte=4,
                    level_order__lte=8
                )
            else:
                eight_four_q = Q(
                    curriculum__code='844',
                    curriculum_level__name__in=eight_four_levels
                )

            qs = qs.filter(cbc_q | eight_four_q)

        # tertiary, university, tvet — no filtering, return all
        return qs

    @action(detail=False, methods=['post'])
    def bulk_set_active(self, request):
        """
        Bulk activate or deactivate grade structures.
        Body: { "grade_ids": [1, 2, 3], "is_active": true/false }
        Can also match by curriculum code: { "curriculum_code": "844", "is_active": false }
        """
        grade_ids = request.data.get('grade_ids', [])
        is_active = request.data.get('is_active', False)
        curriculum_code = request.data.get('curriculum_code', None)

        qs = GradeStructure.objects.filter(is_deleted=False)

        if grade_ids:
            qs = qs.filter(id__in=grade_ids)
        elif curriculum_code:
            qs = qs.filter(curriculum__code=curriculum_code)
        else:
            return Response(
                {'error': 'Provide grade_ids or curriculum_code'},
                status=status.HTTP_400_BAD_REQUEST
            )

        count = qs.update(is_active=is_active)
        return Response({
            'success': True,
            'updated_count': count,
            'is_active': is_active,
            'message': f'{count} grade(s) {"activated" if is_active else "deactivated"} successfully.'
        })

class StreamViewSet(SoftDeleteViewSet):
    queryset = Stream.objects.all()
    serializer_class = StreamSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

class AdmissionConfigViewSet(viewsets.ModelViewSet):
    queryset = AdmissionConfig.objects.all()
    serializer_class = AdmissionConfigSerializer
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request, *args, **kwargs):
        # Always return the first/only config
        obj, created = AdmissionConfig.objects.get_or_create(id=1)
        serializer = self.get_serializer(obj)
        return Response(serializer.data)


class AdmissionWorkflowConfigViewSet(viewsets.ModelViewSet):
    """
    Singleton viewset for AdmissionWorkflowConfig.
    GET  /api/settings/admission-workflow/   → returns current config
    PATCH /api/settings/admission-workflow/1/ → partial update
    """
    queryset = AdmissionWorkflowConfig.objects.all()
    serializer_class = AdmissionWorkflowConfigSerializer
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request, *args, **kwargs):
        obj = AdmissionWorkflowConfig.get_instance()
        return Response(self.get_serializer(obj).data)

    def update(self, request, *args, **kwargs):
        kwargs['partial'] = True  # always allow partial updates
        obj = AdmissionWorkflowConfig.get_instance()
        serializer = self.get_serializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    def stages(self, request):
        """Return the list of currently active stages in order."""
        obj = AdmissionWorkflowConfig.get_instance()
        return Response({'active_stages': obj.active_stages})

class StudentStatusViewSet(SoftDeleteViewSet):
    queryset = StudentStatus.objects.all()
    serializer_class = StudentStatusSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

class PromotionRuleViewSet(viewsets.ModelViewSet):
    queryset = PromotionRule.objects.all()
    serializer_class = PromotionRuleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request, *args, **kwargs):
        obj, created = PromotionRule.objects.get_or_create(id=1)
        serializer = self.get_serializer(obj)
        return Response(serializer.data)

class DemographicConfigViewSet(SoftDeleteViewSet):
    queryset = DemographicConfig.objects.all()
    serializer_class = DemographicConfigSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

class SchoolCalendarViewSet(SoftDeleteViewSet):
    queryset = SchoolCalendar.objects.all()
    serializer_class = SchoolCalendarSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

# Enrollment ViewSet
from rest_framework.decorators import action
from django.db import transaction
from django.shortcuts import get_object_or_404
from student_management.models import Student
from .models import Enrollment
from .serializers import (
    EnrollmentSerializer, EnrollmentCreateSerializer, EnrollmentUpdateSerializer,
    EnrollmentTimelineSerializer, PromotionSerializer, RepeatSerializer,
    CurriculumChangeSerializer
)

class EnrollmentViewSet(SoftDeleteViewSet):
    queryset = Enrollment.objects.all()
    serializer_class = EnrollmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['student', 'academic_year', 'term', 'curriculum', 'grade', 'stream', 'status', 'enrollment_type', 'is_active']
    search_fields = ['student__student__first_name', 'student__student__last_name', 'remarks']
    ordering_fields = ['enrollment_date', 'created_at']
    
    def get_serializer_class(self):
        if self.action == 'create':
            return EnrollmentCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return EnrollmentUpdateSerializer
        elif self.action == 'timeline':
            return EnrollmentTimelineSerializer
        return EnrollmentSerializer
    
        return EnrollmentSerializer
    
    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        
        # Auto-correct Curriculum to match Grade (Prevent Verification Error)
        if 'grade' in data:
            try:
                from .models import GradeStructure
                grade = GradeStructure.objects.get(pk=data['grade'])
                data['curriculum'] = grade.curriculum.id
            except Exception as e:
                print(f"Grade/Curriculum Lookup Failed: {e}")

        serializer = self.get_serializer(data=data)
        if not serializer.is_valid():
            print("Enrollment Validation Errors:", serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        enrollment = serializer.save(created_by=self.request.user, updated_by=self.request.user)
        try:
            self._sync_academics(enrollment)
            self.trigger_auto_billing(enrollment) # Added Auto-Billing
        except Exception as e:
            print(f"Error syncing/billing: {e}")

    def _sync_academics(self, enrollment):
        """
        Syncs the created enrollment to the Academics module.
        Ensures a ClassSession exists and enrolls the student in it.
        """
        from academics.models import ClassSession, StudentSessionEnrollment
        from django.utils import timezone

        # 1. Find or Create the Class Session
        # Logic: A session is defined by Grade + Term + Year + Curriculum
        valid_curriculum = enrollment.curriculum
        
        session, created = ClassSession.objects.get_or_create(
            grade=enrollment.grade,
            term=enrollment.term,
            academic_year=enrollment.academic_year,
            curriculum=valid_curriculum,
            defaults={
                'name': f"{enrollment.grade.name} - {enrollment.term.name} {enrollment.academic_year.name}",
                'status': 'active',
                'start_date': enrollment.term.start_date,
                'end_date': enrollment.term.end_date
            }
        )

        # 2. Enroll Student in Session
        # Requirement: Student needs an Intake. using student.intake or trying to fetch one.
        student = enrollment.student
        intake = student.intake
        
        if not intake:
            # Fallback: Try to find any active intake for this year or just skip with warning
            from .models import Intake
            intake = Intake.objects.filter(academic_year=enrollment.academic_year, is_active=True).first()
        
        if intake:
            StudentSessionEnrollment.objects.update_or_create(
                student=student,
                session=session,
                defaults={
                    'intake': intake,
                    'status': 'active',
                    'is_active': True,
                    'stream': enrollment.stream,
                    'reporting_date': enrollment.enrollment_date or timezone.now().date()
                }
            )
        else:
            print(f"Warning: Could not sync enrollment for {student} - No Intake found.")

    def trigger_auto_billing(self, enrollment):
        """
        Attempts to generate an invoice for the student upon enrollment/reporting.
        """
        from fees.services import BillingService
        from fees.models import FeeStructure
        
        # 1. Find standard Fee Structure for this enrollment context
        structure = FeeStructure.objects.filter(
            grade=enrollment.grade,
            term=enrollment.term,
            academic_year=enrollment.academic_year,
            curriculum=enrollment.curriculum,
            status='ACTIVE'
        ).first()

        # Fallback: Ignore Curriculum if strict match fails (common config issue)
        if not structure:
             structure = FeeStructure.objects.filter(
                grade=enrollment.grade,
                term=enrollment.term,
                academic_year=enrollment.academic_year,
                grade__name=enrollment.grade.name, # Ensure name match if ID differs (unlikely)
                status='ACTIVE'
            ).first()
            
        if not structure:
            print(f"Auto-Billing skipped: No Active Fee Structure found for {enrollment.academic_year} {enrollment.term} {enrollment.grade}.")
            return

        # 2. Collect Mandatory Items
        items = []
        for item in structure.items.filter(is_mandatory=True):
            items.append({
                'id': item.id,
                'amount': float(item.amount) 
            })
            
        if not items:
            print("Auto-Billing skipped: No mandatory fee items found.")
            return

        # 3. Generate Invoice
        payload = {
            'student_id': enrollment.student.id,
            'structure_id': structure.id,
            'items': items,
            'due_date': enrollment.enrollment_date or timezone.now().date(),
            'remarks': 'Auto-generated upon reporting.',
            'is_automated': True
        }
        
        try:
            BillingService.generate_invoice(payload, user=self.request.user)
            print(f"Auto-Billing Success: Invoice generated for {enrollment.student}")
        except Exception as e:
            print(f"Auto-Billing Error: {e}")
            
    @action(detail=False, methods=['post'], url_path='fix-anomalies')
    def fix_anomalies(self, request):
        from django.core.management import call_command
        from io import StringIO
        
        out = StringIO()
        try:
            call_command('check_future_enrollments', '--auto-fix', stdout=out)
            output = out.getvalue()
            return Response({'message': 'Anomalies check completed', 'output': output}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)
    
    @action(detail=False, methods=['post'])
    @transaction.atomic
    def promote(self, request):
        """
        Promote student(s) to the next grade/class.
        Closes current enrollment and creates new one.
        """
        serializer = PromotionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        student_ids = data['student_ids']
        target_academic_year = data['target_academic_year']
        target_term = data['target_term']
        target_grade = data.get('target_grade')
        remarks = data.get('remarks', 'Promoted to next class')
        
        promoted_enrollments = []
        errors = []
        
        for student_id in student_ids:
            try:
                student = get_object_or_404(Student, id=student_id)
                
                # Get current active enrollment
                current_enrollment = Enrollment.objects.filter(
                    student=student,
                    is_active=True,
                    is_deleted=False
                ).first()
                
                if not current_enrollment:
                    errors.append({
                        'student_id': student_id,
                        'error': 'No active enrollment found'
                    })
                    continue
                
                # Determine target grade if not provided
                if not target_grade:
                    # Find next grade in same curriculum based on level_order
                    next_grade = GradeStructure.objects.filter(
                        curriculum=current_enrollment.curriculum,
                        level_order__gt=current_enrollment.grade.level_order,
                        is_deleted=False
                    ).order_by('level_order').first()
                    
                    if not next_grade:
                        errors.append({
                            'student_id': student_id,
                            'error': 'No next grade found in curriculum'
                        })
                        continue
                    
                    target_grade = next_grade
                
                # Close current enrollment
                current_enrollment.close_enrollment(
                    status=Enrollment.EnrollmentStatus.PROMOTED,
                    exit_date=timezone.now().date(),
                    remarks=remarks
                )
                
                # Create new enrollment
                new_enrollment = Enrollment.objects.create(
                    student=student,
                    academic_year=target_academic_year,
                    term=target_term,
                    curriculum=current_enrollment.curriculum,
                    grade=target_grade,
                    stream=None,  # Stream will be assigned separately
                    status=Enrollment.EnrollmentStatus.ACTIVE,
                    enrollment_type=Enrollment.EnrollmentType.PROMOTION,
                    enrollment_date=timezone.now().date(),
                    previous_enrollment=current_enrollment,
                    remarks=remarks,
                    is_active=True,
                    created_by=request.user
                )
                
                promoted_enrollments.append(EnrollmentSerializer(new_enrollment).data)
                
            except Exception as e:
                errors.append({
                    'student_id': student_id,
                    'error': str(e)
                })
        
        return Response({
            'success': True,
            'promoted_count': len(promoted_enrollments),
            'promoted_enrollments': promoted_enrollments,
            'errors': errors
        }, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['post'])
    @transaction.atomic
    def repeat(self, request):
        """
        Mark student to repeat current class.
        Closes current enrollment and creates new one for same grade.
        """
        serializer = RepeatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        student = get_object_or_404(Student, id=data['student_id'])
        academic_year = data['academic_year']
        term = data['term']
        remarks = data.get('remarks', 'Repeating class')
        
        # Get current active enrollment
        current_enrollment = Enrollment.objects.filter(
            student=student,
            is_active=True,
            is_deleted=False
        ).first()
        
        if not current_enrollment:
            return Response({
                'success': False,
                'error': 'No active enrollment found for this student'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Close current enrollment
        current_enrollment.close_enrollment(
            status=Enrollment.EnrollmentStatus.REPEATED,
            exit_date=timezone.now().date(),
            remarks=remarks
        )
        
        # Create new enrollment for same grade
        new_enrollment = Enrollment.objects.create(
            student=student,
            academic_year=academic_year,
            term=term,
            curriculum=current_enrollment.curriculum,
            grade=current_enrollment.grade,
            stream=current_enrollment.stream,
            status=Enrollment.EnrollmentStatus.ACTIVE,
            enrollment_type=Enrollment.EnrollmentType.REPEAT,
            enrollment_date=timezone.now().date(),
            previous_enrollment=current_enrollment,
            remarks=remarks,
            is_active=True,
            created_by=request.user
        )
        
        return Response({
            'success': True,
            'enrollment': EnrollmentSerializer(new_enrollment).data
        }, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'])
    def transfer_out(self, request, pk=None):
        """Close enrollment with transfer status"""
        enrollment = self.get_object()
        remarks = request.data.get('remarks', 'Transferred out')
        exit_date = request.data.get('exit_date', timezone.now().date())
        
        enrollment.close_enrollment(
            status=Enrollment.EnrollmentStatus.TRANSFERRED_OUT,
            exit_date=exit_date,
            remarks=remarks
        )
        enrollment.updated_by = request.user
        enrollment.save()
        
        return Response({
            'success': True,
            'enrollment': EnrollmentSerializer(enrollment).data
        })
    
    @action(detail=False, methods=['post'])
    @transaction.atomic
    def change_curriculum(self, request):
        """
        Change student's curriculum.
        Closes current enrollment and creates new one with different curriculum.
        """
        serializer = CurriculumChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        student = get_object_or_404(Student, id=data['student_id'])
        new_curriculum = data['new_curriculum']
        new_grade = data['new_grade']
        academic_year = data['academic_year']
        term = data['term']
        remarks = data.get('remarks', f'Curriculum changed to {new_curriculum.name}')
        
        # Get current active enrollment
        current_enrollment = Enrollment.objects.filter(
            student=student,
            is_active=True,
            is_deleted=False
        ).first()
        
        if not current_enrollment:
            return Response({
                'success': False,
                'error': 'No active enrollment found for this student'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Close current enrollment
        current_enrollment.close_enrollment(
            status=Enrollment.EnrollmentStatus.COMPLETED,
            exit_date=timezone.now().date(),
            remarks=remarks
        )
        
        # Create new enrollment with new curriculum
        new_enrollment = Enrollment.objects.create(
            student=student,
            academic_year=academic_year,
            term=term,
            curriculum=new_curriculum,
            grade=new_grade,
            stream=None,
            status=Enrollment.EnrollmentStatus.ACTIVE,
            enrollment_type=Enrollment.EnrollmentType.CURRICULUM_CHANGE,
            enrollment_date=timezone.now().date(),
            previous_enrollment=current_enrollment,
            remarks=remarks,
            is_active=True,
            created_by=request.user
        )
        
        return Response({
            'success': True,
            'enrollment': EnrollmentSerializer(new_enrollment).data
        }, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['post'])
    @transaction.atomic
    def bulk_enroll(self, request):
        """Bulk enroll multiple students"""
        enrollments_data = request.data.get('enrollments', [])
        
        if not enrollments_data:
            return Response({
                'success': False,
                'error': 'No enrollment data provided'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        created_enrollments = []
        errors = []
        
        for enrollment_data in enrollments_data:
            try:
                serializer = EnrollmentCreateSerializer(data=enrollment_data)
                serializer.is_valid(raise_exception=True)
                enrollment = serializer.save(created_by=request.user)
                created_enrollments.append(EnrollmentSerializer(enrollment).data)
            except Exception as e:
                errors.append({
                    'data': enrollment_data,
                    'error': str(e)
                })
        
        return Response({
            'success': True,
            'created_count': len(created_enrollments),
            'enrollments': created_enrollments,
            'errors': errors
        }, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        """Close an enrollment with specified status"""
        enrollment = self.get_object()
        close_status = request.data.get('status', Enrollment.EnrollmentStatus.COMPLETED)
        exit_date = request.data.get('exit_date', timezone.now().date())
        remarks = request.data.get('remarks', '')
        
        enrollment.close_enrollment(
            status=close_status,
            exit_date=exit_date,
            remarks=remarks
        )
        enrollment.updated_by = request.user
        enrollment.save()
        
        return Response({
            'success': True,
            'enrollment': EnrollmentSerializer(enrollment).data
        })
    
    @action(detail=False, methods=['get'])
    def timeline(self, request):
        """Get enrollment timeline for a student"""
        student_id = request.query_params.get('student_id')
        
        if not student_id:
            return Response({
                'success': False,
                'error': 'student_id parameter is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        enrollments = Enrollment.objects.filter(
            student_id=student_id,
            is_deleted=False
        ).order_by('enrollment_date')
        
        serializer = EnrollmentTimelineSerializer(enrollments, many=True)
        
        return Response({
            'success': True,
            'student_id': student_id,
            'timeline': serializer.data
        })

    @action(detail=False, methods=['get'], url_path='unreported')
    def unreported(self, request):
        """
        Get students who were enrolled in the previous term but haven't
        reported (no active enrollment) in the current term.
        """
        current_year = AcademicYear.objects.filter(is_current=True).first()
        current_term = Term.objects.filter(is_current=True).first()

        if not current_year or not current_term:
            return Response({
                'success': False,
                'error': 'No current academic year or term configured.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Find the previous term
        prev_term = Term.objects.filter(
            academic_year=current_term.academic_year,
            start_date__lt=current_term.start_date,
            is_deleted=False
        ).order_by('-start_date').first()

        if not prev_term:
            # Try last term of the previous academic year
            prev_year = AcademicYear.objects.filter(
                start_date__lt=current_year.start_date,
                is_deleted=False
            ).order_by('-start_date').first()
            if prev_year:
                prev_term = Term.objects.filter(
                    academic_year=prev_year,
                    is_deleted=False
                ).order_by('-start_date').first()

        if not prev_term:
            return Response({
                'success': True,
                'current_term': current_term.name,
                'current_year': current_year.name,
                'previous_term': None,
                'unreported': [],
                'total': 0
            })

        # Students enrolled in previous term
        prev_student_ids = set(
            Enrollment.objects.filter(
                term=prev_term,
                is_deleted=False,
                status__in=['active', 'promoted']
            ).values_list('student_id', flat=True)
        )

        # Students already enrolled in current term
        current_student_ids = set(
            Enrollment.objects.filter(
                term=current_term,
                academic_year=current_year,
                is_deleted=False,
            ).values_list('student_id', flat=True)
        )

        # Unreported = in previous term but not in current term
        unreported_ids = prev_student_ids - current_student_ids

        # Also filter: student must still be "active" status (not withdrawn/expelled/etc.)
        unreported_enrollments = Enrollment.objects.filter(
            student_id__in=unreported_ids,
            term=prev_term,
            is_deleted=False,
            student__status='active'
        ).select_related(
            'student', 'student__student', 'grade', 'stream', 'curriculum'
        ).order_by('student__student__first_name')

        # Optional grade filter
        grade_filter = request.query_params.get('grade')
        if grade_filter:
            unreported_enrollments = unreported_enrollments.filter(grade_id=grade_filter)

        results = []
        for enr in unreported_enrollments:
            results.append({
                'student_id': enr.student_id,
                'admission_number': enr.student.admission_number,
                'student_name': enr.student.student.get_full_name() if callable(enr.student.student.get_full_name) else str(enr.student.student.get_full_name),
                'grade_id': enr.grade_id,
                'grade_name': enr.grade.name if enr.grade else '',
                'stream_id': enr.stream_id,
                'stream_name': enr.stream.name if enr.stream else '',
                'curriculum_id': enr.curriculum_id,
                'curriculum_name': enr.curriculum.name if enr.curriculum else '',
                'last_term': prev_term.name,
                'last_year': str(prev_term.academic_year.name) if prev_term.academic_year else '',
            })

        return Response({
            'success': True,
            'current_term': current_term.name,
            'current_year': current_year.name,
            'previous_term': prev_term.name,
            'unreported': results,
            'total': len(results)
        })
