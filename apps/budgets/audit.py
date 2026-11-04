import logging
from django.utils import timezone
from budgets.models import Budget, BudgetAuditLog, BudgetAuditAction

logger = logging.getLogger(__name__)


def get_client_ip(request):
    if not request:
        return None
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_budget_action(
    budget: Budget,
    user,
    action: str,
    previous_state: str = None,
    new_state: str = None,
    details: dict = None,
    request=None
):
    """
    Safely creates an immutable record in BudgetAuditLog.
    Never crashes the calling transaction if audit table is pending schema sync.
    """
    try:
        ip = get_client_ip(request)
        actual_user = user if (user and getattr(user, 'is_authenticated', False)) else None

        return BudgetAuditLog.objects.create(
            budget=budget,
            user=actual_user,
            action=action,
            previous_state=str(previous_state or ''),
            new_state=str(new_state or ''),
            details=details or {},
            ip_address=ip
        )
    except Exception as e:
        logger.warning(f"Failed to write to BudgetAuditLog: {e}")
        return None
