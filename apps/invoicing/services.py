from django.db import transaction
from django.core.exceptions import ValidationError
from .models import Invoice
from finance.models import Account, AccountType, AccountSubType, FinanceSettings
from journals.services import JournalService

class InvoiceService:
    @staticmethod
    @transaction.atomic
    def post_invoice(invoice: Invoice, user=None):
        # Allow posting any invoice that hasn't been posted yet (except VOID and PROFORMA)
        if invoice.status in ['VOID', 'PROFORMA']:
            raise ValidationError("Cannot post VOID or PROFORMA invoices.")
        
        if invoice.journal_entry:
            raise ValidationError("Invoice has already been posted to the ledger.")
            
        if not invoice.lines.exists():
            raise ValidationError("Invoice has no lines.")
            
        # 1. Find AR/Debtors Account from Settings
        settings = FinanceSettings.load()
        
        # Try to use sundry debtors account for general customer invoices
        ar_account = settings.default_sundry_debtors_account
        
        # Fallback to default receivable account
        if not ar_account:
            ar_account = settings.default_receivable_account
        
        # Final fallback - search for any active AR account
        if not ar_account:
            ar_account = Account.objects.filter(
                sub_type=AccountSubType.ACCOUNTS_RECEIVABLE, 
                is_active=True,
                children__isnull=True  # Ensure we pick a leaf account
            ).first()
        
        if not ar_account:
            raise ValidationError(
                "No Sundry Debtors or Accounts Receivable account configured. "
                "Please set the 'Sundry Debtors Account' in Finance Settings."
            )
            
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
            
        # Debit AR/Debtors Account (Total Receivable)
        journal_data['lines'].append({
            'account': ar_account,
            'debit': total_revenue,
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
