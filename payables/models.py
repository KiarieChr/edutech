"""
Accounts Payable and Payment Vouchers Module

Compliant with:
- IPSAS 1 (Financial Statement Presentation)
- IPSAS 24 (Budget reporting)
- IPSAS 17 (PPE linkage from procurement)
- IFRS 15 (Revenue recognition)
- IAS 37 (Provisions and accrued liabilities)

Kenyan school ERP specific:
- KRA PIN validation
- Kenya VAT rates (0%, 8%, 16%)
- Multi-currency with default KES
"""

from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils import timezone
from decimal import Decimal
import re


# =============================================================================
# SECTION 1: MASTER DATA MODELS
# =============================================================================

class Supplier(models.Model):
    """
    Supplier/Vendor master data.
    All suppliers must be created in master data before invoices can be entered.
    """
    PAYMENT_TERMS_CHOICES = (
        ('CASH', 'Cash on Delivery'),
        ('NET_7', 'Net 7 Days'),
        ('NET_14', 'Net 14 Days'),
        ('NET_30', 'Net 30 Days'),
    )
    
    # KRA PIN validator: A000000000A (letter, 9 digits, letter)
    kra_pin_validator = RegexValidator(
        regex=r'^[A-Z]\d{9}[A-Z]$',
        message='KRA PIN must be in format: A000000000A (letter, 9 digits, letter)'
    )
    
    name = models.CharField(max_length=255)
    kra_pin = models.CharField(
        max_length=11, 
        unique=True, 
        blank=True,
        null=True,
        validators=[kra_pin_validator],
        help_text="KRA PIN in format: A000000000A (optional)"
    )
    vat_registered = models.BooleanField(default=False)
    
    # Contact Information
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    contact_person = models.CharField(max_length=100, blank=True, null=True)
    
    # Banking Details
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    bank_branch = models.CharField(max_length=100, blank=True, null=True)
    account_number = models.CharField(max_length=50, blank=True, null=True)
    bank_code = models.CharField(max_length=20, blank=True, null=True, help_text="Swift/Bank Code")
    
    # Payment Terms
    payment_terms = models.CharField(
        max_length=20, 
        choices=PAYMENT_TERMS_CHOICES, 
        default='NET_30'
    )
    
    # AP Account - optional, uses default from FinanceSettings if not specified
    ap_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='suppliers',
        limit_choices_to={'type': 'LIABILITY'},
        null=True,
        blank=True,
        help_text="Accounts Payable account (uses default from settings if blank)"
    )
    
    # Auto-generated supplier code
    code = models.CharField(max_length=20, unique=True, blank=True, editable=False)
    
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.PROTECT, 
        null=True,
        related_name='created_suppliers'
    )

    class Meta:
        ordering = ['name']
        verbose_name = 'Supplier'
        verbose_name_plural = 'Suppliers'
        db_table = 'supplier'

    def __str__(self):
        return f"{self.code} - {self.name}"
    
    def save(self, *args, **kwargs):
        if not self.code:
            # Generate supplier code: SUP001, SUP002, etc.
            last = Supplier.objects.order_by('-id').first()
            next_num = (last.id + 1) if last else 1
            self.code = f"SUP{next_num:04d}"
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        # Validate AP account type
        if self.ap_account and self.ap_account.type != 'LIABILITY':
            raise ValidationError({
                'ap_account': 'AP Account must be a LIABILITY type account.'
            })
        
        # Validate KRA PIN format
        if self.kra_pin:
            if not re.match(r'^[A-Z]\d{9}[A-Z]$', self.kra_pin):
                raise ValidationError({
                    'kra_pin': 'KRA PIN must be in format: A000000000A'
                })


