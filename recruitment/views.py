from django.shortcuts import get_object_or_404
from django.db.models import Q, Count, Avg, F, ExpressionWrapper, DurationField
from django.utils import timezone
from django.http import FileResponse, HttpResponse
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings

from rest_framework import viewsets, status, generics, filters
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser, BasePermission, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination

from .models import *
from .serializers import *
from workforce.models import Employee


# ============================================================================
# PERMISSION CLASSES
# ============================================================================

class IsHRManager(BasePermission):
    def has_permission(self, request, view):
        if request.user.is_superuser:
            return True
        return request.user.is_authenticated and hasattr(request.user, 'employee_profile') and \
               request.user.employee_profile.department.name == "Human Resources"


class IsHiringManager(BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated or not hasattr(request.user, 'employee_profile'):
            return False
        
        employee = request.user.employee_profile
        # Check if user is hiring manager for any job opening
        return JobOpening.objects.filter(hiring_manager=employee).exists()


class CanViewApplication(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser or request.user.is_staff:
            return True
        
        if not hasattr(request.user, 'employee_profile'):
            return False
        
        employee = request.user.employee_profile
        
        # HR managers can view all applications
        if employee.department.name == "Human Resources":
            return True
        
        # Hiring managers can view applications for their job openings
        if hasattr(obj, 'job_opening'):
            return obj.job_opening.hiring_manager == employee
        
        # Interviewers can view applications they're interviewing
        if hasattr(obj, 'interviews'):
            return obj.interviews.filter(interviewers=employee).exists()
        
        return False


# ============================================================================
# PAGINATION
# ============================================================================

class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


# ============================================================================
# VIEWSETS
# ============================================================================

class RecruitmentSourceViewSet(viewsets.ModelViewSet):
    queryset = RecruitmentSource.objects.filter(is_active=True)
    serializer_class = RecruitmentSourceSerializer
    permission_classes = [IsAuthenticated, IsHRManager]
    pagination_class = StandardPagination


class JobOpeningViewSet(viewsets.ModelViewSet):
    queryset = JobOpening.objects.all()
    permission_classes = [AllowAny]
    pagination_class = StandardPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'description', 'reference_number', 'department__name']
    ordering_fields = ['opening_date', 'closing_date', 'created_at']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return JobOpeningListSerializer
        elif self.action == 'create':
            return JobOpeningCreateSerializer
        return JobOpeningDetailSerializer
    
    # def get_permissions(self):
    #     if self.action in ['create', 'update', 'partial_update', 'destroy']:
    #         permission_classes = [IsAuthenticated, IsHRManager]
    #     else:
    #         permission_classes = [IsAuthenticated]
    #     return [permission() for permission in permission_classes]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Apply filters
        status_param = self.request.query_params.get('status', None)
        department_param = self.request.query_params.get('department', None)
        campus_param = self.request.query_params.get('campus', None)
        hiring_manager_param = self.request.query_params.get('hiring_manager', None)
        
        if status_param:
            queryset = queryset.filter(status=status_param)
        
        if department_param:
            queryset = queryset.filter(department_id=department_param)
        
        if campus_param:
            queryset = queryset.filter(campus_id=campus_param)
        
        if hiring_manager_param:
            queryset = queryset.filter(hiring_manager_id=hiring_manager_param)
        
        # Non-HR users can only see published job openings
        try:
            is_hr = (
                hasattr(self.request.user, 'employee_profile') and
                self.request.user.employee_profile is not None and
                self.request.user.employee_profile.department.name == "Human Resources"
            )
        except AttributeError:
            is_hr = False

        if not self.request.user.is_staff and not is_hr:
            queryset = queryset.filter(status=JobOpening.Status.PUBLISHED)

        return queryset
    
    @action(detail=True, methods=['post'], permission_classes=[IsHRManager])
    def publish(self, request, pk=None):
        job_opening = self.get_object()
        
        if job_opening.status != JobOpening.Status.APPROVED:
            return Response(
                {'error': 'Job opening must be approved before publishing'},
                status=status.HTTP_400_BAD_REQUEST
            )

        job_opening.status = JobOpening.Status.PUBLISHED
        try:
            job_opening.publish_date = timezone.now().date()
        except AttributeError:
            pass
        try:
            job_opening.published_by = request.user.employee_profile
        except AttributeError:
            pass
        job_opening.save()
        return Response({'status': 'published', 'message': 'Job opening published successfully'})

    def perform_create(self, serializer):
        job_opening = serializer.save()
        
        # Create standard interview rounds
        standard_rounds = [
            {'sequence': 1, 'round_name': 'Initial Screening', 'round_type': 'telephonic', 'duration_minutes': 30},
            {'sequence': 2, 'round_name': 'Technical Interview', 'round_type': 'technical', 'duration_minutes': 60},
            {'sequence': 3, 'round_name': 'Managerial Round', 'round_type': 'video', 'duration_minutes': 45},
            {'sequence': 4, 'round_name': 'HR Discussion', 'round_type': 'hr', 'duration_minutes': 30}
        ]
        
        for round_data in standard_rounds:
            InterviewRound.objects.create(
                job_opening=job_opening,
                **round_data
            )
        
        job_opening.status = JobOpening.Status.PUBLISHED
        job_opening.publish_date = timezone.now().date()
        job_opening.published_by = request.user
        job_opening.save()
        
        return Response({'status': 'published'})
    
    @action(detail=True, methods=['post'], permission_classes=[IsHRManager])
    def close(self, request, pk=None):
        job_opening = self.get_object()
        job_opening.status = JobOpening.Status.CLOSED
        job_opening.save()
        
        return Response({'status': 'closed'})
    
    @action(detail=True, methods=['get'])
    def statistics(self, request, pk=None):
        job_opening = self.get_object()
        
        stats = {
            'total_applications': job_opening.applications.count(),
            'applications_by_status': dict(
                job_opening.applications.values_list('application_status')
                .annotate(count=Count('id'))
                .values_list('application_status', 'count')
            ),
            'applications_by_source': dict(
                job_opening.applications.values_list('application_source')
                .annotate(count=Count('id'))
                .values_list('application_source', 'count')
            ),
            'average_experience': job_opening.applications.aggregate(
                avg=Avg('total_experience_years')
            )['avg'] or 0,
        }
        
        return Response(stats)


class JobApplicationViewSet(viewsets.ModelViewSet):
    queryset = JobApplication.objects.all()
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    pagination_class = StandardPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        'first_name', 'last_name', 'email', 'phone',
        'job_opening__title', 'current_employer'
    ]
    ordering_fields = ['application_date', 'total_experience_years']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return JobApplicationListSerializer
        elif self.action == 'create':
            return JobApplicationCreateSerializer
        return JobApplicationDetailSerializer
    
    def get_permissions(self):
        if self.action == 'create':
            permission_classes = []  # Allow anyone to apply
        elif self.action in ['update', 'partial_update', 'destroy']:
            permission_classes = [IsAuthenticated, IsHRManager]
        else:
            permission_classes = [IsAuthenticated, CanViewApplication]
        return [permission() for permission in permission_classes]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Apply filters
        job_opening_param = self.request.query_params.get('job_opening', None)
        status_param = self.request.query_params.get('status', None)
        source_param = self.request.query_params.get('source', None)
        min_experience = self.request.query_params.get('min_experience', None)
        max_experience = self.request.query_params.get('max_experience', None)
        
        if job_opening_param:
            queryset = queryset.filter(job_opening_id=job_opening_param)
        
        if status_param:
            statuses = status_param.split(',')
            queryset = queryset.filter(application_status__in=statuses)
        
        if source_param:
            queryset = queryset.filter(application_source=source_param)
        
        if min_experience:
            queryset = queryset.filter(total_experience_years__gte=min_experience)
        
        if max_experience:
            queryset = queryset.filter(total_experience_years__lte=max_experience)
        
        # Non-HR users can only see applications they're involved with
        if not self.request.user.is_staff:
            employee = self.request.user.employee_profile
            
            # HR managers can see all
            if employee.department.name != "Human Resources":
                # Hiring managers can see applications for their job openings
                job_openings = JobOpening.objects.filter(hiring_manager=employee)
                queryset = queryset.filter(job_opening__in=job_openings)
        
        return queryset
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # ── Deadline enforcement (server-side, cannot be bypassed) ──
        job_opening_id = serializer.validated_data.get('job_opening')
        if job_opening_id:
            try:
                job = JobOpening.objects.get(pk=job_opening_id.pk
                                              if hasattr(job_opening_id, 'pk')
                                              else job_opening_id)
                if job.closing_date and job.closing_date < timezone.now().date():
                    return Response(
                        {'error': 'Application deadline has expired.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except JobOpening.DoesNotExist:
                return Response(
                    {'error': 'Job opening not found.'},
                    status=status.HTTP_404_NOT_FOUND,
                )

        application = serializer.save()
        self._send_acknowledgment_email(application)

        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers
        )
    
    def _send_acknowledgment_email(self, application):
        subject = f"Application Received - {application.job_opening.title}"
        message = f"""
        Dear {application.first_name} {application.last_name},
        
        Thank you for applying for the position of {application.job_opening.title}.
        We have received your application and will review it shortly.
        
        Application Reference: {application.id}
        Position: {application.job_opening.title}
        Application Date: {application.application_date.strftime('%Y-%m-%d %H:%M')}
        
        We will contact you if your qualifications match our requirements.
        
        Best regards,
        HR Department
        """
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[application.email],
            fail_silently=True
        )
    
    @action(detail=True, methods=['post'], permission_classes=[IsHRManager])
    def change_status(self, request, pk=None):
        application = self.get_object()
        new_status = request.data.get('status')
        notes = request.data.get('notes', '')
        
        if not new_status:
            return Response(
                {'error': 'Status is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate status transition
        valid_transitions = {
            JobApplication.ApplicationStatus.SUBMITTED: [
                JobApplication.ApplicationStatus.SCREENING,
                JobApplication.ApplicationStatus.SHORTLISTED,
                JobApplication.ApplicationStatus.REJECTED
            ],
            JobApplication.ApplicationStatus.SCREENING: [
                JobApplication.ApplicationStatus.SHORTLISTED,
                JobApplication.ApplicationStatus.INTERVIEW,
                JobApplication.ApplicationStatus.REJECTED
            ],
            JobApplication.ApplicationStatus.SHORTLISTED: [
                JobApplication.ApplicationStatus.INTERVIEW,
                JobApplication.ApplicationStatus.REJECTED
            ],
            JobApplication.ApplicationStatus.INTERVIEW: [
                JobApplication.ApplicationStatus.BACKGROUND_CHECK,
                JobApplication.ApplicationStatus.REJECTED
            ],
            JobApplication.ApplicationStatus.BACKGROUND_CHECK: [
                JobApplication.ApplicationStatus.OFFERED,
                JobApplication.ApplicationStatus.REJECTED
            ],
            JobApplication.ApplicationStatus.OFFERED: [
                JobApplication.ApplicationStatus.HIRED,
                JobApplication.ApplicationStatus.REJECTED,
                JobApplication.ApplicationStatus.WITHDRAWN
            ],
        }
        
        current_status = application.application_status
        if new_status not in valid_transitions.get(current_status, []):
            return Response(
                {'error': f'Invalid status transition from {current_status} to {new_status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        application.application_status = new_status
        application.notes = notes
        application.save()
        
        # Send status update email
        self._send_status_update_email(application)
        
        return Response({'status': 'updated'})
    
    def _send_status_update_email(self, application):
        status_display = application.get_application_status_display()
        subject = f"Application Update - {application.job_opening.title}"
        
        message = f"""
        Dear {application.first_name} {application.last_name},
        
        Your application status for {application.job_opening.title} has been updated.
        
        New Status: {status_display}
        
        {"We will contact you soon for next steps." if application.application_status != JobApplication.ApplicationStatus.REJECTED else "Thank you for your interest in our organization."}
        
        Best regards,
        HR Department
        """
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[application.email],
            fail_silently=True
        )
    
    @action(detail=True, methods=['get'])
    def resume(self, request, pk=None):
        application = self.get_object()
        
        if not application.resume:
            return Response(
                {'error': 'Resume not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        return FileResponse(
            application.resume.open(),
            content_type='application/pdf',
            as_attachment=False,
            filename=f"Resume_{application.full_name}.pdf"
        )

    @action(detail=True, methods=['get'])
    def workflow(self, request, pk=None):
        """Get full workflow bundle"""
        application = self.get_object()
        serializer = CandidateFullWorkflowSerializer(application)
        return Response(serializer.data)


class InterviewRoundViewSet(viewsets.ModelViewSet):
    queryset = InterviewRound.objects.all()
    serializer_class = InterviewRoundSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        job_opening = self.request.query_params.get('job_opening', None)
        
        if job_opening:
            queryset = queryset.filter(job_opening_id=job_opening)
        
        return queryset


class InterviewScheduleViewSet(viewsets.ModelViewSet):
    queryset = InterviewSchedule.objects.all()
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    ordering_fields = ['interview_date', 'start_time']
    
    def get_serializer_class(self):
        if self.action == 'create':
            return InterviewScheduleCreateSerializer
        return InterviewScheduleListSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [IsAuthenticated, IsHRManager]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Apply filters
        application_param = self.request.query_params.get('application', None)
        status_param = self.request.query_params.get('status', None)
        interviewer_param = self.request.query_params.get('interviewer', None)
        date_from = self.request.query_params.get('date_from', None)
        date_to = self.request.query_params.get('date_to', None)
        
        if application_param:
            queryset = queryset.filter(application_id=application_param)
        
        if status_param:
            queryset = queryset.filter(status=status_param)
        
        if interviewer_param:
            queryset = queryset.filter(interviewers__id=interviewer_param)
        
        if date_from:
            queryset = queryset.filter(interview_date__gte=date_from)
        
        if date_to:
            queryset = queryset.filter(interview_date__lte=date_to)
        
        # Non-HR users can only see interviews they're involved in
        if not self.request.user.is_staff:
            employee = self.request.user.employee_profile
            if employee.department.name != "Human Resources":
                queryset = queryset.filter(interviewers=employee)
        
        return queryset
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def send_invitation(self, request, pk=None):
        interview = self.get_object()
        
        # Send invitation emails
        self._send_interview_invitations(interview)
        
        interview.candidate_notified = True
        interview.interviewers_notified = True
        interview.notification_sent_date = timezone.now()
        interview.save()
        
        return Response({'status': 'invitations sent'})
    
    def _send_interview_invitations(self, interview):
        # Send to candidate
        candidate_email = interview.application.email
        candidate_subject = f"Interview Invitation - {interview.application.job_opening.title}"
        
        candidate_message = f"""
        Dear {interview.application.first_name} {interview.application.last_name},
        
        You are invited for an interview for the position of {interview.application.job_opening.title}.
        
        Interview Details:
        - Date: {interview.interview_date}
        - Time: {interview.start_time} to {interview.end_time}
        - Mode: {interview.get_interview_mode_display()}
        - Location/Link: {interview.location}
        - Round: {interview.interview_round.round_name}
        
        Please confirm your availability.
        
        Best regards,
        HR Department
        """
        
        send_mail(
            subject=candidate_subject,
            message=candidate_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[candidate_email],
            fail_silently=True
        )
        
        # Send to interviewers
        for interviewer in interview.interviewers.all():
            interviewer_subject = f"Interview Scheduled - {interview.application.job_opening.title}"
            
            interviewer_message = f"""
            Dear {interviewer.get_full_name()},
            
            You are scheduled to interview a candidate.
            
            Candidate: {interview.application.full_name}
            Position: {interview.application.job_opening.title}
            Date: {interview.interview_date}
            Time: {interview.start_time} to {interview.end_time}
            Mode: {interview.get_interview_mode_display()}
            Location/Link: {interview.location}
            Round: {interview.interview_round.round_name}
            
            Please review the candidate's application before the interview.
            
            Regards,
            HR Department
            """
            
            send_mail(
                subject=interviewer_subject,
                message=interviewer_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[interviewer.email],
                fail_silently=True
            )
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def update_status(self, request, pk=None):
        interview = self.get_object()
        new_status = request.data.get('status')
        notes = request.data.get('notes', '')
        
        if not new_status:
            return Response(
                {'error': 'Status is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        interview.status = new_status
        interview.notes = notes
        interview.save()
        
        return Response({'status': 'updated'})


class InterviewEvaluationViewSet(viewsets.ModelViewSet):
    queryset = InterviewEvaluation.objects.all()
    serializer_class = InterviewEvaluationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Apply filters
        interview_param = self.request.query_params.get('interview', None)
        interviewer_param = self.request.query_params.get('interviewer', None)
        
        if interview_param:
            queryset = queryset.filter(interview_id=interview_param)
        
        if interviewer_param:
            queryset = queryset.filter(interviewer_id=interviewer_param)
        
        # Users can only see their own evaluations unless they're HR
        if not self.request.user.is_staff:
            employee = self.request.user.employee_profile
            if employee.department.name != "Human Resources":
                queryset = queryset.filter(interviewer=employee)
        
        return queryset
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Update interview status if all evaluations are completed
        interview_evaluation = serializer.save()
        interview = interview_evaluation.interview
        
        # Check if all interviewers have submitted evaluations
        total_interviewers = interview.interviewers.count()
        evaluations_count = InterviewEvaluation.objects.filter(
            interview=interview
        ).count()
        
        if evaluations_count >= total_interviewers:
            interview.status = InterviewSchedule.InterviewStatus.COMPLETED
            interview.save()
        
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AssessmentTestViewSet(viewsets.ModelViewSet):
    queryset = AssessmentTest.objects.all()
    serializer_class = AssessmentTestSerializer
    permission_classes = [IsAuthenticated, IsHRManager]
    pagination_class = StandardPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        job_opening = self.request.query_params.get('job_opening', None)
        status_param = self.request.query_params.get('status', None)
        
        if job_opening:
            queryset = queryset.filter(job_opening_id=job_opening)
        
        if status_param:
            queryset = queryset.filter(status=status_param)
        
        return queryset


class CandidateAssessmentViewSet(viewsets.ModelViewSet):
    queryset = CandidateAssessment.objects.all()
    serializer_class = CandidateAssessmentSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Apply filters
        application_param = self.request.query_params.get('application', None)
        assessment_param = self.request.query_params.get('assessment_test', None)
        status_param = self.request.query_params.get('status', None)
        
        if application_param:
            queryset = queryset.filter(application_id=application_param)
        
        if assessment_param:
            queryset = queryset.filter(assessment_test_id=assessment_param)
        
        if status_param:
            queryset = queryset.filter(status=status_param)
        
        return queryset
    
    @action(detail=False, methods=['post'], permission_classes=[IsHRManager])
    def send_assessments(self, request):
        serializer = SendAssessmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        assessment_test = serializer.validated_data['assessment_test']
        applications = serializer.validated_data['applications']
        expiry_days = serializer.validated_data['expiry_days']
        
        created_assessments = []
        
        for application in applications:
            # Check if assessment already exists
            if CandidateAssessment.objects.filter(
                application=application,
                assessment_test=assessment_test
            ).exists():
                continue
            
            assessment = CandidateAssessment.objects.create(
                application=application,
                assessment_test=assessment_test,
                status=CandidateAssessment.AssessmentStatus.SENT,
                invitation_sent_date=timezone.now(),
                invitation_expiry_date=timezone.now() + timezone.timedelta(days=expiry_days)
            )
            
            # Send invitation email
            self._send_assessment_invitation(assessment)
            created_assessments.append(assessment.id)
        
        return Response({
            'message': f'Assessments sent to {len(created_assessments)} candidates',
            'assessment_ids': created_assessments
        })
    
    def _send_assessment_invitation(self, assessment):
        subject = f"Assessment Test - {assessment.application.job_opening.title}"
        
        message = f"""
        Dear {assessment.application.first_name} {assessment.application.last_name},
        
        You are invited to take an assessment test for the position of {assessment.application.job_opening.title}.
        
        Test Details:
        - Test Name: {assessment.assessment_test.test_name}
        - Type: {assessment.assessment_test.get_test_type_display()}
        - Duration: {assessment.assessment_test.duration_minutes} minutes
        - Link: {assessment.assessment_test.test_link}
        
        The test must be completed by: {assessment.invitation_expiry_date.strftime('%Y-%m-%d %H:%M')}
        
        Best regards,
        HR Department
        """
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[assessment.application.email],
            fail_silently=True
        )
    
    @action(detail=True, methods=['post'], permission_classes=[IsHRManager])
    def update_score(self, request, pk=None):
        assessment = self.get_object()
        score = request.data.get('score')
        percentage_score = request.data.get('percentage_score')
        detailed_results = request.data.get('detailed_results')
        
        if score is None or percentage_score is None:
            return Response(
                {'error': 'Score and percentage score are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        assessment.score = score
        assessment.percentage_score = percentage_score
        assessment.detailed_results = detailed_results
        assessment.is_passed = percentage_score >= assessment.assessment_test.passing_score
        assessment.status = CandidateAssessment.AssessmentStatus.COMPLETED
        assessment.completed_at = timezone.now()
        assessment.save()
        
        return Response({'status': 'score updated'})


class OfferLetterViewSet(viewsets.ModelViewSet):
    queryset = OfferLetter.objects.all()
    permission_classes = [IsAuthenticated, IsHRManager]
    pagination_class = StandardPagination
    
    def get_serializer_class(self):
        if self.action == 'create':
            return OfferLetterCreateSerializer
        return OfferLetterSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Apply filters
        application_param = self.request.query_params.get('application', None)
        status_param = self.request.query_params.get('status', None)
        
        if application_param:
            queryset = queryset.filter(application_id=application_param)
        
        if status_param:
            queryset = queryset.filter(status=status_param)
        
        return queryset
    
    @action(detail=True, methods=['post'], permission_classes=[IsHRManager])
    def send_offer(self, request, pk=None):
        offer = self.get_object()
        
        if offer.status != OfferLetter.OfferStatus.APPROVED:
            return Response(
                {'error': 'Offer must be approved before sending'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Send offer email
        self._send_offer_email(offer)
        
        offer.status = OfferLetter.OfferStatus.SENT
        offer.sent_date = timezone.now()
        offer.sent_via = 'email'
        offer.save()
        
        # Update application status
        offer.application.application_status = JobApplication.ApplicationStatus.OFFERED
        offer.application.save()
        
        return Response({'status': 'offer sent'})
    
    def _send_offer_email(self, offer):
        subject = f"Job Offer - {offer.job_opening.title}"
        
        # Create a more detailed offer email
        message = f"""
        Dear {offer.application.first_name} {offer.application.last_name},
        
        We are pleased to offer you the position of {offer.job_opening.title}.
        
        Offer Details:
        - Position: {offer.job_opening.title}
        - Department: {offer.job_opening.department.name}
        - Joining Date: {offer.joining_date}
        - Probation Period: {offer.probation_period_months} months
        - Basic Salary: {offer.basic_salary} {offer.currency}
        - Total CTC: {offer.total_ctc} {offer.currency}
        
        Please find the detailed offer letter attached.
        
        To accept this offer, please reply to this email or login to our portal.
        
        The offer is valid for 7 days from the date of this email.
        
        We look forward to welcoming you to our team!
        
        Best regards,
        HR Department
        """
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[offer.application.email],
            fail_silently=True
        )
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def respond(self, request, pk=None):
        offer = self.get_object()
        response = request.data.get('response')  # 'accept' or 'decline'
        notes = request.data.get('notes', '')
        
        if response not in ['accept', 'decline']:
            return Response(
                {'error': 'Response must be either "accept" or "decline"'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if response == 'accept':
            offer.status = OfferLetter.OfferStatus.ACCEPTED
            offer.application.application_status = JobApplication.ApplicationStatus.HIRED
            
            # Create employee record (simplified)
            self._create_employee_record(offer)
        else:
            offer.status = OfferLetter.OfferStatus.DECLINED
            offer.application.application_status = JobApplication.ApplicationStatus.REJECTED
        
        offer.candidate_response_date = timezone.now()
        offer.candidate_response_notes = notes
        offer.save()
        offer.application.save()
        
        return Response({'status': 'response recorded'})


class BackgroundCheckViewSet(viewsets.ModelViewSet):
    queryset = BackgroundCheck.objects.all()
    serializer_class = BackgroundCheckSerializer
    permission_classes = [IsAuthenticated, IsHRManager]
    pagination_class = StandardPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Apply filters
        application_param = self.request.query_params.get('application', None)
        check_type_param = self.request.query_params.get('check_type', None)
        status_param = self.request.query_params.get('status', None)
        
        if application_param:
            queryset = queryset.filter(application_id=application_param)
        
        if check_type_param:
            queryset = queryset.filter(check_type=check_type_param)
        
        if status_param:
            queryset = queryset.filter(status=status_param)
        
        return queryset


class ReferenceCheckViewSet(viewsets.ModelViewSet):
    queryset = ReferenceCheck.objects.all()
    serializer_class = ReferenceCheckSerializer
    permission_classes = [IsAuthenticated, IsHRManager]
    pagination_class = StandardPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        application_param = self.request.query_params.get('application', None)
        
        if application_param:
            queryset = queryset.filter(application_id=application_param)
        
        return queryset


# ============================================================================
# NEW WORKFLOW VIEWSETS
# ============================================================================

class ComplianceChecklistViewSet(viewsets.ModelViewSet):
    queryset = ComplianceChecklist.objects.all()
    serializer_class = ComplianceChecklistSerializer
    permission_classes = [IsAuthenticated, IsHRManager]
    pagination_class = StandardPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        application = self.request.query_params.get('application', None)
        if application:
            queryset = queryset.filter(application_id=application)
        return queryset


class SelectionDecisionViewSet(viewsets.ModelViewSet):
    queryset = SelectionDecision.objects.all()
    serializer_class = SelectionDecisionSerializer
    permission_classes = [IsAuthenticated, IsHRManager]
    pagination_class = StandardPagination

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Action for HR or Principal to approve"""
        selection = self.get_object()
        role = request.data.get('role') # 'hr' or 'principal'
        user = request.user
        
        # Safe access to employee profile
        employee = getattr(user, 'employee_profile', None)

        if role == 'hr':
            # Allow superuser OR anyone in HR department
            can_approve = user.is_superuser or (
                employee and 
                employee.department and 
                employee.department.name == "Human Resources"
            )
            
            if can_approve:
                selection.hr_approved = True
                selection.hr_approver = employee
                selection.hr_approval_date = timezone.now()
            else:
                return Response(
                    {'error': 'Unauthorized: Only HR department staff or Super Admins can approve as HR'}, 
                    status=status.HTTP_403_FORBIDDEN
                )
        elif role == 'principal': 
             # Allow superuser OR principal/director role check
             # TODO: Stronger check for Principal/Director role in real implementation
             selection.principal_approved = True
             selection.principal_approver = employee
             selection.principal_approval_date = timezone.now()
        else:
             return Response({'error': 'Unauthorized approval attempt'}, status=status.HTTP_403_FORBIDDEN)
        
        selection.save()
        return Response({'status': 'approved'})


class OnboardingProcessViewSet(viewsets.ModelViewSet):
    queryset = OnboardingProcess.objects.all()
    serializer_class = OnboardingProcessSerializer
    permission_classes = [IsAuthenticated, IsHRManager]
    pagination_class = StandardPagination


class ProbationReviewViewSet(viewsets.ModelViewSet):
    queryset = ProbationReview.objects.all()
    serializer_class = ProbationReviewSerializer
    permission_classes = [IsAuthenticated, IsHRManager]
    pagination_class = StandardPagination


# ============================================================================
# DASHBOARD & ANALYTICS VIEWS
# ============================================================================

class RecruitmentDashboardView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        # Calculate dashboard statistics
        total_job_openings = JobOpening.objects.count()
        active_job_openings = JobOpening.objects.filter(
            status=JobOpening.Status.PUBLISHED,
            closing_date__gte=timezone.now().date()
        ).count()
        
        total_applications = JobApplication.objects.count()
        applications_today = JobApplication.objects.filter(
            application_date__date=timezone.now().date()
        ).count()
        
        pending_interviews = InterviewSchedule.objects.filter(
            status=InterviewSchedule.InterviewStatus.SCHEDULED,
            interview_date__gte=timezone.now().date()
        ).count()
        
        offers_pending = OfferLetter.objects.filter(
            status=OfferLetter.OfferStatus.SENT
        ).count()
        
        hired_this_month = JobApplication.objects.filter(
            application_status=JobApplication.ApplicationStatus.HIRED,
            application_date__month=timezone.now().month,
            application_date__year=timezone.now().year
        ).count()
        
        # Recent applications
        recent_applications = JobApplication.objects.order_by('-application_date')[:10]
        
        # Upcoming interviews
        upcoming_interviews = InterviewSchedule.objects.filter(
            status=InterviewSchedule.InterviewStatus.SCHEDULED,
            interview_date__gte=timezone.now().date()
        ).order_by('interview_date', 'start_time')[:10]
        
        # Expiring jobs
        expiring_jobs = JobOpening.objects.filter(
            status=JobOpening.Status.PUBLISHED,
            closing_date__range=[
                timezone.now().date(),
                timezone.now().date() + timezone.timedelta(days=7)
            ]
        ).order_by('closing_date')[:10]
        
        # Application status distribution
        status_distribution = dict(
            JobApplication.objects.values_list('application_status')
            .annotate(count=Count('id'))
            .values_list('application_status', 'count')
        )
        
        # Source distribution
        source_distribution = dict(
            JobApplication.objects.values_list('application_source')
            .annotate(count=Count('id'))
            .values_list('application_source', 'count')
        )
        
        data = {
            'total_job_openings': total_job_openings,
            'active_job_openings': active_job_openings,
            'total_applications': total_applications,
            'applications_today': applications_today,
            'pending_interviews': pending_interviews,
            'offers_pending': offers_pending,
            'hired_this_month': hired_this_month,
            'recent_applications': JobApplicationListSerializer(recent_applications, many=True).data,
            'upcoming_interviews': InterviewScheduleListSerializer(upcoming_interviews, many=True).data,
            'expiring_jobs': JobOpeningListSerializer(expiring_jobs, many=True).data,
            'application_status_distribution': status_distribution,
            'source_distribution': source_distribution,
        }
        
        return Response(data)


class RecruitmentAnalyticsView(APIView):
    permission_classes = [IsAuthenticated, IsHRManager]
    
    def get(self, request):
        # Time period filter
        days = int(request.query_params.get('days', 30))
        start_date = timezone.now().date() - timezone.timedelta(days=days)
        
        # Applications over time
        applications_over_time = JobApplication.objects.filter(
            application_date__date__gte=start_date
        ).extra({
            'date': "date(application_date)"
        }).values('date').annotate(
            count=Count('id')
        ).order_by('date')
        
        # Applications by job opening
        applications_by_job = JobApplication.objects.filter(
            application_date__date__gte=start_date
        ).values(
            'job_opening__title', 'job_opening__reference_number'
        ).annotate(
            count=Count('id'),
            shortlisted=Count('id', filter=Q(application_status=JobApplication.ApplicationStatus.SHORTLISTED)),
            hired=Count('id', filter=Q(application_status=JobApplication.ApplicationStatus.HIRED))
        ).order_by('-count')
        
        # Source effectiveness
        source_effectiveness = JobApplication.objects.filter(
            application_date__date__gte=start_date
        ).values('application_source').annotate(
            total=Count('id'),
            shortlisted=Count('id', filter=Q(application_status=JobApplication.ApplicationStatus.SHORTLISTED)),
            hired=Count('id', filter=Q(application_status=JobApplication.ApplicationStatus.HIRED))
        ).annotate(
            conversion_rate=ExpressionWrapper(
                F('hired') * 100.0 / F('total'),
                output_field=models.DecimalField()
            )
        ).order_by('-conversion_rate')
        
        # Time to hire
        hired_applications = JobApplication.objects.filter(
            application_status=JobApplication.ApplicationStatus.HIRED,
            application_date__date__gte=start_date
        )
        
        time_to_hire_data = []
        for app in hired_applications:
            # Find when offer was accepted
            offer = OfferLetter.objects.filter(
                application=app,
                status=OfferLetter.OfferStatus.ACCEPTED
            ).first()
            
            if offer:
                days_to_hire = (offer.candidate_response_date.date() - app.application_date.date()).days
                time_to_hire_data.append({
                    'application_id': app.id,
                    'candidate': app.full_name,
                    'position': app.job_opening.title,
                    'days_to_hire': days_to_hire
                })
        
        avg_time_to_hire = sum(item['days_to_hire'] for item in time_to_hire_data) / len(time_to_hire_data) if time_to_hire_data else 0
        
        return Response({
            'applications_over_time': list(applications_over_time),
            'applications_by_job': list(applications_by_job),
            'source_effectiveness': list(source_effectiveness),
            'time_to_hire': {
                'average_days': avg_time_to_hire,
                'details': time_to_hire_data[:20]  # Top 20
            },
            'period': {
                'start_date': start_date,
                'end_date': timezone.now().date(),
                'days': days
            }
        })


# ============================================================================
# PUBLIC VIEWS (No authentication required)
# ============================================================================

class PublicJobOpeningsView(generics.ListAPIView):
    """Public view for job openings"""
    serializer_class = JobOpeningListSerializer
    pagination_class = StandardPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'description', 'department__name']
    ordering_fields = ['opening_date', 'closing_date']
    
    def get_queryset(self):
        return JobOpening.objects.filter(
            status=JobOpening.Status.PUBLISHED,
            closing_date__gte=timezone.now().date()
        )


class PublicJobApplicationView(generics.CreateAPIView):
    """Public view for submitting job applications"""
    serializer_class = JobApplicationCreateSerializer
    parser_classes = [MultiPartParser, FormParser]
    
    def perform_create(self, serializer):
        # Set application source based on referral
        if self.request.data.get('referral_code'):
            try:
                employee = Employee.objects.get(
                    referral_code=self.request.data['referral_code']
                )
                serializer.validated_data['referral_employee'] = employee
                serializer.validated_data['application_source'] = JobApplication.ApplicationSource.REFERRAL
            except Employee.DoesNotExist:
                pass
        
        serializer.save()


