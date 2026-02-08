from rest_framework import serializers
from django.db import transaction
from django.utils import timezone
from django.core.validators import EmailValidator
from .models import *
from workforce.models import Employee
from django.contrib.auth import get_user_model

User = get_user_model()


# ============================================================================
# HELPER SERIALIZERS
# ============================================================================

class RecruitmentSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecruitmentSource
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')


class EducationLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = EducationLevel
        fields = ('id', 'code', 'name', 'description')


class JobTitleSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobTitle
        fields = ('id', 'title', 'code', 'category')


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ('id', 'name', 'code', 'department_type')


class CampusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Campus
        fields = ('id', 'name', 'code', 'location')


class EmployeeSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    email = serializers.EmailField(source='official_email', read_only=True)
    
    class Meta:
        model = Employee
        fields = ('id', 'employee_no', 'full_name', 'email', 'department')
    
    def get_full_name(self, obj):
        return obj.get_full_name()


# ============================================================================
# JOB OPENING SERIALIZERS
# ============================================================================

class JobOpeningListSerializer(serializers.ModelSerializer):
    department = DepartmentSerializer(read_only=True)
    campus = CampusSerializer(read_only=True)
    job_title = JobTitleSerializer(read_only=True)
    hiring_manager = EmployeeSerializer(read_only=True)
    number_of_applications = serializers.SerializerMethodField()
    days_remaining = serializers.SerializerMethodField()
    
    class Meta:
        model = JobOpening
        fields = (
            'id', 'reference_number', 'title', 'department', 'campus',
            'job_title', 'number_of_positions', 'opening_date', 'closing_date',
            'status', 'hiring_manager', 'number_of_applications', 'days_remaining',
            'is_remote_allowed', 'min_salary', 'max_salary'
        )
    
    def get_number_of_applications(self, obj):
        return obj.applications.count()
    
    def get_days_remaining(self, obj):
        if obj.closing_date:
            remaining = (obj.closing_date - timezone.now().date()).days
            return max(0, remaining)
        return None


class JobOpeningCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobOpening
        fields = (
            'job_title', 'department', 'campus', 'opening_type', 'title',
            'description', 'responsibilities', 'requirements', 'number_of_positions',
            'min_salary', 'max_salary', 'opening_date', 'closing_date',
            'expected_joining_date', 'hiring_manager', 'benefits', 'key_skills',
            'is_remote_allowed', 'travel_requirement', 'recruitment_sources'
        )
    
    def validate(self, data):
        # Validate dates
        if data['opening_date'] > data['closing_date']:
            raise serializers.ValidationError({
                'closing_date': 'Closing date must be after opening date'
            })
        
        if data.get('expected_joining_date'):
            if data['expected_joining_date'] < data['closing_date']:
                raise serializers.ValidationError({
                    'expected_joining_date': 'Expected joining date must be after closing date'
                })
        
        # Validate salary range
        if data.get('min_salary') and data.get('max_salary'):
            if data['min_salary'] > data['max_salary']:
                raise serializers.ValidationError({
                    'max_salary': 'Maximum salary must be greater than minimum salary'
                })
        
        return data
    
    def create(self, validated_data):
        recruitment_sources = validated_data.pop('recruitment_sources', [])
        
        # Set status to draft
        validated_data['status'] = JobOpening.Status.DRAFT
        
        # Generate reference number
        year = timezone.now().year
        prefix = f"JO-{year}-"
        last_job = JobOpening.objects.filter(
            reference_number__startswith=prefix
        ).order_by('-reference_number').first()
        
        if last_job:
            last_num = int(last_job.reference_number.split('-')[-1])
            new_num = last_num + 1
        else:
            new_num = 1001
        
        validated_data['reference_number'] = f"{prefix}{new_num}"
        
        # Set requested by (current user)
        user = self.context['request'].user
        try:
            employee = Employee.objects.get(user=user)
            validated_data['requested_by'] = employee
        except Employee.DoesNotExist:
            pass
        
        job_opening = JobOpening.objects.create(**validated_data)
        
        # Add recruitment sources
        if recruitment_sources:
            job_opening.recruitment_sources.set(recruitment_sources)
        
        return job_opening


