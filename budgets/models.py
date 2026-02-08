from django.db import models
from django.conf import settings
from finance.models import Account

class Budget(models.Model):
    name = models.CharField(max_length=255)
    fiscal_year = models.PositiveIntegerField(help_text="e.g. 2026")
    start_date = models.DateField()
    end_date = models.DateField()
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.fiscal_year})"

class BudgetLine(models.Model):
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='budget_lines')
    amount = models.DecimalField(max_digits=15, decimal_places=2, help_text="Budgeted amount for the period")

    class Meta:
        unique_together = ('budget', 'account')

    def __str__(self):
        return f"{self.budget.name} - {self.account.code}: {self.amount}"
