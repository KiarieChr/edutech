from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import FeeStructure, FeeInvoice, FeeInvoiceItem
from academics.models import StudentSessionEnrollment
from finance.models import FinanceSettings, Account
from journals.models import JournalEntry, JournalLine

class BillingService:
    @staticmethod
    def get_student_context(student_id):
        """
        Derives the billing context for a student based on their ACTIVE enrollment.
        Uses student_settings.Enrollment as the primary source of truth for Fees.
        """
        from student_settings.models import Enrollment
        
        # 1. Try to find active enrollment in Student Settings (The Fee/Admin Source)
        enrollment = Enrollment.objects.filter(
            student_id=student_id, 
            is_active=True
        ).order_by('-academic_year__start_date', '-term__start_date').first()

        if not enrollment:
            # Fallback (optional) or Return None
            return None

        # Map Enrollment fields to Context Variables
        grade = enrollment.grade
        term = enrollment.term
        year = enrollment.academic_year
        curriculum = enrollment.curriculum
        
        # Create a session-like object for the response (since we might not have a ClassSession object)
        session_name = f"{grade.name} - {term.name} {year.name}"
        session_id = None # derived, or we can try to fetch corresponding session if needed, but for billing strictness isn't required if we have grade/term.
        
        # Try to find the synced session just for ID reference (optional)
        from academics.models import ClassSession
        try:
             cs = ClassSession.objects.filter(grade=grade, term=term, academic_year=year, curriculum=curriculum).first()
             if cs: 
                 session_id = cs.id
                 session_name = cs.name
        except:
             pass

        # Find Active Fee Structure
        # Prioritize matching curriculum, fallback to null/default if structure design permits (but usually strict)
        structure = FeeStructure.objects.filter(
            academic_year=year,
            term=term,
            grade=grade,
            status='ACTIVE'
        ).first()
        
        if not structure:
            # Fallback for Duplicate Grades: Filter by Name
             structure = FeeStructure.objects.filter(
                academic_year=year,
                term=term,
                grade__name__iexact=grade.name,
                status='ACTIVE'
            ).first()

        # If curriculum specific structures exist, filter further
        if structure and structure.curriculum and structure.curriculum != curriculum:
             # If the found structure has a curriculum that doesn't match, we need to look harder
             structure = FeeStructure.objects.filter(
                academic_year=year,
                term=term,
                grade=grade,
                curriculum=curriculum,
                status='ACTIVE'
            ).first()
             
             if not structure:
                 # Fallback for curriculum specific too
                 structure = FeeStructure.objects.filter(
                    academic_year=year,
                    term=term,
                    grade__name__iexact=grade.name,
                    curriculum=curriculum,
                    status='ACTIVE'
                ).first()

        context = {
            'student_id': student_id,
            'student_name': str(enrollment.student),
            'enrollment_id': enrollment.id,
            'session': {
                'id': session_id,
                'name': session_name, 
                'grade_id': grade.id,
                'term_id': term.id,
                'year_id': year.id,
                'term_name': term.name,
                'year_name': year.name
            },
            'structure': None,
            'fee_items': []
        }

        if structure:
            context['structure'] = {
                'id': structure.id,
                'name': str(structure)
            }
            # Serialize Items
            items = structure.items.all().order_by('priority')
            context['fee_items'] = [{
                'id': item.id,
                'name': item.name,
                'amount': float(item.amount),
                'is_mandatory': item.is_mandatory,
                'is_optional': item.is_optional,
                'account_id': item.account_id
            } for item in items]
            
        return context

    @staticmethod
    @transaction.atomic
    def generate_invoice(data, user=None):
        """
        Generates a FeeInvoice and posts the Journal Entry.
        data = {
            'student_id': 1,
            'enrollment_id': 10, # Optional validation
            'structure_id': 99,
            'items': [ {'id': 101, 'amount': 15000} ], # id is FeeItem ID
            'due_date': '2026-02-01',
            'remarks': '...'
        }
        """
        student_id = data.get('student_id')
        items_data = data.get('items', [])
        structure_id = data.get('structure_id')
        due_date = data.get('due_date')

        # 1. Validation
        try:
            structure = FeeStructure.objects.get(pk=structure_id)
        except FeeStructure.DoesNotExist:
            raise ValidationError("Invalid Fee Structure")

        # 2. Find Correct Enrollment to Link
        # Instead of just picking 'active', we must match the FeeStructure's context (Year/Term/Grade)
        from academics.models import ClassSession, StudentSessionEnrollment
        
        # Strategy 1: Strict Match (Grade ID + Curriculum)
        session = ClassSession.objects.filter(
            academic_year=structure.academic_year,
            term=structure.term,
            grade=structure.grade,
            curriculum=structure.curriculum
        ).first()

        # Strategy 2: Grade ID Match (Ignore Curriculum - maybe session has None or different)
        if not session:
            session = ClassSession.objects.filter(
                academic_year=structure.academic_year,
                term=structure.term,
                grade=structure.grade
            ).first()

        # Strategy 3: Grade Name Match (Handle Duplicate Grades, Ignore Curriculum)
        if not session:
             session = ClassSession.objects.filter(
                academic_year=structure.academic_year,
                term=structure.term,
                grade__name__iexact=structure.grade.name
            ).first()

        if not session:
            # Strategy 4: Create it (Standard/Default)
            # We use get_or_create just on the Unique fields to avoid IntegrityError
            try:
                session, _ = ClassSession.objects.get_or_create(
                    grade=structure.grade,
                    term=structure.term,
                    academic_year=structure.academic_year,
                    defaults={
                        'curriculum': structure.curriculum, # Set this if creating
                        'name': f"{structure.grade.name} - {structure.term.name} {structure.academic_year.name}",
                        'status': 'active',
                        'start_date': structure.term.start_date, 
                        'end_date': structure.term.end_date
                    }
                )
            except Exception as e:
                # This catches other DB errors, but logic above should handle unique constraints.
                print(f"Session Auto-Creation Failed: {e}")
                pass

        if not session:
            # If session STILL doesn't exist, we can't link an invoice to it.
            raise ValidationError(f"No Academic Session found for {structure.grade.name} {structure.term.name}. Pls contact admin.")

        enrollment = StudentSessionEnrollment.objects.filter(student_id=student_id, session=session).first()
        
        if not enrollment:
             # Try to find ANY active enrollment if specific one fails? 
             # No, FeeInvoice requires strict linking.
             # Auto-fix: Create the enrollment if it's missing (Lazy Sync)
             # This is safe because we are generating an invoice for this specific session.
             from student_settings.models import Intake
             # Try to find intake
             intake = None
             if hasattr(user, 'student') and user.student.intake:
                 intake = user.student.intake
             if not intake:
                 intake = Intake.objects.filter(academic_year=structure.academic_year, is_active=True).first()
             
             if intake:
                 enrollment = StudentSessionEnrollment.objects.create(
                     student_id=student_id,
                     session=session,
                     intake=intake,
                     status='active',
                     is_active=True # Assume active if we are billing
                 )
             else:
                 raise ValidationError("Student is not enrolled in this Session and no Intake found to auto-enroll.")

        # 2. Create Invoice
        invoice = FeeInvoice.objects.create(
            student_enrollment=enrollment,
            student_id=student_id,
            class_session=enrollment.session,
            term=structure.term,
            academic_year=structure.academic_year,
            due_date=due_date,
            status='DRAFT', # Will update to ISSUED after posting
            total_amount=0 # Calc below
        )

        total_amount = 0
        invoice_lines = []

        # 3. Create Invoice Items
        # Map input items to actual FeeItems to get accounts
        fee_items_map = {item.id: item for item in structure.items.all()}
        
        for input_item in items_data:
            f_item_id = input_item.get('id')
            amount = input_item.get('amount')
            
            if f_item_id not in fee_items_map:
                continue # Skip invalid items not in structure
                
            original_item = fee_items_map[f_item_id]
            
            line = FeeInvoiceItem.objects.create(
                invoice=invoice,
                fee_item=original_item,
                description=original_item.name,
                amount=amount,
                is_mandatory=original_item.is_mandatory
            )
            invoice_lines.append(line)
            total_amount += float(amount)

        invoice.total_amount = total_amount
        invoice.balance = total_amount
        invoice.status = 'SENT' # De facto issued
        invoice.save()

        # 4. Accounting Posting
        # Debit: Student Receivables (Asset)
        # Credit: Various Income/Liability Accounts (from items)
        
        settings = FinanceSettings.load()
        receivable_acc = settings.default_receivable_account
        
        if not receivable_acc:
            raise ValidationError("System Finance Settings missing Default Receivable Account. Cannot post invoice.")

        # 4. Accounting Posting
        from journals.services import JournalService
        
        # Prepare Journal Data
        description = f"Invoice for {enrollment.student} - {invoice.term}"
        if data.get('is_automated'):
            description += " (Auto-Generated)"

        journal_data = {
            'date': timezone.now().date(),
            'reference': invoice.invoice_number,
            'description': description,
            'journal_type': 'SALES',
            'status': 'DRAFT'
        }
        
        lines_data = []
        
        # Line 1: Debit Receivable (Total)
        lines_data.append({
            'account': receivable_acc,
            'debit': total_amount,
            'credit': 0,
            'description': f"Invoice {invoice.invoice_number}"
        })
        
        # Lines 2..N: Credit individual accounts
        for line in invoice_lines:
             # FeeItem has the account
            credit_acc = line.fee_item.account
            
            # Ensure account exists (it should, database constraint)
            if credit_acc:
                lines_data.append({
                    'account': credit_acc,
                    'debit': 0,
                    'credit': line.amount,
                    'description': line.description
                })
        
        # Create and Post
        try:
            journal_data['lines'] = lines_data
            entry = JournalService.create_journal_entry(journal_data, user=user)
            JournalService.post_journal_entry(entry)
            
            # Link journal to invoice (optional if model supports it)
            # invoice.journal_entry = entry 
            # invoice.save()
            
        except Exception as e:
            # Revert invoice creation if posting fails?
            # Since we are in transaction.atomic, raising error will rollback everything.
            raise ValidationError(f"Accounting Posting Failed: {str(e)}")

            
        return invoice