class JobOpeningDetailSerializer(serializers.ModelSerializer):
    department = DepartmentSerializer(read_only=True)
    campus = CampusSerializer(read_only=True)
    job_title = JobTitleSerializer(read_only=True)
    hiring_manager = EmployeeSerializer(read_only=True)
    hr_approver = EmployeeSerializer(read_only=True)
    final_approver = EmployeeSerializer(read_only=True)
    requested_by = EmployeeSerializer(read_only=True)
    recruitment_sources = RecruitmentSourceSerializer(many=True, read_only=True)
    
    # Statistics
    total_applications = serializers.SerializerMethodField()
    shortlisted_applications = serializers.SerializerMethodField()
    hired_applications = serializers.SerializerMethodField()
    
    class Meta:
        model = JobOpening
        fields = '__all__'
        read_only_fields = (
            'created_at', 'updated_at', 'created_by', 'updated_by',
            'reference_number', 'requested_by', 'publish_date', 'published_by'
        )
    
    def get_total_applications(self, obj):
        return obj.applications.count()
    
    def get_shortlisted_applications(self, obj):
        return obj.applications.filter(
            application_status=JobApplication.ApplicationStatus.SHORTLISTED
        ).count()
    
    def get_hired_applications(self, obj):
        return obj.applications.filter(
            application_status=JobApplication.ApplicationStatus.HIRED
        ).count()


# ============================================================================
# JOB APPLICATION SERIALIZERS
# ============================================================================

class ApplicationEducationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApplicationEducation
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')


class ApplicationExperienceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApplicationExperience
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')


class ApplicationSkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApplicationSkill
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')


class ApplicationCertificateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApplicationCertificate
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')


class JobApplicationCreateSerializer(serializers.ModelSerializer):
    educations = ApplicationEducationSerializer(many=True, required=False)
    experiences = ApplicationExperienceSerializer(many=True, required=False)
    skills = ApplicationSkillSerializer(many=True, required=False)
    certificates = ApplicationCertificateSerializer(many=True, required=False)
    
    class Meta:
        model = JobApplication
        fields = (
            'job_opening', 'first_name', 'middle_name', 'last_name',
            'email', 'phone', 'alternate_phone', 'address', 'city',
            'state', 'country', 'postal_code', 'application_source',
            'referral_employee', 'recruitment_source', 'resume',
            'cover_letter', 'highest_education', 'total_experience_years',
            'current_employer', 'current_position', 'current_salary',
            'expected_salary', 'notice_period_days', 'gender',
            'date_of_birth', 'nationality', 'preferred_contact_method',
            'consent_to_process_data', 'consent_to_store_data',
            'privacy_policy_accepted', 'linkedin_profile', 'portfolio_url',
            'github_profile', 'notes', 'educations', 'experiences',
            'skills', 'certificates'
        )
    
    def validate_email(self, value):
        # Check if email already applied for this job opening
        request = self.context.get('request')
        if request and request.method == 'POST':
            job_opening_id = request.data.get('job_opening')
            if job_opening_id:
                if JobApplication.objects.filter(
                    email=value,
                    job_opening_id=job_opening_id
                ).exists():
                    raise serializers.ValidationError(
                        "You have already applied for this position with this email"
                    )
        return value
    
    def validate(self, data):
        # Validate consent
        if not data.get('consent_to_process_data'):
            raise serializers.ValidationError({
                'consent_to_process_data': 'You must consent to data processing'
            })
        
        if not data.get('privacy_policy_accepted'):
            raise serializers.ValidationError({
                'privacy_policy_accepted': 'You must accept the privacy policy'
            })
        
        return data
    
    @transaction.atomic
    def create(self, validated_data):
        # Extract nested data
        educations_data = validated_data.pop('educations', [])
        experiences_data = validated_data.pop('experiences', [])
        skills_data = validated_data.pop('skills', [])
        certificates_data = validated_data.pop('certificates', [])
        
        # Create application
        application = JobApplication.objects.create(**validated_data)
        
        # Create related objects
        for education_data in educations_data:
            ApplicationEducation.objects.create(
                application=application, **education_data
            )
        
        for experience_data in experiences_data:
            ApplicationExperience.objects.create(
                application=application, **experience_data
            )
        
        for skill_data in skills_data:
            ApplicationSkill.objects.create(
                application=application, **skill_data
            )
        
        for certificate_data in certificates_data:
            ApplicationCertificate.objects.create(
                application=application, **certificate_data
            )
        
        return application


