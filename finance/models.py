from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.conf import settings

class AccountType(models.TextChoices):
    # 1. ASSET
    ASSET = 'ASSET', _('Asset')
    # 2. LIABILITY
    LIABILITY = 'LIABILITY', _('Liability')
    # 3. EQUITY
    EQUITY = 'EQUITY', _('Equity')
    # 4. INCOME
    INCOME = 'INCOME', _('Income')
    # 5. EXPENSE
    EXPENSE = 'EXPENSE', _('Expense')

class AccountSubType(models.TextChoices):
    # ASSET Sub-types
    CASH = 'CASH', _('Cash')
    BANK = 'BANK', _('Bank')
    ACCOUNTS_RECEIVABLE = 'ACCOUNTS_RECEIVABLE', _('Accounts Receivable')
    PREPAYMENTS = 'PREPAYMENTS', _('Prepayments')
    INVENTORY = 'INVENTORY', _('Inventory')
    FIXED_ASSET = 'FIXED_ASSET', _('Fixed Asset')
    ACCUMULATED_DEPRECIATION = 'ACCUMULATED_DEPRECIATION', _('Accumulated Depreciation')

    # LIABILITY Sub-types
    ACCOUNTS_PAYABLE = 'ACCOUNTS_PAYABLE', _('Accounts Payable')
    ACCRUED_EXPENSES = 'ACCRUED_EXPENSES', _('Accrued Expenses')
    DEFERRED_REVENUE = 'DEFERRED_REVENUE', _('Deferred Revenue')
    TAX_PAYABLE = 'TAX_PAYABLE', _('Tax Payable')
    LONG_TERM_LIABILITY = 'LONG_TERM_LIABILITY', _('Long Term Liability')
    REFUNDABLE_DEPOSIT = 'REFUNDABLE_DEPOSIT', _('Refundable Deposit')

    # EQUITY Sub-types
    CAPITAL = 'CAPITAL', _('Capital')
    RETAINED_EARNINGS = 'RETAINED_EARNINGS', _('Retained Earnings')
    CURRENT_YEAR_SURPLUS = 'CURRENT_YEAR_SURPLUS', _('Current Year Surplus')

    # INCOME Sub-types
    SERVICE_INCOME = 'SERVICE_INCOME', _('Service Income')
    GRANTS_DONATIONS = 'GRANTS_DONATIONS', _('Grants & Donations')
    OTHER_INCOME = 'OTHER_INCOME', _('Other Income')

    # EXPENSE Sub-types
    SALARIES_WAGES = 'SALARIES_WAGES', _('Salaries & Wages')
    UTILITIES = 'UTILITIES', _('Utilities')
    TEACHING_EXPENSES = 'TEACHING_EXPENSES', _('Teaching Expenses')
    ADMIN_EXPENSES = 'ADMIN_EXPENSES', _('Admin Expenses')
    MAINTENANCE = 'MAINTENANCE', _('Maintenance')
    DEPRECIATION = 'DEPRECIATION', _('Depreciation')

class Account(models.Model):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=20, unique=True, help_text="Unique account code (e.g. 1000)")
    type = models.CharField(max_length=20, choices=AccountType.choices)
    sub_type = models.CharField(max_length=50, choices=AccountSubType.choices)
    
    description = models.TextField(blank=True, null=True)
    parent = models.ForeignKey(
        'self', 
        on_delete=models.RESTRICT, 
        null=True, 
        blank=True, 
        related_name='children',
        help_text="Parent account for hierarchy. Postings allowed only to leaf accounts."
    )
    
    is_active = models.BooleanField(default=True)
    is_student_related = models.BooleanField(default=False, help_text="Check if this account is used for student transactions (e.g. Fees, Caution Money)")
    available_in_payroll = models.BooleanField(default=False, help_text="Check if this account should be available for payroll account linkage")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['code']
        verbose_name = _('Account')
        verbose_name_plural = _('Accounts')

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def normal_balance(self):
        """
        Returns 'DEBIT' or 'CREDIT' based on account type.
        """
        if self.type in [AccountType.ASSET, AccountType.EXPENSE]:
            return 'DEBIT'
        return 'CREDIT'

    def clean(self):
        if self.parent:
            if self.parent.type != self.type:
                raise ValidationError(_("Child account must have the same Account Type as its parent."))

