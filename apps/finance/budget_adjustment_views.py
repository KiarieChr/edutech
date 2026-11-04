from decimal import Decimal
import datetime
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from core.campus_filter import get_request_campus_id
from budgets.models import Budget, BudgetAdjustmentHistory
from finance.services.budget_adjustment_service import BudgetAdjustmentService


class BudgetAdjustmentPreviewView(APIView):
    """
    GET /api/finance/budgeting/adjustments/preview/
    Calculates what the budget would look like if the R factor were applied.
    No changes are saved to the database.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        now = timezone.now()
        year_param = request.query_params.get('fiscal_year') or request.query_params.get('year')
        try:
            fiscal_year = int(year_param) if year_param else now.year
        except (ValueError, TypeError):
            fiscal_year = now.year

        campus_id = get_request_campus_id(request)
        budget_id = request.query_params.get('budget_id')

        budget = None
        if budget_id:
            try:
                budget = Budget.objects.get(id=budget_id)
            except Budget.DoesNotExist:
                pass

        if not budget:
            budget = BudgetAdjustmentService.get_budget_for_scope(fiscal_year, campus_id)

        if not budget:
            return Response({
                'success': False,
                'error': f'No active budget found for fiscal year {fiscal_year}.'
            }, status=status.HTTP_404_NOT_FOUND)

        override_param = request.query_params.get('override_factor')
        override_factor = None
        if override_param is not None and override_param != '':
            try:
                override_factor = Decimal(str(override_param))
            except Exception:
                pass

        try:
            calculation = BudgetAdjustmentService.calculate_adjustment(
                budget=budget,
                override_factor=override_factor
            )
            return Response({
                'success': True,
                'preview': calculation,
            })
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Adjustment calculation failed: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BudgetAdjustmentApplyView(APIView):
    """
    POST /api/finance/budgeting/adjustments/apply/
    Officially applies the calculated adjustment factor to the budget:
    - Modifies controlled_budget on lines (preserves original_budget)
    - Updates adjustment_factor and status on Budget
    - Records entry in BudgetAdjustmentHistory
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        now = timezone.now()
        data = request.data or {}

        budget_id = data.get('budget_id')
        year_param = data.get('fiscal_year') or data.get('year')
        campus_id = data.get('campus_id') or get_request_campus_id(request)

        budget = None
        if budget_id:
            try:
                budget = Budget.objects.get(id=budget_id)
            except Budget.DoesNotExist:
                pass

        if not budget:
            try:
                fiscal_year = int(year_param) if year_param else now.year
            except (ValueError, TypeError):
                fiscal_year = now.year
            budget = BudgetAdjustmentService.get_budget_for_scope(fiscal_year, campus_id)

        if not budget:
            return Response({
                'success': False,
                'error': 'Target budget could not be located.'
            }, status=status.HTTP_404_NOT_FOUND)

        override_val = data.get('override_factor')
        override_factor = None
        if override_val is not None and override_val != '':
            try:
                override_factor = Decimal(str(override_val))
            except Exception:
                pass

        reason = data.get('reason') or data.get('trigger_reason') or 'Routine automatic income shortfall alignment'

        try:
            result = BudgetAdjustmentService.apply_adjustment(
                budget=budget,
                user=request.user,
                reason=reason,
                override_factor=override_factor
            )
            return Response(result, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Failed to apply budget adjustment: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BudgetAdjustmentHistoryView(APIView):
    """
    GET /api/finance/budgeting/adjustments/history/
    Returns the audit trail of automatic and overridden adjustments.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        budget_id = request.query_params.get('budget_id')
        year_param = request.query_params.get('fiscal_year') or request.query_params.get('year')
        campus_id = get_request_campus_id(request)

        qs = BudgetAdjustmentHistory.objects.select_related('budget', 'approved_by').all()

        if budget_id:
            qs = qs.filter(budget_id=budget_id)
        elif year_param:
            try:
                qs = qs.filter(budget__fiscal_year=int(year_param))
            except (ValueError, TypeError):
                pass

        if campus_id and campus_id not in ['all', 'undefined', 'null']:
            qs = qs.filter(budget__campus_id=campus_id)

        records = []
        for h in qs[:50]:
            user_display = None
            if h.approved_by:
                fn = getattr(h.approved_by, 'get_full_name', None)
                if callable(fn):
                    user_display = fn()
                else:
                    user_display = str(fn) if fn else getattr(h.approved_by, 'username', 'Finance User')

            records.append({
                'id': h.id,
                'budget_id': h.budget_id,
                'budget_name': h.budget.name if h.budget else '',
                'fiscal_year': h.budget.fiscal_year if h.budget else None,
                'campus_name': h.budget.campus.name if (h.budget and h.budget.campus) else 'All Campuses',
                'previous_factor': float(h.previous_factor),
                'new_factor': float(h.new_factor),
                'trigger_reason': h.trigger_reason,
                'projected_income': str(h.projected_income),
                'actual_income': str(h.actual_income),
                'total_budget_before': str(h.total_budget_before),
                'total_budget_after': str(h.total_budget_after),
                'total_reduction': str(h.total_reduction),
                'calculated_at': h.calculated_at.isoformat(),
                'approved_by': user_display or 'System Automation',
            })

        return Response({
            'success': True,
            'count': len(records),
            'history': records,
        })
