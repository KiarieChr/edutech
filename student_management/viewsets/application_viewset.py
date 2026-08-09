from rest_framework import viewsets, permissions, filters, status, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone
from accounts.models import User
from student_management.models import Student
from student_management.models.application import Application
from student_management.models.admission import Admission
from student_management.models.application_fee import ApplicationFeePayment
from student_management.models.interview import InterviewSchedule
from student_management.models.reporting import ReportingRecord
from student_settings.models import Enrollment
from student_management.serializers import ApplicationSerializer
from student_management.serializers.workflow import (
    RecordFeePaymentSerializer, WaiveFeeSerializer,
    ApplicationFeePaymentSerializer,
    ScheduleInterviewSerializer, RecordInterviewOutcomeSerializer,
    InterviewScheduleSerializer,
    ScheduleReportingSerializer, RecordReportingSerializer,
    ReportingRecordSerializer,
)


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

        # ── Workflow Gate ─────────────────────────────────────────────────────
        # Validate every required workflow stage is cleared before admitting.
        from student_settings.models import AdmissionWorkflowConfig
        workflow = AdmissionWorkflowConfig.get_instance()

        if workflow.require_application_fee:
            fee = getattr(application, 'fee_payment', None)
            if not fee or not fee.is_cleared:
                return Response(
                    {'error': 'Application fee must be paid or waived before admission.',
                     'stage': 'fee_payment'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if workflow.require_interview:
            interview = getattr(application, 'interview', None)
            if not interview or not interview.is_passed:
                return Response(
                    {'error': 'Interview must be completed and passed before admission.',
                     'stage': 'interview'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if workflow.require_reporting:
            reporting = getattr(application, 'reporting_record', None)
            if not reporting or not reporting.is_cleared:
                return Response(
                    {'error': 'Student must have reported (with documents) before formal admission.',
                     'stage': 'reporting'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        # ─────────────────────────────────────────────────────────────────────

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

        # 2b. Create Parent Account (or reuse existing parent)
        from student_management.models import Parent
        existing_parent_user_id = request.data.get('existing_parent_user_id')

        if existing_parent_user_id:
            # Reuse an existing parent user account (e.g. sibling scenario)
            try:
                parent_user = User.objects.get(id=existing_parent_user_id, is_parent=True)
            except User.DoesNotExist:
                raise serializers.ValidationError('Specified parent user account not found.')

            Parent.objects.create(
                user=parent_user,
                student=student,
                first_name=parent_user.first_name,
                last_name=parent_user.last_name,
                phone=application.phone_number,
                email=application.email,
                relation_ship=application.guardian_relationship or '',
            )
            parent_username = parent_user.username
            parent_password = None  # Existing account, no new password
        else:
            # Create a new parent user account
            parent_username = f"P{adm_no}"
            parent_password = parent_username  # Initial password

            parent_user = User(
                username=parent_username,
                email=application.email,  # Guardian email
                first_name=application.guardian_name.split()[0] if application.guardian_name else "Parent",
                last_name=" ".join(application.guardian_name.split()[1:]) if application.guardian_name and len(application.guardian_name.split()) > 1 else "",
                is_parent=True
            )
            parent_user.set_password(parent_password)
            parent_user._skip_account_creation_signal = True
            parent_user.save()

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
            campus=application.campus,
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
        
        Enrollment.objects.create(
            student=student,
            intake=application.intake,
            academic_year=academic_year,
            term=term,
            curriculum=application.applying_for_curriculum,
            curriculum_level=getattr(application.applying_for_grade, 'curriculum_level', None),
            grade=grade,
            stream=stream,
            campus=application.campus,
            enrollment_type='new_admission',
            status='active',
            is_active=True,
            enrollment_date=timezone.now().date(),
            created_by=request.user,
            updated_by=request.user
        )
        
        # Auto-enroll student into active academics session
        from fees.services import ensure_session_enrollment
        try:
            ensure_session_enrollment(
                student_id=student.id,
                grade=grade,
                term=term,
                year=academic_year,
                curriculum=application.applying_for_curriculum
            )
        except Exception as e:
            # Prevent failure of admissions process if academic session sync encounters a minor issue
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Admissions Sync Warning: Failed to auto-enroll student {student.id} in ClassSession: {e}")
        
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
        
        response_data = {
            'success': True,
            'student_id': student.id,
            'admission_number': adm_no,
            'username': username,
            'password': password,
            'parent_username': parent_username,
            'existing_parent': existing_parent_user_id is not None,
        }
        if parent_password:
            response_data['parent_password'] = parent_password

        return Response(response_data)

    @action(detail=False, methods=['get'])
    def dashboard_stats(self, request):
        """
        Aggregates statistics for the Admission Book Dashboard.
        Supports query parameters: campus_id, intake_id, date_start, date_end.
        """
        from datetime import datetime
        from django.db.models import Count, Q, Sum
        from django.db.models.functions import TruncMonth
        from student_management.models.admission import Admission
        from student_settings.models import Enrollment, Intake, Stream
        from student_management.models import Student
        from rest_framework import serializers # Helper import just in case
        
        # Parse query params
        campus_id = request.query_params.get('campus_id')
        intake_id = request.query_params.get('intake_id')
        date_start = request.query_params.get('date_start')
        date_end = request.query_params.get('date_end')
        
        # Base querysets
        apps_qs = self.get_queryset()
        admission_qs = Admission.objects.all()
        enrollment_qs = Enrollment.objects.all()
        
        # Apply filters
        if campus_id:
            apps_qs = apps_qs.filter(campus_id=campus_id)
            admission_qs = admission_qs.filter(campus_id=campus_id)
            enrollment_qs = enrollment_qs.filter(campus_id=campus_id)
            
        if intake_id:
            apps_qs = apps_qs.filter(intake_id=intake_id)
            admission_qs = admission_qs.filter(application__intake_id=intake_id)
            enrollment_qs = enrollment_qs.filter(intake_id=intake_id)
            
        if date_start:
            apps_qs = apps_qs.filter(created_at__date__gte=date_start)
            admission_qs = admission_qs.filter(admission_date__gte=date_start)
            enrollment_qs = enrollment_qs.filter(enrollment_date__gte=date_start)
            
        if date_end:
            apps_qs = apps_qs.filter(created_at__date__lte=date_end)
            admission_qs = admission_qs.filter(admission_date__lte=date_end)
            enrollment_qs = enrollment_qs.filter(enrollment_date__lte=date_end)
        
        # 1. Metrics
        total_apps = apps_qs.count()
        admitted = apps_qs.filter(application_status='accepted').count()
        pending = apps_qs.filter(application_status__in=['pending', 'interview']).count()
        
        # For repeaters/transfers we need Enrollment
        repeaters = enrollment_qs.filter(enrollment_type='repeat', status='active', is_active=True).count()
        transfers = enrollment_qs.filter(enrollment_type='transfer_in', status='active', is_active=True).count()

        # Target Capacity calculation
        target_capacity = 100
        if intake_id:
            try:
                intake = Intake.objects.get(id=intake_id)
                if intake.entry_grade:
                    capacity_sum = Stream.objects.filter(grade=intake.entry_grade, is_active=True).aggregate(total=Sum('capacity'))['total']
                    if capacity_sum:
                        target_capacity = capacity_sum
            except Intake.DoesNotExist:
                pass
        else:
            capacity_sum = Stream.objects.filter(is_active=True).aggregate(total=Sum('capacity'))['total']
            if capacity_sum:
                target_capacity = capacity_sum

        # 2. Charts - Trends (Last 6 Months)
        six_months_ago = timezone.now() - timezone.timedelta(days=180)
        
        apps_trend = apps_qs.filter(created_at__gte=six_months_ago)\
            .annotate(month=TruncMonth('created_at'))\
            .values('month')\
            .annotate(count=Count('id'))\
            .order_by('month')
            
        admissions_trend = admission_qs.filter(admission_date__gte=six_months_ago)\
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
        status_counts = apps_qs.values('application_status').annotate(count=Count('id'))
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
        active_sessions = enrollment_qs.filter(status='active', is_active=True).values('grade__name', 'student__student__gender').annotate(count=Count('id'))
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
                'transfers': transfers,
                'target_capacity': target_capacity
            },
            'trends': chart_data,
            'status_distribution': status_chart,
            'class_distribution': class_chart
        })

    # ─────────────────────────────────────────────────────────────────────────
    # GET /api/student-management/applications/recent_activity/
    # Returns last 15 application events ordered by updated_at desc
    # ─────────────────────────────────────────────────────────────────────────
    @action(detail=False, methods=['get'], url_path='recent_activity')
    def recent_activity(self, request):
        from django.utils import timezone as tz

        limit = int(request.query_params.get('limit', 15))
        campus_id = request.query_params.get('campus_id')
        intake_id = request.query_params.get('intake_id')

        qs = self.get_queryset().select_related('campus', 'intake', 'applying_for_grade')
        if campus_id:
            qs = qs.filter(campus_id=campus_id)
        if intake_id:
            qs = qs.filter(intake_id=intake_id)

        recent = qs.order_by('-updated_at')[:limit]

        STATUS_LABELS = {
            'pending':   'Pending Review',
            'interview': 'Interview Scheduled',
            'accepted':  'Admitted',
            'rejected':  'Rejected',
            'waitlist':  'Waitlisted',
        }
        STATUS_COLORS = {
            'pending':   '#ca8a04',
            'interview': '#2563eb',
            'accepted':  '#16a34a',
            'rejected':  '#dc2626',
            'waitlist':  '#9333ea',
        }

        results = []
        for app in recent:
            results.append({
                'id': app.id,
                'name': f"{app.first_name} {app.last_name}",
                'status': app.application_status,
                'status_label': STATUS_LABELS.get(app.application_status, app.application_status.title()),
                'status_color': STATUS_COLORS.get(app.application_status, '#6b7280'),
                'grade': app.applying_for_grade.name if app.applying_for_grade else None,
                'intake': app.intake.name if app.intake else None,
                'campus': app.campus.name if app.campus else None,
                'updated_at': app.updated_at.isoformat(),
                'created_at': app.created_at.isoformat(),
            })

        return Response({'results': results, 'count': len(results)})

    # ─────────────────────────────────────────────────────────────────────────
    # GET /api/student-management/applications/campus_breakdown/
    # Returns per-campus application and admission counts
    # ─────────────────────────────────────────────────────────────────────────
    @action(detail=False, methods=['get'], url_path='campus_breakdown')
    def campus_breakdown(self, request):
        from django.db.models import Count
        from student_management.models.admission import Admission

        intake_id = request.query_params.get('intake_id')

        apps_qs = self.get_queryset().filter(campus__isnull=False)
        admissions_qs = Admission.objects.filter(campus__isnull=False)

        if intake_id:
            apps_qs = apps_qs.filter(intake_id=intake_id)
            admissions_qs = admissions_qs.filter(application__intake_id=intake_id)

        # Applications per campus
        apps_by_campus = (
            apps_qs
            .values('campus_id', 'campus__name')
            .annotate(total=Count('id'))
        )

        # Admitted per campus
        admitted_by_campus = (
            apps_qs
            .filter(application_status='accepted')
            .values('campus_id')
            .annotate(admitted=Count('id'))
        )
        admitted_map = {row['campus_id']: row['admitted'] for row in admitted_by_campus}

        # Pending per campus
        pending_by_campus = (
            apps_qs
            .filter(application_status__in=['pending', 'interview'])
            .values('campus_id')
            .annotate(pending=Count('id'))
        )
        pending_map = {row['campus_id']: row['pending'] for row in pending_by_campus}

        results = []
        for row in apps_by_campus:
            cid = row['campus_id']
            total = row['total']
            admitted = admitted_map.get(cid, 0)
            pending = pending_map.get(cid, 0)
            yield_pct = round((admitted / total * 100), 1) if total > 0 else 0
            results.append({
                'campus_id': cid,
                'campus': row['campus__name'],
                'total': total,
                'admitted': admitted,
                'pending': pending,
                'yield_pct': yield_pct,
            })

        results.sort(key=lambda x: -x['total'])
        return Response({'results': results})

    # ─────────────────────────────────────────────────────────────────────────
    # GET /api/student-management/applications/intake_deadlines/
    # Returns active intakes as "deadline" items with days-remaining
    # ─────────────────────────────────────────────────────────────────────────
    @action(detail=False, methods=['get'], url_path='intake_deadlines')
    def intake_deadlines(self, request):
        from django.utils import timezone as tz
        from student_settings.models import Intake

        today = tz.now().date()

        # All intakes that are open/active — ordered by start_date
        intakes = (
            Intake.objects
            .filter(is_deleted=False, status__in=['open'])
            .select_related('academic_year', 'entry_grade')
            .order_by('start_date')[:20]
        )

        results = []
        for intake in intakes:
            # Use start_date as the reference date; compute how many days from now
            days_delta = (intake.start_date - today).days
            urgency = (
                'overdue' if days_delta < 0 else
                'critical' if days_delta <= 7 else
                'warning' if days_delta <= 14 else
                'ok'
            )
            results.append({
                'id': intake.id,
                'name': intake.name,
                'code': intake.code,
                'start_date': intake.start_date.isoformat(),
                'status': intake.status,
                'is_active': intake.is_active,
                'academic_year': intake.academic_year.name if intake.academic_year else None,
                'entry_grade': intake.entry_grade.name if intake.entry_grade else None,
                'days_from_now': days_delta,
                'urgency': urgency,
            })

        return Response({'results': results})


    # ─────────────────────────────────────────────────────────────────────────
    # GET /api/student-management/applications/{id}/workflow_status/
    # ─────────────────────────────────────────────────────────────────────────
    @action(detail=True, methods=['get'], url_path='workflow_status')
    def workflow_status(self, request, pk=None):
        """Return the current state of each workflow stage for an application."""
        from student_settings.models import AdmissionWorkflowConfig
        application = self.get_object()
        workflow = AdmissionWorkflowConfig.get_instance()

        fee = getattr(application, 'fee_payment', None)
        interview = getattr(application, 'interview', None)
        reporting = getattr(application, 'reporting_record', None)

        stages = []

        if workflow.require_enquiry:
            enquiry = getattr(application, 'enquiry_source', None)
            stages.append({
                'key': 'enquiry',
                'label': 'Enquiry',
                'required': True,
                'cleared': enquiry is not None,
                'data': {'enquiry_id': enquiry.id if enquiry else None},
            })

        stages.append({
            'key': 'application',
            'label': 'Application',
            'required': True,
            'cleared': True,
            'data': {'status': application.application_status},
        })

        if workflow.require_application_fee:
            stages.append({
                'key': 'fee_payment',
                'label': workflow.application_fee_label,
                'required': True,
                'cleared': bool(fee and fee.is_cleared),
                'data': ApplicationFeePaymentSerializer(fee).data if fee else None,
            })

        if workflow.require_interview:
            stages.append({
                'key': 'interview',
                'label': workflow.interview_label,
                'required': True,
                'cleared': bool(interview and interview.is_passed),
                'data': InterviewScheduleSerializer(interview).data if interview else None,
            })

        if workflow.require_reporting:
            stages.append({
                'key': 'reporting',
                'label': workflow.reporting_label,
                'required': True,
                'cleared': bool(reporting and reporting.is_cleared),
                'data': ReportingRecordSerializer(reporting).data if reporting else None,
            })

        stages.append({
            'key': 'admission',
            'label': 'Admission',
            'required': True,
            'cleared': application.application_status == 'accepted',
            'data': None,
        })

        all_cleared = all(s['cleared'] for s in stages if s['required'])

        return Response({
            'application_id': application.id,
            'applicant': f"{application.first_name} {application.last_name}",
            'current_status': application.application_status,
            'ready_to_admit': all_cleared,
            'stages': stages,
        })


    # ─────────────────────────────────────────────────────────────────────────
    # POST /api/student-management/applications/{id}/record_fee_payment/
    # ─────────────────────────────────────────────────────────────────────────
    @action(detail=True, methods=['post'], url_path='record_fee_payment')
    def record_fee_payment(self, request, pk=None):
        """Mark the application fee as paid."""
        application = self.get_object()
        fee, created = ApplicationFeePayment.objects.get_or_create(
            application=application,
            defaults={'amount': 0, 'currency': 'KES'}
        )
        if fee.status == 'paid':
            return Response({'error': 'Fee has already been marked as paid.'}, status=status.HTTP_400_BAD_REQUEST)

        ser = RecordFeePaymentSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        from student_settings.models import AdmissionWorkflowConfig
        workflow = AdmissionWorkflowConfig.get_instance()
        if not fee.amount or fee.amount == 0:
            fee.amount = workflow.application_fee_amount or 0
            fee.currency = workflow.application_fee_currency

        fee.status = 'paid'
        fee.payment_method = d['payment_method']
        fee.payment_date = d['payment_date']
        fee.payment_reference = d.get('payment_reference', '')
        fee.receipt_number = d.get('receipt_number', '')
        fee.notes = d.get('notes', '')
        fee.recorded_by = request.user
        fee.updated_by = request.user
        fee.save()

        if application.application_status == 'fee_pending':
            application.application_status = 'fee_paid'
            application.updated_by = request.user
            application.save()

        return Response({'success': True, 'fee': ApplicationFeePaymentSerializer(fee).data})


    # ─────────────────────────────────────────────────────────────────────────
    # POST /api/student-management/applications/{id}/waive_fee/
    # ─────────────────────────────────────────────────────────────────────────
    @action(detail=True, methods=['post'], url_path='waive_fee')
    def waive_fee(self, request, pk=None):
        """Waive the application fee with a mandatory reason."""
        application = self.get_object()
        ser = WaiveFeeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        from student_settings.models import AdmissionWorkflowConfig
        workflow = AdmissionWorkflowConfig.get_instance()
        fee, _ = ApplicationFeePayment.objects.get_or_create(
            application=application,
            defaults={'amount': workflow.application_fee_amount or 0, 'currency': workflow.application_fee_currency}
        )
        if fee.status in ('paid', 'waived'):
            return Response({'error': f'Fee is already {fee.status}.'}, status=status.HTTP_400_BAD_REQUEST)

        fee.status = 'waived'
        fee.waiver_reason = ser.validated_data['waiver_reason']
        fee.recorded_by = request.user
        fee.updated_by = request.user
        fee.save()

        if application.application_status == 'fee_pending':
            application.application_status = 'fee_paid'
            application.updated_by = request.user
            application.save()

        return Response({'success': True, 'fee': ApplicationFeePaymentSerializer(fee).data})


    # ─────────────────────────────────────────────────────────────────────────
    # POST /api/student-management/applications/{id}/schedule_interview/
    # ─────────────────────────────────────────────────────────────────────────
    @action(detail=True, methods=['post'], url_path='schedule_interview')
    def schedule_interview(self, request, pk=None):
        """Schedule an interview for an applicant."""
        application = self.get_object()
        if hasattr(application, 'interview') and application.interview.status == 'scheduled':
            return Response(
                {'error': 'An interview is already scheduled. Reschedule or cancel it first.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        ser = ScheduleInterviewSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        interviewer = None
        if d.get('interviewer'):
            try:
                from accounts.models import User as UserModel
                interviewer = UserModel.objects.get(pk=d['interviewer'])
            except UserModel.DoesNotExist:
                return Response({'error': 'Interviewer user not found.'}, status=status.HTTP_400_BAD_REQUEST)

        interview, created = InterviewSchedule.objects.update_or_create(
            application=application,
            defaults={
                'scheduled_date': d['scheduled_date'],
                'venue': d.get('venue', ''),
                'duration_minutes': d.get('duration_minutes', 30),
                'interviewer': interviewer,
                'status': 'scheduled',
                'outcome': 'pending',
                'updated_by': request.user,
            }
        )
        if created:
            interview.created_by = request.user
            interview.save(update_fields=['created_by'])

        panel_ids = d.get('panel_members', [])
        if panel_ids:
            from accounts.models import User as UserModel
            interview.panel_members.set(UserModel.objects.filter(pk__in=panel_ids))

        application.application_status = 'interview'
        application.updated_by = request.user
        application.save()

        return Response(
            {'success': True, 'interview': InterviewScheduleSerializer(interview).data},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


    # ─────────────────────────────────────────────────────────────────────────
    # POST /api/student-management/applications/{id}/record_interview_outcome/
    # ─────────────────────────────────────────────────────────────────────────
    @action(detail=True, methods=['post'], url_path='record_interview_outcome')
    def record_interview_outcome(self, request, pk=None):
        """Record the result of an interview."""
        application = self.get_object()
        if not hasattr(application, 'interview'):
            return Response(
                {'error': 'No interview has been scheduled for this application.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        ser = RecordInterviewOutcomeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        interview = application.interview
        interview.outcome = d['outcome']
        interview.status = d.get('status', 'completed')
        interview.score = d.get('score')
        interview.max_score = d.get('max_score')
        interview.notes = d.get('notes', '')
        interview.feedback_to_applicant = d.get('feedback_to_applicant', '')
        interview.completed_at = timezone.now()
        interview.completed_by = request.user
        interview.updated_by = request.user
        interview.save()

        application.application_status = 'interviewed'
        application.updated_by = request.user
        application.save()

        return Response({
            'success': True,
            'outcome': d['outcome'],
            'interview': InterviewScheduleSerializer(interview).data,
        })


    # ─────────────────────────────────────────────────────────────────────────
    # POST /api/student-management/applications/{id}/schedule_reporting/
    # ─────────────────────────────────────────────────────────────────────────
    @action(detail=True, methods=['post'], url_path='schedule_reporting')
    def schedule_reporting(self, request, pk=None):
        """Set the expected reporting date for an applicant."""
        application = self.get_object()
        ser = ScheduleReportingSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        reporting, created = ReportingRecord.objects.update_or_create(
            application=application,
            defaults={
                'expected_date': d['expected_date'],
                'notes': d.get('notes', ''),
                'status': 'expected',
                'updated_by': request.user,
            }
        )
        if created:
            reporting.created_by = request.user
            reporting.save(update_fields=['created_by'])

        application.application_status = 'reporting'
        application.updated_by = request.user
        application.save()

        return Response(
            {'success': True, 'reporting': ReportingRecordSerializer(reporting).data},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


    # ─────────────────────────────────────────────────────────────────────────
    # POST /api/student-management/applications/{id}/record_reporting/
    # ─────────────────────────────────────────────────────────────────────────
    @action(detail=True, methods=['post'], url_path='record_reporting')
    def record_reporting(self, request, pk=None):
        """Mark a student as having reported (with documents)."""
        application = self.get_object()
        if not hasattr(application, 'reporting_record'):
            return Response(
                {'error': 'No reporting date has been scheduled. Call schedule_reporting first.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        ser = RecordReportingSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        reporting = application.reporting_record
        reporting.status = d.get('status', 'reported')
        reporting.actual_date = d['actual_date']
        reporting.documents_received = d.get('documents_received', False)
        reporting.document_status = d.get('document_status', {})
        reporting.missing_documents = d.get('missing_documents', '')
        reporting.notes = d.get('notes', '')
        reporting.received_by = request.user
        reporting.updated_by = request.user
        reporting.save()

        return Response({'success': True, 'reporting': ReportingRecordSerializer(reporting).data})
