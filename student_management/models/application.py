from django.db import models
from student_settings.models import BaseModel

class Application(BaseModel):
    """
    Tracks applicants before they become students.
    """
    STATUS_CHOICES = (
        ('pending', 'Pending Review'),
        ('interview', 'Interview Scheduled'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('waitlist', 'Waitlisted'),
    )

    # Applicant Details
    first_name = models.CharField(max_length=120)
    last_name = models.CharField(max_length=120)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=[('M', 'Male'), ('F', 'Female')], null=True, blank=True)
    
    # Application Targets
    intake = models.ForeignKey(
        'student_settings.Intake',
        on_delete=models.PROTECT,
        related_name='applications'
    )
    applying_for_curriculum = models.ForeignKey(
        'student_settings.Curriculum',
        on_delete=models.PROTECT,
        related_name='applications'
    )
    applying_for_level = models.ForeignKey(
        'student_settings.CurriculumLevel',
        on_delete=models.PROTECT,
        related_name='applications',
        null=True,
        blank=True
    )
    applying_for_grade = models.ForeignKey(
        'student_settings.GradeStructure',
        on_delete=models.PROTECT,
        related_name='applications',
        null=True,
        blank=True
    )
    
    # Contact Info
    guardian_name = models.CharField(max_length=120, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    
    # Status
    application_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    review_notes = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
        
    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.intake.name}"
