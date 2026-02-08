import os
import django
import sys

# Setup Django Environment
sys.path.append('d:\\Tims Projects\\edutech')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from finance.models import FinanceSettings

def check_settings():
    print("--- Checking Finance Settings ---")
    settings = FinanceSettings.load()
    
    print(f"Default Receivable Account: {settings.default_receivable_account}")
    if settings.default_receivable_account:
        print(f"  ID: {settings.default_receivable_account.id}")
        print(f"  Code: {settings.default_receivable_account.code}")
        print(f"  Name: {settings.default_receivable_account.name}")
    else:
        print("  WARNING: Not Set")

    print(f"Default Payable Account: {settings.default_payable_account}")

if __name__ == "__main__":
    check_settings()
