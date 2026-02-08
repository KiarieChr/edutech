import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from journals.models import LedgerEntry
from finance.models import Account

entries = LedgerEntry.objects.all()
for entry in entries:
    print(f"Account: {entry.account.code} ({entry.account.name}) | Debit: {entry.debit} | Credit: {entry.credit} | Balance After: {entry.balance_after}")
