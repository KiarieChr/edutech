from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.utils import timezone
from django.db.models import Count
from .models import (
    AcademicYear, Term, Curriculum, GradeStructure, Stream,
    AdmissionConfig, StudentStatus, PromotionRule, DemographicConfig, SchoolCalendar, Intake,
    CurriculumLevel, LearningArea
)
from .serializers import (
    AcademicYearSerializer, TermSerializer, CurriculumSerializer,
    GradeStructureSerializer, StreamSerializer, AdmissionConfigSerializer,
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

class GradeStructureViewSet(SoftDeleteViewSet):
    queryset = GradeStructure.objects.all()
    serializer_class = GradeStructureSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

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
from accounts.models import Student
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
    filterset_fields = ['student', 'academic_year', 'term', 'curriculum', 'grade', 'stream', 'status', 'is_active']
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
