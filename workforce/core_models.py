"""
HR & Payroll Django Models for Academic ERP
Part 1: Core Models, Address & Location Management
"""

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.translation import gettext_lazy as _
from decimal import Decimal
from django.contrib.auth import get_user_model

User = get_user_model()


# ============================================================================
# ABSTRACT BASE MODELS
# ============================================================================

class TimestampedModel(models.Model):
    """Abstract model with created and updated timestamps"""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        abstract = True


class AuditedModel(TimestampedModel):
    """Abstract model with audit fields"""
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='%(class)s_created'
    )
    updated_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='%(class)s_updated'
    )
    
    class Meta:
        abstract = True


# ============================================================================
# CORE EMPLOYEE MODEL (Already exists - just referencing)
# ============================================================================

class Employee(AuditedModel):
    """Base Employee Model"""
    
    class EmployeeCategory(models.TextChoices):
        TEACHING = 'teaching', _('Teaching Staff')
        NON_TEACHING = 'non_teaching', _('Non-Teaching Staff')
        CONTRACT = 'contract', _('Contract Staff')
        CASUAL = 'casual', _('Casual Worker')
        VISITING = 'visiting', _('Visiting Faculty')
    
    class PayrollType(models.TextChoices):
        MONTHLY = 'monthly', _('Monthly')
        HOURLY = 'hourly', _('Hourly')
        CONTRACT = 'contract', _('Contract')
        DAILY = 'daily', _('Daily')
    
    class EmploymentStatus(models.TextChoices):
        ACTIVE = 'active', _('Active')
        PROBATION = 'probation', _('On Probation')
        SUSPENDED = 'suspended', _('Suspended')
        TERMINATED = 'terminated', _('Terminated')
        RESIGNED = 'resigned', _('Resigned')
        RETIRED = 'retired', _('Retired')
    
    class Gender(models.TextChoices):
        MALE = 'male', _('Male')
        FEMALE = 'female', _('Female')
        OTHER = 'other', _('Other')
    
    # Primary identification
    employee_no = models.CharField(max_length=20, unique=True, db_index=True)
    
    # Personal details
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=10, choices=Gender.choices)
    national_id = models.CharField(max_length=50, unique=True)
    passport_number = models.CharField(max_length=50, blank=True)
    
    # Contact
    personal_email = models.EmailField()
    official_email = models.EmailField()
    phone_primary = models.CharField(max_length=20)
    phone_secondary = models.CharField(max_length=20, blank=True)
    
    # Employment details
    employee_category = models.CharField(
        max_length=20, 
        choices=EmployeeCategory.choices
    )
    payroll_type = models.CharField(max_length=20, choices=PayrollType.choices)
    employment_status = models.CharField(
        max_length=20, 
        choices=EmploymentStatus.choices,
        default=EmploymentStatus.PROBATION
    )
    
    # Dates
    hire_date = models.DateField()
    confirmation_date = models.DateField(null=True, blank=True)
    termination_date = models.DateField(null=True, blank=True)
    
    # References to other modules
    job_grade = models.ForeignKey(
        'JobGrade', 
        on_delete=models.PROTECT,
        null=True
    )
    department = models.ForeignKey(
        'Department', 
        on_delete=models.PROTECT,
        null=True
    )
    
    class Meta:
        db_table = 'hr_employee'
        ordering = ['employee_no']
        indexes = [
            models.Index(fields=['employee_no']),
            models.Index(fields=['employment_status']),
            models.Index(fields=['employee_category']),
        ]
    
    def __str__(self):
        return f"{self.employee_no} - {self.get_full_name()}"
    
    def get_full_name(self):
        return f"{self.first_name} {self.middle_name} {self.last_name}".strip()


# ============================================================================
# MODULE 1: ADDRESS & LOCATION MANAGEMENT
# ============================================================================

class Country(TimestampedModel):
    """Country master data"""
    code = models.CharField(max_length=2, unique=True, help_text="ISO 3166-1 alpha-2")
    name = models.CharField(max_length=100)
    phone_code = models.CharField(max_length=10)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'hr_country'
        verbose_name_plural = 'Countries'
        ordering = ['name']
    
    def __str__(self):
        return self.name


