"""
Service for creating journal entries from receipts.
Handles automatic double-entry bookkeeping when receipts are posted.
"""

from django.db import transaction
from django.core.exceptions import ValidationError
from decimal import Decimal
from journals.services import JournalService


class ReceiptJournalService:
    """Service to create journal entries from posted receipts"""
    
    @staticmethod
    @transaction.atomic
    def create_receipt_journal_entry(receipt, user=None):
        """
        Create and post a journal entry for a receipt.
        
        Journal Entry Structure:
        - Debit: Cash/Bank Account (from payment method)
        - Credit: Revenue Account(s) (from fee items or income account)
        
        Args:
            receipt: Receipt instance
            user: User creating the journal entry (optional)
            
        Returns:
            JournalEntry instance
        """
        from journals.models import JournalEntry, JournalLine
        from fees.models import FeeItem
        
        # Validate receipt
        if receipt.status not in ['POSTED', 'ISSUED']:
            raise ValidationError(f"Cannot create journal entry for receipt with status: {receipt.status}")
        
        # Get the cash/bank account from payment method
        cash_account = receipt.payment_method.account
        if not cash_account:
            raise ValidationError(f"Payment method '{receipt.payment_method.name}' does not have an associated account.")
        
        # Create journal entry
        journal_data = {
            'date': receipt.received_date,
            'reference': f"Receipt {receipt.receipt_number}",
            'description': f"Receipt from {receipt.payer_name} - {receipt.get_receipt_type_display()}",
            'journal_type': 'CASH_RECEIPT',
        }
        
        if user:
            journal_data['created_by'] = user
        
        # Build journal lines
        lines_data = []
        total_credit = Decimal('0.00')
        
        # Handle different receipt types
        if receipt.receipt_type in ['STUDENT_FEE', 'STUDENT_NON_FEE']:
            # For student receipts, we credit Student Debtors (Accounts Receivable)
            # and Prepayments (for any unallocated surplus)
            
            # Get accounts from FinanceSettings
            from finance.models import FinanceSettings
            settings = FinanceSettings.load()
            
            # Validate required accounts are configured
            if not settings.default_receivable_account:
                raise ValidationError(
                    "Student Debtors account not configured in Finance Settings. "
                    "Please configure the Default Receivable Account."
                )
            
            student_debtors_account = settings.default_receivable_account
            
            # Calculate allocated vs prepayment amounts
            allocated_amount = receipt.amount_allocated or Decimal('0.00')
            prepayment_amount = receipt.amount_received - allocated_amount
            
            # Credit Student Debtors for the allocated portion (payment against invoices)
            if allocated_amount > 0:
                # Get student name safely
                student_name = 'Student'
                if receipt.student and hasattr(receipt.student, 'student'):
                    student_obj = receipt.student.student
                    if hasattr(student_obj, 'get_full_name'):
                        get_full_name_attr = getattr(student_obj, 'get_full_name')
                        if callable(get_full_name_attr):
                            # It's a method
                            student_name = get_full_name_attr()
                        else:
                            # It's a property/string
                            student_name = get_full_name_attr
                    elif hasattr(student_obj, 'full_name'):
                        # It's a property
                        student_name = student_obj.full_name
                    
                lines_data.append({
                    'account': student_debtors_account,
                    'description': f"Payment from {student_name} - Invoice allocation",
                    'debit': Decimal('0.00'),
                    'credit': allocated_amount,
                })
                total_credit += allocated_amount
            
            # Credit Prepayments for any surplus/overpayment
            if prepayment_amount > 0:
                if not settings.default_prepayment_account:
                    raise ValidationError(
                        "Prepayment account not configured in Finance Settings. "
                        "Please configure the Default Prepayment Account."
                    )
                
                prepayment_account = settings.default_prepayment_account
                
                # Get student name safely (reuse if already computed)
                student_name = 'Student'
                if receipt.student and hasattr(receipt.student, 'student'):
                    student_obj = receipt.student.student
                    if hasattr(student_obj, 'get_full_name'):
                        get_full_name_attr = getattr(student_obj, 'get_full_name')
                        if callable(get_full_name_attr):
                            student_name = get_full_name_attr()
                        else:
                            student_name = get_full_name_attr
                    elif hasattr(student_obj, 'full_name'):
                        student_name = student_obj.full_name
                
                lines_data.append({
                    'account': prepayment_account,
                    'description': f"Prepayment/Unallocated credit - {student_name}",
                    'debit': Decimal('0.00'),
                    'credit': prepayment_amount,
                })
                total_credit += prepayment_amount
            
            # Note: 
            # 1. Revenue was already recognized when invoice was created
            # 2. Allocated payments reduce Accounts Receivable
            # 3. Prepayments are liabilities until applied to future invoices
            # 4. The allocation records (ReceiptAllocation) track the detailed breakdown
        
        elif receipt.receipt_type == 'GENERAL':
            # Use the income_account specified in the receipt
            if not receipt.income_account:
                raise ValidationError("General receipt must have an income account specified.")
            
            lines_data.append({
                'account': receipt.income_account,
                'description': receipt.description or "General income",
                'debit': Decimal('0.00'),
                'credit': receipt.amount_received,
            })
            total_credit = receipt.amount_received
        
        elif receipt.receipt_type == 'SPONSOR':
            # Credit the clearing account of the sponsor type
            if not receipt.sponsorship:
                raise ValidationError("Sponsor receipt must be linked to a sponsorship program.")
                
            clearing_account = receipt.sponsorship.sponsor_type.clearing_account
            if not clearing_account:
                raise ValidationError(
                    f"Clearing account not configured for sponsor type '{receipt.sponsorship.sponsor_type.name}'."
                )
            
            lines_data.append({
                'account': clearing_account,
                'description': f"Sponsorship fund receipt - {receipt.sponsorship.name} ({receipt.sponsorship.sponsor_type.name})",
                'debit': Decimal('0.00'),
                'credit': receipt.amount_received,
            })
            total_credit = receipt.amount_received
        
        # Add debit line: either cash/bank, or the clearing account if allocated from a sponsor receipt
        if receipt.parent_receipt:
            if not receipt.parent_receipt.sponsorship:
                raise ValidationError("Parent sponsor receipt is not linked to a sponsorship program.")
            
            debit_account = receipt.parent_receipt.sponsorship.sponsor_type.clearing_account
            debit_desc = f"Allocation from Sponsor Receipt {receipt.parent_receipt.receipt_number}"
        else:
            debit_account = cash_account
            debit_desc = f"Receipt via {receipt.payment_method.name}"
            
        lines_data.insert(0, {
            'account': debit_account,
            'description': debit_desc,
            'debit': receipt.amount_received,
            'credit': Decimal('0.00'),
        })
        
        # Validate totals match
        if total_credit != receipt.amount_received:
            raise ValidationError(
                f"Journal entry unbalanced. Receipt amount: {receipt.amount_received}, "
                f"Total credits: {total_credit}"
            )
        
        # Create the journal entry with lines
        journal_entry = JournalService.create_journal_entry(
            data=journal_data,
            user=user
        )
        
        # Add lines
        for line_data in lines_data:
            JournalLine.objects.create(entry=journal_entry, **line_data)
        
        # Post the journal entry immediately
        JournalService.post_journal_entry(journal_entry)
        
        return journal_entry
