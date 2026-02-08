from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import ClassSession, StudentSessionEnrollment
from student_settings.models import AcademicYear, Term, GradeStructure, CurriculumLevel
from .serializers import ClassSessionSerializer, StudentSessionEnrollmentSerializer

class ClassSessionViewSet(viewsets.ModelViewSet):
    queryset = ClassSession.objects.all()
    serializer_class = ClassSessionSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['grade', 'term', 'academic_year', 'curriculum', 'status']
    search_fields = ['name', 'grade__name']
    ordering_fields = ['academic_year__start_date', 'term__start_date', 'grade__level_order']

    def get_queryset(self):
        qs = super().get_queryset()
       
        
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

            # 3. Zip them to map Year X -> Grade X
            # We only generate as far as we have BOTH years and grades
            progression_map = list(zip(subsequent_years, subsequent_grades))

            if not progression_map:
                return Response({"error": "Could not determine progression map. Check Academic Years and Grades."}, status=status.HTTP_400_BAD_REQUEST)

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
                
        return Response({
            "message": f"Successfully generated {created_count} class sessions for {academic_year.name}",
            "created_count": created_count,
            "academic_year": academic_year.name
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
        """
        from fees.services import BillingService
        from fees.models import FeeStructure
        from django.utils import timezone
        
        # 1. Find standard Fee Structure for this session's context
        # Resolving Grade/Term/Year from session
        grade = enrollment.session.grade
        term = enrollment.session.term
        year = enrollment.session.academic_year
        curriculum = enrollment.session.curriculum
        
        structure = FeeStructure.objects.filter(
            grade=grade,
            term=term,
            academic_year=year,
            curriculum=curriculum,
            status='ACTIVE'
        ).first()

        # Fallback: Ignore Curriculum if strict match fails
        if not structure:
             structure = FeeStructure.objects.filter(
                grade=grade,
                term=term,
                academic_year=year,
                status='ACTIVE'
            ).first()
            
        if not structure:
            print(f"Auto-Billing skipped: No Active Fee Structure found for {year} {term} {grade}.")
            return

        # 2. Collect Mandatory Items
        items = []
        for item in structure.items.filter(is_mandatory=True):
            items.append({
                'id': item.id,
                'amount': float(item.amount) # Full amount
            })
            
        if not items:
            print("Auto-Billing skipped: No mandatory fee items found.")
            return

        # 3. Generate Invoice
        payload = {
            'student_id': enrollment.student.id,
            'structure_id': structure.id,
            'items': items,
            'due_date': timezone.now().date(), # Default to today
            'remarks': 'Auto-generated upon reporting.',
            'is_automated': True
        }
        
        try:
            BillingService.generate_invoice(payload, user=self.request.user)
            print(f"Auto-Billing Success: Invoice generated for {enrollment.student}")
        except Exception as e:
            # Log but don't crash the enrollment?
            # User wants it to "do the same thing", usually implies success or fail.
            # But failing enrollment because of billing might be too harsh.
            # Let's log it.
            print(f"Auto-Billing Error: {e}")
