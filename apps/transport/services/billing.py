from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import math

def round_to_nearest_50(amount):
    """Round to nearest 50 KES."""
    return Decimal(math.ceil(amount / 50.0)) * 50

class TransportBillingService:
    @staticmethod
    @transaction.atomic
    def generate_term_charges(academic_year_id, term_id, route_ids=None, due_date=None, enable_prorating=True, user=None):
        """
        Generate transport fee charges for all active assignments in the given term/year.
        """
        from apps.transport.models import StudentAssignment, FeeCharge, FeeStructure
        from apps.fees.models import FeeInvoice, FeeInvoiceItem, VoteHead
        from apps.academics.models import StudentSessionEnrollment
        from apps.finance.models import FinanceSettings
        from apps.journals.services import JournalService

        if not due_date:
            due_date = timezone.now().date() + timedelta(days=14)

        # 1. Resolve or auto-create TRANSPORT VoteHead
        votehead, _ = VoteHead.objects.get_or_create(
            code='TRANSPORT',
            defaults={
                'name': 'Transport Fee',
                'is_optional': True,
                'frequency': 'RECURRING',
                'description': 'Auto-generated Transport Fee VoteHead',
                'default_account': FinanceSettings.load().default_income_account  # fallback
            }
        )

        if not votehead.default_account:
            # Try to get a default income account
            fin_settings = FinanceSettings.load()
            if fin_settings.default_income_account:
                votehead.default_account = fin_settings.default_income_account
                votehead.save()

        # 2. Get active assignments
        query = StudentAssignment.objects.filter(
            is_active=True
        ).select_related('student', 'route', 'stop')
        
        if route_ids:
            query = query.filter(route_id__in=route_ids)
            
        assignments = query.all()

        processed_count = 0
        total_charged = Decimal('0.00')
        pro_rated_count = 0
        skipped_duplicates = 0
        full_term_count = 0

        # Term length calculation for pro-rating
        # Assuming Term model has start_date and end_date
        # We will fetch the Term from first matching FeeStructure or directly
        from apps.student_settings.models import Term
        term = Term.objects.get(id=term_id)
        
        total_term_days = (term.end_date - term.start_date).days if term.end_date and term.start_date else 90
        week_2_threshold = term.start_date + timedelta(days=14) if term.start_date else timezone.now().date()

        for assignment in assignments:
            # Check duplicate
            if FeeCharge.objects.filter(
                assignment=assignment,
                academic_year_id=academic_year_id,
                term_id=term_id
            ).exists():
                skipped_duplicates += 1
                continue

            # Resolve FeeStructure
            structure = FeeStructure.objects.filter(
                route=assignment.route,
                academic_year_id=academic_year_id,
                term_id=term_id
            ).first()

            if not structure:
                continue # Skip if no fee structure defined for this route in this term
                
            # Determine base amount based on fee_model
            base_amount = Decimal('0.00')
            if assignment.route.fee_model == 'flat_per_route':
                fs = FeeStructure.objects.filter(route=assignment.route, academic_year_id=academic_year_id, term_id=term_id, fee_type='flat').first()
                if fs: base_amount = fs.amount
            elif assignment.route.fee_model == 'per_zone':
                fs = FeeStructure.objects.filter(route=assignment.route, academic_year_id=academic_year_id, term_id=term_id, fee_type=f"{assignment.stop.zone}_zone").first()
                if fs: base_amount = fs.amount
            elif assignment.route.fee_model == 'one_way_two_way':
                fee_type_to_fetch = 'one_way' if assignment.transport_type in ['morning_only', 'evening_only'] else 'two_way'
                fs = FeeStructure.objects.filter(route=assignment.route, academic_year_id=academic_year_id, term_id=term_id, fee_type=fee_type_to_fetch).first()
                if fs: base_amount = fs.amount

            if base_amount <= 0:
                continue # Nothing to charge

            # Pro-rating
            final_amount = base_amount
            is_prorated = False
            if enable_prorating and assignment.start_date > week_2_threshold and term.end_date:
                days_remaining = (term.end_date - assignment.start_date).days
                if days_remaining > 0 and total_term_days > 0:
                    pro_rated_amount = base_amount * Decimal(days_remaining) / Decimal(total_term_days)
                    final_amount = round_to_nearest_50(pro_rated_amount)
                    is_prorated = True
                    pro_rated_count += 1
                else:
                    final_amount = Decimal('0.00')
            else:
                full_term_count += 1

            if final_amount <= 0:
                continue

            description = f"Transport — {assignment.route.route_name} ({assignment.stop.stop_name})"

            # Try to attach to existing FeeInvoice for the student in this term
            enrollment = StudentSessionEnrollment.objects.filter(
                student=assignment.student,
                session__term_id=term_id,
                session__academic_year_id=academic_year_id
            ).first()

            invoice = None
            if enrollment:
                invoice = FeeInvoice.objects.filter(
                    student_enrollment=enrollment
                ).exclude(status='VOID').first()

            if not invoice and enrollment:
                # Create a new invoice just for transport
                # Use a unique sequence number or simple string
                import uuid
                invoice = FeeInvoice.objects.create(
                    student_enrollment=enrollment,
                    student=assignment.student,
                    class_session=enrollment.session,
                    term_id=term_id,
                    academic_year_id=academic_year_id,
                    due_date=due_date,
                    status='SENT',
                    invoice_number=f"TRN-{term_id}-{uuid.uuid4().hex[:6].upper()}",
                    total_amount=0,
                    balance=0
                )

            # Create the charge record
            charge = FeeCharge.objects.create(
                student=assignment.student,
                assignment=assignment,
                academic_year_id=academic_year_id,
                term_id=term_id,
                amount_charged=final_amount,
                fee_label=description,
                linked_to_main_fee_ledger=bool(invoice)
            )

            if invoice:
                # Add line item
                FeeInvoiceItem.objects.create(
                    invoice=invoice,
                    vote_head=votehead,
                    description=description,
                    amount=final_amount,
                    is_optional=True
                )
                
                # Update invoice totals
                invoice.total_amount += final_amount
                invoice.balance += final_amount
                # Ensure status isn't PAID if there's now a balance
                if invoice.balance > 0 and invoice.status == 'PAID':
                    invoice.status = 'PARTIALLY_PAID'
                invoice.save()

                # Post Journal Entry for the Transport Add-on
                settings = FinanceSettings.load()
                receivable_acc = settings.default_receivable_account
                income_acc = votehead.default_account

                if receivable_acc and income_acc:
                    journal_data = {
                        'date': timezone.now().date(),
                        'reference': f"TRN-{charge.id}-{invoice.invoice_number}",
                        'description': f"Transport Fee Add-on for {assignment.student}",
                        'journal_type': 'SALES',
                        'status': 'DRAFT',
                        'lines': [
                            {
                                'account': receivable_acc,
                                'debit': final_amount,
                                'credit': 0,
                                'description': f"Transport Add-on {invoice.invoice_number}"
                            },
                            {
                                'account': income_acc,
                                'debit': 0,
                                'credit': final_amount,
                                'description': description
                            }
                        ]
                    }
                    try:
                        entry = JournalService.create_journal_entry(journal_data, user=user)
                        JournalService.post_journal_entry(entry)
                    except Exception as e:
                        # Fallback or log if needed, but we raise to rollback atomic transaction
                        raise Exception(f"Failed to post transport journal entry: {e}")

            processed_count += 1
            total_charged += final_amount

        return {
            "total_processed": processed_count,
            "total_charged": str(total_charged),
            "pro_rated_count": pro_rated_count,
            "full_term_count": full_term_count,
            "skipped_duplicates": skipped_duplicates
        }