class Tax(models.Model):
    TAX_TYPE_CHOICES = (
        ('SALES', 'Sales Tax (Collected on Income)'),
        ('PURCHASE', 'Purchase Tax (Paid on Expenses)'),
        ('BOTH', 'Both'),
    )

    name = models.CharField(max_length=100)
    rate = models.DecimalField(max_digits=5, decimal_places=2, help_text="Percentage (e.g., 16.00 for 16%)")
    type = models.CharField(max_length=20, choices=TAX_TYPE_CHOICES, default='BOTH')
    
    # Liability Account where collected tax is recorded (e.g., VAT Payable)
    account = models.ForeignKey(
        Account, 
        on_delete=models.RESTRICT,
        limit_choices_to={'type': 'LIABILITY'},
        related_name='taxes',
        help_text="Liability account to post tax to (e.g. VAT Payable)"
    )
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.rate}%)"

class FiscalPeriod(models.Model):
    name = models.CharField(max_length=50, help_text="e.g. 2024, Q1 2025")
    start_date = models.DateField()
    end_date = models.DateField()
    is_closed = models.BooleanField(default=False, help_text="If closed, no further transactions can be posted.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.name} ({self.start_date} - {self.end_date})"

    def clean(self):
        if self.start_date >= self.end_date:
            raise ValidationError(_("Start date must be before end date."))

    @classmethod
    def auto_close_expired(cls):
        """
        Closes any fiscal periods whose end_date has passed.
        Returns count of closed periods.
        """
        from django.utils import timezone
        today = timezone.now().date()
        
        # Find open periods that have ended
        expired = cls.objects.filter(is_closed=False, end_date__lt=today)
        count = expired.count()
        
        if count > 0:
            expired.update(is_closed=True)
            
        return count

class PaymentMethod(models.Model):
    name = models.CharField(max_length=50, help_text="e.g. M-Pesa, Equity Bank", default="Payment Method")
    METHOD_CHOICES = (
        ('CASH', 'Cash'),
        ('BANK', 'Bank Transfer'),
        ('MPESA', 'M-Pesa / Mobile Money'),
        ('CHEQUE', 'Cheque'),
        ('OTHER', 'Other'),
    )
    account_number = models.CharField(max_length=50, blank=True, null=True, help_text="Bank Account Number, Paybill, or Till Number")
    account = models.ForeignKey(
        Account,
        on_delete=models.RESTRICT,
        related_name='payment_methods',
        limit_choices_to={'type__in': ['ASSET', 'LIABILITY']},
        help_text="The GL Account where transactions for this method are posted.",
        null=True, blank=True
    )
    is_active = models.BooleanField(default=True)
    
    # Capability Flags
    is_for_payment = models.BooleanField(default=True, verbose_name="Can Make Payments")
    is_for_receipt = models.BooleanField(default=True, verbose_name="Can Receive Payments")
    is_sponsorship_clearing = models.BooleanField(default=False, help_text="Used for clearing sponsorship allocations")
    is_application_fee = models.BooleanField(default=False, help_text="Used for application fee payments")

    def __str__(self):
        return self.name

class Cashbook(models.Model):
    name = models.CharField(max_length=100, help_text="e.g. Main Office Cash, Petty Cash")
    currency = models.CharField(max_length=10, default='KES')
    account = models.ForeignKey(
        Account,
        on_delete=models.RESTRICT,
        limit_choices_to={'type': 'ASSET'},
        help_text="The GL Asset Account linked to this cashbook."
    )
    low_cash_threshold = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, help_text="Alert when balance drops below this amount.")
    
    # Opening Balance
    opening_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    opening_balance_date = models.DateField(null=True, blank=True, help_text="Date of opening balance")
    is_opening_balance_posted = models.BooleanField(default=False, help_text="System flag: True if opening balance journal created")
    
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False, help_text="Default for Payment Vouchers")
    voucher_prefix = models.CharField(max_length=10, default='PV', help_text="Prefix for vouchers from this cashbook (e.g. PV-)")
    
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.is_default:
            # Unset default for others
            Cashbook.objects.filter(is_default=True).exclude(pk=self.pk).update(is_default=False)
        super(Cashbook, self).save(*args, **kwargs)

    def __str__(self):
        return self.name

