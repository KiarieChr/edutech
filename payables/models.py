from django.db import models
from django.conf import settings
from finance.models import Account, AccountType

class Vendor(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    tax_id = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Bill(models.Model):
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
    
    # Link to journal entry when posted
    journal_entry = models.OneToOneField('journals.JournalEntry', on_delete=models.SET_NULL, null=True, blank=True, related_name='bill')
    
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True)

    class Meta:
        ordering = ['-date_received', 'bill_number']
        unique_together = ('vendor', 'bill_number')

    def __str__(self):
        return f"{self.vendor.name} - {self.bill_number}"

class BillLine(models.Model):
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name='lines')
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    
    # Expense or Asset account to debit
    expense_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='bill_lines', 
                                        limit_choices_to=models.Q(type='EXPENSE') | models.Q(type='ASSET'))

    def __str__(self):
        return f"{self.description} - {self.amount}"
