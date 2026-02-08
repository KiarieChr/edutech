from django.db import models
from django.urls import reverse
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.db.models import Q
from PIL import Image

from course.models import Program
from .validators import ASCIIUsernameValidator
from django.contrib.auth.models import AbstractUser, BaseUserManager, UserManager
from django.utils.translation import gettext_lazy as _
from PIL import Image
import os
from django.contrib.auth.validators import UnicodeUsernameValidator 


# LEVEL_COURSE = "Level course"
BACHELOR_DEGREE = _("Bachelor")
MASTER_DEGREE = _("Master")

LEVEL = (
    # (LEVEL_COURSE, "Level course"),
    (BACHELOR_DEGREE, _("Bachelor Degree")),
    (MASTER_DEGREE, _("Master Degree")),
)

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




class CustomUserManager(BaseUserManager):
    """Custom user manager that handles email and username authentication."""
    
    def create_user(self, email=None, username=None, password=None, **extra_fields):
        """
        Create and save a regular User with the given email and password.
        """
        if not email and not username:
            raise ValueError(_('At least email or username must be set'))
        
        # Normalize email if provided
        if email:
            email = self.normalize_email(email)
            extra_fields['email'] = email
            
        # Generate username from email if not provided
        if not username and email:
            # Use email prefix as username
            username = email.split('@')[0]
            # Ensure uniqueness
            base_username = username
            counter = 1
            while self.model.objects.filter(username=base_username).exists():
                base_username = f"{username}{counter}"
                counter += 1
            username = base_username
        
        # Create user
        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email=None, username=None, password=None, **extra_fields):
        """
        Create and save a SuperUser with the given email and password.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))
        
        return self.create_user(email, username, password, **extra_fields)
    
    def search(self, query=None):
        """Search users by username, email, first name, or last name."""
        queryset = self.get_queryset()
        if query is not None:
            or_lookup = (
                Q(username__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(email__icontains=query)
            )
            queryset = queryset.filter(or_lookup).distinct()
        return queryset
    
    def get_student_count(self):
        return self.model.objects.filter(is_student=True).count()
    
    def get_lecturer_count(self):
        return self.model.objects.filter(is_lecturer=True).count()
    
    def get_superuser_count(self):
        return self.model.objects.filter(is_superuser=True).count()
    
    def get_by_email(self, email):
        """Get user by email address."""
        try:
            return self.get(email__iexact=email)
        except self.model.DoesNotExist:
            return None


GENDERS = ((_("M"), _("Male")), (_("F"), _("Female")))


class User(AbstractUser):
    is_student = models.BooleanField(default=False)
    is_lecturer = models.BooleanField(default=False)
    is_parent = models.BooleanField(default=False)
    is_dep_head = models.BooleanField(default=False)
    gender = models.CharField(max_length=1, choices=GENDERS, blank=True, null=True)
    phone = models.CharField(max_length=60, blank=True, null=True)
    address = models.CharField(max_length=60, blank=True, null=True)
    picture = models.ImageField(
        upload_to="profile_pictures/%y/%m/%d/", default="default.png", null=True
    )
    email = models.EmailField(blank=True, null=True)
    activated_on = models.DateTimeField(blank=True, null=True)
    is_first_login = models.BooleanField(
        default=True,
        help_text="Indicates if user needs to complete first-time setup"
    )
    
    # Updated to UnicodeUsernameValidator
    username_validator = UnicodeUsernameValidator()
    
    objects = CustomUserManager()
    
    class Meta:
        ordering = ("-date_joined",)
    
    @property
    def get_full_name(self):
        full_name = self.username
        if self.first_name and self.last_name:
            full_name = f"{self.first_name} {self.last_name}"
        return full_name
    
    def __str__(self):
        return "{} ({})".format(self.username, self.get_full_name)
    
    
    
    def get_picture(self):
        try:
            return self.picture.url
        except:
            no_picture = settings.MEDIA_URL + "default.png"
            return no_picture
    
    def get_absolute_url(self):
        return reverse("profile_single", kwargs={"user_id": self.id})
    
    def save(self, *args, **kwargs):
        # If no username but has email, generate username from email
        if not self.username and self.email:
            username = self.email.split('@')[0]
            # Ensure uniqueness
            base_username = username
            counter = 1
            while User.objects.filter(username=base_username).exclude(pk=self.pk).exists():
                base_username = f"{username}{counter}"
                counter += 1
            self.username = base_username
        
        super().save(*args, **kwargs)
        
        # Resize picture if it exists
        try:
            if self.picture and self.picture.name != 'default.png':
                img = Image.open(self.picture.path)
                if img.height > 300 or img.width > 300:
                    output_size = (300, 300)
                    img.thumbnail(output_size)
                    img.save(self.picture.path)
        except Exception as e:
            print(f"Error resizing image: {e}")
    
    def delete(self, *args, **kwargs):
        if self.picture and self.picture.name != 'default.png':
            try:
                if os.path.isfile(self.picture.path):
                    os.remove(self.picture.path)
            except:
                pass
        super().delete(*args, **kwargs)
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
    nationality = models.CharField(max_length=100, null=True, blank=True)
    religion = models.CharField(max_length=50, null=True, blank=True)
    
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
    student = models.OneToOneField(Student, null=True, on_delete=models.SET_NULL)
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

class OTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='otps')
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    def __str__(self):
        return f"OTP for {self.user.username} - {self.code}"

    def is_expired(self):
        from django.utils import timezone
        return timezone.now() > self.expires_at


# Activity tracking for user actions
class Activity(models.Model):
    """
    Track user activities like login, password changes, profile updates, etc.
    Useful for security auditing and activity logging.
    """
    ACTIVITY_TYPES = [
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('password_change', 'Password Change'),
        ('profile_update', 'Profile Update'),
        ('avatar_upload', 'Avatar Upload'),
        ('session_terminate', 'Session Terminated'),
        ('permission_change', 'Permission Change'),
        ('failed_login', 'Failed Login Attempt'),
        ('email_verification', 'Email Verified'),
        ('account_locked', 'Account Locked'),
        ('account_unlocked', 'Account Unlocked'),
    ]
    
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('pending', 'Pending'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=50, choices=ACTIVITY_TYPES)
    description = models.CharField(max_length=255, blank=True)
    device = models.CharField(max_length=100, blank=True, null=True)
    browser = models.CharField(max_length=100, blank=True, null=True)
    os = models.CharField(max_length=100, blank=True, null=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='success')
    user_agent = models.TextField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)  # Extra data as JSON
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['activity_type', '-timestamp']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.activity_type} - {self.timestamp}"

    @classmethod
    def log_activity(cls, user, activity_type, request=None, description='', status='success', **kwargs):
        """
        Helper method to log user activities
        """
        import user_agents
        from django.utils import timezone
        
        device = ''
        browser = ''
        os = ''
        ip_address = ''
        user_agent_string = ''
        
        if request:
            # Get IP address
            ip_address = cls.get_client_ip(request)
            
            # Parse user agent
            user_agent_string = request.META.get('HTTP_USER_AGENT', '')
            ua = user_agents.parse(user_agent_string)
            device = ua.device.family if ua else 'Unknown'
            browser = f"{ua.browser.family} {ua.browser.version_string}" if ua else 'Unknown'
            os = f"{ua.os.family} {ua.os.version_string}" if ua else 'Unknown'
        
        activity = cls(
            user=user,
            activity_type=activity_type,
            description=description,
            device=device,
            browser=browser,
            os=os,
            ip_address=ip_address,
            user_agent=user_agent_string,
            status=status,
            metadata=kwargs
        )
        activity.save()
        return activity

    @staticmethod
    def get_client_ip(request):
        """Get client IP address from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


