from django.db import transaction
from django.core.exceptions import ValidationError
from .models import Invoice
from finance.models import Account, AccountType, AccountSubType
from journals.services import JournalService

class InvoiceService:
    @staticmethod
    @transaction.atomic
    def post_invoice(invoice: Invoice, user=None):
        if invoice.status != 'DRAFT':
            raise ValidationError("Only DRAFT invoices can be posted.")
            
        if not invoice.lines.exists():
            raise ValidationError("Invoice has no lines.")
            
        # 1. Find Accounts
        # AR Account (Asset -> Accounts Receivable)
        # For simplicity, pick the first active AR account. In real app, might come from Customer or Settings.
        ar_account = Account.objects.filter(
            sub_type=AccountSubType.ACCOUNTS_RECEIVABLE, 
            is_active=True,
            children__isnull=True # Ensure we pick a leaf account
        ).first()
        
        if not ar_account:
            raise ValidationError("No active Accounts Receivable account found. Please configure the Chart of Accounts.")
            
        # 2. Prepare Journal Data
        journal_data = {
            'date': invoice.date_issued,
            'description': f"Invoice #{invoice.invoice_number} - {invoice.customer.name}",
            'journal_type': 'SALES',
            'reference': invoice.invoice_number,
            'lines': []
        }
        
        total_revenue = 0
        
        # Credit Income Accounts (Revenue)
        for line in invoice.lines.all():
            journal_data['lines'].append({
                'account': line.income_account,
                'debit': 0,
                'credit': line.amount,
                'description': line.description
            })
            total_revenue += line.amount
            
        # Debit AR Account (Total Receivable)
        # Note: If tax exists, tax is also credited to Tax Payable, and AR = Revenue + Tax.
        # Assuming simple model for now (Total = Revenue).
        
        journal_data['lines'].append({
            'account': ar_account,
            'debit': total_revenue, # Should match invoice.total_amount
            'credit': 0,
            'description': f"Receivable for Invoice #{invoice.invoice_number}"
        })
        
        # 3. Create and Post Journal
        entry = JournalService.create_journal_entry(journal_data, user=user)
        JournalService.post_journal_entry(entry)
        
        # 4. Update Invoice
        invoice.status = 'ISSUED'
        invoice.journal_entry = entry
        invoice.save()
        
        return invoice
