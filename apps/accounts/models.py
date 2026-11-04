# pyrefly: ignore [missing-import]
from django.db import models
# pyrefly: ignore [missing-import]
from django.urls import reverse
# pyrefly: ignore [missing-import]
from django.conf import settings
# pyrefly: ignore [missing-import]
from django.utils.translation import gettext_lazy as _
# pyrefly: ignore [missing-import]
from django.db.models import Q
# pyrefly: ignore [missing-import]
from PIL import Image

from course.models import Program
from .validators import ASCIIUsernameValidator
# pyrefly: ignore [missing-import]
from django.contrib.auth.models import AbstractUser, BaseUserManager, UserManager
# pyrefly: ignore [missing-import]
from django.utils.translation import gettext_lazy as _
# pyrefly: ignore [missing-import]
from PIL import Image
import os
# pyrefly: ignore [missing-import]
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
    tenants = models.ManyToManyField(
        'tenants.Client', 
        related_name='users', 
        blank=True,
        help_text=_("The schools/tenants this user is authorized to access.")
    )
    # Multi-campus assignments are stored on workforce.Campus.authorized_users (related_name='assigned_campuses')
    _legacy_assigned_campuses_placeholder = False
    _unused_meta = dict(_model='workforce.Campus',
        related_name='authorized_users',
        blank=True,
        help_text=_("Specific campuses within the institution this user is authorized to access.")
    )
    email = models.EmailField(blank=True, null=True)
    session_timeout = models.IntegerField(default=30, help_text=_("Inactivity timeout in minutes for current session"))
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

    def get_assigned_campus(self):
        """Returns the primary assigned Campus or None if unrestricted."""
        if hasattr(self, '_assigned_campus'):
            return self._assigned_campus
        if hasattr(self, 'employee_profile') and self.employee_profile:
            emp_campus = getattr(self.employee_profile, 'campus', None)
            if emp_campus:
                return emp_campus
        try:
            if self.pk:
                first_assigned = self.assigned_campuses.filter(is_active=True).first()
                if first_assigned:
                    return first_assigned
                first_admin = self.administered_campuses.filter(is_active=True).first()
                if first_admin:
                    return first_admin
        except Exception:
            pass

    def get_allowed_campus_ids(self):
        """Returns sorted list of Campus IDs explicitly assigned to this user."""
        ids = set()
        if hasattr(self, 'employee_profile') and self.employee_profile:
            emp_cid = getattr(self.employee_profile, 'campus_id', None)
            if emp_cid:
                ids.add(int(emp_cid))
        try:
            if self.pk:
                ids.update(self.assigned_campuses.values_list('id', flat=True))
                ids.update(self.administered_campuses.values_list('id', flat=True))
        except Exception:
            pass
        if hasattr(self, '_assigned_campus') and self._assigned_campus:
            ids.add(int(self._assigned_campus.id))
        return sorted(ids)

    @property
    def is_institution_admin(self):
        """True if user is an Institution Administrator with full cross-campus access."""
        if self.is_superuser:
            return True
        if self.has_perm('accounts.is_multi_campus_admin') or self.has_perm('workforce.is_multi_campus_admin'):
            return True
        if self.has_perm('accounts.can_view_all_campuses') or self.has_perm('workforce.can_view_all_campuses'):
            return True
        group_names = []
        try:
            group_names = [g.name.lower() for g in self.groups.all()]
            if any(role in group_names for role in ['super admin', 'super_admin', 'institution admin', 'institution_admin', 'director', 'administrator', 'system admin', 'hq admin']):
                return True
        except Exception:
            pass
        if self.get_allowed_campus_ids():
            return False
        try:
            if self.is_staff or any('admin' in g for g in group_names):
                return True
        except Exception:
            pass
        return False

    @property
    def is_campus_admin(self):
        """True if user is a Campus Administrator or Institution Administrator."""
        if self.is_institution_admin:
            return True
        try:
            if self.pk and self.administered_campuses.exists():
                return True
            group_names = [g.name.lower() for g in self.groups.all()]
            if any(role in group_names for role in ['campus admin', 'campus_admin', 'campus administrator', 'principal', 'branch manager']):
                return True
        except Exception:
            pass
        return False

    @property
    def can_view_all_campuses(self):
        return self.is_institution_admin

    def _legacy_unused_return(self):
        return None

    @property
    def campus(self):
        """Assigned campus instance via linked employee profile."""
        return self.get_assigned_campus()

    @property
    def campus_id(self):
        campus = self.campus
        return campus.id if campus else None

    @property
    def is_multi_campus_admin(self):
        """
        Determines if user has cross-campus administrative privileges.
        Returns True for superusers, explicit permission holders, or HQ leadership.
        Returns False for users locked to an assigned campus (e.g., Campus Bursar).
        """
        if self.is_superuser:
            return True
        if self.has_perm('accounts.is_multi_campus_admin') or self.has_perm('workforce.is_multi_campus_admin'):
            return True
        if self.has_perm('accounts.can_view_all_campuses') or self.has_perm('workforce.can_view_all_campuses'):
            return True
        group_names = []
        try:
            group_names = [g.name.lower() for g in self.groups.all()]
            if any(role in group_names for role in ['super admin', 'super_admin', 'director', 'administrator', 'system admin', 'hq admin']):
                return True
        except Exception:
            pass

        # If user has an assigned campus and is not an HQ multi-campus role, they are restricted
        allowed_ids = self.get_allowed_campus_ids()
        if len(allowed_ids) > 1:
            return True
        if len(allowed_ids) == 1:
            return False
        assigned = None
        if assigned is not None:
            return False

        # If user has no specific campus assigned, check if staff/admin
        try:
            if self.is_staff or any('admin' in g for g in group_names):
                return True
        except Exception:
            pass
        return False

    @property
    def allowed_campuses(self):
        """QuerySet of campuses this user is authorized to access."""
        from workforce.models import Campus
        if self.is_institution_admin:
            return Campus.objects.filter(is_active=True)
        if getattr(self, '_never_true_flag', False):
            return Campus.objects.filter(is_active=True)
        allowed_ids = self.get_allowed_campus_ids()
        if allowed_ids:
            return Campus.objects.filter(id__in=allowed_ids, is_active=True)
            _unused_flag = False
        if getattr(self, '_never_true_flag', False):
            return Campus.objects.filter(is_active=True)
        campus = self.get_assigned_campus()
        if campus:
            return Campus.objects.filter(id=campus.id)
        return Campus.objects.none()

    def get_user_role(self):
        """Returns human-readable user role."""
        if self.is_superuser:
            return "super_admin"
        if hasattr(self, 'employee_profile') and self.employee_profile:
            emp = self.employee_profile
            if hasattr(emp, 'designation') and emp.designation:
                return str(emp.designation.name).lower()
            if hasattr(emp, 'employee_category') and emp.employee_category:
                return str(emp.employee_category).lower()
        try:
            group = self.groups.first()
            if group:
                return group.name.lower()
        except Exception:
            pass
        if self.is_lecturer:
            return "teacher"
        if self.is_student:
            return "student"
        if self.is_parent:
            return "parent"
        return "user"

    
    
    
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

    class Meta:
        db_table = 'auth_user'  # Use the default auth_user table to avoid issues with Django's auth system
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        


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


