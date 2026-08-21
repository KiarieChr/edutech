from django.db import models
from .parent import ParentGuardian
from student_management.models.profiles import Student

class ParentStudentRelationship(models.Model):
    parent = models.ForeignKey(ParentGuardian, on_delete=models.CASCADE, related_name='students')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='crm_parents')
    relationship_type = models.CharField(max_length=50) # FATHER, MOTHER, GUARDIAN, SPONSOR, OTHER
    
    is_primary_contact = models.BooleanField(default=False)
    is_emergency_contact = models.BooleanField(default=False)
    
    can_receive_academic_updates = models.BooleanField(default=True)
    can_receive_financial_updates = models.BooleanField(default=False)
    can_receive_attendance_updates = models.BooleanField(default=True)
    can_receive_disciplinary_updates = models.BooleanField(default=True)
    can_receive_general_notifications = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "crm_parent_student_relationship"
        unique_together = ('parent', 'student')

    def __str__(self):
        return f"{self.parent} -> {self.student} ({self.relationship_type})"
