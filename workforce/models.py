"""
HR & Payroll Django Models for Academic ERP
Part 3: Job & Role Management
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
from .core_models import TimestampedModel, AuditedModel, Employee


from django.contrib.auth import get_user_model

User = get_user_model()

class EducationLevel(TimestampedModel):
    """Minimum education levels (referenced from Module 2)"""
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_academic = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    
    class Meta:
        db_table = 'hr_education_level'
        ordering = ['sort_order']
    
    def __str__(self):
        return self.name

class FieldOfStudy(models.Model):
    name = models.CharField(max_length=200)
    discipline = models.CharField(
        max_length=100,
        help_text=_("STEM, Education, Business, Arts, etc.")
    )
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name
class Institution(models.Model):
    name = models.CharField(max_length=255)
    country = models.CharField(max_length=100)
    accreditation_body = models.CharField(max_length=255, blank=True)
    is_accredited = models.BooleanField(default=True)
    website = models.URLField(blank=True)

    def __str__(self):
        return self.name
class EmployeeEducation(models.Model):
    employee = models.ForeignKey(
        'workforce.Employee',
        on_delete=models.CASCADE,
        related_name='educations'
    )
    education_level = models.ForeignKey(
        EducationLevel,
        on_delete=models.PROTECT, related_name='education_level'
    )
    institution = models.ForeignKey(
        Institution,
        on_delete=models.PROTECT
    )
    field_of_study = models.ForeignKey(
        FieldOfStudy,
        on_delete=models.SET_NULL,
        null=True, blank=True
    )
    award_title = models.CharField(max_length=255)
    graduation_date = models.DateField()
    classification = models.CharField(
        max_length=100,
        blank=True,
        help_text=_("First Class, Second Upper, GPA, etc.")
    )
    certificate_file = models.FileField(
        upload_to='employee/education/',
        blank=True, null=True
    )

    verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='verified_educations'
    )
    verification_date = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-graduation_date']
        unique_together = ('employee', 'education_level', 'institution')

    def __str__(self):
        return f"{self.employee} - {self.award_title}"

class ProfessionalCertification(models.Model):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('suspended', 'Suspended'),
    )

    employee = models.ForeignKey(
        'workforce.Employee',
        on_delete=models.CASCADE,
        related_name='certifications'
    )
    certification_name = models.CharField(max_length=255)
    issuing_body = models.CharField(max_length=255)
    certificate_number = models.CharField(max_length=100, blank=True)
    issue_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
    certificate_file = models.FileField(
        upload_to='employee/certifications/',
        blank=True, null=True
    )

    is_mandatory = models.BooleanField(default=False)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active'
    )

    verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='verified_certifications'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.certification_name} - {self.employee}"

class ContinuousProfessionalDevelopment(models.Model):
    employee = models.ForeignKey(
        'workforce.Employee',
        on_delete=models.CASCADE,
        related_name='cpd_records'
    )
    activity_name = models.CharField(max_length=255)
    provider = models.CharField(max_length=255)
    cpd_hours = models.DecimalField(max_digits=5, decimal_places=2)

    start_date = models.DateField()
    end_date = models.DateField()

    certificate_file = models.FileField(
        upload_to='employee/cpd/',
        blank=True, null=True
    )

    linked_certification = models.ForeignKey(
        ProfessionalCertification,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='cpd_activities'
    )

    approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='approved_cpd'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.activity_name} ({self.cpd_hours} hrs)"

# ============================================================================
# MODULE 3: JOB & ROLE MANAGEMENT
# ============================================================================

class Campus(AuditedModel):
    """Institution campuses"""
    institution = models.ForeignKey(
        'core.InstitutionProfile',
        on_delete=models.CASCADE,
        related_name='campuses',
        null=True,
        blank=True,
        help_text='The institution this campus belongs to'
    )
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    location = models.CharField(max_length=255)
    cost_center_code = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)

    # Address
    address_line_1 = models.CharField(max_length=255, blank=True)
    address_line_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    county = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)

    # Contact
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    principal_name = models.CharField(max_length=200, blank=True)

    # Optional campus geofence anchor for on-site attendance
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    geofence_radius_meters = models.PositiveIntegerField(default=200)
    
    class Meta:
        db_table = 'hr_campus'
        verbose_name_plural = 'Campuses'
        ordering = ['name']
    
    def __str__(self):
        return self.name


class Faculty(AuditedModel):
    """Academic faculties/schools"""
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    dean = models.ForeignKey(
        Employee, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='faculty_dean'
    )
    campus = models.ForeignKey(Campus, on_delete=models.PROTECT)
    cost_center_code = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'hr_faculty'
        verbose_name_plural = 'Faculties'
        ordering = ['name']
    
    def __str__(self):
        return self.name


class Department(AuditedModel):
    """Departments - both academic and administrative"""
    
    class DepartmentType(models.TextChoices):
        ACADEMIC = 'academic', _('Academic')
        ADMINISTRATIVE = 'administrative', _('Administrative')
        SUPPORT = 'support', _('Support Services')
    
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    department_type = models.CharField(
        max_length=20, 
        choices=DepartmentType.choices,
        default=DepartmentType.ADMINISTRATIVE
    )
    
    faculty = models.ForeignKey(
        Faculty, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        help_text="For academic departments only"
    )
    parent_department = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='sub_departments'
    )
    
    head_of_department = models.ForeignKey(
        Employee, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='department_head'
    )
    
    campus = models.ForeignKey(Campus, on_delete=models.PROTECT, null=True, blank=True)
    cost_center_code = models.CharField(max_length=50, blank=True, null=True)
    
    is_active = models.BooleanField(default=True)
    budget_allocation = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    establishment_date = models.DateField(null=True, blank=True)
    
    class Meta:
        db_table = 'hr_department'
        ordering = ['name']
    
    def __str__(self):
        return self.name





class JobGrade(AuditedModel):
    """Job grades/groups with salary scales"""
    
    class Category(models.TextChoices):
        TEACHING = 'teaching', _('Teaching Staff')
        NON_TEACHING = 'non_teaching', _('Non-Teaching Staff')
        MANAGEMENT = 'management', _('Management')
        EXECUTIVE = 'executive', _('Executive')
    
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=Category.choices)
    
    min_salary = models.DecimalField(max_digits=12, decimal_places=2)
    max_salary = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    
    grade_level = models.PositiveIntegerField(
        help_text="Numerical level for comparisons"
    )
    
    requires_degree = models.BooleanField(default=False)
    minimum_education_level = models.ForeignKey(
        EducationLevel, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'hr_job_grade'
        ordering = ['grade_level']
    
    def __str__(self):
        return f"{self.code} - {self.name}"


class PayGradeStep(AuditedModel):
    """
    Incremental salary steps within a job grade.
    e.g. Job Group J has 12 steps, step 1 = 12,000, step 2 = 12,500, etc.
    """
    job_grade = models.ForeignKey(
        JobGrade,
        on_delete=models.CASCADE,
        related_name='steps'
    )
    step_number = models.PositiveSmallIntegerField()
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Salary amount at this step"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'hr_pay_grade_step'
        unique_together = ['job_grade', 'step_number']
        ordering = ['job_grade', 'step_number']

    def __str__(self):
        return f"{self.job_grade.code} - Step {self.step_number} ({self.amount})"


class JobTitle(AuditedModel):
    """Job titles/positions"""
    
    class Category(models.TextChoices):
        TEACHING = 'teaching', _('Teaching Staff')
        NON_TEACHING = 'non_teaching', _('Non-Teaching Staff')
        CONTRACT = 'contract', _('Contract Staff')
    
    title = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    job_grade = models.ForeignKey(JobGrade, on_delete=models.PROTECT)
    category = models.CharField(max_length=20, choices=Category.choices)
    
    is_academic_rank = models.BooleanField(
        default=False,
        help_text="Is this an academic rank?"
    )
    academic_rank_level = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text="1=Lecturer, 2=Senior Lecturer, 3=Associate Prof, 4=Professor"
    )
    
    description = models.TextField(blank=True)
    min_experience_years = models.PositiveIntegerField(default=0)
    required_qualifications = models.TextField(blank=True)
    
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'hr_job_title'
        ordering = ['title']
    
    def __str__(self):
        return self.title


class JobDescription(AuditedModel):
    """Detailed job descriptions - versioned"""
    job_title = models.ForeignKey(
        JobTitle, 
        on_delete=models.CASCADE,
        related_name='descriptions'
    )
    department = models.ForeignKey(
        Department, 
        on_delete=models.CASCADE
    )
    
    version = models.CharField(max_length=20)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    
    summary = models.TextField()
    key_responsibilities = models.JSONField(
        help_text="List of responsibilities"
    )
    required_skills = models.JSONField(
        help_text="List of required skills"
    )
    required_competencies = models.JSONField(
        help_text="List of competencies"
    )
    
    physical_requirements = models.TextField(blank=True)
    working_conditions = models.TextField(blank=True)
    travel_requirements = models.TextField(blank=True)
    
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='approved_job_descriptions'
    )
    approved_date = models.DateField(null=True, blank=True)
    
    class Meta:
        db_table = 'hr_job_description'
        ordering = ['-effective_from']
        unique_together = ['job_title', 'version']
    
    def __str__(self):
        return f"{self.job_title.title} - v{self.version}"


class EmployeeJobAssignment(AuditedModel):
    """Employee job assignments - current and historical"""
    
    class AssignmentType(models.TextChoices):
        PERMANENT = 'permanent', _('Permanent')
        ACTING = 'acting', _('Acting')
        TEMPORARY = 'temporary', _('Temporary')
        SECONDMENT = 'secondment', _('Secondment')
    
    class EmploymentType(models.TextChoices):
        FULL_TIME = 'full_time', _('Full-Time')
        PART_TIME = 'part_time', _('Part-Time')
        VISITING = 'visiting', _('Visiting')
        ADJUNCT = 'adjunct', _('Adjunct')
    
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='job_assignments'
    )
    job_title = models.ForeignKey(JobTitle, on_delete=models.PROTECT)
    department = models.ForeignKey(Department, on_delete=models.PROTECT)
    campus = models.ForeignKey(Campus, on_delete=models.PROTECT)
    
    reports_to = models.ForeignKey(
        Employee, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='subordinates'
    )
    
    assignment_type = models.CharField(
        max_length=20, 
        choices=AssignmentType.choices
    )
    employment_type = models.CharField(
        max_length=20, 
        choices=EmploymentType.choices
    )
    
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    
    fte = models.DecimalField(
        max_digits=3, 
        decimal_places=2,
        default=Decimal('1.00'),
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        help_text="Full-Time Equivalent (1.0 = 100%)"
    )
    
    # For teaching staff
    teaching_load_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        null=True, 
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    administrative_load_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        null=True, 
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    research_load_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        null=True, 
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    
    is_primary_assignment = models.BooleanField(default=True)
    reason_for_change = models.TextField(blank=True)
    
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='approved_assignments'
    )
    approval_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'hr_employee_job_assignment'
        ordering = ['-effective_from']
        indexes = [
            models.Index(fields=['employee', 'is_primary_assignment']),
            models.Index(fields=['effective_from', 'effective_to']),
        ]
    
    def __str__(self):
        return f"{self.employee.employee_no} - {self.job_title.title}"


class ReportingLine(AuditedModel):
    """Reporting relationships"""
    
    class ReportingType(models.TextChoices):
        DIRECT = 'direct', _('Direct Report')
        DOTTED_LINE = 'dotted_line', _('Dotted Line')
        FUNCTIONAL = 'functional', _('Functional Report')
        PROJECT = 'project', _('Project Report')
    
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='reporting_lines'
    )
    supervisor = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='supervised_employees'
    )
    
    reporting_type = models.CharField(
        max_length=20, 
        choices=ReportingType.choices
    )
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_primary = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'hr_reporting_line'
        ordering = ['-is_primary', '-effective_from']
    
    def __str__(self):
        return f"{self.employee.employee_no} reports to {self.supervisor.employee_no}"


class SuccessionPlan(AuditedModel):
    """Succession planning for critical positions"""
    
    class ReadinessLevel(models.TextChoices):
        READY_NOW = 'ready_now', _('Ready Now')
        ONE_YEAR = '1_year', _('1 Year')
        TWO_YEARS = '2_years', _('2 Years')
        THREE_PLUS = '3_plus_years', _('3+ Years')
    
    position = models.ForeignKey(
        JobTitle, 
        on_delete=models.CASCADE,
        related_name='succession_plans'
    )
    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    
    successor_employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='succession_opportunities'
    )
    
    readiness_level = models.CharField(
        max_length=20, 
        choices=ReadinessLevel.choices
    )
    development_plan = models.TextField()
    
    assessed_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True
    )
    assessment_date = models.DateField()
    next_review_date = models.DateField()
    
    class Meta:
        db_table = 'hr_succession_plan'
        ordering = ['position', 'readiness_level']
    
    def __str__(self):
        return f"{self.position.title} - {self.successor_employee.employee_no}"
    
class AttendancePolicy(AuditedModel):
    """Attendance policies for different employee categories"""
    
    class EmployeeCategory(models.TextChoices):
        TEACHING = 'teaching', _('Teaching Staff')
        NON_TEACHING = 'non_teaching', _('Non-Teaching Staff')
        MANAGEMENT = 'management', _('Management')
        ALL = 'all', _('All Staff')
    
    class OvertimeCalculation(models.TextChoices):
        DAILY = 'daily', _('Daily')
        WEEKLY = 'weekly', _('Weekly')
        MONTHLY = 'monthly', _('Monthly')
    
    name = models.CharField(max_length=200)
    employee_category = models.CharField(
        max_length=20, 
        choices=EmployeeCategory.choices
    )
    
    work_days_per_week = models.PositiveIntegerField(default=5)
    standard_hours_per_day = models.DecimalField(
        max_digits=4, 
        decimal_places=2, 
        default=8
    )
    standard_hours_per_week = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=40
    )
    
    grace_period_minutes = models.PositiveIntegerField(
        default=15,
        help_text="Late arrival tolerance in minutes"
    )
    minimum_hours_for_full_day = models.DecimalField(
        max_digits=4, 
        decimal_places=2, 
        default=7
    )
    half_day_threshold_hours = models.DecimalField(
        max_digits=4, 
        decimal_places=2, 
        default=4
    )
    
    overtime_eligible = models.BooleanField(default=False)
    overtime_calculation_method = models.CharField(
        max_length=10, 
        choices=OvertimeCalculation.choices,
        default=OvertimeCalculation.DAILY
    )
    overtime_threshold_hours = models.DecimalField(
        max_digits=4, 
        decimal_places=2, 
        default=8
    )
    
    weekend_work_multiplier = models.DecimalField(
        max_digits=3, 
        decimal_places=2, 
        default=1.5
    )
    holiday_work_multiplier = models.DecimalField(
        max_digits=3, 
        decimal_places=2, 
        default=2.0
    )
    night_shift_multiplier = models.DecimalField(
        max_digits=3, 
        decimal_places=2, 
        default=1.5
    )
    
    requires_biometric = models.BooleanField(default=False)
    allow_biometric_clock_in = models.BooleanField(default=True)
    allow_remote_clock_in = models.BooleanField(default=True)
    allow_geolocation_clock_in = models.BooleanField(default=True)
    require_on_site_geofence = models.BooleanField(default=False)
    default_geofence_radius_meters = models.PositiveIntegerField(default=200)
    
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'hr_attendance_policy'
        verbose_name_plural = 'Attendance Policies'
        ordering = ['name']
    
    def __str__(self):
        return self.name


class WorkSchedule(AuditedModel):
    """Standard working hours/schedules"""
    
    class ScheduleType(models.TextChoices):
        FIXED = 'fixed', _('Fixed Schedule')
        FLEXIBLE = 'flexible', _('Flexible Schedule')
        SHIFT = 'shift', _('Shift-Based')
        TEACHING_TIMETABLE = 'teaching_timetable', _('Teaching Timetable')
    
    name = models.CharField(max_length=200)
    schedule_type = models.CharField(
        max_length=20, 
        choices=ScheduleType.choices
    )
    attendance_policy = models.ForeignKey(
        AttendancePolicy, 
        on_delete=models.PROTECT
    )
    
    # Weekly schedule
    monday_start = models.TimeField(null=True, blank=True)
    monday_end = models.TimeField(null=True, blank=True)
    tuesday_start = models.TimeField(null=True, blank=True)
    tuesday_end = models.TimeField(null=True, blank=True)
    wednesday_start = models.TimeField(null=True, blank=True)
    wednesday_end = models.TimeField(null=True, blank=True)
    thursday_start = models.TimeField(null=True, blank=True)
    thursday_end = models.TimeField(null=True, blank=True)
    friday_start = models.TimeField(null=True, blank=True)
    friday_end = models.TimeField(null=True, blank=True)
    saturday_start = models.TimeField(null=True, blank=True)
    saturday_end = models.TimeField(null=True, blank=True)
    sunday_start = models.TimeField(null=True, blank=True)
    sunday_end = models.TimeField(null=True, blank=True)
    
    break_duration_minutes = models.PositiveIntegerField(default=60)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'hr_work_schedule'
        ordering = ['name']
    
    def __str__(self):
        return self.name


class EmployeeWorkSchedule(AuditedModel):
    """Employee schedule assignments"""
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='work_schedules'
    )
    work_schedule = models.ForeignKey(WorkSchedule, on_delete=models.PROTECT)
    
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'hr_employee_work_schedule'
        ordering = ['-effective_from']
        indexes = [
            models.Index(fields=['employee', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.employee.employee_no} - {self.work_schedule.name}"


class EmployeeAttendanceAccessProfile(AuditedModel):
    """Optional per-employee attendance access overrides."""

    employee = models.OneToOneField(
        Employee,
        on_delete=models.CASCADE,
        related_name='attendance_access_profile'
    )

    # Nullable booleans act as tri-state overrides: None -> inherit policy.
    enforce_biometric = models.BooleanField(null=True, blank=True)
    allow_remote_clock_in = models.BooleanField(null=True, blank=True)
    allow_geolocation_clock_in = models.BooleanField(null=True, blank=True)
    require_on_site_geofence = models.BooleanField(null=True, blank=True)

    assigned_campus = models.ForeignKey(
        Campus,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='attendance_profiles'
    )
    geofence_radius_meters = models.PositiveIntegerField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'hr_employee_attendance_access_profile'
        verbose_name_plural = 'Employee Attendance Access Profiles'

    def __str__(self):
        return f"Attendance Access - {self.employee.employee_no}"


class BiometricDevice(TimestampedModel):
    """Biometric attendance devices"""
    
    class DeviceType(models.TextChoices):
        FINGERPRINT = 'fingerprint', _('Fingerprint')
        FACE_RECOGNITION = 'face_recognition', _('Face Recognition')
        CARD_READER = 'card_reader', _('Card Reader')
        MOBILE = 'mobile', _('Mobile App')
    
    device_id = models.CharField(max_length=100, unique=True)
    device_name = models.CharField(max_length=200)
    location = models.CharField(max_length=255)
    campus = models.ForeignKey('Campus', on_delete=models.PROTECT)
    device_type = models.CharField(max_length=20, choices=DeviceType.choices)
    
    is_active = models.BooleanField(default=True)
    last_sync_time = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'hr_biometric_device'
        ordering = ['campus', 'location']
    
    def __str__(self):
        return f"{self.device_name} - {self.location}"


class AttendanceRecord(AuditedModel):
    """Daily attendance records"""
    
    class CheckMethod(models.TextChoices):
        BIOMETRIC = 'biometric', _('Biometric')
        GEOLOCATION = 'geolocation', _('On-Site Geolocation')
        REMOTE = 'remote', _('Remote')
        MANUAL = 'manual', _('Manual Entry')
        MOBILE = 'mobile', _('Mobile App')
        SYSTEM = 'system', _('System Generated')
    
    class Status(models.TextChoices):
        PRESENT = 'present', _('Present')
        ABSENT = 'absent', _('Absent')
        LATE = 'late', _('Late')
        HALF_DAY = 'half_day', _('Half Day')
        ON_LEAVE = 'on_leave', _('On Leave')
        HOLIDAY = 'holiday', _('Holiday')
        WEEKEND = 'weekend', _('Weekend')
    
    class ApprovalStatus(models.TextChoices):
        PENDING = 'pending', _('Pending')
        APPROVED = 'approved', _('Approved')
        REJECTED = 'rejected', _('Rejected')
    
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='attendance_records'
    )
    attendance_date = models.DateField()
    work_schedule = models.ForeignKey(
        WorkSchedule, 
        on_delete=models.PROTECT
    )
    
    # Check-in
    check_in_time = models.TimeField(null=True, blank=True)
    check_in_method = models.CharField(
        max_length=20, 
        choices=CheckMethod.choices,
        null=True, 
        blank=True
    )
    check_in_device = models.ForeignKey(
        BiometricDevice, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='check_ins'
    )
    check_in_location = models.CharField(max_length=255, blank=True)
    
    # Check-out
    check_out_time = models.TimeField(null=True, blank=True)
    check_out_method = models.CharField(
        max_length=20, 
        choices=CheckMethod.choices,
        null=True, 
        blank=True
    )
    check_out_device = models.ForeignKey(
        BiometricDevice, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='check_outs'
    )
    check_out_location = models.CharField(max_length=255, blank=True)
    
    # Calculated hours
    total_hours = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0
    )
    regular_hours = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0
    )
    overtime_hours = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0
    )
    night_hours = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0
    )
    weekend_hours = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0
    )
    
    status = models.CharField(max_length=20, choices=Status.choices)
    late_by_minutes = models.PositiveIntegerField(default=0)
    early_departure_minutes = models.PositiveIntegerField(default=0)
    
    notes = models.TextField(blank=True)
    
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='approved_attendance'
    )
    approval_status = models.CharField(
        max_length=20, 
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING
    )
    
    class Meta:
        db_table = 'hr_attendance_record'
        ordering = ['-attendance_date']
        unique_together = ['employee', 'attendance_date']
        indexes = [
            models.Index(fields=['employee', 'attendance_date']),
            models.Index(fields=['attendance_date', 'status']),
        ]
    
    def __str__(self):
        return f"{self.employee.employee_no} - {self.attendance_date}"


class TeachingSessionAttendance(AuditedModel):
    """Attendance for teaching sessions"""
    
    class Status(models.TextChoices):
        CONDUCTED = 'conducted', _('Conducted')
        CANCELLED = 'cancelled', _('Cancelled')
        RESCHEDULED = 'rescheduled', _('Rescheduled')
        ABSENT = 'absent', _('Lecturer Absent')
    
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='teaching_sessions'
    )
    # timetable_entry_id would link to Academic module's CourseSchedule
    timetable_entry_id = models.PositiveIntegerField(
        help_text="Foreign key to CourseSchedule in Academic module"
    )
    
    session_date = models.DateField()
    scheduled_start_time = models.TimeField()
    scheduled_end_time = models.TimeField()
    
    actual_start_time = models.TimeField(null=True, blank=True)
    actual_end_time = models.TimeField(null=True, blank=True)
    teaching_hours = models.DecimalField(
        max_digits=4, 
        decimal_places=2, 
        default=0
    )
    
    students_present_count = models.PositiveIntegerField(default=0)
    attendance_marked = models.BooleanField(default=False)
    
    status = models.CharField(max_length=20, choices=Status.choices)
    cancellation_reason = models.TextField(blank=True)
    
    substitute_lecturer = models.ForeignKey(
        Employee, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='substitute_sessions'
    )
    
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='approved_teaching_sessions'
    )
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'hr_teaching_session_attendance'
        ordering = ['-session_date', '-scheduled_start_time']
        indexes = [
            models.Index(fields=['employee', 'session_date']),
            models.Index(fields=['session_date', 'status']),
        ]
    
    def __str__(self):
        return f"{self.employee.employee_no} - {self.session_date}"


class OvertimeRequest(AuditedModel):
    """Overtime pre-approval requests"""
    
    class ApprovalStatus(models.TextChoices):
        PENDING = 'pending', _('Pending')
        APPROVED = 'approved', _('Approved')
        REJECTED = 'rejected', _('Rejected')
    
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='overtime_requests'
    )
    request_date = models.DateField(auto_now_add=True)
    overtime_date = models.DateField()
    
    start_time = models.TimeField()
    end_time = models.TimeField()
    estimated_hours = models.DecimalField(max_digits=4, decimal_places=2)
    
    reason = models.TextField()
    department = models.ForeignKey('Department', on_delete=models.PROTECT)
    
    requested_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='overtime_requests_made'
    )
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='overtime_requests_approved'
    )
    
    approval_status = models.CharField(
        max_length=20, 
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING
    )
    approval_notes = models.TextField(blank=True)
    
    actual_hours = models.DecimalField(
        max_digits=4, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Filled from attendance record"
    )
    
    class Meta:
        db_table = 'hr_overtime_request'
        ordering = ['-request_date']
        indexes = [
            models.Index(fields=['employee', 'overtime_date']),
            models.Index(fields=['approval_status']),
        ]
    
    def __str__(self):
        return f"{self.employee.employee_no} - {self.overtime_date}"


class AttendanceException(AuditedModel):
    """Attendance exceptions and explanations"""
    
    class ExceptionType(models.TextChoices):
        LATE_ARRIVAL = 'late_arrival', _('Late Arrival')
        EARLY_DEPARTURE = 'early_departure', _('Early Departure')
        MISSING_CHECKOUT = 'missing_checkout', _('Missing Check-out')
        ABSENT = 'absent', _('Absent')
    
    class ReviewStatus(models.TextChoices):
        PENDING = 'pending', _('Pending Review')
        ACCEPTED = 'accepted', _('Accepted')
        REJECTED = 'rejected', _('Rejected')
    
    class PayrollImpact(models.TextChoices):
        NONE = 'none', _('No Impact')
        DEDUCTION = 'deduction', _('Salary Deduction')
        WARNING = 'warning', _('Warning Only')
    
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='attendance_exceptions'
    )
    exception_date = models.DateField()
    exception_type = models.CharField(
        max_length=20, 
        choices=ExceptionType.choices
    )
    
    reason = models.TextField()
    supporting_document = models.FileField(
        upload_to='attendance_exceptions/',
        blank=True
    )
    
    reported_by = models.CharField(max_length=50)
    reviewed_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='reviewed_exceptions'
    )
    
    review_status = models.CharField(
        max_length=20, 
        choices=ReviewStatus.choices,
        default=ReviewStatus.PENDING
    )
    review_notes = models.TextField(blank=True)
    payroll_impact = models.CharField(
        max_length=20, 
        choices=PayrollImpact.choices,
        default=PayrollImpact.NONE
    )
    
    class Meta:
        db_table = 'hr_attendance_exception'
        ordering = ['-exception_date']
        indexes = [
            models.Index(fields=['employee', 'exception_date']),
            models.Index(fields=['review_status']),
        ]
    
    def __str__(self):
        return f"{self.employee.employee_no} - {self.exception_date} - {self.get_exception_type_display()}"

class LeaveType(AuditedModel):
    """Leave types master data"""
    
    class Category(models.TextChoices):
        PAID = 'paid', _('Paid Leave')
        UNPAID = 'unpaid', _('Unpaid Leave')
        HALF_PAID = 'half_paid', _('Half-Paid Leave')
    
    class GenderSpecific(models.TextChoices):
        ALL = 'all', _('All Genders')
        MALE = 'male', _('Male Only')
        FEMALE = 'female', _('Female Only')
    
    class AccrualMethod(models.TextChoices):
        MONTHLY = 'monthly', _('Monthly Accrual')
        YEARLY = 'yearly', _('Yearly Accrual')
        ON_ANNIVERSARY = 'on_anniversary', _('On Anniversary')
    
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=Category.choices)
    
    is_statutory = models.BooleanField(
        default=False,
        help_text="Required by law"
    )
    max_days_per_year = models.PositiveIntegerField()
    gender_specific = models.CharField(
        max_length=10, 
        choices=GenderSpecific.choices,
        default=GenderSpecific.ALL
    )
    
    requires_medical_certificate = models.BooleanField(default=False)
    requires_supporting_document = models.BooleanField(default=False)
    advance_notice_days = models.PositiveIntegerField(
        default=7,
        help_text="Minimum days notice required"
    )
    
    can_be_carried_forward = models.BooleanField(default=True)
    max_carryforward_days = models.PositiveIntegerField(
        default=0,
        help_text="0 means no carryforward"
    )
    carryforward_expiry_months = models.PositiveIntegerField(
        default=3,
        help_text="Months before carried-forward leave expires"
    )
    
    can_be_encashed = models.BooleanField(default=False)
    
    accrual_rate = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        help_text="Days per month (e.g., 1.75 for 21 days/year)"
    )
    accrual_method = models.CharField(
        max_length=20, 
        choices=AccrualMethod.choices,
        default=AccrualMethod.MONTHLY
    )
    
    affects_attendance = models.BooleanField(default=True)
    affects_payroll = models.BooleanField(
        default=False,
        help_text="Does this leave type affect salary?"
    )
    
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    
    class Meta:
        db_table = 'hr_leave_type'
        ordering = ['sort_order', 'name']
    
    def __str__(self):
        return self.name


class LeavePolicyByCategory(AuditedModel):
    """Leave policies per employee category"""
    
    class EmployeeCategory(models.TextChoices):
        TEACHING = 'teaching', _('Teaching Staff')
        NON_TEACHING = 'non_teaching', _('Non-Teaching Staff')
        CONTRACT = 'contract', _('Contract Staff')
        CASUAL = 'casual', _('Casual Worker')
    
    leave_type = models.ForeignKey(
        LeaveType, 
        on_delete=models.CASCADE,
        related_name='policies'
    )
    employee_category = models.CharField(
        max_length=20, 
        choices=EmployeeCategory.choices
    )
    job_grade = models.ForeignKey(
        'JobGrade', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    annual_entitlement_days = models.PositiveIntegerField()
    accrual_starts_after_months = models.PositiveIntegerField(
        default=3,
        help_text="Probation period"
    )
    min_service_years_required = models.PositiveIntegerField(default=0)
    
    max_consecutive_days = models.PositiveIntegerField(
        help_text="Maximum continuous leave days"
    )
    min_days_per_application = models.PositiveIntegerField(default=1)
    
    blackout_period_applies = models.BooleanField(
        default=False,
        help_text="e.g., no leave during exams"
    )
    
    # approval_workflow_id would link to workflow configuration
    approval_workflow_id = models.PositiveIntegerField(null=True, blank=True)
    
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    
    class Meta:
        db_table = 'hr_leave_policy_by_category'
        verbose_name_plural = 'Leave Policies by Category'
        ordering = ['leave_type', 'employee_category']
        unique_together = ['leave_type', 'employee_category', 'job_grade']
    
    def __str__(self):
        return f"{self.leave_type.name} - {self.get_employee_category_display()}"


class EmployeeLeaveBalance(AuditedModel):
    """Leave balance per employee per leave type per year"""
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='leave_balances'
    )
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT)
    year = models.PositiveIntegerField()
    
    opening_balance = models.DecimalField(
        max_digits=6, 
        decimal_places=2, 
        default=0
    )
    accrued_days = models.DecimalField(
        max_digits=6, 
        decimal_places=2, 
        default=0
    )
    carried_forward_days = models.DecimalField(
        max_digits=6, 
        decimal_places=2, 
        default=0
    )
    adjustment_days = models.DecimalField(
        max_digits=6, 
        decimal_places=2, 
        default=0,
        help_text="Manual corrections"
    )
    
    taken_days = models.DecimalField(
        max_digits=6, 
        decimal_places=2, 
        default=0
    )
    pending_days = models.DecimalField(
        max_digits=6, 
        decimal_places=2, 
        default=0,
        help_text="Approved but not yet taken"
    )
    encashed_days = models.DecimalField(
        max_digits=6, 
        decimal_places=2, 
        default=0
    )
    forfeited_days = models.DecimalField(
        max_digits=6, 
        decimal_places=2, 
        default=0
    )
    
    closing_balance = models.DecimalField(
        max_digits=6, 
        decimal_places=2, 
        default=0
    )
    
    last_accrual_date = models.DateField(null=True, blank=True)
    next_accrual_date = models.DateField(null=True, blank=True)
    
    class Meta:
        db_table = 'hr_employee_leave_balance'
        ordering = ['-year', 'employee', 'leave_type']
        unique_together = ['employee', 'leave_type', 'year']
        indexes = [
            models.Index(fields=['employee', 'year']),
            models.Index(fields=['leave_type', 'year']),
        ]
    
    def __str__(self):
        return f"{self.employee.employee_no} - {self.leave_type.name} - {self.year}"


class LeaveApplication(AuditedModel):
    """Leave applications"""
    
    class Status(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        SUBMITTED = 'submitted', _('Submitted')
        PENDING_APPROVAL = 'pending_approval', _('Pending Approval')
        APPROVED = 'approved', _('Approved')
        REJECTED = 'rejected', _('Rejected')
        CANCELLED = 'cancelled', _('Cancelled')
        ON_LEAVE = 'on_leave', _('On Leave')
        COMPLETED = 'completed', _('Completed')
    
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='leave_applications'
    )
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT)
    
    application_date = models.DateField(auto_now_add=True)
    start_date = models.DateField()
    end_date = models.DateField()
    
    total_days = models.DecimalField(max_digits=5, decimal_places=2)
    working_days = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        help_text="Excludes weekends/holidays"
    )
    
    reason = models.TextField()
    emergency_contact_during_leave = models.CharField(
        max_length=200, 
        blank=True
    )
    emergency_phone = models.CharField(max_length=20, blank=True)
    
    return_date = models.DateField(
        help_text="Planned return date"
    )
    acting_employee = models.ForeignKey(
        Employee, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='acting_duties',
        help_text="Employee covering duties"
    )
    
    supporting_document_path = models.FileField(
        upload_to='leave_documents/',
        blank=True
    )
    medical_certificate_path = models.FileField(
        upload_to='leave_documents/medical/',
        blank=True
    )
    
    status = models.CharField(
        max_length=20, 
        choices=Status.choices,
        default=Status.DRAFT
    )
    
    current_approver = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='pending_leave_approvals'
    )
    
    submitted_date = models.DateTimeField(null=True, blank=True)
    approved_date = models.DateTimeField(null=True, blank=True)
    rejected_date = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    
    cancelled_date = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)
    
    actual_return_date = models.DateField(null=True, blank=True)
    remarks = models.TextField(blank=True)
    
    class Meta:
        db_table = 'hr_leave_application'
        ordering = ['-application_date']
        indexes = [
            models.Index(fields=['employee', 'status']),
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.employee.employee_no} - {self.leave_type.name} - {self.start_date}"


class LeaveApprovalWorkflow(AuditedModel):
    """Leave approval workflow tracking"""
    
    class ApproverRole(models.TextChoices):
        SUPERVISOR = 'supervisor', _('Direct Supervisor')
        HOD = 'hod', _('Head of Department')
        HR = 'hr', _('HR Manager')
        DEAN = 'dean', _('Dean')
        REGISTRAR = 'registrar', _('Registrar')
    
    class ApprovalStatus(models.TextChoices):
        PENDING = 'pending', _('Pending')
        APPROVED = 'approved', _('Approved')
        REJECTED = 'rejected', _('Rejected')
    
    leave_application = models.ForeignKey(
        LeaveApplication, 
        on_delete=models.CASCADE,
        related_name='approval_workflow'
    )
    
    approval_level = models.PositiveIntegerField()
    approver = models.ForeignKey(User, on_delete=models.PROTECT)
    approver_role = models.CharField(
        max_length=20, 
        choices=ApproverRole.choices
    )
    
    approval_status = models.CharField(
        max_length=20, 
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING
    )
    approval_date = models.DateTimeField(null=True, blank=True)
    comments = models.TextField(blank=True)
    notification_sent = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'hr_leave_approval_workflow'
        ordering = ['leave_application', 'approval_level']
        unique_together = ['leave_application', 'approval_level']
    
    def __str__(self):
        return f"{self.leave_application.employee.employee_no} - Level {self.approval_level}"


class LeaveEncashment(AuditedModel):
    """Leave encashment requests and payments"""
    
    class PaymentStatus(models.TextChoices):
        PENDING = 'pending', _('Pending Payment')
        PROCESSED = 'processed', _('Processed')
    
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='leave_encashments'
    )
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT)
    year = models.PositiveIntegerField()
    
    days_encashed = models.DecimalField(max_digits=5, decimal_places=2)
    rate_per_day = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Based on daily salary"
    )
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    
    request_date = models.DateField(auto_now_add=True)
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='approved_encashments'
    )
    approval_date = models.DateField(null=True, blank=True)
    
    payroll_period_id = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text="Link to payroll period when processed"
    )
    payment_status = models.CharField(
        max_length=20, 
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING
    )
    processed_date = models.DateField(null=True, blank=True)
    
    class Meta:
        db_table = 'hr_leave_encashment'
        ordering = ['-request_date']
        indexes = [
            models.Index(fields=['employee', 'year']),
            models.Index(fields=['payment_status']),
        ]
    
    def __str__(self):
        return f"{self.employee.employee_no} - {self.days_encashed} days - {self.year}"


class LeaveBlackoutPeriod(AuditedModel):
    """Periods when leave is restricted"""
    
    class AppliesToCategory(models.TextChoices):
        TEACHING = 'teaching', _('Teaching Staff')
        NON_TEACHING = 'non_teaching', _('Non-Teaching Staff')
        ALL = 'all', _('All Staff')
    
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    start_date = models.DateField()
    end_date = models.DateField()
    
    applies_to_category = models.CharField(
        max_length=20, 
        choices=AppliesToCategory.choices
    )
    applies_to_departments = models.JSONField(
        blank=True, 
        null=True,
        help_text="List of department IDs"
    )
    leave_types_restricted = models.JSONField(
        blank=True, 
        null=True,
        help_text="List of leave type IDs"
    )
    
    exception_approval_required = models.BooleanField(
        default=True,
        help_text="Can exceptions be granted?"
    )
    exception_approver = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='blackout_exceptions'
    )
    
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'hr_leave_blackout_period'
        ordering = ['start_date']
        indexes = [
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.start_date} to {self.end_date})"


class LeaveCalendar(TimestampedModel):
    """Public holidays and institutional closures"""
    
    class HolidayType(models.TextChoices):
        PUBLIC = 'public', _('Public Holiday')
        INSTITUTIONAL = 'institutional', _('Institutional Holiday')
        RELIGIOUS = 'religious', _('Religious Holiday')
    
    date = models.DateField()
    name = models.CharField(max_length=200)
    holiday_type = models.CharField(
        max_length=20, 
        choices=HolidayType.choices
    )
    
    is_working_day = models.BooleanField(
        default=False,
        help_text="Some institutions work on certain public holidays"
    )
    
    country = models.ForeignKey('Country', on_delete=models.PROTECT)
    is_recurring = models.BooleanField(
        default=False,
        help_text="Recurs annually"
    )
    
    class Meta:
        db_table = 'hr_leave_calendar'
        ordering = ['date']
        unique_together = ['date', 'country']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['country', 'date']),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.date}"

class ShiftType(AuditedModel):
    """Shift types definition"""
    
    class ShiftCategory(models.TextChoices):
        TEACHING = 'teaching', _('Teaching')
        NON_TEACHING = 'non_teaching', _('Non-Teaching')
        SECURITY = 'security', _('Security')
        MAINTENANCE = 'maintenance', _('Maintenance')
        LIBRARY = 'library', _('Library')
        OTHER = 'other', _('Other')
    
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    shift_category = models.CharField(
        max_length=20, 
        choices=ShiftCategory.choices
    )
    
    start_time = models.TimeField()
    end_time = models.TimeField()
    duration_hours = models.DecimalField(max_digits=4, decimal_places=2)
    
    is_overnight = models.BooleanField(
        default=False,
        help_text="Shift spans midnight"
    )
    break_duration_minutes = models.PositiveIntegerField(default=60)
    
    shift_multiplier = models.DecimalField(
        max_digits=3, 
        decimal_places=2,
        default=1.0,
        help_text="Pay multiplier (e.g., 1.5 for night shifts)"
    )
    
    color_code = models.CharField(
        max_length=7, 
        blank=True,
        help_text="Hex color for calendar display"
    )
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'hr_shift_type'
        ordering = ['start_time']
    
    def __str__(self):
        return f"{self.name} ({self.start_time}-{self.end_time})"


class ShiftSchedule(AuditedModel):
    """Shift roster templates"""
    
    class ShiftPattern(models.TextChoices):
        FIXED = 'fixed', _('Fixed Schedule')
        ROTATING = 'rotating', _('Rotating Schedule')
        FLEXIBLE = 'flexible', _('Flexible Schedule')
    
    name = models.CharField(max_length=200)
    department = models.ForeignKey(
        'Department', 
        on_delete=models.PROTECT
    )
    shift_pattern = models.CharField(
        max_length=20, 
        choices=ShiftPattern.choices
    )
    rotation_cycle_days = models.PositiveIntegerField(
        default=7,
        help_text="e.g., 7 for weekly rotation"
    )
    
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'hr_shift_schedule'
        ordering = ['name']
    
    def __str__(self):
        return self.name


class EmployeeShiftAssignment(AuditedModel):
    """Individual shift assignments"""
    
    class Status(models.TextChoices):
        SCHEDULED = 'scheduled', _('Scheduled')
        CONFIRMED = 'confirmed', _('Confirmed')
        COMPLETED = 'completed', _('Completed')
        ABSENT = 'absent', _('Absent')
        SWAPPED = 'swapped', _('Swapped')
        SUBSTITUTED = 'substituted', _('Substituted')
    
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='shift_assignments'
    )
    shift_schedule = models.ForeignKey(
        ShiftSchedule, 
        on_delete=models.PROTECT
    )
    shift_type = models.ForeignKey(ShiftType, on_delete=models.PROTECT)
    
    assignment_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    
    campus = models.ForeignKey('Campus', on_delete=models.PROTECT)
    location = models.CharField(
        max_length=255,
        blank=True,
        help_text="Specific building/area"
    )
    
    status = models.CharField(
        max_length=20, 
        choices=Status.choices,
        default=Status.SCHEDULED
    )
    notes = models.TextField(blank=True)
    
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='approved_shifts'
    )
    
    class Meta:
        db_table = 'hr_employee_shift_assignment'
        ordering = ['assignment_date', 'start_time']
        indexes = [
            models.Index(fields=['employee', 'assignment_date']),
            models.Index(fields=['assignment_date', 'status']),
        ]
    
    def __str__(self):
        return f"{self.employee.employee_no} - {self.assignment_date} - {self.shift_type.name}"


class ShiftSwapRequest(AuditedModel):
    """Shift swap requests between employees"""
    
    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending')
        APPROVED = 'approved', _('Approved')
        REJECTED = 'rejected', _('Rejected')
        CANCELLED = 'cancelled', _('Cancelled')
    
    requesting_employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='shift_swap_requests'
    )
    target_employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='shift_swap_offers'
    )
    
    original_shift_assignment = models.ForeignKey(
        EmployeeShiftAssignment, 
        on_delete=models.CASCADE,
        related_name='swap_requests_as_original'
    )
    swap_shift_assignment = models.ForeignKey(
        EmployeeShiftAssignment, 
        on_delete=models.CASCADE,
        related_name='swap_requests_as_swap'
    )
    
    reason = models.TextField()
    request_date = models.DateField(auto_now_add=True)
    
    status = models.CharField(
        max_length=20, 
        choices=Status.choices,
        default=Status.PENDING
    )
    
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='approved_shift_swaps'
    )
    approval_date = models.DateField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    
    class Meta:
        db_table = 'hr_shift_swap_request'
        ordering = ['-request_date']
    
    def __str__(self):
        return f"{self.requesting_employee.employee_no} <-> {self.target_employee.employee_no}"


class TeachingTimetable(AuditedModel):
    """Teaching timetable - auto-generated from academic module"""
    
    class SessionType(models.TextChoices):
        LECTURE = 'lecture', _('Lecture')
        TUTORIAL = 'tutorial', _('Tutorial')
        LAB = 'lab', _('Laboratory')
        PRACTICAL = 'practical', _('Practical')
        SEMINAR = 'seminar', _('Seminar')
    
    class DayOfWeek(models.TextChoices):
        MONDAY = 'monday', _('Monday')
        TUESDAY = 'tuesday', _('Tuesday')
        WEDNESDAY = 'wednesday', _('Wednesday')
        THURSDAY = 'thursday', _('Thursday')
        FRIDAY = 'friday', _('Friday')
        SATURDAY = 'saturday', _('Saturday')
        SUNDAY = 'sunday', _('Sunday')
    
    class Status(models.TextChoices):
        ACTIVE = 'active', _('Active')
        CANCELLED = 'cancelled', _('Cancelled')
        COMPLETED = 'completed', _('Completed')
    
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='teaching_timetable'
    )
    
    # Links to Academic Module
    course_id = models.PositiveIntegerField(
        help_text="Foreign key to Course in Academic module"
    )
    class_id = models.PositiveIntegerField(
        help_text="Foreign key to Class in Academic module"
    )
    academic_term_id = models.PositiveIntegerField(
        help_text="Foreign key to Academic Term"
    )
    room_id = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text="Foreign key to ClassRoom"
    )
    
    day_of_week = models.CharField(max_length=10, choices=DayOfWeek.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()
    duration_hours = models.DecimalField(max_digits=4, decimal_places=2)
    
    campus = models.ForeignKey('Campus', on_delete=models.PROTECT)
    session_type = models.CharField(
        max_length=20, 
        choices=SessionType.choices
    )
    
    is_recurring = models.BooleanField(
        default=True,
        help_text="Weekly throughout term"
    )
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    
    status = models.CharField(
        max_length=20, 
        choices=Status.choices,
        default=Status.ACTIVE
    )
    
    class Meta:
        db_table = 'hr_teaching_timetable'
        ordering = ['day_of_week', 'start_time']
        indexes = [
            models.Index(fields=['employee', 'academic_term_id']),
            models.Index(fields=['day_of_week', 'start_time']),
        ]
    
    def __str__(self):
        return f"{self.employee.employee_no} - {self.get_day_of_week_display()} {self.start_time}"


class TimetableSubstitution(AuditedModel):
    """Teaching substitutions"""
    
    class SubstitutionType(models.TextChoices):
        ONE_TIME = 'one_time', _('One-Time')
        TEMPORARY_PERIOD = 'temporary_period', _('Temporary Period')
        PERMANENT = 'permanent', _('Permanent')
    
    class CompensationType(models.TextChoices):
        PAID = 'paid', _('Paid')
        RECIPROCAL = 'reciprocal', _('Reciprocal')
        GOODWILL = 'goodwill', _('Goodwill')
    
    original_timetable = models.ForeignKey(
        TeachingTimetable, 
        on_delete=models.CASCADE,
        related_name='substitutions'
    )
    original_lecturer = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='substitutions_as_original'
    )
    substitute_lecturer = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='substitutions_as_substitute'
    )
    
    substitution_date = models.DateField()
    reason = models.TextField()
    
    substitution_type = models.CharField(
        max_length=20, 
        choices=SubstitutionType.choices
    )
    
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='approved_substitutions'
    )
    
    compensation_type = models.CharField(
        max_length=20, 
        choices=CompensationType.choices
    )
    compensation_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        null=True, 
        blank=True
    )
    
    payroll_period_id = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text="Link to payroll period for payment"
    )
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'hr_timetable_substitution'
        ordering = ['-substitution_date']
        indexes = [
            models.Index(fields=['substitute_lecturer', 'substitution_date']),
            models.Index(fields=['substitution_date']),
        ]
    
    def __str__(self):
        return f"{self.original_lecturer.employee_no} â†’ {self.substitute_lecturer.employee_no}"


class ShiftAttendance(AuditedModel):
    """Actual shift worked record"""
    
    class Status(models.TextChoices):
        COMPLETED = 'completed', _('Completed')
        INCOMPLETE = 'incomplete', _('Incomplete')
        ABSENT = 'absent', _('Absent')
        PARTIAL = 'partial', _('Partial')
    
    shift_assignment = models.OneToOneField(
        EmployeeShiftAssignment, 
        on_delete=models.CASCADE,
        related_name='attendance'
    )
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='shift_attendance'
    )
    
    check_in_time = models.TimeField(null=True, blank=True)
    check_out_time = models.TimeField(null=True, blank=True)
    
    actual_hours = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0
    )
    regular_hours = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0
    )
    overtime_hours = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0
    )
    
    status = models.CharField(max_length=20, choices=Status.choices)
    
    was_substituted = models.BooleanField(default=False)
    substitute_employee = models.ForeignKey(
        Employee, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='shift_substitutions'
    )
    
    verified_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='verified_shift_attendance'
    )
    verification_date = models.DateField(null=True, blank=True)
    
    class Meta:
        db_table = 'hr_shift_attendance'
        ordering = ['-shift_assignment__assignment_date']
    
    def __str__(self):
        return f"{self.employee.employee_no} - Shift {self.shift_assignment_id}"


class TeachingLoadSummary(AuditedModel):
    """Aggregated teaching load per employee per term"""
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='teaching_load_summaries'
    )
    academic_term_id = models.PositiveIntegerField(
        help_text="Foreign key to Academic Term"
    )
    
    total_weekly_hours = models.DecimalField(
        max_digits=5, 
        decimal_places=2
    )
    lecture_hours = models.DecimalField(
        max_digits=5, 
        decimal_places=2
    )
    tutorial_hours = models.DecimalField(
        max_digits=5, 
        decimal_places=2
    )
    lab_hours = models.DecimalField(
        max_digits=5, 
        decimal_places=2
    )
    
    standard_load_hours = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        help_text="From policy"
    )
    overload_hours = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        default=0
    )
    underload_hours = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        default=0
    )
    
    courses_count = models.PositiveIntegerField(default=0)
    last_calculated = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'hr_teaching_load_summary'
        ordering = ['-academic_term_id', 'employee']
        unique_together = ['employee', 'academic_term_id']
    
    def __str__(self):
        return f"{self.employee.employee_no} - Term {self.academic_term_id} - {self.total_weekly_hours}hrs"

class PerformanceMetric(AuditedModel):
    """KPI Library - reusable performance metrics"""
    
    class MetricCategory(models.TextChoices):
        TEACHING = 'teaching', _('Teaching')
        RESEARCH = 'research', _('Research')
        ADMINISTRATION = 'administration', _('Administration')
        SERVICE = 'service', _('Service')
        BEHAVIORAL = 'behavioral', _('Behavioral')
    
    class MeasurementType(models.TextChoices):
        QUANTITATIVE = 'quantitative', _('Quantitative')
        QUALITATIVE = 'qualitative', _('Qualitative')
        RATING_SCALE = 'rating_scale', _('Rating Scale')
    
    class TargetType(models.TextChoices):
        INDIVIDUAL = 'individual', _('Individual')
        DEPARTMENTAL = 'departmental', _('Departmental')
        INSTITUTIONAL = 'institutional', _('Institutional')
    
    class DataSource(models.TextChoices):
        MANUAL = 'manual', _('Manual Entry')
        SYSTEM_GENERATED = 'system_generated', _('System Generated')
        PEER_REVIEW = 'peer_review', _('Peer Review')
    
    class AppliesToCategory(models.TextChoices):
        TEACHING = 'teaching', _('Teaching Staff')
        NON_TEACHING = 'non_teaching', _('Non-Teaching Staff')
        ALL = 'all', _('All Staff')
    
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField()
    
    metric_category = models.CharField(
        max_length=20, 
        choices=MetricCategory.choices
    )
    measurement_type = models.CharField(
        max_length=20, 
        choices=MeasurementType.choices
    )
    target_type = models.CharField(max_length=20, choices=TargetType.choices)
    data_source = models.CharField(max_length=20, choices=DataSource.choices)
    
    applies_to_category = models.CharField(
        max_length=20, 
        choices=AppliesToCategory.choices
    )
    applies_to_job_grades = models.JSONField(
        blank=True, 
        null=True,
        help_text="List of job grade IDs"
    )
    
    weight_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    measurement_frequency = models.CharField(max_length=20)
    
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'hr_performance_metric'
        ordering = ['metric_category', 'name']
    
    def __str__(self):
        return f"{self.code} - {self.name}"


class PerformanceIndicatorTemplate(AuditedModel):
    """Appraisal templates for different roles"""
    name = models.CharField(max_length=255)
    job_title = models.ForeignKey(
        'JobTitle', 
        on_delete=models.CASCADE,
        related_name='appraisal_templates'
    )
    department = models.ForeignKey(
        'Department', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    appraisal_cycle_id = models.PositiveIntegerField(
        null=True, 
        blank=True
    )
    
    description = models.TextField(blank=True)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'hr_performance_indicator_template'
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} - {self.job_title.title}"


class TemplateMetricMapping(AuditedModel):
    """Maps metrics to templates"""
    template = models.ForeignKey(
        PerformanceIndicatorTemplate, 
        on_delete=models.CASCADE,
        related_name='metric_mappings'
    )
    metric = models.ForeignKey(
        PerformanceMetric, 
        on_delete=models.CASCADE
    )
    
    target_value = models.CharField(max_length=100, blank=True)
    weight_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    is_mandatory = models.BooleanField(default=True)
    evaluation_criteria = models.TextField(
        help_text="How to measure this metric"
    )
    
    class Meta:
        db_table = 'hr_template_metric_mapping'
        unique_together = ['template', 'metric']
    
    def __str__(self):
        return f"{self.template.name} - {self.metric.name}"


class AppraisalCycle(AuditedModel):
    """Appraisal periods/cycles"""
    
    class CycleType(models.TextChoices):
        ANNUAL = 'annual', _('Annual Review')
        MID_YEAR = 'mid_year', _('Mid-Year Review')
        QUARTERLY = 'quarterly', _('Quarterly Review')
        PROBATION = 'probation', _('Probation Review')
    
    class Status(models.TextChoices):
        PLANNED = 'planned', _('Planned')
        ACTIVE = 'active', _('Active')
        IN_REVIEW = 'in_review', _('In Review')
        COMPLETED = 'completed', _('Completed')
        CLOSED = 'closed', _('Closed')
    
    name = models.CharField(max_length=200)
    cycle_type = models.CharField(max_length=20, choices=CycleType.choices)
    
    start_date = models.DateField()
    end_date = models.DateField()
    
    self_appraisal_deadline = models.DateField()
    supervisor_appraisal_deadline = models.DateField()
    final_review_deadline = models.DateField()
    
    status = models.CharField(
        max_length=20, 
        choices=Status.choices,
        default=Status.PLANNED
    )
    
    applies_to_categories = models.JSONField(
        help_text="List of employee categories: teaching, non_teaching"
    )
    
    class Meta:
        db_table = 'hr_appraisal_cycle'
        ordering = ['-start_date']
    
    def __str__(self):
        return f"{self.name} ({self.start_date} - {self.end_date})"


class EmployeeAppraisal(AuditedModel):
    """Individual employee appraisals"""
    
    class FinalRating(models.TextChoices):
        OUTSTANDING = 'outstanding', _('Outstanding')
        EXCEEDS = 'exceeds_expectations', _('Exceeds Expectations')
        MEETS = 'meets_expectations', _('Meets Expectations')
        NEEDS_IMPROVEMENT = 'needs_improvement', _('Needs Improvement')
        UNSATISFACTORY = 'unsatisfactory', _('Unsatisfactory')
    
    class Status(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        IN_PROGRESS = 'in_progress', _('In Progress')
        COMPLETED = 'completed', _('Completed')
        DISPUTED = 'disputed', _('Disputed')
        CLOSED = 'closed', _('Closed')
    
    class RecommendedAction(models.TextChoices):
        PROMOTION = 'promotion', _('Promotion')
        SALARY_INCREMENT = 'salary_increment', _('Salary Increment')
        TRAINING = 'training', _('Training')
        WARNING = 'warning', _('Warning')
        TERMINATION = 'termination', _('Termination')
        NO_CHANGE = 'no_change', _('No Change')
    
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='appraisals'
    )
    appraisal_cycle = models.ForeignKey(
        AppraisalCycle, 
        on_delete=models.PROTECT
    )
    template = models.ForeignKey(
        PerformanceIndicatorTemplate, 
        on_delete=models.PROTECT
    )
    appraiser = models.ForeignKey(
        Employee, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='appraisals_as_appraiser',
        help_text="Direct supervisor"
    )
    
    appraisal_date = models.DateField(auto_now_add=True)
    review_period_start = models.DateField()
    review_period_end = models.DateField()
    
    # Self-assessment
    self_assessment_status = models.CharField(max_length=20, default='pending')
    self_assessment_date = models.DateField(null=True, blank=True)
    
    # Supervisor assessment
    supervisor_assessment_status = models.CharField(
        max_length=20, 
        default='pending'
    )
    supervisor_assessment_date = models.DateField(null=True, blank=True)
    
    # HOD review
    hod_review_status = models.CharField(max_length=20, default='pending')
    hod_review_date = models.DateField(null=True, blank=True)
    
    # Final rating
    final_rating = models.CharField(
        max_length=20, 
        choices=FinalRating.choices,
        null=True, 
        blank=True
    )
    final_score = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        null=True, 
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    
    overall_comments = models.TextField(blank=True)
    strengths = models.TextField(blank=True)
    areas_for_improvement = models.TextField(blank=True)
    development_plan = models.TextField(blank=True)
    
    recommended_action = models.CharField(
        max_length=20, 
        choices=RecommendedAction.choices,
        null=True, 
        blank=True
    )
    recommended_increment_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        null=True, 
        blank=True
    )
    
    status = models.CharField(
        max_length=20, 
        choices=Status.choices,
        default=Status.DRAFT
    )
    
    disputed = models.BooleanField(default=False)
    dispute_reason = models.TextField(blank=True)
    dispute_resolution = models.TextField(blank=True)
    
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='approved_appraisals'
    )
    approval_date = models.DateField(null=True, blank=True)
    
    class Meta:
        db_table = 'hr_employee_appraisal'
        ordering = ['-appraisal_date']
        indexes = [
            models.Index(fields=['employee', 'appraisal_cycle']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.employee.employee_no} - {self.appraisal_cycle.name}"


class AppraisalMetricScore(AuditedModel):
    """Individual metric scores within an appraisal"""
    appraisal = models.ForeignKey(
        EmployeeAppraisal, 
        on_delete=models.CASCADE,
        related_name='metric_scores'
    )
    metric = models.ForeignKey(PerformanceMetric, on_delete=models.PROTECT)
    
    # Self-rating
    self_rating = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        null=True, 
        blank=True
    )
    self_comments = models.TextField(blank=True)
    self_evidence = models.TextField(blank=True)
    
    # Supervisor rating
    supervisor_rating = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        null=True, 
        blank=True
    )
    supervisor_comments = models.TextField(blank=True)
    supervisor_evidence = models.TextField(blank=True)
    
    # Agreed rating (after discussion)
    agreed_rating = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        null=True, 
        blank=True
    )
    
    weight_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    weighted_score = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        null=True, 
        blank=True
    )
    
    target_value = models.CharField(max_length=100, blank=True)
    actual_value = models.CharField(max_length=100, blank=True)
    achievement_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        null=True, 
        blank=True
    )
    
    class Meta:
        db_table = 'hr_appraisal_metric_score'
        unique_together = ['appraisal', 'metric']
    
    def __str__(self):
        return f"{self.appraisal.employee.employee_no} - {self.metric.name}"


class EmployeePerformanceGoal(AuditedModel):
    """Individual performance goals and objectives for an employee"""
    class GoalStatus(models.TextChoices):
        NOT_STARTED = 'not_started', _('Not Started')
        IN_PROGRESS = 'in_progress', _('In Progress')
        COMPLETED = 'completed', _('Completed')
        ON_HOLD = 'on_hold', _('On Hold')
        CANCELLED = 'cancelled', _('Cancelled')

    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='performance_goals'
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=20,
        choices=GoalStatus.choices,
        default=GoalStatus.NOT_STARTED
    )
    progress_percentage = models.PositiveIntegerField(default=0)
    start_date = models.DateField()
    target_completion_date = models.DateField()
    actual_completion_date = models.DateField(null=True, blank=True)
    
    appraisal_cycle = models.ForeignKey(
        AppraisalCycle, 
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employee_goals'
    )

    class Meta:
        db_table = 'hr_employee_performance_goal'
        ordering = ['-target_completion_date']

    def __str__(self):
        return f"{self.employee.employee_no} - {self.title}"


class AcademicProductivity(AuditedModel):
    """Academic productivity tracking for teaching staff"""
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='academic_productivity'
    )
    academic_year = models.PositiveIntegerField()
    
    publications_count = models.PositiveIntegerField(default=0)
    journal_articles_count = models.PositiveIntegerField(default=0)
    conference_papers_count = models.PositiveIntegerField(default=0)
    books_authored = models.PositiveIntegerField(default=0)
    book_chapters = models.PositiveIntegerField(default=0)
    
    research_grants_value = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0
    )
    
    phd_students_supervised = models.PositiveIntegerField(default=0)
    masters_students_supervised = models.PositiveIntegerField(default=0)
    projects_completed = models.PositiveIntegerField(default=0)
    
    community_service_hours = models.DecimalField(
        max_digits=6, 
        decimal_places=2, 
        default=0
    )
    professional_memberships = models.PositiveIntegerField(default=0)
    patents_filed = models.PositiveIntegerField(default=0)
    
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'hr_academic_productivity'
        verbose_name_plural = 'Academic Productivity'
        unique_together = ['employee', 'academic_year']
        ordering = ['-academic_year', 'employee']
    
    def __str__(self):
        return f"{self.employee.employee_no} - {self.academic_year}"


class Publication(AuditedModel):
    """Individual publications"""
    
    class PublicationType(models.TextChoices):
        JOURNAL = 'journal', _('Journal Article')
        CONFERENCE = 'conference', _('Conference Paper')
        BOOK = 'book', _('Book')
        CHAPTER = 'chapter', _('Book Chapter')
        PATENT = 'patent', _('Patent')
    
    class Indexing(models.TextChoices):
        SCOPUS = 'scopus', _('Scopus')
        WEB_OF_SCIENCE = 'web_of_science', _('Web of Science')
        OTHER = 'other', _('Other')
    
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='publications'
    )
    publication_type = models.CharField(
        max_length=20, 
        choices=PublicationType.choices
    )
    
    title = models.CharField(max_length=500)
    co_authors = models.TextField(blank=True)
    journal_name = models.CharField(max_length=300, blank=True)
    conference_name = models.CharField(max_length=300, blank=True)
    
    publication_date = models.DateField()
    volume = models.CharField(max_length=50, blank=True)
    issue = models.CharField(max_length=50, blank=True)
    pages = models.CharField(max_length=50, blank=True)
    
    doi = models.CharField(max_length=200, blank=True)
    isbn = models.CharField(max_length=50, blank=True)
    
    impact_factor = models.DecimalField(
        max_digits=6, 
        decimal_places=3,
        null=True, 
        blank=True
    )
    is_peer_reviewed = models.BooleanField(default=False)
    indexing = models.CharField(
        max_length=20, 
        choices=Indexing.choices,
        blank=True
    )
    
    url = models.URLField(blank=True)
    citation_count = models.PositiveIntegerField(default=0)
    
    is_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    class Meta:
        db_table = 'hr_publication'
        ordering = ['-publication_date']
        indexes = [
            models.Index(fields=['employee', 'publication_date']),
        ]
    
    def __str__(self):
        return f"{self.employee.employee_no} - {self.title[:50]}"


class ResearchGrant(AuditedModel):
    """Research grants and funding"""
    
    class Status(models.TextChoices):
        APPLIED = 'applied', _('Applied')
        AWARDED = 'awarded', _('Awarded')
        ONGOING = 'ongoing', _('Ongoing')
        COMPLETED = 'completed', _('Completed')
        TERMINATED = 'terminated', _('Terminated')
    
    principal_investigator = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='grants_as_pi'
    )
    co_investigators = models.JSONField(
        blank=True, 
        null=True,
        help_text="List of employee IDs"
    )
    
    grant_title = models.CharField(max_length=500)
    funding_agency = models.CharField(max_length=300)
    
    grant_amount = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    
    start_date = models.DateField()
    end_date = models.DateField()
    
    status = models.CharField(max_length=20, choices=Status.choices)
    completion_percentage = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    publications_from_grant = models.PositiveIntegerField(default=0)
    
    class Meta:
        db_table = 'hr_research_grant'
        ordering = ['-start_date']
    
    def __str__(self):
        return f"{self.grant_title[:50]} - {self.funding_agency}"


class Peer360Feedback(AuditedModel):
    """360-degree feedback"""
    
    class FeedbackType(models.TextChoices):
        PEER = 'peer', _('Peer')
        SUBORDINATE = 'subordinate', _('Subordinate')
        STUDENT = 'student', _('Student')
        EXTERNAL = 'external', _('External')
    
    appraisal = models.ForeignKey(
        EmployeeAppraisal, 
        on_delete=models.CASCADE,
        related_name='peer_feedback'
    )
    feedback_provider = models.ForeignKey(
        Employee, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='feedback_provided'
    )
    feedback_type = models.CharField(max_length=20, choices=FeedbackType.choices)
    relationship_to_employee = models.CharField(max_length=100)
    
    feedback_date = models.DateField(auto_now_add=True)
    
    rating_scale_1_to_5 = models.DecimalField(
        max_digits=3, 
        decimal_places=2,
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    
    strengths = models.TextField()
    areas_for_improvement = models.TextField()
    additional_comments = models.TextField(blank=True)
    
    is_anonymous = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'hr_peer_360_feedback'
        ordering = ['-feedback_date']
    
    def __str__(self):
        return f"Feedback for {self.appraisal.employee.employee_no}"


class StudentFeedback(AuditedModel):
    """Student teaching evaluations"""
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='student_feedback'
    )
    course_id = models.PositiveIntegerField()
    academic_term_id = models.PositiveIntegerField()
    
    feedback_date = models.DateField()
    total_responses = models.PositiveIntegerField()
    
    average_rating = models.DecimalField(max_digits=3, decimal_places=2)
    teaching_effectiveness = models.DecimalField(max_digits=3, decimal_places=2)
    course_content_quality = models.DecimalField(max_digits=3, decimal_places=2)
    assessment_fairness = models.DecimalField(max_digits=3, decimal_places=2)
    availability_for_consultation = models.DecimalField(
        max_digits=3, 
        decimal_places=2
    )
    overall_satisfaction = models.DecimalField(max_digits=3, decimal_places=2)
    
    comments = models.TextField(
        blank=True,
        help_text="Aggregated, anonymized comments"
    )
    
    class Meta:
        db_table = 'hr_student_feedback'
        ordering = ['-feedback_date']
        unique_together = ['employee', 'course_id', 'academic_term_id']
    
    def __str__(self):
        return f"{self.employee.employee_no} - Course {self.course_id}"


class DevelopmentPlan(AuditedModel):
    """Employee development plans"""
    
    class Status(models.TextChoices):
        PLANNED = 'planned', _('Planned')
        IN_PROGRESS = 'in_progress', _('In Progress')
        COMPLETED = 'completed', _('Completed')
        CANCELLED = 'cancelled', _('Cancelled')
    
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='development_plans'
    )
    appraisal = models.ForeignKey(
        EmployeeAppraisal, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    development_area = models.CharField(max_length=255)
    recommended_training = models.TextField()
    timeline = models.CharField(max_length=200)
    budget_required = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        null=True, 
        blank=True
    )
    
    status = models.CharField(
        max_length=20, 
        choices=Status.choices,
        default=Status.PLANNED
    )
    completion_date = models.DateField(null=True, blank=True)
    impact_assessment = models.TextField(blank=True)
    
    class Meta:
        db_table = 'hr_development_plan'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.employee.employee_no} - {self.development_area}"

class PayrollPeriod(AuditedModel):
    """Payroll periods"""
    
    class PeriodType(models.TextChoices):
        MONTHLY = 'monthly', _('Monthly')
        BI_WEEKLY = 'bi_weekly', _('Bi-Weekly')
        WEEKLY = 'weekly', _('Weekly')
    
    class Status(models.TextChoices):
        OPEN = 'open', _('Open')
        PROCESSING = 'processing', _('Processing')
        CALCULATED = 'calculated', _('Calculated')
        APPROVED = 'approved', _('Approved')
        PAID = 'paid', _('Paid')
        CLOSED = 'closed', _('Closed')
    
    period_name = models.CharField(max_length=100)
    period_type = models.CharField(max_length=20, choices=PeriodType.choices)
    
    start_date = models.DateField()
    end_date = models.DateField()
    payment_date = models.DateField()
    
    status = models.CharField(
        max_length=20, 
        choices=Status.choices,
        default=Status.OPEN
    )
    
    total_gross_pay = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0
    )
    total_deductions = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0
    )
    total_net_pay = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0
    )
    employee_count = models.PositiveIntegerField(default=0)
    
    processing_started_at = models.DateTimeField(null=True, blank=True)
    processing_completed_at = models.DateTimeField(null=True, blank=True)
    
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='approved_payroll_periods'
    )
    approved_date = models.DateField(null=True, blank=True)
    
    locked = models.BooleanField(
        default=False,
        help_text="Prevents any changes"
    )
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'payroll_period'
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['status']),
        ]
        permissions = [
            ('can_unlock_payroll_period', 'Can unlock payroll period for re-run'),
        ]
    
    def __str__(self):
        return f"{self.period_name} ({self.start_date} - {self.end_date})"


class PayProfile(AuditedModel):
    """Salary structure templates"""
    
    class EmployeeCategory(models.TextChoices):
        TEACHING = 'teaching', _('Teaching Staff')
        NON_TEACHING = 'non_teaching', _('Non-Teaching Staff')
        CONTRACT = 'contract', _('Contract Staff')
        CASUAL = 'casual', _('Casual Worker')
    
    class PayFrequency(models.TextChoices):
        MONTHLY = 'monthly', _('Monthly')
        BI_WEEKLY = 'bi_weekly', _('Bi-Weekly')
        HOURLY = 'hourly', _('Hourly')
    
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    job_grade = models.ForeignKey(
        'JobGrade', 
        on_delete=models.PROTECT,
        related_name='pay_profiles'
    )
    employee_category = models.CharField(
        max_length=20, 
        choices=EmployeeCategory.choices
    )
    
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    pay_frequency = models.CharField(
        max_length=20, 
        choices=PayFrequency.choices
    )
    
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'payroll_pay_profile'
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} - {self.code}"


class PayrollAccount(AuditedModel):
    """
    Unified payroll account for both earnings and deductions.
    Each account links to GL accounts and controls how the item
    behaves during payroll calculation.
    """

    class AccountType(models.TextChoices):
        EARNING = 'earning', _('Earning')
        DEDUCTION = 'deduction', _('Deduction')

    class Category(models.TextChoices):
        # Earning categories
        BASIC = 'basic', _('Basic Salary')
        ALLOWANCE = 'allowance', _('Allowance')
        BONUS = 'bonus', _('Bonus')
        OVERTIME = 'overtime', _('Overtime')
        COMMISSION = 'commission', _('Commission')
        ARREARS = 'arrears', _('Arrears')
        # Deduction categories
        STATUTORY = 'statutory', _('Statutory')
        VOLUNTARY = 'voluntary', _('Voluntary')
        LOAN = 'loan', _('Loan Repayment')
        ADVANCE = 'advance', _('Advance Recovery')
        PENALTY = 'penalty', _('Penalty')

    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    account_type = models.CharField(max_length=20, choices=AccountType.choices)
    category = models.CharField(max_length=20, choices=Category.choices)

    # GL linkage — employee side
    employee_gl_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='payroll_accounts_employee',
        limit_choices_to={'available_in_payroll': True},
        help_text="GL account for employee portion"
    )

    # GL linkage — employer side (for items like NSSF, pension)
    has_employer_contribution = models.BooleanField(
        default=False,
        help_text="Does this account have an employer-side contribution?"
    )
    employer_gl_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='payroll_accounts_employer',
        limit_choices_to={'available_in_payroll': True},
        help_text="GL account for employer portion"
    )

    # --- Behaviour flags (earnings) ---
    used_for_paye = models.BooleanField(
        default=False,
        help_text="Include this earning in PAYE taxable income calculation"
    )
    used_for_nhif_shif = models.BooleanField(
        default=False,
        help_text="Include this earning in NHIF/SHIF contribution base"
    )
    used_for_pension = models.BooleanField(
        default=False,
        help_text="Include this earning in pension/NSSF contribution base"
    )

    # --- Behaviour flags (deductions) ---
    is_allowable_deduction = models.BooleanField(
        default=False,
        help_text="Deduction that reduces taxable income before PAYE"
    )
    used_for_housing_levy = models.BooleanField(
        default=False,
        help_text="This is the housing levy deduction"
    )
    is_mandatory = models.BooleanField(
        default=False,
        help_text="Automatically applied to all eligible employees"
    )

    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'payroll_account'
        ordering = ['account_type', 'sort_order', 'name']

    def __str__(self):
        return f"{self.code} - {self.name} ({self.get_account_type_display()})"


class EarningType(AuditedModel):
    """Master data for earnings"""
    
    class Category(models.TextChoices):
        BASIC = 'basic', _('Basic Salary')
        ALLOWANCE = 'allowance', _('Allowance')
        BONUS = 'bonus', _('Bonus')
        OVERTIME = 'overtime', _('Overtime')
        COMMISSION = 'commission', _('Commission')
        ARREARS = 'arrears', _('Arrears')
    
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=Category.choices)
    
    is_taxable = models.BooleanField(default=True)
    is_pensionable = models.BooleanField(default=False)
    
    gl_account_code = models.CharField(
        max_length=50,
        help_text="General Ledger account code"
    )
    description = models.TextField(blank=True)
    
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    
    class Meta:
        db_table = 'payroll_earning_type'
        ordering = ['sort_order', 'name']
    
    def __str__(self):
        return f"{self.code} - {self.name}"


class DeductionType(AuditedModel):
    """Master data for deductions"""
    
    class Category(models.TextChoices):
        STATUTORY = 'statutory', _('Statutory')
        VOLUNTARY = 'voluntary', _('Voluntary')
        LOAN = 'loan', _('Loan Repayment')
        ADVANCE = 'advance', _('Advance Recovery')
        PENALTY = 'penalty', _('Penalty')
    
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=Category.choices)
    
    is_mandatory = models.BooleanField(default=False)
    
    gl_account_code = models.CharField(
        max_length=50,
        help_text="Liability account code"
    )
    description = models.TextField(blank=True)
    
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    
    class Meta:
        db_table = 'payroll_deduction_type'
        ordering = ['sort_order', 'name']
    
    def __str__(self):
        return f"{self.code} - {self.name}"


class PayProfileComponent(AuditedModel):
    """Allowances/earnings in pay profile"""
    
    class CalculationMethod(models.TextChoices):
        FIXED = 'fixed', _('Fixed Amount')
        PERCENTAGE_BASIC = 'percentage_of_basic', _('Percentage of Basic')
        PERCENTAGE_GROSS = 'percentage_of_gross', _('Percentage of Gross')
    
    pay_profile = models.ForeignKey(
        PayProfile, 
        on_delete=models.CASCADE,
        related_name='components'
    )
    earning_type = models.ForeignKey(EarningType, on_delete=models.PROTECT)
    
    amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        null=True, 
        blank=True
    )
    calculation_method = models.CharField(
        max_length=30, 
        choices=CalculationMethod.choices
    )
    percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        null=True, 
        blank=True
    )
    
    is_taxable = models.BooleanField(default=True)
    is_pensionable = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'payroll_pay_profile_component'
        unique_together = ['pay_profile', 'earning_type']
    
    def __str__(self):
        return f"{self.pay_profile.name} - {self.earning_type.name}"


class EmployeePayProfile(AuditedModel):
    """Employee-specific pay profile assignments"""
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='pay_profiles'
    )
    pay_profile = models.ForeignKey(
        PayProfile, on_delete=models.PROTECT, null=True, blank=True
    )
    
    # Pay grade step — auto-resolves basic_salary from step amount
    pay_grade_step = models.ForeignKey(
        PayGradeStep,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employee_profiles',
        help_text="If set, basic_salary is derived from step amount"
    )

    basic_salary = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        help_text="Can override profile default"
    )
    currency = models.CharField(max_length=3, default='USD')
    
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    
    reason_for_change = models.TextField(
        blank=True,
        help_text="e.g., promotion, increment, adjustment"
    )
    
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='approved_pay_profiles'
    )
    approval_date = models.DateField(null=True, blank=True)
    
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'payroll_employee_pay_profile'
        ordering = ['-effective_from']
        indexes = [
            models.Index(fields=['employee', 'is_active']),
            models.Index(fields=['effective_from', 'effective_to']),
        ]
    
    def __str__(self):
        return f"{self.employee.employee_no} - {self.pay_profile.name}"

    def save(self, *args, **kwargs):
        # Auto-sync basic_salary from step when step is set
        if self.pay_grade_step and not kwargs.pop('skip_step_sync', False):
            self.basic_salary = self.pay_grade_step.amount
        super().save(*args, **kwargs)


class EmployeeEarning(AuditedModel):
    """Employee-specific earnings"""
    
    class CalculationBasis(models.TextChoices):
        FIXED = 'fixed', _('Fixed Amount')
        HOURS = 'hours', _('Hours Worked')
        RATE = 'rate', _('Rate Ã— Units')
        PERCENTAGE = 'percentage', _('Percentage')
    
    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending')
        APPROVED = 'approved', _('Approved')
        PROCESSED = 'processed', _('Processed')
    
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='earnings'
    )
    payroll_account = models.ForeignKey(
        PayrollAccount,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='employee_earnings',
        help_text="Select from payroll accounts of type 'earning'"
    )
    earning_type = models.ForeignKey(EarningType, on_delete=models.PROTECT, null=True, blank=True)
    payroll_period = models.ForeignKey(
        PayrollPeriod, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        help_text="Null for recurring earnings"
    )
    
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    calculation_basis = models.CharField(
        max_length=20, 
        choices=CalculationBasis.choices
    )
    units = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        null=True, 
        blank=True,
        help_text="e.g., hours worked, days"
    )
    rate = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        null=True, 
        blank=True,
        help_text="e.g., hourly rate"
    )
    
    is_recurring = models.BooleanField(
        default=False,
        help_text="Appears every payroll period"
    )
    is_one_time = models.BooleanField(
        default=False,
        help_text="Specific period only"
    )
    
    is_taxable = models.BooleanField(default=True)
    is_pensionable = models.BooleanField(default=False)
    
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    
    reason = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='approved_earnings'
    )
    approval_date = models.DateField(null=True, blank=True)
    
    status = models.CharField(
        max_length=20, 
        choices=Status.choices,
        default=Status.PENDING
    )
    
    class Meta:
        db_table = 'payroll_employee_earning'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['employee', 'payroll_period']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.employee.employee_no} - {self.earning_type.name} - {self.amount}"


class EmployeeDeduction(AuditedModel):
    """Employee-specific deductions"""
    
    class CalculationMethod(models.TextChoices):
        FIXED = 'fixed', _('Fixed Amount')
        PERCENTAGE_GROSS = 'percentage_of_gross', _('Percentage of Gross')
        PERCENTAGE_BASIC = 'percentage_of_basic', _('Percentage of Basic')
    
    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending')
        APPROVED = 'approved', _('Approved')
        PROCESSED = 'processed', _('Processed')
    
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='deductions'
    )
    payroll_account = models.ForeignKey(
        PayrollAccount,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='employee_deductions',
        help_text="Select from payroll accounts of type 'deduction'"
    )
    deduction_type = models.ForeignKey(
        DeductionType, 
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )
    payroll_period = models.ForeignKey(
        PayrollPeriod, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    calculation_method = models.CharField(
        max_length=30, 
        choices=CalculationMethod.choices
    )
    percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        null=True, 
        blank=True
    )
    
    is_recurring = models.BooleanField(default=False)
    is_one_time = models.BooleanField(default=False)
    
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    
    # For loan tracking
    max_deduction_amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        null=True, 
        blank=True,
        help_text="Total loan amount"
    )
    balance_remaining = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        null=True, 
        blank=True
    )
    
    reason = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='approved_deductions'
    )
    approval_date = models.DateField(null=True, blank=True)
    
    status = models.CharField(
        max_length=20, 
        choices=Status.choices,
        default=Status.PENDING
    )
    
    class Meta:
        db_table = 'payroll_employee_deduction'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['employee', 'payroll_period']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.employee.employee_no} - {self.deduction_type.name} - {self.amount}"


class GroupEarning(AuditedModel):
    """
    Earnings assigned to a job/pay grade group.
    All employees in this grade receive this earning.
    Employee-level earnings take precedence over group earnings.
    """
    job_grade = models.ForeignKey(
        'JobGrade',
        on_delete=models.CASCADE,
        related_name='group_earnings'
    )
    payroll_account = models.ForeignKey(
        PayrollAccount,
        on_delete=models.PROTECT,
        related_name='group_earnings',
        limit_choices_to={'account_type': 'earning'}
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    calculation_method = models.CharField(
        max_length=30,
        choices=[
            ('fixed', 'Fixed Amount'),
            ('percentage_of_basic', 'Percentage of Basic'),
        ],
        default='fixed'
    )
    percentage = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        help_text="Only used when calculation_method is percentage-based"
    )
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'payroll_group_earning'
        unique_together = ['job_grade', 'payroll_account']
        ordering = ['job_grade', 'payroll_account__sort_order']

    def __str__(self):
        return f"{self.job_grade.code} - {self.payroll_account.name} - {self.amount}"


class GroupDeduction(AuditedModel):
    """
    Deductions assigned to a job/pay grade group.
    All employees in this grade have this deduction.
    Employee-level deductions take precedence over group deductions.
    """
    job_grade = models.ForeignKey(
        'JobGrade',
        on_delete=models.CASCADE,
        related_name='group_deductions'
    )
    payroll_account = models.ForeignKey(
        PayrollAccount,
        on_delete=models.PROTECT,
        related_name='group_deductions',
        limit_choices_to={'account_type': 'deduction'}
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    calculation_method = models.CharField(
        max_length=30,
        choices=[
            ('fixed', 'Fixed Amount'),
            ('percentage_of_gross', 'Percentage of Gross'),
            ('percentage_of_basic', 'Percentage of Basic'),
        ],
        default='fixed'
    )
    percentage = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        help_text="Only used when calculation_method is percentage-based"
    )
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'payroll_group_deduction'
        unique_together = ['job_grade', 'payroll_account']
        ordering = ['job_grade', 'payroll_account__sort_order']

    def __str__(self):
        return f"{self.job_grade.code} - {self.payroll_account.name} - {self.amount}"


# ============================================================================
# PENSION SCHEME MODELS
# ============================================================================

class PensionScheme(AuditedModel):
    """
    Master pension scheme configuration.
    Supports IPP (Individual Pension Plans), occupational schemes, etc.
    """

    class SchemeType(models.TextChoices):
        IPP = 'ipp', _('Individual Pension Plan')
        OCCUPATIONAL = 'occupational', _('Occupational Scheme')
        NSSF = 'nssf', _('NSSF')
        CUSTOM = 'custom', _('Custom')

    class CalculationBasis(models.TextChoices):
        BASIC_SALARY = 'basic_salary', _('Basic Salary')
        GROSS_PAY = 'gross_pay', _('Gross Pay')
        FIXED_AMOUNT = 'fixed_amount', _('Fixed Amount')

    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    scheme_type = models.CharField(
        max_length=20,
        choices=SchemeType.choices,
        default=SchemeType.IPP
    )
    provider_name = models.CharField(max_length=200, blank=True)
    provider_account_number = models.CharField(max_length=100, blank=True)

    # Default contribution rates
    employee_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text="Default employee contribution rate (%)"
    )
    employer_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text="Default employer contribution rate (%)"
    )
    max_employee_contribution = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Monthly cap on employee contribution"
    )
    max_employer_contribution = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Monthly cap on employer contribution"
    )

    calculation_basis = models.CharField(
        max_length=20,
        choices=CalculationBasis.choices,
        default=CalculationBasis.BASIC_SALARY
    )

    # GL mapping via payroll account
    payroll_account = models.ForeignKey(
        PayrollAccount,
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='pension_schemes',
        help_text="Payroll account for GL mapping"
    )

    is_tax_exempt = models.BooleanField(
        default=True,
        help_text="Whether contributions qualify for tax relief"
    )
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)

    class Meta:
        db_table = 'payroll_pension_scheme'
        ordering = ['name']

    def __str__(self):
        return f"{self.code} - {self.name}"


class PensionSchemeGradeRate(AuditedModel):
    """
    Grade-specific rate overrides for a pension scheme.
    Overrides the scheme default rates for employees in a specific grade.
    """
    pension_scheme = models.ForeignKey(
        PensionScheme,
        on_delete=models.CASCADE,
        related_name='grade_rates'
    )
    job_grade = models.ForeignKey(
        'JobGrade',
        on_delete=models.CASCADE,
        related_name='pension_grade_rates'
    )
    employee_rate = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text="Employee contribution rate (%) for this grade"
    )
    employer_rate = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text="Employer contribution rate (%) for this grade"
    )
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'payroll_pension_grade_rate'
        unique_together = ['pension_scheme', 'job_grade']
        ordering = ['pension_scheme', 'job_grade']

    def __str__(self):
        return f"{self.pension_scheme.code} - {self.job_grade.code} ({self.employee_rate}%/{self.employer_rate}%)"


class EmployeePensionEnrollment(AuditedModel):
    """
    Employee enrollment in a pension scheme.
    Individual rate overrides take highest precedence.
    Precedence: Employee override > Grade rate > Scheme default
    """

    class Status(models.TextChoices):
        ACTIVE = 'active', _('Active')
        SUSPENDED = 'suspended', _('Suspended')
        EXITED = 'exited', _('Exited')

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='pension_enrollments'
    )
    pension_scheme = models.ForeignKey(
        PensionScheme,
        on_delete=models.CASCADE,
        related_name='enrollments'
    )
    membership_number = models.CharField(
        max_length=100, blank=True,
        help_text="External pension member ID"
    )

    # Individual rate overrides (null = use grade/scheme default)
    employee_rate = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Individual employee rate override (%)"
    )
    employer_rate = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Individual employer rate override (%)"
    )
    custom_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Fixed amount override (when basis is fixed_amount)"
    )

    enrollment_date = models.DateField()
    exit_date = models.DateField(null=True, blank=True)
    exit_reason = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
    )
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'payroll_pension_enrollment'
        unique_together = ['employee', 'pension_scheme']
        ordering = ['-enrollment_date']

    def __str__(self):
        return f"{self.employee.employee_no} - {self.pension_scheme.name} ({self.status})"

    def get_effective_rates(self):
        """
        Returns (employee_rate, employer_rate) using precedence:
        Employee override > Grade rate > Scheme default
        """
        ee_rate = self.employee_rate
        er_rate = self.employer_rate

        if ee_rate is None or er_rate is None:
            # Try grade rate
            try:
                grade = self.employee.job_grade
                if grade:
                    grade_rate = PensionSchemeGradeRate.objects.filter(
                        pension_scheme=self.pension_scheme,
                        job_grade=grade
                    ).first()
                    if grade_rate:
                        if ee_rate is None:
                            ee_rate = grade_rate.employee_rate
                        if er_rate is None:
                            er_rate = grade_rate.employer_rate
            except Exception:
                pass

        # Fall back to scheme defaults
        if ee_rate is None:
            ee_rate = self.pension_scheme.employee_rate
        if er_rate is None:
            er_rate = self.pension_scheme.employer_rate

        return ee_rate, er_rate


class PensionContribution(AuditedModel):
    """
    Monthly pension contribution record per employee per period.
    Tracks both employee and employer contributions.
    """
    enrollment = models.ForeignKey(
        EmployeePensionEnrollment,
        on_delete=models.CASCADE,
        related_name='contributions'
    )
    payroll_period = models.ForeignKey(
        'PayrollPeriod',
        on_delete=models.CASCADE,
        related_name='pension_contributions'
    )
    employee_amount = models.DecimalField(max_digits=12, decimal_places=2)
    employer_amount = models.DecimalField(max_digits=12, decimal_places=2)
    employee_rate_applied = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text="Rate that was applied for this period"
    )
    employer_rate_applied = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text="Rate that was applied for this period"
    )
    base_amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text="The salary base used for calculation"
    )
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'payroll_pension_contribution'
        unique_together = ['enrollment', 'payroll_period']
        ordering = ['-payroll_period__start_date']

    def __str__(self):
        return f"{self.enrollment.employee.employee_no} - {self.enrollment.pension_scheme.code} - {self.employee_amount + self.employer_amount}"

    @property
    def total_contribution(self):
        return self.employee_amount + self.employer_amount


class PayrollCalculation(AuditedModel):
    """Payroll calculation summary per employee per period"""
    
    class PaymentMethod(models.TextChoices):
        BANK_TRANSFER = 'bank_transfer', _('Bank Transfer')
        CHECK = 'check', _('Check')
        CASH = 'cash', _('Cash')
        MOBILE_MONEY = 'mobile_money', _('Mobile Money')
    
    class PaymentStatus(models.TextChoices):
        PENDING = 'pending', _('Pending')
        PAID = 'paid', _('Paid')
        FAILED = 'failed', _('Failed')
        CANCELLED = 'cancelled', _('Cancelled')
    
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='payroll_calculations'
    )
    payroll_period = models.ForeignKey(
        PayrollPeriod, 
        on_delete=models.CASCADE,
        related_name='calculations'
    )
    
    # Earnings
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2)
    total_earnings = models.DecimalField(max_digits=12, decimal_places=2)
    total_allowances = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0
    )
    total_overtime = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0
    )
    total_bonuses = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0
    )
    gross_pay = models.DecimalField(max_digits=12, decimal_places=2)
    
    # Deductions
    total_statutory_deductions = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0
    )
    total_voluntary_deductions = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0
    )
    total_loan_deductions = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0
    )
    total_deductions = models.DecimalField(max_digits=12, decimal_places=2)
    
    # Tax & Pension
    taxable_income = models.DecimalField(max_digits=12, decimal_places=2)
    tax_amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0
    )
    pension_employee = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0
    )
    pension_employer = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0
    )
    
    # Net Pay
    net_pay = models.DecimalField(max_digits=12, decimal_places=2)
    employer_cost = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        help_text="Includes employer contributions"
    )
    
    # Payment info
    payment_method = models.CharField(
        max_length=20, 
        choices=PaymentMethod.choices
    )
    bank_account_number = models.CharField(max_length=50, blank=True)
    payment_status = models.CharField(
        max_length=20, 
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING
    )
    payment_date = models.DateField(null=True, blank=True)
    payment_reference = models.CharField(max_length=100, blank=True)
    
    notes = models.TextField(blank=True)
    
    calculated_at = models.DateTimeField(auto_now_add=True)
    calculated_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='payroll_calculated'
    )
    
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='payroll_approved'
    )
    
    class Meta:
        db_table = 'payroll_calculation'
        ordering = ['-calculated_at']
        unique_together = ['employee', 'payroll_period']
        indexes = [
            models.Index(fields=['employee', 'payroll_period']),
            models.Index(fields=['payroll_period', 'payment_status']),
        ]
    
    def __str__(self):
        return f"{self.employee.employee_no} - {self.payroll_period.period_name}"


class PayrollCalculationDetail(AuditedModel):
    """Line items in payroll calculation"""
    
    class ItemType(models.TextChoices):
        EARNING = 'earning', _('Earning')
        DEDUCTION = 'deduction', _('Deduction')
    
    payroll_calculation = models.ForeignKey(
        PayrollCalculation, 
        on_delete=models.CASCADE,
        related_name='details'
    )
    
    item_type = models.CharField(max_length=20, choices=ItemType.choices)
    earning_type = models.ForeignKey(
        EarningType, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    deduction_type = models.ForeignKey(
        DeductionType, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    payroll_account = models.ForeignKey(
        PayrollAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='calculation_details',
        help_text="PayrollAccount used for this line item"
    )
    
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    
    is_taxable = models.BooleanField(default=False)
    is_pensionable = models.BooleanField(default=False)
    
    units = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        null=True, 
        blank=True
    )
    rate = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        null=True, 
        blank=True
    )
    
    gl_account_code = models.CharField(max_length=50)
    
    class Meta:
        db_table = 'payroll_calculation_detail'
        ordering = ['item_type', 'description']
    
    def __str__(self):
        return f"{self.payroll_calculation.employee.employee_no} - {self.description}"


class Payslip(AuditedModel):
    """Generated payslips"""
    payroll_calculation = models.OneToOneField(
        PayrollCalculation, 
        on_delete=models.CASCADE,
        related_name='payslip'
    )
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE,
        related_name='payslips'
    )
    payroll_period = models.ForeignKey(
        PayrollPeriod, 
        on_delete=models.CASCADE
    )
    
    payslip_number = models.CharField(max_length=100, unique=True)
    generation_date = models.DateTimeField(auto_now_add=True)
    
    pdf_path = models.FileField(
        upload_to='payslips/%Y/%m/',
        blank=True,
        help_text="Generated PDF file"
    )
    
    email_sent = models.BooleanField(default=False)
    email_sent_date = models.DateTimeField(null=True, blank=True)
    
    downloaded = models.BooleanField(default=False)
    download_date = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'payroll_payslip'
        ordering = ['-generation_date']
        indexes = [
            models.Index(fields=['employee', 'payroll_period']),
            models.Index(fields=['payslip_number']),
        ]
    
    def __str__(self):
        return f"Payslip {self.payslip_number} - {self.employee.employee_no}"


class PayrollAuditLog(TimestampedModel):
    """Audit trail for payroll changes"""
    
    class Action(models.TextChoices):
        CREATED = 'created', _('Created')
        CALCULATED = 'calculated', _('Calculated')
        APPROVED = 'approved', _('Approved')
        PAID = 'paid', _('Paid')
        REVERSED = 'reversed', _('Reversed')
        ADJUSTED = 'adjusted', _('Adjusted')
    
    payroll_period = models.ForeignKey(
        PayrollPeriod, 
        on_delete=models.CASCADE,
        related_name='audit_logs'
    )
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='payroll_audit_logs'
    )
    
    action = models.CharField(max_length=20, choices=Action.choices)
    old_values = models.JSONField(blank=True, null=True)
    new_values = models.JSONField(blank=True, null=True)
    reason = models.TextField(blank=True)
    
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    performed_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    class Meta:
        db_table = 'payroll_audit_log'
        ordering = ['-performed_at']
        indexes = [
            models.Index(fields=['payroll_period', 'performed_at']),
            models.Index(fields=['employee', 'action']),
        ]
    
    def __str__(self):
        return f"{self.get_action_display()} - {self.payroll_period.period_name}"


# ============================================================================
# HRMS ENHANCEMENT - PHASE 1: POSITION MANAGEMENT
# ============================================================================

class Position(AuditedModel):
    """
    Funded positions in the organization - separate from job titles.
    A JobTitle can have multiple Positions across departments.
    This enables headcount planning and budget control.
    """
    class PositionType(models.TextChoices):
        PERMANENT = 'permanent', _('Permanent')
        CONTRACT = 'contract', _('Contract')
        TEMPORARY = 'temporary', _('Temporary')
        GRANT_FUNDED = 'grant_funded', _('Grant Funded')
    
    class FundingStatus(models.TextChoices):
        FUNDED = 'funded', _('Funded')
        UNFUNDED = 'unfunded', _('Unfunded')
        FROZEN = 'frozen', _('Frozen')
    
    class VacancyStatus(models.TextChoices):
        VACANT = 'vacant', _('Vacant')
        OCCUPIED = 'occupied', _('Occupied')
        ON_HOLD = 'on_hold', _('On Hold')
    
    position_code = models.CharField(max_length=50, unique=True)  # e.g., POS-ACAD-001
    title = models.CharField(max_length=200)  # Display name
    
    job_title = models.ForeignKey(
        'JobTitle', 
        on_delete=models.PROTECT, 
        related_name='positions'
    )
    department = models.ForeignKey(
        'Department', 
        on_delete=models.PROTECT, 
        related_name='positions'
    )
    campus = models.ForeignKey(
        'Campus', 
        on_delete=models.PROTECT,
        related_name='positions'
    )
    
    reports_to_position = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='subordinate_positions'
    )
    
    position_type = models.CharField(max_length=20, choices=PositionType.choices)
    funding_status = models.CharField(
        max_length=20, 
        choices=FundingStatus.choices, 
        default=FundingStatus.FUNDED
    )
    vacancy_status = models.CharField(
        max_length=20, 
        choices=VacancyStatus.choices, 
        default=VacancyStatus.VACANT
    )
    
    # Budget allocation
    budgeted_salary = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    budget_code = models.CharField(max_length=50, blank=True)  # Links to finance
    fiscal_year = models.PositiveIntegerField(null=True, blank=True)
    
    # Dates
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    
    # Current holder (denormalized for performance)
    current_employee = models.ForeignKey(
        Employee, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='held_positions'
    )
    
    is_critical = models.BooleanField(
        default=False, 
        help_text="Key position requiring succession plan"
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'hr_position'
        ordering = ['department', 'position_code']
        indexes = [
            models.Index(fields=['department', 'vacancy_status']),
            models.Index(fields=['position_code']),
            models.Index(fields=['vacancy_status']),
            models.Index(fields=['funding_status']),
        ]
    
    def __str__(self):
        return f"{self.position_code} - {self.title}"
    
    def assign_employee(self, employee):
        """Assign an employee to this position"""
        self.current_employee = employee
        self.vacancy_status = self.VacancyStatus.OCCUPIED
        self.save()
    
    def vacate(self):
        """Mark position as vacant"""
        self.current_employee = None
        self.vacancy_status = self.VacancyStatus.VACANT
        self.save()


# ============================================================================
# HRMS ENHANCEMENT - PHASE 2: EMPLOYEE LIFECYCLE MANAGEMENT
# ============================================================================

class EmployeeLifecycleLog(TimestampedModel):
    """
    Comprehensive audit trail of all employee lifecycle events.
    Provides complete historical record for compliance and analytics.
    """
    class EventType(models.TextChoices):
        HIRED = 'hired', _('Hired')
        PROMOTION = 'promotion', _('Promotion')
        TRANSFER = 'transfer', _('Transfer')
        DEMOTION = 'demotion', _('Demotion')
        SALARY_CHANGE = 'salary_change', _('Salary Change')
        STATUS_CHANGE = 'status_change', _('Status Change')
        PROBATION_CONFIRMED = 'probation_confirmed', _('Probation Confirmed')
        PROBATION_EXTENDED = 'probation_extended', _('Probation Extended')
        SUSPENDED = 'suspended', _('Suspended')
        REINSTATED = 'reinstated', _('Reinstated')
        RESIGNED = 'resigned', _('Resigned')
        TERMINATED = 'terminated', _('Terminated')
        RETIRED = 'retired', _('Retired')
        CONTRACT_RENEWED = 'contract_renewed', _('Contract Renewed')
        CONTRACT_ENDED = 'contract_ended', _('Contract Ended')
        POSITION_ASSIGNED = 'position_assigned', _('Position Assigned')
        DEPARTMENT_CHANGED = 'department_changed', _('Department Changed')
    
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE, 
        related_name='lifecycle_logs'
    )
    event_type = models.CharField(max_length=30, choices=EventType.choices)
    event_date = models.DateField()
    effective_date = models.DateField()
    
    # Before/After snapshots
    old_status = models.CharField(max_length=50, blank=True)
    new_status = models.CharField(max_length=50)
    old_department = models.ForeignKey(
        'Department', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='lifecycle_logs_old_dept'
    )
    new_department = models.ForeignKey(
        'Department', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='lifecycle_logs_new_dept'
    )
    old_position = models.ForeignKey(
        'Position', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='lifecycle_logs_old_pos'
    )
    new_position = models.ForeignKey(
        'Position', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='lifecycle_logs_new_pos'
    )
    old_job_grade = models.ForeignKey(
        'JobGrade',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lifecycle_logs_old_grade'
    )
    new_job_grade = models.ForeignKey(
        'JobGrade',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lifecycle_logs_new_grade'
    )
    old_salary = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    new_salary = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    
    # Documentation
    reason = models.TextField()
    supporting_document = models.FileField(
        upload_to='lifecycle_docs/%Y/%m/', 
        blank=True
    )
    reference_number = models.CharField(
        max_length=100, 
        blank=True,
        help_text="e.g., termination letter number"
    )
    
    # Approval
    initiated_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='initiated_lifecycle_events'
    )
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='approved_lifecycle_events'
    )
    approval_date = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    metadata = models.JSONField(
        default=dict, 
        blank=True, 
        help_text="Additional event-specific data"
    )
    
    class Meta:
        db_table = 'hr_employee_lifecycle_log'
        ordering = ['-event_date', '-created_at']
        indexes = [
            models.Index(fields=['employee', 'event_type']),
            models.Index(fields=['event_date']),
            models.Index(fields=['event_type']),
            models.Index(fields=['effective_date']),
        ]
    
    def __str__(self):
        return f"{self.employee.employee_no} - {self.get_event_type_display()} - {self.event_date}"


# ============================================================================
# HRMS ENHANCEMENT - PHASE 3: BULK IMPORT FRAMEWORK
# ============================================================================

class BulkImportSession(AuditedModel):
    """
    Tracks Excel import sessions with validation and preview.
    Supports multiple import types with staged validation.
    """
    class ImportType(models.TextChoices):
        EMPLOYEES = 'employees', _('Employees')
        DEPARTMENTS = 'departments', _('Departments')
        POSITIONS = 'positions', _('Positions')
        ATTENDANCE = 'attendance', _('Attendance')
        LEAVE_BALANCES = 'leave_balances', _('Leave Balances')
        JOB_TITLES = 'job_titles', _('Job Titles')
        JOB_GRADES = 'job_grades', _('Job Grades')
    
    class Status(models.TextChoices):
        UPLOADED = 'uploaded', _('Uploaded')
        VALIDATING = 'validating', _('Validating')
        VALIDATED = 'validated', _('Validated')
        VALIDATION_FAILED = 'validation_failed', _('Validation Failed')
        PREVIEW = 'preview', _('Ready for Preview')
        IMPORTING = 'importing', _('Importing')
        COMPLETED = 'completed', _('Completed')
        PARTIALLY_COMPLETED = 'partially_completed', _('Partially Completed')
        FAILED = 'failed', _('Failed')
        CANCELLED = 'cancelled', _('Cancelled')
    
    import_type = models.CharField(max_length=30, choices=ImportType.choices)
    status = models.CharField(
        max_length=30, 
        choices=Status.choices, 
        default=Status.UPLOADED
    )
    
    # File tracking
    original_filename = models.CharField(max_length=255)
    uploaded_file = models.FileField(upload_to='bulk_imports/%Y/%m/')
    file_size_bytes = models.PositiveIntegerField()
    
    # Statistics
    total_rows = models.PositiveIntegerField(default=0)
    valid_rows = models.PositiveIntegerField(default=0)
    error_rows = models.PositiveIntegerField(default=0)
    warning_rows = models.PositiveIntegerField(default=0)
    imported_rows = models.PositiveIntegerField(default=0)
    skipped_rows = models.PositiveIntegerField(default=0)
    
    # Processing timestamps
    uploaded_at = models.DateTimeField(auto_now_add=True)
    validation_started_at = models.DateTimeField(null=True, blank=True)
    validation_completed_at = models.DateTimeField(null=True, blank=True)
    import_started_at = models.DateTimeField(null=True, blank=True)
    import_completed_at = models.DateTimeField(null=True, blank=True)
    
    # User tracking
    uploaded_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='bulk_imports'
    )
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='approved_imports'
    )
    approval_date = models.DateTimeField(null=True, blank=True)
    
    # Error log
    error_summary = models.TextField(blank=True)
    error_file = models.FileField(
        upload_to='bulk_imports/errors/%Y/%m/', 
        blank=True
    )
    
    # Options
    skip_duplicates = models.BooleanField(
        default=True,
        help_text="Skip rows with duplicate identifiers"
    )
    update_existing = models.BooleanField(
        default=False,
        help_text="Update existing records instead of skipping"
    )
    
    class Meta:
        db_table = 'hr_bulk_import_session'
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['import_type', 'status']),
            models.Index(fields=['uploaded_at']),
        ]
    
    def __str__(self):
        return f"{self.get_import_type_display()} - {self.original_filename} ({self.get_status_display()})"


class BulkImportRecord(models.Model):
    """
    Individual row from Excel with validation status.
    Each row is tracked separately for detailed error reporting.
    """
    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending Validation')
        VALID = 'valid', _('Valid')
        INVALID = 'invalid', _('Invalid')
        WARNING = 'warning', _('Valid with Warnings')
        IMPORTED = 'imported', _('Imported')
        SKIPPED = 'skipped', _('Skipped')
        FAILED = 'failed', _('Import Failed')
    
    import_session = models.ForeignKey(
        BulkImportSession, 
        on_delete=models.CASCADE, 
        related_name='records'
    )
    row_number = models.PositiveIntegerField()
    
    # Raw data from Excel
    raw_data = models.JSONField()
    
    # Validation results
    status = models.CharField(
        max_length=20, 
        choices=Status.choices, 
        default=Status.PENDING
    )
    validation_errors = models.JSONField(default=list, blank=True)
    validation_warnings = models.JSONField(default=list, blank=True)
    
    # Processed data (after transformation)
    processed_data = models.JSONField(null=True, blank=True)
    
    # Reference to created record
    created_employee_id = models.PositiveIntegerField(null=True, blank=True)
    created_object_type = models.CharField(max_length=50, blank=True)
    created_object_id = models.PositiveIntegerField(null=True, blank=True)
    
    # Error details
    error_message = models.TextField(blank=True)
    
    class Meta:
        db_table = 'hr_bulk_import_record'
        ordering = ['row_number']
        unique_together = ['import_session', 'row_number']
        indexes = [
            models.Index(fields=['import_session', 'status']),
        ]
    
    def __str__(self):
        return f"Row {self.row_number} - {self.get_status_display()}"


# ============================================================================
# HRMS ENHANCEMENT - PHASE 4: DOCUMENT MANAGEMENT
# ============================================================================

class EmployeeDocument(AuditedModel):
    """
    Centralized document storage for employees.
    Supports categorization, verification, and expiry tracking.
    """
    class DocumentCategory(models.TextChoices):
        IDENTIFICATION = 'identification', _('Identification')
        EDUCATION = 'education', _('Education')
        EMPLOYMENT = 'employment', _('Employment')
        CERTIFICATION = 'certification', _('Certification')
        MEDICAL = 'medical', _('Medical')
        LEGAL = 'legal', _('Legal')
        CONTRACT = 'contract', _('Contract')
        PERFORMANCE = 'performance', _('Performance')
        DISCIPLINARY = 'disciplinary', _('Disciplinary')
        FINANCIAL = 'financial', _('Financial')
        OTHER = 'other', _('Other')
    
    class VerificationStatus(models.TextChoices):
        PENDING = 'pending', _('Pending Verification')
        VERIFIED = 'verified', _('Verified')
        REJECTED = 'rejected', _('Rejected')
        EXPIRED = 'expired', _('Expired')
    
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE, 
        related_name='documents'
    )
    
    document_name = models.CharField(max_length=255)
    document_category = models.CharField(
        max_length=30, 
        choices=DocumentCategory.choices
    )
    document_type = models.CharField(
        max_length=100, 
        help_text="e.g., Passport, Degree Certificate, Contract"
    )
    description = models.TextField(blank=True)
    
    file = models.FileField(upload_to='employee_documents/%Y/%m/')
    file_size_bytes = models.PositiveIntegerField()
    mime_type = models.CharField(max_length=100)
    original_filename = models.CharField(max_length=255)
    
    # Document metadata
    document_number = models.CharField(
        max_length=100, 
        blank=True, 
        help_text="e.g., Passport Number, Certificate Number"
    )
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    issuing_authority = models.CharField(max_length=255, blank=True)
    issuing_country = models.ForeignKey(
        'Country',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='issued_documents'
    )
    
    # Verification
    verification_status = models.CharField(
        max_length=20, 
        choices=VerificationStatus.choices, 
        default=VerificationStatus.PENDING
    )
    verified_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='verified_employee_documents'
    )
    verification_date = models.DateField(null=True, blank=True)
    verification_notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    
    # Access control
    is_confidential = models.BooleanField(
        default=False,
        help_text="Only HR admins can view"
    )
    is_active = models.BooleanField(default=True)
    
    # Alert settings
    expiry_alert_days = models.PositiveIntegerField(
        default=30,
        help_text="Days before expiry to send alert"
    )
    expiry_alert_sent = models.BooleanField(default=False)
    expiry_alert_sent_date = models.DateTimeField(null=True, blank=True)
    
    # Version control
    version = models.PositiveIntegerField(default=1)
    previous_version = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='newer_versions'
    )
    
    class Meta:
        db_table = 'hr_employee_document'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['employee', 'document_category']),
            models.Index(fields=['expiry_date']),
            models.Index(fields=['verification_status']),
            models.Index(fields=['document_category']),
        ]
    
    def __str__(self):
        return f"{self.employee.employee_no} - {self.document_name}"
    
    @property
    def is_expired(self):
        """Check if document has expired"""
        if self.expiry_date:
            from django.utils import timezone
            return self.expiry_date < timezone.now().date()
        return False
    
    @property
    def days_until_expiry(self):
        """Calculate days until expiry"""
        if self.expiry_date:
            from django.utils import timezone
            delta = self.expiry_date - timezone.now().date()
            return delta.days
        return None


# ============================================================================
# HRMS ENHANCEMENT - PHASE 5: HR AUTOMATION
# ============================================================================

class HRAutomationRule(AuditedModel):
    """
    Configurable automation rules for HR events.
    Triggers notifications and workflows based on defined conditions.
    """
    class TriggerEvent(models.TextChoices):
        PROBATION_ENDING = 'probation_ending', _('Probation Ending Soon')
        CONTRACT_ENDING = 'contract_ending', _('Contract Ending Soon')
        DOCUMENT_EXPIRING = 'document_expiring', _('Document Expiring')
        BIRTHDAY = 'birthday', _('Employee Birthday')
        WORK_ANNIVERSARY = 'work_anniversary', _('Work Anniversary')
        APPRAISAL_DUE = 'appraisal_due', _('Appraisal Due')
        LEAVE_BALANCE_LOW = 'leave_balance_low', _('Leave Balance Low')
        NEW_HIRE_ONBOARDING = 'new_hire_onboarding', _('New Hire Onboarding')
        STATUS_CHANGE = 'status_change', _('Employment Status Change')
        CERTIFICATION_EXPIRING = 'certification_expiring', _('Certification Expiring')
        ATTENDANCE_THRESHOLD = 'attendance_threshold', _('Attendance Threshold')
        LEAVE_REQUEST_PENDING = 'leave_request_pending', _('Leave Request Pending')
    
    class ActionType(models.TextChoices):
        SEND_EMAIL = 'send_email', _('Send Email')
        SEND_NOTIFICATION = 'send_notification', _('Send In-App Notification')
        CREATE_TASK = 'create_task', _('Create Task')
        UPDATE_STATUS = 'update_status', _('Update Status')
        TRIGGER_WORKFLOW = 'trigger_workflow', _('Trigger Workflow')
        SEND_SMS = 'send_sms', _('Send SMS')
    
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    
    trigger_event = models.CharField(max_length=30, choices=TriggerEvent.choices)
    trigger_conditions = models.JSONField(
        default=dict, 
        help_text="Additional conditions in JSON format"
    )
    trigger_days_before = models.PositiveIntegerField(
        default=7, 
        help_text="Days before event to trigger"
    )
    
    action_type = models.CharField(max_length=30, choices=ActionType.choices)
    action_config = models.JSONField(
        default=dict, 
        help_text="Action configuration in JSON format"
    )
    
    # Recipients
    notify_employee = models.BooleanField(default=True)
    notify_supervisor = models.BooleanField(default=False)
    notify_hr = models.BooleanField(default=True)
    notify_department_head = models.BooleanField(default=False)
    additional_recipients = models.JSONField(
        default=list, 
        blank=True,
        help_text="List of email addresses or user IDs"
    )
    
    # Email template
    email_subject = models.CharField(max_length=255, blank=True)
    email_body_template = models.TextField(
        blank=True,
        help_text="Supports placeholders: {employee_name}, {event_date}, etc."
    )
    
    # Scheduling
    is_active = models.BooleanField(default=True)
    run_frequency = models.CharField(
        max_length=20,
        choices=[
            ('daily', 'Daily'),
            ('weekly', 'Weekly'),
            ('monthly', 'Monthly'),
        ],
        default='daily'
    )
    last_run = models.DateTimeField(null=True, blank=True)
    next_run = models.DateTimeField(null=True, blank=True)
    run_count = models.PositiveIntegerField(default=0)
    
    # Scope
    applies_to_departments = models.ManyToManyField(
        'Department',
        blank=True,
        related_name='automation_rules',
        help_text="Leave empty to apply to all departments"
    )
    applies_to_employee_categories = models.JSONField(
        default=list,
        blank=True,
        help_text="List of employee categories: teaching, non_teaching, etc."
    )
    
    class Meta:
        db_table = 'hr_automation_rule'
        ordering = ['name']
        indexes = [
            models.Index(fields=['trigger_event', 'is_active']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.code} - {self.name}"


class HRAutomationLog(TimestampedModel):
    """
    Log of automation executions for audit and debugging.
    """
    class Status(models.TextChoices):
        SUCCESS = 'success', _('Success')
        FAILED = 'failed', _('Failed')
        SKIPPED = 'skipped', _('Skipped')
        PARTIAL = 'partial', _('Partial Success')
    
    rule = models.ForeignKey(
        HRAutomationRule, 
        on_delete=models.CASCADE, 
        related_name='logs'
    )
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE, 
        related_name='automation_logs',
        null=True,
        blank=True
    )
    
    triggered_at = models.DateTimeField(auto_now_add=True)
    trigger_reason = models.CharField(max_length=255)
    action_taken = models.CharField(max_length=255)
    
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SUCCESS
    )
    error_message = models.TextField(blank=True)
    
    # Notification tracking
    recipients_notified = models.JSONField(default=list, blank=True)
    notification_sent_at = models.DateTimeField(null=True, blank=True)
    
    # Additional context
    context_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional context about the trigger"
    )
    
    class Meta:
        db_table = 'hr_automation_log'
        ordering = ['-triggered_at']
        indexes = [
            models.Index(fields=['rule', 'triggered_at']),
            models.Index(fields=['employee', 'triggered_at']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        emp_no = self.employee.employee_no if self.employee else 'N/A'
        return f"{self.rule.code} - {emp_no} - {self.triggered_at}"


# ============================================================================
# HRMS ENHANCEMENT - HR NOTIFICATION PREFERENCES
# ============================================================================

class HRNotificationPreference(AuditedModel):
    """
    User preferences for HR notifications.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='hr_notification_preferences'
    )
    
    # Email notifications
    email_probation_reminders = models.BooleanField(default=True)
    email_contract_reminders = models.BooleanField(default=True)
    email_document_expiry = models.BooleanField(default=True)
    email_leave_requests = models.BooleanField(default=True)
    email_appraisal_reminders = models.BooleanField(default=True)
    email_birthday_wishes = models.BooleanField(default=True)
    email_work_anniversary = models.BooleanField(default=True)
    
    # In-app notifications
    app_probation_reminders = models.BooleanField(default=True)
    app_contract_reminders = models.BooleanField(default=True)
    app_document_expiry = models.BooleanField(default=True)
    app_leave_requests = models.BooleanField(default=True)
    app_appraisal_reminders = models.BooleanField(default=True)
    
    # Frequency preferences
    digest_frequency = models.CharField(
        max_length=20,
        choices=[
            ('immediate', 'Immediate'),
            ('daily', 'Daily Digest'),
            ('weekly', 'Weekly Digest'),
        ],
        default='immediate'
    )
    
    quiet_hours_start = models.TimeField(null=True, blank=True)
    quiet_hours_end = models.TimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'hr_notification_preference'
    
    def __str__(self):
        return f"Notification Preferences - {self.user.username}"