class FinanceSettings(models.Model):
    """
    Singleton model to store global finance settings.
    """
    # General
    financial_year_start_month = models.IntegerField(default=1, choices=[(i, i) for i in range(1, 13)])
    financial_year_start_day = models.IntegerField(default=1)
    currency_code = models.CharField(max_length=10, default='KES')
    currency_symbol = models.CharField(max_length=5, default='KSh')
    tax_id_label = models.CharField(max_length=50, default='KRA PIN', help_text="Label for Tax ID field on invoices")
    vat_enabled = models.BooleanField(default=False)
    budgeting_enabled = models.BooleanField(default=True)
    
    # Document Settings
    receipt_prefix = models.CharField(max_length=10, default='RCPT')
    receipt_footer_message = models.TextField(blank=True, default="Thank you for your business.")
    receipt_show_balance = models.BooleanField(default=True)
    receipt_show_voteheads = models.BooleanField(default=True, help_text="Breakdown receipts per invoice vote head")

    # Receipt Format & Branding
    RECEIPT_FORMAT_CHOICES = [
        ('STANDARD_A4', 'Standard A4 (Full Page)'),
        ('COMPACT_A4', 'Compact A4 (Half Page)'),
        ('A5_RECEIPT', 'A5 Receipt'),
        ('THERMAL_80MM', 'POS Thermal 80mm'),
        ('THERMAL_58MM', 'POS Thermal 58mm'),
        ('DUPLICATE_BOOK', 'Duplicate Book Style'),
    ]
    RECEIPT_HEADER_STYLE_CHOICES = [
        ('LOGO_ONLY', 'Logo Only'),
        ('COAT_ONLY', 'Coat of Arms Only'),
        ('BOTH_SIDE', 'Logo Left, Coat of Arms Right'),
        ('COAT_LEFT_LOGO_RIGHT', 'Coat of Arms Left, Logo Right'),
        ('BOTH_CENTER', 'Both Centered (Stacked)'),
    ]
    receipt_format = models.CharField(max_length=20, choices=RECEIPT_FORMAT_CHOICES, default='THERMAL_80MM')
    receipt_logo = models.ImageField(upload_to='receipt_branding/', blank=True, null=True, help_text='School/Institution logo')
    receipt_coat_of_arms = models.ImageField(upload_to='receipt_branding/', blank=True, null=True, help_text='Coat of arms or government seal')
    receipt_header_style = models.CharField(max_length=25, choices=RECEIPT_HEADER_STYLE_CHOICES, default='LOGO_ONLY')
    receipt_show_qr_code = models.BooleanField(default=True, help_text='Show QR code for verification')
    receipt_show_student_photo = models.BooleanField(default=False)
    receipt_color_primary = models.CharField(max_length=7, default='#1a56db', help_text='Primary accent color (hex)')
    receipt_color_secondary = models.CharField(max_length=7, default='#374151', help_text='Secondary color for headers (hex)')
    receipt_watermark_enabled = models.BooleanField(default=False, help_text='Light coat of arms watermark on A4 receipts')
    receipt_copies = models.IntegerField(default=1, choices=[(1, 'Original Only'), (2, 'Original + Duplicate'), (3, 'Original + Duplicate + Office Copy')])
    receipt_paper_size = models.CharField(max_length=10, default='A4', choices=[('A4', 'A4'), ('LETTER', 'Letter'), ('A5', 'A5')])
    receipt_signature_enabled = models.BooleanField(default=True, help_text='Show signature line on receipt')
    receipt_institution_name = models.CharField(max_length=200, blank=True, default='', help_text='Institution name on receipt header')
    receipt_institution_address = models.CharField(max_length=300, blank=True, default='', help_text='Address line on receipt')
    receipt_institution_phone = models.CharField(max_length=50, blank=True, default='')
    receipt_institution_email = models.CharField(max_length=100, blank=True, default='')
    receipt_institution_motto = models.CharField(max_length=200, blank=True, default='')

    voucher_attachments_required = models.BooleanField(default=False)
    imprest_max_amount = models.DecimalField(max_digits=12, decimal_places=2, default=50000.00)
    imprest_surrender_days = models.IntegerField(default=7, help_text="Days to surrender imprest after issuance")

    # Auto-Billing Settings
    auto_billing_enabled = models.BooleanField(default=False)
    billing_mode = models.CharField(
        max_length=20,
        default='STRUCTURE',
        choices=[
            ('STRUCTURE', 'Per-Grade Fee Structure'),
            ('TEMPLATE', 'Grade-Band Fee Template'),
            ('AUTO', 'Auto (Template first, fallback to Structure)'),
        ],
        help_text='Which billing pipeline to use when auto-generating invoices',
    )
    billing_frequency = models.CharField(max_length=20, default='TERMLY', choices=[('YEARLY', 'Yearly'), ('TERMLY', 'Termly'), ('MONTHLY', 'Monthly')])
    default_billing_days = models.IntegerField(default=14, help_text="Default due days for auto-generated invoices")

    # Notifications
    low_cash_alert_enabled = models.BooleanField(default=True)
    overdue_invoice_alert_enabled = models.BooleanField(default=True)

    # Approvals
    voucher_approval_levels = models.IntegerField(default=1, help_text="Number of approvals required for vouchers")
    imprest_approval_levels = models.IntegerField(default=1, help_text="Number of approvals required for imprest")

    # Default Accounts for Automation
    default_receivable_account = models.ForeignKey(
        Account, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='settings_receivable',
        limit_choices_to={'sub_type': 'ACCOUNTS_RECEIVABLE'}
    )
    
    default_payable_account = models.ForeignKey(
        Account, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='settings_payable',
        limit_choices_to={'sub_type': 'ACCOUNTS_PAYABLE'}
    )
    
    default_bank_account = models.ForeignKey(
        Account, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='settings_bank',
        limit_choices_to={'sub_type': 'BANK'}
    )
    
    default_prepayment_account = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='settings_prepayment',
        limit_choices_to={'type': 'LIABILITY'},
        help_text='Account for student prepayments/unallocated credits'
    )
    
    # Sundry/Other Debtors - for non-student receivables (general customer invoices)
    default_sundry_debtors_account = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='settings_sundry_debtors',
        limit_choices_to={'type': 'ASSET'},
        help_text='Account for sundry/other debtors (non-student receivables)'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Finance Settings'
        verbose_name_plural = 'Finance Settings'

    def __str__(self):
        return "Finance Settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super(FinanceSettings, self).save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj


# Sponsor Type and Sponsorship Models

class SponsorType(models.Model):
    """
    Represents classifications of sponsors (e.g. Government Scholarships, NGO Scholarships, CDF Bursaries, County Bursaries)
    Linked to a liability clearing account for double-entry bookkeeping.
    """
    name = models.CharField(max_length=100, unique=True)
    clearing_account = models.ForeignKey(
        'Account',
        on_delete=models.RESTRICT,
        limit_choices_to={'type': 'LIABILITY'},
        related_name='sponsor_types',
        help_text='Liability account used in clearing sponsorship receipts during allocations'
    )
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Sponsor Type'
        verbose_name_plural = 'Sponsor Types'

    def __str__(self):
        return self.name


class Sponsorship(models.Model):
    """
    Represents specific sponsorship programs or sponsors (e.g., Equity Group Foundation Wings to Fly, Elimu Scholarship)
    """
    name = models.CharField(max_length=200, unique=True)
    sponsor_type = models.ForeignKey(
        SponsorType,
        on_delete=models.PROTECT,
        related_name='sponsorships',
        help_text='The category of this sponsor'
    )
    code = models.CharField(max_length=50, blank=True, null=True, help_text='Unique identifier or code for the sponsor')
    contact_person = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Sponsorship'
        verbose_name_plural = 'Sponsorships'

    def __str__(self):
        return f"{self.name} ({self.sponsor_type.name})"


# Receipt Models - Payment and Allocation Tracking

