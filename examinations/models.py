"""
Examinations App — Multi-curriculum grading, marks entry, and analysis.

Uses existing models (no duplication):
  - student_settings: Curriculum, CurriculumLevel, GradeStructure, AcademicYear, Term, Stream
  - timetable: Subject
  - academics: ClassSession, StudentSessionEnrollment
  - accounts: Student
"""
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone


class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="%(class)s_created"
    )
    is_deleted = models.BooleanField(default=False)

    class Meta:
        abstract = True


# =============================================================================
# GRADING SYSTEM — curriculum-specific, fully configurable
# =============================================================================

class GradingScale(BaseModel):
    """
    A named grading system tied to a curriculum.
    Examples:
      - "CBC Lower Primary" → EE, ME, AE, BE (rubric-based)
      - "8-4-4 Secondary" → A, A-, B+, B, ... E (points 12→1)
      - "IGCSE" → A*, A, B, C, D, E, U (percentage-based)
    """
    SCALE_TYPE_CHOICES = (
        ('rubric', 'Rubric / Competency'),       # CBC style: EE/ME/AE/BE
        ('points', 'Points-based'),               # 8-4-4 style: A=12, A-=11 ...
        ('percentage', 'Percentage-based'),        # IGCSE / generic: A*=90%+
    )

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=30, unique=True)
    curriculum = models.ForeignKey(
        'student_settings.Curriculum',
        on_delete=models.PROTECT,
        related_name='grading_scales'
    )
    curriculum_level = models.ForeignKey(
        'student_settings.CurriculumLevel',
        on_delete=models.PROTECT,
        related_name='grading_scales',
        null=True, blank=True,
        help_text='If set, this scale applies only to this level within the curriculum'
    )
    scale_type = models.CharField(max_length=20, choices=SCALE_TYPE_CHOICES)
    max_mark = models.DecimalField(
        max_digits=5, decimal_places=2, default=100,
        help_text='Maximum possible mark (e.g., 100)'
    )
    pass_mark = models.DecimalField(
        max_digits=5, decimal_places=2, default=40,
        help_text='Minimum mark to pass'
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['curriculum__name', 'name']
        db_table = 'exam_grading_scales'

    def __str__(self):
        return f"{self.name} ({self.curriculum.code})"


class GradingLevel(BaseModel):
    """
    Individual grade entry within a grading scale.
    Ordered by min_mark descending so the first match wins.
    """
    scale = models.ForeignKey(
        GradingScale, on_delete=models.CASCADE, related_name='levels'
    )
    grade = models.CharField(max_length=10, help_text='e.g., EE, A+, A*, B+')
    label = models.CharField(max_length=100, help_text='e.g., Exceeding Expectations, Excellent')
    min_mark = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text='Minimum mark for this grade (inclusive)'
    )
    max_mark = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text='Maximum mark for this grade (inclusive)'
    )
    points = models.DecimalField(
        max_digits=4, decimal_places=2, default=0,
        help_text='Grade points (e.g., 12 for A in 8-4-4, 4.0 for EE in CBC)'
    )
    order = models.PositiveIntegerField(
        help_text='Display order (1 = highest grade)'
    )
    color_hex = models.CharField(max_length=7, default='#6366f1', help_text='UI badge color')

    class Meta:
        ordering = ['scale', 'order']
        unique_together = ['scale', 'grade']
        db_table = 'exam_grading_levels'

    def __str__(self):
        return f"{self.scale.code}: {self.grade} ({self.min_mark}-{self.max_mark})"


# =============================================================================
# ASSESSMENT TYPES — configurable per curriculum
# =============================================================================

class AssessmentType(BaseModel):
    """
    Types of assessment within a curriculum, each with a weight.
    e.g., CBC Junior Secondary might have:
      - Opener (10%), Mid-Term (20%), End-Term (50%), Project (20%)
    8-4-4 might have:
      - CAT 1 (10%), CAT 2 (10%), Mid-Term (20%), End-Term (60%)
    """
    CATEGORY_CHOICES = (
        ('formative', 'Formative'),     # CATs, assignments, projects
        ('summative', 'Summative'),     # Mid-term, End-term, final exams
    )

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=30)
    curriculum = models.ForeignKey(
        'student_settings.Curriculum',
        on_delete=models.PROTECT,
        related_name='assessment_types'
    )
    curriculum_level = models.ForeignKey(
        'student_settings.CurriculumLevel',
        on_delete=models.PROTECT,
        related_name='assessment_types',
        null=True, blank=True,
        help_text='If set, this type applies only to this level'
    )
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='summative')
    weight = models.DecimalField(
        max_digits=5, decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Weight as percentage of total (e.g., 30.00 for 30%)'
    )
    max_mark = models.DecimalField(
        max_digits=5, decimal_places=2, default=100,
        help_text='Maximum possible raw mark for this assessment'
    )
    order = models.PositiveIntegerField(default=0, help_text='Display order')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['curriculum', 'order']
        unique_together = ['curriculum', 'code']
        db_table = 'exam_assessment_types'

    def __str__(self):
        return f"{self.name} ({self.curriculum.code}) - {self.weight}%"