class JobApplicationListSerializer(serializers.ModelSerializer):
    job_opening = JobOpeningListSerializer(read_only=True)
    full_name = serializers.SerializerMethodField()
    days_since_application = serializers.SerializerMethodField()
    
    class Meta:
        model = JobApplication
        fields = (
            'id', 'full_name', 'email', 'phone', 'job_opening',
            'application_status', 'application_date', 'days_since_application',
            'total_experience_years', 'current_employer'
        )
    
    def get_full_name(self, obj):
        return obj.full_name
    
    def get_days_since_application(self, obj):
        return (timezone.now() - obj.application_date).days


class JobApplicationDetailSerializer(serializers.ModelSerializer):
    job_opening = JobOpeningListSerializer(read_only=True)
    highest_education = EducationLevelSerializer(read_only=True)
    referral_employee = EmployeeSerializer(read_only=True)
    recruitment_source = RecruitmentSourceSerializer(read_only=True)
    
    # Nested serializers
    educations = ApplicationEducationSerializer(many=True, read_only=True)
    experiences = ApplicationExperienceSerializer(many=True, read_only=True)
    skills = ApplicationSkillSerializer(many=True, read_only=True)
    certificates = ApplicationCertificateSerializer(many=True, read_only=True)
    
    # Additional fields
    full_name = serializers.SerializerMethodField()
    resume_url = serializers.SerializerMethodField()
    cover_letter_url = serializers.SerializerMethodField()
    
    class Meta:
        model = JobApplication
        fields = '__all__'
        read_only_fields = (
            'created_at', 'updated_at', 'created_by', 'updated_by',
            'application_date'
        )
    
    def get_full_name(self, obj):
        return obj.full_name
    
    def get_resume_url(self, obj):
        if obj.resume:
            return obj.resume.url
        return None
    
    def get_cover_letter_url(self, obj):
        if obj.cover_letter:
            return obj.cover_letter.url
        return None


# ============================================================================
# INTERVIEW SERIALIZERS
# ============================================================================

class InterviewRoundSerializer(serializers.ModelSerializer):
    job_opening_title = serializers.CharField(source='job_opening.title', read_only=True)

    class Meta:
        model = InterviewRound
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'updated_by', 'job_opening_title')


class InterviewScheduleCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = InterviewSchedule
        fields = (
            'application', 'interview_round', 'interview_date',
            'start_time', 'end_time', 'interview_mode', 'location',
            'interviewers', 'primary_interviewer', 'notes'
        )
    
    def validate(self, data):
        # Validate interview time
        if data['start_time'] >= data['end_time']:
            raise serializers.ValidationError({
                'end_time': 'End time must be after start time'
            })
        
        # Check for scheduling conflicts for interviewers
        interview_date = data['interview_date']
        start_time = data['start_time']
        end_time = data['end_time']
        
        for interviewer in data.get('interviewers', []):
            conflicting_interviews = InterviewSchedule.objects.filter(
                interviewers=interviewer,
                interview_date=interview_date,
                start_time__lt=end_time,
                end_time__gt=start_time,
                status__in=[
                    InterviewSchedule.InterviewStatus.SCHEDULED,
                    InterviewSchedule.InterviewStatus.IN_PROGRESS
                ]
            )
            
            if conflicting_interviews.exists():
                raise serializers.ValidationError(
                    f"Interviewer {interviewer.employee_no} has a scheduling conflict"
                )
        
        return data


