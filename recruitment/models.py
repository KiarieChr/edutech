# ============================================================================
# RECRUITMENT MODULE
# ============================================================================

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.auth import get_user_model

from workforce.core_models import AuditedModel, Employee
from workforce.models import JobTitle, Department, Campus, EducationLevel

User = get_user_model()

class RecruitmentSource(AuditedModel):
    """Sources of job applications"""
    
    class SourceType(models.TextChoices):
        PORTAL = 'portal', _('Career Portal')
        REFERRAL = 'referral', _('Employee Referral')
        AGENCY = 'agency', _('Recruitment Agency')
        CAMPUS = 'campus', _('Campus Recruitment')
        SOCIAL = 'social', _('Social Media')
        NEWSPAPER = 'newspaper', _('Newspaper')
        OTHER = 'other', _('Other')
    
    name = models.CharField(max_length=200)
    source_type = models.CharField(max_length=20, choices=SourceType.choices)
    contact_person = models.CharField(max_length=200, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    website = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'recruitment_source'
        ordering = ['name']
    
    def __str__(self):
        return self.name


class JobOpening(AuditedModel):
    """Vacant positions available for recruitment"""
    
    class OpeningType(models.TextChoices):
        NEW = 'new', _('New Position')
        REPLACEMENT = 'replacement', _('Replacement')
        TEMPORARY = 'temporary', _('Temporary')
        CONTRACT = 'contract', _('Contract')
    
    class Status(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        APPROVED = 'approved', _('Approved')
        PUBLISHED = 'published', _('Published')
        ON_HOLD = 'on_hold', _('On Hold')
        CLOSED = 'closed', _('Closed')
        CANCELLED = 'cancelled', _('Cancelled')
    
    job_title = models.ForeignKey(
        JobTitle, 
        on_delete=models.PROTECT,
        related_name='job_openings'
    )
    department = models.ForeignKey(
        Department, 
        on_delete=models.PROTECT,
        related_name='job_openings'
    )
    campus = models.ForeignKey(
        Campus, 
        on_delete=models.PROTECT,
        related_name='job_openings'
    )
    
    opening_type = models.CharField(max_length=20, choices=OpeningType.choices)
    status = models.CharField(
        max_length=20, 
        choices=Status.choices,
        default=Status.DRAFT
    )
    
    reference_number = models.CharField(max_length=100, unique=True)
    title = models.CharField(max_length=500)
    description = models.TextField()
    responsibilities = models.TextField()
    requirements = models.TextField()
    
    # Position details
    number_of_positions = models.PositiveIntegerField(default=1)
    min_salary = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        null=True, 
        blank=True
    )
    max_salary = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        null=True, 
        blank=True
    )
    salary_currency = models.CharField(max_length=3, default='USD')
    
    # Dates
    opening_date = models.DateField()
    closing_date = models.DateField()
    expected_joining_date = models.DateField(null=True, blank=True)
    
    # Approval workflow
    requested_by = models.ForeignKey(
        Employee, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='job_openings_requested'
    )
    hiring_manager = models.ForeignKey(
        Employee, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='job_openings_managed'
    )
    hr_approver = models.ForeignKey(
        Employee, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='job_openings_approved'
    )
    final_approver = models.ForeignKey(
        Employee, 
        on_delete=models.SET_NULL, 
        null=True,
        blank=True,
        related_name='job_openings_final_approved'
    )
    
    # Published details
    publish_date = models.DateField(null=True, blank=True)
    published_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='published_job_openings'
    )
    
    # Recruitment sources
    recruitment_sources = models.ManyToManyField(
        RecruitmentSource,
        blank=True,
        related_name='job_openings'
    )
    
    # Additional fields
    benefits = models.TextField(blank=True)
    key_skills = models.JSONField(
        blank=True, 
        null=True,
        help_text="List of required skills"
    )
    is_remote_allowed = models.BooleanField(default=False)
    travel_requirement = models.TextField(blank=True)
    
    class Meta:
        db_table = 'recruitment_job_opening'
        ordering = ['-opening_date']
        indexes = [
            models.Index(fields=['reference_number']),
            models.Index(fields=['status', 'closing_date']),
        ]
    
    def __str__(self):
        return f"{self.reference_number} - {self.title}"


