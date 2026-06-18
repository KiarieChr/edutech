"""
Timetable App — PLANNING layer.

Responsibilities:
  - Define what subjects exist per curriculum.
  - Define physical/virtual rooms.
  - Define recurring weekly schedule slots (TimetableSlot).
  - Record planned topics (CurriculumUnit).
  - Record school-wide exceptions (holidays, closures).
  - Work allocation tracking (who teaches what, how many lessons).
  - Teacher availability management.
  - Timetable locking and versioning.

This app NEVER stores:
  - What actually happened.
  - Attendance.
  - Lesson completion.
  - Operational session data.

Timetable edits after a term starts set effective_from to today and expire the
old slot, so past PlannedLesson records are never retroactively altered.

Architecture:
  TimePeriod     → School-wide period definitions (e.g., Period 1: 08:00-08:40)
  Subject        → Academic subjects per curriculum
  Room           → Physical or virtual spaces
  WorkAllocation → Who teaches what subject to which class, how many times/week
  TimetableSlot  → Actual scheduled lessons (the output of timetabling)
  TeacherAvailability → When teachers are available/unavailable
  TimetableLock  → Prevents edits to finalized timetables
  TimetableVersion → History of timetable snapshots
"""
from django.db import models
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db.models import Sum, Count, Q
from django.utils import timezone


