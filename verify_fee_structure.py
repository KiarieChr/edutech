import os
import django
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from fees.models import FeeStructure, FeeItem
from student_settings.models import AcademicYear, Term, GradeStructure
from finance.models import Account
from invoicing.models import Invoice

def verify_fee_configuration():
    print("Verifying Fee Structure Configuration (No Accounting Impact)...")
    
    # Prerequisite Data
    year = AcademicYear.objects.first()
    term = Term.objects.first()
    grade = GradeStructure.objects.first()
    
    if not all([year, term, grade]):
        print("Skipping: Missing basic academic data.")
        return

    # 1. Create Structure
    print("\n1. creating Fee Structure...")
    # Clean prev test
    FeeStructure.objects.filter(academic_year=year, term=term, grade=grade).delete()
    
    structure = FeeStructure.objects.create(
        academic_year=year,
        term=term,
        grade=grade,
        status='DRAFT'
    )
    print(f"Structure created: {structure}")

    # 2. Add Items
    print("\n2. Adding Fee Items...")
    # Find valid account
    account = Account.objects.filter(type='INCOME', is_student_related=True).first()
    if not account:
        print("Warning: No student-related Income account found. Creating one for test.")
        # Ensure your Account model allows creating without manual ID if strictly managed
        # Assuming we can find one or user has one.
        pass
    
    if account:
        item = FeeItem.objects.create(
            structure=structure,
            name="Tuition Test",
            amount=Decimal('15000.00'),
            account=account,
            is_mandatory=True
        )
        print(f"Item added: {item}")
    else:
        print("Skipping Item creation (no valid account).")

    # 3. Verify No Side Effects (Invoices)
    print("\n3. Verifying NO Invoices created...")
    initial_invoice_count = Invoice.objects.count()
    
    # Save, Update, Change Status
    structure.status = 'ACTIVE'
    structure.save()
    
    final_invoice_count = Invoice.objects.count()
    
    if final_invoice_count == initial_invoice_count:
        print("SUCCESS: No invoices created during configuration.")
    else:
        print(f"FAILURE: Invoices count changed! ({initial_invoice_count} -> {final_invoice_count})")

    # 4. Verify Cloning
    print("\n4. Verifying Cloning...")
    # Mock next term
    # term2 = Term.objects.exclude(id=term.id).first() # if exists
    
    # Clone to same term (should fail unique constraint if saved with same params)
    # Let's clone to same instance in memory to check logic
    
    clone = FeeStructure(
        academic_year=year,
        term=term,
        grade=grade, # Duplicate!
        status='DRAFT'
    )
    # We won't save clone to DB to avoid error, just test clone_from method
    clone.save = lambda: None # Mock save
    clone.items = type('obj', (object,), {'all': lambda: []}) # Mock relation
    
    # Actually, let's create a real clone if we have another grade
    grade2 = GradeStructure.objects.exclude(id=grade.id).first()
    if grade2:
        clone_struct = FeeStructure.objects.create(
            academic_year=year,
            term=term,
            grade=grade2,
            status='DRAFT'
        )
        clone_struct.clone_from(structure)
        
        print(f"Cloned Structure Items: {clone_struct.items.count()}")
        if clone_struct.items.count() == structure.items.count():
            print("SUCCESS: Items cloned correctly.")
        else:
            print("FAILURE: Items not cloned.")
            
        clone_struct.items.all().delete()
        clone_struct.delete()
    else:
        print("Skipping Clone Test (Need >1 Grade)")

    # Cleanup
    structure.items.all().delete()
    structure.delete()
    print("\nVerification Complete.")

if __name__ == '__main__':
    verify_fee_configuration()
