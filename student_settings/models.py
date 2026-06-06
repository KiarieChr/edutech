from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name="%(class)s_created"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name="%(class)s_updated"
    )
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save()

class AcademicYear(BaseModel):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('archived', 'Archived'),
    )
    name = models.CharField(max_length=50, unique=True)  # e.g., 2025, 2025/2026
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    description = models.TextField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if self.is_current:
            AcademicYear.objects.filter(is_current=True).exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['-start_date']
        db_table = 'academic_years'

class Intake(BaseModel):
    """Represents a cohort of students admitted in a specific academic year"""
    
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name='intakes',
        help_text='Academic year for this intake cohort'
    )
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text='e.g., "2024 Intake", "Class of 2024"'
    )
    code = models.CharField(
        max_length=20,
        unique=True,
        help_text='Short code, e.g., "INT2024"'
    )
    start_date = models.DateField(
        help_text='When this intake cohort started'
    )
    expected_graduation_date = models.DateField(
        null=True,
        blank=True,
        help_text='Expected graduation date for this cohort'
    )
    
    # Entry Configuration
    entry_curriculum = models.ForeignKey(
        'Curriculum',
        on_delete=models.PROTECT,
        related_name='intakes',
        null=True,
        blank=True
    )
    entry_level = models.ForeignKey(
        'CurriculumLevel',
        on_delete=models.PROTECT,
        related_name='intakes',
        null=True,
        blank=True
    )
    entry_grade = models.ForeignKey(
        'GradeStructure',
        on_delete=models.PROTECT,
        related_name='intakes',
        null=True,
        blank=True,
        help_text='Specific grade level for entry (e.g., Grade 1)'
    )
    
    ADMISSION_TYPES = (
        ('regular', 'Regular'),
        ('transfer', 'Transfer'),
        ('re_entry', 'Re-entry'),
    )
    admission_type = models.CharField(
        max_length=20,
        choices=ADMISSION_TYPES,
        default='regular'
    )
    
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(
        default=True,
        help_text='Whether this intake is currently accepting students'
    )
    
    STATUS_CHOICES = (
        ('open', 'Open'),
        ('closed', 'Closed'),
        ('archived', 'Archived'),
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    
    class Meta:
        ordering = ['-academic_year__start_date', '-start_date']
        verbose_name = 'Intake'
        verbose_name_plural = 'Intakes'
        db_table = 'intakes'
    def __str__(self):
        return self.name
    
    @property
    def student_count(self):
        """Count of students in this intake"""
        return self.students.count()
    
    @property
    def year_name(self):
        """Get academic year name"""
        return self.academic_year.name if self.academic_year else None

    @property
    def current_expected_stage(self):
        """
        Dynamically calculates the expected stage/grade and term/semester 
        for this cohort based on the current date and curriculum structure.
        """
        if not self.start_date:
            return "N/A"
            
        today = timezone.now().date()
        if today < self.start_date:
            return "Scheduled"
            
        if self.expected_graduation_date and today > self.expected_graduation_date:
            return "Completed / Graduated"
            
        # Determine expected grade level based on years elapsed
        elapsed_years = today.year - self.start_date.year
        
        # Start from entry grade if defined, otherwise the first grade in curriculum
        grades = []
        if self.entry_curriculum:
            grades = list(self.entry_curriculum.grades.all().order_by('level_order'))
            
        if not grades:
            return "Active"
            
        start_idx = 0
        if self.entry_grade and self.entry_grade in grades:
            try:
                start_idx = grades.index(self.entry_grade)
            except ValueError:
                start_idx = 0
            
        expected_grade_idx = min(start_idx + elapsed_years, len(grades) - 1)
        expected_grade = grades[expected_grade_idx]
        
        # Get active term/semester if any
        current_term = Term.objects.filter(is_current=True).first()
        if current_term:
            return f"{expected_grade.name} ({current_term.name})"
            
        return expected_grade.name


class Term(BaseModel):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('closed', 'Closed'),
    )
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="terms")
    name = models.CharField(max_length=50)  # Term 1, Semester 1
    order = models.PositiveIntegerField()
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')

    def save(self, *args, **kwargs):
        if self.is_current:
            Term.objects.filter(academic_year=self.academic_year, is_current=True).exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.academic_year.name})"
    
    class Meta:
        ordering = ['academic_year__start_date', 'order']
        unique_together = ['academic_year', 'order']
        db_table = 'terms'

