"""
Budget Views

API ViewSets for budget management and budget-vs-actual reporting.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum
from decimal import Decimal

from .models import Budget, BudgetLine
from .serializers import (
    BudgetListSerializer, BudgetDetailSerializer, BudgetLineSerializer
)


class BudgetViewSet(viewsets.ModelViewSet):
    queryset = Budget.objects.prefetch_related('lines', 'lines__account').all()
    permission_classes = [IsAuthenticated]
    ordering = ['-fiscal_year']

    def get_serializer_class(self):
        if self.action == 'list':
            return BudgetListSerializer
        return BudgetDetailSerializer

    @action(detail=True, methods=['get'])
    def budget_vs_actual(self, request, pk=None):
        """Budget vs Actual report for a specific budget."""
        budget = self.get_object()
        lines = budget.lines.select_related('account').all()
        serializer = BudgetLineSerializer(lines, many=True)

        total_budget = sum(line.amount for line in lines)
        total_spent = Decimal('0.00')
        line_data = serializer.data
        for ld in line_data:
            total_spent += Decimal(ld['spent'])

        return Response({
            'budget': {
                'id': budget.id,
                'name': budget.name,
                'fiscal_year': budget.fiscal_year,
            },
            'total_budget': str(total_budget),
            'total_spent': str(total_spent),
            'total_remaining': str(total_budget - total_spent),
            'utilization': str(
                (total_spent / total_budget * 100).quantize(Decimal('0.01'))
                if total_budget > 0 else Decimal('0.00')
            ),
            'lines': line_data
        })


class BudgetLineViewSet(viewsets.ModelViewSet):
    """Direct access to budget lines (for dropdowns in invoice/voucher forms)."""
    queryset = BudgetLine.objects.select_related('budget', 'account').filter(budget__is_active=True)
    serializer_class = BudgetLineSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # Small dataset for dropdowns
