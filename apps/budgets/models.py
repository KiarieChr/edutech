from decimal import Decimal
from django.db import models
from django.conf import settings
from finance.models import Account

class BudgetStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    PENDING_APPROVAL = 'pending_approval', 'Pending Approval'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'

class BudgetAdjustmentStatus(models.TextChoices):
    NORMAL = 'normal', 'Normal'
    REDUCED = 'reduced', 'Reduced'
    PENDING_REVIEW = 'pending_review', 'Pending Review'

class CategoryRule(models.TextChoices):
    PROTECTED = 'protected', 'Protected'
    FLEXIBLE = 'flexible', 'Flexible'
    CONDITIONAL = 'conditional', 'Conditional'

class Budget(models.Model):
    name = models.CharField(max_length=255)
    fiscal_year = models.PositiveIntegerField(help_text="e.g. 2026")
    start_date = models.DateField()
    end_date = models.DateField()
    description = models.TextField(blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=BudgetStatus.choices,
        default=BudgetStatus.DRAFT,
        help_text="Status: draft, pending_approval, approved, rejected"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    campus = models.ForeignKey(
        'workforce.Campus',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='budgets',
        help_text="Optional campus link for campus-specific budgeting"
    )

    # Milestone 4: Automatic Budget Adjustment Engine
    adjustment_factor = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        default=Decimal('1.0000'),
        help_text="Multiplier applied to flexible budget lines (<= 1.0000)"
    )
    adjustment_triggered_at = models.DateTimeField(null=True, blank=True)
    adjustment_status = models.CharField(
        max_length=30,
        choices=BudgetAdjustmentStatus.choices,
        default=BudgetAdjustmentStatus.NORMAL,
        help_text="Adjustment state: normal, reduced, pending_review"
    )

    def __str__(self):
        campus_str = f" - {self.campus.name}" if self.campus else ""
        return f"{self.name} ({self.fiscal_year}){campus_str} - {self.status}"

class BudgetLine(models.Model):
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='budget_lines')
    amount = models.DecimalField(max_digits=15, decimal_places=2, help_text="Budgeted amount for the period")

    # Milestone 4: Controlled Expenditure Limits
    original_budget = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Original baseline approved budget (immutable)"
    )
    controlled_budget = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Live controlled budget after applying adjustment factor"
    )
    category_rule = models.CharField(
        max_length=20,
        choices=CategoryRule.choices,
        default=CategoryRule.FLEXIBLE,
        help_text="Adjustment rule: protected (1.0), flexible (R factor), conditional (0 if shortfall)"
    )

    class Meta:
        unique_together = ('budget', 'account')

    @property
    def effective_original_budget(self):
        return self.original_budget if self.original_budget is not None else self.amount

    @property
    def effective_controlled_budget(self):
        if self.controlled_budget is not None:
            return self.controlled_budget
        return self.original_budget if self.original_budget is not None else self.amount

    def save(self, *args, **kwargs):
        if self.original_budget is None:
            self.original_budget = self.amount
        if self.controlled_budget is None:
            self.controlled_budget = self.amount
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.budget.name} - {self.account.code}: {self.effective_controlled_budget} (orig: {self.effective_original_budget})"

class BudgetAdjustmentHistory(models.Model):
    """
    Audit log record for automatic budget adjustments triggered by actual income collection shortfalls.
    """
    budget = models.ForeignKey(
        Budget,
        on_delete=models.CASCADE,
        related_name='adjustment_history'
    )
    previous_factor = models.DecimalField(max_digits=6, decimal_places=4)
    new_factor = models.DecimalField(max_digits=6, decimal_places=4)
    trigger_reason = models.CharField(max_length=255, default="Income shortfall detected")
    projected_income = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    actual_income = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    total_budget_before = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    total_budget_after = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    total_reduction = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    line_snapshot = models.JSONField(default=list, blank=True, help_text="Snapshot of adjustments per line item")
    calculated_at = models.DateTimeField(auto_now_add=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_budget_adjustments'
    )

    class Meta:
        ordering = ['-calculated_at']
        verbose_name = "Budget Adjustment History"
        verbose_name_plural = "Budget Adjustment Histories"

    def __str__(self):
        return f"Budget #{self.budget_id} adjustment: {self.previous_factor} -> {self.new_factor} at {self.calculated_at}"



