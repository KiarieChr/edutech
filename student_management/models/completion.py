from django.db import models
from student_settings.models import BaseModel

class Completion(BaseModel):
    """
    Tracks when a learner completes a curriculum level or leaves the institution.
    """
    COMPLETION_TYPES = (
        ('graduated', 'Graduated'),
        ('transferred', 'Transferred Out'),
        ('dropped', 'Dropped Out'),
        ('expelled', 'Expelled'),
    )

    student = models.ForeignKey(
        'accounts.Student',
        on_delete=models.CASCADE,
        related_name='completions'
    )
    curriculum = models.ForeignKey(
        'student_settings.Curriculum',
        on_delete=models.PROTECT
    )
    curriculum_level = models.ForeignKey(
        'student_settings.CurriculumLevel',
        on_delete=models.PROTECT,
        null=True, 
        blank=True
    )
    
    completion_date = models.DateField()
    completion_type = models.CharField(max_length=20, choices=COMPLETION_TYPES)
    remarks = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name = "Completion Record"
        verbose_name_plural = "Completion Records"

        db_table = 'student_completions'

    def __str__(self):
        return f"{self.student} - {self.completion_type}"
