from decimal import Decimal
import datetime
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, BasePermission

from core.campus_filter import get_request_campus_id
from budgets.models import (
    Budget,
    BudgetLine,
    BudgetStatus,
    BudgetAdjustmentStatus,
    BudgetAdjustmentHistory,
    BudgetAuditAction,
    BudgetAuditLog,
)
from budgets.audit import log_budget_action
from finance.services.budget_adjustment_service import BudgetAdjustmentService


class CanApproveBudgetAdjustmentPermission(BasePermission):
    """
    Ensures user has executive authorization to ratify budget adjustments and austerity reductions.
    Allows superusers, staff administrators, or users granted 'finance.can_approve_budget_adjustment'.
    """
    message = "You do not have permission to approve budget adjustments (finance.can_approve_budget_adjustment required)."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser or request.user.is_staff:
            return True
        return request.user.has_perm('finance.can_approve_budget_adjustment')


class BudgetPlanningApproveView(APIView):
    """
    POST /api/finance/budgeting/planning/{id}/approve/
    POST /api/finance/budgeting/planning/approve/
    Transitions budget status from 'pending_approval' to 'approved'.
    Finalizes BudgetLine allocations: proposed_budget becomes original_budget and controlled_budget.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk=None):
        budget_id = pk or request.data.get('budget_id') or request.data.get('id')
        year = request.data.get('fiscal_year') or request.data.get('year')

        budget = None
        if budget_id:
            budget = Budget.objects.filter(id=budget_id).first()
        elif year:
            budget = Budget.objects.filter(fiscal_year=int(year), status=BudgetStatus.PENDING_APPROVAL).first()

        if not budget:
            return Response({'error': 'Budget not found.'}, status=status.HTTP_404_NOT_FOUND)

        if budget.status == BudgetStatus.APPROVED:
            return Response({'error': 'Budget is already approved.'}, status=status.HTTP_400_BAD_REQUEST)

        prev_status = budget.status
        budget.status = BudgetStatus.APPROVED
        budget.save()

        # Finalize lines: lock proposed_budget into original_budget & controlled_budget
        updated_lines = 0
        lines_snapshot = []
        for line in budget.lines.select_related('account').all():
            # If line amount is set, lock it
            line.original_budget = line.amount
            line.controlled_budget = line.amount
            line.save()
            updated_lines += 1
            lines_snapshot.append({
                'account_code': line.account.code if line.account else '',
                'account_name': line.account.name if line.account else '',
                'approved_amount': str(line.amount),
            })

        # Audit Log
        log_budget_action(
            budget=budget,
            user=request.user,
            action=BudgetAuditAction.APPROVED,
            previous_state=prev_status,
            new_state=BudgetStatus.APPROVED,
            details={
                'notes': request.data.get('notes', 'Ratified and approved by financial authority.'),
                'lines_count': updated_lines,
                'total_approved': str(sum(l.amount for l in budget.lines.all())),
            },
            request=request
        )

        return Response({
            'success': True,
            'message': f"Budget '{budget.name}' successfully ratified and approved.",
            'budget': {
                'id': budget.id,
                'name': budget.name,
                'fiscal_year': budget.fiscal_year,
                'status': budget.status,
                'lines_count': updated_lines,
            }
        })


class BudgetPlanningRejectView(APIView):
    """
    POST /api/finance/budgeting/planning/{id}/reject/
    POST /api/finance/budgeting/planning/reject/
    Rejects a pending budget, reverting status to 'draft' or 'rejected' with reason notes.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk=None):
        budget_id = pk or request.data.get('budget_id') or request.data.get('id')
        reason = request.data.get('reason') or request.data.get('notes') or 'Returned for revision.'

        budget = None
        if budget_id:
            budget = Budget.objects.filter(id=budget_id).first()

        if not budget:
            return Response({'error': 'Budget not found.'}, status=status.HTTP_404_NOT_FOUND)

        prev_status = budget.status
        budget.status = BudgetStatus.REJECTED
        budget.save()

        # Audit Log
        log_budget_action(
            budget=budget,
            user=request.user,
            action=BudgetAuditAction.REJECTED,
            previous_state=prev_status,
            new_state=BudgetStatus.REJECTED,
            details={'rejection_reason': reason},
            request=request
        )

        return Response({
            'success': True,
            'message': f"Budget '{budget.name}' rejected and returned for revision.",
            'budget': {
                'id': budget.id,
                'name': budget.name,
                'status': budget.status,
            }
        })