# ============================================
# PAYROLL CONFIGURATION MODELS
# ============================================

class PayrollConfiguration(AuditedModel):
    """
    Global payroll configuration settings.
    Singleton pattern - only one active configuration per organization.
    """
    
    class PayFrequency(models.TextChoices):
        WEEKLY = 'weekly', _('Weekly')
        BI_WEEKLY = 'bi_weekly', _('Bi-Weekly')
        MONTHLY = 'monthly', _('Monthly')
    
    class FinancialYearStart(models.TextChoices):
        JANUARY = 'january', _('January (Calendar Year)')
        APRIL = 'april', _('April (UK/India)')
        JULY = 'july', _('July (East Africa)')
        OCTOBER = 'october', _('October (US Federal)')
    
    # Cycle Settings
    pay_frequency = models.CharField(
        max_length=20,
        choices=PayFrequency.choices,
        default=PayFrequency.MONTHLY
    )
    payroll_run_date = models.PositiveSmallIntegerField(
        default=25,
        help_text="Day of month when payroll is processed"
    )
    attendance_cutoff_date = models.PositiveSmallIntegerField(
        default=20,
        help_text="Last day for including attendance/OT in current cycle"
    )
    financial_year_start = models.CharField(
        max_length=20,
        choices=FinancialYearStart.choices,
        default=FinancialYearStart.JULY
    )
    is_locked = models.BooleanField(
        default=False,
        help_text="Lock prevents all payroll changes"
    )
    
    # Calculation Settings
    currency_code = models.CharField(max_length=3, default='KES')
    rounding_method = models.CharField(
        max_length=20,
        choices=[
            ('none', 'No Rounding (Exact)'),
            ('nearest', 'Nearest Whole Number'),
            ('up_10', 'Round Up to Nearest 10'),
        ],
        default='none'
    )
    overtime_multiplier = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        default=Decimal('1.5')
    )
    holiday_multiplier = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        default=Decimal('2.0')
    )
    enable_proration = models.BooleanField(
        default=True,
        help_text="Auto-calculate for mid-month joiners/leavers"
    )
    
    # Security Settings
    require_2fa_approval = models.BooleanField(default=False)
    allow_retroactive_changes = models.BooleanField(default=False)
    audit_retention_years = models.PositiveSmallIntegerField(default=7)
    
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'payroll_configuration'
        verbose_name = 'Payroll Configuration'
    
    def __str__(self):
        return f"Payroll Config ({self.pay_frequency})"
    
    @classmethod
    def get_active(cls):
        """Get the active configuration or create default."""
        config, created = cls.objects.get_or_create(
            is_active=True,
            defaults={'pay_frequency': 'monthly'}
        )
        return config


