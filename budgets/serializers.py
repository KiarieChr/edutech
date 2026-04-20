"""
Budget Serializers

Covers:
- Budget CRUD with nested budget lines
- BudgetLine with computed spent/remaining fields
"""

from rest_framework import serializers
from django.db import transaction
from django.db.models import Sum
from decimal import Decimal

from .models import Budget, BudgetLine


class BudgetLineSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source='account.code', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)
    account_type = serializers.CharField(source='account.type', read_only=True)
    spent = serializers.SerializerMethodField()
    remaining = serializers.SerializerMethodField()
    utilization = serializers.SerializerMethodField()

    class Meta:
        model = BudgetLine
        fields = [
            'id', 'account', 'account_code', 'account_name', 'account_type',
            'amount', 'spent', 'remaining', 'utilization'
        ]

    def _get_spent(self, obj):
        """Aggregate spending from supplier invoices, payment vouchers, and supply issues."""
        total = Decimal('0.00')

        # Supplier invoice lines (POSTED invoices)
        inv_spent = obj.supplier_invoice_lines.filter(
            invoice__status='POSTED'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        total += inv_spent

        # Payment voucher lines (POSTED vouchers)
        pv_spent = obj.payment_voucher_lines.filter(
            voucher__status='POSTED'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        total += pv_spent

        # Supply issue items (ISSUED)
        issue_spent = obj.supply_issues.filter(
            status='ISSUED'
        ).aggregate(total=Sum('total_value'))['total'] or Decimal('0.00')
        total += issue_spent

        return total

    def get_spent(self, obj):
        return str(self._get_spent(obj))

    def get_remaining(self, obj):
        return str(obj.amount - self._get_spent(obj))

    def get_utilization(self, obj):
        if obj.amount == 0:
            return '0.00'
        return str((self._get_spent(obj) / obj.amount * 100).quantize(Decimal('0.01')))


class BudgetListSerializer(serializers.ModelSerializer):
    line_count = serializers.SerializerMethodField()
    total_budget = serializers.SerializerMethodField()
    total_spent = serializers.SerializerMethodField()

    class Meta:
        model = Budget
        fields = [
            'id', 'name', 'fiscal_year', 'start_date', 'end_date',
            'description', 'is_active', 'line_count',
            'total_budget', 'total_spent', 'created_at'
        ]

    def get_line_count(self, obj):
        return obj.lines.count()

    def get_total_budget(self, obj):
        return str(obj.lines.aggregate(total=Sum('amount'))['total'] or Decimal('0.00'))

    def get_total_spent(self, obj):
        total = Decimal('0.00')
        for line in obj.lines.all():
            total += BudgetLineSerializer()._get_spent(line)
        return str(total)


class BudgetDetailSerializer(serializers.ModelSerializer):
    lines = BudgetLineSerializer(many=True)

    class Meta:
        model = Budget
        fields = [
            'id', 'name', 'fiscal_year', 'start_date', 'end_date',
            'description', 'is_active', 'created_at', 'lines'
        ]

    @transaction.atomic
    def create(self, validated_data):
        lines_data = validated_data.pop('lines')
        budget = Budget.objects.create(**validated_data)
        for line_data in lines_data:
            BudgetLine.objects.create(budget=budget, **line_data)
        return budget

    @transaction.atomic
    def update(self, instance, validated_data):
        lines_data = validated_data.pop('lines', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if lines_data is not None:
            instance.lines.all().delete()
            for line_data in lines_data:
                BudgetLine.objects.create(budget=instance, **line_data)
        return instance
