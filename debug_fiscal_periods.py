import os
import django
import sys

# Setup Django Environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from finance.models import FiscalPeriod

def check_fiscal_periods():
    print("Checking Fiscal Periods in Database...")
    count = FiscalPeriod.objects.count()
    print(f"Total Count: {count}")
    
    if count == 0:
        print(">> The database has NO Fiscal Periods.")
    else:
        print(">> Listing Periods:")
        for p in FiscalPeriod.objects.all().order_by('-start_date'):
            print(f"- ID: {p.id} | Name: {p.name} | Start: {p.start_date} | End: {p.end_date} | Closed: {p.is_closed}")

if __name__ == "__main__":
    check_fiscal_periods()
