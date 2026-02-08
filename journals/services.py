from django.db import transaction
from django.db.models import Sum
from django.core.exceptions import ValidationError
from .models import JournalEntry, LedgerEntry

class JournalService:
    @staticmethod
    @transaction.atomic
    def post_journal_entry(entry: JournalEntry):
        """
        Validates and posts a valid journal entry to the Ledger.
        Sets status='POSTED'.
        """
        # 0. Auto-close expired periods to ensure validation is accurate
        # This acts as a "lazy" cron job
        from finance.models import FiscalPeriod
        FiscalPeriod.auto_close_expired()

        # 1. Check if already posted
        if entry.status == 'POSTED':
            raise ValidationError("Journal entry is already posted.")

        # 1.5 Check Fiscal Period Status
        from finance.models import FiscalPeriod
        period = FiscalPeriod.objects.filter(
            start_date__lte=entry.date, 
            end_date__gte=entry.date
        ).first()

        if period and period.is_closed:
             raise ValidationError(f"Cannot post to a Closed Fiscal Period: {period.name} ({period.start_date} - {period.end_date})")
        
        # Optional: Enforce period existence? 
        # For now, if no period defined, we allow it (flexible), or we could block it.
        # Strict mode would be: if not period: raise ValidationError("No Fiscal Period defined for this date.")

        # 2. Validate Lines Exist
        lines = entry.lines.select_related('account').all()
        if not lines.exists():
            raise ValidationError("Journal entry must have at least one line.")

        # 3. Validate Balance (Double Entry)
        total_debit = sum(line.debit for line in lines)
        total_credit = sum(line.credit for line in lines)

        if total_debit != total_credit:
             raise ValidationError(f"Journal Entry is unbalanced. Total Debit: {total_debit}, Total Credit: {total_credit}.")

        # 4. Validate Accounts & Post to Ledger
        for line in lines:
            if line.account.children.exists():
                 raise ValidationError(f"Line account '{line.account.name}' is a parent account. Postings allowed only to leaf accounts.")
            
            # Calculate running balance
            # This is critical/complex for high volume, but for now:
            # Get last balance
            last_entry = LedgerEntry.objects.filter(account=line.account).order_by('-date', '-created_at').first()
            current_balance = last_entry.balance_after if last_entry else 0
            
            # Determine effective movement based on 'normal balance' logic?
            # Or just store purely mathematical balance?
            # Usually: Asset/Expense increases with Debit. Liab/Equity/Income increases with Credit.
            # Let's simple arithmetic: Balance = Sum(Dr) - Sum(Cr) for Asset/Expense?
            # Actually, let's keep it simple: Balance = Previous + Debit - Credit.
            # Interpreting that balance depends on account type in reporting.
            
            new_balance = current_balance + line.debit - line.credit
            
            LedgerEntry.objects.create(
                account=line.account,
                journal_entry=entry,
                date=entry.date,
                debit=line.debit,
                credit=line.credit,
                balance_after=new_balance
            )

        # 5. Lock and Post
        entry.status = 'POSTED'
        entry.save()
        
        return entry

    @staticmethod
    @transaction.atomic
    def create_journal_entry(data, user=None):
        lines_data = data.pop('lines', [])
        
        entry = JournalEntry(**data)
        if user:
            entry.created_by = user
        entry.save()
        
        from .models import JournalLine
        for line_data in lines_data:
            JournalLine.objects.create(entry=entry, **line_data)
            
        return entry
