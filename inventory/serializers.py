"""
Inventory Serializers

Covers:
- Category CRUD
- Inventory Item CRUD with stats
- Stock Movement (read-only)
- GRN with nested lines
- Supply Issue with nested items
- Stock Take with nested lines
"""

from rest_framework import serializers
from django.db import transaction
from decimal import Decimal

from .models import (
    Category, InventoryItem, StockMovement,
    GoodsReceivedNote, GRNLine,
    SupplyIssue, SupplyIssueItem,
    StockTake, StockTakeLine
)


# =============================================================================
# CATEGORY
# =============================================================================

class CategorySerializer(serializers.ModelSerializer):
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            'id', 'code', 'name', 'description', 'parent',
            'gl_expense_account', 'is_active', 'item_count', 'created_at'
        ]

    def get_item_count(self, obj):
        return obj.items.count()


# =============================================================================
# INVENTORY ITEM
# =============================================================================

class InventoryItemListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    category_name = serializers.CharField(source='category.name', read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True, allow_null=True)
    stock_value = serializers.DecimalField(max_digits=20, decimal_places=2, read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = InventoryItem
        fields = [
            'id', 'code', 'name', 'category', 'category_name',
            'item_type', 'unit_of_measure', 'unit_cost',
            'stock_quantity', 'min_level', 'location',
            'supplier', 'supplier_name',
            'batch_number', 'expiry_date', 'status',
            'stock_value', 'is_low_stock', 'is_expired'
        ]


class InventoryItemDetailSerializer(serializers.ModelSerializer):
    """Full serializer for create/update/detail views."""
    category_name = serializers.CharField(source='category.name', read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True, allow_null=True)
    gl_asset_account_name = serializers.CharField(source='gl_asset_account.name', read_only=True, allow_null=True)
    gl_expense_account_name = serializers.CharField(source='gl_expense_account.name', read_only=True, allow_null=True)
    stock_value = serializers.DecimalField(max_digits=20, decimal_places=2, read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = InventoryItem
        fields = [
            'id', 'code', 'name', 'category', 'category_name',
            'item_type', 'unit_of_measure',
            'unit_cost', 'stock_quantity', 'min_level', 'reorder_quantity',
            'location', 'batch_number', 'barcode', 'expiry_date',
            'supplier', 'supplier_name',
            'gl_asset_account', 'gl_asset_account_name',
            'gl_expense_account', 'gl_expense_account_name',
            'status', 'notes',
            'stock_value', 'is_low_stock', 'is_expired',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['code', 'created_at', 'updated_at']

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


# =============================================================================
# STOCK MOVEMENT (Read-only)
# =============================================================================

class StockMovementSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    item_code = serializers.CharField(source='item.code', read_only=True)
    movement_type_display = serializers.CharField(source='get_movement_type_display', read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = StockMovement
        fields = [
            'id', 'item', 'item_name', 'item_code',
            'movement_type', 'movement_type_display',
            'quantity', 'unit_cost', 'total_cost', 'balance_after',
            'reference_number', 'reason', 'journal_entry',
            'created_at', 'created_by', 'created_by_name'
        ]

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return None


# =============================================================================
# STOCK ADJUSTMENT (Write)
# =============================================================================

class StockAdjustmentSerializer(serializers.Serializer):
    """Input serializer for stock adjustment action."""
    adjustment_type = serializers.ChoiceField(choices=['INCREASE', 'DECREASE'])
    quantity = serializers.DecimalField(max_digits=15, decimal_places=2, min_value=Decimal('0.01'))
    reason = serializers.CharField(max_length=500)
    post_to_gl = serializers.BooleanField(default=False, required=False)


# =============================================================================
# GRN (Goods Received Note)
# =============================================================================

class GRNLineSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    item_code = serializers.CharField(source='item.code', read_only=True)

    class Meta:
        model = GRNLine
        fields = [
            'id', 'item', 'item_name', 'item_code',
            'quantity_ordered', 'quantity_received', 'unit_cost', 'total_cost'
        ]
        read_only_fields = ['total_cost']


class GRNListSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    line_count = serializers.SerializerMethodField()
    total_value = serializers.SerializerMethodField()

    class Meta:
        model = GoodsReceivedNote
        fields = [
            'id', 'grn_number', 'supplier', 'supplier_name',
            'received_date', 'status', 'status_display',
            'line_count', 'total_value', 'created_at'
        ]

    def get_line_count(self, obj):
        return obj.lines.count()

    def get_total_value(self, obj):
        return sum(line.total_cost for line in obj.lines.all())


class GRNDetailSerializer(serializers.ModelSerializer):
    lines = GRNLineSerializer(many=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = GoodsReceivedNote
        fields = [
            'id', 'grn_number', 'supplier', 'supplier_name',
            'supplier_invoice', 'received_date', 'received_by',
            'status', 'status_display', 'notes', 'journal_entry',
            'created_at', 'updated_at', 'lines'
        ]
        read_only_fields = ['grn_number', 'journal_entry', 'created_at', 'updated_at']

    @transaction.atomic
    def create(self, validated_data):
        lines_data = validated_data.pop('lines')
        grn = GoodsReceivedNote.objects.create(**validated_data)
        for line_data in lines_data:
            GRNLine.objects.create(grn=grn, **line_data)
        return grn

    @transaction.atomic
    def update(self, instance, validated_data):
        if instance.status != 'DRAFT':
            raise serializers.ValidationError("Only DRAFT GRNs can be edited.")
        lines_data = validated_data.pop('lines', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if lines_data is not None:
            instance.lines.all().delete()
            for line_data in lines_data:
                GRNLine.objects.create(grn=instance, **line_data)
        return instance


# =============================================================================
# SUPPLY ISSUE
# =============================================================================

class SupplyIssueItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    item_code = serializers.CharField(source='item.code', read_only=True)
    available_stock = serializers.SerializerMethodField()

    class Meta:
        model = SupplyIssueItem
        fields = [
            'id', 'item', 'item_name', 'item_code',
            'quantity_requested', 'quantity_issued',
            'unit_cost', 'total', 'available_stock'
        ]
        read_only_fields = ['total']

    def get_available_stock(self, obj):
        return obj.item.stock_quantity


class SupplyIssueListSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    approved_by_name = serializers.SerializerMethodField()
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = SupplyIssue
        fields = [
            'id', 'issue_number', 'department', 'requested_by',
            'approved_by', 'approved_by_name', 'issue_date',
            'status', 'status_display', 'total_value',
            'item_count', 'created_at'
        ]

    def get_approved_by_name(self, obj):
        if obj.approved_by:
            return obj.approved_by.get_full_name() or obj.approved_by.username
        return None

    def get_item_count(self, obj):
        return obj.items.count()


class SupplyIssueDetailSerializer(serializers.ModelSerializer):
    items = SupplyIssueItemSerializer(many=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    approved_by_name = serializers.SerializerMethodField()

    class Meta:
        model = SupplyIssue
        fields = [
            'id', 'issue_number', 'department', 'requested_by',
            'approved_by', 'approved_by_name', 'issue_date',
            'status', 'status_display', 'total_value',
            'budget_line', 'notes', 'journal_entry',
            'created_at', 'updated_at', 'items'
        ]
        read_only_fields = [
            'issue_number', 'total_value', 'approved_by',
            'journal_entry', 'created_at', 'updated_at'
        ]

    def get_approved_by_name(self, obj):
        if obj.approved_by:
            return obj.approved_by.get_full_name() or obj.approved_by.username
        return None

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        issue = SupplyIssue.objects.create(**validated_data)
        total = Decimal('0.00')
        for item_data in items_data:
            si = SupplyIssueItem.objects.create(issue=issue, **item_data)
            total += si.total
        issue.total_value = total
        issue.save()
        return issue

    @transaction.atomic
    def update(self, instance, validated_data):
        if instance.status not in ['PENDING']:
            raise serializers.ValidationError("Only PENDING issues can be edited.")
        items_data = validated_data.pop('items', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if items_data is not None:
            instance.items.all().delete()
            total = Decimal('0.00')
            for item_data in items_data:
                si = SupplyIssueItem.objects.create(issue=instance, **item_data)
                total += si.total
            instance.total_value = total
            instance.save()
        return instance


# =============================================================================
# STOCK TAKE
# =============================================================================

class StockTakeLineSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    item_code = serializers.CharField(source='item.code', read_only=True)

    class Meta:
        model = StockTakeLine
        fields = [
            'id', 'item', 'item_name', 'item_code',
            'system_quantity', 'physical_quantity', 'variance', 'variance_reason'
        ]
        read_only_fields = ['variance']


class StockTakeListSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    conducted_by_name = serializers.SerializerMethodField()
    line_count = serializers.SerializerMethodField()

    class Meta:
        model = StockTake
        fields = [
            'id', 'reference', 'date', 'status', 'status_display',
            'conducted_by', 'conducted_by_name', 'line_count', 'created_at'
        ]

    def get_conducted_by_name(self, obj):
        if obj.conducted_by:
            return obj.conducted_by.get_full_name() or obj.conducted_by.username
        return None

    def get_line_count(self, obj):
        return obj.lines.count()


class StockTakeDetailSerializer(serializers.ModelSerializer):
    lines = StockTakeLineSerializer(many=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    conducted_by_name = serializers.SerializerMethodField()

    class Meta:
        model = StockTake
        fields = [
            'id', 'reference', 'date', 'status', 'status_display',
            'conducted_by', 'conducted_by_name', 'notes',
            'created_at', 'updated_at', 'lines'
        ]
        read_only_fields = ['reference', 'created_at', 'updated_at']

    def get_conducted_by_name(self, obj):
        if obj.conducted_by:
            return obj.conducted_by.get_full_name() or obj.conducted_by.username
        return None

    @transaction.atomic
    def create(self, validated_data):
        lines_data = validated_data.pop('lines')
        stock_take = StockTake.objects.create(**validated_data)
        for line_data in lines_data:
            # Auto-fill system_quantity from current stock
            item = line_data['item']
            line_data['system_quantity'] = item.stock_quantity
            StockTakeLine.objects.create(stock_take=stock_take, **line_data)
        return stock_take

    @transaction.atomic
    def update(self, instance, validated_data):
        if instance.status == 'COMPLETED':
            raise serializers.ValidationError("Completed stock takes cannot be edited.")
        lines_data = validated_data.pop('lines', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if lines_data is not None:
            instance.lines.all().delete()
            for line_data in lines_data:
                item = line_data['item']
                line_data['system_quantity'] = item.stock_quantity
                StockTakeLine.objects.create(stock_take=instance, **line_data)
        return instance
