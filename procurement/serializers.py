from rest_framework import serializers
from .models import (
    PurchaseRequisition, RequisitionLine,
    RequestForQuotation, RFQLine, RFQSupplierInvitation,
    SupplierQuotation, SupplierQuotationLine,
    PurchaseOrder, PurchaseOrderLine,
    SupplierContract, ContractMilestone,
)


# =============================================================================
# PURCHASE REQUISITION
# =============================================================================

class RequisitionLineSerializer(serializers.ModelSerializer):
    estimated_total = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    item_name = serializers.CharField(source='item.name', read_only=True, default=None)

    class Meta:
        model = RequisitionLine
        fields = [
            'id', 'item', 'item_name', 'description', 'specification',
            'quantity', 'unit_of_measure', 'estimated_unit_cost', 'estimated_total',
        ]


class PurchaseRequisitionListSerializer(serializers.ModelSerializer):
    requested_by_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()
    supplier_name = serializers.CharField(source='suggested_supplier.name', read_only=True, default=None)
    total_estimated_cost = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    line_count = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseRequisition
        fields = [
            'id', 'requisition_number', 'requested_by', 'requested_by_name',
            'department', 'date_needed', 'priority', 'status',
            'suggested_supplier', 'supplier_name', 'total_estimated_cost',
            'line_count', 'approved_by', 'approved_by_name', 'approved_at',
            'created_at', 'updated_at',
        ]

    def get_requested_by_name(self, obj):
        return obj.requested_by.get_full_name if obj.requested_by else None

    def get_approved_by_name(self, obj):
        return obj.approved_by.get_full_name if obj.approved_by else None

    def get_line_count(self, obj):
        return obj.lines.count()


class PurchaseRequisitionDetailSerializer(serializers.ModelSerializer):
    lines = RequisitionLineSerializer(many=True, read_only=True)
    requested_by_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()
    supplier_name = serializers.CharField(source='suggested_supplier.name', read_only=True, default=None)
    total_estimated_cost = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)

    class Meta:
        model = PurchaseRequisition
        fields = [
            'id', 'requisition_number', 'requested_by', 'requested_by_name',
            'department', 'date_needed', 'priority', 'status',
            'justification', 'suggested_supplier', 'supplier_name',
            'budget_line', 'approved_by', 'approved_by_name', 'approved_at',
            'rejection_reason', 'notes', 'total_estimated_cost',
            'lines', 'created_at', 'updated_at',
        ]

    def get_requested_by_name(self, obj):
        return obj.requested_by.get_full_name if obj.requested_by else None

    def get_approved_by_name(self, obj):
        return obj.approved_by.get_full_name if obj.approved_by else None


class PurchaseRequisitionCreateSerializer(serializers.ModelSerializer):
    lines = RequisitionLineSerializer(many=True, required=False)

    class Meta:
        model = PurchaseRequisition
        fields = [
            'department', 'date_needed', 'priority', 'justification',
            'suggested_supplier', 'budget_line', 'notes', 'lines',
        ]

    def create(self, validated_data):
        lines_data = validated_data.pop('lines', [])
        validated_data['requested_by'] = self.context['request'].user
        requisition = PurchaseRequisition.objects.create(**validated_data)
        for line_data in lines_data:
            RequisitionLine.objects.create(requisition=requisition, **line_data)
        return requisition

    def update(self, instance, validated_data):
        lines_data = validated_data.pop('lines', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if lines_data is not None:
            instance.lines.all().delete()
            for line_data in lines_data:
                RequisitionLine.objects.create(requisition=instance, **line_data)
        return instance


# =============================================================================
# RFQ
# =============================================================================

class RFQLineSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True, default=None)

    class Meta:
        model = RFQLine
        fields = [
            'id', 'item', 'item_name', 'description', 'specification',
            'quantity', 'unit_of_measure',
        ]


class RFQSupplierInvitationSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    supplier_email = serializers.CharField(source='supplier.email', read_only=True)
    public_url = serializers.CharField(read_only=True)
    has_quotation = serializers.SerializerMethodField()

    class Meta:
        model = RFQSupplierInvitation
        fields = [
            'id', 'supplier', 'supplier_name', 'supplier_email',
            'token', 'public_url', 'invited_at', 'viewed_at',
            'email_sent', 'has_quotation',
        ]
        read_only_fields = ['token', 'invited_at', 'viewed_at']

    def get_has_quotation(self, obj):
        return hasattr(obj, 'quotation')


class RFQListSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    requisition_number = serializers.CharField(
        source='requisition.requisition_number', read_only=True, default=None
    )
    supplier_count = serializers.SerializerMethodField()
    quotation_count = serializers.SerializerMethodField()

    class Meta:
        model = RequestForQuotation
        fields = [
            'id', 'rfq_number', 'title', 'status', 'deadline',
            'requisition', 'requisition_number',
            'supplier_count', 'quotation_count',
            'created_by', 'created_by_name', 'created_at',
        ]

    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name if obj.created_by else None

    def get_supplier_count(self, obj):
        return obj.invitations.count()

    def get_quotation_count(self, obj):
        return SupplierQuotation.objects.filter(invitation__rfq=obj).count()


