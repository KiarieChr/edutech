from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError

class ClassSession(models.Model):
    """
    Represents a specific class running during a specific term and academic year.
    Example: Grade 1 - Term 1 2026
    This is the operational unit for attendance, reporting, and grading.
    """
    STATUS_CHOICES = (
        ('scheduled', 'Scheduled'),
        ('active', 'Active'),
        ('closed', 'Closed'),
        ('archived', 'Archived'),
    )

    name = models.CharField(max_length=150, help_text="Auto-generated name, e.g., 'Grade 1 - Term 1 2026'")
    
    # Links to Definitions - Updated related_names to avoid clash with student_management.ClassSession
    grade = models.ForeignKey(
        'student_settings.GradeStructure', 
        on_delete=models.PROTECT,
        related_name='academic_sessions' 
    )
    term = models.ForeignKey(
        'student_settings.Term', 
        on_delete=models.PROTECT,
        related_name='academic_sessions'
    )
    academic_year = models.ForeignKey(
        'student_settings.AcademicYear', 
        on_delete=models.PROTECT,
        related_name='academic_sessions'
    )
    
    # Curriculum Context
    curriculum = models.ForeignKey(
        'student_settings.Curriculum',
        on_delete=models.PROTECT,
        related_name='academic_sessions'
    )
    curriculum_level = models.ForeignKey(
        'student_settings.CurriculumLevel',
        on_delete=models.PROTECT,
        related_name='academic_sessions',
        null=True, blank=True
    )
    
    # Operational Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['grade', 'term', 'academic_year']
        ordering = ['academic_year__start_date', 'term__start_date', 'grade__level_order']
        verbose_name = "Class Session"
        verbose_name_plural = "Class Sessions"
        db_table = 'class_sessions'

    def __str__(self):
        return self.name

    def update_status(self):
        """Update status based on current date"""
        if not self.start_date or not self.end_date:
            return

        today = timezone.now().date()
        
        if today < self.start_date:
            new_status = 'scheduled'
        elif self.start_date <= today <= self.end_date:
            new_status = 'active'
        else: # today > self.end_date
            new_status = 'closed'
            
        if self.status != new_status:
            self.status = new_status
            # Avoid recursion if calling save() from here, but usually this is called BEFORE save
            
    def save(self, *args, **kwargs):
        # Auto-generate name
        if not self.name:
            curr_str = self.curriculum.code if self.curriculum.code else self.curriculum.name
            self.name = f"{self.grade.name} ({curr_str}) - {self.term.name} {self.academic_year.name}"
        
        # Enforce Curriculum Consistency
        if self.grade.curriculum != self.curriculum:
            raise ValidationError(f"Grade {self.grade} does not belong to Curriculum {self.curriculum}")

        # Auto-update status based on dates
        self.update_status()
            
        super().save(*args, **kwargs)


class StudentSessionEnrollment(models.Model):
    """
    Links a Student to a specific ClassSession.
    Tracks their status within that specific term (Promoted, Repeated, etc).
    """
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('transferred_out', 'Transferred Out'),
        ('dropped', 'Dropped'),
        ('expelled', 'Expelled'),
    )
    
    PROGRESSION_CHOICES = (
        ('promoted', 'Promoted'),
        ('retained', 'Retained/Repeated'),
        ('graduated', 'Graduated'),
        ('discontinued', 'Discontinued'),
        ('pending', 'Pending Decision'), # Default until end of term
    )

    student = models.ForeignKey(
        'accounts.Student',
        on_delete=models.CASCADE,
        related_name='session_enrollments'
    )
    
    session = models.ForeignKey(
        ClassSession,
        on_delete=models.PROTECT,
        related_name='student_enrollments'
    )
    
    # The Permanent Cohort
    intake = models.ForeignKey(
        'student_settings.Intake',
        on_delete=models.PROTECT,
        related_name='enrollments',
        help_text="The intake cohort this student belongs to (immutable usually)"
    )
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    progression_status = models.CharField(max_length=20, choices=PROGRESSION_CHOICES, default='pending')
    
    # Validations
    is_active = models.BooleanField(default=True, help_text="Is this the student's CURRENT active session?")
    
    reporting_date = models.DateField(default=timezone.now)
    completion_date = models.DateField(null=True, blank=True)
    
    # Stream Assignment (Specific to this session)
    stream = models.ForeignKey(
        'student_settings.Stream',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='session_students'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # A student can only be enrolled in a session once
        unique_together = ['student', 'session']
        indexes = [
            models.Index(fields=['student', 'is_active']),
            models.Index(fields=['session', 'status']),
        ]
        db_table = 'student_session_enrollments'

    def __str__(self):
        return f"{self.student} - {self.session.name}"

    def save(self, *args, **kwargs):
        # Enforce: One active session per student at a time
        if self.is_active:
            StudentSessionEnrollment.objects.filter(student=self.student, is_active=True).exclude(pk=self.pk).update(is_active=False)
            
        super().save(*args, **kwargs)