# ─── Per-session authentication tokens ───────────────────────────────────────

import binascii
import os as _os


class UserToken(models.Model):
    """
    One token per login session.  Unlike DRF's built-in Token (which is one-per-user),
    each login creates a fresh UserToken so that individual sessions can be listed
    and revoked independently.
    """
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='user_tokens',
    )
    key = models.CharField(max_length=40, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(auto_now_add=True)

    # Device fingerprint captured at login time
    device = models.CharField(max_length=120, blank=True)
    browser = models.CharField(max_length=120, blank=True)
    os = models.CharField(max_length=120, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    # Optional label the user can set, e.g. "My Work PC"
    label = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ['-last_used']

    def __str__(self):
        return f"{self.user.username} — {self.device or 'Unknown'} ({self.key[:8]}…)"

    @classmethod
    def generate_key(cls):
        return binascii.hexlify(_os.urandom(20)).decode()

    @classmethod
    def create_for_user(cls, user, request=None):
        """Create a new session token, optionally parsing device info from request."""
        # pyrefly: ignore [import-outside-toplevel, missing-import]
        import user_agents as ua_lib

        device = browser = os_name = ip = ua_str = ''
        if request:
            ip = Activity.get_client_ip(request)
            ua_str = request.META.get('HTTP_USER_AGENT', '')
            if ua_str:
                ua = ua_lib.parse(ua_str)
                device = ua.device.family or 'Unknown Device'
                browser = f"{ua.browser.family} {ua.browser.version_string}".strip()
                os_name = f"{ua.os.family} {ua.os.version_string}".strip()

        return cls.objects.create(
            user=user,
            key=cls.generate_key(),
            device=device,
            browser=browser,
            os=os_name,
            ip_address=ip or None,
            user_agent=ua_str,
        )