class InterviewScheduleListSerializer(serializers.ModelSerializer):
    application = serializers.CharField(source='application.full_name', read_only=True)
    application_id = serializers.IntegerField(source='application.id', read_only=True)
    interview_round = serializers.CharField(source='interview_round.round_name', read_only=True)
    interview_round_id = serializers.IntegerField(source='interview_round.id', read_only=True)
    primary_interviewer = EmployeeSerializer(read_only=True)
    interviewers = EmployeeSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    interview_mode_display = serializers.CharField(source='get_interview_mode_display', read_only=True)
    
    job_title = serializers.CharField(source='application.job_opening.title', read_only=True)
    job_opening_id = serializers.IntegerField(source='application.job_opening.id', read_only=True)
    
    class Meta:
        model = InterviewSchedule
        fields = (
            'id', 'application', 'application_id', 'job_title', 'job_opening_id',
            'interview_round', 'interview_round_id', 'interview_date',
            'start_time', 'end_time', 'interview_mode', 'interview_mode_display',
            'location', 'status', 'status_display', 'primary_interviewer',
            'interviewers', 'candidate_notified', 'interviewers_notified'
        )


class InterviewEvaluationSerializer(serializers.ModelSerializer):
    interviewer = EmployeeSerializer(read_only=True)
    interview = serializers.PrimaryKeyRelatedField(queryset=InterviewSchedule.objects.all())
    
    class Meta:
        model = InterviewEvaluation
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')
    
    def validate(self, data):
        interview = data.get('interview')
        interviewer = self.context['request'].user.employee_profile
        
        # Check if interviewer is part of the interview
        if not interview.interviewers.filter(id=interviewer.id).exists():
            raise serializers.ValidationError({
                'interviewer': 'You are not assigned to this interview'
            })
        
        # Check if evaluation already exists
        if InterviewEvaluation.objects.filter(
            interview=interview,
            interviewer=interviewer
        ).exists():
            raise serializers.ValidationError({
                'interview': 'You have already submitted evaluation for this interview'
            })
        
        return data
    
    def create(self, validated_data):
        # Set interviewer from current user
        interviewer = self.context['request'].user.employee_profile
        validated_data['interviewer'] = interviewer
        
        return super().create(validated_data)


# ============================================================================
# ASSESSMENT SERIALIZERS
# ============================================================================

class AssessmentTestSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssessmentTest
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')


class CandidateAssessmentSerializer(serializers.ModelSerializer):
    application = serializers.CharField(source='application.full_name')
    assessment_test = AssessmentTestSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display')
    
    class Meta:
        model = CandidateAssessment
        fields = '__all__'
        read_only_fields = (
            'created_at', 'updated_at', 'created_by', 'updated_by',
            'invitation_sent_date', 'started_at', 'completed_at'
        )


class SendAssessmentSerializer(serializers.Serializer):
    assessment_test = serializers.PrimaryKeyRelatedField(
        queryset=AssessmentTest.objects.filter(status=AssessmentTest.TestStatus.ACTIVE)
    )
    applications = serializers.PrimaryKeyRelatedField(
        queryset=JobApplication.objects.all(),
        many=True
    )
    expiry_days = serializers.IntegerField(min_value=1, max_value=30, default=7)


# ============================================================================
# OFFER LETTER SERIALIZERS
# ============================================================================

class OfferLetterCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = OfferLetter
        fields = (
            'application', 'job_opening', 'offer_date', 'joining_date',
            'probation_period_months', 'basic_salary', 'allowances',
            'total_ctc', 'currency', 'benefits', 'working_hours',
            'work_location', 'terms_and_conditions', 'notes'
        )
    
    def validate(self, data):
        application = data.get('application')
        
        # Check if application is in offered status
        if application.application_status != JobApplication.ApplicationStatus.OFFERED:
            raise serializers.ValidationError({
                'application': 'Application must be in OFFERED status to create offer letter'
            })
        
        # Check if offer already exists
        if OfferLetter.objects.filter(application=application).exists():
            raise serializers.ValidationError({
                'application': 'Offer letter already exists for this application'
            })
        
        return data
    
    def create(self, validated_data):
        # Generate offer reference
        year = timezone.now().year
        prefix = f"OFFER-{year}-"
        last_offer = OfferLetter.objects.filter(
            offer_reference__startswith=prefix
        ).order_by('-offer_reference').first()
        
        if last_offer:
            last_num = int(last_offer.offer_reference.split('-')[-1])
            new_num = last_num + 1
        else:
            new_num = 1001
        
        validated_data['offer_reference'] = f"{prefix}{new_num}"
        
        # Set prepared by
        user = self.context['request'].user
        try:
            employee = Employee.objects.get(user=user)
            validated_data['prepared_by'] = employee
        except Employee.DoesNotExist:
            pass
        
        return super().create(validated_data)


class OfferLetterSerializer(serializers.ModelSerializer):
    application = serializers.CharField(source='application.full_name')
    job_opening = serializers.CharField(source='job_opening.title')
    prepared_by = EmployeeSerializer(read_only=True)
    approved_by = EmployeeSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display')
    
    class Meta:
        model = OfferLetter
        fields = '__all__'
        read_only_fields = (
            'created_at', 'updated_at', 'created_by', 'updated_by',
            'offer_reference', 'prepared_by', 'sent_date'
        )


# ============================================================================
# BACKGROUND CHECK SERIALIZERS
# ============================================================================

class BackgroundCheckSerializer(serializers.ModelSerializer):
    application = serializers.CharField(source='application.full_name')
    check_type_display = serializers.CharField(source='get_check_type_display')
    status_display = serializers.CharField(source='get_status_display')
    reviewed_by = EmployeeSerializer(read_only=True)
    
    class Meta:
        model = BackgroundCheck
        fields = '__all__'
        read_only_fields = (
            'created_at', 'updated_at', 'created_by', 'updated_by',
            'completed_date', 'reviewed_by', 'review_date'
        )


class ReferenceCheckSerializer(serializers.ModelSerializer):
    application = serializers.CharField(source='application.full_name')
    reference_type_display = serializers.CharField(source='get_reference_type_display')
    work_ethics_rating_display = serializers.CharField(source='get_work_ethics_rating_display')
    
    class Meta:
        model = ReferenceCheck
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')


# ============================================================================
# WORKFLOW SERIALIZERS
# ============================================================================

class RecruitmentWorkflowSerializer(serializers.ModelSerializer):
    job_opening = serializers.CharField(source='job_opening.title')
    
    class Meta:
        model = RecruitmentWorkflow
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')


class ApplicationWorkflowSerializer(serializers.ModelSerializer):
    application = serializers.CharField(source='application.full_name')
    workflow_stage = RecruitmentWorkflowSerializer(read_only=True)
    assigned_to = EmployeeSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display')
    
    class Meta:
        model = ApplicationWorkflow
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')


# ============================================================================
# ANALYTICS SERIALIZERS
# ============================================================================

class RecruitmentAnalyticsSerializer(serializers.ModelSerializer):
    job_opening = serializers.CharField(source='job_opening.title')
    
    class Meta:
        model = RecruitmentAnalytics
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')


# ============================================================================
# EMAIL TEMPLATE SERIALIZERS
# ============================================================================

class RecruitmentEmailTemplateSerializer(serializers.ModelSerializer):
    template_type_display = serializers.CharField(source='get_template_type_display')
    
    class Meta:
        model = RecruitmentEmailTemplate
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')


# ============================================================================
# COMMUNICATION SERIALIZERS
# ============================================================================

