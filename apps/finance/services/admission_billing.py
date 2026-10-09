from django.db import transaction
from django.utils import timezone
from apps.finance.models import AdmissionFeeTemplate, AdmissionFeeItem
from apps.invoicing.models import Invoice, InvoiceLine, Customer
from apps.student_settings.models import AcademicYear

def generate_student_admission_invoice(student, template_id=None):
    """
    Generates an invoice for admission fees.
    Idempotency: Ensure the student hasn't already been billed admission fees for this academic year.
    """
    academic_year = AcademicYear.objects.filter(is_current=True).first()
    if not academic_year:
        academic_year = AcademicYear.objects.filter(is_active=True).first()
    if not academic_year:
        return None, "No active academic year found."

    customer, created = Customer.objects.get_or_create(
        name=student.student.get_full_name(),
        defaults={
            'email': student.student.email,
            'tax_id': student.admission_number,
        }
    )

    # Check for existing admission invoice
    existing_invoice = Invoice.objects.filter(
        customer=customer,
        academic_year=academic_year,
        is_admission_fee=True,
        status__in=['DRAFT', 'ISSUED', 'PARTIAL', 'PAID']
    ).first()

    if existing_invoice:
        return existing_invoice, "Admission invoice already exists."

    with transaction.atomic():
        if template_id:
            template = AdmissionFeeTemplate.objects.filter(id=template_id, is_active=True).first()
        else:
            template = AdmissionFeeTemplate.objects.filter(is_active=True).first()

        if not template:
            return None, "No active admission fee template found."

        items = template.items.all()
        if not items:
            return None, "Admission fee template has no items."

        total_amount = sum(item.amount for item in items)

        invoice_number = f"ADM-{student.admission_number or student.id}-{timezone.now().strftime('%Y%m%d')}"

        invoice = Invoice.objects.create(
            customer=customer,
            academic_year=academic_year,
            invoice_number=invoice_number,
            date_issued=timezone.now().date(),
            due_date=timezone.now().date(),
            status='DRAFT',
            subtotal=total_amount,
            total_amount=total_amount,
            notes=f"Admission Fees for {student.student.get_full_name()}",
            is_admission_fee=True
        )

        for item in items:
            InvoiceLine.objects.create(
                invoice=invoice,
                income_account=item.account,
                description=item.name,
                quantity=1,
                unit_price=item.amount,
                amount=item.amount
            )

        return invoice, "Admission invoice generated successfully."
