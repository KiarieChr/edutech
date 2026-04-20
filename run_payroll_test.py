"""Quick script to re-run payroll and check journals."""
import os, django
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
django.setup()

from workforce.models import PayrollPeriod
from workforce.services.payroll_service import PayrollCalculationService
from workforce.models import PayrollCalculation, PayrollCalculationDetail
from journals.models import JournalEntry, JournalLine

period = PayrollPeriod.objects.get(id=3)
print(f"Running payroll for: {period.period_name}")

svc = PayrollCalculationService(period)
result = svc.run()

print(f"Success: {result['success']}")
print(f"Message: {result['message']}")
print(f"Processed: {result['processed']}")
if result['errors']:
    for e in result['errors']:
        print(f"  ERROR: {e}")
else:
    print("No errors!")

print("\n=== PAYROLL CALCULATIONS ===")
for c in PayrollCalculation.objects.filter(payroll_period=period):
    print(f"  {c.employee.employee_no} | gross={c.gross_pay} net={c.net_pay}")
    for d in c.details.all():
        pa_str = f"{d.payroll_account.code}" if d.payroll_account else "None"
        print(f"    {d.item_type} | {d.description} | amt={d.amount} | gl={d.gl_account_code} | pa={pa_str}")

print("\n=== PAYROLL JOURNAL ===")
ref = f"PAYROLL-{period.period_name}"
journals = JournalEntry.objects.filter(reference=ref)
if not journals.exists():
    print("  No payroll journal found!")
else:
    for j in journals:
        print(f"  ID={j.id} | {j.reference} | status={j.status} | date={j.date}")
        total_dr = 0
        total_cr = 0
        for line in j.lines.all():
            print(f"    {line.account.code} {line.account.name} | DR={line.debit} CR={line.credit} | {line.description}")
            total_dr += line.debit
            total_cr += line.credit
        print(f"  TOTALS: DR={total_dr} CR={total_cr} | Balanced={total_dr == total_cr}")
