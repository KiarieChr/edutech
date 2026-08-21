from django.db import models
from django.db.models import Q
from django.conf import settings
from django.utils.translation import gettext_lazy as _


NEWS = _("News")
EVENTS = _("Event")

POST = (
    (NEWS, _("News")),
    (EVENTS, _("Event")),
)

FIRST = _("First")
SECOND = _("Second")
THIRD = _("Third")

SEMESTER = (
    (FIRST, _("First")),
    (SECOND, _("Second")),
    (THIRD, _("Third")),
)


class NewsAndEventsQuerySet(models.query.QuerySet):
    def search(self, query):
        lookups = (
            Q(title__icontains=query)
            | Q(summary__icontains=query)
            | Q(posted_as__icontains=query)
        )
        return self.filter(lookups).distinct()


class NewsAndEventsManager(models.Manager):
    def get_queryset(self):
        return NewsAndEventsQuerySet(self.model, using=self._db)

    def all(self):
        return self.get_queryset()

    def get_by_id(self, id):
        qs = self.get_queryset().filter(
            id=id
        )  # NewsAndEvents.objects == self.get_queryset()
        if qs.count() == 1:
            return qs.first()
        return None

    def search(self, query):
        return self.get_queryset().search(query)


class NewsAndEvents(models.Model):
    title = models.CharField(max_length=200, null=True)
    summary = models.TextField(max_length=200, blank=True, null=True)
    posted_as = models.CharField(choices=POST, max_length=10)
    updated_date = models.DateTimeField(auto_now=True, auto_now_add=False, null=True)
    upload_time = models.DateTimeField(auto_now=False, auto_now_add=True, null=True)

    objects = NewsAndEventsManager()

    def __str__(self):
        return f"{self.title}"


class Session(models.Model):
    session = models.CharField(max_length=200, unique=True)
    is_current_session = models.BooleanField(default=False, blank=True, null=True)
    next_session_begins = models.DateField(blank=True, null=True)

    def __str__(self):
        return f"{self.session}"


class Semester(models.Model):
    semester = models.CharField(max_length=10, choices=SEMESTER, blank=True)
    is_current_semester = models.BooleanField(default=False, blank=True, null=True)
    session = models.ForeignKey(
        Session, on_delete=models.CASCADE, blank=True, null=True
    )
    next_semester_begins = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.semester}"


class ActivityLog(models.Model):
    message = models.TextField()
    created_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"[{self.created_at}]{self.message}"


# ============================================================================
# INSTITUTION PROFILE (Singleton)
# ============================================================================

class InstitutionProfile(models.Model):
    """
    Singleton model storing the school/institution's identity and contact info.
    Only one row should ever exist — use InstitutionProfile.get_instance().
    """

    class BusinessSector(models.TextChoices):
        EDUCATION = 'education', _('Education & Academic')
        RETAIL = 'retail', _('Retail & Commerce')
        HEALTHCARE = 'healthcare', _('Healthcare')
        CORPORATE = 'corporate', _('Corporate / Services')
        NGO = 'ngo', _('Non-Governmental Organization')
        GENERAL = 'general', _('General Business')

    class InstitutionType(models.TextChoices):
        LOWER_PRIMARY = 'lower_primary', _('Lower Primary')
        UPPER_PRIMARY = 'upper_primary', _('Upper Primary')
        PRIMARY = 'primary', _('Primary School')
        JUNIOR_SECONDARY = 'junior_secondary', _('Junior Secondary')
        SENIOR_SECONDARY = 'senior_secondary', _('Senior Secondary')
        SECONDARY = 'secondary', _('Secondary School (Junior & Senior)')
        MIXED = 'mixed', _('Mixed (Primary & Secondary)')
        TERTIARY = 'tertiary', _('Tertiary / College')
        UNIVERSITY = 'university', _('University')
        TVET = 'tvet', _('TVET Institution')

    # Identity
    business_sector = models.CharField(
        max_length=50, choices=BusinessSector.choices,
        default=BusinessSector.EDUCATION
    )
    enabled_modules = models.JSONField(
        default=list, blank=True, null=True,
        help_text='List of enabled modules e.g., ["academics", "hr", "procurement"]'
    )
    name = models.CharField(_('Institution Name'), max_length=255)
    short_name = models.CharField(_('Abbreviation'), max_length=50, blank=True)
    motto = models.CharField(max_length=255, blank=True)
    institution_type = models.CharField(
        max_length=20, choices=InstitutionType.choices,
        default=InstitutionType.SECONDARY
    )
    # NOTE: max_length=20 covers 'junior_secondary' (16) and 'senior_secondary' (16)
    registration_number = models.CharField(
        _('Registration / License No.'), max_length=100, blank=True
    )
    established_date = models.DateField(null=True, blank=True)
    logo = models.ImageField(upload_to='institution/', blank=True, null=True)

    # Contact
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    website = models.URLField(blank=True)

    # Address
    address_line_1 = models.CharField(max_length=255, blank=True)
    address_line_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    county = models.CharField(_('County / State'), max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, default='Kenya')

    # Branding
    primary_color = models.CharField(max_length=7, default='#4f46e5', blank=True)
    secondary_color = models.CharField(max_length=7, default='#f59e0b', blank=True)

    # Portal
    portal_url = models.URLField(
        _('Student/Parent Portal URL'), blank=True,
        help_text='Login URL sent in admission emails'
    )

    # Document Signing
    principal_name = models.CharField(
        _('Principal / Head Name'), max_length=150, blank=True,
        help_text='Appears on the signature block of generated letters'
    )
    principal_title = models.CharField(
        _('Principal Title'), max_length=100, default='PRINCIPAL', blank=True,
        help_text='e.g. PRINCIPAL, HEAD TEACHER, DIRECTOR'
    )
    signature_image = models.ImageField(
        upload_to='institution/signatures/', null=True, blank=True,
        help_text='Drawn or uploaded signature — appears above the principal name on letters'
    )
    stamp_image = models.ImageField(
        upload_to='institution/stamps/', null=True, blank=True,
        help_text='Official school stamp / seal — overlaid on the signature block'
    )

    class Meta:
        verbose_name = _('Institution Profile')
        verbose_name_plural = _('Institution Profile')

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Enforce singleton — always use pk=1
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_instance(cls):
        """Return the singleton instance, creating a default if needed."""
        obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={'name': 'My School'}
        )
        return obj


