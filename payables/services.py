"""
Accounts Payable Services Layer

Handles business logic for:
- Supplier Invoice posting (accrual accounting)
- Payment Voucher creation, approval, and posting
- Imprest retirement

All operations use atomic transactions for data integrity.
Journal entries are created via JournalService.
"""

from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal

from .models import (
    Supplier, SupplierInvoice, SupplierInvoiceLine,
    PaymentVoucher, PaymentVoucherLine, VoucherApproval,
    ImprestRetirement, ImprestRetirementLine, ApprovalThreshold
)
from finance.models import Account, AccountSubType, FinanceSettings
from journals.services import JournalService


# =============================================================================
# SECTION 5.1: SUPPLIER INVOICE SERVICE
# =============================================================================

class SupplierInvoiceService:
    """
    Handles supplier invoice lifecycle including posting to journals.
    """
    
    @staticmethod
    @transaction.atomic
    def approve_invoice(invoice: SupplierInvoice, user) -> SupplierInvoice:
        """
        Approve a draft supplier invoice.
        """
        if invoice.status != 'DRAFT':
            raise ValidationError("Only DRAFT invoices can be approved.")
        
        if not invoice.lines.exists():
            raise ValidationError("Invoice has no line items.")
        
        invoice.status = 'APPROVED'
        invoice.approved_by = user
        invoice.approved_at = timezone.now()
        invoice.save()
        
        return invoice
    
    @staticmethod
    @transaction.atomic
    def post_invoice(invoice: SupplierInvoice, user) -> SupplierInvoice:
        """
        Posts an approved supplier invoice to the General Ledger.
        
        Creates accrual journal entry:
        DR: Expense/Asset accounts (per line)
        DR: VAT Input account (total VAT, if applicable)
        CR: Supplier's AP account (total amount)
        
        Args:
            invoice: SupplierInvoice with status=APPROVED
            user: User performing the posting
            
        Returns:
            Posted SupplierInvoice with linked journal entry
            
        Raises:
            ValidationError: If invoice cannot be posted
        """
        # Validate status
        if invoice.status != 'APPROVED':
            raise ValidationError("Only APPROVED invoices can be posted.")
        
        # Validate lines exist
        lines = invoice.lines.select_related('gl_account').all()
        if not lines.exists():
            raise ValidationError("Invoice has no line items.")
        
        # Get finance settings for VAT account
        settings = FinanceSettings.load()
        
        # Get VAT Input account if VAT enabled
        vat_account = None
        if settings.vat_enabled and invoice.vat_amount > 0:
            vat_account = Account.objects.filter(
                sub_type=AccountSubType.TAX_PAYABLE,  # VAT receivable/input
                is_active=True,
                children__isnull=True
            ).first()
        
        # Build journal entry data
        journal_data = {
            'date': invoice.invoice_date,
            'description': f"Supplier Invoice: {invoice.supplier.name} - {invoice.invoice_number}",
            'journal_type': 'PURCHASE',
            'reference': f"SINV-{invoice.id}",
            'lines': []
        }
        
        # Debit expense/asset accounts (per line)
        for line in lines:
            if line.amount > 0:
                journal_data['lines'].append({
                    'account': line.gl_account,
                    'debit': line.amount,
                    'credit': Decimal('0.00'),
                    'description': line.description
                })
        
        # Debit VAT input account (total VAT)
        if vat_account and invoice.vat_amount > 0:
            journal_data['lines'].append({
                'account': vat_account,
                'debit': invoice.vat_amount,
                'credit': Decimal('0.00'),
                'description': f"VAT on {invoice.invoice_number}"
            })
        
        # Credit supplier's AP account (total) — fallback to FinanceSettings default
        ap_account = invoice.supplier.ap_account
        if not ap_account:
            ap_account = settings.default_payable_account
        if not ap_account:
            ap_account = Account.objects.filter(
                sub_type=AccountSubType.ACCOUNTS_PAYABLE,
                is_active=True,
                children__isnull=True
            ).first()
        if not ap_account:
            raise ValidationError(
                "No Trade Payables account found. "
                "Set the supplier's AP account or configure a default in Finance Settings."
            )
        journal_data['lines'].append({
            'account': ap_account,
            'debit': Decimal('0.00'),
            'credit': invoice.total_amount,
            'description': f"Payable to {invoice.supplier.name}"
        })
        
        # Create and post journal entry
        entry = JournalService.create_journal_entry(journal_data, user=user)
        JournalService.post_journal_entry(entry)
        
        # Update invoice status
        invoice.status = 'POSTED'
        invoice.journal_entry = entry
        invoice.posted_by = user
        invoice.posted_at = timezone.now()
        invoice.save()
        
        return invoice
    
    @staticmethod
    @transaction.atomic
    def void_invoice(invoice: SupplierInvoice, user, reason: str) -> SupplierInvoice:
        """
        Void a supplier invoice (only DRAFT or APPROVED).
        Posted invoices require reversal journal instead.
        """
        if invoice.status in ['PAID', 'VOID']:
            raise ValidationError(f"Cannot void invoice with status {invoice.status}")
        
        if invoice.status == 'POSTED':
            raise ValidationError("Posted invoices cannot be voided. Create a reversal entry instead.")
        
        invoice.status = 'VOID'
        invoice.notes = f"{invoice.notes or ''}\n\nVOIDED by {user.get_full_name()} on {timezone.now()}: {reason}"
        invoice.save()
        
        return invoice


