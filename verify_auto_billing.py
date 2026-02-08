import os
import django
from django.utils import timezone
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from student_management.models import ClassSession
from fees.models import FeeStructure, FeeItem
from finance.models import Account, FinanceSettings
from student_settings.models import AcademicYear, Term, GradeStructure, Curriculum
from accounts.models import Student

def verify_auto_billing():
    print("Verifying Auto Billing...")
    
    # 1. Setup Data
    print("Setting up test data...")
    # Ensure settings enabled
    settings = FinanceSettings.load()
    settings.auto_billing_enabled = True
    settings.save()
    
    # Get or create dependencies
    year = AcademicYear.objects.first()
    term = Term.objects.first()
    grade = GradeStructure.objects.first()
    
    if not all([year, term, grade]):
        print("Error: Missing basic academic data (Year, Term, or Grade). Cannot proceed.")
        return

    # Create Fee Structure
    structure, created = FeeStructure.objects.get_or_create(
        academic_year=year,
        term=term,
        grade=grade,
        defaults={'is_active': True}
    )
    
    # Add Item
    income_acc = Account.objects.filter(type='INCOME').first()
    if not income_acc:
        print("Error: No Income Account found.")
        return
        
    FeeItem.objects.get_or_create(
        structure=structure,
        name="Tuition Fee Test",
        defaults={'amount': Decimal('10000.00'), 'account': income_acc}
    )
    
    # Get Student
    student = Student.objects.first()
    if not student:
        print("Error: No Student found.")
        return

    print(f"Testing with Student: {student}")

    # 2. Trigger Auto Billing (Create Reporting Session)
    print("Triggering student reporting...")
    session = ClassSession.objects.create(
        student=student,
        academic_year=year,
        term=term,
        grade=grade,
        curriculum=structure.curriculum if structure.curriculum else Curriculum.objects.first(), # diligent check
        session_type='reporting',
        session_status='active',
        start_date=timezone.now().date()
    )
    
    # 3. Verify Invoice
    print("Checking for invoice...")
    from invoicing.models import Invoice
    # Check for invoice created today for this student
    # Note: Service creates invoice number based on session.
    expected_inv_num = f"INV-{year}-{term}-{student.id}"
    
    try:
        invoice = Invoice.objects.get(invoice_number=expected_inv_num)
        print(f"SUCCESS: Invoice {invoice.invoice_number} created!")
        print(f"Amount: {invoice.total_amount}")
        print(f"Status: {invoice.status}")
        
        # Cleanup
        invoice.lines.all().delete()
        invoice.delete()
        session.delete()
        if created:
             structure.items.all().delete()
             structure.delete()
             
    except Invoice.DoesNotExist:
        print(f"FAILURE: Invoice {expected_inv_num} was NOT created.")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == '__main__':
    verify_auto_billing()