class PayslipTemplate(AuditedModel):
    """
    Template configuration for generating PDF payslips via the frontend editor.
    """
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(
        default=False,
        help_text="If true, this template will be used for all newly generated payslips"
    )
    
    config = models.JSONField(
        default=dict,
        help_text="JSON payload containing frontend visualization settings (colors, logo, toggles)"
    )
    
    class Meta:
        db_table = 'payroll_payslip_template'
        verbose_name = 'Payslip Template'
    
    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Automatically disable is_default on others if this one is set to default
        if self.is_default:
            PayslipTemplate.objects.exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class TaxBand(AuditedModel):
    """
    Income tax bands for PAYE calculation.
    Supports versioning via effective_date.
    """
    
    lower_limit = models.DecimalField(max_digits=12, decimal_places=2)
    upper_limit = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        null=True, 
        blank=True,
        help_text="Leave blank for top band (no upper limit)"
    )
    rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Tax rate as percentage (e.g., 30.00)"
    )
    
    effective_date = models.DateField(
        help_text="Date from which this band applies"
    )
    expiry_date = models.DateField(
        null=True,
        blank=True,
        help_text="Leave blank if currently active"
    )
    
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    
    class Meta:
        db_table = 'payroll_tax_band'
        ordering = ['effective_date', 'sort_order', 'lower_limit']
    
    def __str__(self):
        upper = f"{self.upper_limit:,.0f}" if self.upper_limit else "∞"
        return f"{self.lower_limit:,.0f} - {upper} @ {self.rate}%"
    
    @classmethod
    def get_current_bands(cls):
        """Get currently active tax bands."""
        today = timezone.now().date()
        return cls.objects.filter(
            is_active=True,
            effective_date__lte=today
        ).filter(
            models.Q(expiry_date__isnull=True) | models.Q(expiry_date__gte=today)
        ).order_by('sort_order', 'lower_limit')