class RFQDetailSerializer(serializers.ModelSerializer):
    lines = RFQLineSerializer(many=True, read_only=True)
    invitations = RFQSupplierInvitationSerializer(many=True, read_only=True)
    created_by_name = serializers.SerializerMethodField()
    requisition_number = serializers.CharField(
        source='requisition.requisition_number', read_only=True, default=None
    )

    class Meta:
        model = RequestForQuotation
        fields = [
            'id', 'rfq_number', 'title', 'description', 'status',
            'deadline', 'terms_and_conditions',
            'requisition', 'requisition_number',
            'lines', 'invitations',
            'created_by', 'created_by_name', 'created_at', 'updated_at',
        ]

    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name if obj.created_by else None


class RFQCreateSerializer(serializers.ModelSerializer):
    lines = RFQLineSerializer(many=True, required=False)
    supplier_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False
    )

    class Meta:
        model = RequestForQuotation
        fields = [
            'title', 'description', 'requisition', 'deadline',
            'terms_and_conditions', 'lines', 'supplier_ids',
        ]

    def create(self, validated_data):
        lines_data = validated_data.pop('lines', [])
        supplier_ids = validated_data.pop('supplier_ids', [])
        validated_data['created_by'] = self.context['request'].user
        rfq = RequestForQuotation.objects.create(**validated_data)
        for line_data in lines_data:
            RFQLine.objects.create(rfq=rfq, **line_data)
        for sid in supplier_ids:
            RFQSupplierInvitation.objects.create(rfq=rfq, supplier_id=sid)
        return rfq


# =============================================================================
# SUPPLIER QUOTATION
# =============================================================================

class SupplierQuotationLineSerializer(serializers.ModelSerializer):
    line_total = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    vat_amount = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    total_with_vat = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)

    class Meta:
        model = SupplierQuotationLine
        fields = [
            'id', 'rfq_line', 'description', 'quantity', 'unit_price',
            'vat_rate', 'line_total', 'vat_amount', 'total_with_vat',
        ]


class SupplierQuotationSerializer(serializers.ModelSerializer):
    lines = SupplierQuotationLineSerializer(many=True, read_only=True)
    supplier_name = serializers.SerializerMethodField()
    rfq_number = serializers.SerializerMethodField()

    class Meta:
        model = SupplierQuotation
        fields = [
            'id', 'invitation', 'quotation_reference', 'status',
            'total_amount', 'currency', 'validity_days',
            'delivery_period', 'payment_terms', 'notes', 'document',
            'supplier_name', 'rfq_number',
            'submitted_at', 'reviewed_at', 'reviewed_by',
            'lines',
        ]

    def get_supplier_name(self, obj):
        return obj.supplier.name

    def get_rfq_number(self, obj):
        return obj.rfq.rfq_number


class PublicQuotationSubmitSerializer(serializers.Serializer):
    """Used by the public quotation link — no auth required."""
    quotation_reference = serializers.CharField(required=False, allow_blank=True)
    delivery_period = serializers.CharField(required=False, allow_blank=True)
    payment_terms = serializers.CharField(required=False, allow_blank=True)
    validity_days = serializers.IntegerField(required=False, default=30)
    notes = serializers.CharField(required=False, allow_blank=True)
    document = serializers.FileField(required=False)
    lines = SupplierQuotationLineSerializer(many=True)

    def validate_lines(self, value):
        if not value:
            raise serializers.ValidationError("At least one line item is required.")
        return value


# =============================================================================
# PURCHASE ORDER
# =============================================================================

class PurchaseOrderLineSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True, default=None)
    line_total = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    vat_amount = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    total_with_vat = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    outstanding_quantity = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    is_fully_received = serializers.BooleanField(read_only=True)

    class Meta:
        model = PurchaseOrderLine
        fields = [
            'id', 'item', 'item_name', 'description', 'quantity',
            'unit_of_measure', 'unit_price', 'vat_rate',
            'quantity_received', 'outstanding_quantity', 'is_fully_received',
            'line_total', 'vat_amount', 'total_with_vat',
        ]


class PurchaseOrderListSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    created_by_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()
    receipt_percentage = serializers.FloatField(read_only=True)
    line_count = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrder
        fields = [
            'id', 'po_number', 'supplier', 'supplier_name', 'status',
            'order_date', 'expected_delivery_date',
            'total_amount', 'currency', 'receipt_percentage', 'line_count',
            'approved_by', 'approved_by_name', 'approved_at',
            'created_by', 'created_by_name', 'created_at',
        ]

    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name if obj.created_by else None

    def get_approved_by_name(self, obj):
        return obj.approved_by.get_full_name if obj.approved_by else None

    def get_line_count(self, obj):
        return obj.lines.count()