class JobApplication(AuditedModel):
    """Job applications from candidates"""
    
    class ApplicationStatus(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        SUBMITTED = 'submitted', _('Submitted')
        SCREENING = 'screening', _('Screening')
        SHORTLISTED = 'shortlisted', _('Shortlisted')
        INTERVIEW = 'interview', _('Interview')
        BACKGROUND_CHECK = 'background_check', _('Background Check')
        OFFERED = 'offered', _('Offered')
        HIRED = 'hired', _('Hired')
        REJECTED = 'rejected', _('Rejected')
        WITHDRAWN = 'withdrawn', _('Withdrawn')
    
    class ApplicationSource(models.TextChoices):
        PORTAL = 'portal', _('Career Portal')
        EMAIL = 'email', _('Email')
        REFERRAL = 'referral', _('Employee Referral')
        AGENCY = 'agency', _('Agency')
        WALK_IN = 'walk_in', _('Walk-in')
    
    # Personal Information
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    alternate_phone = models.CharField(max_length=20, blank=True)
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20, blank=True)
    
    # Application Details
    job_opening = models.ForeignKey(
        JobOpening, 
        on_delete=models.CASCADE,
        related_name='applications'
    )
    application_source = models.CharField(
        max_length=20, 
        choices=ApplicationSource.choices
    )
    referral_employee = models.ForeignKey(
        Employee, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='referred_applications'
    )
    recruitment_source = models.ForeignKey(
        RecruitmentSource, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    # Documents
    resume = models.FileField(
        upload_to='applications/resumes/%Y/%m/',
        help_text="PDF/DOC/DOCX format"
    )
    cover_letter = models.FileField(
        upload_to='applications/cover_letters/%Y/%m/',
        blank=True
    )
    
    # Status & Tracking
    application_status = models.CharField(
        max_length=20, 
        choices=ApplicationStatus.choices,
        default=ApplicationStatus.SUBMITTED
    )
    application_date = models.DateTimeField(auto_now_add=True)
    
    # Educational Information
    highest_education = models.ForeignKey(
        EducationLevel, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    total_experience_years = models.DecimalField(
        max_digits=4, 
        decimal_places=1,
        default=0,
        help_text="Years of experience"
    )
    current_employer = models.CharField(max_length=200, blank=True)
    current_position = models.CharField(max_length=200, blank=True)
    current_salary = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        null=True, 
        blank=True
    )
    expected_salary = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        null=True, 
        blank=True
    )
    notice_period_days = models.PositiveIntegerField(
        default=30,
        help_text="Days of notice period"
    )
    
    # Diversity & Equal Opportunity (Optional)
    gender = models.CharField(max_length=10, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    nationality = models.CharField(max_length=100, blank=True)
    
    # Communication Preferences
    preferred_contact_method = models.CharField(
        max_length=20,
        choices=[('email', 'Email'), ('phone', 'Phone'), ('whatsapp', 'WhatsApp')],
        default='email'
    )
    
    # Consent & Legal
    consent_to_process_data = models.BooleanField(default=False)
    consent_to_store_data = models.BooleanField(default=False)
    privacy_policy_accepted = models.BooleanField(default=False)
    
    # Additional Info
    linkedin_profile = models.URLField(blank=True)
    portfolio_url = models.URLField(blank=True)
    github_profile = models.URLField(blank=True)
    
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'recruitment_job_application'
        ordering = ['-application_date']
        indexes = [
            models.Index(fields=['email', 'job_opening']),
            models.Index(fields=['application_status']),
            models.Index(fields=['application_date']),
        ]
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.job_opening.title}"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()


class ApplicationEducation(AuditedModel):
    """Educational qualifications for applications"""
    application = models.ForeignKey(
        JobApplication, 
        on_delete=models.CASCADE,
        related_name='educations'
    )
    institution = models.CharField(max_length=255)
    degree = models.CharField(max_length=200)
    field_of_study = models.CharField(max_length=200, blank=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=False)
    grade = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    
    class Meta:
        db_table = 'recruitment_application_education'
        ordering = ['-end_date']
    
    def __str__(self):
        return f"{self.application.full_name} - {self.degree}"


class ApplicationExperience(AuditedModel):
    """Work experience for applications"""
    application = models.ForeignKey(
        JobApplication, 
        on_delete=models.CASCADE,
        related_name='experiences'
    )
    company = models.CharField(max_length=255)
    position = models.CharField(max_length=200)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=False)
    responsibilities = models.TextField()
    achievements = models.TextField(blank=True)
    
    class Meta:
        db_table = 'recruitment_application_experience'
        ordering = ['-start_date']
    
    def __str__(self):
        return f"{self.application.full_name} - {self.position} at {self.company}"