# =============================================================================
# EXAMINATION — the actual exam event
# =============================================================================

class Examination(BaseModel):
    """
    An exam event: ties a specific assessment type to a class session + subject.
    e.g., "Grade 7 Math End-Term Exam — Term 1 2026"
    """
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('marks_entry', 'Marks Entry'),
        ('completed', 'Completed'),
        ('published', 'Published'),
    )

    name = models.CharField(max_length=200, blank=True)
    class_session = models.ForeignKey(
        'academics.ClassSession',
        on_delete=models.PROTECT,
        related_name='examinations'
    )
    subject = models.ForeignKey(
        'timetable.Subject',
        on_delete=models.PROTECT,
        related_name='examinations'
    )
    assessment_type = models.ForeignKey(
        AssessmentType,
        on_delete=models.PROTECT,
        related_name='examinations'
    )
    grading_scale = models.ForeignKey(
        GradingScale,
        on_delete=models.PROTECT,
        related_name='examinations'
    )

    # Schedule
    exam_date = models.DateField(null=True, blank=True)
    start_time = models.TimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)

    # Marks config
    max_mark = models.DecimalField(
        max_digits=5, decimal_places=2, default=100,
        help_text='Maximum possible mark for this specific exam'
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='published_exams'
    )

    # Teacher who set/administered the exam
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='administered_exams'
    )

    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ['-exam_date', 'subject__name']
        db_table = 'exam_examinations'

    def __str__(self):
        return self.name or f"{self.subject.name} {self.assessment_type.name}"

    def save(self, *args, **kwargs):
        if not self.name:
            session = self.class_session
            self.name = (
                f"{session.grade.name} {self.subject.name} "
                f"{self.assessment_type.name} — {session.term.name} {session.academic_year.name}"
            )
        super().save(*args, **kwargs)

    @property
    def curriculum(self):
        return self.class_session.curriculum

    @property
    def term(self):
        return self.class_session.term

    @property
    def academic_year(self):
        return self.class_session.academic_year

    @property
    def grade(self):
        return self.class_session.grade


# =============================================================================
# STUDENT MARKS
# =============================================================================

class StudentMark(BaseModel):
    """
    Individual student score for a specific examination.
    Grade, points, and remarks are auto-computed from the grading scale.
    """
    examination = models.ForeignKey(
        Examination, on_delete=models.CASCADE, related_name='marks'
    )
    student = models.ForeignKey(
        'accounts.Student',
        on_delete=models.PROTECT,
        related_name='exam_marks'
    )
    stream = models.ForeignKey(
        'student_settings.Stream',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='exam_marks'
    )

    # Raw score
    raw_mark = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text='Raw mark out of examination.max_mark'
    )
    # Normalized to scale max (computed)
    normalized_mark = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text='Mark normalized to grading_scale.max_mark'
    )
    # Auto-computed from grading scale
    grade = models.CharField(max_length=10, blank=True)
    points = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    grade_label = models.CharField(max_length=100, blank=True)

    # Status
    is_absent = models.BooleanField(default=False)
    is_exempted = models.BooleanField(default=False)
    teacher_remark = models.CharField(max_length=200, blank=True)

    # Audit
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='entered_marks'
    )

    class Meta:
        unique_together = ['examination', 'student']
        ordering = ['student__student__first_name']
        db_table = 'exam_student_marks'

    def __str__(self):
        return f"{self.student} — {self.examination}: {self.raw_mark}"

    def save(self, *args, **kwargs):
        if self.is_absent or self.is_exempted:
            self.raw_mark = None
            self.normalized_mark = None
            self.grade = ''
            self.points = 0
            self.grade_label = ''
        elif self.raw_mark is not None:
            self._compute_grade()
        super().save(*args, **kwargs)

    def _compute_grade(self):
        """Normalize mark and look up grade from the grading scale."""
        exam = self.examination
        scale = exam.grading_scale

        # Normalize: (raw / exam_max) * scale_max
        if exam.max_mark and exam.max_mark > 0:
            self.normalized_mark = (
                Decimal(str(self.raw_mark)) / Decimal(str(exam.max_mark))
            ) * Decimal(str(scale.max_mark))
        else:
            self.normalized_mark = self.raw_mark

        # Find matching grade level (ordered by min_mark desc → first match)
        levels = scale.levels.order_by('-min_mark')
        for level in levels:
            if self.normalized_mark >= level.min_mark:
                self.grade = level.grade
                self.points = level.points
                self.grade_label = level.label
                return

        # Fallback: lowest grade
        lowest = levels.last()
        if lowest:
            self.grade = lowest.grade
            self.points = lowest.points
            self.grade_label = lowest.label