class ProjectionMethod(models.TextChoices):
    BILLING_BASED = 'billing_based', 'Billing-Based'
    EVEN_DISTRIBUTION = 'even_distribution', 'Even Distribution'


class AdjustmentStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    PENDING_APPROVAL = 'pending_approval', 'Pending Approval'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'


class IncomeProjectionAdjustment(models.Model):
    """
    Financial audit record for manual adjustments made to system-generated income projections.
    Preserves historical system projections, recording adjustment amount, justification reason,
    user, timestamp, and authorization workflow status.
    """
    budget = models.ForeignKey(
        Budget,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='income_adjustments'
    )
    fiscal_year = models.PositiveIntegerField(help_text="e.g. 2026")
    period_type = models.CharField(
        max_length=20,
        help_text="monthly, termly, quarterly, custom, annual"
    )
    period_key = models.CharField(
        max_length=50,
        help_text="e.g. '2026-05', 'term-1', 'Q1', 'custom-2026-01-01_2026-12-31'"
    )
    period_label = models.CharField(
        max_length=100,
        help_text="Human-readable label, e.g. 'Term 1 2026'"
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    projection_method = models.CharField(
        max_length=30,
        choices=ProjectionMethod.choices,
        default=ProjectionMethod.BILLING_BASED
    )

    # Immutable system calculation vs approved adjusted amounts
    system_projection = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Original system-calculated projection (never overwritten)"
    )
    adjustment_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Manual adjustment increment/decrement (+/-)"
    )
    final_projection = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Final approved projection: system_projection + adjustment_amount"
    )

    reason = models.TextField(help_text="Audit explanation and justification for adjustment")
    status = models.CharField(
        max_length=20,
        choices=AdjustmentStatus.choices,
        default=AdjustmentStatus.APPROVED,
        help_text="Workflow status: draft, pending_approval, approved, rejected"
    )

    adjusted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='projection_adjustments'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = "Income Projection Adjustment"
        verbose_name_plural = "Income Projection Adjustments"

    def save(self, *args, **kwargs):
        self.final_projection = (self.system_projection or Decimal('0.00')) + (self.adjustment_amount or Decimal('0.00'))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.period_label} ({self.fiscal_year}): {self.system_projection} -> {self.final_projection} [{self.status}]"


class BudgetAuditAction(models.TextChoices):
    CREATED = 'created', 'Created'
    SUBMITTED = 'submitted', 'Submitted for Approval'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'
    ADJUSTED = 'adjusted', 'Adjusted'
    OVERRIDDEN = 'overridden', 'Manager Override'
    VIREMENT = 'virement', 'Virement Transfer'


class BudgetAuditLog(models.Model):
    """
    Append-only audit trail logging all lifecycle and governance events on budgets.
    Tracks state transitions, authorizations, user attribution, and before/after payloads.
    """
    budget = models.ForeignKey(
        Budget,
        on_delete=models.CASCADE,
        related_name='audit_logs',
        null=True,
        blank=True
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='budget_audit_logs'
    )
    action = models.CharField(
        max_length=50,
        choices=BudgetAuditAction.choices,
        help_text="Lifecycle action: created, submitted, approved, rejected, adjusted, overridden, virement"
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    previous_state = models.CharField(max_length=100, blank=True, null=True)
    new_state = models.CharField(max_length=100, blank=True, null=True)
    details = models.JSONField(default=dict, blank=True, help_text="Audit details and line snapshots")
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Budget Audit Log"
        verbose_name_plural = "Budget Audit Logs"

    def __str__(self):
        user_str = self.user.username if self.user else "System"
        return f"{self.action} on Budget #{self.budget_id} by {user_str} at {self.timestamp}"


