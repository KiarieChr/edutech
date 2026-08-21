import os
import django
import sys

# Setup Django Environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import transaction
from journals.models import JournalEntry
from journals.services import JournalService

def fix_missing_ledger_entries():
    print("Checking for Journal Entries that are POSTED but missing (ledger_entries)...")
    
    # query: status is POSTED but related ledger_entries is empty
    # Distinct is important when filtering across relationships to avoid duplicates if multiple checks were involved, 
    # though here we check for 'isnull' so it's 1:1 check per journal.
    missing_ledger_journals = JournalEntry.objects.filter(
        status='POSTED',
        ledger_entries__isnull=True
    )
    
    count = missing_ledger_journals.count()
    print(f"Found {count} journals with missing ledger entries.")
    
    if count == 0:
        print("Everything looks healthy! No action needed.")
        return

    print("Starting re-posting process...")
    processed = 0
    errors = 0
    
    for journal in missing_ledger_journals:
        try:
            with transaction.atomic():
                print(f"Fixing Journal #{journal.id} ({journal.reference or 'No Ref'}) - {journal.description}")
                
                # 1. Reset to DRAFT (so post_journal_entry accepts it)
                journal.status = 'DRAFT'
                journal.save(update_fields=['status'])
                
                # 2. Post it properly
                JournalService.post_journal_entry(journal)
                processed += 1
                
        except Exception as e:
            print(f"FAILED to post Journal #{journal.id}: {e}")
            errors += 1
            # We continue to the next one, transaction atomic ensures this specific one rolls back
            
    print("-" * 30)
    print(f"Process Complete.")
    print(f"Successfully Reposted: {processed}")
    print(f"Errors: {errors}")

if __name__ == "__main__":
    fix_missing_ledger_entries()