class ApprovalThreshold(models.Model):
    """
    Defines approval chains based on voucher amounts.
    """
    VOUCHER_TYPE_CHOICES = (
        ('AP', 'Accounts Payable'),
        ('GENERAL', 'General Payment'),
        ('IMPREST', 'Imprest/Cash Advance'),
        ('REFUND', 'Refund'),
        ('ALL', 'All Voucher Types'),
    )
    
    name = models.CharField(max_length=100, help_text="e.g. 'Bursar Only', 'Principal Required'")
    min_amount = models.DecimalField(max_digits=15, decimal_places=2)
    max_amount = models.DecimalField(max_digits=15, decimal_places=2)
    
    # List of role names in approval order
    required_roles = models.JSONField(
        default=list,
        help_text="List of role names required to approve, in order. e.g. ['BURSAR', 'PRINCIPAL']"
    )
    
    # Which voucher types this threshold applies to
    voucher_types = models.JSONField(
        default=list,
        help_text="List of voucher types: AP, GENERAL, IMPREST, REFUND, or ALL"
    )
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['min_amount']
        verbose_name = 'Approval Threshold'
        verbose_name_plural = 'Approval Thresholds'

    def __str__(self):
        return f"{self.name} ({self.min_amount:,.0f} - {self.max_amount:,.0f})"

    def clean(self):
        super().clean()
        if self.min_amount >= self.max_amount:
            raise ValidationError('min_amount must be less than max_amount')

    @classmethod
    def get_threshold_for_amount(cls, amount, voucher_type):
        """
        Returns the applicable ApprovalThreshold for a given amount and voucher type.
        """
        return cls.objects.filter(
            is_active=True,
            min_amount__lte=amount,
            max_amount__gte=amount
        ).filter(
            models.Q(voucher_types__contains=[voucher_type]) |
            models.Q(voucher_types__contains=['ALL'])
        ).first()


# =============================================================================
# SECTION 2: SUPPLIER INVOICE MODELS
# =============================================================================

class SupplierInvoice(models.Model):
    """
    Supplier invoice for accounts payable tracking.
    Supports both manual entry and procurement-linked invoices.
    """
    SOURCE_CHOICES = (
        ('MANUAL', 'Manual Entry'),
        ('PROCUREMENT', 'From Procurement'),
    )
    
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('APPROVED', 'Approved'),
        ('POSTED', 'Posted'),
        ('PAID', 'Paid'),
        ('VOID', 'Void'),
    )
    
    VAT_RATE_CHOICES = (
        (Decimal('0.00'), '0% (Zero Rated)'),
        (Decimal('8.00'), '8% (Reduced Rate)'),
        (Decimal('16.00'), '16% (Standard Rate)'),
    )
    
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name='invoices'
    )
    
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='MANUAL')
    
    # Reference to procurement PO (optional - for linking when source=PROCUREMENT)
    purchase_order_ref = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Purchase Order reference when source=PROCUREMENT"
    )
    purchase_order = models.ForeignKey(
        'procurement.PurchaseOrder', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='invoices',
        help_text="Link to purchase order for 3-way matching"
    )
    
    # Supplier's own invoice details
    invoice_number = models.CharField(max_length=50, help_text="Supplier's invoice number")
    invoice_date = models.DateField()
    due_date = models.DateField()
    
    # Currency
    currency = models.CharField(max_length=10, default='KES')
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal('1.0000'))
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    
    # Computed fields (updated by save method)
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    vat_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    
    notes = models.TextField(blank=True, null=True)
    
    # Attachment for scanned invoice/supporting docs
    attachment = models.FileField(
        upload_to='supplier_invoices/%Y/%m/',
        null=True,
        blank=True,
        help_text="Scanned invoice or supporting document"
    )
    
    # Journal entry link (set when posted)
    journal_entry = models.OneToOneField(
        'journals.JournalEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='supplier_invoice'
    )
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        related_name='created_supplier_invoices'
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='approved_supplier_invoices'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='posted_supplier_invoices'
    )
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-invoice_date', '-created_at']
        unique_together = ['supplier', 'invoice_number']
        verbose_name = 'Supplier Invoice'
        verbose_name_plural = 'Supplier Invoices'
        db_table = 'supplier_invoices'

    def __str__(self):
        return f"{self.supplier.name} - {self.invoice_number} ({self.total_amount:,.2f})"

    def clean(self):
        super().clean()
        # Validate source/PO relationship
        if self.source == 'PROCUREMENT' and not self.purchase_order_ref:
            raise ValidationError({
                'purchase_order_ref': 'Purchase Order reference is required when source is PROCUREMENT'
            })
        if self.source == 'MANUAL' and self.purchase_order_ref:
            raise ValidationError({
                'source': 'Source must be PROCUREMENT when Purchase Order is linked'
            })
        
        # Cannot edit posted invoices
        if self.pk:
            original = SupplierInvoice.objects.filter(pk=self.pk).first()
            if original and original.status in ['POSTED', 'PAID']:
                if (self.subtotal != original.subtotal or 
                    self.total_amount != original.total_amount):
                    raise ValidationError('Cannot modify amounts on posted/paid invoices')

    def update_totals(self):
        """Recalculates totals from line items."""
        lines = self.lines.all()
        self.subtotal = sum(line.amount for line in lines)
        self.vat_amount = sum(line.vat_amount for line in lines)
        self.total_amount = self.subtotal + self.vat_amount
        self.balance = self.total_amount
        
    def save(self, *args, **kwargs):
        if self.pk:  # Only update totals if saved (has lines)
            self.update_totals()
        super().save(*args, **kwargs)


