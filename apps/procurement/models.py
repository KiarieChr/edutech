"""
Procurement Module

Full procurement cycle:
  Employee Requisition → Purchase Requisition → RFQ/Quotation → Purchase Order → GRN → Invoice → Payment

Includes:
- Internal purchase requisitions (from staff)
- Request for Quotation (RFQ) with public supplier links
- Supplier quotation responses
- Purchase orders with line items
- Supplier contracts with document upload
- 3-way matching support (PO ↔ GRN ↔ Invoice)
"""

from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
import uuid


# =============================================================================
# PURCHASE REQUISITION (Internal Request from Staff)
# =============================================================================

class PurchaseRequisition(models.Model):
    """Internal purchase request raised by an employee."""

    PRIORITY_CHOICES = (
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
        ('URGENT', 'Urgent'),
    )

    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('SUBMITTED', 'Submitted'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('CONVERTED', 'Converted to PO'),
        ('CANCELLED', 'Cancelled'),
    )

    requisition_number = models.CharField(max_length=30, unique=True, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='purchase_requisitions'
    )
    department = models.CharField(max_length=100, blank=True, null=True)
    date_needed = models.DateField(null=True, blank=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='MEDIUM')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')

    justification = models.TextField(blank=True, null=True, help_text="Reason for the purchase")
    suggested_supplier = models.ForeignKey(
        'payables.Supplier', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='suggested_requisitions',
        help_text="Optional preferred supplier"
    )
    budget_line = models.ForeignKey(
        'budgets.BudgetLine', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='requisitions'
    )

    # Approval
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='approved_requisitions'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, null=True)

    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Purchase Requisition'
        verbose_name_plural = 'Purchase Requisitions'

    def __str__(self):
        return f"{self.requisition_number} - {self.requested_by}"

    @property
    def total_estimated_cost(self):
        return sum(line.estimated_total for line in self.lines.all())

    def save(self, *args, **kwargs):
        if not self.requisition_number:
            year = timezone.now().year
            last = PurchaseRequisition.objects.filter(
                requisition_number__startswith=f"PR-{year}"
            ).order_by('-requisition_number').first()
            num = (int(last.requisition_number.split('-')[-1]) + 1) if last else 1
            self.requisition_number = f"PR-{year}-{num:04d}"
        super().save(*args, **kwargs)


class RequisitionLine(models.Model):
    """Line item on a purchase requisition."""
    requisition = models.ForeignKey(
        PurchaseRequisition, on_delete=models.CASCADE, related_name='lines'
    )
    item = models.ForeignKey(
        'inventory.InventoryItem', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='requisition_lines',
        help_text="Link to existing inventory item (optional)"
    )
    description = models.CharField(max_length=500)
    specification = models.TextField(blank=True, null=True)
    quantity = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('1.00'))
    unit_of_measure = models.CharField(max_length=30, default='Pcs')
    estimated_unit_cost = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0.00')
    )

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.description} x {self.quantity}"

    @property
    def estimated_total(self):
        return self.quantity * self.estimated_unit_cost


# =============================================================================
# REQUEST FOR QUOTATION (RFQ)
# =============================================================================

