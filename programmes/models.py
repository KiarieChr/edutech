from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from student_settings.models import BaseModel


# ─────────────────────────────────────────────────────────────────────────────
# FACULTY
# ─────────────────────────────────────────────────────────────────────────────

class Faculty(BaseModel):
    """Top-level academic grouping — used by universities and large TVETs."""

    # Override BaseModel reverse names to avoid clash with workforce.Faculty
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='academic_faculty_created'
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='academic_faculty_updated'
    )

    name = models.CharField(max_length=200, unique=True)
    code = models.CharField(max_length=20, unique=True)
    dean = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='dean_of_faculties'
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'faculties'
        ordering = ['name']
        verbose_name_plural = 'Faculties'

    def __str__(self):
        return f"{self.code} — {self.name}"


# ─────────────────────────────────────────────────────────────────────────────
# DEPARTMENT
# ─────────────────────────────────────────────────────────────────────────────

class Department(BaseModel):
    """Academic department — optional grouping under a Faculty."""

    # Override BaseModel reverse names to avoid clash with workforce.Department
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='academic_department_created'
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='academic_department_updated'
    )

    faculty = models.ForeignKey(
        Faculty, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='departments'
    )
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True)
    head = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='head_of_departments'
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'departments'
        ordering = ['name']

    def __str__(self):
        return f"{self.code} — {self.name}"


# ─────────────────────────────────────────────────────────────────────────────
# PROGRAMME
# ─────────────────────────────────────────────────────────────────────────────

