"""
Inventory Management Models

Covers:
- Item categories with GL defaults
- Inventory items (consumable, capital asset, raw material)
- Stock movements (immutable audit trail)
- Goods Received Notes (inbound from suppliers)
- Supply Issue vouchers (outbound to departments)
- Stock takes (physical count reconciliation)
"""

from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from decimal import Decimal


# =============================================================================
# CATEGORY
# =============================================================================

class Category(models.Model):
    """Item category with optional GL account defaults."""
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True, null=True)
    parent = models.ForeignKey(
        'self', on_delete=models.CASCADE,
        null=True, blank=True, related_name='children'
    )
    gl_expense_account = models.ForeignKey(
        'finance.Account', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='inventory_categories',
        help_text="Default expense GL account for items in this category"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']

    def __str__(self):
        return self.name


# =============================================================================
# INVENTORY ITEM
# =============================================================================

class InventoryItem(models.Model):
    """Master inventory item register."""

    ITEM_TYPE_CHOICES = (
        ('CONSUMABLE', 'Consumable'),
        ('CAPITAL_ASSET', 'Capital Asset'),
        ('RAW_MATERIAL', 'Raw Material'),
    )

    STATUS_CHOICES = (
        ('ACTIVE', 'Active'),
        ('INACTIVE', 'Inactive'),
        ('EXPIRED', 'Expired'),
        ('DISPOSED', 'Disposed'),
    )

    UNIT_CHOICES = (
        ('Pcs', 'Pieces'),
        ('Box', 'Box'),
        ('Ream', 'Ream'),
        ('Bale', 'Bale'),
        ('Unit', 'Unit'),
        ('Kg', 'Kilograms'),
        ('Liters', 'Liters'),
        ('Meters', 'Meters'),
        ('Jerrican', 'Jerrican'),
        ('Pack', 'Pack'),
        ('Roll', 'Roll'),
        ('Set', 'Set'),
        ('Pair', 'Pair'),
        ('Carton', 'Carton'),
        ('Bottle', 'Bottle'),
        ('Dozen', 'Dozen'),
    )

    code = models.CharField(max_length=30, unique=True, help_text="Auto-generated if blank")
    name = models.CharField(max_length=255)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name='items'
    )
    item_type = models.CharField(max_length=20, choices=ITEM_TYPE_CHOICES, default='CONSUMABLE')
    unit_of_measure = models.CharField(max_length=20, choices=UNIT_CHOICES, default='Pcs')

    # Cost & Stock
    unit_cost = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    stock_quantity = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    min_level = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0.00'),
        help_text="Minimum stock level before reorder alert"
    )
    reorder_quantity = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0.00'),
        help_text="Suggested quantity to reorder"
    )

    # Storage
    location = models.CharField(max_length=100, blank=True, null=True, help_text="e.g. Store A-12")
    batch_number = models.CharField(max_length=50, blank=True, null=True)
    barcode = models.CharField(max_length=100, blank=True, null=True)
    expiry_date = models.DateField(null=True, blank=True)

    # Supplier
    supplier = models.ForeignKey(
        'payables.Supplier', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='inventory_items',
        help_text="Default/primary supplier"
    )

    # GL Accounts
    gl_asset_account = models.ForeignKey(
        'finance.Account', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='inventory_asset_items',
        limit_choices_to={'sub_type': 'INVENTORY'},
        help_text="Inventory asset account (BS)"
    )
    gl_expense_account = models.ForeignKey(
        'finance.Account', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='inventory_expense_items',
        limit_choices_to={'type': 'EXPENSE'},
        help_text="Expense account for consumption (P&L)"
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    notes = models.TextField(blank=True, null=True)

    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_inventory_items'
    )

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def stock_value(self):
        return self.stock_quantity * self.unit_cost

    @property
    def is_low_stock(self):
        return self.stock_quantity <= self.min_level

    @property
    def is_expired(self):
        if self.expiry_date:
            from django.utils import timezone
            return self.expiry_date < timezone.now().date()
        return False

    def save(self, *args, **kwargs):
        if not self.code:
            prefix = 'INV'
            last = InventoryItem.objects.order_by('-id').first()
            num = (last.id + 1) if last else 1
            self.code = f"{prefix}-{num:05d}"
        super().save(*args, **kwargs)


# =============================================================================
# STOCK MOVEMENT (Immutable Audit Trail)
# =============================================================================

