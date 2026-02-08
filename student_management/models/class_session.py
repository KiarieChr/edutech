from django.db import models
from student_settings.models import BaseModel

class StudentPlacement(BaseModel):
    """
    Represents a student's placement in a specific class for a specific period.
    Replaces Enrollment.
    """
    SESSION_TYPE_CHOICES = (
        ('admission', 'Admission'),
        ('reporting', 'Reporting'),
        ('promotion', 'Promotion'),
        ('repeat', 'Repeat'),
        ('transfer', 'Transfer In'),
    )
    
    SESSION_STATUS_CHOICES = (
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('transferred', 'Transferred Out'),
        ('dropped', 'Dropped'),
    )

    student = models.ForeignKey(
        'accounts.Student',
        on_delete=models.PROTECT,
        related_name='placements'
    )
    
    # Placement
    intake = models.ForeignKey(
        'student_settings.Intake',
        on_delete=models.PROTECT,
        related_name='placements'
    )
    academic_year = models.ForeignKey(
        'student_settings.AcademicYear',
        on_delete=models.PROTECT,
        related_name='placements'
    )
    term = models.ForeignKey(
        'student_settings.Term',
        on_delete=models.PROTECT,
        related_name='placements'
    )
    
    # Curriculum Details
    curriculum = models.ForeignKey(
        'student_settings.Curriculum',
        on_delete=models.PROTECT,
        related_name='placements'
    )
    curriculum_level = models.ForeignKey(
        'student_settings.CurriculumLevel',
        on_delete=models.PROTECT,
        related_name='placements',
        null=True,
        blank=True
    )
    grade = models.ForeignKey(
        'student_settings.GradeStructure',
        on_delete=models.PROTECT,
        related_name='placements'
    )
    stream = models.ForeignKey(
        'student_settings.Stream',
        on_delete=models.PROTECT,
        related_name='placements',
        null=True, 
        blank=True
    )
    
    # Session Details
    session_type = models.CharField(max_length=20, choices=SESSION_TYPE_CHOICES, default='reporting')
    session_status = models.CharField(max_length=20, choices=SESSION_STATUS_CHOICES, default='active')
    
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    
    previous_placement = models.OneToOneField(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='next_placement'
    )
    
    class Meta:
        ordering = ['-academic_year__start_date', '-term__start_date']
        verbose_name = "Student Placement"
        verbose_name_plural = "Student Placements"
        indexes = [
            models.Index(fields=['student', 'session_status']),
        ]

    def __str__(self):
        return f"{self.student} - {self.grade} ({self.academic_year})"
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