class RecruitmentCommunicationSerializer(serializers.ModelSerializer):
    application = serializers.CharField(source='application.full_name')
    communication_type_display = serializers.CharField(
        source='get_communication_type_display'
    )
    direction_display = serializers.CharField(source='get_direction_display')
    
    class Meta:
        model = RecruitmentCommunication
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')


# ============================================================================
# DASHBOARD SERIALIZERS
# ============================================================================

class RecruitmentDashboardSerializer(serializers.Serializer):
    total_job_openings = serializers.IntegerField()
    active_job_openings = serializers.IntegerField()
    total_applications = serializers.IntegerField()
    applications_today = serializers.IntegerField()
    pending_interviews = serializers.IntegerField()
    offers_pending = serializers.IntegerField()
    
    recent_applications = JobApplicationListSerializer(many=True)
    upcoming_interviews = InterviewScheduleListSerializer(many=True)
    expiring_jobs = JobOpeningListSerializer(many=True)
    
    application_status_distribution = serializers.DictField()
    source_distribution = serializers.DictField()


# ============================================================================
# NEW WORKFLOW SERIALIZERS (STAGES 5-9)
# ============================================================================

class ComplianceChecklistSerializer(serializers.ModelSerializer):
    """Stage 5"""
    is_complete = serializers.SerializerMethodField()

    class Meta:
        model = ComplianceChecklist
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')

    def get_is_complete(self, obj):
        return all([
            obj.certificates_verified,
            obj.teaching_license_verified,
            obj.references_checked,
            obj.criminal_clearance_verified
        ])


class SelectionDecisionSerializer(serializers.ModelSerializer):
    """Stage 6"""
    hr_approver = EmployeeSerializer(read_only=True)
    principal_approver = EmployeeSerializer(read_only=True)

    class Meta:
        model = SelectionDecision
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'updated_by', 'hr_approval_date', 'principal_approval_date')


class OnboardingProcessSerializer(serializers.ModelSerializer):
    """Stage 8"""
    class Meta:
        model = OnboardingProcess
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'updated_by', 'is_completed', 'completion_date', 'progress_percentage')


class ProbationReviewSerializer(serializers.ModelSerializer):
    """Stage 9"""
    class Meta:
        model = ProbationReview
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')


class CandidateFullWorkflowSerializer(serializers.ModelSerializer):
    """Aggregates all workflow data for a single candidate"""
    application_id = serializers.IntegerField(source='id')
    full_name = serializers.CharField()
    position = serializers.CharField(source='job_opening.title')
    status = serializers.CharField(source='application_status')
    
    # Stages
    evaluation = serializers.SerializerMethodField()
    compliance = ComplianceChecklistSerializer(source='compliance_checklist', read_only=True)
    selection = SelectionDecisionSerializer(source='selection_decision', read_only=True)
    offer = OfferLetterSerializer(source='offer_letter', read_only=True)
    onboarding = OnboardingProcessSerializer(source='onboarding_process', read_only=True)
    probation = serializers.SerializerMethodField()
    active_interview_id = serializers.SerializerMethodField()
    
    class Meta:
        model = JobApplication
        fields = (
            'application_id', 'full_name', 'position', 'status',
            'evaluation', 'compliance', 'selection', 'offer', 'onboarding', 'probation',
            'active_interview_id'
        )
        
    def get_evaluation(self, obj):
        # Logic: Find the latest interview with an evaluation.
        last_interview = obj.interviews.last()
        if last_interview and hasattr(last_interview, 'evaluation'):
             return InterviewEvaluationSerializer(last_interview.evaluation).data
        return None

    def get_probation(self, obj):
        if hasattr(obj, 'onboarding_process') and obj.onboarding_process.employee_profile:
             probation = ProbationReview.objects.filter(employee=obj.onboarding_process.employee_profile).last()
             if probation:
                 return ProbationReviewSerializer(probation).data
        return None
        
    def get_active_interview_id(self, obj):
        last_interview = obj.interviews.exclude(status__in=['completed', 'cancelled']).last()
        return last_interview.id if last_interview else None