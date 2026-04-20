import os
from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone


def assignment_upload_path(instance, filename):
    return f"assignments/{instance.class_session_id}/{timezone.now():%Y/%m}/{filename}"


def submission_upload_path(instance, filename):
    return f"assignments/submissions/{instance.assignment_id}/{instance.student.student.id}/{filename}"


class Assignment(models.Model):
    """A teacher-uploaded assignment for a class session + subject."""

    TYPE_CHOICES = (
        ('homework', 'Homework'),
        ('classwork', 'Classwork'),
        ('project', 'Project'),
        ('exam_prep', 'Exam Preparation'),
        ('revision', 'Revision'),
    )
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('closed', 'Closed'),
    )

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    assignment_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='homework')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    class_session = models.ForeignKey(
        'academics.ClassSession',
        on_delete=models.CASCADE,
        related_name='assignments',
    )
    subject = models.ForeignKey(
        'timetable.Subject',
        on_delete=models.CASCADE,
        related_name='assignments',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='assignments_created',
    )

    file = models.FileField(
        upload_to=assignment_upload_path,
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx', 'jpg', 'jpeg', 'png'])],
        help_text='Upload the assignment file (PDF recommended)',
    )
    max_score = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    due_date = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Assignment'
        verbose_name_plural = 'Assignments'

    def __str__(self):
        return f"{self.title} — {self.subject.name} ({self.class_session.name})"

    @property
    def is_past_due(self):
        if self.due_date:
            return timezone.now() > self.due_date
        return False

    @property
    def submission_count(self):
        return self.submissions.count()

    @property
    def graded_count(self):
        return self.submissions.filter(status='graded').count()


class AssignmentSubmission(models.Model):
    """A student's submission for an assignment."""

    STATUS_CHOICES = (
        ('submitted', 'Submitted'),
        ('graded', 'Graded'),
        ('returned', 'Returned'),
        ('late', 'Late Submission'),
    )

    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name='submissions',
    )
    student = models.ForeignKey(
        'accounts.Student',
        on_delete=models.CASCADE,
        related_name='assignment_submissions',
    )
    file = models.FileField(
        upload_to=submission_upload_path,
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png'])],
        null=True, blank=True,
        help_text='Upload response file',
    )
    text_response = models.TextField(blank=True, help_text='Optional text response')
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    teacher_remarks = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='submitted')

    submitted_at = models.DateTimeField(auto_now_add=True)
    graded_at = models.DateTimeField(null=True, blank=True)
    graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='submissions_graded',
    )

    class Meta:
        ordering = ['-submitted_at']
        unique_together = ['assignment', 'student']
        verbose_name = 'Assignment Submission'
        verbose_name_plural = 'Assignment Submissions'

    def __str__(self):
        return f"{self.student} — {self.assignment.title}"

    def save(self, *args, **kwargs):
        # Auto-mark late submissions
        if not self.pk and self.assignment.due_date:
            if timezone.now() > self.assignment.due_date:
                self.status = 'late'
        super().save(*args, **kwargs)