class Programme(BaseModel):
    """
    A tertiary academic programme — replaces 'Curriculum' for universities,
    colleges, and TVETs.
    Examples: BSc Computer Science, Diploma in Business, Certificate in Plumbing
    """
    LEVEL_CHOICES = [
        ('certificate', _('Certificate')),
        ('diploma',     _('Diploma')),
        ('degree',      _("Bachelor's Degree")),
        ('masters',     _("Master's Degree")),
        ('phd',         _('PhD / Doctorate')),
        ('short_course', _('Short Course / Professional')),
    ]
    DURATION_TYPE_CHOICES = [
        ('years',     _('Years')),
        ('months',    _('Months')),
        ('semesters', _('Semesters')),
        ('weeks',     _('Weeks')),
    ]

    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='programmes'
    )
    name = models.CharField(max_length=255, unique=True)
    code = models.CharField(max_length=30, unique=True)
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES)
    duration = models.PositiveIntegerField(help_text='Numeric duration, e.g. 3 (years)')
    duration_type = models.CharField(
        max_length=10, choices=DURATION_TYPE_CHOICES, default='years'
    )
    total_credit_units = models.PositiveIntegerField(
        default=0, help_text='Minimum credit units required to graduate'
    )
    description = models.TextField(blank=True)
    minimum_entry_requirements = models.TextField(
        blank=True, help_text='E.g. KCSE grade C+ or equivalent'
    )
    has_specialization = models.BooleanField(
        default=False, help_text='Whether this programme has named tracks/specializations'
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'programmes'
        ordering = ['level', 'name']

    def __str__(self):
        return f"{self.code} — {self.name}"

    @property
    def level_display(self):
        return dict(self.LEVEL_CHOICES).get(self.level, self.level)

    @property
    def duration_label(self):
        return f"{self.duration} {self.get_duration_type_display()}"


# ─────────────────────────────────────────────────────────────────────────────
# SPECIALIZATION
# ─────────────────────────────────────────────────────────────────────────────

class Specialization(BaseModel):
    """An optional track or major within a Programme."""
    programme = models.ForeignKey(
        Programme, on_delete=models.CASCADE, related_name='specializations'
    )
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'programme_specializations'
        unique_together = ['programme', 'code']
        ordering = ['name']

    def __str__(self):
        return f"{self.programme.code} / {self.name}"


# ─────────────────────────────────────────────────────────────────────────────
# PROGRAMME UNIT (Course/Module/Subject)
# ─────────────────────────────────────────────────────────────────────────────

class ProgrammeUnit(BaseModel):
    """
    A unit, course, or module within a programme.
    Replaces 'Subject' for tertiary institutions.
    Examples: CS101 – Introduction to Programming, MATH201 – Calculus II
    """
    UNIT_TYPE_CHOICES = [
        ('core',         _('Core / Compulsory')),
        ('elective',     _('Elective')),
        ('prerequisite', _('Prerequisite')),
        ('audit',        _('Audit Only')),
    ]
    SEMESTER_CHOICES = [
        ('1',    _('Semester 1')),
        ('2',    _('Semester 2')),
        ('both', _('Both Semesters')),
        ('any',  _('Any Semester')),
    ]

    programme = models.ForeignKey(
        Programme, on_delete=models.CASCADE, related_name='units'
    )
    specialization = models.ForeignKey(
        Specialization, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='units',
        help_text='Link only if this unit belongs to a specific specialization'
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=30, unique=True)
    credit_units = models.DecimalField(
        max_digits=4, decimal_places=1, default=3.0,
        help_text='Credit hours / units for this course'
    )
    year_of_study = models.PositiveIntegerField(
        default=1, help_text='Year in which this unit is normally taught (1, 2, 3…)'
    )
    semester_offered = models.CharField(
        max_length=10, choices=SEMESTER_CHOICES, default='1'
    )
    unit_type = models.CharField(
        max_length=15, choices=UNIT_TYPE_CHOICES, default='core'
    )
    description = models.TextField(blank=True)
    prerequisites = models.ManyToManyField(
        'self', symmetrical=False, blank=True,
        related_name='required_before',
        help_text='Units that must be passed before taking this unit'
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'programme_units'
        ordering = ['year_of_study', 'code']

    def __str__(self):
        return f"{self.code} – {self.name} (Yr {self.year_of_study})"


# ─────────────────────────────────────────────────────────────────────────────
# UNIT OFFERING (a unit running in a specific intake/semester)
# ─────────────────────────────────────────────────────────────────────────────

class UnitOffering(BaseModel):
    """A specific running of a ProgrammeUnit for a given intake and semester."""
    unit = models.ForeignKey(
        ProgrammeUnit, on_delete=models.CASCADE, related_name='offerings'
    )
    intake = models.ForeignKey(
        'student_settings.Intake', on_delete=models.CASCADE,
        related_name='unit_offerings'
    )
    semester = models.ForeignKey(
        'student_settings.Term', on_delete=models.CASCADE,
        related_name='unit_offerings',
        help_text='Term used as semester for tertiary mode'
    )
    lecturer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='unit_offerings'
    )
    room = models.CharField(max_length=100, blank=True)
    max_students = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'unit_offerings'
        unique_together = ['unit', 'intake', 'semester']
        ordering = ['intake', 'unit__year_of_study', 'unit__code']

    def __str__(self):
        return f"{self.unit.code} | {self.intake} | {self.semester}"


# ─────────────────────────────────────────────────────────────────────────────
# PROGRAMME ENROLLMENT
# ─────────────────────────────────────────────────────────────────────────────

class ProgrammeEnrollment(BaseModel):
    """
    A student enrolled in a specific programme.
    Replaces K-12 Enrollment for tertiary institutions.
    """
    STATUS_CHOICES = [
        ('active',     _('Active')),
        ('deferred',   _('Deferred')),
        ('completed',  _('Completed / Graduated')),
        ('withdrawn',  _('Withdrawn')),
        ('suspended',  _('Suspended')),
        ('transferred', _('Transferred')),
    ]

    student = models.ForeignKey(
        'student_management.Student', on_delete=models.CASCADE,
        related_name='programme_enrollments'
    )
    programme = models.ForeignKey(
        Programme, on_delete=models.PROTECT, related_name='enrollments'
    )
    specialization = models.ForeignKey(
        Specialization, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='enrollments'
    )
    intake = models.ForeignKey(
        'student_settings.Intake', on_delete=models.PROTECT,
        related_name='programme_enrollments'
    )
    registration_number = models.CharField(
        max_length=50, unique=True,
        help_text='Institution-issued registration/student number'
    )
    year_of_study = models.PositiveIntegerField(default=1)
    current_semester = models.ForeignKey(
        'student_settings.Term', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='current_programme_enrollments'
    )
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='active')
    enrollment_date = models.DateField()
    expected_graduation = models.DateField(null=True, blank=True)
    actual_graduation = models.DateField(null=True, blank=True)
    gpa = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True,
        help_text='Cumulative GPA — computed by the grading module'
    )
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'programme_enrollments'
        ordering = ['-enrollment_date']

    def __str__(self):
        return f"{self.registration_number} — {self.student} in {self.programme.code}"


# ─────────────────────────────────────────────────────────────────────────────
# UNIT REGISTRATION
# ─────────────────────────────────────────────────────────────────────────────

class UnitRegistration(BaseModel):
    """A student registering for a specific unit offering in a semester."""
    STATUS_CHOICES = [
        ('registered',  _('Registered')),
        ('dropped',     _('Dropped')),
        ('completed',   _('Completed')),
        ('failed',      _('Failed')),
        ('incomplete',  _('Incomplete')),
        ('audit',       _('Auditing')),
    ]

    programme_enrollment = models.ForeignKey(
        ProgrammeEnrollment, on_delete=models.CASCADE,
        related_name='unit_registrations'
    )
    offering = models.ForeignKey(
        UnitOffering, on_delete=models.CASCADE,
        related_name='registrations'
    )
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='registered')
    grade = models.CharField(max_length=5, blank=True, null=True)
    grade_points = models.DecimalField(
        max_digits=3, decimal_places=1, null=True, blank=True
    )
    marks = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    remarks = models.TextField(blank=True)

    class Meta:
        db_table = 'unit_registrations'
        unique_together = ['programme_enrollment', 'offering']
        ordering = ['-offering__semester__start_date']

    def __str__(self):
        return f"{self.programme_enrollment.registration_number} — {self.offering.unit.code}"
