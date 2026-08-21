# pyrefly: ignore [missing-import]
from django.db import models
# pyrefly: ignore [missing-import]
from django.conf import settings
from student_settings.models import BaseModel

class Admission(BaseModel):
    """
    Bridges applicant -> student. Represents the official admission record.
    """
    application = models.OneToOneField(
        'student_management.Application',
        on_delete=models.PROTECT,
        related_name='admission'
    )
    student = models.OneToOneField(
        'student_management.Student',
        on_delete=models.PROTECT,
        related_name='admission_record'
    )
    
    admission_number = models.CharField(max_length=50, unique=True)
    admission_date = models.DateField()
    campus = models.ForeignKey(
        'workforce.Campus',
        on_delete=models.PROTECT,
        related_name='campus_admissions',
        null=True,
        blank=True,
        help_text='Campus the student was admitted to'
    )
    
    admitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='admissions_processed'
    )
    
    notes = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"Admission {self.admission_number} - {self.student}"
    
    class Meta:
        ordering = ['-admission_date']
        db_table = 'student_admissions'