class Curriculum(BaseModel):
   
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('phased_out', 'Phased Out'),
    )
    name = models.CharField(max_length=100)  # 8-4-4, CBC, IGCSE
    code = models.CharField(max_length=20, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']
        db_table = 'curriculums'

class CurriculumLevel(BaseModel):
    """Represents a stage within a curriculum (e.g. Primary, JSS, Senior Secondary)"""
    curriculum = models.ForeignKey(Curriculum, on_delete=models.CASCADE, related_name="levels")
    name = models.CharField(max_length=100) # Primary, JSS, Senior Secondary
    order = models.PositiveIntegerField(help_text="Order in the curriculum progression")
    min_years = models.PositiveIntegerField(null=True, blank=True, help_text="Minimum years to complete this level")
    max_years = models.PositiveIntegerField(null=True, blank=True, help_text="Maximum years allowed for this level")
    
    class Meta:
        ordering = ['curriculum', 'order']
        unique_together = ['curriculum', 'name']
        db_table = 'curriculum_levels'

    def __str__(self):
        return f"{self.curriculum.code} - {self.name}"


class LearningArea(BaseModel):
    """Groups subjects into broader categories (Sciences, Languages, Humanities, etc.)"""
    CATEGORY_CHOICES = (
        ('sciences', 'Sciences'),
        ('languages', 'Languages'),
        ('humanities', 'Humanities'),
        ('technical', 'Technical/Vocational'),
        ('arts', 'Creative Arts'),
        ('pe', 'Physical Education'),
        ('other', 'Other'),
    )
    
    name = models.CharField(max_length=100, unique=True)  # e.g., Sciences, Languages
    code = models.CharField(max_length=20, blank=True, null=True)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default='other')
    description = models.TextField(blank=True, null=True)
    color_hex = models.CharField(max_length=7, default='#6366f1', help_text="UI color")
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0, help_text="Display order")

    class Meta:
        ordering = ['order', 'name']
        verbose_name = 'Learning Area'
        verbose_name_plural = 'Learning Areas'
        db_table = 'learning_areas'

    def __str__(self):
        return self.name


class GradeStructure(BaseModel):
    curriculum = models.ForeignKey(Curriculum, on_delete=models.CASCADE, related_name="grades")
    curriculum_level = models.ForeignKey(
        CurriculumLevel, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name="grades"
    )
    name = models.CharField(max_length=50)  # Grade 6, Form 3, Year 10
    code = models.CharField(max_length=20, blank=True, null=True)
    level_order = models.PositiveIntegerField()
    age_range = models.CharField(max_length=50, blank=True, null=True)
    credits_required = models.PositiveIntegerField(
        default=0,
        help_text='Total course credits required to complete this stage (for higher education)'
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['level_order']
        db_table = 'grade_structures'

    def __str__(self):
        return f"{self.name} ({self.curriculum.name})"

class Stream(BaseModel):
    grade = models.ForeignKey(GradeStructure, on_delete=models.CASCADE, related_name="streams")
    name = models.CharField(max_length=50)  # A, B, North
    capacity = models.PositiveIntegerField(null=True, blank=True)
    class_teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name="managed_streams"
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.grade.name} - {self.name}"
    
    class Meta:
        ordering = ['grade__level_order', 'name']
        unique_together = ['grade', 'name']
        db_table = 'streams'