class TaxRelief(AuditedModel):
    """
    Tax relief configurations (Personal, Insurance, Housing, etc.)
    """
    
    class ReliefType(models.TextChoices):
        PERSONAL = 'personal', _('Personal Relief')
        INSURANCE = 'insurance', _('Insurance Relief')
        HOUSING = 'housing', _('Affordable Housing Relief')
        PENSION = 'pension', _('Pension Relief')
        DISABILITY = 'disability', _('Disability Relief')
    
    relief_type = models.CharField(
        max_length=20,
        choices=ReliefType.choices,
        unique=True
    )
    name = models.CharField(max_length=100)
    
    # For fixed amount reliefs
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Fixed monthly relief amount"
    )
    
    # For percentage-based reliefs
    percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Relief as % of contribution"
    )
    max_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum relief cap"
    )
    
    effective_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'payroll_tax_relief'
    
    def __str__(self):
        return f"{self.name} - {self.amount or f'{self.percentage}%'}"


class StatutoryRate(AuditedModel):
    """
    Statutory deduction rates (NSSF, NHIF/SHA, Housing Levy, etc.)
    """
    
    class RateType(models.TextChoices):
        NSSF_TIER1 = 'nssf_tier1', _('NSSF Tier I')
        NSSF_TIER2 = 'nssf_tier2', _('NSSF Tier II')
        SHIF = 'shif', _('Social Health Insurance Fund')
        NHIF = 'nhif', _('NHIF (Legacy)')
        HOUSING_LEVY = 'housing_levy', _('Affordable Housing Levy')
        NITA = 'nita', _('NITA Levy')
    
    rate_type = models.CharField(
        max_length=20,
        choices=RateType.choices
    )
    name = models.CharField(max_length=100)
    
    # Rate configuration
    employee_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Employee contribution %"
    )
    employer_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Employer contribution %"
    )
    fixed_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Fixed amount if not percentage-based"
    )
    
    # Limits
    lower_limit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Income threshold for this tier"
    )
    upper_limit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )
    max_contribution = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum contribution cap"
    )
    
    effective_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_enabled = models.BooleanField(
        default=True,
        help_text="Whether this deduction is applied in calculations"
    )

    # Link to PayrollAccount for GL resolution
    payroll_account = models.ForeignKey(
        PayrollAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='statutory_rates',
        help_text="Payroll account (deduction type) linked to this statutory item"
    )

    class Meta:
        db_table = 'payroll_statutory_rate'
        ordering = ['rate_type', 'effective_date']
    
    def __str__(self):
        return f"{self.name} ({self.rate_type})"


