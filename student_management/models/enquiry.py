from django.db import models
from django.conf import settings
from student_settings.models import BaseModel


class Enquiry(BaseModel):
    """
    Pre-application interest record.
    Used when AdmissionWorkflowConfig.require_enquiry=True.
    A prospective parent/student expresses interest; staff follow up and
    eventually convert it into a formal Application.
    """

    STATUS_CHOICES = [
        ('new', 'New'),
        ('contacted', 'Contacted'),
        ('converted', 'Converted to Application'),
        ('dropped', 'Dropped'),
    ]

    SOURCE_CHOICES = [
        ('walk_in', 'Walk-in'),
        ('phone', 'Phone Call'),
        ('email', 'Email'),
        ('website', 'Website Form'),
        ('referral', 'Referral'),
        ('social_media', 'Social Media'),
        ('open_day', 'Open Day'),
        ('other', 'Other'),
    ]

    # ── Contact Information ─────────────────────────────────────────────────────
    full_name = models.CharField(max_length=200, help_text="Name of the parent or enquiring party")
    child_name = models.CharField(max_length=200, blank=True, null=True, help_text="Name of the prospective student")
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)

    # ── Interest Details ────────────────────────────────────────────────────────
    intake = models.ForeignKey(
        'student_settings.Intake',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='enquiries',
        help_text='Which intake are they interested in?'
    )
    curriculum = models.ForeignKey(
        'student_settings.Curriculum',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='enquiries'
    )
    grade = models.ForeignKey(
        'student_settings.GradeStructure',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='enquiries',
        help_text='Grade/class level they are enquiring about'
    )
    campus = models.ForeignKey(
        'workforce.Campus',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='enquiries'
    )
    message = models.TextField(blank=True, null=True, help_text='Free-text message from the enquiring party')
    source = models.CharField(max_length=30, choices=SOURCE_CHOICES, default='walk_in')

    # ── Tracking ────────────────────────────────────────────────────────────────
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assigned_enquiries',
        help_text='Staff member responsible for following up'
    )
    follow_up_date = models.DateField(null=True, blank=True, help_text='Scheduled follow-up date')
    follow_up_notes = models.TextField(blank=True, null=True)

    # ── Conversion ──────────────────────────────────────────────────────────────
    converted_application = models.OneToOneField(
        'student_management.Application',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='enquiry_source',
        help_text='The Application created from this enquiry'
    )
    converted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'student_enquiries'
        ordering = ['-created_at']
        verbose_name = 'Enquiry'
        verbose_name_plural = 'Enquiries'

    def __str__(self):
        return f"Enquiry — {self.full_name} ({self.get_status_display()})"