class SupplierInvoiceLine(models.Model):
    """
    Line items for supplier invoices.
    Each line posts to a specific GL account.
    """
    VAT_RATE_CHOICES = (
        (Decimal('0.00'), '0%'),
        (Decimal('8.00'), '8%'),
        (Decimal('16.00'), '16%'),
    )
    
    invoice = models.ForeignKey(
        SupplierInvoice,
        on_delete=models.CASCADE,
        related_name='lines'
    )
    
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('1.00'))
    unit_price = models.DecimalField(max_digits=15, decimal_places=2)
    
    # Computed amount
    amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    
    # GL Account for this expense/liability/asset
    gl_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='supplier_invoice_lines',
        limit_choices_to={'type__in': ['EXPENSE', 'LIABILITY', 'ASSET']}
    )
    
    # VAT
    vat_rate = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        choices=VAT_RATE_CHOICES,
        default=Decimal('16.00')
    )
    vat_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    
    # Budget tracking (IPSAS 24)
    budget_line = models.ForeignKey(
        'budgets.BudgetLine',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='supplier_invoice_lines',
        help_text="Budget line for IPSAS 24 tracking"
    )

    class Meta:
        ordering = ['id']
        db_table = 'supplier_invoice_lines'


    def __str__(self):
        return f"{self.description} - {self.amount:,.2f}"

    def save(self, *args, **kwargs):
        # Compute amount
        self.amount = self.quantity * self.unit_price
        # Compute VAT
        self.vat_amount = self.amount * (self.vat_rate / Decimal('100'))
        super().save(*args, **kwargs)
        # Update invoice totals
        self.invoice.save()


# =============================================================================
# SECTION 3: PAYMENT VOUCHER MODELS
# =============================================================================