class County(TimestampedModel):
    """County/District/State"""
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='counties')
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'hr_county'
        verbose_name_plural = 'Counties'
        ordering = ['country', 'name']
        unique_together = ['country', 'code']
    
    def __str__(self):
        return f"{self.name}, {self.country.name}"


class SubCounty(TimestampedModel):
    """Sub-County/Ward"""
    county = models.ForeignKey(County, on_delete=models.CASCADE, related_name='subcounties')
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=100)
    
    class Meta:
        db_table = 'hr_subcounty'
        verbose_name_plural = 'Sub-Counties'
        ordering = ['county', 'name']
    
    def __str__(self):
        return f"{self.name}, {self.county.name}"


class Village(TimestampedModel):
    """Village/Location"""
    subcounty = models.ForeignKey(
        SubCounty, 
        on_delete=models.CASCADE, 
        related_name='villages'
    )
    name = models.CharField(max_length=100)
    
    class Meta:
        db_table = 'hr_village'
        ordering = ['subcounty', 'name']
    
    def __str__(self):
        return self.name


class EmployeeAddress(AuditedModel):
    """Employee addresses - supports multiple addresses per employee"""
    
    class AddressType(models.TextChoices):
        CURRENT = 'current', _('Current Address')
        PERMANENT = 'permanent', _('Permanent Address')
        EMERGENCY = 'emergency', _('Emergency Contact Address')
        POSTAL = 'postal', _('Postal Address')
    
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE, 
        related_name='addresses'
    )
    address_type = models.CharField(max_length=20, choices=AddressType.choices)
    
    # Location hierarchy
    country = models.ForeignKey(Country, on_delete=models.PROTECT)
    county = models.ForeignKey(County, on_delete=models.PROTECT)
    subcounty = models.ForeignKey(SubCounty, on_delete=models.PROTECT, null=True, blank=True)
    village = models.ForeignKey(Village, on_delete=models.PROTECT, null=True, blank=True)
    
    # Address details
    street_address = models.CharField(max_length=255)
    building_name = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    city = models.CharField(max_length=100)
    landmark = models.CharField(max_length=255, blank=True)
    
    # GPS coordinates for future mapping
    latitude = models.DecimalField(
        max_digits=10, 
        decimal_places=8, 
        null=True, 
        blank=True
    )
    longitude = models.DecimalField(
        max_digits=11, 
        decimal_places=8, 
        null=True, 
        blank=True
    )
    
    # Flags
    is_primary = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    verified_date = models.DateField(null=True, blank=True)
    verified_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='verified_addresses'
    )
    
    # Validity period
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    
    class Meta:
        db_table = 'hr_employee_address'
        verbose_name_plural = 'Employee Addresses'
        ordering = ['-is_primary', '-effective_from']
        indexes = [
            models.Index(fields=['employee', 'address_type']),
            models.Index(fields=['is_primary']),
        ]
    
    def __str__(self):
        return f"{self.employee.employee_no} - {self.get_address_type_display()}"
    
    def save(self, *args, **kwargs):
        # Ensure only one primary address per type
        if self.is_primary:
            EmployeeAddress.objects.filter(
                employee=self.employee,
                address_type=self.address_type,
                is_primary=True
            ).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)


class EmergencyContact(AuditedModel):
    """Emergency contact information"""
    
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE, 
        related_name='emergency_contacts'
    )
    contact_name = models.CharField(max_length=200)
    relationship = models.CharField(max_length=50)
    phone_primary = models.CharField(max_length=20)
    phone_secondary = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    
    address = models.ForeignKey(
        EmployeeAddress, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='emergency_contacts'
    )
    
    is_primary = models.BooleanField(default=False)
    can_make_medical_decisions = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'hr_emergency_contact'
        ordering = ['-is_primary', 'contact_name']
    
    def __str__(self):
        return f"{self.employee.employee_no} - {self.contact_name}"