class PurchaseOrderDetailSerializer(serializers.ModelSerializer):
    lines = PurchaseOrderLineSerializer(many=True, read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    created_by_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()
    requisition_number = serializers.CharField(
        source='requisition.requisition_number', read_only=True, default=None
    )
    rfq_number = serializers.CharField(
        source='rfq.rfq_number', read_only=True, default=None
    )
    contract_number = serializers.CharField(
        source='contract.contract_number', read_only=True, default=None
    )
    receipt_percentage = serializers.FloatField(read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = [
            'id', 'po_number', 'supplier', 'supplier_name', 'status',
            'order_date', 'expected_delivery_date', 'delivery_address',
            'currency', 'subtotal', 'vat_amount', 'total_amount',
            'payment_terms', 'budget_line',
            'requisition', 'requisition_number',
            'rfq', 'rfq_number',
            'quotation', 'contract', 'contract_number',
            'receipt_percentage',
            'approved_by', 'approved_by_name', 'approved_at',
            'notes', 'lines',
            'created_by', 'created_by_name', 'created_at', 'updated_at',
        ]

    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name if obj.created_by else None

    def get_approved_by_name(self, obj):
        return obj.approved_by.get_full_name if obj.approved_by else None


class PurchaseOrderCreateSerializer(serializers.ModelSerializer):
    lines = PurchaseOrderLineSerializer(many=True, required=False)

    class Meta:
        model = PurchaseOrder
        fields = [
            'supplier', 'requisition', 'rfq', 'quotation', 'contract',
            'order_date', 'expected_delivery_date', 'delivery_address',
            'currency', 'payment_terms', 'budget_line', 'notes', 'lines',
        ]

    def create(self, validated_data):
        lines_data = validated_data.pop('lines', [])
        validated_data['created_by'] = self.context['request'].user
        po = PurchaseOrder.objects.create(**validated_data)
        for line_data in lines_data:
            line_data.pop('item_name', None)
            PurchaseOrderLine.objects.create(purchase_order=po, **line_data)
        po.recalculate_totals()
        return po

    def update(self, instance, validated_data):
        lines_data = validated_data.pop('lines', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if lines_data is not None:
            instance.lines.all().delete()
            for line_data in lines_data:
                line_data.pop('item_name', None)
                PurchaseOrderLine.objects.create(purchase_order=instance, **line_data)
            instance.recalculate_totals()
        return instance


# =============================================================================
# SUPPLIER CONTRACT
# =============================================================================

class ContractMilestoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractMilestone
        fields = [
            'id', 'title', 'description', 'due_date', 'amount',
            'status', 'completed_at',
        ]


class SupplierContractListSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    days_remaining = serializers.IntegerField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    needs_renewal_reminder = serializers.BooleanField(read_only=True)

    class Meta:
        model = SupplierContract
        fields = [
            'id', 'contract_number', 'title', 'supplier', 'supplier_name',
            'contract_type', 'status', 'start_date', 'end_date',
            'contract_value', 'currency',
            'days_remaining', 'is_expired', 'needs_renewal_reminder',
            'created_at',
        ]


class SupplierContractDetailSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    milestones = ContractMilestoneSerializer(many=True, read_only=True)
    days_remaining = serializers.IntegerField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    needs_renewal_reminder = serializers.BooleanField(read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = SupplierContract
        fields = [
            'id', 'contract_number', 'title', 'supplier', 'supplier_name',
            'contract_type', 'status', 'start_date', 'end_date',
            'contract_value', 'currency',
            'terms_and_conditions', 'description', 'document',
            'renewal_reminder_days', 'days_remaining',
            'is_expired', 'needs_renewal_reminder',
            'milestones',
            'created_by', 'created_by_name', 'created_at', 'updated_at',
        ]

    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name if obj.created_by else None


class SupplierContractCreateSerializer(serializers.ModelSerializer):
    milestones = ContractMilestoneSerializer(many=True, required=False)

    class Meta:
        model = SupplierContract
        fields = [
            'title', 'supplier', 'contract_type', 'start_date', 'end_date',
            'contract_value', 'currency', 'terms_and_conditions',
            'description', 'document', 'renewal_reminder_days', 'milestones',
        ]

    def create(self, validated_data):
        milestones_data = validated_data.pop('milestones', [])
        validated_data['created_by'] = self.context['request'].user
        contract = SupplierContract.objects.create(**validated_data)
        for m_data in milestones_data:
            ContractMilestone.objects.create(contract=contract, **m_data)
        return contract

    def update(self, instance, validated_data):
        milestones_data = validated_data.pop('milestones', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if milestones_data is not None:
            instance.milestones.all().delete()
            for m_data in milestones_data:
                ContractMilestone.objects.create(contract=instance, **m_data)
        return instance
