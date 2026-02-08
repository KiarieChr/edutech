import os
import django
import sys

# Setup Django Environment
sys.path.append('d:\\Tims Projects\\edutech')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from finance.models import FinanceSettings, Account, AccountType, AccountSubType

def configure_defaults():
    print("--- Configuring Finance Defaults ---")
    settings = FinanceSettings.load()
    
    # 1. Find or Create Receivable Account
    # Look for "Student Receivables" or "Student Debtors"
    receivable = Account.objects.filter(
        sub_type=AccountSubType.ACCOUNTS_RECEIVABLE,
        is_student_related=True
    ).first()
    
    if not receivable:
        print("No Student Receivable account found. Creating one...")
        receivable = Account.objects.create(
            name="Student Debtors Control",
            code="1200", # Example code
            type=AccountType.ASSET,
            sub_type=AccountSubType.ACCOUNTS_RECEIVABLE,
            is_student_related=True,
            description="Auto-generated Control Account for Student Fees"
        )
        print(f"Created Account: {receivable}")
    else:
        print(f"Found Existing Receivable Account: {receivable}")

    # 2. Update Settings
    if not settings.default_receivable_account:
        settings.default_receivable_account = receivable
        settings.save()
        print(f"SUCCESS: Updated FinanceSettings.default_receivable_account = {receivable.name}")
    else:
        print(f"FinanceSettings already has a default: {settings.default_receivable_account}")

if __name__ == "__main__":
    configure_defaults()