class ApplicationSkill(AuditedModel):
    """Skills for applications"""
    application = models.ForeignKey(
        JobApplication, 
        on_delete=models.CASCADE,
        related_name='skills'
    )
    skill_name = models.CharField(max_length=200)
    proficiency_level = models.CharField(
        max_length=20,
        choices=[
            ('beginner', 'Beginner'),
            ('intermediate', 'Intermediate'),
            ('advanced', 'Advanced'),
            ('expert', 'Expert')
        ]
    )
    years_of_experience = models.DecimalField(max_digits=4, decimal_places=1)
    
    class Meta:
        db_table = 'recruitment_application_skill'
    
    def __str__(self):
        return f"{self.application.full_name} - {self.skill_name}"


class ApplicationCertificate(AuditedModel):
    """Certifications for applications"""
    application = models.ForeignKey(
        JobApplication, 
        on_delete=models.CASCADE,
        related_name='certifications'
    )
    certificate_name = models.CharField(max_length=255)
    issuing_organization = models.CharField(max_length=255)
    issue_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
    certificate_id = models.CharField(max_length=100, blank=True)
    certificate_url = models.URLField(blank=True)
    
    class Meta:
        db_table = 'recruitment_application_certificate'
    
    def __str__(self):
        return f"{self.application.full_name} - {self.certificate_name}"


class InterviewRound(AuditedModel):
    """Interview rounds definition"""
    
    class RoundType(models.TextChoices):
        TELEPHONIC = 'telephonic', _('Telephonic')
        VIDEO = 'video', _('Video Interview')
        TECHNICAL = 'technical', _('Technical Round')
        HR = 'hr', _('HR Round')
        PANEL = 'panel', _('Panel Interview')
        PRESENTATION = 'presentation', _('Presentation')
        ASSESSMENT = 'assessment', _('Assessment')
        FINAL = 'final', _('Final Round')
    
    job_opening = models.ForeignKey(
        JobOpening, 
        on_delete=models.CASCADE,
        related_name='interview_rounds'
    )
    round_name = models.CharField(max_length=200)
    round_type = models.CharField(max_length=20, choices=RoundType.choices)
    sequence = models.PositiveIntegerField(
        help_text="Order in which rounds should be conducted"
    )
    description = models.TextField(blank=True)
    duration_minutes = models.PositiveIntegerField(default=60)
    is_mandatory = models.BooleanField(default=True)
    passing_score = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        null=True, 
        blank=True,
        help_text="Minimum score required to pass"
    )
    
    class Meta:
        db_table = 'recruitment_interview_round'
        ordering = ['sequence']
        unique_together = ['job_opening', 'sequence']
    
    def __str__(self):
        return f"{self.job_opening.reference_number} - {self.round_name}"


class InterviewSchedule(AuditedModel):
    """Interview scheduling"""
    
    class InterviewStatus(models.TextChoices):
        SCHEDULED = 'scheduled', _('Scheduled')
        IN_PROGRESS = 'in_progress', _('In Progress')
        COMPLETED = 'completed', _('Completed')
        CANCELLED = 'cancelled', _('Cancelled')
        RESCHEDULED = 'rescheduled', _('Rescheduled')
        NO_SHOW = 'no_show', _('No Show')
    
    class InterviewMode(models.TextChoices):
        IN_PERSON = 'in_person', _('In Person')
        VIDEO = 'video', _('Video Call')
        PHONE = 'phone', _('Phone Call')
    
    application = models.ForeignKey(
        JobApplication, 
        on_delete=models.CASCADE,
        related_name='interviews'
    )
    interview_round = models.ForeignKey(
        InterviewRound, 
        on_delete=models.PROTECT
    )
    
    interview_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    
    interview_mode = models.CharField(
        max_length=20, 
        choices=InterviewMode.choices
    )
    location = models.CharField(
        max_length=500,
        blank=True,
        help_text="Physical location or video link"
    )
    
    # Interviewers
    interviewers = models.ManyToManyField(
        Employee,
        related_name='interviews_to_conduct'
    )
    primary_interviewer = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        related_name='primary_interviews'
    )
    
    status = models.CharField(
        max_length=20, 
        choices=InterviewStatus.choices,
        default=InterviewStatus.SCHEDULED
    )
    
    # Scheduling info
    scheduled_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='scheduled_interviews'
    )
    scheduled_date = models.DateTimeField(auto_now_add=True)
    
    # Communication
    candidate_notified = models.BooleanField(default=False)
    interviewers_notified = models.BooleanField(default=False)
    notification_sent_date = models.DateTimeField(null=True, blank=True)
    
    # Follow-up
    reminder_sent = models.BooleanField(default=False)
    reminder_sent_date = models.DateTimeField(null=True, blank=True)
    
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'recruitment_interview_schedule'
        ordering = ['interview_date', 'start_time']
        indexes = [
            models.Index(fields=['application', 'status']),
            models.Index(fields=['interview_date']),
        ]
    
    def __str__(self):
        return f"{self.application.full_name} - {self.interview_round.round_name}"


