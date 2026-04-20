"""
Accounts Payable Serializers

Covers:
- Supplier management
- Supplier Invoices
- Payment Vouchers
- Imprest Retirement
- Approval Thresholds
"""

from rest_framework import serializers
from django.db import transaction
from decimal import Decimal

from .models import (
    Vendor, Bill, BillLine,  # Legacy
    Supplier, ApprovalThreshold, SupplierInvoice, SupplierInvoiceLine,
    PaymentVoucher, PaymentVoucherLine, VoucherApproval,
    ImprestRetirement, ImprestRetirementLine
)


# =============================================================================
# SUPPLIER SERIALIZERS
# =============================================================================

class SupplierListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    ap_account_name = serializers.CharField(source='ap_account.name', read_only=True)
    outstanding_balance = serializers.SerializerMethodField()
    
    class Meta:
        model = Supplier
        fields = [
            'id', 'code', 'name', 'kra_pin', 'vat_registered',
            'email', 'phone', 'payment_terms', 'is_active',
            'ap_account_name', 'outstanding_balance'
        ]
    
    def get_outstanding_balance(self, obj):
        """Calculate outstanding balance from posted invoices."""
        return obj.invoices.filter(status='POSTED').aggregate(
            total=serializers.models.Sum('balance')
        )['total'] or Decimal('0.00')


class SupplierDetailSerializer(serializers.ModelSerializer):
    """Full serializer for create/update/detail views."""
    ap_account_name = serializers.CharField(source='ap_account.name', read_only=True)
    
    class Meta:
        model = Supplier
        fields = '__all__'
        read_only_fields = ['code', 'created_at', 'updated_at']


# =============================================================================
# APPROVAL THRESHOLD SERIALIZERS
# =============================================================================

class ApprovalThresholdSerializer(serializers.ModelSerializer):
    """Serializer for approval threshold configuration."""
    
    class Meta:
        model = ApprovalThreshold
        fields = '__all__'
    
    def validate(self, data):
        if data.get('min_amount') and data.get('max_amount'):
            if data['min_amount'] >= data['max_amount']:
                raise serializers.ValidationError(
                    "min_amount must be less than max_amount"
                )
        return data


# =============================================================================
# SUPPLIER INVOICE SERIALIZERS
# =============================================================================

class SupplierInvoiceLineSerializer(serializers.ModelSerializer):
    """Serializer for invoice line items."""
    gl_account_name = serializers.CharField(source='gl_account.name', read_only=True)
    budget_line_name = serializers.CharField(source='budget_line.name', read_only=True, allow_null=True)
    vat_display = serializers.SerializerMethodField()
    # Override vat_rate to accept integer or decimal values
    vat_rate = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
    
    class Meta:
        model = SupplierInvoiceLine
        fields = [
            'id', 'description', 'quantity', 'unit_price', 'amount',
            'gl_account', 'gl_account_name', 'vat_rate', 'vat_display',
            'vat_amount', 'budget_line', 'budget_line_name'
        ]
        read_only_fields = ['amount', 'vat_amount']
    
    def validate_vat_rate(self, value):
        """Validate that VAT rate is one of the allowed values."""
        from decimal import Decimal
        allowed = [Decimal('0.00'), Decimal('8.00'), Decimal('16.00')]
        if value not in allowed:
            raise serializers.ValidationError(f"VAT rate must be one of: 0, 8, or 16")
        return value
    
    def get_vat_display(self, obj):
        return f"{int(obj.vat_rate)}%"


class SupplierInvoiceListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.get_full_name', read_only=True, allow_null=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    days_until_due = serializers.SerializerMethodField()
    
    class Meta:
        model = SupplierInvoice
        fields = [
            'id', 'invoice_number', 'supplier', 'supplier_name',
            'invoice_date', 'due_date', 'days_until_due',
            'subtotal', 'vat_amount', 'total_amount', 'balance',
            'status', 'status_display', 'source', 'approved_by_name', 'approved_at'
        ]
    
    def get_days_until_due(self, obj):
        if obj.due_date:
            from django.utils import timezone
            delta = obj.due_date - timezone.now().date()
            return delta.days
        return None


