from django.db import models
from django.conf import settings
from finance.models import Account, AccountType

class Customer(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    tax_id = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Invoice(models.Model):
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('PROFORMA', 'Proforma'),
        ('ISSUED', 'Issued'),
        ('PARTIALLY_PAID', 'Partially Paid'),
        ('PAID', 'Paid'),
        ('VOID', 'Void'),
    )
    
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    invoice_number = models.CharField(max_length=50, unique=True)
    date_issued = models.DateField()
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    
    # Recurring flag
    is_recurring = models.BooleanField(default=False)

    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    tax_total = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    
    # Link to journal entry when posted
    journal_entry = models.OneToOneField('journals.JournalEntry', on_delete=models.SET_NULL, null=True, blank=True, related_name='invoice')
    
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, related_name='created_invoices')

    class Meta:
        ordering = ['-date_issued', '-invoice_number']

    def __str__(self):
        return f"{self.invoice_number} - {self.customer.name}"

class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='lines')
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=15, decimal_places=2)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    
    # Revenue account to credit
    income_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='invoice_lines', limit_choices_to={'type': 'INCOME'})

    def save(self, *args, **kwargs):
        self.amount = self.quantity * self.unit_price
        super().save(*args, **kwargs)
