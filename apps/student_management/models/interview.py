from django.db import models
from django.conf import settings
from student_settings.models import BaseModel


class InterviewSchedule(BaseModel):
    """
    Interview record for an applicant.
    Created when AdmissionWorkflowConfig.require_interview=True and
    staff schedule an interview for an Application.
    """

    # Override BaseModel FK related_names to avoid clash with recruitment.InterviewSchedule
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='student_interview_created'
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='student_interview_updated'
    )

    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('no_show', 'No Show'),
        ('rescheduled', 'Rescheduled'),
        ('cancelled', 'Cancelled'),
    ]

    OUTCOME_CHOICES = [
        ('pending', 'Pending'),
        ('pass', 'Pass'),
        ('conditional', 'Conditional Pass'),
        ('fail', 'Fail'),
    ]

    # ── Core Link ───────────────────────────────────────────────────────────────
    application = models.OneToOneField(
        'student_management.Application',
        on_delete=models.CASCADE,
        related_name='interview',
        help_text='The application being interviewed'
    )

    # ── Schedule ────────────────────────────────────────────────────────────────
    scheduled_date = models.DateTimeField(help_text='Date and time of the interview')
    venue = models.CharField(
        max_length=200, blank=True, null=True,
        help_text='Room name, building, or online link'
    )
    duration_minutes = models.PositiveIntegerField(
        default=30,
        help_text='Expected duration in minutes'
    )

    # ── Interviewer ─────────────────────────────────────────────────────────────
    interviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assigned_interviews',
        help_text='Primary interviewer (staff member)'
    )
    panel_members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='interview_panel_memberships',
        help_text='Additional panel members'
    )

    # ── Status & Outcome ────────────────────────────────────────────────────────
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    outcome = models.CharField(max_length=20, choices=OUTCOME_CHOICES, default='pending')

    # ── Assessment ──────────────────────────────────────────────────────────────
    score = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        help_text='Numeric score if interview uses scoring rubric'
    )
    max_score = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        help_text='Maximum possible score'
    )
    notes = models.TextField(
        blank=True, null=True,
        help_text='Interviewer notes — visible to admin only'
    )
    feedback_to_applicant = models.TextField(
        blank=True, null=True,
        help_text='Optional feedback communicated to the applicant/guardian'
    )

    # ── Completion Tracking ──────────────────────────────────────────────────────
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='interviews_completed',
        help_text='Staff who recorded the interview outcome'
    )

    class Meta:
        db_table = 'application_interviews'
        ordering = ['scheduled_date']
        verbose_name = 'Interview Schedule'

    def __str__(self):
        return (
            f"Interview — {self.application} on "
            f"{self.scheduled_date.strftime('%d %b %Y %H:%M')} [{self.get_status_display()}]"
        )

    @property
    def is_passed(self):
        """True when this interview no longer blocks progression."""
        return self.outcome in ('pass', 'conditional')
