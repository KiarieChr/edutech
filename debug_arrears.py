# Debug script to check FeeInvoice data
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from fees.models import FeeInvoice
from student_settings.models import AcademicYear, Term

print("=== ACADEMIC YEARS ===")
years = AcademicYear.objects.filter(is_deleted=False).order_by('-start_date')
for year in years:
    print(f"  {year.id}: {year.name} ({year.start_date} to {year.end_date})")

print("\n=== TERMS ===")
terms = Term.objects.filter(is_deleted=False).order_by('academic_year', 'order')
for term in terms:
    print(f"  {term.id}: {term.name} - {term.academic_year.name}")

print("\n=== FEE INVOICES ===")
invoices = FeeInvoice.objects.all().select_related('academic_year', 'term', 'student')
print(f"Total invoices: {invoices.count()}")

if invoices.count() > 0:
    print("\nBreakdown by year:")
    for year in years:
        year_invoices = invoices.filter(academic_year=year)
        print(f"  {year.name}: {year_invoices.count()} invoices")
        
        # Show invoice details
        for inv in year_invoices[:3]:  # Show first 3
            print(f"    - {inv.invoice_number}: {inv.student.admission_number if inv.student else 'No student'} - Balance: {inv.balance}")
    
    print("\nInvoices with balance > 0 (arrears):")
    arrears = invoices.filter(balance__gt=0).exclude(status='VOID')
    print(f"  Total: {arrears.count()}")
    for year in years:
        year_arrears = arrears.filter(academic_year=year)
        print(f"  {year.name}: {year_arrears.count()} with arrears")
else:
    print("❌ NO INVOICES FOUND IN DATABASE")
    print("\nThis is why the dashboard shows no data.")
    print("You need to create invoices first using the billing system.")