class Subject(models.Model):
    """
    An academic subject tied to a specific curriculum.
    e.g., Mathematics (CBC Grade 1-3), English (IGCSE Year 7)
    """
    SUBJECT_TYPE_CHOICES = (
        ('compulsory', 'Compulsory'),
        ('optional', 'Optional'),
        ('elective', 'Elective'),
    )
    
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    curriculum = models.ForeignKey(
        'student_settings.Curriculum',
        on_delete=models.PROTECT,
        related_name='subjects'
    )
    curriculum_level = models.ForeignKey(
        'student_settings.CurriculumLevel',
        on_delete=models.PROTECT,
        related_name='subjects',
        null=True, blank=True,
        help_text="If null, subject applies to all levels of the curriculum."
    )
    learning_area = models.ForeignKey(
        'student_settings.LearningArea',
        on_delete=models.SET_NULL,
        related_name='subjects',
        null=True, blank=True,
        help_text="Learning area / subject category"
    )
    subject_type = models.CharField(max_length=20, choices=SUBJECT_TYPE_CHOICES, default='compulsory')
    weekly_lessons = models.PositiveSmallIntegerField(default=5, help_text="Default lessons per week")
    color_hex = models.CharField(
        max_length=7, default='#6366f1',
        help_text="UI colour code for timetable and dashboard display."
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Subject'
        verbose_name_plural = 'Subjects'
        db_table = 'subjects'

    def __str__(self):
        return f"{self.code} – {self.name}"


class GradeSubjectMapping(models.Model):
    """
    Explicitly maps a Subject to a specific GradeStructure (e.g., Grade 7).
    Used to filter subjects dynamically when scheduling exams or allocating teachers.
    """
    grade = models.ForeignKey(
        'student_settings.GradeStructure',
        on_delete=models.CASCADE,
        related_name='subject_mappings'
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='grade_mappings'
    )
    is_core = models.BooleanField(
        default=True,
        help_text="Is this subject compulsory for this grade?"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Grade Subject Mapping'
        verbose_name_plural = 'Grade Subject Mappings'
        db_table = 'grade_subject_mappings'
        unique_together = ('grade', 'subject')

    def __str__(self):
        return f"{self.grade} -> {self.subject}"


class Room(models.Model):
    """
    A physical or virtual space where lessons take place.
    """
    ROOM_TYPE_CHOICES = (
        ('classroom', 'Classroom'),
        ('lab',       'Laboratory'),
        ('hall',      'Assembly Hall / Multipurpose'),
        ('library',   'Library'),
        ('field',     'Sports Field / Outdoor'),
        ('online',    'Online / Virtual'),
    )

    name = models.CharField(max_length=80)
    room_type = models.CharField(max_length=20, choices=ROOM_TYPE_CHOICES, default='classroom')
    # campus FK is optional — for single-campus schools this can be null
    campus = models.ForeignKey(
        'workforce.Campus',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='rooms'
    )
    capacity = models.PositiveSmallIntegerField(default=40)
    is_active = models.BooleanField(default=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Room'
        verbose_name_plural = 'Rooms'
        db_table = 'rooms'
    def __str__(self):
        return f"{self.name} ({self.get_room_type_display()})"


class TimetableSlot(models.Model):
    """
    A recurring weekly rule:
    "Every [day_of_week] from [start_time] to [end_time],
     [class_session/grade+term] has [subject] with [teacher] in [room]."

    This is the ONLY source of scheduling truth.
    It drives the PlannedLesson generation engine in scheduled_lessons.

    Mid-term edits:
      - Set effective_until = today - 1 day on the old record.
      - Create a new record with effective_from = today.
      - The generation engine deletes future pending PlannedLessons for the
        old slot and regenerates them from the new slot.
    """
    DAY_OF_WEEK_CHOICES = (
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
    )

    # --- Academic context ---
    # Links to academics.ClassSession (the Grade+Term enrollment container).
    # This is NOT the operational session; it is the term-grade planning unit.
    class_session = models.ForeignKey(
        'academics.ClassSession',
        on_delete=models.CASCADE,
        related_name='timetable_slots',
        help_text="The Grade+Term academic container this slot belongs to."
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.PROTECT,
        related_name='timetable_slots'
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='timetable_slots'
    )
    room = models.ForeignKey(
        Room,
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='timetable_slots'
    )

    # --- Schedule definition ---
    day_of_week = models.PositiveSmallIntegerField(choices=DAY_OF_WEEK_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    # Computed on save; stored for fast querying without datetime arithmetic
    duration_minutes = models.PositiveSmallIntegerField(editable=False, default=0)

    # --- Validity window ---
    # Allows mid-term corrections without mutating historical records.
    effective_from = models.DateField(
        help_text="Date from which this slot takes effect. Usually the term start date."
    )
    effective_until = models.DateField(
        null=True, blank=True,
        help_text="Date until which this slot is valid. Null = valid until term ends."
    )
    is_active = models.BooleanField(default=True)

    # --- Audit ---
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='timetable_slots_created'
    )

    class Meta:
        verbose_name = 'Timetable Slot'
        verbose_name_plural = 'Timetable Slots'
        db_table = 'timetable_slots'
        # Prevent the same class from being scheduled twice in the same period
        constraints = [
            models.UniqueConstraint(
                fields=['class_session', 'day_of_week', 'start_time', 'effective_from'],
                name='unique_class_timeslot',
                condition=models.Q(is_active=True)
            ),
            # Prevent room double-booking
            models.UniqueConstraint(
                fields=['room', 'day_of_week', 'start_time', 'effective_from'],
                name='unique_room_timeslot',
                condition=models.Q(is_active=True, room__isnull=False)
            ),
            # Prevent teacher double-booking
            models.UniqueConstraint(
                fields=['teacher', 'day_of_week', 'start_time', 'effective_from'],
                name='unique_teacher_timeslot',
                condition=models.Q(is_active=True)
            ),
        ]
        ordering = ['day_of_week', 'start_time']

    def clean(self):
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError("end_time must be after start_time.")
        if self.effective_until and self.effective_from and self.effective_until < self.effective_from:
            raise ValidationError("effective_until must be on or after effective_from.")

    def save(self, *args, **kwargs):
        # Compute duration
        from datetime import datetime
        if self.start_time and self.end_time:
            dummy = datetime(2000, 1, 1)
            start_dt = datetime.combine(dummy, self.start_time)
            end_dt   = datetime.combine(dummy, self.end_time)
            self.duration_minutes = int((end_dt - start_dt).total_seconds() // 60)
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.class_session} | {self.subject} | "
            f"{self.get_day_of_week_display()} {self.start_time:%H:%M}–{self.end_time:%H:%M}"
        )


class TimetableException(models.Model):
    """
    Blocks lesson generation for a specific date range.

    When affects_all_classes=True, the generation engine skips ALL slots on
    those dates and marks generated PlannedLessons as 'holiday'.

    When affects_all_classes=False, only the specified class_sessions are
    affected — useful for exam periods per stream/grade.
    """
    EXCEPTION_TYPE_CHOICES = (
        ('holiday',   'Public Holiday'),
        ('closure',   'School Closure'),
        ('exam',      'Examination Period'),
        ('event',     'School Event'),
        ('emergency', 'Emergency Closure'),
    )

    date_from = models.DateField()
    date_to   = models.DateField()
    reason    = models.CharField(max_length=255)
    exception_type = models.CharField(
        max_length=20, choices=EXCEPTION_TYPE_CHOICES, default='holiday'
    )
    affects_all_classes = models.BooleanField(
        default=True,
        help_text="If False, only the class_sessions listed below are affected."
    )
    class_sessions = models.ManyToManyField(
        'academics.ClassSession',
        blank=True,
        related_name='timetable_exceptions',
        help_text="Relevant only when affects_all_classes=False."
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date_from']
        verbose_name = 'Timetable Exception'
        verbose_name_plural = 'Timetable Exceptions'
        db_table = 'timetable_exceptions'

    def clean(self):
        if self.date_from and self.date_to and self.date_to < self.date_from:
            raise ValidationError("date_to must be on or after date_from.")

    def __str__(self):
        return f"{self.get_exception_type_display()}: {self.date_from} – {self.date_to} | {self.reason}"


class CurriculumUnit(models.Model):
    """
    A planned teaching unit/topic within a subject for a specific term-grade.

    Created before the term begins. Provides the content skeleton that teachers
    reference when logging what they taught (LessonSession.curriculum_unit).
    Drives curriculum coverage % calculation.
    """
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='curriculum_units'
    )
    # scope: which Grade+Term this unit is planned for
    class_session = models.ForeignKey(
        'academics.ClassSession',
        on_delete=models.CASCADE,
        related_name='curriculum_units'
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    # How many teaching weeks this unit is expected to take
    planned_lessons = models.PositiveSmallIntegerField(
        default=1,
        help_text="Expected number of lessons needed to complete this unit."
    )
    sequence_order = models.PositiveSmallIntegerField(
        default=1,
        help_text="Order in which this unit should be taught."
    )
    is_compulsory = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['class_session', 'subject', 'sequence_order']
        verbose_name = 'Curriculum Unit'
        verbose_name_plural = 'Curriculum Units'
        db_table = 'curriculum_units'

    def __str__(self):
        return f"{self.subject.code} | Unit {self.sequence_order}: {self.title}"


# ============================================================================
# NEW MODELS FOR COMPREHENSIVE TIMETABLING ENGINE
# ============================================================================


class TimePeriod(models.Model):
    """
    School-wide period definition.
    
    Defines standard lesson slots that apply across the school.
    Example: Period 1 (08:00-08:40), Period 2 (08:45-09:25), Break (10:00-10:30)
    
    These are separate from TimetableSlot to allow:
    - Consistent period naming across all classes
    - Break periods (not schedulable lessons)
    - Easy drag-and-drop UI (drop to Period 3 rather than arbitrary times)
    """
    PERIOD_TYPE_CHOICES = (
        ('lesson',    'Lesson Period'),
        ('break',     'Break'),
        ('assembly',  'Assembly'),
        ('lunch',     'Lunch'),
        ('activity',  'Extra-curricular'),
    )

    name = models.CharField(
        max_length=50,
        help_text="Display name, e.g., 'Period 1', 'Morning Break'"
    )
    short_name = models.CharField(
        max_length=10,
        help_text="Short code for UI, e.g., 'P1', 'BRK'"
    )
    period_type = models.CharField(
        max_length=20,
        choices=PERIOD_TYPE_CHOICES,
        default='lesson'
    )
    start_time = models.TimeField()
    end_time = models.TimeField()
    order = models.PositiveSmallIntegerField(
        help_text="Sort order within a day (1=first period)"
    )
    is_schedulable = models.BooleanField(
        default=True,
        help_text="Can lessons be scheduled in this period?"
    )
    # Academic year scope (periods may change between years)
    academic_year = models.ForeignKey(
        'student_settings.AcademicYear',
        on_delete=models.CASCADE,
        related_name='time_periods',
        null=True, blank=True,
        help_text="If null, applies to all academic years"
    )
    # Day-specific periods (e.g., Friday has shorter periods)
    applies_to_days = models.CharField(
        max_length=20,
        default='0,1,2,3,4,5',
        help_text="Comma-separated day indices (0=Mon, 5=Sat). Empty = all days."
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'start_time']
        verbose_name = 'Time Period'
        verbose_name_plural = 'Time Periods'
        db_table = 'time_periods'
        constraints = [
            models.UniqueConstraint(
                fields=['academic_year', 'order'],
                name='unique_period_order_per_year',
                condition=Q(is_active=True)
            ),
        ]

    def clean(self):
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError("End time must be after start time.")

    @property
    def duration_minutes(self):
        """Calculate duration in minutes."""
        from datetime import datetime
        if self.start_time and self.end_time:
            dummy = datetime(2000, 1, 1)
            start_dt = datetime.combine(dummy, self.start_time)
            end_dt = datetime.combine(dummy, self.end_time)
            return int((end_dt - start_dt).total_seconds() // 60)
        return 0

    def applies_to_day(self, day_of_week):
        """Check if this period applies to a specific day (0=Monday)."""
        if not self.applies_to_days:
            return True
        applicable_days = [int(d.strip()) for d in self.applies_to_days.split(',') if d.strip()]
        return day_of_week in applicable_days

    def __str__(self):
        return f"{self.name} ({self.start_time:%H:%M}–{self.end_time:%H:%M})"


class WorkAllocation(models.Model):
    """
    Defines who teaches what subject to which class, and how many lessons per week.
    
    This is the INPUT to the timetabling process.
    Work allocations represent the REQUIREMENTS that must be satisfied.
    TimetableSlots represent the OUTPUT (actual scheduled lessons).
    
    Example:
    - Teacher: Mr. Smith
    - Subject: Mathematics
    - Class Session: Grade 5 - Term 1 2026
    - Lessons Per Week: 5
    
    The timetabling engine will create 5 TimetableSlots to satisfy this allocation.
    """
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='work_allocations'
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.PROTECT,
        related_name='work_allocations'
    )
    class_session = models.ForeignKey(
        'academics.ClassSession',
        on_delete=models.CASCADE,
        related_name='work_allocations'
    )
    lessons_per_week = models.PositiveSmallIntegerField(
        default=1,
        help_text="Number of lessons this teacher should teach this subject to this class weekly"
    )
    # Room preference (soft constraint)
    preferred_room = models.ForeignKey(
        Room,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='preferred_allocations',
        help_text="Preferred room for this allocation (soft constraint)"
    )
    # Room requirement (hard constraint) - e.g., Science must be in lab
    required_room_type = models.CharField(
        max_length=20,
        choices=Room.ROOM_TYPE_CHOICES,
        blank=True,
        help_text="Required room type (hard constraint). Empty = any room."
    )
    # Priority affects scheduling order
    priority = models.PositiveSmallIntegerField(
        default=5,
        help_text="1=highest priority (scheduled first), 10=lowest"
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='work_allocations_created'
    )

    class Meta:
        db_table = 'work_allocations'
        verbose_name = 'Work Allocation'
        verbose_name_plural = 'Work Allocations'
        constraints = [
            # One allocation per teacher-subject-class combination
            models.UniqueConstraint(
                fields=['teacher', 'subject', 'class_session'],
                name='unique_work_allocation',
                condition=Q(is_active=True)
            ),
        ]
        ordering = ['priority', 'class_session', 'subject']
        indexes = [
            models.Index(fields=['teacher', 'class_session']),
            models.Index(fields=['subject', 'class_session']),
            models.Index(fields=['class_session', 'is_active']),
        ]

    @property
    def scheduled_lessons(self):
        """Count how many TimetableSlots exist for this allocation."""
        return TimetableSlot.objects.filter(
            teacher=self.teacher,
            subject=self.subject,
            class_session=self.class_session,
            is_active=True
        ).count()

    @property
    def remaining_lessons(self):
        """How many more lessons need to be scheduled."""
        return max(0, self.lessons_per_week - self.scheduled_lessons)

    @property
    def is_fully_allocated(self):
        """Check if all required lessons have been scheduled."""
        return self.scheduled_lessons >= self.lessons_per_week

    @property
    def allocation_percentage(self):
        """Percentage of required lessons that have been scheduled."""
        if self.lessons_per_week == 0:
            return 100
        return min(100, round((self.scheduled_lessons / self.lessons_per_week) * 100, 1))

    def __str__(self):
        return (
            f"{self.teacher.get_full_name() or self.teacher.username} → "
            f"{self.subject.code} → {self.class_session.name} "
            f"({self.scheduled_lessons}/{self.lessons_per_week} lessons)"
        )


class TeacherAvailability(models.Model):
    """
    Records when a teacher is NOT available for scheduling.
    
    Used for:
    - Part-time teachers (only available certain days/times)
    - Personal commitments
    - Meetings
    - Administrative duties
    
    The conflict engine checks this before allowing a slot assignment.
    """
    AVAILABILITY_TYPE_CHOICES = (
        ('unavailable', 'Not Available'),      # Cannot schedule
        ('preferred',   'Preferred'),          # Soft preference for this time
        ('avoid',       'Avoid if Possible'),  # Soft constraint to avoid
    )
    RECURRENCE_CHOICES = (
        ('once',      'One-time'),
        ('weekly',    'Weekly Recurring'),
        ('term',      'Entire Term'),
    )

    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='availability_records'
    )
    availability_type = models.CharField(
        max_length=20,
        choices=AVAILABILITY_TYPE_CHOICES,
        default='unavailable'
    )
    recurrence = models.CharField(
        max_length=20,
        choices=RECURRENCE_CHOICES,
        default='weekly'
    )
    # For one-time or term-long unavailability
    date_from = models.DateField(null=True, blank=True)
    date_to = models.DateField(null=True, blank=True)
    # For weekly recurring
    day_of_week = models.PositiveSmallIntegerField(
        choices=TimetableSlot.DAY_OF_WEEK_CHOICES,
        null=True, blank=True
    )
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    # If times are null, entire day is affected
    all_day = models.BooleanField(default=False)
    
    reason = models.CharField(max_length=255, blank=True)
    academic_year = models.ForeignKey(
        'student_settings.AcademicYear',
        on_delete=models.CASCADE,
        related_name='teacher_availabilities',
        null=True, blank=True
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='availability_records_created'
    )

    class Meta:
        verbose_name = 'Teacher Availability'
        db_table = 'teacher_availabilities'
        verbose_name_plural = 'Teacher Availabilities'
        ordering = ['teacher', 'day_of_week', 'start_time']
        indexes = [
            models.Index(fields=['teacher', 'day_of_week']),
            models.Index(fields=['teacher', 'is_active']),
        ]

    def clean(self):
        if self.recurrence == 'weekly' and self.day_of_week is None:
            raise ValidationError("Weekly recurring availability requires day_of_week.")
        if not self.all_day and self.start_time and self.end_time:
            if self.start_time >= self.end_time:
                raise ValidationError("End time must be after start time.")

    def conflicts_with(self, day, start_time, end_time, check_date=None):
        """
        Check if this availability record conflicts with a proposed slot.
        
        Returns True if the teacher CANNOT be scheduled at this time.
        """
        if not self.is_active:
            return False
        if self.availability_type != 'unavailable':
            return False

        # Check date range for one-time or term availability
        if self.recurrence in ('once', 'term'):
            if check_date:
                if self.date_from and check_date < self.date_from:
                    return False
                if self.date_to and check_date > self.date_to:
                    return False
            else:
                return False  # Can't check without a date

        # Check day of week for weekly recurring
        if self.recurrence == 'weekly':
            if self.day_of_week != day:
                return False

        # If all-day, any time conflicts
        if self.all_day:
            return True

        # Check time overlap
        if self.start_time and self.end_time:
            # Times overlap if: start1 < end2 AND start2 < end1
            return self.start_time < end_time and start_time < self.end_time

        return False

    def __str__(self):
        if self.all_day:
            time_str = "All day"
        elif self.start_time and self.end_time:
            time_str = f"{self.start_time:%H:%M}–{self.end_time:%H:%M}"
        else:
            time_str = "Unspecified time"

        if self.recurrence == 'weekly':
            day_str = dict(TimetableSlot.DAY_OF_WEEK_CHOICES).get(self.day_of_week, '')
            return f"{self.teacher.get_full_name() or self.teacher.username}: {self.get_availability_type_display()} on {day_str} {time_str}"
        else:
            return f"{self.teacher.get_full_name() or self.teacher.username}: {self.get_availability_type_display()} ({self.recurrence})"


class TimetableLock(models.Model):
    """
    Prevents modifications to a timetable once it's been finalized.
    
    Lock levels:
    - draft:    Fully editable
    - review:   Editable by admin only
    - locked:   No edits allowed (requires explicit unlock)
    - archived: Historical record, cannot be modified
    
    Locking can be at class_session level or entire academic term level.
    """
    LOCK_LEVEL_CHOICES = (
        ('draft',    'Draft - Fully Editable'),
        ('review',   'Under Review - Admin Only'),
        ('locked',   'Locked - No Edits'),
        ('archived', 'Archived - Historical'),
    )

    # Lock can be for specific class or entire term
    class_session = models.OneToOneField(
        'academics.ClassSession',
        on_delete=models.CASCADE,
        related_name='timetable_lock',
        null=True, blank=True
    )
    term = models.ForeignKey(
        'student_settings.Term',
        on_delete=models.CASCADE,
        related_name='timetable_locks',
        null=True, blank=True
    )
    lock_level = models.CharField(
        max_length=20,
        choices=LOCK_LEVEL_CHOICES,
        default='draft'
    )
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='timetables_locked'
    )
    unlock_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Timetable Lock'
        verbose_name_plural = 'Timetable Locks'

    def clean(self):
        if not self.class_session and not self.term:
            raise ValidationError("Either class_session or term must be specified.")
        if self.class_session and self.term:
            raise ValidationError("Specify either class_session OR term, not both.")

    def lock(self, user, level='locked'):
        """Lock the timetable."""
        self.lock_level = level
        self.locked_at = timezone.now()
        self.locked_by = user
        self.save()

    def unlock(self, user, reason=''):
        """Unlock the timetable (returns to draft)."""
        self.lock_level = 'draft'
        self.unlock_reason = reason
        self.locked_at = None
        self.locked_by = None
        self.save()

    @property
    def is_editable(self):
        """Check if timetable can be edited."""
        return self.lock_level in ('draft', 'review')

    @property
    def is_admin_only(self):
        """Check if only admin can edit."""
        return self.lock_level == 'review'

    def __str__(self):
        target = self.class_session or self.term
        return f"{target}: {self.get_lock_level_display()}"

    class Meta:
        db_table = 'timetable_locks'


class TimetableVersion(models.Model):
    """
    Stores snapshots of timetable configurations for history and rollback.
    
    Created automatically when:
    - Timetable is locked
    - Major changes are made
    - User explicitly saves a version
    
    Allows "what-if" analysis and rollback to previous configurations.
    """
    class_session = models.ForeignKey(
        'academics.ClassSession',
        on_delete=models.CASCADE,
        related_name='timetable_versions'
    )
    version_number = models.PositiveIntegerField()
    name = models.CharField(
        max_length=100,
        help_text="Version name, e.g., 'Initial Draft', 'After PE adjustment'"
    )
    description = models.TextField(blank=True)
    # Store the entire timetable configuration as JSON
    slot_data = models.JSONField(
        help_text="JSON snapshot of all TimetableSlots for this class_session"
    )
    # Metadata
    total_slots = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='timetable_versions_created'
    )
    # Track if this version was ever restored
    was_restored = models.BooleanField(default=False)
    restored_at = models.DateTimeField(null=True, blank=True)
    restored_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='timetable_versions_restored'
    )

    class Meta:
        verbose_name = 'Timetable Version'
        verbose_name_plural = 'Timetable Versions'
        ordering = ['-version_number']
        db_table = 'timetable_versions'
        unique_together = ['class_session', 'version_number']

    @classmethod
    def create_snapshot(cls, class_session, name, user, description=''):
        """
        Create a new version snapshot from current timetable state.
        """
        from .serializers import TimetableSlotSerializer
        
        slots = TimetableSlot.objects.filter(
            class_session=class_session,
            is_active=True
        ).select_related('subject', 'teacher', 'room')
        
        # Get next version number
        last_version = cls.objects.filter(
            class_session=class_session
        ).order_by('-version_number').first()
        
        next_version = (last_version.version_number + 1) if last_version else 1
        
        # Serialize slots
        slot_data = TimetableSlotSerializer(slots, many=True).data
        
        return cls.objects.create(
            class_session=class_session,
            version_number=next_version,
            name=name,
            description=description,
            slot_data=slot_data,
            total_slots=len(slot_data),
            created_by=user
        )

    def restore(self, user):
        """
        Restore timetable slots from this version snapshot.
        
        WARNING: This will deactivate all current slots and create new ones
        from the snapshot data.
        """
        # Deactivate current slots
        TimetableSlot.objects.filter(
            class_session=self.class_session,
            is_active=True
        ).update(is_active=False)

        # Recreate slots from snapshot
        for slot_data in self.slot_data:
            TimetableSlot.objects.create(
                class_session_id=slot_data['class_session'],
                subject_id=slot_data['subject'],
                teacher_id=slot_data['teacher'],
                room_id=slot_data.get('room'),
                day_of_week=slot_data['day_of_week'],
                start_time=slot_data['start_time'],
                end_time=slot_data['end_time'],
                effective_from=timezone.localdate(),
                is_active=True,
                created_by=user
            )

        # Mark this version as restored
        self.was_restored = True
        self.restored_at = timezone.now()
        self.restored_by = user
        self.save()

    def __str__(self):
        return f"{self.class_session.name} v{self.version_number}: {self.name}"
