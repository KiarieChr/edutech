"""
Scheduled Lessons App — GENERATION layer.

Responsibilities:
  - Daily generation of PlannedLesson records from TimetableSlot rules.
  - One PlannedLesson per (timetable_slot, date).
  - Respect school holidays and exceptions.
  - Prevent duplicate generation.
  - Auto-mark missed lessons at end of each day.

This app NEVER stores what happened — only what is expected to happen.
"""
from django.db import models
from django.conf import settings


class PlannedLesson(models.Model):
    """
    One expected lesson for a specific calendar date.

    Generated automatically by the management command / Celery task.
    Should NOT be created manually except by admin override.

    Lifecycle:
      pending  → executed   (teacher started a LessonSession)
      pending  → missed     (Celery auto-marks after lesson end_time passes)
      pending  → cancelled  (admin explicitly cancels)
      pending  → holiday    (generated on a blocked date)
    """
    STATUS_CHOICES = (
        ('pending',   'Pending'),
        ('executed',  'Executed'),
        ('missed',    'Missed'),
        ('cancelled', 'Cancelled'),
        ('holiday',   'Holiday / School Closed'),
    )

    # Source timetable rule
    timetable_slot = models.ForeignKey(
        'timetable.TimetableSlot',
        on_delete=models.CASCADE,
        related_name='planned_lessons'
    )
    date = models.DateField(db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Denormalised from TimetableSlot for fast dashboard queries (no joins)
    class_session = models.ForeignKey(
        'academics.ClassSession',
        on_delete=models.CASCADE,
        related_name='planned_lessons',
        help_text="The Grade+Term academic container — NOT an operational session."
    )
    subject = models.ForeignKey(
        'timetable.Subject',
        on_delete=models.CASCADE,
        related_name='planned_lessons'
    )
    room = models.ForeignKey(
        'timetable.Room',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='planned_lessons'
    )
    expected_teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='planned_lessons'
    )
    scheduled_start_time = models.TimeField()
    scheduled_end_time   = models.TimeField()

    # Audit
    generated_at = models.DateTimeField(auto_now_add=True)
    # 'scheduler' = Celery task | 'admin' = manual | 'regen' = timetable edit trigger
    generated_by = models.CharField(max_length=50, default='scheduler')
    cancellation_reason = models.CharField(max_length=255, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='cancelled_planned_lessons'
    )

    class Meta:
        # Core de-duplication constraint
        unique_together = ['timetable_slot', 'date']
        indexes = [
            models.Index(fields=['date', 'status']),
            models.Index(fields=['class_session', 'date']),
            models.Index(fields=['expected_teacher', 'date']),
            models.Index(fields=['subject', 'date']),
        ]
        ordering = ['date', 'scheduled_start_time']
        verbose_name = 'Planned Lesson'
        verbose_name_plural = 'Planned Lessons'

    @property
    def scheduled_duration_minutes(self):
        from datetime import datetime
        dummy = datetime(2000, 1, 1)
        start = datetime.combine(dummy, self.scheduled_start_time)
        end   = datetime.combine(dummy, self.scheduled_end_time)
        return int((end - start).total_seconds() // 60)

    def __str__(self):
        return (
            f"{self.class_session} | {self.subject} | "
            f"{self.date} {self.scheduled_start_time:%H:%M} [{self.status}]"
        )