# =============================================================================
# SECTION 5.2: PAYMENT VOUCHER SERVICE
# =============================================================================

class PaymentVoucherService:
    """
    Handles payment voucher lifecycle including approval workflow and journal posting.
    """
    
    @staticmethod
    @transaction.atomic
    def create_voucher(data: dict, user) -> PaymentVoucher:
        """
        Creates a payment voucher with proper validation and approval chain setup.
        
        Args:
            data: Dictionary with voucher fields and optional 'lines' for GENERAL/IMPREST types
            user: User creating the voucher
            
        Returns:
            Created PaymentVoucher
        """
        lines_data = data.pop('lines', [])
        
        # Determine approval chain from threshold before creating voucher
        amount = data.get('amount', 0)
        voucher_type = data.get('voucher_type')
        threshold = ApprovalThreshold.get_threshold_for_amount(amount, voucher_type)
        
        if threshold and threshold.required_roles:
            data['approval_chain'] = threshold.required_roles
            data['status'] = 'PENDING_APPROVAL'
        else:
            # No approval required, go straight to approved
            data['approval_chain'] = []
            data['status'] = 'APPROVED'
        
        # Create voucher
        voucher = PaymentVoucher(
            prepared_by=user,
            **data
        )
        
        # Full clean validation
        voucher.full_clean()
        voucher.save()
        
        # Create lines for GENERAL and IMPREST types
        if voucher.voucher_type in ['GENERAL', 'IMPREST'] and lines_data:
            for line_data in lines_data:
                # Convert gl_account ID to gl_account_id for FK assignment
                if 'gl_account' in line_data and isinstance(line_data['gl_account'], int):
                    line_data['gl_account_id'] = line_data.pop('gl_account')
                PaymentVoucherLine.objects.create(voucher=voucher, **line_data)
        
        return voucher
    
    @staticmethod
    @transaction.atomic
    def process_approval(
        voucher: PaymentVoucher, 
        approver, 
        decision: str, 
        comments: str = None
    ) -> PaymentVoucher:
        """
        Process an approval decision on a voucher.
        
        Args:
            voucher: PaymentVoucher to approve
            approver: User making the decision
            decision: 'APPROVED' or 'REJECTED'
            comments: Optional approval comments
            
        Returns:
            Updated PaymentVoucher
            
        Raises:
            ValidationError: If approval is invalid
        """
        if voucher.status != 'PENDING_APPROVAL':
            raise ValidationError("Voucher is not pending approval.")
        
        # Get expected role
        expected_role = voucher.next_approval_role
        if not expected_role:
            raise ValidationError("No pending approval step.")
        
        # Validate approver has the required role
        # This assumes user has a 'groups' or 'role' attribute
        # Adjust based on your user model
        user_roles = [g.name.upper() for g in approver.groups.all()]
        if expected_role.upper() not in user_roles:
            raise ValidationError(
                f"You do not have the required role ({expected_role}) to approve this voucher."
            )
        
        # Record approval
        VoucherApproval.objects.create(
            voucher=voucher,
            approver=approver,
            role=expected_role,
            decision=decision,
            comments=comments
        )
        
        if decision == 'APPROVED':
            voucher.current_approval_step += 1
            
            # Check if all approvals complete
            if voucher.is_fully_approved:
                voucher.status = 'APPROVED'
            
            voucher.save()
        else:
            # Rejection - revert to draft
            voucher.status = 'DRAFT'
            voucher.current_approval_step = 0
            voucher.approval_chain = []  # Reset chain
            voucher.notes = f"{voucher.notes or ''}\n\nREJECTED by {approver.get_full_name()} ({expected_role}): {comments or 'No reason given'}"
            voucher.save()
        
        return voucher
    
    @staticmethod
    @transaction.atomic
    def post_payment(voucher: PaymentVoucher, user) -> PaymentVoucher:
        """
        Posts a payment voucher to the General Ledger.
        
        Journal entries by type:
        - AP:      DR AP Account / CR Bank
        - GENERAL: DR Expense lines / CR Bank
        - IMPREST: DR Imprest Account / CR Bank
        - REFUND:  DR Income or Liability / CR Bank
        
        Args:
            voucher: Approved PaymentVoucher
            user: User performing the payment
            
        Returns:
            Paid PaymentVoucher with journal entry
        """
        if voucher.status != 'APPROVED':
            raise ValidationError("Only APPROVED vouchers can be paid.")
        
        # Get bank/cash account from payment method
        if not voucher.bank_account.account:
            raise ValidationError("Payment method has no linked GL account.")
        
        bank_account = voucher.bank_account.account
        
        # Build journal based on voucher type
        journal_data = {
            'date': voucher.payment_date,
            'description': f"Payment Voucher: {voucher.voucher_number}",
            'journal_type': 'CASH_PAYMENT',
            'reference': voucher.voucher_number,
            'lines': []
        }
        
        if voucher.voucher_type == 'AP':
            # AP Payment: DR AP Account / CR Bank
            journal_data['lines'] = PaymentVoucherService._build_ap_journal_lines(
                voucher, bank_account
            )
            
        elif voucher.voucher_type == 'GENERAL':
            # General Payment: DR Expense lines / CR Bank
            journal_data['lines'] = PaymentVoucherService._build_general_journal_lines(
                voucher, bank_account
            )
            
        elif voucher.voucher_type == 'IMPREST':
            # Imprest: DR Imprest Account / CR Bank
            journal_data['lines'] = PaymentVoucherService._build_imprest_journal_lines(
                voucher, bank_account
            )
            
        elif voucher.voucher_type == 'REFUND':
            # Refund: DR Income/Liability / CR Bank
            journal_data['lines'] = PaymentVoucherService._build_refund_journal_lines(
                voucher, bank_account
            )
        
        # Create and post journal
        entry = JournalService.create_journal_entry(journal_data, user=user)
        JournalService.post_journal_entry(entry)
        
        # Update voucher
        voucher.status = 'PAID'
        voucher.journal_entry = entry
        voucher.paid_by = user
        voucher.paid_at = timezone.now()
        voucher.save()
        
        # If AP voucher, update linked supplier invoice
        if voucher.voucher_type == 'AP' and voucher.supplier_invoice:
            invoice = voucher.supplier_invoice
            invoice.balance = invoice.balance - voucher.amount
            if invoice.balance <= 0:
                invoice.status = 'PAID'
            invoice.save()
        
        return voucher
    
    @staticmethod
    def _build_ap_journal_lines(voucher: PaymentVoucher, bank_account) -> list:
        """Build journal lines for AP payment."""
        invoice = voucher.supplier_invoice
        
        return [
            {
                'account': invoice.supplier.ap_account,
                'debit': voucher.amount,
                'credit': Decimal('0.00'),
                'description': f"Payment to {invoice.supplier.name}"
            },
            {
                'account': bank_account,
                'debit': Decimal('0.00'),
                'credit': voucher.amount,
                'description': f"Payment via {voucher.get_payment_method_display()}"
            }
        ]
    
    @staticmethod
    def _build_general_journal_lines(voucher: PaymentVoucher, bank_account) -> list:
        """Build journal lines for general payment."""
        lines = []
        
        # Debit expense accounts from voucher lines
        for line in voucher.lines.select_related('gl_account').all():
            lines.append({
                'account': line.gl_account,
                'debit': line.amount,
                'credit': Decimal('0.00'),
                'description': line.description
            })
        
        # Credit bank account
        lines.append({
            'account': bank_account,
            'debit': Decimal('0.00'),
            'credit': voucher.amount,
            'description': f"Payment to {voucher.payee_name}"
        })
        
        return lines
    
    @staticmethod
    def _build_imprest_journal_lines(voucher: PaymentVoucher, bank_account) -> list:
        """Build journal lines for imprest issuance."""
        return [
            {
                'account': voucher.imprest_account,
                'debit': voucher.amount,
                'credit': Decimal('0.00'),
                'description': f"Imprest to {voucher.staff_member.get_full_name()}"
            },
            {
                'account': bank_account,
                'debit': Decimal('0.00'),
                'credit': voucher.amount,
                'description': f"Imprest via {voucher.get_payment_method_display()}"
            }
        ]
    
    @staticmethod
    def _build_refund_journal_lines(voucher: PaymentVoucher, bank_account) -> list:
        """Build journal lines for refund."""
        settings = FinanceSettings.load()
        
        # Determine account to debit based on refund context
        # If from receipt, use the income/liability account
        # Otherwise use prepayment account
        if voucher.refund_receipt:
            # Get account from receipt allocation
            debit_account = settings.default_receivable_account or settings.default_prepayment_account
        else:
            debit_account = settings.default_prepayment_account
        
        if not debit_account:
            raise ValidationError("No refund account configured in Finance Settings.")
        
        return [
            {
                'account': debit_account,
                'debit': voucher.amount,
                'credit': Decimal('0.00'),
                'description': f"Refund to {voucher.payee_name}"
            },
            {
                'account': bank_account,
                'debit': Decimal('0.00'),
                'credit': voucher.amount,
                'description': f"Refund via {voucher.get_payment_method_display()}"
            }
        ]
    
    @staticmethod
    @transaction.atomic
    def void_voucher(voucher: PaymentVoucher, user, reason: str) -> PaymentVoucher:
        """
        Void a payment voucher (only DRAFT, PENDING_APPROVAL, or APPROVED).
        """
        if voucher.status in ['PAID', 'VOID']:
            raise ValidationError(f"Cannot void voucher with status {voucher.status}")
        
        voucher.status = 'VOID'
        voucher.notes = f"{voucher.notes or ''}\n\nVOIDED by {user.get_full_name()} on {timezone.now()}: {reason}"
        voucher.save()
        
        return voucher