class PaymentVoucher(models.Model):
    """
    Universal payment voucher supporting multiple payment types.
    """
    VOUCHER_TYPE_CHOICES = (
        ('AP', 'Accounts Payable'),
        ('GENERAL', 'General Payment'),
        ('IMPREST', 'Imprest/Cash Advance'),
        ('REFUND', 'Refund'),
    )
    
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('PENDING_APPROVAL', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('PAID', 'Paid'),
        ('VOID', 'Void'),
    )
    
    PAYMENT_METHOD_CHOICES = (
        ('BANK_TRANSFER', 'Bank Transfer'),
        ('CHEQUE', 'Cheque'),
        ('CASH', 'Cash'),
        ('MOBILE_MONEY', 'Mobile Money (M-Pesa)'),
    )
    
    # Identification
    voucher_number = models.CharField(max_length=50, unique=True, editable=False)
    voucher_type = models.CharField(max_length=20, choices=VOUCHER_TYPE_CHOICES)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    
    # Amount and Payment Details
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.CharField(max_length=10, default='KES')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    payment_reference = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        help_text="M-Pesa code or EFT reference"
    )
    cheque_number = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Cheque number (for cheque payments)"
    )
    
    # Bank account being debited (school's bank)
    bank_account = models.ForeignKey(
        'finance.PaymentMethod',  # Using existing PaymentMethod which links to Account
        on_delete=models.PROTECT,
        related_name='payment_vouchers',
        limit_choices_to={'is_for_payment': True},
        help_text="School's bank account to debit",
        null=True,
        blank=True
    )
    
    payment_date = models.DateField()
    
    # Type-specific fields
    # AP type - link to supplier invoice
    supplier_invoice = models.ForeignKey(
        SupplierInvoice,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='payment_vouchers',
        help_text="Required for AP voucher type"
    )
    
    # GENERAL and REFUND types - payee name for non-suppliers
    payee_name = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="Required for GENERAL and REFUND types"
    )
    
    # IMPREST type - staff member receiving advance
    staff_member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='imprest_vouchers',
        help_text="Required for IMPREST type"
    )
    
    # REFUND type - link to original receipt
    refund_receipt = models.ForeignKey(
        'finance.Receipt',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='refund_vouchers',
        help_text="Original receipt being refunded (REFUND type)"
    )
    
    # Imprest account (used for IMPREST vouchers)
    imprest_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='imprest_vouchers',
        limit_choices_to={'sub_type': 'PREPAYMENTS'},
        help_text="Imprest account for tracking advances"
    )
    
    # REFUND type - reason for refund
    refund_reason = models.TextField(blank=True, null=True, help_text="Reason for refund")
    
    # Description for all voucher types
    description = models.TextField(blank=True, null=True, help_text="Payment description")
    
    notes = models.TextField(blank=True, null=True)
    
    # Journal entry link (set when paid)
    journal_entry = models.OneToOneField(
        'journals.JournalEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment_voucher'
    )
    
    # Approval chain tracking
    approval_chain = models.JSONField(
        default=list,
        blank=True,
        help_text="Required approval steps from ApprovalThreshold"
    )
    current_approval_step = models.IntegerField(default=0)
    
    # Audit
    prepared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='prepared_vouchers'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='paid_vouchers'
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Payment Voucher'
        verbose_name_plural = 'Payment Vouchers'
        db_table = 'payment_voucher'

    def __str__(self):
        return f"{self.voucher_number} - {self.get_voucher_type_display()} ({self.amount:,.2f})"

    def clean(self):
        super().clean()
        # Type-specific validation
        if self.voucher_type == 'AP':
            if not self.supplier_invoice:
                raise ValidationError({
                    'supplier_invoice': 'Supplier Invoice is required for AP voucher type'
                })
        elif self.voucher_type == 'GENERAL':
            if not self.payee_name:
                raise ValidationError({
                    'payee_name': 'Payee name is required for GENERAL voucher type'
                })
        elif self.voucher_type == 'IMPREST':
            if not self.staff_member:
                raise ValidationError({
                    'staff_member': 'Staff member is required for IMPREST voucher type'
                })
            if not self.imprest_account:
                raise ValidationError({
                    'imprest_account': 'Imprest account is required for IMPREST voucher type'
                })
        elif self.voucher_type == 'REFUND':
            if not self.payee_name and not self.refund_receipt:
                raise ValidationError({
                    'payee_name': 'Payee name or refund receipt is required for REFUND voucher type'
                })

    def save(self, *args, **kwargs):
        # Generate voucher number if not set
        if not self.voucher_number:
            self.voucher_number = self._generate_voucher_number()
        super().save(*args, **kwargs)

    def _generate_voucher_number(self):
        """Generate voucher number: {TYPE}-{YEAR}-{SEQUENCE}"""
        year = timezone.now().year
        prefix = self.voucher_type
        
        # Get last sequence for this type and year
        last_voucher = PaymentVoucher.objects.filter(
            voucher_number__startswith=f"{prefix}-{year}-"
        ).order_by('-voucher_number').first()
        
        if last_voucher:
            try:
                last_seq = int(last_voucher.voucher_number.split('-')[-1])
                new_seq = last_seq + 1
            except (ValueError, IndexError):
                new_seq = 1
        else:
            new_seq = 1
        
        return f"{prefix}-{year}-{new_seq:04d}"

    @property
    def is_fully_approved(self):
        """Check if all required approvals are complete."""
        if not self.approval_chain:
            return True
        return self.current_approval_step >= len(self.approval_chain)

    @property
    def next_approval_role(self):
        """Get the next required approval role."""
        if not self.approval_chain or self.is_fully_approved:
            return None
        return self.approval_chain[self.current_approval_step]


class PaymentVoucherLine(models.Model):
    """
    Line items for GENERAL and IMPREST vouchers.
    AP vouchers use the linked supplier invoice lines instead.
    """
    voucher = models.ForeignKey(
        PaymentVoucher,
        on_delete=models.CASCADE,
        related_name='lines'
    )
    
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    
    gl_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='payment_voucher_lines',
        limit_choices_to={'type__in': ['EXPENSE', 'LIABILITY', 'ASSET']}
    )
    
    # Budget tracking (IPSAS 24)
    budget_line = models.ForeignKey(
        'budgets.BudgetLine',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment_voucher_lines'
    )

    class Meta:
        ordering = ['id']
        db_table = 'voucher_details'

    def __str__(self):
        return f"{self.description} - {self.amount:,.2f}"


# =============================================================================
# SECTION 4: APPROVAL MODELS
# =============================================================================

class VoucherApproval(models.Model):
    """
    Tracks approval decisions for payment vouchers.
    """
    DECISION_CHOICES = (
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    )
    
    voucher = models.ForeignKey(
        PaymentVoucher,
        on_delete=models.CASCADE,
        related_name='approvals'
    )
    
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='voucher_approvals'
    )
    
    role = models.CharField(
        max_length=50, 
        help_text="Role the approver is acting as (e.g. BURSAR, PRINCIPAL)"
    )
    
    decision = models.CharField(max_length=20, choices=DECISION_CHOICES)
    comments = models.TextField(blank=True, null=True)
    approved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['approved_at']
        verbose_name = 'Voucher Approval'
        verbose_name_plural = 'Voucher Approvals'
        db_table = 'voucher_approval'

    def __str__(self):
        return f"{self.voucher.voucher_number} - {self.role} - {self.decision}"