class RequestForQuotation(models.Model):
    """RFQ sent to one or more suppliers. Can originate from a requisition."""

    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('SENT', 'Sent to Suppliers'),
        ('CLOSED', 'Closed'),
        ('AWARDED', 'Awarded'),
        ('CANCELLED', 'Cancelled'),
    )

    rfq_number = models.CharField(max_length=30, unique=True, blank=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    requisition = models.ForeignKey(
        PurchaseRequisition, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='rfqs',
        help_text="Originating purchase requisition"
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    deadline = models.DateTimeField(
        null=True, blank=True,
        help_text="Deadline for suppliers to submit quotations"
    )
    terms_and_conditions = models.TextField(blank=True, null=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_rfqs'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Request for Quotation'
        verbose_name_plural = 'Requests for Quotation'

    def __str__(self):
        return f"{self.rfq_number} - {self.title}"

    @property
    def is_past_deadline(self):
        if self.deadline:
            return timezone.now() > self.deadline
        return False

    def save(self, *args, **kwargs):
        if not self.rfq_number:
            year = timezone.now().year
            last = RequestForQuotation.objects.filter(
                rfq_number__startswith=f"RFQ-{year}"
            ).order_by('-rfq_number').first()
            num = (int(last.rfq_number.split('-')[-1]) + 1) if last else 1
            self.rfq_number = f"RFQ-{year}-{num:04d}"
        super().save(*args, **kwargs)


class RFQLine(models.Model):
    """Items requested in the RFQ."""
    rfq = models.ForeignKey(
        RequestForQuotation, on_delete=models.CASCADE, related_name='lines'
    )
    item = models.ForeignKey(
        'inventory.InventoryItem', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='rfq_lines'
    )
    description = models.CharField(max_length=500)
    specification = models.TextField(blank=True, null=True)
    quantity = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('1.00'))
    unit_of_measure = models.CharField(max_length=30, default='Pcs')

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.description} x {self.quantity}"


class RFQSupplierInvitation(models.Model):
    """
    Links a supplier to an RFQ. Contains a unique token for
    the public quotation submission link.
    """
    rfq = models.ForeignKey(
        RequestForQuotation, on_delete=models.CASCADE, related_name='invitations'
    )
    supplier = models.ForeignKey(
        'payables.Supplier', on_delete=models.CASCADE, related_name='rfq_invitations'
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    invited_at = models.DateTimeField(auto_now_add=True)
    viewed_at = models.DateTimeField(null=True, blank=True)
    email_sent = models.BooleanField(default=False)

    class Meta:
        unique_together = ('rfq', 'supplier')
        verbose_name = 'RFQ Supplier Invitation'

    def __str__(self):
        return f"{self.rfq.rfq_number} → {self.supplier.name}"

    @property
    def public_url(self):
        """Returns the relative public URL for supplier to submit quotation."""
        return f"/api/procurement/quote/{self.token}/"


# =============================================================================
# SUPPLIER QUOTATION RESPONSE
# =============================================================================

class SupplierQuotation(models.Model):
    """A supplier's response/bid to an RFQ."""

    STATUS_CHOICES = (
        ('SUBMITTED', 'Submitted'),
        ('UNDER_REVIEW', 'Under Review'),
        ('SELECTED', 'Selected / Awarded'),
        ('REJECTED', 'Rejected'),
    )

    invitation = models.OneToOneField(
        RFQSupplierInvitation, on_delete=models.CASCADE,
        related_name='quotation'
    )
    quotation_reference = models.CharField(
        max_length=100, blank=True, null=True,
        help_text="Supplier's own quotation/reference number"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='SUBMITTED')

    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    currency = models.CharField(max_length=3, default='KES')
    validity_days = models.PositiveIntegerField(
        default=30, help_text="Number of days the quotation is valid"
    )
    delivery_period = models.CharField(
        max_length=100, blank=True, null=True,
        help_text="e.g. '14 days after PO'"
    )
    payment_terms = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    document = models.FileField(
        upload_to='procurement/quotations/%Y/%m/', blank=True, null=True,
        help_text="Uploaded quotation document (PDF)"
    )

    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='reviewed_quotations'
    )

    class Meta:
        ordering = ['total_amount']
        verbose_name = 'Supplier Quotation'

    def __str__(self):
        return f"Quote from {self.invitation.supplier.name} for {self.invitation.rfq.rfq_number}"

    @property
    def supplier(self):
        return self.invitation.supplier

    @property
    def rfq(self):
        return self.invitation.rfq


class SupplierQuotationLine(models.Model):
    """Line-level pricing from the supplier."""
    quotation = models.ForeignKey(
        SupplierQuotation, on_delete=models.CASCADE, related_name='lines'
    )
    rfq_line = models.ForeignKey(
        RFQLine, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='quotation_lines',
        help_text="Maps back to the RFQ line item"
    )
    description = models.CharField(max_length=500)
    quantity = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('1.00'))
    unit_price = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    vat_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('16.00'),
        help_text="VAT rate as percentage (0, 8, 16)"
    )

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.description} @ {self.unit_price}"

    @property
    def line_total(self):
        return self.quantity * self.unit_price

    @property
    def vat_amount(self):
        return self.line_total * (self.vat_rate / Decimal('100'))

    @property
    def total_with_vat(self):
        return self.line_total + self.vat_amount


# =============================================================================
# PURCHASE ORDER
# =============================================================================

class PurchaseOrder(models.Model):
    """Purchase order to a supplier."""

    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('PENDING_APPROVAL', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('SENT', 'Sent to Supplier'),
        ('PARTIALLY_RECEIVED', 'Partially Received'),
        ('FULLY_RECEIVED', 'Fully Received'),
        ('CLOSED', 'Closed'),
        ('CANCELLED', 'Cancelled'),
    )

    po_number = models.CharField(max_length=30, unique=True, blank=True)
    supplier = models.ForeignKey(
        'payables.Supplier', on_delete=models.PROTECT, related_name='purchase_orders'
    )

    # Traceability
    requisition = models.ForeignKey(
        PurchaseRequisition, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='purchase_orders'
    )
    rfq = models.ForeignKey(
        RequestForQuotation, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='purchase_orders'
    )
    quotation = models.ForeignKey(
        SupplierQuotation, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='purchase_orders'
    )
    contract = models.ForeignKey(
        'SupplierContract', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='purchase_orders',
        help_text="Contract/framework agreement this PO falls under"
    )

    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='DRAFT')
    order_date = models.DateField(default=timezone.now)
    expected_delivery_date = models.DateField(null=True, blank=True)
    delivery_address = models.TextField(blank=True, null=True)

    # Financial
    currency = models.CharField(max_length=3, default='KES')
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    vat_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    payment_terms = models.CharField(max_length=100, blank=True, null=True)

    # Budget
    budget_line = models.ForeignKey(
        'budgets.BudgetLine', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='purchase_orders'
    )

    # Approval
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='approved_pos'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)

    # Audit
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_pos'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Purchase Order'
        verbose_name_plural = 'Purchase Orders'

    def __str__(self):
        return f"{self.po_number} - {self.supplier.name}"

    def recalculate_totals(self):
        """Recalculate from line items."""
        lines = self.lines.all()
        self.subtotal = sum(l.line_total for l in lines)
        self.vat_amount = sum(l.vat_amount for l in lines)
        self.total_amount = self.subtotal + self.vat_amount
        self.save(update_fields=['subtotal', 'vat_amount', 'total_amount'])

    @property
    def receipt_percentage(self):
        """Percentage of order received based on line quantities."""
        lines = self.lines.all()
        if not lines:
            return 0
        total_ordered = sum(l.quantity for l in lines)
        total_received = sum(l.quantity_received for l in lines)
        if total_ordered == 0:
            return 0
        return round((total_received / total_ordered) * 100, 1)

    def save(self, *args, **kwargs):
        if not self.po_number:
            year = timezone.now().year
            last = PurchaseOrder.objects.filter(
                po_number__startswith=f"PO-{year}"
            ).order_by('-po_number').first()
            num = (int(last.po_number.split('-')[-1]) + 1) if last else 1
            self.po_number = f"PO-{year}-{num:04d}"
        super().save(*args, **kwargs)


