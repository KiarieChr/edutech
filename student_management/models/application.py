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
    
    RELIGION_CHOICES = (
        ('christian', 'Christian'),
        ('muslim', 'Muslim'),
        ('hindu', 'Hindu'),
        ('traditional', 'African Traditional'),
        ('other', 'Other'),
        ('none', 'None'),
    )

    # Applicant Details
    first_name = models.CharField(max_length=120)
    last_name = models.CharField(max_length=120)
    middle_name = models.CharField(max_length=120, blank=True, null=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=[('M', 'Male'), ('F', 'Female')], null=True, blank=True)
    
    # Kenyan Identity Fields
    birth_certificate_number = models.CharField(max_length=50, null=True, blank=True, help_text='Birth certificate number')
    nationality = models.CharField(max_length=100, default='Kenyan', blank=True, null=True)
    religion = models.CharField(max_length=50, choices=RELIGION_CHOICES, null=True, blank=True)
    home_address = models.TextField(null=True, blank=True, help_text='Physical home address')
    county = models.CharField(max_length=100, blank=True, null=True, help_text='County of residence')
    sub_county = models.CharField(max_length=100, blank=True, null=True)
    
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
    
    # Primary Guardian/Parent Contact Info
    guardian_name = models.CharField(max_length=120, blank=True, null=True)
    guardian_relationship = models.CharField(max_length=50, blank=True, null=True, choices=[
        ('father', 'Father'), ('mother', 'Mother'), ('guardian', 'Guardian'),
        ('uncle', 'Uncle'), ('aunt', 'Aunt'), ('grandparent', 'Grandparent'), ('other', 'Other')
    ])
    guardian_id_number = models.CharField(max_length=20, blank=True, null=True, help_text='National ID or Passport')
    guardian_occupation = models.CharField(max_length=100, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    guardian_address = models.TextField(blank=True, null=True)
    
    # Secondary Guardian Contact
    guardian2_name = models.CharField(max_length=120, blank=True, null=True)
    guardian2_relationship = models.CharField(max_length=50, blank=True, null=True)
    guardian2_phone = models.CharField(max_length=20, blank=True, null=True)
    guardian2_email = models.EmailField(blank=True, null=True)
    
    # Emergency Contact
    emergency_contact_name = models.CharField(max_length=150, null=True, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, null=True, blank=True)
    emergency_contact_relationship = models.CharField(max_length=50, null=True, blank=True)
    
    # Medical Information
    medical_conditions = models.TextField(null=True, blank=True, help_text='Any known medical conditions')
    allergies = models.TextField(null=True, blank=True, help_text='Known allergies')
    special_needs = models.TextField(null=True, blank=True, help_text='Special educational needs or requirements')
    blood_group = models.CharField(max_length=5, null=True, blank=True, choices=[
        ('A+', 'A+'), ('A-', 'A-'), ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'), ('O+', 'O+'), ('O-', 'O-')
    ])
    doctor_name = models.CharField(max_length=120, blank=True, null=True)
    doctor_phone = models.CharField(max_length=20, blank=True, null=True)
    health_insurance = models.CharField(max_length=100, blank=True, null=True, help_text='NHIF or private insurance')
    
    # Previous School Information
    previous_school_name = models.CharField(max_length=200, null=True, blank=True)
    previous_school_address = models.TextField(null=True, blank=True)
    previous_class = models.CharField(max_length=50, null=True, blank=True)
    previous_school_contact = models.CharField(max_length=20, null=True, blank=True)
    transfer_reason = models.TextField(null=True, blank=True)
    previous_school_leaving_date = models.DateField(null=True, blank=True)
    is_transfer = models.BooleanField(default=False)
    
    # Assessment/Score
    assessment_score = models.CharField(max_length=50, blank=True, null=True)
    
    # Documents (store file paths or use FileField)
    birth_certificate = models.FileField(upload_to='applications/documents/', null=True, blank=True)
    previous_report_card = models.FileField(upload_to='applications/documents/', null=True, blank=True)
    transfer_letter = models.FileField(upload_to='applications/documents/', null=True, blank=True)
    passport_photo = models.ImageField(upload_to='applications/photos/', null=True, blank=True)
    medical_report = models.FileField(upload_to='applications/documents/', null=True, blank=True)
    
    # Status & Processing
    application_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    review_notes = models.TextField(blank=True, null=True)
    referral_source = models.CharField(max_length=50, blank=True, null=True, choices=[
        ('walk_in', 'Walk-in'), ('online', 'Online'), ('referral', 'Referral'),
        ('advertisement', 'Advertisement'), ('other', 'Other')
    ])
    
    class Meta:
        ordering = ['-created_at']
        
    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.intake.name}"
