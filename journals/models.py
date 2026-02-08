from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from finance.models import Account

class JournalEntry(models.Model):
    JOURNAL_TYPE_CHOICES = (
        ('GENERAL', 'General'),
        ('SALES', 'Sales'),
        ('PURCHASE', 'Purchase'),
        ('CASH_RECEIPT', 'Cash Receipt'),
        ('CASH_PAYMENT', 'Cash Payment'),
        ('ADJUSTMENT', 'Adjustment'),
    )
    
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('POSTED', 'Posted'),
    )

    date = models.DateField()
    description = models.CharField(max_length=255)
    journal_type = models.CharField(max_length=20, choices=JOURNAL_TYPE_CHOICES, default='GENERAL')
    reference = models.CharField(max_length=100, blank=True, null=True, help_text="e.g. Invoice #123")
    
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='DRAFT')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_journals', null=True)

    class Meta:
        verbose_name = "Journal Entry"
        verbose_name_plural = "Journal Entries"
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.date} - {self.description} ({self.status})"

class JournalLine(models.Model):
    entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='journal_lines')
    debit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    credit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    description = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.account.code} - Dr: {self.debit} Cr: {self.credit}"
        
class LedgerEntry(models.Model):
    """
    The immutable source of truth for financial reporting.
    Generated only when a JournalEntry is POSTED.
    """
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='ledger_entries')
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, related_name='ledger_entries')
    
    date = models.DateField()
    debit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    credit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    balance_after = models.DecimalField(max_digits=15, decimal_places=2)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date', 'created_at']
        indexes = [
            models.Index(fields=['account', 'date']),
        ]

    def __str__(self):
        return f"Ledger: {self.account.code} | {self.date} | Dr {self.debit} Cr {self.credit}"