class GLAccountMapping(AuditedModel):
    """
    Maps payroll items to General Ledger accounts for finance integration.
    """
    
    class MappingType(models.TextChoices):
        SALARY_EXPENSE = 'salary_expense', _('Gross Salary Expense')
        PAYE_LIABILITY = 'paye_liability', _('PAYE Payable')
        NSSF_LIABILITY = 'nssf_liability', _('NSSF Payable')
        NHIF_LIABILITY = 'nhif_liability', _('NHIF/SHIF Payable')
        HOUSING_LEVY = 'housing_levy', _('Housing Levy Payable')
        PENSION_LIABILITY = 'pension_liability', _('Pension Payable')
        NET_PAY_LIABILITY = 'net_pay_liability', _('Net Salary Payable')
        BANK_ACCOUNT = 'bank_account', _('Payroll Bank Account')
        ALLOWANCE_EXPENSE = 'allowance_expense', _('Allowances Expense')
        OVERTIME_EXPENSE = 'overtime_expense', _('Overtime Expense')
    
    mapping_type = models.CharField(
        max_length=30,
        choices=MappingType.choices,
        unique=True
    )
    gl_account_code = models.CharField(max_length=50)
    gl_account_name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'payroll_gl_mapping'
    
    def __str__(self):
        return f"{self.gl_account_code} - {self.gl_account_name}"


class ApprovalWorkflowLevel(AuditedModel):
    """
    Configurable approval workflow for payroll processing.
    """
    
    level_number = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    # Who can approve
    approver_role = models.CharField(
        max_length=100,
        help_text="Role name that can approve at this level"
    )
    
    # Permissions
    can_approve = models.BooleanField(default=True)
    can_reject = models.BooleanField(default=True)
    can_request_changes = models.BooleanField(default=True)
    
    # Notifications
    notify_on_pending = models.BooleanField(default=True)
    auto_escalate_hours = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Hours before auto-escalating to next level"
    )
    
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'payroll_approval_workflow'
        ordering = ['level_number']
    
    def __str__(self):
        return f"Level {self.level_number}: {self.name}"