# ============================================================================
# AUDIT LOG
# ============================================================================

class AuditLog(models.Model):
    """
    Comprehensive system-wide audit trail.
    Populated by AuditMiddleware (request-level) and post_save/post_delete signals.
    """

    class Action(models.TextChoices):
        CREATE = 'CREATE', _('Create')
        UPDATE = 'UPDATE', _('Update')
        DELETE = 'DELETE', _('Delete')
        LOGIN = 'LOGIN', _('Login')
        LOGOUT = 'LOGOUT', _('Logout')
        LOGIN_FAILED = 'LOGIN_FAILED', _('Login Failed')
        VIEW = 'VIEW', _('View')
        EXPORT = 'EXPORT', _('Export')
        IMPORT = 'IMPORT', _('Import')
        APPROVE = 'APPROVE', _('Approve')
        REJECT = 'REJECT', _('Reject')
        OTHER = 'OTHER', _('Other')

    class Severity(models.TextChoices):
        INFO = 'INFO', _('Info')
        WARNING = 'WARNING', _('Warning')
        ERROR = 'ERROR', _('Error')
        CRITICAL = 'CRITICAL', _('Critical')

    # Who
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='audit_logs'
    )
    username = models.CharField(max_length=150, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    # What
    action = models.CharField(max_length=20, choices=Action.choices)
    severity = models.CharField(
        max_length=10, choices=Severity.choices, default=Severity.INFO
    )

    # Where
    module = models.CharField(max_length=100, blank=True, help_text='App label')
    model_name = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=50, blank=True)
    object_repr = models.CharField(max_length=255, blank=True)

    # Request details
    request_method = models.CharField(max_length=10, blank=True)
    request_path = models.CharField(max_length=500, blank=True)
    response_code = models.PositiveIntegerField(null=True, blank=True)

    # Change details
    changes = models.JSONField(
        null=True, blank=True,
        help_text='Diff of old → new values for UPDATE actions'
    )
    description = models.TextField(blank=True)

    # When
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'core_audit_log'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['action', '-timestamp']),
            models.Index(fields=['module', 'model_name']),
        ]

    def __str__(self):
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {self.action} by {self.username or 'system'}"


# ============================================================================
# SYSTEM CONFIGURATION (Key-Value Store)
# ============================================================================

class SystemConfiguration(models.Model):
    """
    Typed key-value configuration store, grouped by category.
    Each key is unique. Values are stored as text and cast by value_type.
    """

    class ValueType(models.TextChoices):
        STRING = 'string', _('String')
        INTEGER = 'integer', _('Integer')
        FLOAT = 'float', _('Float')
        BOOLEAN = 'boolean', _('Boolean')
        JSON = 'json', _('JSON')
        SECRET = 'secret', _('Secret')  # masked in API responses

    class Group(models.TextChoices):
        PAYMENTS = 'payments', _('Payments & M-Pesa')
        TIMETABLE = 'timetable', _('Timetable')
        NOTIFICATIONS = 'notifications', _('Notifications')
        GRADING = 'grading', _('Grading & Reports')
        SECURITY = 'security', _('Security')
        ADMISSIONS = 'admissions', _('Admissions')
        GENERAL = 'general', _('General')

    key = models.CharField(max_length=100, unique=True, db_index=True)
    value = models.TextField(blank=True, default='')
    value_type = models.CharField(
        max_length=10, choices=ValueType.choices, default=ValueType.STRING
    )
    group = models.CharField(
        max_length=20, choices=Group.choices, default=Group.GENERAL
    )
    label = models.CharField(
        max_length=200,
        help_text='Human-readable label shown in the UI'
    )
    description = models.TextField(blank=True, help_text='Help text shown under the field')
    is_editable = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
    )

    class Meta:
        db_table = 'core_system_config'
        ordering = ['group', 'display_order', 'key']

    def __str__(self):
        return f"{self.group}/{self.key}"

    @classmethod
    def get(cls, key, default=None):
        """Retrieve a config value, cast to its declared type."""
        try:
            obj = cls.objects.get(key=key)
            return obj.typed_value
        except cls.DoesNotExist:
            return default

    @property
    def typed_value(self):
        """Return value cast to the declared type."""
        import json
        v = self.value
        if self.value_type == self.ValueType.BOOLEAN:
            return v.lower() in ('true', '1', 'yes')
        elif self.value_type == self.ValueType.INTEGER:
            return int(v) if v else 0
        elif self.value_type == self.ValueType.FLOAT:
            return float(v) if v else 0.0
        elif self.value_type == self.ValueType.JSON:
            return json.loads(v) if v else {}
        return v