# =============================================================================
# SECTION 5.3: IMPREST SERVICE
# =============================================================================

class ImprestService:
    """
    Handles imprest retirement workflow.
    """
    
    @staticmethod
    @transaction.atomic
    def submit_retirement(
        voucher: PaymentVoucher, 
        retirement_data: dict, 
        user
    ) -> ImprestRetirement:
        """
        Create and submit imprest retirement.
        
        Args:
            voucher: IMPREST PaymentVoucher with status=PAID
            retirement_data: Dict with retirement_date, surrender_amount, notes, and lines
            user: User submitting
            
        Returns:
            Created ImprestRetirement
        """
        # Validate voucher
        if voucher.voucher_type != 'IMPREST':
            raise ValidationError("Can only retire IMPREST vouchers.")
        
        if voucher.status != 'PAID':
            raise ValidationError("Imprest must be PAID before retirement.")
        
        # Check if already retired
        if hasattr(voucher, 'retirement'):
            raise ValidationError("This imprest has already been retired.")
        
        lines_data = retirement_data.pop('lines', [])
        
        # Create retirement
        retirement = ImprestRetirement.objects.create(
            voucher=voucher,
            status='SUBMITTED',
            submitted_by=user,
            submitted_at=timezone.now(),
            **retirement_data
        )
        
        # Create lines
        for line_data in lines_data:
            ImprestRetirementLine.objects.create(retirement=retirement, **line_data)
        
        # Validate balance
        if not retirement.is_balanced:
            raise ValidationError(
                f"Retirement does not balance. "
                f"Retired: {retirement.total_retired}, "
                f"Surrender: {retirement.surrender_amount}, "
                f"Original: {voucher.amount}"
            )
        
        return retirement
    
    @staticmethod
    @transaction.atomic
    def approve_retirement(retirement: ImprestRetirement, user) -> ImprestRetirement:
        """Approve a submitted retirement."""
        if retirement.status != 'SUBMITTED':
            raise ValidationError("Only SUBMITTED retirements can be approved.")
        
        retirement.status = 'APPROVED'
        retirement.approved_by = user
        retirement.approved_at = timezone.now()
        retirement.save()
        
        return retirement
    
    @staticmethod
    @transaction.atomic
    def post_retirement(retirement: ImprestRetirement, user) -> ImprestRetirement:
        """
        Post imprest retirement to GL.
        
        Journal:
        DR: Expense accounts (per retirement lines)
        DR: Cash account (surrender amount, if > 0)
        CR: Imprest Account (total voucher amount)
        """
        if retirement.status != 'APPROVED':
            raise ValidationError("Only APPROVED retirements can be posted.")
        
        voucher = retirement.voucher
        settings = FinanceSettings.load()
        
        # Build journal
        journal_data = {
            'date': retirement.retirement_date,
            'description': f"Imprest Retirement: {voucher.voucher_number}",
            'journal_type': 'GENERAL',
            'reference': f"RET-{voucher.voucher_number}",
            'lines': []
        }
        
        # Debit expense accounts (per line)
        for line in retirement.lines.select_related('gl_account').all():
            journal_data['lines'].append({
                'account': line.gl_account,
                'debit': line.amount,
                'credit': Decimal('0.00'),
                'description': f"{line.description} (Receipt: {line.receipt_number or 'N/A'})"
            })
        
        # Debit cash account for surrender (if any)
        if retirement.surrender_amount > 0:
            # Get cash account
            cash_account = Account.objects.filter(
                sub_type=AccountSubType.CASH,
                is_active=True,
                children__isnull=True
            ).first()
            
            if not cash_account:
                raise ValidationError("No cash account found for surrender.")
            
            journal_data['lines'].append({
                'account': cash_account,
                'debit': retirement.surrender_amount,
                'credit': Decimal('0.00'),
                'description': "Cash surrender from imprest"
            })
        
        # Credit imprest account (total original amount)
        journal_data['lines'].append({
            'account': voucher.imprest_account,
            'debit': Decimal('0.00'),
            'credit': voucher.amount,
            'description': f"Retirement of imprest {voucher.voucher_number}"
        })
        
        # Create and post journal
        entry = JournalService.create_journal_entry(journal_data, user=user)
        JournalService.post_journal_entry(entry)
        
        # Update retirement
        retirement.status = 'POSTED'
        retirement.journal_entry = entry
        retirement.posted_by = user
        retirement.posted_at = timezone.now()
        retirement.save()
        
        return retirement


