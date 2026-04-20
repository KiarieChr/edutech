from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import FeeStructure, FeeInvoice, FeeInvoiceItem
from academics.models import StudentSessionEnrollment, ClassSession
from finance.models import FinanceSettings, Account
from journals.models import JournalEntry, JournalLine


def ensure_session_enrollment(student_id, grade, term, year, curriculum=None):
    """
    Find or create a ClassSession + StudentSessionEnrollment for a student.
    Bridges the gap between student_settings.Enrollment and academics models.
    Returns the StudentSessionEnrollment instance.
    """
    from student_settings.models import Enrollment

    # 1. Find or create ClassSession
    session = ClassSession.objects.filter(
        grade=grade, term=term, academic_year=year
    ).first()

    if not session:
        # Auto-create session
        curriculum_to_use = curriculum or grade.curriculum
        session = ClassSession.objects.create(
            grade=grade,
            term=term,
            academic_year=year,
            curriculum=curriculum_to_use,
            status='active',
        )

    # 2. Find or create StudentSessionEnrollment
    enrollment, created = StudentSessionEnrollment.objects.get_or_create(
        student_id=student_id,
        session=session,
        defaults={
            'status': 'active',
            'is_active': True,
            'intake_id': _get_student_intake(student_id),
            'stream_id': _get_student_stream(student_id, grade, term, year),
        }
    )
    return enrollment


def _get_student_intake(student_id):
    """Get intake from student_settings.Enrollment or student record."""
    from student_settings.models import Enrollment
    enr = Enrollment.objects.filter(
        student_id=student_id, is_active=True
    ).values_list('intake_id', flat=True).first()
    if enr:
        return enr
    from accounts.models import Student
    return Student.objects.filter(pk=student_id).values_list('intake_id', flat=True).first()


