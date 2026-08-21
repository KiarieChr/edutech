# pyrefly: ignore [missing-import]
from django.db import models
# pyrefly: ignore [missing-import]
from django.urls import reverse
# pyrefly: ignore [missing-import]
from django.conf import settings
# pyrefly: ignore [missing-import]
from django.db.models import Q
# pyrefly: ignore [missing-import]
from course.models import Program
# pyrefly: ignore [missing-import]
from accounts.models import User
# pyrefly: ignore [missing-import]
from django.utils.translation import gettext_lazy as _

FATHER = _("Father")
MOTHER = _("Mother")
BROTHER = _("Brother")
SISTER = _("Sister")
GRAND_MOTHER = _("Grand mother")
GRAND_FATHER = _("Grand father")
OTHER = _("Other")

RELATION_SHIP = (
    (FATHER, _("Father")),
    (MOTHER, _("Mother")),
    (BROTHER, _("Brother")),
    (SISTER, _("Sister")),
    (GRAND_MOTHER, _("Grand mother")),
    (GRAND_FATHER, _("Grand father")),
    (OTHER, _("Other")),
)

class StudentManager(models.Manager):
    def search(self, query=None):
        qs = self.get_queryset()
        if query is not None:
            or_lookup = Q(level__icontains=query) | Q(program__icontains=query)
            qs = qs.filter(
                or_lookup
            ).distinct()  # distinct() is often necessary with Q lookups
        return qs


class Student(models.Model):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('alumni', 'Alumni'),
        ('suspended', 'Suspended'),
        ('expelled', 'Expelled'),
        ('transferred', 'Transferred'),
        ('withdrawn', 'Withdrawn'),
    )

    student = models.OneToOneField(User, on_delete=models.CASCADE)
    
    # Identity & Demographics
    admission_number = models.CharField(max_length=50, unique=True, null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    nationality = models.CharField(max_length=100, null=True, blank=True, default='Kenyan')
    religion = models.CharField(max_length=50, null=True, blank=True)
    
    # Kenyan Admission Fields
    birth_certificate_number = models.CharField(max_length=50, null=True, blank=True, help_text='Birth certificate number')
    home_address = models.TextField(null=True, blank=True, help_text='Physical home address')
    
    # Medical Information
    medical_conditions = models.TextField(null=True, blank=True, help_text='Any known medical conditions')
    allergies = models.TextField(null=True, blank=True, help_text='Known allergies')
    special_needs = models.TextField(null=True, blank=True, help_text='Special educational needs or requirements')
    blood_group = models.CharField(max_length=5, null=True, blank=True, choices=[
        ('A+', 'A+'), ('A-', 'A-'), ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'), ('O+', 'O+'), ('O-', 'O-')
    ])
    
    # Emergency Contact
    emergency_contact_name = models.CharField(max_length=150, null=True, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, null=True, blank=True)
    emergency_contact_relationship = models.CharField(max_length=50, null=True, blank=True)
    
    # Previous School Information
    previous_school_name = models.CharField(max_length=200, null=True, blank=True)
    previous_school_address = models.TextField(null=True, blank=True)
    previous_class = models.CharField(max_length=50, null=True, blank=True)
    transfer_reason = models.TextField(null=True, blank=True)
    previous_school_leaving_date = models.DateField(null=True, blank=True)
    
    # Intake/Cohort tracking - tracks which cohort the student belongs to
    intake = models.ForeignKey(
        'student_settings.Intake',
        on_delete=models.PROTECT,
        related_name='students',
        null=True,
        blank=True,
        help_text='The intake cohort this student belongs to'
    )
    admission_date = models.DateField(
        null=True,
        blank=True,
        help_text='Date when student was admitted to the school'
    )
    campus = models.ForeignKey(
        'workforce.Campus',
        on_delete=models.PROTECT,
        related_name='students',
        null=True,
        blank=True,
        help_text='Primary campus this student belongs to'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active'
    )

    objects = StudentManager()

    class Meta:
        ordering = ("-student__date_joined",)

    def __str__(self):
        return f"{self.student.get_full_name} ({self.admission_number})"
    
    @classmethod
    def get_gender_count(cls):
        males_count = Student.objects.filter(student__gender="M").count()
        females_count = Student.objects.filter(student__gender="F").count()

        return {"M": males_count, "F": females_count}

    def get_absolute_url(self):
        return reverse("profile_single", kwargs={"user_id": self.id})

    def delete(self, *args, **kwargs):
        self.student.delete()
        super().delete(*args, **kwargs)
    
    @property
    def current_enrollment(self):
        """Get the student's current active enrollment"""
        from student_settings.models import Enrollment
        return Enrollment.objects.filter(
            student=self,
            is_active=True,
            is_deleted=False
        ).order_by('-academic_year__start_date', '-term__start_date').first()
    
    @property
    def current_grade(self):
        """Get the student's current grade/class"""
        enrollment = self.current_enrollment
        if enrollment and enrollment.grade and not enrollment.grade.is_deleted:
            return enrollment.grade
        # Fallback to intake entry grade for new students
        if self.intake and self.intake.entry_grade and not self.intake.entry_grade.is_deleted:
            return self.intake.entry_grade
        return None
    
    @property
    def current_stream(self):
        """Get the student's current stream"""
        enrollment = self.current_enrollment
        return enrollment.stream if enrollment else None
    
    @property
    def current_academic_year(self):
        """Get the student's current academic year"""
        enrollment = self.current_enrollment
        return enrollment.academic_year if enrollment else None
    
    @property
    def current_term(self):
        """Get the student's current term"""
        enrollment = self.current_enrollment
        return enrollment.term if enrollment else None


class Parent(models.Model):
    """
    Connect student with their parent, parents can
    only view their connected students information
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, null=True, on_delete=models.SET_NULL, related_name='parents')
    first_name = models.CharField(max_length=120)
    last_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=60, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)

    # What is the relationship between the student and
    # the parent (i.e. father, mother, brother, sister)
    relation_ship = models.TextField(choices=RELATION_SHIP, blank=True)

    class Meta:
        ordering = ("-user__date_joined",)

    def __str__(self):
        return self.user.username


class DepartmentHead(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    department = models.ForeignKey(Program, on_delete=models.CASCADE, null=True)

    class Meta:
        ordering = ("-user__date_joined",)

    def __str__(self):
        return "{}".format(self.user)