class PurchaseOrderLine(models.Model):
    """Line item on a purchase order."""
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name='lines'
    )
    item = models.ForeignKey(
        'inventory.InventoryItem', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='po_lines'
    )
    description = models.CharField(max_length=500)
    quantity = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('1.00'))
    unit_of_measure = models.CharField(max_length=30, default='Pcs')
    unit_price = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    vat_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('16.00'),
        help_text="VAT rate percentage"
    )
    quantity_received = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0.00'),
        help_text="Updated when GRN is confirmed"
    )

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.description} x {self.quantity} @ {self.unit_price}"

    @property
    def line_total(self):
        return self.quantity * self.unit_price

    @property
    def vat_amount(self):
        return self.line_total * (self.vat_rate / Decimal('100'))

    @property
    def total_with_vat(self):
        return self.line_total + self.vat_amount

    @property
    def is_fully_received(self):
        return self.quantity_received >= self.quantity

    @property
    def outstanding_quantity(self):
        return max(self.quantity - self.quantity_received, Decimal('0.00'))


# =============================================================================
# SUPPLIER CONTRACT
# =============================================================================

class SupplierContract(models.Model):
    """Contracts / framework agreements with suppliers."""

    CONTRACT_TYPE_CHOICES = (
        ('FIXED_PRICE', 'Fixed Price'),
        ('FRAMEWORK', 'Framework Agreement'),
        ('BLANKET', 'Blanket Order'),
        ('SERVICE', 'Service Contract'),
    )

    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('ACTIVE', 'Active'),
        ('EXPIRED', 'Expired'),
        ('TERMINATED', 'Terminated'),
        ('RENEWED', 'Renewed'),
    )

    contract_number = models.CharField(max_length=30, unique=True, blank=True)
    title = models.CharField(max_length=255)
    supplier = models.ForeignKey(
        'payables.Supplier', on_delete=models.PROTECT, related_name='contracts'
    )
    contract_type = models.CharField(max_length=20, choices=CONTRACT_TYPE_CHOICES, default='FIXED_PRICE')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')

    start_date = models.DateField()
    end_date = models.DateField()
    contract_value = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    currency = models.CharField(max_length=3, default='KES')

    terms_and_conditions = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    document = models.FileField(
        upload_to='procurement/contracts/%Y/%m/', blank=True, null=True,
        help_text="Signed contract document (PDF)"
    )

    renewal_reminder_days = models.PositiveIntegerField(
        default=30,
        help_text="Days before end_date to send renewal reminder"
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_contracts'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Supplier Contract'

    def __str__(self):
        return f"{self.contract_number} - {self.title}"

    @property
    def is_expired(self):
        return self.end_date < timezone.now().date()

    @property
    def days_remaining(self):
        delta = self.end_date - timezone.now().date()
        return max(delta.days, 0)

    @property
    def needs_renewal_reminder(self):
        return 0 < self.days_remaining <= self.renewal_reminder_days

    def save(self, *args, **kwargs):
        if not self.contract_number:
            year = timezone.now().year
            last = SupplierContract.objects.filter(
                contract_number__startswith=f"CON-{year}"
            ).order_by('-contract_number').first()
            num = (int(last.contract_number.split('-')[-1]) + 1) if last else 1
            self.contract_number = f"CON-{year}-{num:04d}"
        super().save(*args, **kwargs)


class ContractMilestone(models.Model):
    """Deliverables and payment milestones for a contract."""

    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('COMPLETED', 'Completed'),
        ('OVERDUE', 'Overdue'),
    )

    contract = models.ForeignKey(
        SupplierContract, on_delete=models.CASCADE, related_name='milestones'
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    due_date = models.DateField()
    amount = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0.00'),
        help_text="Payment amount due at this milestone"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['due_date']

    def __str__(self):
        return f"{self.contract.contract_number} - {self.title}"