class InterviewEvaluation(AuditedModel):
    """Interview evaluation and feedback"""
    
    class Recommendation(models.TextChoices):
        STRONG_HIRE = 'strong_hire', _('Strong Hire')
        HIRE = 'hire', _('Hire')
        NO_HIRE = 'no_hire', _('No Hire')
        STRONG_NO_HIRE = 'strong_no_hire', _('Strong No Hire')
        NOT_SURE = 'not_sure', _('Not Sure')
    
    interview = models.OneToOneField(
        InterviewSchedule, 
        on_delete=models.CASCADE,
        related_name='evaluation'
    )
    interviewer = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='interview_evaluations'
    )
    
    # Ratings
    technical_skills_score = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(10)]
    )
    communication_skills_score = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(10)]
    )
    problem_solving_score = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(10)]
    )
    cultural_fit_score = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(10)]
    )
    
    overall_score = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(10)]
    )
    
    # Feedback
    strengths = models.TextField()
    areas_for_improvement = models.TextField()
    additional_comments = models.TextField(blank=True)
    
    recommendation = models.CharField(
        max_length=20, 
        choices=Recommendation.choices
    )
    
    # Confidential questions
    red_flags = models.TextField(
        blank=True,
        help_text="Any concerns about the candidate"
    )
    is_recommended_for_next_round = models.BooleanField(default=False)
    
    submitted_date = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'recruitment_interview_evaluation'
        ordering = ['-submitted_date']
        unique_together = ['interview', 'interviewer']
    
    def __str__(self):
        return f"{self.interview.application.full_name} - {self.interviewer.employee_no}"


class AssessmentTest(AuditedModel):
    """Assessment tests for candidates"""
    
    class TestType(models.TextChoices):
        APTITUDE = 'aptitude', _('Aptitude Test')
        TECHNICAL = 'technical', _('Technical Test')
        PSYCHOMETRIC = 'psychometric', _('Psychometric Test')
        LANGUAGE = 'language', _('Language Test')
        CODING = 'coding', _('Coding Test')
        CASE_STUDY = 'case_study', _('Case Study')
    
    class TestStatus(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        ACTIVE = 'active', _('Active')
        INACTIVE = 'inactive', _('Inactive')
    
    job_opening = models.ForeignKey(
        JobOpening, 
        on_delete=models.CASCADE,
        related_name='assessment_tests'
    )
    test_name = models.CharField(max_length=200)
    test_type = models.CharField(max_length=20, choices=TestType.choices)
    description = models.TextField(blank=True)
    
    duration_minutes = models.PositiveIntegerField()
    total_questions = models.PositiveIntegerField()
    passing_score = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        help_text="Percentage score required to pass"
    )
    
    test_link = models.URLField(blank=True)
    test_platform = models.CharField(max_length=100, blank=True)
    
    status = models.CharField(
        max_length=20, 
        choices=TestStatus.choices,
        default=TestStatus.DRAFT
    )
    
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='created_assessment_tests'
    )
    
    class Meta:
        db_table = 'recruitment_assessment_test'
        ordering = ['test_name']
    
    def __str__(self):
        return f"{self.test_name} - {self.job_opening.reference_number}"


class CandidateAssessment(AuditedModel):
    """Candidate assessment results"""
    
    class AssessmentStatus(models.TextChoices):
        NOT_SENT = 'not_sent', _('Not Sent')
        SENT = 'sent', _('Sent')
        IN_PROGRESS = 'in_progress', _('In Progress')
        COMPLETED = 'completed', _('Completed')
        EXPIRED = 'expired', _('Expired')
        CANCELLED = 'cancelled', _('Cancelled')
    
    application = models.ForeignKey(
        JobApplication, 
        on_delete=models.CASCADE,
        related_name='assessments'
    )
    assessment_test = models.ForeignKey(
        AssessmentTest, 
        on_delete=models.PROTECT
    )
    
    status = models.CharField(
        max_length=20, 
        choices=AssessmentStatus.choices,
        default=AssessmentStatus.NOT_SENT
    )
    
    # Test administration
    invitation_sent_date = models.DateTimeField(null=True, blank=True)
    invitation_expiry_date = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Results
    score = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        null=True, 
        blank=True
    )
    percentage_score = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        null=True, 
        blank=True
    )
    is_passed = models.BooleanField(default=False)
    
    # Detailed results
    detailed_results = models.JSONField(
        null=True, 
        blank=True,
        help_text="Section-wise scores and answers"
    )
    result_summary = models.TextField(blank=True)
    
    # Proctoring data
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    completion_time_seconds = models.PositiveIntegerField(null=True, blank=True)
    
    class Meta:
        db_table = 'recruitment_candidate_assessment'
        unique_together = ['application', 'assessment_test']
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.application.full_name} - {self.assessment_test.test_name}"


