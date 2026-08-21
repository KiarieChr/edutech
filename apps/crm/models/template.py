from django.db import models

class CommunicationTemplate(models.Model):
    CATEGORY_CHOICES = (
        ('ACADEMIC', 'Academic'),
        ('FEES', 'Fees'),
        ('ATTENDANCE', 'Attendance'),
        ('EXAMINATION', 'Examination'),
        ('DISCIPLINE', 'Discipline'),
        ('ADMISSION', 'Admission'),
        ('GENERAL', 'General Announcement'),
    )
    
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='GENERAL')
    body = models.TextField()
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "crm_communication_template"
        
    def __str__(self):
        return f"{self.name} ({self.category})"
