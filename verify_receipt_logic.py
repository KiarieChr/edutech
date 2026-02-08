
import os
import django
from decimal import Decimal, InvalidOperation as DecimalException

# Setup Django before imports
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()


from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory
from fees.receipt_views import ReceiptViewSet
from finance.models import PaymentMethod, Receipt, ReceiptAllocation
from accounts.models import Student
from student_settings.models import Term, AcademicYear
from fees.models import FeeInvoice, FeeInvoiceItem, FeeItem

def run_test():
    print("--- Starting Receipt Backend Verification ---")
    
    # 1. Fetch Prerequisites
    student = Student.objects.first()
    if not student:
        print("FAIL: No students found in DB.")
        return

    pm = PaymentMethod.objects.first()
    if not pm:
        print("FAIL: No payment methods found.")
        return

    year = AcademicYear.objects.filter(is_current=True).first() or AcademicYear.objects.first()
    term = Term.objects.filter(academic_year=year).first()
    
    if not year or not term:
        print("FAIL: No Active Year/Term found.")
        return

    print(f"Using Student: {student}")
    print(f"Using Payment Method: {pm}")
    print(f"Using Year/Term: {year} / {term}")

    # 2. Find or Create Invoice Item to Allocate
    invoice_item = FeeInvoiceItem.objects.filter(
        invoice__student=student, 
        invoice__status__in=['SENT', 'PARTIALLY_PAID', 'OVERDUE', 'DRAFT']
    ).first()

    allocations = []
    if invoice_item:
        print(f"Found Invoice Item to allocate: {invoice_item} (Amount: {invoice_item.amount})")
        allocations.append({
            "fee_category_id": invoice_item.fee_item.id, 
            "amount": 100, 
            "term_id": invoice_item.invoice.term.id,
            "academic_year_id": invoice_item.invoice.academic_year.id
        })
    else:
        print("WARNING: No pending invoice items found. Allocation logic will essentially skip loop, but Receipt should still create.")

    # 3. Construct Payload (Simulating Frontend Service format - snake_case)
    payload = {
        "receipt_type": "STUDENT_FEE",
        "student_id": student.id,
        "payment_method_id": pm.id,
        "amount_received": 1000, 
        "payer_name": "Backend Verifier",
        "reference": "TEST-VERIFY-001",
        "academic_year_id": year.id, 
        "term_id": term.id,
        "allocations": allocations,
        "notes": "Testing fixed allocation logic"
    }
    
    print("\nSending Payload:")
    print(payload)

    # 4. Invoke ViewSet
    factory = APIRequestFactory()
    request = factory.post('/api/fees/receipts/', payload, format='json')
    
    # Authentication
    User = get_user_model()
    request.user = User.objects.filter(is_superuser=True).first()
    
    view = ReceiptViewSet.as_view({'post': 'create'})
    
    try:
        response = view(request)
        print(f"\nResponse Status: {response.status_code}")
        print(f"Response Data: {response.data}")
        
        if response.status_code == 201:
            receipt_id = response.data.get('id')
            receipt = Receipt.objects.get(pk=receipt_id)
            print(f"\nSUCCESS: Receipt created! ID: {receipt_id}")
            print(f"Receipt Amount Received: {receipt.amount_received}")
            print(f"Receipt Amount Allocated: {receipt.amount_allocated}")
            
            # Check Allocations
            allocs = ReceiptAllocation.objects.filter(receipt=receipt)
            print(f"Allocations Created: {allocs.count()}")
            for a in allocs:
                print(f" - Allocated {a.amount} to {a.invoice_item}")
        else:
            print("FAIL: API returned error.")
            
    except Exception as e:
        print(f"EXCEPTION during view execution: {e}")

if __name__ == "__main__":
    run_test()