class AdmissionConfig(BaseModel):
    ADMISSION_FORMAT_CHOICES = (
        ('auto', 'Auto-generated'),
        ('manual', 'Manual'),
    )
    YEAR_FORMAT_CHOICES = (
        ('YYYY', 'Full Year (e.g. 2026)'),
        ('YY', 'Last 2 Digits (e.g. 26)'),
    )
    SEQUENCE_CHOICES = (
        ('P-Y-S', 'Prefix - Year - Serial'),
        ('P-S-Y', 'Prefix - Serial - Year'),
        ('Y-P-S', 'Year - Prefix - Serial'),
        ('P-S', 'Prefix - Serial'),  # Fallback if no year
    )

    admission_format = models.CharField(max_length=10, choices=ADMISSION_FORMAT_CHOICES, default='auto')
    prefix = models.CharField(max_length=20, default='SCH')
    separator = models.CharField(max_length=5, default='/', blank=True)
    
    # Year Configuration
    include_year = models.BooleanField(default=True)
    year_format = models.CharField(max_length=4, choices=YEAR_FORMAT_CHOICES, default='YYYY')
    
    # Sequence
    sequence_format = models.CharField(max_length=10, choices=SEQUENCE_CHOICES, default='P-Y-S')
    
    enforce_unique = models.BooleanField(default=True)
    default_status = models.CharField(max_length=20, default='Active')
    allow_mid_term = models.BooleanField(default=True)
    require_application = models.BooleanField(
        default=True,
        help_text='If True, students must have an approved Application before being admitted. '
                  'Excel bulk import bypasses this requirement.'
    )
    default_curriculum = models.ForeignKey(Curriculum, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = 'admission_configs'

    def __str__(self):
        return "Global Admission Settings"

class AdmissionWorkflowConfig(BaseModel):
    """
    Singleton — controls which stages are active in the school's admission pipeline.
    Read alongside AdmissionConfig. All stages default to OFF so existing schools
    are unaffected. Set require_application=True on AdmissionConfig to enforce the
    Application stage; use this model for the surrounding workflow stages.
    """

    # ── Stage Toggles ──────────────────────────────────────────────────────────
    require_enquiry = models.BooleanField(
        default=False,
        help_text='If True, an Enquiry record must exist and be converted before an Application can be created.'
    )
    require_application_fee = models.BooleanField(
        default=False,
        help_text='If True, a registration/application fee must be paid (or waived) before the application can proceed.'
    )
    require_interview = models.BooleanField(
        default=False,
        help_text='If True, an Interview must be scheduled and passed before admission.'
    )
    require_reporting = models.BooleanField(
        default=False,
        help_text='If True, a Reporting record (student physically arrives with documents) must be marked before formal admission.'
    )

    # ── Application Fee Settings ────────────────────────────────────────────────
    application_fee_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Amount charged as the application/registration fee.'
    )
    application_fee_label = models.CharField(
        max_length=100, default='Application Registration Fee',
        help_text='Label shown on receipts and the frontend.'
    )
    application_fee_currency = models.CharField(
        max_length=10, default='KES', blank=True,
        help_text='Currency code, e.g. KES, USD.'
    )

    # ── Interview Settings ──────────────────────────────────────────────────────
    interview_label = models.CharField(
        max_length=100, default='Interview',
        help_text='Label shown in the UI, e.g. "Entrance Interview", "Assessment Day".'
    )
    allow_self_schedule = models.BooleanField(
        default=False,
        help_text='If True, applicants can pick their own interview slot from available slots.'
    )

    # ── Reporting / Document Submission Settings ────────────────────────────────
    reporting_label = models.CharField(
        max_length=100, default='Reporting & Document Submission',
        help_text='Label shown in the UI for the reporting stage.'
    )
    document_checklist = models.JSONField(
        default=list, blank=True,
        help_text=(
            'List of required documents as strings, e.g. '
            '["Birth Certificate", "Passport Photo", "Previous Report Card"]. '
            'Displayed as a checklist on the reporting form.'
        )
    )

    class Meta:
        db_table = 'admission_workflow_configs'
        verbose_name = 'Admission Workflow Configuration'

    def __str__(self):
        return 'Admission Workflow Configuration'

    def save(self, *args, **kwargs):
        # Enforce singleton — always use pk=1
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_instance(cls):
        """Return the singleton, creating defaults if needed."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def active_stages(self):
        """Returns an ordered list of the stages that are currently enabled."""
        stages = ['application']  # always present
        if self.require_enquiry:
            stages.insert(0, 'enquiry')
        if self.require_application_fee:
            stages.append('fee_payment')
        if self.require_interview:
            stages.append('interview')
        if self.require_reporting:
            stages.append('reporting')
        stages.append('admission')
        return stages


class StudentStatus(BaseModel):

    name = models.CharField(max_length=50, unique=True)  # Active, Alumni, Transferred
    is_active_state = models.BooleanField(default=True)  # Does this status allow class assignment?
    is_enabled = models.BooleanField(default=True)

    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['name']
        db_table = 'student_statuses'

class PromotionRule(BaseModel):
    METHOD_CHOICES = (
        ('manual', 'Manual'),
        ('automatic', 'Automatic'),
    )
    promotion_method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='manual')
    allow_mid_year = models.BooleanField(default=False)
    promote_by_order = models.BooleanField(default=True)  # True for Class Order, False for Curriculum Track

    def __str__(self):
        return "Promotion & Progression rules"
    
    class Meta:
        db_table = 'promotion_rules'

class DemographicConfig(BaseModel):
    field_name = models.CharField(max_length=100)
    is_required = models.BooleanField(default=True)
    is_enabled = models.BooleanField(default=True)

    def __str__(self):
        return self.field_name

    class Meta:
        db_table = 'demographic_configs'

class SchoolCalendar(BaseModel):
    EVENT_TYPE_CHOICES = (
        ('holiday', 'Holiday'),
        ('exam', 'Exam Period'),
        ('open_day', 'Open Day'),
        ('sports', 'Sports'),
        ('other', 'Other'),
    )
    event_name = models.CharField(max_length=200)
    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    
    # Applicability
    all_students = models.BooleanField(default=True)
    curriculum = models.ForeignKey(Curriculum, on_delete=models.SET_NULL, null=True, blank=True)
    grade = models.ForeignKey(GradeStructure, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return self.event_name
    
    class Meta:
        ordering = ['start_date']
        db_table = 'school_calendars'


class Enrollment(BaseModel):
    """
    Tracks student enrollment and progression history.
    Each enrollment represents a student's placement at a specific point in time.
    """
    
    # Status Choices
    class EnrollmentStatus(models.TextChoices):
        ACTIVE = 'active', 'Active'
        PROMOTED = 'promoted', 'Promoted'
        REPEATED = 'repeated', 'Repeated'
        TRANSFERRED_OUT = 'transferred_out', 'Transferred Out'
        COMPLETED = 'completed', 'Completed'
        WITHDRAWN = 'withdrawn', 'Withdrawn'
    
    # Enrollment Type Choices
    class EnrollmentType(models.TextChoices):
        NEW_ADMISSION = 'new_admission', 'New Admission'
        PROMOTION = 'promotion', 'Promotion'
        REPEAT = 'repeat', 'Repeat'
        TRANSFER_IN = 'transfer_in', 'Transfer In'
        CURRICULUM_CHANGE = 'curriculum_change', 'Curriculum Change'
    
    # Core Fields
    student = models.ForeignKey(
        'accounts.Student',
        on_delete=models.CASCADE,
        related_name='enrollments'
    )
    intake = models.ForeignKey(
        Intake,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='student_enrollments',
        help_text='Intake cohort the student belongs to'
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name='enrollments'
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.PROTECT,
        related_name='enrollments'
    )
    curriculum = models.ForeignKey(
        Curriculum,
        on_delete=models.PROTECT,
        related_name='enrollments'
    )
    curriculum_level = models.ForeignKey(
        CurriculumLevel,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='enrollments',
        help_text='Level within curriculum (e.g. Primary, JSS, Senior Secondary)'
    )
    grade = models.ForeignKey(
        GradeStructure,
        on_delete=models.PROTECT,
        related_name='enrollments',
        help_text='Class/Grade level'
    )
    stream = models.ForeignKey(
        Stream,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='enrollments',
        help_text='Section/Stream within the class'
    )
    campus = models.ForeignKey(
        'workforce.Campus',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='campus_enrollments',
        help_text='Campus for this enrollment'
    )
    
    # Status and Type
    status = models.CharField(
        max_length=20,
        choices=EnrollmentStatus.choices,
        default=EnrollmentStatus.ACTIVE
    )
    enrollment_type = models.CharField(
        max_length=20,
        choices=EnrollmentType.choices,
        default=EnrollmentType.NEW_ADMISSION
    )
    
    # Progression Tracking
    previous_enrollment = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='next_enrollments',
        help_text='Links to previous enrollment for progression tracking'
    )
    
    # Dates
    enrollment_date = models.DateField(
        help_text='Date when student was enrolled'
    )
    exit_date = models.DateField(
        null=True,
        blank=True,
        help_text='Date when enrollment ended'
    )
    
    # Additional Information
    remarks = models.TextField(
        blank=True,
        null=True,
        help_text='Reason for enrollment, transfer, or any special notes'
    )
    
    STAY_STATUS_CHOICES = (
        ('day_scholar', 'Day Scholar'),
        ('boarder', 'Boarder'),
    )
    stay_status = models.CharField(
        max_length=20,
        choices=STAY_STATUS_CHOICES,
        default='day_scholar',
        null=True,
        blank=True,
        help_text="Student's residential status for this term"
    )
    
    reporting_reason = models.CharField(
        max_length=100,
        null=True, 
        blank=True,
        help_text="Reason for reporting (e.g., 'Opening Day', 'Late Reporting')"
    )
    
    # Active Status
    is_active = models.BooleanField(
        default=True,
        help_text='Only one active enrollment per student per term'
    )
    
    class Meta:
        ordering = ['-enrollment_date', '-created_at']
        indexes = [
            models.Index(fields=['student', 'academic_year', 'term']),
            models.Index(fields=['status', 'is_active']),
            models.Index(fields=['enrollment_date']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'academic_year', 'term'],
                condition=models.Q(is_active=True, is_deleted=False),
                name='unique_active_enrollment_per_term'
            )
        ]
        
    
    def __str__(self):
        return f"{self.student} - {self.grade.name} ({self.academic_year.name} {self.term.name})"
    
    def clean(self):
        """Validate enrollment data"""
        super().clean()
        
        # Validate exit date is after enrollment date
        if self.exit_date and self.enrollment_date:
            if self.exit_date < self.enrollment_date:
                raise ValidationError({
                    'exit_date': 'Exit date must be on or after enrollment date.'
                })
        
        # Validate term belongs to academic year
        if self.term and self.academic_year:
            if self.term.academic_year != self.academic_year:
                raise ValidationError({
                    'term': f'Term {self.term.name} does not belong to academic year {self.academic_year.name}.'
                })
        
        # Validate stream belongs to grade
        if self.stream and self.grade:
            if self.stream.grade != self.grade:
                raise ValidationError({
                    'stream': f'Stream {self.stream.name} does not belong to grade {self.grade.name}.'
                })
        
        # Validate grade belongs to curriculum
        if self.grade and self.curriculum:
            if self.grade.curriculum != self.curriculum:
                raise ValidationError({
                    'grade': f'Grade {self.grade.name} does not belong to curriculum {self.curriculum.name}.'
                })
    
    def save(self, *args, **kwargs):
        # Run validation
        self.full_clean()
        
        # If setting as active, deactivate other enrollments for same student/term
        if self.is_active and not self.is_deleted:
            Enrollment.objects.filter(
                student=self.student,
                academic_year=self.academic_year,
                term=self.term,
                is_active=True,
                is_deleted=False
            ).exclude(pk=self.pk).update(is_active=False)
        
        super().save(*args, **kwargs)
    
    def close_enrollment(self, status, exit_date=None, remarks=None):
        """Helper method to close an enrollment"""
        self.status = status
        self.is_active = False
        self.exit_date = exit_date or timezone.now().date()
        if remarks:
            self.remarks = remarks
        self.save()
    
    def get_progression_history(self):
        """Get the full progression chain for this student"""
        history = []
        current = self
        
        # Go backwards through previous enrollments
        while current:
            history.insert(0, current)
            current = current.previous_enrollment
        
        return history
    class Meta:
        ordering = ['-enrollment_date', '-created_at']
        indexes = [
            models.Index(fields=['student', 'academic_year', 'term']),
            models.Index(fields=['status', 'is_active']),
            models.Index(fields=['enrollment_date']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'academic_year', 'term'],
                condition=models.Q(is_active=True, is_deleted=False),
                name='unique_active_enrollment_per_term'
            )
        ]
        db_table = 'student_enrollments'