# =============================================================================
# AGGREGATED RESULTS — per student per term (across all subjects)
# =============================================================================

class TermResult(BaseModel):
    """
    Aggregated result for a student in a term.
    Computed from all StudentMark records for that student + class_session.
    """
    student = models.ForeignKey(
        'accounts.Student',
        on_delete=models.PROTECT,
        related_name='term_results'
    )
    class_session = models.ForeignKey(
        'academics.ClassSession',
        on_delete=models.PROTECT,
        related_name='term_results'
    )
    stream = models.ForeignKey(
        'student_settings.Stream',
        on_delete=models.SET_NULL,
        null=True, blank=True,
    )

    # Aggregated scores
    total_marks = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    total_points = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    average_mark = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    average_points = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    subjects_taken = models.PositiveIntegerField(default=0)

    # Overall grade (computed from average)
    overall_grade = models.CharField(max_length=10, blank=True)
    overall_grade_label = models.CharField(max_length=100, blank=True)

    # Ranking
    class_rank = models.PositiveIntegerField(null=True, blank=True)
    stream_rank = models.PositiveIntegerField(null=True, blank=True)
    grade_rank = models.PositiveIntegerField(null=True, blank=True)
    total_in_class = models.PositiveIntegerField(null=True, blank=True)
    total_in_stream = models.PositiveIntegerField(null=True, blank=True)
    total_in_grade = models.PositiveIntegerField(null=True, blank=True)

    # Teacher remarks
    class_teacher_remark = models.TextField(blank=True)
    principal_remark = models.TextField(blank=True)

    # Status
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ['student', 'class_session']
        ordering = ['class_rank']
        db_table = 'exam_term_results'

    def __str__(self):
        return f"{self.student} — {self.class_session}: Avg {self.average_mark}"


# =============================================================================
# TERM SUBJECT RESULT — per student per subject per term
# =============================================================================

class TermSubjectResult(BaseModel):
    """
    Weighted aggregate of all assessment types for one student + one subject in a term.
    e.g., Math total = Opener*10% + MidTerm*20% + EndTerm*50% + Project*20%
    """
    term_result = models.ForeignKey(
        TermResult, on_delete=models.CASCADE, related_name='subject_results'
    )
    subject = models.ForeignKey(
        'timetable.Subject',
        on_delete=models.PROTECT,
        related_name='term_subject_results'
    )

    # Weighted total
    weighted_mark = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    grade = models.CharField(max_length=10, blank=True)
    points = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    grade_label = models.CharField(max_length=100, blank=True)

    # Per-assessment breakdown stored as JSON
    # e.g., {"opener": 45.0, "mid_term": 67.0, "end_term": 78.0}
    assessment_breakdown = models.JSONField(default=dict, blank=True)

    teacher_remark = models.CharField(max_length=200, blank=True)
    subject_rank = models.PositiveIntegerField(null=True, blank=True)
    total_in_subject = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        unique_together = ['term_result', 'subject']
        ordering = ['subject__name']
        db_table = 'exam_term_subject_results'

    def __str__(self):
        return f"{self.term_result.student} — {self.subject.name}: {self.weighted_mark}"


# =============================================================================
# REPORT CARD CONFIG — template per curriculum
# =============================================================================

class ReportCardTemplate(BaseModel):
    """
    Configuration for report card layout per curriculum/level.
    Controls which sections appear and their order.
    """
    name = models.CharField(max_length=100)
    curriculum = models.ForeignKey(
        'student_settings.Curriculum',
        on_delete=models.PROTECT,
        related_name='report_templates'
    )
    curriculum_level = models.ForeignKey(
        'student_settings.CurriculumLevel',
        on_delete=models.PROTECT,
        related_name='report_templates',
        null=True, blank=True,
    )

    # Section toggles
    show_marks = models.BooleanField(default=True)
    show_grades = models.BooleanField(default=True)
    show_points = models.BooleanField(default=True)
    show_rank = models.BooleanField(default=True)
    show_grade_distribution = models.BooleanField(default=False)
    show_attendance = models.BooleanField(default=True)
    show_teacher_remarks = models.BooleanField(default=True)
    show_principal_remarks = models.BooleanField(default=True)
    show_assessment_breakdown = models.BooleanField(default=True)
    show_previous_terms = models.BooleanField(default=False)

    # Display preferences
    show_class_average = models.BooleanField(default=True)
    show_highest_mark = models.BooleanField(default=False)
    show_lowest_mark = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'exam_report_card_templates'

    def __str__(self):
        return f"{self.name} ({self.curriculum.code})"