def _get_student_stream(student_id, grade, term, year):
    """Get stream from the student's active enrollment."""
    from student_settings.models import Enrollment
    return Enrollment.objects.filter(
        student_id=student_id, grade=grade, term=term,
        academic_year=year, is_deleted=False
    ).values_list('stream_id', flat=True).first()

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
            # Serialize Items - use is_optional (is_mandatory is computed property)
            items = structure.items.all().order_by('priority')
            context['fee_items'] = [{
                'id': item.id,
                'name': item.name,
                'amount': float(item.amount),
                'is_optional': item.is_optional,  # Backend field
                'is_mandatory': item.is_mandatory,  # Computed property for compatibility
                'account_id': item.account_id
            } for item in items]
            
        return context

    @staticmethod
    @transaction.atomic
    def generate_invoice(data, user=None):
        """
        Generates a FeeInvoice and posts the Journal Entry.
        
        KENYA SCHOOL BILLING RULES:
        - Student must be enrolled (StudentSessionEnrollment) before invoice generation
        - One invoice per student per term (unless previous is VOID)
        - Never auto-create sessions or enrollments
        
        data = {
            'student_id': 1,
            'structure_id': 99,
            'items': [{'id': 101, 'amount': 15000}],  # id is FeeItem ID
            'due_date': '2026-02-01',
            'remarks': '...',
            'is_automated': False  # Set True for bulk generation
        }
        """
        student_id = data.get('student_id')
        items_data = data.get('items', [])
        structure_id = data.get('structure_id')
        due_date = data.get('due_date')

        # 1. Validate Fee Structure
        try:
            structure = FeeStructure.objects.get(pk=structure_id)
        except FeeStructure.DoesNotExist:
            raise ValidationError("Invalid Fee Structure.")
        
        if structure.status != 'ACTIVE':
            raise ValidationError(
                f"Fee Structure '{structure}' is not ACTIVE. Only ACTIVE structures can be invoiced."
            )

        # 2. Find Student Enrollment - auto-create from student_settings.Enrollment if needed
        enrollment = StudentSessionEnrollment.objects.filter(
            student_id=student_id,
            session__grade=structure.grade,
            session__term=structure.term,
            session__academic_year=structure.academic_year
        ).first()
        
        if not enrollment:
            # Try to auto-create from student_settings.Enrollment
            enrollment = ensure_session_enrollment(
                student_id, structure.grade, structure.term,
                structure.academic_year, structure.curriculum
            )

        # 3. Check for existing non-void invoice (prevent duplicates)
        existing_invoice = FeeInvoice.objects.filter(
            student_enrollment=enrollment
        ).exclude(status='VOID').first()
        
        if existing_invoice:
            raise ValidationError(
                f"An active invoice ({existing_invoice.invoice_number}) already exists for this "
                f"enrollment. Void the existing invoice before creating a new one."
            )

        # 4. Create Invoice
        invoice = FeeInvoice.objects.create(
            student_enrollment=enrollment,
            student_id=student_id,
            class_session=enrollment.session,
            term=structure.term,
            academic_year=structure.academic_year,
            due_date=due_date,
            status='DRAFT',  # Will update to SENT after posting
            total_amount=0  # Calculated below
        )

        total_amount = 0
        invoice_lines = []

        # 5. Create Invoice Items
        # Map input items to actual FeeItems to get accounts
        fee_items_map = {item.id: item for item in structure.items.all()}
        
        for input_item in items_data:
            f_item_id = input_item.get('id')
            amount = input_item.get('amount')
            
            if f_item_id not in fee_items_map:
                continue  # Skip invalid items not in structure
                
            original_item = fee_items_map[f_item_id]
            
            line = FeeInvoiceItem.objects.create(
                invoice=invoice,
                fee_item=original_item,
                description=original_item.name,
                amount=amount,
                is_optional=original_item.is_optional  # Snapshot optional status
            )
            invoice_lines.append(line)
            total_amount += float(amount)

        invoice.total_amount = total_amount
        invoice.balance = total_amount
        invoice.status = 'SENT'  # De facto issued
        invoice.save()

        # 6. Accounting Posting
        # Debit: Student Receivables (Asset)
        # Credit: Various Income/Liability Accounts (from items)
        
        settings = FinanceSettings.load()
        receivable_acc = settings.default_receivable_account
        
        if not receivable_acc:
            raise ValidationError(
                "System Finance Settings missing Default Receivable Account. Cannot post invoice."
            )

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
        
        # Lines 2..N: Credit individual income/liability accounts
        for line in invoice_lines:
            credit_acc = line.fee_item.account
            
            if credit_acc:
                lines_data.append({
                    'account': credit_acc,
                    'debit': 0,
                    'credit': line.amount,
                    'description': line.description
                })
        
        # Create and Post Journal Entry
        try:
            journal_data['lines'] = lines_data
            entry = JournalService.create_journal_entry(journal_data, user=user)
            JournalService.post_journal_entry(entry)
            
        except Exception as e:
            # Since we are in transaction.atomic, raising error will rollback everything
            raise ValidationError(f"Accounting Posting Failed: {str(e)}")

        return invoice

    @staticmethod
    @transaction.atomic
    def bulk_generate_invoices(data, user=None):
        """
        Generates invoices for all active students in a ClassSession.
        
        KENYA SCHOOL BILLING RULES:
        - Bulk billing is per session (grade + term + year)
        - Students with existing non-void invoices are skipped
        - All invoices use the same fee structure and due date
        
        data = {
            'session_id': 1,        # ClassSession ID (required)
            'due_date': '2026-02-15',
            'remarks': 'Term 1 fees'
        }
        
        Returns:
            {
                'success': ['INV-2026-T1-0001', 'INV-2026-T1-0002', ...],
                'skipped': [
                    {'student_id': 5, 'reason': 'Invoice already exists'},
                    {'student_id': 8, 'reason': 'No fee structure found'},
                    ...
                ]
            }
        """
        from academics.models import ClassSession
        
        session_id = data.get('session_id')
        due_date = data.get('due_date')
        remarks = data.get('remarks', '')
        
        if not session_id:
            raise ValidationError("session_id is required for bulk invoice generation.")
        
        # 1. Get the ClassSession
        try:
            session = ClassSession.objects.select_related(
                'grade', 'term', 'academic_year'
            ).get(pk=session_id)
        except ClassSession.DoesNotExist:
            raise ValidationError(f"ClassSession with ID {session_id} not found.")
        
        # 2. Find the active fee structure for this session
        # Match by grade, term, year. Curriculum matching is handled by structure design.
        structure = FeeStructure.objects.filter(
            academic_year=session.academic_year,
            term=session.term,
            grade=session.grade,
            status='ACTIVE'
        ).first()
        
        if not structure:
            raise ValidationError(
                f"No ACTIVE fee structure found for {session.grade.name} "
                f"{session.term.name} {session.academic_year.name}."
            )
        
        # 3. Get all active enrollments for this session
        enrollments = StudentSessionEnrollment.objects.filter(
            session=session,
            is_active=True
        ).select_related('student')
        
        if not enrollments.exists():
            raise ValidationError(
                f"No active student enrollments found for session: {session}."
            )
        
        # 4. Prepare fee items (all mandatory items by default)
        items_data = [{
            'id': item.id,
            'amount': float(item.amount)
        } for item in structure.items.filter(is_optional=False)]  # Only mandatory items
        
        success = []
        skipped = []
        
        # 5. Generate invoice for each enrolled student
        for enrollment in enrollments:
            student_id = enrollment.student_id
            student_name = str(enrollment.student)
            
            # Check for existing non-void invoice
            existing = FeeInvoice.objects.filter(
                student_enrollment=enrollment
            ).exclude(status='VOID').first()
            
            if existing:
                skipped.append({
                    'student_id': student_id,
                    'student_name': student_name,
                    'reason': f"Invoice already exists ({existing.invoice_number})"
                })
                continue
            
            # Attempt to generate invoice
            try:
                invoice_data = {
                    'student_id': student_id,
                    'structure_id': structure.id,
                    'items': items_data,
                    'due_date': due_date,
                    'remarks': remarks,
                    'is_automated': True  # Flag for journal description
                }
                
                invoice = BillingService.generate_invoice(invoice_data, user=user)
                success.append(invoice.invoice_number)
                
            except ValidationError as e:
                skipped.append({
                    'student_id': student_id,
                    'student_name': student_name,
                    'reason': str(e)
                })
            except Exception as e:
                skipped.append({
                    'student_id': student_id,
                    'student_name': student_name,
                    'reason': f"Unexpected error: {str(e)}"
                })
        
        return {
            'success': success,
            'skipped': skipped,
            'summary': {
                'total_processed': len(enrollments),
                'invoices_created': len(success),
                'students_skipped': len(skipped)
            }
        }