class StockMovement(models.Model):
    """Immutable record of every stock change."""

    MOVEMENT_TYPE_CHOICES = (
        ('RECEIPT', 'Receipt (GRN)'),
        ('ISSUE', 'Issue (Supply Voucher)'),
        ('ADJUSTMENT_IN', 'Adjustment In'),
        ('ADJUSTMENT_OUT', 'Adjustment Out'),
        ('RETURN', 'Return'),
        ('WRITE_OFF', 'Write Off'),
        ('OPENING', 'Opening Balance'),
    )

    item = models.ForeignKey(
        InventoryItem, on_delete=models.PROTECT, related_name='movements'
    )
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPE_CHOICES)
    quantity = models.DecimalField(max_digits=15, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    total_cost = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    balance_after = models.DecimalField(max_digits=15, decimal_places=2)

    reference_number = models.CharField(max_length=50, blank=True, null=True)
    reason = models.TextField(blank=True, null=True)

    # GL link (set when movement is posted to finance)
    journal_entry = models.ForeignKey(
        'journals.JournalEntry', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='stock_movements'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='stock_movements'
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.item.code} {self.movement_type} {self.quantity} -> {self.balance_after}"

    def save(self, *args, **kwargs):
        self.total_cost = self.quantity * self.unit_cost
        super().save(*args, **kwargs)


# =============================================================================
# GOODS RECEIVED NOTE (GRN)
# =============================================================================

class GoodsReceivedNote(models.Model):
    """Inbound stock receipt from suppliers."""

    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('CONFIRMED', 'Confirmed'),
        ('POSTED', 'Posted to GL'),
    )

    grn_number = models.CharField(max_length=30, unique=True)
    supplier = models.ForeignKey(
        'payables.Supplier', on_delete=models.PROTECT, related_name='grns'
    )
    supplier_invoice = models.ForeignKey(
        'payables.SupplierInvoice', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='grns',
        help_text="Link to supplier invoice for 3-way matching"
    )
    purchase_order = models.ForeignKey(
        'procurement.PurchaseOrder', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='grns',
        help_text="Link to purchase order for 3-way matching"
    )
    received_date = models.DateField()
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='received_grns'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    notes = models.TextField(blank=True, null=True)

    # GL link
    journal_entry = models.ForeignKey(
        'journals.JournalEntry', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='grns'
    )

    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_grns'
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.grn_number} - {self.supplier.name}"

    def save(self, *args, **kwargs):
        if not self.grn_number:
            from django.utils import timezone
            year = timezone.now().year
            last = GoodsReceivedNote.objects.filter(
                grn_number__startswith=f"GRN-{year}"
            ).order_by('-grn_number').first()
            if last:
                num = int(last.grn_number.split('-')[-1]) + 1
            else:
                num = 1
            self.grn_number = f"GRN-{year}-{num:04d}"
        super().save(*args, **kwargs)


class GRNLine(models.Model):
    """Line items for a GRN."""
    grn = models.ForeignKey(
        GoodsReceivedNote, on_delete=models.CASCADE, related_name='lines'
    )
    item = models.ForeignKey(
        InventoryItem, on_delete=models.PROTECT, related_name='grn_lines'
    )
    quantity_ordered = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    quantity_received = models.DecimalField(max_digits=15, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=15, decimal_places=2)
    total_cost = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.item.name} x {self.quantity_received}"

    def save(self, *args, **kwargs):
        self.total_cost = self.quantity_received * self.unit_cost
        super().save(*args, **kwargs)


# =============================================================================
# SUPPLY ISSUE VOUCHER
# =============================================================================

class SupplyIssue(models.Model):
    """Issue voucher for distributing stock to departments."""

    STATUS_CHOICES = (
        ('PENDING', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('ISSUED', 'Issued'),
        ('REJECTED', 'Rejected'),
    )

    issue_number = models.CharField(max_length=30, unique=True)
    department = models.CharField(max_length=100)
    requested_by = models.CharField(max_length=100)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='approved_issues'
    )
    issue_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    total_value = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    notes = models.TextField(blank=True, null=True)

    # Budget tracking (IPSAS 24)
    budget_line = models.ForeignKey(
        'budgets.BudgetLine', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='supply_issues',
        help_text="Budget line for consumption tracking"
    )

    # GL link
    journal_entry = models.ForeignKey(
        'journals.JournalEntry', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='supply_issues'
    )

    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_issues'
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.issue_number} - {self.department}"

    def save(self, *args, **kwargs):
        if not self.issue_number:
            from django.utils import timezone
            year = timezone.now().year
            last = SupplyIssue.objects.filter(
                issue_number__startswith=f"ISS-{year}"
            ).order_by('-issue_number').first()
            if last:
                num = int(last.issue_number.split('-')[-1]) + 1
            else:
                num = 1
            self.issue_number = f"ISS-{year}-{num:04d}"
        super().save(*args, **kwargs)


class SupplyIssueItem(models.Model):
    """Line items for a supply issue voucher."""
    issue = models.ForeignKey(
        SupplyIssue, on_delete=models.CASCADE, related_name='items'
    )
    item = models.ForeignKey(
        InventoryItem, on_delete=models.PROTECT, related_name='issue_items'
    )
    quantity_requested = models.DecimalField(max_digits=15, decimal_places=2)
    quantity_issued = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    unit_cost = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.item.name} x {self.quantity_issued}"

    def save(self, *args, **kwargs):
        if not self.unit_cost:
            self.unit_cost = self.item.unit_cost
        self.total = self.quantity_issued * self.unit_cost
        super().save(*args, **kwargs)


# =============================================================================
# STOCK TAKE (Physical Count)
# =============================================================================

class StockTake(models.Model):
    """Physical stock count event."""

    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
    )

    reference = models.CharField(max_length=30, unique=True)
    date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    conducted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='stock_takes'
    )
    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.reference} ({self.date})"

    def save(self, *args, **kwargs):
        if not self.reference:
            from django.utils import timezone
            year = timezone.now().year
            last = StockTake.objects.filter(
                reference__startswith=f"ST-{year}"
            ).order_by('-reference').first()
            if last:
                num = int(last.reference.split('-')[-1]) + 1
            else:
                num = 1
            self.reference = f"ST-{year}-{num:04d}"
        super().save(*args, **kwargs)


class StockTakeLine(models.Model):
    """Individual item count within a stock take."""
    stock_take = models.ForeignKey(
        StockTake, on_delete=models.CASCADE, related_name='lines'
    )
    item = models.ForeignKey(
        InventoryItem, on_delete=models.PROTECT, related_name='stock_take_lines'
    )
    system_quantity = models.DecimalField(max_digits=15, decimal_places=2)
    physical_quantity = models.DecimalField(max_digits=15, decimal_places=2)
    variance = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    variance_reason = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['id']
        unique_together = ('stock_take', 'item')

    def __str__(self):
        return f"{self.item.name}: sys={self.system_quantity} phys={self.physical_quantity}"

    def save(self, *args, **kwargs):
        self.variance = self.physical_quantity - self.system_quantity
        super().save(*args, **kwargs)
