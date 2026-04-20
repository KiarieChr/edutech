"""
Template-based Billing Service (v2)

Resolves fee templates by grade (direct or via GradeBand), filters optional
items through StudentFeeProfile, and generates invoices with VoteHead-linked
line items while maintaining full backward-compatibility with the legacy
FeeStructure/FeeItem pipeline.
"""
from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import (
    FeeTemplate, TemplateLineItem, StudentFeeProfile,
    FeeInvoice, FeeInvoiceItem, VoteHead,
)
from academics.models import StudentSessionEnrollment, ClassSession
from finance.models import FinanceSettings


class BillingError(Exception):
    """Raised when template resolution or billing fails."""
    pass


class TemplateBillingService:
    """
    Template-aware billing service.  Falls back to the legacy
    BillingService.generate_invoice when no template is found,
    so existing workflows continue to work.
    """

    # ------------------------------------------------------------------
    # RESOLUTION
    # ------------------------------------------------------------------

    @staticmethod
    def resolve_template(student, term, academic_year):
        """
        Finds the ACTIVE FeeTemplate for a student's grade in a given term/year.

        Resolution priority:
          1. Template with direct grade match (via grades M2M)
          2. Template via grade_band containing the student's grade

        Raises BillingError if no match found.
        """
        from student_settings.models import Enrollment

        enrollment = Enrollment.objects.filter(
            student=student,
            is_active=True,
        ).order_by('-academic_year__start_date', '-term__start_date').first()

        if not enrollment:
            raise BillingError(f"No active enrollment for student {student}.")

        grade = enrollment.grade

        # Priority 1: direct grade match
        template = FeeTemplate.objects.filter(
            status='ACTIVE',
            term=term,
            academic_year=academic_year,
            grades=grade,
        ).first()

        if not template:
            # Priority 2: via grade_band
            template = FeeTemplate.objects.filter(
                status='ACTIVE',
                term=term,
                academic_year=academic_year,
                grade_band__grades=grade,
            ).first()

        if not template:
            raise BillingError(
                f"No active fee template covers {grade.name} for "
                f"{term.name} {academic_year.name}."
            )

        return template, enrollment

    @staticmethod
    def resolve_line_items(template, student):
        """
        Returns the TemplateLineItems that apply to this student:
          - Filter by applies_to (ALL / BOARDERS / DAY_SCHOLARS)
          - All mandatory items that pass applies_to filter
          - Optional items filtered via StudentFeeProfile

        Returns QuerySet of TemplateLineItem ordered by priority.
        """
        all_lines = template.line_items.select_related(
            'vote_head', 'override_account', 'vote_head__default_account'
        ).order_by('priority', 'vote_head__name')

        # Filter by applies_to based on student's boarding status
        profile = StudentFeeProfile.objects.filter(student=student).first()
        is_boarder = profile.is_boarder if profile else False

        if is_boarder:
            eligible_lines = all_lines.exclude(applies_to='DAY_SCHOLARS')
        else:
            eligible_lines = all_lines.exclude(applies_to='BOARDERS')

        mandatory = eligible_lines.filter(is_mandatory=True)

        # Resolve optional items
        optional_ids = []

        for line in eligible_lines.filter(is_mandatory=False):
            code = line.vote_head.code.upper()

            # Auto-include via profile flags
            if profile:
                if code in ('BRD', 'BOARDING') and profile.is_boarder:
                    optional_ids.append(line.id)
                    continue
                if code in ('TRN', 'TRANSPORT') and profile.uses_transport:
                    optional_ids.append(line.id)
                    continue
                # Custom opted-in vote heads
                if profile.custom_items.filter(id=line.vote_head_id).exists():
                    optional_ids.append(line.id)
                    continue

        included_ids = list(mandatory.values_list('id', flat=True)) + optional_ids
        return all_lines.filter(id__in=included_ids)

    # ------------------------------------------------------------------
    # BILLING CONTEXT (for frontend)
    # ------------------------------------------------------------------

    @staticmethod
    def get_student_context(student_id):
        """
        Returns the billing context for a student using the template system.
        Falls back to legacy BillingService if no template found.
        """
        from accounts.models import Student
        from student_settings.models import Enrollment

        try:
            student = Student.objects.get(pk=student_id)
        except Student.DoesNotExist:
            return None

        enrollment = Enrollment.objects.filter(
            student_id=student_id,
            is_active=True,
        ).select_related('grade', 'term', 'academic_year', 'curriculum').order_by(
            '-academic_year__start_date', '-term__start_date'
        ).first()

        if not enrollment:
            return None

        grade = enrollment.grade
        term = enrollment.term
        year = enrollment.academic_year

        # Try template resolution
        template = FeeTemplate.objects.filter(
            status='ACTIVE',
            term=term,
            academic_year=year,
        ).filter(
            # direct grade OR via band
            models_Q_grade_or_band(grade)
        ).first()

        if not template:
            # Fallback to legacy service
            from .services import BillingService
            return BillingService.get_student_context(student_id)

        # Resolve line items for this student
        lines = TemplateBillingService.resolve_line_items(template, student)

        # Build session reference
        session_id = None
        session_name = f"{grade.name} - {term.name} {year.name}"
        try:
            cs = ClassSession.objects.filter(
                grade=grade, term=term, academic_year=year
            ).first()
            if cs:
                session_id = cs.id
                session_name = cs.name
        except Exception:
            pass

        return {
            'student_id': student_id,
            'student_name': str(student),
            'enrollment_id': enrollment.id,
            'billing_source': 'template',
            'session': {
                'id': session_id,
                'name': session_name,
                'grade_id': grade.id,
                'term_id': term.id,
                'year_id': year.id,
                'term_name': term.name,
                'year_name': year.name,
            },
            'template': {
                'id': template.id,
                'name': template.name,
                'total': float(template.total_amount),
                'mandatory_total': float(template.mandatory_total),
            },
            'fee_items': [{
                'id': line.id,
                'vote_head_id': line.vote_head_id,
                'name': line.vote_head.name,
                'code': line.vote_head.code,
                'amount': float(line.amount),
                'is_optional': line.is_optional,
                'is_mandatory': line.is_mandatory,
                'account_id': line.effective_account.id if line.effective_account else None,
            } for line in lines],
        }

    # ------------------------------------------------------------------
    # INVOICE GENERATION
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def generate_invoice(data, user=None):
        """
        Generate a FeeInvoice from a FeeTemplate.

        data = {
            'student_id': int,
            'template_id': int,
            'line_item_ids': [int, ...],   # TemplateLineItem IDs to include
            'due_date': 'YYYY-MM-DD',
            'remarks': str,
            'is_automated': bool,
        }
        """
        from accounts.models import Student

        student_id = data['student_id']
        template_id = data['template_id']
        line_item_ids = data.get('line_item_ids', [])
        due_date = data.get('due_date')

        # 1. Validate template
        try:
            template = FeeTemplate.objects.get(pk=template_id)
        except FeeTemplate.DoesNotExist:
            raise ValidationError("Invalid Fee Template.")

        if template.status != 'ACTIVE':
            raise ValidationError(
                f"Fee Template '{template.name}' is not ACTIVE."
            )

        # 2. Get student
        try:
            student = Student.objects.get(pk=student_id)
        except Student.DoesNotExist:
            raise ValidationError("Student not found.")

        # 3. Find enrollment - auto-create from student_settings.Enrollment if needed
        enrollment = StudentSessionEnrollment.objects.filter(
            student_id=student_id,
            session__term=template.term,
            session__academic_year=template.academic_year,
            session__grade__in=template.get_covered_grades(),
        ).first()

        if not enrollment:
            # Auto-create: find student's grade from student_settings.Enrollment
            from student_settings.models import Enrollment as SettingsEnrollment
            from .services import ensure_session_enrollment
            settings_enr = SettingsEnrollment.objects.filter(
                student_id=student_id, is_active=True, is_deleted=False
            ).order_by('-academic_year__start_date').first()
            if settings_enr and settings_enr.grade in template.get_covered_grades():
                enrollment = ensure_session_enrollment(
                    student_id, settings_enr.grade, template.term,
                    template.academic_year, settings_enr.curriculum
                )

        if not enrollment:
            raise ValidationError(
                f"Student is not enrolled for {template.term.name} "
                f"{template.academic_year.name}. Enroll first."
            )

        # 4. Duplicate check
        existing = FeeInvoice.objects.filter(
            student_enrollment=enrollment,
        ).exclude(status='VOID').first()

        if existing:
            raise ValidationError(
                f"Active invoice ({existing.invoice_number}) already exists."
            )

        # 5. Determine line items
        if line_item_ids:
            lines = template.line_items.filter(id__in=line_item_ids).select_related(
                'vote_head', 'override_account', 'vote_head__default_account'
            )
        else:
            lines = TemplateBillingService.resolve_line_items(template, student)

        if not lines.exists():
            raise ValidationError("No line items resolved for this student.")

        # 6. Create Invoice
        invoice = FeeInvoice.objects.create(
            student_enrollment=enrollment,
            student=student,
            class_session=enrollment.session,
            term=template.term,
            academic_year=template.academic_year,
            due_date=due_date,
            status='DRAFT',
            total_amount=0,
        )

        total_amount = Decimal('0.00')
        invoice_lines = []

        for line in lines:
            inv_item = FeeInvoiceItem.objects.create(
                invoice=invoice,
                fee_item=None,  # No legacy FeeItem
                vote_head=line.vote_head,
                description=line.vote_head.name,
                amount=line.amount,
                is_optional=line.is_optional,
            )
            invoice_lines.append(inv_item)
            total_amount += line.amount

        invoice.total_amount = total_amount
        invoice.balance = total_amount
        invoice.status = 'SENT'
        invoice.save()

        # 7. Post journal entry
        settings = FinanceSettings.load()
        receivable_acc = settings.default_receivable_account
        if not receivable_acc:
            raise ValidationError(
                "Finance Settings missing Default Receivable Account."
            )

        from journals.services import JournalService

        description = f"Invoice for {student} - {template.term}"
        if data.get('is_automated'):
            description += " (Auto-Generated)"

        journal_data = {
            'date': timezone.now().date(),
            'reference': invoice.invoice_number,
            'description': description,
            'journal_type': 'SALES',
            'status': 'DRAFT',
            'lines': [],
        }

        # Debit receivable
        journal_data['lines'].append({
            'account': receivable_acc,
            'debit': float(total_amount),
            'credit': 0,
            'description': f"Invoice {invoice.invoice_number}",
        })

        # Credit per line item account
        for inv_item in invoice_lines:
            credit_acc = inv_item.effective_account
            if credit_acc:
                journal_data['lines'].append({
                    'account': credit_acc,
                    'debit': 0,
                    'credit': float(inv_item.amount),
                    'description': inv_item.description,
                })

        try:
            entry = JournalService.create_journal_entry(journal_data, user=user)
            JournalService.post_journal_entry(entry)
        except Exception as e:
            raise ValidationError(f"Accounting Posting Failed: {e}")

        return invoice

    # ------------------------------------------------------------------
    # BULK BILLING
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def bulk_generate_invoices(data, user=None):
        """
        Bulk-generate invoices for a ClassSession using fee templates.

        data = {
            'session_id': int,
            'due_date': 'YYYY-MM-DD',
            'remarks': str,
        }
        """
        session_id = data.get('session_id')
        due_date = data.get('due_date')

        if not session_id:
            raise ValidationError("session_id is required.")

        try:
            session = ClassSession.objects.select_related(
                'grade', 'term', 'academic_year'
            ).get(pk=session_id)
        except ClassSession.DoesNotExist:
            raise ValidationError(f"ClassSession {session_id} not found.")

        grade = session.grade
        term = session.term
        year = session.academic_year

        # Find template covering this grade
        from django.db.models import Q
        template = FeeTemplate.objects.filter(
            status='ACTIVE',
            term=term,
            academic_year=year,
        ).filter(
            Q(grades=grade) | Q(grade_band__grades=grade)
        ).first()

        if not template:
            # Fallback to legacy
            from .services import BillingService
            return BillingService.bulk_generate_invoices(data, user=user)

        enrollments = StudentSessionEnrollment.objects.filter(
            session=session,
            is_active=True,
        ).select_related('student')

        if not enrollments.exists():
            raise ValidationError(f"No active enrollments for session {session}.")

        success = []
        skipped = []

        for enrollment in enrollments:
            student = enrollment.student
            student_name = str(student)

            existing = FeeInvoice.objects.filter(
                student_enrollment=enrollment,
            ).exclude(status='VOID').first()

            if existing:
                skipped.append({
                    'student_id': student.id,
                    'student_name': student_name,
                    'reason': f"Invoice already exists ({existing.invoice_number})",
                })
                continue

            try:
                invoice = TemplateBillingService.generate_invoice({
                    'student_id': student.id,
                    'template_id': template.id,
                    'due_date': due_date,
                    'remarks': data.get('remarks', ''),
                    'is_automated': True,
                }, user=user)
                success.append(invoice.invoice_number)
            except (ValidationError, BillingError) as e:
                skipped.append({
                    'student_id': student.id,
                    'student_name': student_name,
                    'reason': str(e),
                })
            except Exception as e:
                skipped.append({
                    'student_id': student.id,
                    'student_name': student_name,
                    'reason': f"Unexpected error: {e}",
                })

        return {
            'success': success,
            'skipped': skipped,
            'summary': {
                'total_processed': len(enrollments),
                'invoices_created': len(success),
                'students_skipped': len(skipped),
            },
        }

    # ------------------------------------------------------------------
    # READINESS CHECK
    # ------------------------------------------------------------------

    @staticmethod
    def readiness_check(term_id, academic_year_id):
        """
        Returns a report of which class sessions have/lack an active
        fee template, so admins can fix gaps before bulk billing.
        """
        sessions = ClassSession.objects.filter(
            term_id=term_id,
            academic_year_id=academic_year_id,
        ).select_related('grade', 'term', 'academic_year')

        from django.db.models import Q

        report = []
        for session in sessions:
            grade = session.grade
            template = FeeTemplate.objects.filter(
                status='ACTIVE',
                term_id=term_id,
                academic_year_id=academic_year_id,
            ).filter(
                Q(grades=grade) | Q(grade_band__grades=grade)
            ).first()

            # Also check legacy FeeStructure
            from .models import FeeStructure
            legacy = FeeStructure.objects.filter(
                status='ACTIVE',
                term_id=term_id,
                academic_year_id=academic_year_id,
                grade=grade,
            ).first()

            enrolled = StudentSessionEnrollment.objects.filter(
                session=session, is_active=True
            ).count()

            report.append({
                'session_id': session.id,
                'session_name': session.name,
                'grade_id': grade.id,
                'grade_name': grade.name,
                'enrolled_students': enrolled,
                'has_template': template is not None,
                'template_id': template.id if template else None,
                'template_name': template.name if template else None,
                'has_legacy_structure': legacy is not None,
                'legacy_structure_id': legacy.id if legacy else None,
                'ready': template is not None or legacy is not None,
            })

        return {
            'term_id': term_id,
            'academic_year_id': academic_year_id,
            'total_sessions': len(report),
            'ready_count': sum(1 for r in report if r['ready']),
            'missing_count': sum(1 for r in report if not r['ready']),
            'sessions': report,
        }

    # ------------------------------------------------------------------
    # YEAR ROLLOVER
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def rollover(from_year_id, to_year_id, percentage_increase=0, dry_run=False):
        """
        Clones all ACTIVE templates from one academic year to another.

        Returns a report of what was/would be created.
        """
        from student_settings.models import AcademicYear, Term

        try:
            from_year = AcademicYear.objects.get(pk=from_year_id)
            to_year = AcademicYear.objects.get(pk=to_year_id)
        except AcademicYear.DoesNotExist:
            raise ValidationError("Invalid academic year ID.")

        source_templates = FeeTemplate.objects.filter(
            academic_year=from_year,
            status='ACTIVE',
        ).prefetch_related('line_items', 'grades')

        # Get terms for the target year
        target_terms = Term.objects.filter(academic_year=to_year)

        report = {
            'from_year': from_year.name,
            'to_year': to_year.name,
            'percentage_increase': percentage_increase,
            'dry_run': dry_run,
            'templates_found': source_templates.count(),
            'created': [],
            'skipped': [],
        }

        for src in source_templates:
            # Find matching term in target year
            target_term = target_terms.filter(name=src.term.name).first()
            if not target_term:
                report['skipped'].append({
                    'source': src.name,
                    'reason': f"No matching term '{src.term.name}' in {to_year.name}",
                })
                continue

            # Check if already exists
            from django.db.models import Q
            existing = FeeTemplate.objects.filter(
                academic_year=to_year,
                term=target_term,
                name=src.name,
            ).exists()

            if existing:
                report['skipped'].append({
                    'source': src.name,
                    'reason': f"Template '{src.name}' already exists for {target_term.name} {to_year.name}",
                })
                continue

            if dry_run:
                report['created'].append({
                    'name': src.name,
                    'term': target_term.name,
                    'line_items': src.line_items.count(),
                    'grades': list(src.get_covered_grades().values_list('name', flat=True)),
                })
            else:
                new = src.clone_to(
                    target_year=to_year,
                    target_term=target_term,
                    percentage_increase=percentage_increase,
                )
                report['created'].append({
                    'id': new.id,
                    'name': new.name,
                    'term': target_term.name,
                    'line_items': new.line_items.count(),
                    'grades': list(new.get_covered_grades().values_list('name', flat=True)),
                })

        return report

# ------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------

def models_Q_grade_or_band(grade):
    """Build a Q object that matches templates covering a grade (direct or via band)."""
    from django.db.models import Q
    return Q(grades=grade) | Q(grade_band__grades=grade)
