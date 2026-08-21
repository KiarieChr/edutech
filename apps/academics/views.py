from django.db import models
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import ClassSession, StudentSessionEnrollment
from student_settings.models import AcademicYear, Term, GradeStructure, CurriculumLevel
from .serializers import ClassSessionSerializer, StudentSessionEnrollmentSerializer

# Maps institution_type → allowed CurriculumLevel names.
# A secondary school only gets Junior/Senior Secondary (CBC) or Secondary (8-4-4).
INSTITUTION_LEVEL_MAP = {
    'lower_primary':    ['Pre-Primary', 'Lower Primary'],
    'upper_primary':    ['Upper Primary'],
    'primary':          ['Pre-Primary', 'Lower Primary', 'Upper Primary', 'Primary'],
    'junior_secondary': ['Junior Secondary'],
    'senior_secondary': ['Senior Secondary'],
    'secondary':        ['Junior Secondary', 'Senior Secondary', 'Secondary'],
    'mixed':            None,   # None = no filtering, all levels
    'tertiary':         None,
    'university':       None,
    'tvet':             None,
}

from core.permissions import ModuleRequiredPermission

class ClassSessionViewSet(viewsets.ModelViewSet):
    queryset = ClassSession.objects.all()
    serializer_class = ClassSessionSerializer
    permission_classes = [permissions.IsAuthenticated, ModuleRequiredPermission]
    required_module = 'academics'
    filterset_fields = ['grade', 'term', 'academic_year', 'curriculum', 'status']
    search_fields = ['name', 'grade__name']
    ordering_fields = ['academic_year__start_date', 'term__start_date', 'grade__level_order']

    def _get_institution_level_names(self):
        """Return the list of allowed CurriculumLevel names for this institution, or None for all."""
        try:
            from core.models import InstitutionProfile
            inst = InstitutionProfile.objects.first()
            if inst:
                return INSTITUTION_LEVEL_MAP.get(inst.institution_type)
        except Exception:
            pass
        return None

    def _filter_grades_by_institution(self, grades_qs):
        """Filter a GradeStructure queryset to only include grades
        whose curriculum_level matches the institution type."""
        allowed = self._get_institution_level_names()
        if allowed is not None:
            grades_qs = grades_qs.filter(curriculum_level__name__in=allowed)
        return grades_qs

    def get_queryset(self):
        from django.db.models import Count
        qs = super().get_queryset().annotate(
            enrollment_count=Count('student_enrollments', filter=models.Q(student_enrollments__is_active=True))
        )
       
        
        from django.utils import timezone
        today = timezone.now().date()
        
        # 1. Open scheduled sessions that reached start_date
        ClassSession.objects.filter(
            status='scheduled',
            start_date__lte=today
        ).update(status='active')
        
        # 2. Close active sessions that passed end_date
        ClassSession.objects.filter(
            status='active',
            end_date__lt=today
        ).update(status='closed')
        
        # Custom filter: current academic year only
        current_year = self.request.query_params.get('current_year')
        if current_year and current_year.lower() in ('true', '1', 'yes'):
            qs = qs.filter(academic_year__is_current=True)

        # Custom filter: Intake Progression
        intake_id = self.request.query_params.get('intake')
        if intake_id:
            from student_settings.models import Intake, AcademicYear, GradeStructure
            try:
                intake = Intake.objects.get(pk=intake_id)
                if intake.entry_grade:
                    # Logic to determine expected sessions (Year + Grade)
                    start_year = intake.academic_year
                    start_grade = intake.entry_grade
                    curriculum = start_grade.curriculum
                    
                    # Subsequent years
                    years = list(AcademicYear.objects.filter(
                        start_date__gte=start_year.start_date,
                        is_deleted=False
                    ).order_by('start_date'))
                    
                    # Subsequent grades
                    grades = list(GradeStructure.objects.filter(
                        curriculum=curriculum,
                        level_order__gte=start_grade.level_order,
                        is_active=True,
                        is_deleted=False
                    ).order_by('level_order'))
                    
                    # Map Year -> Grade
                    # Note: Using Q objects to construct complex OR query
                    from django.db.models import Q
                    progression_filter = Q()
                    
                    # Zip creates pairs until shortest list is exhausted
                    for year, grade in zip(years, grades):
                        progression_filter |= Q(academic_year=year, grade=grade)
                    
                    if progression_filter:
                        qs = qs.filter(progression_filter)
                    else:
                        qs = qs.none()
                else:
                    qs = qs.none()
            except (Intake.DoesNotExist, ValueError):
                qs = qs.none()

        return qs

    @action(detail=False, methods=['post'])
    def auto_generate(self, request):
        """
        Auto-generate class sessions.
        Mode 1: By Intake (Intake Progression) -> Generates sessions for the lifecycle of an intake.
        Mode 2: By Academic Year (Bulk) -> Generates sessions for all grades in one year.
        """
        intake_id = request.data.get('intake_id')
        year_id = request.data.get('academic_year')
        
        from student_settings.models import Intake, AcademicYear, Term, GradeStructure
        
        created_count = 0

        # --- MODE 1: Intake Progression ---
        if intake_id:
            try:
                intake = Intake.objects.get(pk=intake_id)
            except Intake.DoesNotExist:
                return Response({"error": "Intake not found"}, status=status.HTTP_404_NOT_FOUND)

            if not intake.entry_grade:
                return Response({"error": "Intake must have an Entry Grade assigned to auto-generate sessions."}, status=status.HTTP_400_BAD_REQUEST)
            
            start_year = intake.academic_year
            start_grade = intake.entry_grade
            curriculum = start_grade.curriculum

            # 1. Get Progression of Years (starting from intake year)
            # We assume academic years are sequential by start_date
            subsequent_years = AcademicYear.objects.filter(
                start_date__gte=start_year.start_date,
                is_deleted=False
            ).order_by('start_date')

            # 2. Get Progression of Grades (starting from entry grade)
            subsequent_grades = GradeStructure.objects.filter(
                curriculum=curriculum,
                level_order__gte=start_grade.level_order,
                is_active=True,
                is_deleted=False
            ).order_by('level_order')
            # Removed _filter_grades_by_institution here so it doesn't strip the intake's intended progression map
            # subsequent_grades = self._filter_grades_by_institution(subsequent_grades)

            # 3. Zip them to map Year X -> Grade X
            # We only generate as far as we have BOTH years and grades
            progression_map = list(zip(subsequent_years, subsequent_grades))

            if not progression_map:
                return Response({"error": "Could not determine progression map. Ensure there are active future Academic Years and Grades in the curriculum starting from the entry grade."}, status=status.HTTP_400_BAD_REQUEST)

            # Validate Inconsistency: Do we have enough years for the grades?
            # User requirement: "IF NOT RAISE AN INCOSITENCY ERROR"
            # If we have more grades than years, it means we haven't set up the future years yet.
            if len(subsequent_grades) > len(subsequent_years):
                 missing_count = len(subsequent_grades) - len(subsequent_years)
                 # We can either error or warn. The prompt says "RAISE AN INCOSITENCY ERROR"
                 # if "TERMS NO BEEN SETUP".
                 return Response({
                     "error": f"Inconsistency Error: configurations for future Academic Years are missing. Need {missing_count} more years to complete the curriculum progression for this intake."
                 }, status=status.HTTP_400_BAD_REQUEST)

            skipped_years = []
            
            for year, grade in progression_map:
                # Get Terms for this year
                terms = Term.objects.filter(academic_year=year, is_deleted=False).order_by('start_date')
                
                if not terms.exists():
                     # Instead of erroring, skip and log
                     skipped_years.append(year.name)
                     continue

                for term in terms:
                    # Check existing
                    if ClassSession.objects.filter(academic_year=year, term=term, grade=grade).exists():
                        continue
                        
                    ClassSession.objects.create(
                        academic_year=year,
                        term=term,
                        grade=grade,
                        curriculum=grade.curriculum,
                        curriculum_level=grade.curriculum_level,
                        start_date=term.start_date,
                        end_date=term.end_date
                    )
                    created_count += 1
            
            msg = f"Successfully generated {created_count} progression sessions for Intake '{intake.name}'."
            if skipped_years:
                msg += f" Note: skipped {len(skipped_years)} years ({', '.join(skipped_years)}) due to missing terms."
                
            return Response({
                "message": msg,
                "created_count": created_count,
                "partial": bool(skipped_years)
            })

        # --- MODE 2: Single Academic Year (Bulk) ---
        
        if year_id:
            try:
                academic_year = AcademicYear.objects.get(pk=year_id)
            except AcademicYear.DoesNotExist:
                return Response({"error": "Academic Year not found"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            academic_year = AcademicYear.objects.filter(is_current=True).first()
            if not academic_year:
                # Fallback to latest
                academic_year = AcademicYear.objects.order_by('-start_date').first()
        
        if not academic_year:
             return Response({"error": "No Academic Year found"}, status=status.HTTP_400_BAD_REQUEST)
             
        terms = Term.objects.filter(academic_year=academic_year, is_deleted=False)
        grades = GradeStructure.objects.filter(
            is_active=True, 
            is_deleted=False, 
            curriculum__is_deleted=False,
            curriculum__is_active=True,
            curriculum__status='active'
        )
        # Filter grades to only those matching the institution type
        grades = self._filter_grades_by_institution(grades)

        if not grades.exists():
            return Response({
                "error": "No active grades found matching your institution type. Check your Institution Profile settings and ensure grades have curriculum levels assigned.",
            }, status=status.HTTP_400_BAD_REQUEST)
        
        for term in terms:
            for grade in grades:
                # Check for existing
                if ClassSession.objects.filter(
                    academic_year=academic_year,
                    term=term,
                    grade=grade
                ).exists():
                    continue
                    
                ClassSession.objects.create(
                    academic_year=academic_year,
                    term=term,
                    grade=grade,
                    curriculum=grade.curriculum,
                    curriculum_level=grade.curriculum_level,
                    start_date=term.start_date,
                    end_date=term.end_date
                )
                created_count += 1
                
        # Gather institution context for the response
        try:
            from core.models import InstitutionProfile
            inst = InstitutionProfile.objects.first()
            inst_type = inst.get_institution_type_display() if inst else 'Unknown'
        except Exception:
            inst_type = 'Unknown'

        return Response({
            "message": f"Successfully generated {created_count} class sessions for {academic_year.name}",
            "created_count": created_count,
            "academic_year": academic_year.name,
            "institution_type": inst_type,
            "grades_included": list(grades.values_list('name', flat=True)),
        })

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        session = self.get_object()
        session.status = 'active'
        session.save()
        return Response({
            "status": "active",
            "message": f"Successfully activated class session '{session.name}'."
        })

    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        session = self.get_object()
        session.status = 'closed'
        session.save()
        return Response({
            "status": "closed",
            "message": f"Successfully closed class session '{session.name}'."
        })

    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        session = self.get_object()
        session.status = 'archived'
        session.save()
        return Response({
            "status": "archived",
            "message": f"Successfully archived class session '{session.name}'."
        })

class StudentSessionEnrollmentViewSet(viewsets.ModelViewSet):
    queryset = StudentSessionEnrollment.objects.all()
    serializer_class = StudentSessionEnrollmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['student', 'session', 'intake', 'status', 'is_active']
    search_fields = ['student__student__first_name', 'student__student__last_name', 'session__name']
    ordering_fields = ['reporting_date', 'session__start_date', 'created_at']
    ordering = ['-created_at']

    def perform_create(self, serializer):
        enrollment = serializer.save()
        # Trigger Auto-Billing
        # "once the student is reported" -> usually implies creation of this record
        self.trigger_auto_billing(enrollment)

    def trigger_auto_billing(self, enrollment):
        """
        Attempts to generate an invoice for the student upon enrollment/reporting.
        Respects FinanceSettings.billing_mode:
          STRUCTURE  – legacy per-grade FeeStructure pipeline
          TEMPLATE   – modern grade-band FeeTemplate pipeline
          AUTO       – try template first, fall back to structure
        """
        from finance.models import FinanceSettings
        from django.utils import timezone

        settings = FinanceSettings.load()
        if not settings.auto_billing_enabled:
            return

        mode = settings.billing_mode  # STRUCTURE | TEMPLATE | AUTO

        grade = enrollment.session.grade
        term = enrollment.session.term
        year = enrollment.session.academic_year

        invoice = None

        # ── Template billing ──────────────────────────────────
        if mode in ('TEMPLATE', 'AUTO'):
            try:
                from fees.template_billing_service import TemplateBillingService
                svc = TemplateBillingService()
                template = svc.resolve_template(enrollment.student, term, year)
                if template:
                    line_items = svc.resolve_line_items(template, enrollment.student)
                    if line_items:
                        payload = {
                            'student_id': enrollment.student.id,
                            'template_id': template.id,
                            'items': [
                                {'vote_head_id': li.vote_head_id, 'amount': float(li.amount)}
                                for li in line_items
                            ],
                            'due_date': (timezone.now() + timezone.timedelta(days=settings.default_billing_days)).date(),
                            'remarks': 'Auto-generated (template) upon reporting.',
                            'is_automated': True,
                        }
                        invoice = svc.generate_invoice(payload, user=self.request.user)
                        print(f"Auto-Billing Success (template): Invoice for {enrollment.student}")
            except Exception as e:
                print(f"Auto-Billing template error: {e}")

        # ── Structure billing (legacy) ────────────────────────
        if invoice is None and mode in ('STRUCTURE', 'AUTO'):
            try:
                from fees.services import BillingService
                from fees.models import FeeStructure

                curriculum = enrollment.session.curriculum
                structure = FeeStructure.objects.filter(
                    grade=grade, term=term, academic_year=year,
                    curriculum=curriculum, status='ACTIVE',
                ).first()
                if not structure:
                    structure = FeeStructure.objects.filter(
                        grade=grade, term=term, academic_year=year,
                        status='ACTIVE',
                    ).first()

                if not structure:
                    print(f"Auto-Billing skipped: No Active Fee Structure for {year} {term} {grade}.")
                    return

                items = [
                    {'id': item.id, 'amount': float(item.amount)}
                    for item in structure.items.filter(is_mandatory=True)
                ]
                if not items:
                    print("Auto-Billing skipped: No mandatory fee items found.")
                    return

                payload = {
                    'student_id': enrollment.student.id,
                    'structure_id': structure.id,
                    'items': items,
                    'due_date': (timezone.now() + timezone.timedelta(days=settings.default_billing_days)).date(),
                    'remarks': 'Auto-generated upon reporting.',
                    'is_automated': True,
                }
                BillingService.generate_invoice(payload, user=self.request.user)
                print(f"Auto-Billing Success (structure): Invoice for {enrollment.student}")
            except Exception as e:
                print(f"Auto-Billing Error: {e}")

    @action(detail=True, methods=['post'])
    def transfer(self, request, pk=None):
        """Transfer a student from current session to a new session."""
        enrollment = self.get_object()
        new_session_id = request.data.get('new_session')
        if not new_session_id:
            return Response({"error": "new_session is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            new_session = ClassSession.objects.get(pk=new_session_id)
        except ClassSession.DoesNotExist:
            return Response({"error": "Target session not found"}, status=status.HTTP_404_NOT_FOUND)
        if StudentSessionEnrollment.objects.filter(student=enrollment.student, session=new_session).exists():
            return Response({"error": "Student is already enrolled in the target session"}, status=status.HTTP_400_BAD_REQUEST)
        enrollment.status = 'transferred_out'
        enrollment.is_active = False
        enrollment.save()
        new_enrollment = StudentSessionEnrollment.objects.create(
            student=enrollment.student,
            session=new_session,
            intake=enrollment.intake,
            stream=enrollment.stream,
            status='active',
            is_active=True,
        )
        self.trigger_auto_billing(new_enrollment)
        return Response({
            "message": f"Transferred {enrollment.student} to {new_session.name}",
            "new_enrollment": StudentSessionEnrollmentSerializer(new_enrollment).data,
        })

    @action(detail=False, methods=['post'])
    def bulk_session_enroll(self, request):
        """Enroll multiple students into a session at once."""
        session_id = request.data.get('session')
        student_ids = request.data.get('students', [])
        intake_id = request.data.get('intake')
        stream_id = request.data.get('stream')
        if not session_id or not student_ids or not intake_id:
            return Response({"error": "session, students, and intake are required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            session = ClassSession.objects.get(pk=session_id)
        except ClassSession.DoesNotExist:
            return Response({"error": "Session not found"}, status=status.HTTP_404_NOT_FOUND)
        from student_management.models import Student
        from student_settings.models import Intake, Stream
        try:
            intake = Intake.objects.get(pk=intake_id)
        except Intake.DoesNotExist:
            return Response({"error": "Intake not found"}, status=status.HTTP_404_NOT_FOUND)
        stream = None
        if stream_id:
            try:
                stream = Stream.objects.get(pk=stream_id)
            except Stream.DoesNotExist:
                pass
        created = 0
        skipped = 0
        for sid in student_ids:
            try:
                student = Student.objects.get(pk=sid)
            except Student.DoesNotExist:
                skipped += 1
                continue
            if StudentSessionEnrollment.objects.filter(student=student, session=session).exists():
                skipped += 1
                continue
            enrollment = StudentSessionEnrollment.objects.create(
                student=student, session=session, intake=intake,
                stream=stream, status='active', is_active=True,
            )
            self.trigger_auto_billing(enrollment)
            created += 1
        return Response({
            "message": f"Enrolled {created} students, skipped {skipped}",
            "created": created,
            "skipped": skipped,
        })
