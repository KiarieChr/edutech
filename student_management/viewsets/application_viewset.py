from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone
from accounts.models import User, Student
from student_management.models.application import Application
from student_management.models.admission import Admission
from student_management.models.class_session import StudentPlacement
from student_management.serializers import ApplicationSerializer

class ApplicationViewSet(viewsets.ModelViewSet):
    queryset = Application.objects.all()
    serializer_class = ApplicationSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['first_name', 'last_name', 'email', 'guardian_name', 'phone_number']
    ordering_fields = ['created_at', 'last_name']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def admit(self, request, pk=None):
        """
        Admit an applicant:
        1. Create User & Student account
        2. Create Admission record
        3. Create ClassSession (Reporting)
        4. Update Application status
        """
        application = self.get_object()
        
        if application.application_status == 'accepted':
            return Response({'error': 'Application already accepted'}, status=status.HTTP_400_BAD_REQUEST)
        
        # --- Admission Number Generation (Step 0) ---
        from accounts.utils import generate_student_id
        
        adm_no = request.data.get('admission_number')
        if not adm_no:
            adm_no = generate_student_id()
        
        # 1. Create User
        username = f"{application.first_name.lower()}.{application.last_name.lower()}"
        # Ensure unique username
        counter = 1
        original_username = username
        while User.objects.filter(username=username).exists():
            username = f"{original_username}{counter}"
            counter += 1
            
        # Password is the admission number as requested
        password = adm_no
        
        # Create user manually to skip signal logic that overwrites credentials
        user = User(
            username=username,
            email=application.email,
            first_name=application.first_name,
            last_name=application.last_name,
            gender=application.gender,
            is_student=True
        )
        user.set_password(password)
        user._skip_account_creation_signal = True # Flag for signal to skip
        user.save()
        
        # 2. Create Student   
        student = Student.objects.create(
            student=user,
            admission_number=adm_no,
            date_of_birth=application.date_of_birth,
            # Copy other demographics
        )

        # 2b. Create Parent Account
        # Username: P{admission_number}
        parent_username = f"P{adm_no}"
        parent_password = parent_username # Initial password
        
        # Check if parent user already exists with this username (unlikely for new adm no)
        # Check by email? If email exists, we might want to check if it's a parent.
        # BUT current Parent model is OneToOne with Student. So we MUST create a new User/Parent pair 
        # for this specific student if we want to follow the existing model strictness.
        
        parent_user = User(
            username=parent_username,
            email=application.email, # Guardian email
            first_name=application.guardian_name.split()[0] if application.guardian_name else "Parent",
            last_name=" ".join(application.guardian_name.split()[1:]) if application.guardian_name and len(application.guardian_name.split()) > 1 else "",
            is_parent=True
        )
        parent_user.set_password(parent_password)
        parent_user._skip_account_creation_signal = True
        parent_user.save()
        
        from accounts.models import Parent
        Parent.objects.create(
            user=parent_user,
            student=student,
            first_name=parent_user.first_name,
            last_name=parent_user.last_name,
            phone=application.phone_number,
            email=application.email
        )
        
        # 3. Create Admission Record
        Admission.objects.create(
            application=application,
            student=student,
            admission_number=adm_no,
            admission_date=timezone.now().date(),
            admitted_by=request.user,
            created_by=request.user
        )
        
        # 4. Create Class Session (Reporting/Admission)
        from student_settings.models import AcademicYear, Term, GradeStructure, Stream
        
        # Try to find active academic year
        academic_year = AcademicYear.objects.filter(status='active').first()
        if not academic_year:
             # Fallback to intake's year or error
             academic_year = application.intake.academic_year
             
        # Try to find active term
        term = Term.objects.filter(academic_year=academic_year, status='active').first()
        
        # Mapping application level to a grade?
        # Application now has applying_for_grade
        grade = application.applying_for_grade
        
        if not grade:
             # Clean up if we fail here? Ideally atomic transaction handles rollback.
             # raise serializer validation error if inside atomic
             # But here we are deep in logic.
             # Since atomic, raising exception rolls back.
             raise serializers.ValidationError('Application does not have a specific class/grade assigned.')

        stream_id = request.data.get('stream_id')
        stream = Stream.objects.get(id=stream_id) if stream_id else None
        
        StudentPlacement.objects.create(
            student=student,
            intake=application.intake,
            academic_year=academic_year,
            term=term, # Might fail if no active term
            curriculum=application.applying_for_curriculum,
            curriculum_level=application.applying_for_grade.curriculum_level, # Use grade's level
            grade=grade,
            stream=stream,
            session_type='admission',
            session_status='active',
            start_date=timezone.now().date(),
            created_by=request.user
        )
        
        # 5. Update Application
        application.application_status = 'accepted'
        application.save()
        
        # 6. Send Admission Email
        try:
            from student_management.utils.email_utils import send_admission_email
            send_admission_email(application, user, password, parent_user, parent_password)
        except Exception as e:
            # Don't fail the transaction just because email failed
            print(f"Failed to send admission email: {e}")
        
        return Response({
            'success': True,
            'student_id': student.id,
            'admission_number': adm_no,
            'username': username,
            'password': password 
        })

    @action(detail=False, methods=['get'])
    def dashboard_stats(self, request):
        """
        Aggregates statistics for the Admission Book Dashboard.
        """
        from datetime import datetime
        from django.db.models import Count, Q
        from django.db.models.functions import TruncMonth
        from student_management.models.admission import Admission
        from student_management.models.class_session import StudentPlacement
        from accounts.models import Student
        from rest_framework import serializers # Helper import just in case
        
        # 1. Metrics
        total_apps = self.get_queryset().count()
        admitted = self.get_queryset().filter(application_status='accepted').count()
        pending = self.get_queryset().filter(application_status__in=['pending', 'interview']).count()
        
        # For repeaters/transfers we need ClassSession or explicit flags
        repeaters = StudentPlacement.objects.filter(session_type='repeat', session_status='active').count()
        transfers = StudentPlacement.objects.filter(session_type='transfer', session_status='active').count()

        # 2. Charts - Trends (Last 6 Months)
        six_months_ago = timezone.now() - timezone.timedelta(days=180)
        
        apps_trend = self.get_queryset().filter(created_at__gte=six_months_ago)\
            .annotate(month=TruncMonth('created_at'))\
            .values('month')\
            .annotate(count=Count('id'))\
            .order_by('month')
            
        admissions_trend = Admission.objects.filter(admission_date__gte=six_months_ago)\
            .annotate(month=TruncMonth('admission_date'))\
            .values('month')\
            .annotate(count=Count('id'))\
            .order_by('month')

        # Merge for chart
        trend_data = {}
        for item in apps_trend:
            if not item['month']: continue
            month_str = item['month'].strftime('%b')
            if month_str not in trend_data: trend_data[month_str] = {'name': month_str, 'apps': 0, 'admitted': 0}
            trend_data[month_str]['apps'] = item['count']
            
        for item in admissions_trend:
            if not item['month']: continue
            month_str = item['month'].strftime('%b')
            if month_str not in trend_data: trend_data[month_str] = {'name': month_str, 'apps': 0, 'admitted': 0}
            trend_data[month_str]['admitted'] = item['count']
            
        chart_data = list(trend_data.values())

        # 3. Status Distribution
        status_counts = self.get_queryset().values('application_status').annotate(count=Count('id'))
        status_map = {
            'accepted': {'color': '#16a34a', 'label': 'Admitted'},
            'pending': {'color': '#ca8a04', 'label': 'Pending'},
            'interview': {'color': '#eab308', 'label': 'Interview'},
            'rejected': {'color': '#dc2626', 'label': 'Rejected'},
            'waitlist': {'color': '#9333ea', 'label': 'Waitlist'}
        }
        status_chart = []
        for item in status_counts:
            s = item['application_status']
            meta = status_map.get(s, {'color': '#6b7280', 'label': s.title()})
            status_chart.append({
                'name': meta['label'],
                'value': item['count'],
                'color': meta['color']
            })

        # 4. Class Distribution by Gender
        active_sessions = StudentPlacement.objects.filter(session_status='active').values('grade__name', 'student__student__gender').annotate(count=Count('id'))
        class_dist = {}
        for item in active_sessions:
            grade = item['grade__name']
            if not grade: continue
            gender = item['student__student__gender']
            count = item['count']
            
            if grade not in class_dist: class_dist[grade] = {'name': grade, 'boys': 0, 'girls': 0}
            if gender == 'M': class_dist[grade]['boys'] += count
            elif gender == 'F': class_dist[grade]['girls'] += count
            
        class_chart = list(class_dist.values())

        return Response({
            'metrics': {
                'total_apps': total_apps,
                'admitted': admitted,
                'pending': pending,
                'repeaters': repeaters,
                'transfers': transfers
            },
            'trends': chart_data,
            'status_distribution': status_chart,
            'class_distribution': class_chart
        })