# =============================================================================
# LEGACY SERVICE (kept for backward compatibility)
# =============================================================================

class PayablesService:
    """Legacy service - use SupplierInvoiceService instead."""
    
    @staticmethod
    @transaction.atomic
    def post_bill(bill, user=None):
        """Legacy method for posting old Bill model."""
        from .models import Bill
        from finance.models import Account, AccountSubType, FinanceSettings
        
        if bill.status != 'DRAFT':
            raise ValidationError("Only DRAFT bills can be posted.")
            
        if not bill.lines.exists():
            raise ValidationError("Bill has no lines.")
        
        # Resolve AP account: FinanceSettings default → fallback query
        settings = FinanceSettings.load()
        ap_account = settings.default_payable_account
        if not ap_account:
            ap_account = Account.objects.filter(
                sub_type=AccountSubType.ACCOUNTS_PAYABLE, 
                is_active=True,
                children__isnull=True
            ).first()
        
        if not ap_account:
            raise ValidationError("No active Accounts Payable account found.")
            
        journal_data = {
            'date': bill.date_received,
            'description': f"Bill #{bill.bill_number} - {bill.vendor.name}",
            'journal_type': 'PURCHASE',
            'reference': bill.bill_number,
            'lines': []
        }
        
        total_expense = 0
        
        for line in bill.lines.all():
            journal_data['lines'].append({
                'account': line.expense_account,
                'debit': line.amount,
                'credit': 0,
                'description': line.description
            })
            total_expense += line.amount
            
        journal_data['lines'].append({
            'account': ap_account,
            'debit': 0,
            'credit': total_expense,
            'description': f"Payable for Bill #{bill.bill_number}"
        })
        
        entry = JournalService.create_journal_entry(journal_data, user=user)
        JournalService.post_journal_entry(entry)
        
        bill.status = 'RECEIVED'
        bill.journal_entry = entry
        bill.save()
        
        return bill

