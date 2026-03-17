from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from decimal import Decimal

# Import Account to validate links, but we only store reference ID effectively via ForeignKey
from finance.models import Account


class FeeStructure(models.Model):
    """
    Fee structure per grade/term/year combination.
    
    MIGRATION NOTE: The `is_active` field has been removed. 
    Use `status='ACTIVE'` instead. Run migration to remove the column:
    python manage.py makemigrations fees --name remove_is_active_from_feestructure
    """
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('ACTIVE', 'Active'),
        ('INACTIVE', 'Inactive'),
    )

    academic_year = models.ForeignKey(
        'student_settings.AcademicYear', 
        on_delete=models.PROTECT,  # Protect historical data
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
        related_name='fee_structures',
        help_text="Required for CBC/8-4-4 differentiated billing"
    )
    
    currency = models.CharField(max_length=10, default='KES')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    # is_active field REMOVED - use status field only
    
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
    """
    Individual fee line item within a FeeStructure.
    
    MIGRATION NOTE: The `is_mandatory` field has been removed.
    Mandatory items are now identified as `is_optional=False`.
    Run migration: python manage.py makemigrations fees --name remove_is_mandatory_from_feeitem
    """
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
    
    # Classification: is_optional=False means mandatory, is_optional=True means student can opt-out
    is_optional = models.BooleanField(
        default=False, 
        help_text="If True, student can opt-out (e.g. Transport, Lunch). If False, item is mandatory."
    )
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='RECURRING')
    priority = models.IntegerField(default=0, help_text="Order on invoice (lower first)")

    # Accounting Link
    account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        limit_choices_to={'is_student_related': True},  # Validated in clean()
        related_name='fee_items',
        help_text="Account for journal posting. MUST be Income or Liability."
    )
    
    class Meta:
        ordering = ['priority', 'name']

    @property
    def is_mandatory(self):
        """Mandatory = not optional. Provided for backwards compatibility."""
        return not self.is_optional

    def __str__(self):
        status = "Optional" if self.is_optional else "Mandatory"
        return f"{self.name} - {self.amount} ({status})"

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
    """
    Fee invoice for a student enrollment in a specific term/session.
    
    Business Rules (Kenya School Billing):
    - One invoice per student per term (unless previous is VOID)
    - Invoice number format: INV-{YEAR}-T{TERM_NUMBER}-{SEQUENCE}
    - Sequence resets per year/term combination
    """
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
        related_name='invoices',
        help_text="The billing anchor - must exist before invoice creation"
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
        # Allow re-invoicing after void: exclude VOID invoices from uniqueness check
        constraints = [
            models.UniqueConstraint(
                fields=['student_enrollment'],
                condition=~Q(status='VOID'),
                name='unique_active_invoice_per_enrollment'
            )
        ]
        
    def __str__(self):
        return f"{self.invoice_number} - {self.student}"

    def _generate_invoice_number(self):
        """
        Generate invoice number in format: INV-{YEAR}-T{TERM_NUMBER}-{SEQUENCE}
        Example: INV-2026-T1-0042
        Sequence resets per year/term combination using database-level counting.
        """
        from django.db.models import Max
        
        year_name = self.academic_year.name if self.academic_year else '0000'
        # Extract year from academic year name (e.g., "2026" from "2026" or "2025/2026")
        year_str = ''.join(filter(str.isdigit, str(year_name)))[:4] or '0000'
        
        # Get term number (1, 2, or 3 for Kenyan schools)
        term_number = 1
        if self.term:
            term_name = str(self.term.name).lower()
            if '1' in term_name or 'one' in term_name or 'first' in term_name:
                term_number = 1
            elif '2' in term_name or 'two' in term_name or 'second' in term_name:
                term_number = 2
            elif '3' in term_name or 'three' in term_name or 'third' in term_name:
                term_number = 3
        
        # Get max sequence for this year/term (database-level counting)
        prefix = f"INV-{year_str}-T{term_number}-"
        max_invoice = FeeInvoice.objects.filter(
            invoice_number__startswith=prefix
        ).aggregate(max_num=Max('invoice_number'))
        
        if max_invoice['max_num']:
            # Extract sequence number from existing invoice
            try:
                last_seq = int(max_invoice['max_num'].split('-')[-1])
                next_seq = last_seq + 1
            except (ValueError, IndexError):
                next_seq = 1
        else:
            next_seq = 1
        
        return f"{prefix}{next_seq:04d}"

    def update_payment_status(self):
        """
        Recalculates balance and updates payment status based on paid_amount.
        
        IMPORTANT: Only call this method from payment processing code,
        not on every save. This prevents status overwrites during regular updates.
        """
        self.balance = self.total_amount - self.paid_amount
        
        if self.status == 'VOID':
            # Don't change status of voided invoices
            return
        
        if self.balance <= 0 and self.total_amount > 0:
            self.status = 'PAID'
        elif self.paid_amount > 0:
            self.status = 'PARTIALLY_PAID'
        # Note: SENT, DRAFT, OVERDUE statuses are managed elsewhere
        
        self.save(update_fields=['balance', 'status', 'updated_at'])
        
    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = self._generate_invoice_number()
        
        # Always recalculate balance (but don't auto-update status)
        self.balance = self.total_amount - self.paid_amount
            
        super().save(*args, **kwargs)

class FeeInvoiceItem(models.Model):
    """
    Individual line item on a fee invoice.
    Stores snapshot of fee item details at time of invoicing.
    """
    invoice = models.ForeignKey(FeeInvoice, on_delete=models.CASCADE, related_name='items')
    fee_item = models.ForeignKey(FeeItem, on_delete=models.PROTECT, related_name='invoiced_items')
    
    description = models.CharField(max_length=255)  # Snapshot of name at invoice time
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    
    # Snapshot of optional status at invoice time (is_optional=False means mandatory)
    is_optional = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['invoice', 'fee_item']  # Prevent duplicate items on same invoice

    @property
    def is_mandatory(self):
        """Mandatory = not optional. Provided for backwards compatibility."""
        return not self.is_optional

    def __str__(self):
        return f"{self.description} - {self.amount}"
