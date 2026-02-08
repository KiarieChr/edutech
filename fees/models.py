from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from decimal import Decimal

# Import Account to validate links, but we only store reference ID effectively via ForeignKey
from finance.models import Account

class FeeStructure(models.Model):
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('ACTIVE', 'Active'),
        ('INACTIVE', 'Inactive'),
    )

    academic_year = models.ForeignKey(
        'student_settings.AcademicYear', 
        on_delete=models.PROTECT, # Protect historical data
        related_name='fee_structures'
    )
    term = models.ForeignKey(
        'student_settings.Term', 
        on_delete=models.PROTECT,
        related_name='fee_structures'
    )
    grade = models.ForeignKey(
        'student_settings.GradeStructure',
        on_delete=models.PROTECT,
        related_name='fee_structures'
    )
    curriculum = models.ForeignKey(
        'student_settings.Curriculum',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='fee_structures'
    )
    
    currency = models.CharField(max_length=10, default='KES')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    
    is_active = models.BooleanField(default=True, help_text="Legacy field, prefer status='ACTIVE'")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-academic_year', 'grade', 'term']
        unique_together = ['academic_year', 'term', 'grade', 'curriculum']
        verbose_name = _('Fee Structure')
        verbose_name_plural = _('Fee Structures')

    def __str__(self):
        curr = f" - {self.curriculum}" if self.curriculum else ""
        return f"{self.grade} {self.term} ({self.academic_year}){curr} [{self.status}]"

    @property
    def total_amount(self):
        return sum(item.amount for item in self.items.all())

    def clone_from(self, source_structure, percentage_increase=0):
        """
        Clones items from a source structure to this one.
        percentage_increase: Floating point percentage (e.g. 10.0 for 10%).
        """
        if not source_structure:
            return
        
        factor = 1 + (Decimal(percentage_increase) / 100)
        
        for item in source_structure.items.all():
            new_amount = item.amount * factor
            
            FeeItem.objects.create(
                structure=self,
                name=item.name,
                amount=new_amount,
                account=item.account,
                is_optional=item.is_optional,
                is_mandatory=item.is_mandatory,
                frequency=item.frequency,
                priority=item.priority
            )
            
    def clean(self):
        # Additional validation if needed
        if self.status == 'ACTIVE':
            # Ensure no other active structure exists for this combination?
            # Managed by unique_together generally, but unique_together allows multiple if different IDs.
            # But unique_together enforces ONE per comb. So we are good.
            pass

class FeeItem(models.Model):
    FREQUENCY_CHOICES = (
        ('ONE_TIME', 'One Time'),
        ('RECURRING', 'Recurring (Termly)'),
        ('YEARLY', 'Yearly'),
    )

    structure = models.ForeignKey(
        FeeStructure, 
        on_delete=models.CASCADE, 
        related_name='items'
    )
    name = models.CharField(max_length=100, help_text="e.g. Tuition Fee, Activity Fee")
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    # Classification
    is_mandatory = models.BooleanField(default=True)
    is_optional = models.BooleanField(default=False, help_text="If True, student can opt-out (e.g. Transport). overrides mandatory.")
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='RECURRING')
    priority = models.IntegerField(default=0, help_text="Order on invoice (lower first)")

    # Accounting Link (Metadata Only)
    account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        limit_choices_to={'is_student_related': True}, # We will validate Type in clean()
        related_name='fee_items',
        help_text="Projected Account for posting. MUST be Income or Liability."
    )
    
    class Meta:
        ordering = ['priority', 'name']

    def __str__(self):
        return f"{self.name} - {self.amount}"

    def clean(self):
        # Validate Account Type
        if self.account:
            if not self.account.is_student_related:
                 # Ideally caught by limit_choices_to, but strict check here
                 raise ValidationError({'account': _("Selected account must be marked as 'Student Related'.")})
            
            if self.account.type not in ['INCOME', 'LIABILITY']:
                raise ValidationError({'account': _("Fee Item account must be either INCOME (Revenue) or LIABILITY (e.g. Caution Money).")})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

class FeeInvoice(models.Model):
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('SENT', 'Sent'),
        ('PAID', 'Paid'),
        ('PARTIALLY_PAID', 'Partially Paid'),
        ('OVERDUE', 'Overdue'),
        ('VOID', 'Void'),
    )

    student_enrollment = models.ForeignKey(
        'academics.StudentSessionEnrollment',
        on_delete=models.PROTECT,
        related_name='invoices'
    )
    
    # Denormalized fields for faster queries / history preservation
    student = models.ForeignKey('accounts.Student', on_delete=models.PROTECT, related_name='fee_invoices')
    class_session = models.ForeignKey('academics.ClassSession', on_delete=models.PROTECT)
    term = models.ForeignKey('student_settings.Term', on_delete=models.PROTECT)
    academic_year = models.ForeignKey('student_settings.AcademicYear', on_delete=models.PROTECT)
    
    invoice_number = models.CharField(max_length=50, unique=True, editable=False)
    date_issued = models.DateField(default=models.functions.Now)
    due_date = models.DateField(null=True, blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-date_issued', '-invoice_number']
        unique_together = ['student_enrollment'] # One invoice per enrollment? Or allow multiple? 
        # Usually one main invoice per term per student. But maybe supplemental?
        # Let's enforce unique enrollment for now to prevent duplicates as requested.
        
    def __str__(self):
        return f"{self.invoice_number} - {self.student}"
        
    def save(self, *args, **kwargs):
        if not self.invoice_number:
            # Generate e.g. INV-2026-0001
            import uuid
            self.invoice_number = f"INV-{uuid.uuid4().hex[:8].upper()}"
            
        self.balance = self.total_amount - self.paid_amount
        if self.balance <= 0 and self.total_amount > 0:
            self.status = 'PAID'
        elif self.paid_amount > 0:
            self.status = 'PARTIALLY_PAID'
            
        super().save(*args, **kwargs)

class FeeInvoiceItem(models.Model):
    invoice = models.ForeignKey(FeeInvoice, on_delete=models.CASCADE, related_name='items')
    fee_item = models.ForeignKey(FeeItem, on_delete=models.PROTECT, related_name='invoiced_items')
    
    description = models.CharField(max_length=255) # Snapshot of name
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    
    is_mandatory = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['invoice', 'fee_item'] # Prevent duplicate items on same invoice

    def __str__(self):
        return f"{self.description} - {self.amount}"