class OfferLetter(AuditedModel):
    """Job offer letters"""
    
    class OfferStatus(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        PENDING_APPROVAL = 'pending_approval', _('Pending Approval')
        APPROVED = 'approved', _('Approved')
        SENT = 'sent', _('Sent')
        ACCEPTED = 'accepted', _('Accepted')
        DECLINED = 'declined', _('Declined')
        EXPIRED = 'expired', _('Expired')
        WITHDRAWN = 'withdrawn', _('Withdrawn')
    
    application = models.OneToOneField(
        JobApplication, 
        on_delete=models.CASCADE,
        related_name='offer_letter'
    )
    job_opening = models.ForeignKey(
        JobOpening, 
        on_delete=models.PROTECT
    )
    
    offer_reference = models.CharField(max_length=100, unique=True)
    offer_date = models.DateField()
    joining_date = models.DateField()
    probation_period_months = models.PositiveIntegerField(default=3)
    
    # Compensation
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2)
    allowances = models.JSONField(
        default=list,
        help_text="List of allowances with amounts"
    )
    total_ctc = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    
    # Benefits
    benefits = models.TextField()
    working_hours = models.CharField(max_length=100, default='9:00 AM - 5:00 PM')
    work_location = models.CharField(max_length=500)
    
    # Approval workflow
    prepared_by = models.ForeignKey(
        Employee, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='offers_prepared'
    )
    approved_by = models.ForeignKey(
        Employee, 
        on_delete=models.SET_NULL, 
        null=True,
        blank=True,
        related_name='offers_approved'
    )
    
    status = models.CharField(
        max_length=20, 
        choices=OfferStatus.choices,
        default=OfferStatus.DRAFT
    )
    
    # Communication
    sent_date = models.DateTimeField(null=True, blank=True)
    sent_via = models.CharField(
        max_length=20,
        choices=[('email', 'Email'), ('portal', 'Portal'), ('both', 'Both')],
        blank=True
    )
    
    candidate_response_date = models.DateTimeField(null=True, blank=True)
    candidate_response_notes = models.TextField(blank=True)
    
    # Document
    offer_letter_file = models.FileField(
        upload_to='offer_letters/%Y/%m/',
        blank=True
    )
    
    terms_and_conditions = models.TextField()
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'recruitment_offer_letter'
        ordering = ['-offer_date']
        indexes = [
            models.Index(fields=['offer_reference']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.offer_reference} - {self.application.full_name}"


class BackgroundCheck(AuditedModel):
    """Background verification"""
    
    class CheckType(models.TextChoices):
        EMPLOYMENT = 'employment', _('Employment History')
        EDUCATION = 'education', _('Education Verification')
        CRIMINAL = 'criminal', _('Criminal Record')
        REFERENCE = 'reference', _('Reference Check')
        CREDIT = 'credit', _('Credit Check')
        IDENTITY = 'identity', _('Identity Verification')
    
    class CheckStatus(models.TextChoices):
        PENDING = 'pending', _('Pending')
        IN_PROGRESS = 'in_progress', _('In Progress')
        CLEARED = 'cleared', _('Cleared')
        ISSUE_FOUND = 'issue_found', _('Issue Found')
        CANCELLED = 'cancelled', _('Cancelled')
    
    application = models.ForeignKey(
        JobApplication, 
        on_delete=models.CASCADE,
        related_name='background_checks'
    )
    check_type = models.CharField(max_length=20, choices=CheckType.choices)
    
    initiated_date = models.DateField()
    completed_date = models.DateField(null=True, blank=True)
    
    status = models.CharField(
        max_length=20, 
        choices=CheckStatus.choices,
        default=CheckStatus.PENDING
    )
    
    # Verification agency
    verification_agency = models.CharField(max_length=200, blank=True)
    agency_contact = models.CharField(max_length=200, blank=True)
    agency_report_id = models.CharField(max_length=100, blank=True)
    
    # Results
    is_clear = models.BooleanField(default=False)
    findings = models.TextField(blank=True)
    risk_level = models.CharField(
        max_length=20,
        choices=[
            ('low', 'Low Risk'),
            ('medium', 'Medium Risk'),
            ('high', 'High Risk')
        ],
        blank=True
    )
    
    # Documents
    report_file = models.FileField(
        upload_to='background_checks/%Y/%m/',
        blank=True
    )
    supporting_documents = models.JSONField(
        blank=True, 
        null=True,
        help_text="List of document URLs"
    )
    
    reviewed_by = models.ForeignKey(
        Employee, 
        on_delete=models.SET_NULL, 
        null=True,
        blank=True,
        related_name='background_checks_reviewed'
    )
    review_date = models.DateField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'recruitment_background_check'
        ordering = ['initiated_date']
    
    def __str__(self):
        return f"{self.application.full_name} - {self.get_check_type_display()}"


class ReferenceCheck(AuditedModel):
    """Reference checks"""
    
    class ReferenceType(models.TextChoices):
        PROFESSIONAL = 'professional', _('Professional')
        ACADEMIC = 'academic', _('Academic')
        PERSONAL = 'personal', _('Personal')
    
    class Rating(models.TextChoices):
        EXCELLENT = 'excellent', _('Excellent')
        GOOD = 'good', _('Good')
        AVERAGE = 'average', _('Average')
        POOR = 'poor', _('Poor')
        VERY_POOR = 'very_poor', _('Very Poor')
    
    application = models.ForeignKey(
        JobApplication, 
        on_delete=models.CASCADE,
        related_name='reference_checks'
    )
    
    # Reference details
    reference_name = models.CharField(max_length=200)
    reference_position = models.CharField(max_length=200)
    reference_organization = models.CharField(max_length=200)
    reference_email = models.EmailField()
    reference_phone = models.CharField(max_length=20)
    reference_type = models.CharField(
        max_length=20, 
        choices=ReferenceType.choices
    )
    relationship = models.CharField(
        max_length=200,
        help_text="e.g., Former Manager, Professor"
    )
    
    # Contact details
    contact_date = models.DateField(null=True, blank=True)
    contact_method = models.CharField(
        max_length=20,
        choices=[('email', 'Email'), ('phone', 'Phone'), ('in_person', 'In Person')],
        blank=True
    )
    
    # Ratings
    work_ethics_rating = models.CharField(
        max_length=20, 
        choices=Rating.choices,
        blank=True
    )
    skills_rating = models.CharField(
        max_length=20, 
        choices=Rating.choices,
        blank=True
    )
    reliability_rating = models.CharField(
        max_length=20, 
        choices=Rating.choices,
        blank=True
    )
    teamwork_rating = models.CharField(
        max_length=20, 
        choices=Rating.choices,
        blank=True
    )
    overall_rating = models.CharField(
        max_length=20, 
        choices=Rating.choices,
        blank=True
    )
    
    # Feedback
    strengths = models.TextField(blank=True)
    areas_for_improvement = models.TextField(blank=True)
    would_you_rehire = models.BooleanField(null=True, blank=True)
    additional_comments = models.TextField(blank=True)
    
    # Verification
    is_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    class Meta:
        db_table = 'recruitment_reference_check'
    
    def __str__(self):
        return f"{self.application.full_name} - {self.reference_name}"


class RecruitmentWorkflow(AuditedModel):
    """Recruitment workflow stages"""
    job_opening = models.ForeignKey(
        JobOpening, 
        on_delete=models.CASCADE,
        related_name='workflow_stages'
    )
    stage_name = models.CharField(max_length=200)
    stage_order = models.PositiveIntegerField()
    is_mandatory = models.BooleanField(default=True)
    expected_duration_days = models.PositiveIntegerField(
        default=7,
        help_text="Expected time to complete this stage"
    )
    required_approvals = models.JSONField(
        blank=True, 
        null=True,
        help_text="List of roles required for approval"
    )
    
    class Meta:
        db_table = 'recruitment_workflow'
        ordering = ['stage_order']
        unique_together = ['job_opening', 'stage_order']
    
    def __str__(self):
        return f"{self.job_opening.reference_number} - {self.stage_name}"


class ApplicationWorkflow(AuditedModel):
    """Application progress through workflow"""
    
    class StageStatus(models.TextChoices):
        NOT_STARTED = 'not_started', _('Not Started')
        IN_PROGRESS = 'in_progress', _('In Progress')
        COMPLETED = 'completed', _('Completed')
        ON_HOLD = 'on_hold', _('On Hold')
        CANCELLED = 'cancelled', _('Cancelled')
    
    application = models.ForeignKey(
        JobApplication, 
        on_delete=models.CASCADE,
        related_name='workflow_progress'
    )
    workflow_stage = models.ForeignKey(
        RecruitmentWorkflow, 
        on_delete=models.CASCADE
    )
    
    status = models.CharField(
        max_length=20, 
        choices=StageStatus.choices,
        default=StageStatus.NOT_STARTED
    )
    
    started_date = models.DateTimeField(null=True, blank=True)
    completed_date = models.DateTimeField(null=True, blank=True)
    
    assigned_to = models.ForeignKey(
        Employee, 
        on_delete=models.SET_NULL, 
        null=True,
        blank=True,
        related_name='assigned_recruitment_tasks'
    )
    
    notes = models.TextField(blank=True)
    next_action = models.TextField(blank=True)
    
    class Meta:
        db_table = 'recruitment_application_workflow'
        ordering = ['workflow_stage__stage_order']
        unique_together = ['application', 'workflow_stage']
    
    def __str__(self):
        return f"{self.application.full_name} - {self.workflow_stage.stage_name}"


class RecruitmentAnalytics(AuditedModel):
    """Recruitment analytics and metrics"""
    job_opening = models.ForeignKey(
        JobOpening, 
        on_delete=models.CASCADE,
        related_name='analytics'
    )
    metric_date = models.DateField()
    
    # Application metrics
    total_applications = models.PositiveIntegerField(default=0)
    new_applications = models.PositiveIntegerField(default=0)
    applications_screened = models.PositiveIntegerField(default=0)
    applications_shortlisted = models.PositiveIntegerField(default=0)
    applications_rejected = models.PositiveIntegerField(default=0)
    
    # Interview metrics
    interviews_scheduled = models.PositiveIntegerField(default=0)
    interviews_completed = models.PositiveIntegerField(default=0)
    interview_no_shows = models.PositiveIntegerField(default=0)
    
    # Offer metrics
    offers_made = models.PositiveIntegerField(default=0)
    offers_accepted = models.PositiveIntegerField(default=0)
    offers_declined = models.PositiveIntegerField(default=0)
    
    # Time metrics
    avg_time_to_screen = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        default=0
    )
    avg_time_to_hire = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        default=0
    )
    
    # Source metrics
    source_breakdown = models.JSONField(
        blank=True, 
        null=True,
        help_text="Applications by source"
    )
    
    # Cost metrics
    recruitment_cost = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        default=0
    )
    cost_per_hire = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        default=0
    )
    
    class Meta:
        db_table = 'recruitment_analytics'
        ordering = ['-metric_date']
        unique_together = ['job_opening', 'metric_date']
    
    def __str__(self):
        return f"{self.job_opening.reference_number} - {self.metric_date}"


