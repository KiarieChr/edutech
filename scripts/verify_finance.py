import os
import django
from decimal import Decimal
from datetime import date

# Setup Django source
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from finance.models import Account, AccountType, AccountSubType
from journals.models import JournalEntry, JournalLine, LedgerEntry
from journals.services import JournalService
from invoicing.models import Invoice, InvoiceLine, Customer
from invoicing.services import InvoiceService
from finance_reports.services import ReportService

def run_verification():
    print(">>> STARTING LEDGER VERIFICATION >>>")
    
    # 1. Verify Accounts
    print("\n1. Verifying Chart of Accounts...")
    # Select specific leaf accounts to avoid selecting parents (like '1000 - Assets' which matches subtype CASH)
    cash = Account.objects.filter(code='1100').first() # Cash on Hand
    sales_income = Account.objects.filter(code='4200').first() # Service Revenue
    ar = Account.objects.filter(code='1300').first() # Accounts Receivable
    
    if not (cash and sales_income and ar):
        print("!! FAILURE: Default accounts not found.")
        return

    # 2. Test Manual Journal Entry with Ledger Creation
    print("\n2. Testing Manual Journal Posting & Ledger Creation...")
    try:
        entry = JournalService.create_journal_entry({
            'date': date.today(),
            'description': 'Manual Cash Sale for Ledger Test',
            'journal_type': 'CASH_RECEIPT',
            'lines': [
                {'account': cash, 'debit': 1500, 'credit': 0, 'description': 'Cash Received'},
                {'account': sales_income, 'debit': 0, 'credit': 1500, 'description': 'Sales Revenue'}
            ]
        })
        JournalService.post_journal_entry(entry)
        
        # Verify status
        print(f"   Journal #{entry.id} Status: {entry.status}")
        
        # Verify Ledger Entries
        ledger_entries = LedgerEntry.objects.filter(journal_entry=entry)
        print(f"   Ledger Entries Created: {ledger_entries.count()}")
        for le in ledger_entries:
            print(f"      - Account: {le.account.code} | Dr: {le.debit} | Cr: {le.credit} | Bal: {le.balance_after}")
            
    except Exception as e:
        print(f"!! FAILURE: {e}")

    # 3. Verify Reports reading from Ledger
    print("\n3. Verifying Reports using Ledger Data...")
    
    # Trial Balance
    tb = ReportService.get_trial_balance()
    print(f"   Trial Balance Balanced: {tb['balanced']}")
    print(f"   Total Debit: {tb['total_debit']}")
    
    if tb['total_debit'] == 0:
        print("!! WARNING: Total Debit is 0. Did posting fail?")

    print("\n<<< VERIFICATION COMPLETED <<<")

if __name__ == '__main__':
    run_verification()
