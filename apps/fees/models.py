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
    student = models.ForeignKey('student_management.Student', on_delete=models.PROTECT, related_name='fee_invoices')
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
    
    Supports both legacy FeeItem and new VoteHead-based templates:
    - fee_item: FK to legacy FeeItem (nullable for template-based invoices)
    - vote_head: FK to VoteHead (nullable for legacy invoices)
    - At least one must be set.
    """
    invoice = models.ForeignKey(FeeInvoice, on_delete=models.CASCADE, related_name='items')
    fee_item = models.ForeignKey(FeeItem, on_delete=models.PROTECT, null=True, blank=True, related_name='invoiced_items')
    vote_head = models.ForeignKey(
        'fees.VoteHead',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='invoiced_items',
        help_text="Set for template-based invoices. Null for legacy FeeItem invoices."
    )
    
    description = models.CharField(max_length=255)  # Snapshot of name at invoice time
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    
    # Snapshot of optional status at invoice time (is_optional=False means mandatory)
    is_optional = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        # Legacy constraint kept for backward compat; new invoices use vote_head
        constraints = [
            models.UniqueConstraint(
                fields=['invoice', 'fee_item'],
                condition=Q(fee_item__isnull=False),
                name='unique_legacy_fee_item_per_invoice'
            ),
            models.UniqueConstraint(
                fields=['invoice', 'vote_head'],
                condition=Q(vote_head__isnull=False),
                name='unique_vote_head_per_invoice'
            ),
        ]

    @property
    def effective_account(self):
        """Returns the accounting account for journal posting."""
        if self.vote_head:
            return self.vote_head.default_account
        if self.fee_item:
            return self.fee_item.account
        return None

    @property
    def is_mandatory(self):
        """Mandatory = not optional. Provided for backwards compatibility."""
        return not self.is_optional

    def __str__(self):
        return f"{self.description} - {self.amount}"


# ============================================================
# LAYER 1–3: FEE TEMPLATE ARCHITECTURE
# ============================================================
# Eliminates per-grade duplication of fee structures.
# VoteHead → FeeTemplate → TemplateLineItem
# ============================================================


class VoteHead(models.Model):
    """
    Master registry of fee line items at school level.
    Single source of truth for account mapping — no more per-structure duplication.
    
    Examples: Tuition Fee, Boarding Fee, Transport Fee, Lab Fee
    """
    FREQUENCY_CHOICES = (
        ('ONE_TIME', 'One Time'),
        ('RECURRING', 'Recurring (Termly)'),
        ('YEARLY', 'Yearly'),
    )

    name = models.CharField(max_length=100, unique=True, help_text="e.g. Tuition Fee, Boarding Fee")
    code = models.CharField(
        max_length=20, unique=True,
        help_text="Short code e.g. TUI, BRD, TRN"
    )
    default_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        limit_choices_to={'is_student_related': True},
        related_name='vote_heads',
        help_text="Default income/liability account. Can be overridden per template."
    )
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='RECURRING')
    is_optional = models.BooleanField(
        default=False,
        help_text="If True, item can be opted out (e.g. Transport, Lunch)."
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = _('Vote Head')
        verbose_name_plural = _('Vote Heads')

    def __str__(self):
        return f"{self.code} - {self.name}"

    def clean(self):
        if self.default_account:
            if not self.default_account.is_student_related:
                raise ValidationError({'default_account': _("Account must be marked as Student Related.")})
            if self.default_account.type not in ['INCOME', 'LIABILITY']:
                raise ValidationError({'default_account': _("Account must be Income or Liability type.")})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class GradeBand(models.Model):
    """
    Groups grades that share the same fee structure.
    e.g. "Lower Primary" (Grade 1-3), "Upper Primary" (Grade 4-6), "Secondary" (Form 1-4)
    
    Reduces O(grades × terms) to O(bands × terms) for fee configuration.
    """
    name = models.CharField(max_length=100, unique=True)
    grades = models.ManyToManyField(
        'student_settings.GradeStructure',
        related_name='fee_bands',
        help_text="Grades in this band share the same fee template."
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = _('Grade Band')
        verbose_name_plural = _('Grade Bands')

    def __str__(self):
        return self.name

    @property
    def grade_names(self):
        return list(self.grades.values_list('name', flat=True))


class FeeTemplate(models.Model):
    """
    Reusable fee configuration that applies to multiple grades via a GradeBand
    or directly to specific grades.
    
    Resolution priority:
      1. Template with direct grade match (via grades M2M)
      2. Template via grade_band
    
    One ACTIVE template per grade+term+year combination enforced on activation.
    """
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('ACTIVE', 'Active'),
        ('INACTIVE', 'Inactive'),
    )

    name = models.CharField(max_length=200)
    
    # Grade targeting: band OR direct grades (at least one required)
    grade_band = models.ForeignKey(
        GradeBand,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='fee_templates',
        help_text="Apply to all grades in this band."
    )
    cohort = models.ForeignKey(
        'student_settings.Intake',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='fee_templates',
        help_text="Link this fee template to a specific cohort intake for locked entry pricing"
    )
    grades = models.ManyToManyField(
        'student_settings.GradeStructure',
        blank=True,
        related_name='fee_templates',
        help_text="Direct grade assignment (overrides band for matching)."
    )
    
    curriculum = models.ForeignKey(
        'student_settings.Curriculum',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='fee_templates'
    )
    term = models.ForeignKey(
        'student_settings.Term',
        on_delete=models.PROTECT,
        related_name='fee_templates'
    )
    academic_year = models.ForeignKey(
        'student_settings.AcademicYear',
        on_delete=models.PROTECT,
        related_name='fee_templates'
    )
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    currency = models.CharField(max_length=10, default='KES')
    
    # Template inheritance for year rollover
    parent_template = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='child_templates',
        help_text="Source template this was cloned from."
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-academic_year', 'name']
        verbose_name = _('Fee Template')
        verbose_name_plural = _('Fee Templates')

    def __str__(self):
        return f"{self.name} ({self.term} {self.academic_year}) [{self.status}]"

    @property
    def total_amount(self):
        return self.line_items.aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')

    @property
    def mandatory_total(self):
        return self.line_items.filter(is_mandatory=True).aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')

    def get_covered_grades(self):
        """Returns all GradeStructure objects this template covers."""
        direct = set(self.grades.values_list('id', flat=True))
        band = set()
        if self.grade_band:
            band = set(self.grade_band.grades.values_list('id', flat=True))
        all_ids = direct | band
        from student_settings.models import GradeStructure
        return GradeStructure.objects.filter(id__in=all_ids)

    def clean(self):
        if self.status == 'ACTIVE':
            # Check for conflicts: another ACTIVE template covering the same grade+term+year
            covered = self.get_covered_grades()
            for grade in covered:
                conflicts = FeeTemplate.objects.filter(
                    status='ACTIVE',
                    term=self.term,
                    academic_year=self.academic_year,
                ).exclude(pk=self.pk)
                
                for other in conflicts:
                    other_grades = set(other.get_covered_grades().values_list('id', flat=True))
                    if grade.id in other_grades:
                        raise ValidationError(
                            f"Cannot activate: Template '{other.name}' already covers "
                            f"{grade.name} for {self.term} {self.academic_year}."
                        )
            
            # Must have at least one mandatory line item with amount > 0
            if not self.pk:
                return  # Skip on create (no line items yet)
            mandatory = self.line_items.filter(is_mandatory=True, amount__gt=0)
            if not mandatory.exists():
                raise ValidationError(
                    "Cannot activate: Template must have at least one mandatory line item with amount > 0."
                )
            
            # Must cover at least one grade
            if not covered.exists():
                raise ValidationError(
                    "Cannot activate: Template must cover at least one grade (via grades or grade_band)."
                )

    def save(self, *args, **kwargs):
        if self.status == 'ACTIVE' and self.pk:
            self.clean()
        super().save(*args, **kwargs)

    def clone_to(self, target_year, target_term, percentage_increase=0, user=None):
        """
        Clone this template to a new year/term with optional price increase.
        Returns the new FeeTemplate.
        """
        factor = 1 + (Decimal(str(percentage_increase)) / 100)
        
        new_template = FeeTemplate.objects.create(
            name=f"{self.name}",
            grade_band=self.grade_band,
            cohort=self.cohort,
            curriculum=self.curriculum,
            term=target_term,
            academic_year=target_year,
            status='DRAFT',
            currency=self.currency,
            parent_template=self,
        )
        
        # Copy direct grade assignments
        new_template.grades.set(self.grades.all())
        
        # Clone line items with price adjustment
        for line in self.line_items.all():
            TemplateLineItem.objects.create(
                template=new_template,
                vote_head=line.vote_head,
                amount=line.amount * factor,
                override_account=line.override_account,
                is_mandatory=line.is_mandatory,
                is_credit_hour=line.is_credit_hour,
                priority=line.priority,
            )
        
        return new_template


class TemplateLineItem(models.Model):
    """
    Amount per vote head within a fee template.
    The override_account allows template-specific account mapping
    while defaulting to the VoteHead's default_account.
    """
    APPLIES_TO_CHOICES = (
        ('ALL', 'All Students'),
        ('BOARDERS', 'Boarders Only'),
        ('DAY_SCHOLARS', 'Day Scholars Only'),
    )

    template = models.ForeignKey(
        FeeTemplate,
        on_delete=models.CASCADE,
        related_name='line_items'
    )
    vote_head = models.ForeignKey(
        VoteHead,
        on_delete=models.PROTECT,
        related_name='template_lines'
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    # Override account (if different from vote head default)
    override_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        limit_choices_to={'is_student_related': True},
        related_name='template_line_overrides',
        help_text="Override the vote head's default account for this template only."
    )
    
    is_mandatory = models.BooleanField(
        default=True,
        help_text="If False, this is an optional item students can opt out of."
    )
    is_credit_hour = models.BooleanField(
        default=False,
        help_text="If True, this line item fee is multiplied by the student's total course credits instead of being billed as a flat rate"
    )
    applies_to = models.CharField(
        max_length=20,
        choices=APPLIES_TO_CHOICES,
        default='ALL',
        help_text="Which students this line item applies to."
    )
    priority = models.IntegerField(default=0, help_text="Display order (lower first)")

    class Meta:
        ordering = ['priority', 'vote_head__name']
        unique_together = ['template', 'vote_head']
        verbose_name = _('Template Line Item')
        verbose_name_plural = _('Template Line Items')

    @property
    def effective_account(self):
        """Returns override_account if set, else vote_head.default_account."""
        return self.override_account or self.vote_head.default_account

    @property
    def is_optional(self):
        """Backward-compatible property."""
        return not self.is_mandatory

    def __str__(self):
        tag = "Mandatory" if self.is_mandatory else "Optional"
        return f"{self.vote_head.name} - {self.amount} ({tag})"


class StudentFeeProfile(models.Model):
    """
    Per-student fee customization. Tracks boarding status, transport usage,
    and any custom optional items the student has opted into.
    """
    student = models.OneToOneField(
        'student_management.Student',
        on_delete=models.CASCADE,
        related_name='fee_profile'
    )
    is_boarder = models.BooleanField(default=False, help_text="Student uses boarding facilities")
    uses_transport = models.BooleanField(default=False, help_text="Student uses school transport")
    
    # Custom optional vote heads this student has opted into
    custom_items = models.ManyToManyField(
        VoteHead,
        blank=True,
        related_name='opted_in_students',
        help_text="Additional optional vote heads this student is enrolled in."
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Student Fee Profile')
        verbose_name_plural = _('Student Fee Profiles')

    def __str__(self):
        flags = []
        if self.is_boarder:
            flags.append("Boarder")
        if self.uses_transport:
            flags.append("Transport")
        return f"{self.student} ({', '.join(flags) or 'Day Scholar'})"