class SupplierInvoiceDetailSerializer(serializers.ModelSerializer):
    """Full serializer for create/update/detail views."""
    lines = SupplierInvoiceLineSerializer(many=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.get_full_name', read_only=True, allow_null=True)
    posted_by_name = serializers.CharField(source='posted_by.get_full_name', read_only=True, allow_null=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = SupplierInvoice
        fields = [
            'id', 'invoice_number', 'supplier', 'supplier_name',
            'invoice_date', 'due_date', 'source', 'purchase_order_ref',
            'subtotal', 'vat_amount', 'total_amount', 'balance',
            'status', 'status_display', 'notes', 'attachment',
            'approved_by', 'approved_by_name', 'approved_at',
            'posted_by', 'posted_by_name', 'posted_at',
            'journal_entry', 'created_at', 'updated_at', 'lines'
        ]
        read_only_fields = [
            'subtotal', 'vat_amount', 'total_amount', 'balance',
            'approved_by', 'approved_at', 'posted_by', 'posted_at',
            'journal_entry', 'created_at', 'updated_at'
        ]
    
    @transaction.atomic
    def create(self, validated_data):
        lines_data = validated_data.pop('lines')
        invoice = SupplierInvoice.objects.create(**validated_data)
        
        subtotal = Decimal('0.00')
        vat_total = Decimal('0.00')
        
        for line_data in lines_data:
            line = SupplierInvoiceLine.objects.create(invoice=invoice, **line_data)
            subtotal += line.amount
            vat_total += line.vat_amount
        
        invoice.subtotal = subtotal
        invoice.vat_amount = vat_total
        invoice.total_amount = subtotal + vat_total
        invoice.balance = invoice.total_amount
        invoice.save()
        
        return invoice
    
    @transaction.atomic
    def update(self, instance, validated_data):
        if instance.status not in ['DRAFT']:
            raise serializers.ValidationError("Only DRAFT invoices can be edited.")
        
        lines_data = validated_data.pop('lines', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        if lines_data is not None:
            instance.lines.all().delete()
            
            subtotal = Decimal('0.00')
            vat_total = Decimal('0.00')
            
            for line_data in lines_data:
                line = SupplierInvoiceLine.objects.create(invoice=instance, **line_data)
                subtotal += line.amount
                vat_total += line.vat_amount
            
            instance.subtotal = subtotal
            instance.vat_amount = vat_total
            instance.total_amount = subtotal + vat_total
            instance.balance = instance.total_amount
        
        instance.save()
        return instance


# =============================================================================
# PAYMENT VOUCHER SERIALIZERS
# =============================================================================

class VoucherApprovalSerializer(serializers.ModelSerializer):
    """Serializer for voucher approval history."""
    approver_name = serializers.CharField(source='approver.get_full_name', read_only=True)
    decision_display = serializers.CharField(source='get_decision_display', read_only=True)
    
    class Meta:
        model = VoucherApproval
        fields = [
            'id', 'approver', 'approver_name', 'role',
            'decision', 'decision_display', 'comments', 'created_at'
        ]
        read_only_fields = ['approver', 'created_at']


class PaymentVoucherLineSerializer(serializers.ModelSerializer):
    """Serializer for voucher line items."""
    gl_account_name = serializers.CharField(source='gl_account.name', read_only=True)
    budget_line_name = serializers.CharField(source='budget_line.name', read_only=True, allow_null=True)
    
    class Meta:
        model = PaymentVoucherLine
        fields = [
            'id', 'description', 'amount', 'gl_account', 'gl_account_name',
            'budget_line', 'budget_line_name'
        ]


class PaymentVoucherListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    payee_display = serializers.SerializerMethodField()
    prepared_by_name = serializers.CharField(source='prepared_by.get_full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    voucher_type_display = serializers.CharField(source='get_voucher_type_display', read_only=True)
    next_approval = serializers.CharField(source='next_approval_role', read_only=True)
    
    class Meta:
        model = PaymentVoucher
        fields = [
            'id', 'voucher_number', 'voucher_type', 'voucher_type_display',
            'payee_display', 'amount', 'payment_date',
            'status', 'status_display', 'next_approval',
            'prepared_by_name', 'created_at'
        ]
    
    def get_payee_display(self, obj):
        if obj.voucher_type == 'AP' and obj.supplier_invoice:
            return obj.supplier_invoice.supplier.name
        elif obj.voucher_type == 'IMPREST' and obj.staff_member:
            return obj.staff_member.get_full_name()
        elif obj.voucher_type == 'REFUND' and obj.payee_name:
            return obj.payee_name
        return obj.payee_name or 'N/A'


class PaymentVoucherDetailSerializer(serializers.ModelSerializer):
    """Full serializer for create/update/detail views."""
    lines = PaymentVoucherLineSerializer(many=True, required=False)
    approvals = VoucherApprovalSerializer(many=True, read_only=True)
    
    # Related object names
    supplier_invoice_number = serializers.CharField(
        source='supplier_invoice.invoice_number', read_only=True, allow_null=True
    )
    supplier_name = serializers.CharField(
        source='supplier_invoice.supplier.name', read_only=True, allow_null=True
    )
    staff_member_name = serializers.CharField(
        source='staff_member.get_full_name', read_only=True, allow_null=True
    )
    bank_account_name = serializers.CharField(
        source='bank_account.name', read_only=True, allow_null=True
    )
    imprest_account_name = serializers.CharField(
        source='imprest_account.name', read_only=True, allow_null=True
    )
    prepared_by_name = serializers.CharField(
        source='prepared_by.get_full_name', read_only=True
    )
    paid_by_name = serializers.CharField(
        source='paid_by.get_full_name', read_only=True, allow_null=True
    )
    
    # Status/display fields
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    voucher_type_display = serializers.CharField(source='get_voucher_type_display', read_only=True)
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)
    next_approval = serializers.CharField(source='next_approval_role', read_only=True)
    is_fully_approved = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = PaymentVoucher
        fields = [
            'id', 'voucher_number', 'voucher_type', 'voucher_type_display',
            'status', 'status_display', 'payment_date', 'amount', 'description',
            # AP-specific
            'supplier_invoice', 'supplier_invoice_number', 'supplier_name',
            # Imprest-specific
            'staff_member', 'staff_member_name', 'imprest_account', 'imprest_account_name',
            # Refund-specific
            'payee_name', 'refund_receipt', 'refund_reason',
            # Payment info
            'payment_method', 'payment_method_display', 'bank_account', 'bank_account_name',
            'cheque_number', 'payment_reference',
            # Approval
            'approval_chain', 'current_approval_step', 'next_approval', 'is_fully_approved',
            # Audit
            'prepared_by', 'prepared_by_name', 'paid_by', 'paid_by_name', 'paid_at',
            'journal_entry', 'notes', 'created_at', 'updated_at',
            # Nested
            'lines', 'approvals'
        ]
        read_only_fields = [
            'voucher_number', 'status', 'approval_chain', 'current_approval_step',
            'prepared_by', 'paid_by', 'paid_at', 'journal_entry',
            'created_at', 'updated_at'
        ]
    
    def validate(self, data):
        voucher_type = data.get('voucher_type')
        status = data.get('status', 'DRAFT')
        
        # Type-specific validations (required for non-draft vouchers)
        if voucher_type == 'AP':
            if not data.get('supplier_invoice'):
                raise serializers.ValidationError({
                    'supplier_invoice': 'Required for AP vouchers.'
                })
        
        elif voucher_type == 'IMPREST':
            if not data.get('staff_member'):
                raise serializers.ValidationError({
                    'staff_member': 'Required for IMPREST vouchers.'
                })
        
        elif voucher_type == 'GENERAL':
            # Lines are recommended but not strictly required for drafts
            pass
        
        elif voucher_type == 'REFUND':
            if not data.get('payee_name'):
                raise serializers.ValidationError({
                    'payee_name': 'Required for REFUND vouchers.'
                })
        
        return data


class VoucherApprovalActionSerializer(serializers.Serializer):
    """Serializer for approval actions."""
    decision = serializers.ChoiceField(choices=['APPROVED', 'REJECTED'])
    comments = serializers.CharField(required=False, allow_blank=True)


# =============================================================================
# IMPREST RETIREMENT SERIALIZERS
# =============================================================================

class ImprestRetirementLineSerializer(serializers.ModelSerializer):
    """Serializer for retirement line items."""
    gl_account_name = serializers.CharField(source='gl_account.name', read_only=True)
    
    class Meta:
        model = ImprestRetirementLine
        fields = [
            'id', 'description', 'amount', 'gl_account', 'gl_account_name',
            'receipt_number', 'receipt_date', 'receipt_attachment'
        ]


class ImprestRetirementListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    voucher_number = serializers.CharField(source='voucher.voucher_number', read_only=True)
    staff_member_name = serializers.CharField(
        source='voucher.staff_member.get_full_name', read_only=True
    )
    original_amount = serializers.DecimalField(
        source='voucher.amount', max_digits=14, decimal_places=2, read_only=True
    )
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = ImprestRetirement
        fields = [
            'id', 'voucher', 'voucher_number', 'staff_member_name',
            'retirement_date', 'original_amount', 'total_retired',
            'surrender_amount', 'status', 'status_display'
        ]


class ImprestRetirementDetailSerializer(serializers.ModelSerializer):
    """Full serializer for create/update/detail views."""
    lines = ImprestRetirementLineSerializer(many=True)
    voucher_number = serializers.CharField(source='voucher.voucher_number', read_only=True)
    staff_member_name = serializers.CharField(
        source='voucher.staff_member.get_full_name', read_only=True
    )
    original_amount = serializers.DecimalField(
        source='voucher.amount', max_digits=14, decimal_places=2, read_only=True
    )
    submitted_by_name = serializers.CharField(
        source='submitted_by.get_full_name', read_only=True, allow_null=True
    )
    approved_by_name = serializers.CharField(
        source='approved_by.get_full_name', read_only=True, allow_null=True
    )
    posted_by_name = serializers.CharField(
        source='posted_by.get_full_name', read_only=True, allow_null=True
    )
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    is_balanced = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = ImprestRetirement
        fields = [
            'id', 'voucher', 'voucher_number', 'staff_member_name',
            'retirement_date', 'original_amount', 'total_retired',
            'surrender_amount', 'is_balanced',
            'status', 'status_display', 'notes',
            'submitted_by', 'submitted_by_name', 'submitted_at',
            'approved_by', 'approved_by_name', 'approved_at',
            'posted_by', 'posted_by_name', 'posted_at',
            'journal_entry', 'lines'
        ]
        read_only_fields = [
            'total_retired', 'submitted_by', 'submitted_at',
            'approved_by', 'approved_at', 'posted_by', 'posted_at',
            'journal_entry'
        ]
    
    def validate(self, data):
        voucher = data.get('voucher')
        lines = data.get('lines', [])
        surrender = data.get('surrender_amount', Decimal('0.00'))
        
        if voucher:
            # Calculate total from lines
            total_retired = sum(line['amount'] for line in lines)
            
            # Validate balance
            if total_retired + surrender != voucher.amount:
                raise serializers.ValidationError(
                    f"Retirement does not balance. "
                    f"Retired: {total_retired}, Surrender: {surrender}, "
                    f"Expected: {voucher.amount}"
                )
        
        return data


# =============================================================================
# LEGACY SERIALIZERS (kept for backward compatibility)
# =============================================================================

class VendorSerializer(serializers.ModelSerializer):
    """Legacy Vendor serializer."""
    class Meta:
        model = Vendor
        fields = '__all__'


class BillLineSerializer(serializers.ModelSerializer):
    """Legacy BillLine serializer."""
    class Meta:
        model = BillLine
        fields = ['id', 'description', 'amount', 'expense_account']


class BillSerializer(serializers.ModelSerializer):
    """Legacy Bill serializer."""
    lines = BillLineSerializer(many=True)
    vendor_name = serializers.CharField(source='vendor.name', read_only=True)
    
    class Meta:
        model = Bill
        fields = [
            'id', 'vendor', 'vendor_name', 'bill_number', 'date_received', 
            'due_date', 'status', 'total_amount', 'notes', 'created_at', 'lines'
        ]
        read_only_fields = ['total_amount', 'created_at']

    def create(self, validated_data):
        lines_data = validated_data.pop('lines')
        bill = Bill.objects.create(**validated_data)
        
        total = 0
        for line_data in lines_data:
            total += line_data['amount']
            BillLine.objects.create(bill=bill, **line_data)
        
        bill.total_amount = total
        bill.save()
        return bill

    def update(self, instance, validated_data):
        lines_data = validated_data.pop('lines', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
            
        if lines_data is not None:
            instance.lines.all().delete()
            total = 0
            for line_data in lines_data:
                total += line_data['amount']
                BillLine.objects.create(bill=instance, **line_data)
            instance.total_amount = total
            
        instance.save()
        return instance
