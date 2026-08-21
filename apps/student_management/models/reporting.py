from django.db import models
from django.conf import settings
from student_settings.models import BaseModel


class ReportingRecord(BaseModel):
    """
    Physical 'reporting day' record — the student arrives at school with documents
    before being formally admitted.
    Used when AdmissionWorkflowConfig.require_reporting=True.
    """

    STATUS_CHOICES = [
        ('expected', 'Expected'),
        ('reported', 'Reported'),
        ('absent', 'Did Not Report'),
        ('deferred', 'Deferred to Later Date'),
    ]

    # ── Core Link ───────────────────────────────────────────────────────────────
    application = models.OneToOneField(
        'student_management.Application',
        on_delete=models.CASCADE,
        related_name='reporting_record',
        help_text='The application this reporting record is for'
    )

    # ── Schedule ────────────────────────────────────────────────────────────────
    expected_date = models.DateField(
        help_text='Date the student is expected to report'
    )
    actual_date = models.DateField(
        null=True, blank=True,
        help_text='Date the student actually reported'
    )

    # ── Status ──────────────────────────────────────────────────────────────────
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='expected')

    # ── Document Checklist ──────────────────────────────────────────────────────
    documents_received = models.BooleanField(
        default=False,
        help_text='True when all required documents have been received'
    )
    document_status = models.JSONField(
        default=dict, blank=True,
        help_text=(
            'Per-document submission status. Key = document name, '
            'Value = "received" | "missing" | "partial". '
            'e.g. {"Birth Certificate": "received", "Passport Photo": "missing"}'
        )
    )
    missing_documents = models.TextField(
        blank=True, null=True,
        help_text='Free-text list of any documents still outstanding'
    )

    # ── Staff ───────────────────────────────────────────────────────────────────
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reporting_records_received',
        help_text='Staff member who received the student on reporting day'
    )
    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'application_reporting_records'
        ordering = ['expected_date']
        verbose_name = 'Reporting Record'

    def __str__(self):
        return (
            f"Reporting — {self.application} "
            f"({self.get_status_display()}, {self.expected_date})"
        )

    @property
    def is_cleared(self):
        """True when this reporting stage no longer blocks admission."""
        return self.status == 'reported'