class Receipt(models.Model):
    """
    Receipt model for recording payments from students and other sources.
    Immutable after posting to maintain audit trail.
    """
    RECEIPT_TYPES = [
        ('STUDENT_FEE', 'Student Fee'),
        ('STUDENT_NON_FEE', 'Student Non-Fee'),
        ('SPONSOR', 'Sponsor'),
        ('GENERAL', 'General'),
    ]
    
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('ISSUED', 'Issued'),
        ('PRINTED', 'Printed'),
        ('REVERSED', 'Reversed'),
    ]
    
    # Identification
    receipt_number = models.CharField(max_length=50, unique=True, editable=False)
    receipt_type = models.CharField(max_length=20, choices=RECEIPT_TYPES, default='STUDENT_FEE')
    
    # Payer Information
    payer_name = models.CharField(
        max_length=200,
        help_text='Name of the person/entity making the payment'
    )
    
    # Links
    student = models.ForeignKey(
        'accounts.Student',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='receipts',
        help_text='Required for STUDENT_FEE and STUDENT_NON_FEE types'
    )
    sponsorship = models.ForeignKey(
        Sponsorship,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='receipts',
        help_text='Required for SPONSOR receipt type'
    )
    parent_receipt = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='child_allocations',
        help_text='Sponsor receipt that this student payment was allocated from'
    )
    payment_method = models.ForeignKey(
        'PaymentMethod',
        on_delete=models.PROTECT,
        related_name='receipts'
    )
    
    # Amounts
    amount_received = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Total amount received from payer'
    )
    amount_allocated = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text='Amount allocated to invoices (updated by allocation service)'
    )
    
    # Metadata
    received_date = models.DateField()
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='receipts_created'
    )
    reference = models.CharField(
        max_length=100,
        blank=True,
        help_text='External reference: Cheque #, M-Pesa code, Bank transfer ref, etc.'
    )
    notes = models.TextField(blank=True)
    
    # Status and tracking
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='DRAFT'
    )
    print_count = models.PositiveIntegerField(
        default=0,
        help_text='Number of times this receipt has been printed'
    )
    reversal_reason = models.TextField(
        null=True,
        blank=True,
        help_text='Reason for reversing this receipt (if status is REVERSED)'
    )
    
    # Student Fee Receipt - specific fields
    fee_category = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text='Fee category name (e.g., Tuition Fees, Boarding Fees)'
    )
    term = models.ForeignKey(
        'student_settings.Term',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        help_text='Academic term for student fee payments'
    )
    academic_year = models.ForeignKey(
        'student_settings.AcademicYear',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        help_text='Academic year for student fee payments'
    )
    
    # Student Non-Fee Receipt - specific fields
    non_fee_category = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text='Non-fee item category (e.g., School Uniform, Educational Trip)'
    )
    description = models.TextField(
        null=True,
        blank=True,
        help_text='Description for non-fee items or general receipts'
    )
    
    # Sponsor Receipt - specific fields
    sponsorship_type = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text='Type of sponsorship (e.g., Full Scholarship, Partial Scholarship)'
    )
    allocation_rule = models.TextField(
        null=True,
        blank=True,
        help_text='Rule for allocating sponsorship amount to students'
    )
    
    # General Receipt - specific fields
    income_account = models.ForeignKey(
        'Account',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='receipt_income',
        help_text='Income account for general receipts (e.g., Donations, Rental Income)'
    )
    
    # Status
    is_posted = models.BooleanField(
        default=False,
        help_text='True when allocations have been created. Receipt becomes immutable.'
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-received_date', '-receipt_number']
        verbose_name = _('Receipt')
        verbose_name_plural = _('Receipts')
        indexes = [
            models.Index(fields=['student', 'received_date']),
            models.Index(fields=['receipt_number']),
            models.Index(fields=['is_posted']),
        ]
    
    def __str__(self):
        return f"{self.receipt_number} - {self.get_receipt_type_display()} - {self.amount_received}"
    
    @property
    def unallocated_amount(self):
        """Calculate unallocated portion of receipt"""
        return self.amount_received - self.amount_allocated
    
    @property
    def is_fully_allocated(self):
        """Check if entire receipt has been allocated"""
        return self.amount_allocated >= self.amount_received
    
    def clean(self):
        # Validate student is provided for student receipt types
        if self.receipt_type in ['STUDENT_FEE', 'STUDENT_NON_FEE'] and not self.student:
            raise ValidationError({
                'student': _('Student is required for student fee/non-fee receipts.')
            })
            
        # Validate sponsorship is provided for sponsor receipts
        if self.receipt_type == 'SPONSOR' and not self.sponsorship:
            raise ValidationError({
                'sponsorship': _('Sponsorship is required for Sponsor receipts.')
            })
        
        # Prevent editing after posting
        if self.pk and self.is_posted:
            original = Receipt.objects.get(pk=self.pk)
            if original.is_posted:
                # Compare critical fields
                if (original.amount_received != self.amount_received or
                    original.student_id != self.student_id or
                    original.payment_method_id != self.payment_method_id):
                    raise ValidationError(_('Cannot modify a posted receipt.'))
    
    def save(self, *args, **kwargs):
        self.clean()
        
        # Sync sponsorship type text field if sponsorship is set
        if self.sponsorship:
            self.sponsorship_type = self.sponsorship.sponsor_type.name
            
        # Generate receipt number if new
        if not self.receipt_number:
            # Temporary inline generation until service layer is created
            import uuid
            from django.utils import timezone
            prefix = 'RCPT'  # Will be from FinanceSettings later
            year = timezone.now().year
            self.receipt_number = f"{prefix}-{year}-{uuid.uuid4().hex[:8].upper()}"
        
        super().save(*args, **kwargs)


class ReceiptAllocation(models.Model):
    """
    Tracks allocation of receipt amounts to specific invoice items.
    This is the single source of truth for payment breakdowns.
    """
    receipt = models.ForeignKey(
        Receipt,
        on_delete=models.PROTECT,
        related_name='allocations'
    )
    invoice = models.ForeignKey(
        'fees.FeeInvoice',
        on_delete=models.PROTECT,
        related_name='allocations'
    )
    invoice_item = models.ForeignKey(
        'fees.FeeInvoiceItem',
        on_delete=models.PROTECT,
        related_name='allocations'
    )
    
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Amount allocated to this invoice item'
    )
    
    allocated_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = [['receipt', 'invoice_item']]
        ordering = ['allocated_at', 'invoice__date_issued']
        verbose_name = _('Receipt Allocation')
        verbose_name_plural = _('Receipt Allocations')
        indexes = [
            models.Index(fields=['receipt', 'invoice']),
            models.Index(fields=['invoice_item']),
        ]
    
    def __str__(self):
        return f"{self.receipt.receipt_number} â†’ {self.invoice.invoice_number} ({self.amount})"
    
    def clean(self):
        # Validate amount is positive
        if self.amount <= 0:
            raise ValidationError({'amount': _('Allocation amount must be positive.')})
        
        # Validate invoice item belongs to invoice
        if self.invoice_item.invoice_id != self.invoice_id:
            raise ValidationError(_('Invoice item does not belong to the specified invoice.'))
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class StudentPrepayment(models.Model):
    """
    Tracks unallocated student credits (prepayments) that can be applied to future invoices.
    Created when receipt amount exceeds outstanding invoice balances.
    """
    student = models.ForeignKey(
        'accounts.Student',
        on_delete=models.PROTECT,
        related_name='prepayments'
    )
    receipt = models.ForeignKey(
        Receipt,
        on_delete=models.PROTECT,
        related_name='prepayment_records',
        help_text='Original receipt that created this prepayment'
    )
    
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Original prepayment amount'
    )
    balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Remaining prepayment balance (decreases as used)'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    is_fully_used = models.BooleanField(
        default=False,
        help_text='True when balance reaches zero'
    )
    
    class Meta:
        ordering = ['created_at']  # FIFO usage
        verbose_name = _('Student Prepayment')
        verbose_name_plural = _('Student Prepayments')
        indexes = [
            models.Index(fields=['student', 'is_fully_used']),
        ]
    
    def __str__(self):
        return f"{self.student} Prepayment: {self.balance} / {self.amount}"
    
    @property
    def amount_used(self):
        """Calculate how much of this prepayment has been used"""
        return self.amount - self.balance
    
    def clean(self):
        # Ensure balance never exceeds original amount
        if self.balance > self.amount:
            raise ValidationError({'balance': _('Balance cannot exceed original amount.')})
        
        # Ensure balance is not negative
        if self.balance < 0:
            raise ValidationError({'balance': _('Balance cannot be negative.')})
    
    def save(self, *args, **kwargs):
        self.clean()
        
        # Auto-set is_fully_used flag
        if self.balance == 0:
            self.is_fully_used = True
        
        super().save(*args, **kwargs)