# =============================================================================
# SECTION 5: IMPREST RETIREMENT MODELS
# =============================================================================

class ImprestRetirement(models.Model):
    """
    Retirement/accounting for imprest (cash advance) vouchers.
    """
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('SUBMITTED', 'Submitted'),
        ('APPROVED', 'Approved'),
        ('POSTED', 'Posted'),
    )
    
    voucher = models.OneToOneField(
        PaymentVoucher,
        on_delete=models.PROTECT,
        related_name='retirement',
        limit_choices_to={'voucher_type': 'IMPREST'}
    )
    
    retirement_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    # Cash returned (if any)
    surrender_amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=Decimal('0.00'),
        help_text="Cash returned from imprest"
    )
    
    notes = models.TextField(blank=True, null=True)
    
    # Journal entry link (set when posted)
    journal_entry = models.OneToOneField(
        'journals.JournalEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='imprest_retirement'
    )
    
    # Audit
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='submitted_retirements'
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='approved_retirements'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='posted_retirements'
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-retirement_date']
        verbose_name = 'Imprest Retirement'
        verbose_name_plural = 'Imprest Retirements'
        db_table = 'imprest_surrender'

    def __str__(self):
        return f"Retirement: {self.voucher.voucher_number}"

    def clean(self):
        super().clean()
        # Voucher must be IMPREST type
        if self.voucher.voucher_type != 'IMPREST':
            raise ValidationError('Can only retire IMPREST vouchers')
        
        # Voucher must be PAID before retirement
        if self.voucher.status != 'PAID':
            raise ValidationError('Imprest voucher must be PAID before retirement')

    @property
    def total_retired(self):
        """Sum of retirement line amounts."""
        return sum(line.amount for line in self.lines.all())

    @property
    def is_balanced(self):
        """Check if retirement + surrender equals original imprest amount."""
        return (self.total_retired + self.surrender_amount) == self.voucher.amount


class ImprestRetirementLine(models.Model):
    """
    Line items for imprest retirement - actual expenses incurred.
    """
    retirement = models.ForeignKey(
        ImprestRetirement,
        on_delete=models.CASCADE,
        related_name='lines'
    )
    
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    
    gl_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.PROTECT,
        related_name='imprest_retirement_lines',
        limit_choices_to={'type': 'EXPENSE'}
    )
    
    receipt_number = models.CharField(max_length=50, blank=True, null=True)
    receipt_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.description} - {self.amount:,.2f}"


# =============================================================================
# LEGACY MODELS (kept for backward compatibility)
# =============================================================================

class Vendor(models.Model):
    """
    Legacy vendor model - use Supplier instead.
    Kept for backward compatibility with existing data.
    """
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    tax_id = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Vendor (Legacy)'
        verbose_name_plural = 'Vendors (Legacy)'
        db_table = 'vendors'

    def __str__(self):
        return self.name


class Bill(models.Model):
    """
    Legacy bill model - use SupplierInvoice instead.
    Kept for backward compatibility.
    """
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('RECEIVED', 'Received'),
        ('PARTIALLY_PAID', 'Partially Paid'),
        ('PAID', 'Paid'),
        ('VOID', 'Void'),
    )
    
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT)
    bill_number = models.CharField(max_length=50, help_text="Vendor's invoice number")
    date_received = models.DateField()
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    journal_entry = models.OneToOneField(
        'journals.JournalEntry', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='legacy_bill'
    )
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True)

    class Meta:
        ordering = ['-date_received', 'bill_number']
        unique_together = ('vendor', 'bill_number')
        verbose_name = 'Bill (Legacy)'
        verbose_name_plural = 'Bills (Legacy)'
        db_table = 'vendor_bills'

    def __str__(self):
        return f"{self.vendor.name} - {self.bill_number}"


class BillLine(models.Model):
    """Legacy bill line - use SupplierInvoiceLine instead."""
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name='lines')
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    expense_account = models.ForeignKey(
        'finance.Account', 
        on_delete=models.PROTECT, 
        related_name='legacy_bill_lines',
        limit_choices_to=models.Q(type='EXPENSE') | models.Q(type='ASSET')
    )

    def __str__(self):
        return f"{self.description} - {self.amount}"

