"""
Lesson Sessions App — EXECUTION layer.

This is the operational source of truth for everything that ACTUALLY happened:
  - Which teacher taught.
  - Exact start and end times.
  - Topic covered.
  - Student attendance per lesson.
  - Substitutions.
  - Curriculum coverage achieved.

Naming clarification:
  DO NOT confuse LessonSession with academics.ClassSession.

  academics.ClassSession  = Grade 4A – Term 1 2026
    → student enrollment container, tracks progression through years.

  lesson_sessions.LessonSession  = Mathematics lesson on 2026-02-27 at 08:00
    → a single operational teaching event that actually occurred.
"""
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.conf import settings


class LessonSession(models.Model):
    """
    The execution record of a single lesson.

    Created when a teacher (or admin) clicks "Start Session".
    The planned_lesson FK links back to what was scheduled.

    A LessonSession can exist without a planned_lesson (ad-hoc session).
    A planned_lesson can exist without a LessonSession (missed/cancelled).

    Lifecycle:
      [teacher starts]     → status = 'ongoing'
      [teacher ends]       → status = 'completed'  (attendance locked)
      [Celery end-of-day]  → status = 'missed'     (if still pending in PlannedLesson)
      [admin cancels]      → status = 'cancelled'
    """
    STATUS_CHOICES = (
        ('ongoing',   'Ongoing'),
        ('completed', 'Completed'),
        ('missed',    'Missed'),
        ('cancelled', 'Cancelled'),
    )
    DELIVERY_MODE_CHOICES = (
        ('physical', 'Physical Classroom'),
        ('online',   'Online / Virtual'),
        ('hybrid',   'Hybrid'),
    )

    # --- Link to planning layer ---
    # OneToOne: one lesson can only result in one real execution record.
    # null=True allows ad-hoc sessions created without a timetable slot.
    planned_lesson = models.OneToOneField(
        'scheduled_lessons.PlannedLesson',
        on_delete=models.PROTECT,
        related_name='lesson_session',
        null=True, blank=True,
        help_text="The planned lesson this execution corresponds to. Null for ad-hoc sessions."
    )

    # --- Execution data — ACTUAL values, not planned ---
    actual_teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='conducted_lessons',
        help_text="The teacher who actually conducted this lesson."
    )
    actual_start_time = models.DateTimeField(
        help_text="Actual datetime the lesson started."
    )
    actual_end_time = models.DateTimeField(
        null=True, blank=True,
        help_text="Actual datetime the lesson ended. Null while ongoing."
    )

    # --- Academic context ---
    # Denormalised from PlannedLesson for fast querying.
    # academics.ClassSession = the Grade+Term enrollment container (NOT this record)
    class_session = models.ForeignKey(
        'academics.ClassSession',
        on_delete=models.PROTECT,
        related_name='lesson_sessions',
        help_text="The Grade+Term period this lesson belongs to."
    )
    subject = models.ForeignKey(
        'timetable.Subject',
        on_delete=models.PROTECT,
        related_name='lesson_sessions'
    )
    room = models.ForeignKey(
        'timetable.Room',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='lesson_sessions'
    )
    date = models.DateField(db_index=True)

    # --- Lesson content ---
    topic_taught    = models.CharField(max_length=255, blank=True)
    lesson_notes    = models.TextField(blank=True)
    homework_given  = models.TextField(blank=True)
    delivery_mode   = models.CharField(
        max_length=20, choices=DELIVERY_MODE_CHOICES, default='physical'
    )
    curriculum_unit = models.ForeignKey(
        'timetable.CurriculumUnit',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='lesson_sessions',
        help_text="The curriculum unit/topic covered in this session."
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ongoing')

    # --- Audit ---
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='lessons_started'
    )
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='lessons_completed'
    )
    cancellation_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['date', 'status']),
            models.Index(fields=['class_session', 'date']),
            models.Index(fields=['actual_teacher', 'date']),
        ]
        ordering = ['-date', 'actual_start_time']
        verbose_name = 'Lesson Session'
        verbose_name_plural = 'Lesson Sessions'

    @property
    def actual_duration_minutes(self):
        """Actual lesson length in minutes. None while ongoing."""
        if self.actual_start_time and self.actual_end_time:
            delta = self.actual_end_time - self.actual_start_time
            return int(delta.total_seconds() // 60)
        return None

    @property
    def start_delay_minutes(self):
        """How many minutes late the lesson started vs the timetable slot."""
        if not self.planned_lesson or not self.actual_start_time:
            return None
        from datetime import datetime
        planned_dt = datetime.combine(self.date, self.planned_lesson.scheduled_start_time)
        import pytz
        planned_dt = timezone.make_aware(planned_dt)
        delta = self.actual_start_time - planned_dt
        return max(0, int(delta.total_seconds() // 60))

    def complete(self, completed_by_user, topic_taught='', lesson_notes='',
                 homework_given='', curriculum_unit=None):
        """
        End the lesson session. Locks attendance and updates the planned lesson.
        """
        self.actual_end_time = timezone.now()
        self.status = 'completed'
        self.completed_by = completed_by_user
        if topic_taught:
            self.topic_taught = topic_taught
        if lesson_notes:
            self.lesson_notes = lesson_notes
        if homework_given:
            self.homework_given = homework_given
        if curriculum_unit is not None:
            self.curriculum_unit = curriculum_unit
        self.save()

        # Lock attendance
        SessionAttendance.objects.filter(lesson_session=self).update(is_locked=True)

        # Mark planned lesson as executed
        if self.planned_lesson_id:
            from scheduled_lessons.models import PlannedLesson
            PlannedLesson.objects.filter(pk=self.planned_lesson_id).update(status='executed')

        # Record curriculum coverage
        CurriculumCoverage.record_coverage(self)

    def __str__(self):
        return (
            f"[{self.status.upper()}] {self.class_session} | "
            f"{self.subject} | {self.date} | {self.actual_teacher}"
        )


class SessionAttendance(models.Model):
    """
    Per-student attendance record for a single LessonSession.

    Locked (is_locked=True) once the LessonSession is completed.
    Attendance belongs to the execution layer ONLY — never to the timetable.

    Auto-created for all enrolled students when a session starts (default: absent).
    Teacher marks present/late/excused during the session.
    """
    STATUS_CHOICES = (
        ('present', 'Present'),
        ('absent',  'Absent'),
        ('late',    'Late'),
        ('excused', 'Excused Absent'),
    )

    lesson_session = models.ForeignKey(
        LessonSession,
        on_delete=models.CASCADE,
        related_name='attendances'
    )
    student = models.ForeignKey(
        'student_management.Student',
        on_delete=models.CASCADE,
        related_name='lesson_attendances'
    )
    status      = models.CharField(max_length=20, choices=STATUS_CHOICES, default='absent')
    marked_at   = models.DateTimeField(null=True, blank=True)
    marked_by   = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='attendance_markings'
    )
    minutes_late = models.PositiveSmallIntegerField(
        default=0,
        help_text="How many minutes late the student arrived. Relevant when status=late."
    )
    # Locked after session completion; no edits allowed
    is_locked = models.BooleanField(default=False)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ['lesson_session', 'student']
        indexes = [
            models.Index(fields=['student', 'status']),
            models.Index(fields=['lesson_session', 'status']),
        ]
        verbose_name = 'Session Attendance'
        verbose_name_plural = 'Session Attendance Records'

    def save(self, *args, **kwargs):
        # Block edits on locked records (but allow initial creation)
        if self.pk:
            try:
                original = SessionAttendance.objects.get(pk=self.pk)
                if original.is_locked:
                    raise PermissionError(
                        "Cannot modify attendance for a completed and locked session."
                    )
            except SessionAttendance.DoesNotExist:
                pass

        # Auto-set marked_at when marking a non-absent status
        if self.status in ('present', 'late', 'excused') and not self.marked_at:
            self.marked_at = timezone.now()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student} | {self.lesson_session} | {self.status}"


class TeacherSubstitution(models.Model):
    """
    Formal record when a substitute teacher takes a planned lesson.

    Created BEFORE the session starts (planned substitution) or immediately
    after as a post-hoc record when an admin overrides the teacher.

    On save, updates PlannedLesson.expected_teacher to the substitute so the
    dashboard shows the correct teacher before the session starts.
    """
    REASON_CHOICES = (
        ('sick_leave',  'Teacher Sick Leave'),
        ('emergency',   'Personal Emergency'),
        ('training',    'Training / Workshop'),
        ('travel',      'Official Travel'),
        ('no_show',     'Teacher No-Show'),
        ('other',       'Other'),
    )

    planned_lesson = models.ForeignKey(
        'scheduled_lessons.PlannedLesson',
        on_delete=models.CASCADE,
        related_name='substitutions'
    )
    original_teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='lessons_substituted_out'
    )
    substitute_teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='substitute_lessons'
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='substitutions_approved'
    )
    reason        = models.CharField(max_length=30, choices=REASON_CHOICES)
    reason_notes  = models.TextField(blank=True)
    requested_at  = models.DateTimeField(auto_now_add=True)
    approved_at   = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-requested_at']
        verbose_name = 'Teacher Substitution'
        verbose_name_plural = 'Teacher Substitutions'

    def clean(self):
        # Substitute must not have another lesson at the same time
        from scheduled_lessons.models import PlannedLesson
        conflict = PlannedLesson.objects.filter(
            date=self.planned_lesson.date,
            scheduled_start_time=self.planned_lesson.scheduled_start_time,
            expected_teacher=self.substitute_teacher,
        ).exclude(pk=self.planned_lesson.pk).exists()
        if conflict:
            raise ValidationError(
                f"{self.substitute_teacher} already has a lesson "
                f"scheduled at {self.planned_lesson.scheduled_start_time} "
                f"on {self.planned_lesson.date}."
            )
        if self.original_teacher == self.substitute_teacher:
            raise ValidationError("Substitute teacher must be different from the original teacher.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        # Update the planned lesson's expected teacher so dashboards reflect the change
        from scheduled_lessons.models import PlannedLesson
        PlannedLesson.objects.filter(pk=self.planned_lesson_id).update(
            expected_teacher=self.substitute_teacher
        )

    def __str__(self):
        return (
            f"Sub: {self.substitute_teacher} replaces {self.original_teacher} | "
            f"{self.planned_lesson}"
        )


class CurriculumCoverage(models.Model):
    """
    Records which curriculum unit was addressed in which lesson session.

    Updated automatically when LessonSession.complete() is called.
    Drives the subject completion % analytics.
    """
    curriculum_unit = models.ForeignKey(
        'timetable.CurriculumUnit',
        on_delete=models.CASCADE,
        related_name='coverage_records'
    )
    lesson_session = models.ForeignKey(
        LessonSession,
        on_delete=models.CASCADE,
        related_name='coverage_records'
    )
    coverage_percent = models.PositiveSmallIntegerField(
        default=100,
        help_text="Percentage of this unit covered in this session (0–100)."
    )
    teacher_notes = models.TextField(blank=True)
    recorded_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['curriculum_unit', 'lesson_session']
        verbose_name = 'Curriculum Coverage'
        verbose_name_plural = 'Curriculum Coverage Records'

    @classmethod
    def record_coverage(cls, lesson_session):
        """
        Called automatically when a LessonSession is completed.
        Links the CurriculumUnit to the session if specified.
        """
        if not lesson_session.curriculum_unit_id:
            return
        cls.objects.get_or_create(
            curriculum_unit_id=lesson_session.curriculum_unit_id,
            lesson_session=lesson_session,
            defaults={'coverage_percent': 100}
        )

    @classmethod
    def subject_completion_percent(cls, subject_id, class_session_id):
        """
        Returns the % of CurriculumUnits for a subject that have been covered
        (at least one CurriculumCoverage record exists).
        """
        from timetable.models import CurriculumUnit
        total = CurriculumUnit.objects.filter(
            subject_id=subject_id,
            class_session_id=class_session_id
        ).count()
        if not total:
            return 0.0
        covered = cls.objects.filter(
            curriculum_unit__subject_id=subject_id,
            curriculum_unit__class_session_id=class_session_id,
        ).values('curriculum_unit').distinct().count()
        return round((covered / total) * 100, 1)

    def __str__(self):
        return (
            f"{self.curriculum_unit} | "
            f"{self.lesson_session.date} | {self.coverage_percent}%"
        )