class BudgetAdjustmentApproveView(APIView):
    """
    POST /api/finance/budgeting/adjustments/{id}/approve/
    POST /api/finance/budgeting/adjustments/approve/
    Finalizes a pending automatic budget adjustment or shortfall reduction.
    """
    permission_classes = [IsAuthenticated, CanApproveBudgetAdjustmentPermission]

    def post(self, request, pk=None):
        item_id = pk or request.data.get('adjustment_id') or request.data.get('id')
        notes = request.data.get('notes') or 'Adjustment approved by finance manager.'

        # Check if item_id refers to BudgetAdjustmentHistory or Budget
        history = None
        budget = None

        if item_id:
            history = BudgetAdjustmentHistory.objects.filter(id=item_id).first()
            if history:
                budget = history.budget
            else:
                budget = Budget.objects.filter(id=item_id).first()

        if not budget:
            year = request.data.get('fiscal_year') or timezone.now().year
            budget = Budget.objects.filter(fiscal_year=int(year)).first()

        if not budget:
            return Response({'error': 'Target budget or adjustment record not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Apply and finalize the reduction
        prev_status = budget.adjustment_status
        budget.adjustment_status = BudgetAdjustmentStatus.REDUCED
        budget.save()

        if history:
            history.approved_by = request.user
            history.save()

        # Audit Log
        log_budget_action(
            budget=budget,
            user=request.user,
            action=BudgetAuditAction.ADJUSTED,
            previous_state=prev_status,
            new_state=BudgetAdjustmentStatus.REDUCED,
            details={
                'notes': notes,
                'factor': float(budget.adjustment_factor),
                'history_id': history.id if history else None
            },
            request=request
        )

        return Response({
            'success': True,
            'message': f"Budget adjustment for '{budget.name}' ratified. Multiplier locked at {float(budget.adjustment_factor * 100):.1f}%.",
            'adjustment_status': budget.adjustment_status,
            'factor': float(budget.adjustment_factor),
        })


class BudgetAdjustmentRejectView(APIView):
    """
    POST /api/finance/budgeting/adjustments/{id}/reject/
    POST /api/finance/budgeting/adjustments/reject/
    Rejects a pending adjustment and restores full 100% baseline ceilings.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk=None):
        item_id = pk or request.data.get('adjustment_id') or request.data.get('id')
        reason = request.data.get('reason') or request.data.get('notes') or 'Adjustment rejected by finance committee.'

        budget = None
        if item_id:
            history = BudgetAdjustmentHistory.objects.filter(id=item_id).first()
            if history:
                budget = history.budget
            else:
                budget = Budget.objects.filter(id=item_id).first()

        if not budget:
            year = request.data.get('fiscal_year') or timezone.now().year
            budget = Budget.objects.filter(fiscal_year=int(year)).first()

        if not budget:
            return Response({'error': 'Budget not found.'}, status=status.HTTP_404_NOT_FOUND)

        prev_status = budget.adjustment_status
        # Revert factor and restore original ceilings
        budget.adjustment_factor = Decimal('1.0000')
        budget.adjustment_status = BudgetAdjustmentStatus.NORMAL
        budget.save()

        for line in budget.lines.all():
            line.controlled_budget = line.effective_original_budget
            line.save()

        # Audit Log
        log_budget_action(
            budget=budget,
            user=request.user,
            action=BudgetAuditAction.REJECTED,
            previous_state=prev_status,
            new_state=BudgetAdjustmentStatus.NORMAL,
            details={'rejection_reason': reason},
            request=request
        )

        return Response({
            'success': True,
            'message': f"Budget adjustment rejected. Ceilings restored to 100% baseline.",
            'adjustment_status': budget.adjustment_status,
            'factor': 1.0,
        })


class PendingApprovalsListView(APIView):
    """
    GET /api/finance/budgeting/approvals/pending/
    Returns all governance items awaiting executive authorization:
    - Formulation cycles in 'pending_approval' status
    - Income shortfall adjustments awaiting manager sign-off
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        now = timezone.now()
        year_param = request.query_params.get('fiscal_year') or request.query_params.get('year')
        campus_id = get_request_campus_id(request)

        try:
            fiscal_year = int(year_param) if year_param else now.year
        except (ValueError, TypeError):
            fiscal_year = now.year

        # 1. Pending Budgets
        budget_qs = Budget.objects.filter(
            status=BudgetStatus.PENDING_APPROVAL,
            fiscal_year=fiscal_year
        ).select_related('campus')

        if campus_id and campus_id not in ['all', 'undefined', 'null']:
            budget_qs = budget_qs.filter(campus_id=campus_id)

        pending_budgets = []
        for b in budget_qs:
            lines = []
            total_amt = Decimal('0.00')
            for l in b.lines.select_related('account').all():
                total_amt += l.amount
                lines.append({
                    'id': l.id,
                    'account_code': l.account.code if l.account else '',
                    'account_name': l.account.name if l.account else '',
                    'amount': str(l.amount),
                    'category_rule': l.category_rule,
                })

            pending_budgets.append({
                'id': b.id,
                'name': b.name,
                'fiscal_year': b.fiscal_year,
                'campus_name': b.campus.name if b.campus else 'All Campuses',
                'status': b.status,
                'total_amount': str(total_amt),
                'lines_count': len(lines),
                'lines': lines,
                'created_at': b.created_at.isoformat() if b.created_at else None,
                'description': b.description or 'Annual budget formulation submitted for ratification.',
            })

        # 2. Pending Adjustments
        # Adjustments with approved_by=None or budget adjustment_status == 'pending_review' or 'reduced'
        history_qs = BudgetAdjustmentHistory.objects.filter(
            approved_by__isnull=True,
            budget__fiscal_year=fiscal_year
        ).select_related('budget', 'budget__campus')

        if campus_id and campus_id not in ['all', 'undefined', 'null']:
            history_qs = history_qs.filter(budget__campus_id=campus_id)

        pending_adjustments = []
        for h in history_qs[:20]:
            pending_adjustments.append({
                'id': h.id,
                'budget_id': h.budget_id,
                'budget_name': h.budget.name if h.budget else '',
                'fiscal_year': h.budget.fiscal_year if h.budget else fiscal_year,
                'campus_name': h.budget.campus.name if (h.budget and h.budget.campus) else 'All Campuses',
                'previous_factor': float(h.previous_factor),
                'new_factor': float(h.new_factor),
                'factor_pct': round(float(h.new_factor * 100), 1),
                'total_reduction': str(h.total_reduction),
                'trigger_reason': h.trigger_reason,
                'projected_income': str(h.projected_income),
                'actual_income': str(h.actual_income),
                'calculated_at': h.calculated_at.isoformat(),
                'line_snapshot': h.line_snapshot or [],
            })

        return Response({
            'success': True,
            'fiscal_year': fiscal_year,
            'counts': {
                'budgets': len(pending_budgets),
                'adjustments': len(pending_adjustments),
                'total': len(pending_budgets) + len(pending_adjustments),
            },
            'pending_budgets': pending_budgets,
            'pending_adjustments': pending_adjustments,
        })