class RecruitmentEmailTemplate(AuditedModel):
    """Email templates for recruitment communication"""
    
    class TemplateType(models.TextChoices):
        APPLICATION_ACKNOWLEDGEMENT = 'application_ack', _('Application Acknowledgement')
        INTERVIEW_INVITATION = 'interview_invite', _('Interview Invitation')
        OFFER_LETTER = 'offer_letter', _('Offer Letter')
        REJECTION = 'rejection', _('Rejection')
        BACKGROUND_CHECK = 'background_check', _('Background Check Request')
        WELCOME = 'welcome', _('Welcome Email')
        ASSESSMENT_INVITE = 'assessment_invite', _('Assessment Invitation')
    
    template_name = models.CharField(max_length=200)
    template_type = models.CharField(max_length=30, choices=TemplateType.choices)
    subject = models.CharField(max_length=200)
    body = models.TextField()
    is_active = models.BooleanField(default=True)
    variables = models.JSONField(
        blank=True, 
        null=True,
        help_text="Available template variables"
    )
    
    class Meta:
        db_table = 'recruitment_email_template'
        ordering = ['template_name']
    
    def __str__(self):
        return self.template_name


class RecruitmentCommunication(AuditedModel):
    """Communication history with candidates"""
    
    class CommunicationType(models.TextChoices):
        EMAIL = 'email', _('Email')
        SMS = 'sms', _('SMS')
        PHONE = 'phone', _('Phone Call')
        WHATSAPP = 'whatsapp', _('WhatsApp')
        PORTAL = 'portal', _('Portal Message')
    
    class Direction(models.TextChoices):
        SENT = 'sent', _('Sent')
        RECEIVED = 'received', _('Received')
    
    application = models.ForeignKey(
        JobApplication, 
        on_delete=models.CASCADE,
        related_name='communications'
    )
    communication_type = models.CharField(
        max_length=20, 
        choices=CommunicationType.choices
    )
    direction = models.CharField(max_length=10, choices=Direction.choices)
    
    subject = models.CharField(max_length=500, blank=True)
    message = models.TextField()
    
    sent_to = models.CharField(max_length=500)
    sent_from = models.CharField(max_length=500)
    
    sent_date = models.DateTimeField(auto_now_add=True)
    read_receipt = models.BooleanField(default=False)
    read_date = models.DateTimeField(null=True, blank=True)
    
    template_used = models.ForeignKey(
        RecruitmentEmailTemplate, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    attachments = models.JSONField(
        blank=True, 
        null=True,
        help_text="List of attachment file paths"
    )
    
    class Meta:
        db_table = 'recruitment_communication'
        ordering = ['-sent_date']
    
    def __str__(self):
        return f"{self.application.full_name} - {self.subject}"


# ============================================================================
# NEW WORKFLOW MODELS (STAGES 5-9)
# ============================================================================

class ComplianceChecklist(AuditedModel):
    """Stage 5: Compliance Checklist"""
    application = models.OneToOneField(
        JobApplication, 
        on_delete=models.CASCADE, 
        related_name='compliance_checklist'
    )
    
    # Checklist Items
    certificates_verified = models.BooleanField(default=False)
    teaching_license_verified = models.BooleanField(default=False)
    references_checked = models.BooleanField(default=False)
    criminal_clearance_verified = models.BooleanField(default=False)
    medical_clearance_verified = models.BooleanField(default=False)
    
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'recruitment_compliance_checklist'
        
    def __str__(self):
        return f"Compliance - {self.application.full_name}"


class SelectionDecision(AuditedModel):
    """Stage 6: Final Selection Decision"""
    class Decision(models.TextChoices):
        SELECTED = 'selected', _('Selected')
        WAITLISTED = 'waitlisted', _('Waitlisted')
        NOT_SELECTED = 'not_selected', _('Not Selected')

    application = models.OneToOneField(
        JobApplication, 
        on_delete=models.CASCADE, 
        related_name='selection_decision'
    )
    decision = models.CharField(max_length=20, choices=Decision.choices)
    
    # Approvals
    hr_approved = models.BooleanField(default=False)
    hr_approver = models.ForeignKey(
        Employee, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='selections_hr_approved',
        blank=True
    )
    hr_approval_date = models.DateTimeField(null=True, blank=True)
    
    principal_approved = models.BooleanField(default=False)
    principal_approver = models.ForeignKey(
        Employee, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='selections_principal_approved',
        blank=True
    )
    principal_approval_date = models.DateTimeField(null=True, blank=True)
    
    remarks = models.TextField(blank=True)
    
    class Meta:
        db_table = 'recruitment_selection_decision'
        
    def __str__(self):
        return f"Selection - {self.application.full_name}"


class OnboardingProcess(AuditedModel):
    """Stage 8: Onboarding Process"""
    application = models.OneToOneField(
        JobApplication, 
        on_delete=models.CASCADE, 
        related_name='onboarding_process'
    )
    # Link to the employee record once created
    employee_profile = models.OneToOneField(
        Employee, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='onboarding_process_record'
    )
    
    # Checklist
    profile_created = models.BooleanField(default=False)
    system_access_granted = models.BooleanField(default=False)
    department_assigned = models.BooleanField(default=False)
    timetable_assigned = models.BooleanField(default=False)
    documents_submitted = models.BooleanField(default=False)
    
    progress_percentage = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    is_completed = models.BooleanField(default=False)
    completion_date = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'recruitment_onboarding_process'
        
    def __str__(self):
        return f"Onboarding - {self.application.full_name}"


class ProbationReview(AuditedModel):
    """Stage 9: Probation Review"""
    class Status(models.TextChoices):
        ACTIVE = 'active', _('Active')
        CONFIRMED = 'confirmed', _('Confirmed')
        EXTENDED = 'extended', _('Extended')
        TERMINATED = 'terminated', _('Terminated')

    # Link to Employee (as they are now hired)
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE, 
        related_name='probation_reviews'
    )
    start_date = models.DateField()
    review_date = models.DateField()
    
    status = models.CharField(
        max_length=20, 
        choices=Status.choices, 
        default=Status.ACTIVE
    )
    performance_rating = models.PositiveIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(5)], 
        default=0
    )
    remarks = models.TextField(blank=True)
    
    class Meta:
        db_table = 'recruitment_probation_review'
        ordering = ['-review_date']
        
    def __str__(self):
        return f"Probation - {self.employee.full_name}"