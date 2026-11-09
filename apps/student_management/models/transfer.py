from django.db import models
from django.conf import settings
from student_settings.models import BaseModel


class StudentCampusTransfer(BaseModel):
    """
    Audit log tracking historical transfers of students between campuses.
    Enables multi-campus institutions to track student movement, reason,
    academic placement change, and administrative accountability.
    """
    student = models.ForeignKey(
        'student_management.Student',
        on_delete=models.CASCADE,
        related_name='campus_transfers',
        help_text='Student who was migrated'
    )
    admission = models.ForeignKey(
        'student_management.Admission',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='campus_transfers'
    )
    source_campus = models.ForeignKey(
        'workforce.Campus',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transfers_out',
        help_text='Campus the student moved from'
    )
    target_campus = models.ForeignKey(
        'workforce.Campus',
        on_delete=models.PROTECT,
        related_name='transfers_in',
        help_text='Campus the student moved to'
    )
    admission_number = models.CharField(
        max_length=50,
        help_text='Admission number at time of transfer'
    )
    previous_class = models.CharField(max_length=100, blank=True, null=True)
    new_class = models.CharField(max_length=100, blank=True, null=True)
    reason = models.CharField(
        max_length=255,
        default='Administrative Reassignment',
        help_text='Primary reason for cross-campus transfer'
    )
    notes = models.TextField(blank=True, null=True, help_text='Administrative notes or justification')
    transferred_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='initiated_campus_transfers'
    )
    transferred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-transferred_at']
        db_table = 'student_campus_transfers'

    def __str__(self):
        src = self.source_campus.name if self.source_campus else "Unassigned"
        tgt = self.target_campus.name if self.target_campus else "Unassigned"
        return f"{self.student} ({src} -> {tgt}) on {self.transferred_at.strftime('%Y-%m-%d')}"

