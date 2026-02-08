from django.db import transaction
from django.core.exceptions import ValidationError
from .models import Bill
from finance.models import Account, AccountType, AccountSubType
from journals.services import JournalService

class PayablesService:
    @staticmethod
    @transaction.atomic
    def post_bill(bill: Bill, user=None):
        if bill.status != 'DRAFT':
            raise ValidationError("Only DRAFT bills can be posted.")
            
        if not bill.lines.exists():
            raise ValidationError("Bill has no lines.")
            
        # 1. Find Accounts
        # AP Account (Liability -> Accounts Payable)
        ap_account = Account.objects.filter(
            sub_type=AccountSubType.ACCOUNTS_PAYABLE, 
            is_active=True,
            children__isnull=True # Ensure we pick a leaf account
        ).first()
        
        if not ap_account:
            raise ValidationError("No active Accounts Payable account found.")
            
        # 2. Prepare Journal Data
        journal_data = {
            'date': bill.date_received,
            'description': f"Bill #{bill.bill_number} - {bill.vendor.name}",
            'journal_type': 'PURCHASE',
            'reference': bill.bill_number,
            'lines': []
        }
        
        total_expense = 0
        
        # Debit Expense/Asset Accounts
        for line in bill.lines.all():
            journal_data['lines'].append({
                'account': line.expense_account,
                'debit': line.amount,
                'credit': 0,
                'description': line.description
            })
            total_expense += line.amount
            
        # Credit AP Account
        journal_data['lines'].append({
            'account': ap_account,
            'debit': 0,
            'credit': total_expense,
            'description': f"Payable for Bill #{bill.bill_number}"
        })
        
        # 3. Create and Post Journal
        entry = JournalService.create_journal_entry(journal_data, user=user)
        JournalService.post_journal_entry(entry)
        
        # 4. Update Bill
        bill.status = 'RECEIVED'
        bill.journal_entry = entry
        bill.save()
        
        return bill
