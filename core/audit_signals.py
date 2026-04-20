"""
Audit signals — captures model-level changes and auth events.
Auto-discovers via CoreConfig.ready().
"""
import json

from django.db.models.signals import post_save, post_delete
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver
from django.contrib.auth import get_user_model

User = get_user_model()

# Models we want detailed change tracking for — add app_label.ModelName
TRACKED_MODELS = {
    'core.InstitutionProfile',
    'core.SystemConfiguration',
    'workforce.Employee',
    'workforce.Campus',
    'workforce.Department',
    'student_settings.Enrollment',
    'student_management.Application',
    'student_management.Admission',
    'accounts.Student',
    'fees.FeeStructure',
    'fees.FeeTemplate',
    'fees.VoteHead',
    'fees.GradeBand',
    'finance.FiscalYear',
}


def _get_request():
    from core.audit_middleware import get_current_request
    return get_current_request()


def _get_model_key(instance):
    return f"{instance._meta.app_label}.{instance.__class__.__name__}"


@receiver(post_save)
def audit_post_save(sender, instance, created, **kwargs):
    """Log CREATE and UPDATE for tracked models."""
    model_key = _get_model_key(instance)
    if model_key not in TRACKED_MODELS:
        return

    # Avoid circular import
    from core.models import AuditLog

    # Don't log AuditLog saves (infinite recursion)
    if isinstance(instance, AuditLog):
        return

    request = _get_request()
    user = None
    ip = None
    if request and hasattr(request, 'user') and request.user.is_authenticated:
        user = request.user
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        ip = xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR')

    action = AuditLog.Action.CREATE if created else AuditLog.Action.UPDATE

    AuditLog.objects.create(
        user=user,
        username=getattr(user, 'username', '') if user else 'system',
        ip_address=ip,
        action=action,
        severity=AuditLog.Severity.INFO,
        module=instance._meta.app_label,
        model_name=instance.__class__.__name__,
        object_id=str(instance.pk),
        object_repr=str(instance)[:255],
        description=f"{'Created' if created else 'Updated'} {instance.__class__.__name__} #{instance.pk}",
    )


@receiver(post_delete)
def audit_post_delete(sender, instance, **kwargs):
    """Log DELETE for tracked models."""
    model_key = _get_model_key(instance)
    if model_key not in TRACKED_MODELS:
        return

    from core.models import AuditLog

    request = _get_request()
    user = None
    ip = None
    if request and hasattr(request, 'user') and request.user.is_authenticated:
        user = request.user
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        ip = xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR')

    AuditLog.objects.create(
        user=user,
        username=getattr(user, 'username', '') if user else 'system',
        ip_address=ip,
        action=AuditLog.Action.DELETE,
        severity=AuditLog.Severity.WARNING,
        module=instance._meta.app_label,
        model_name=instance.__class__.__name__,
        object_id=str(instance.pk),
        object_repr=str(instance)[:255],
        description=f"Deleted {instance.__class__.__name__} #{instance.pk}: {str(instance)[:100]}",
    )


# ── Auth events ───────────────────────────────────────────────────────────

@receiver(user_logged_in)
def audit_login(sender, request, user, **kwargs):
    from core.models import AuditLog
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    ip = xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR')
    AuditLog.objects.create(
        user=user,
        username=user.username,
        ip_address=ip,
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
        action=AuditLog.Action.LOGIN,
        severity=AuditLog.Severity.INFO,
        module='auth',
        description=f"User {user.username} logged in",
    )


@receiver(user_logged_out)
def audit_logout(sender, request, user, **kwargs):
    from core.models import AuditLog
    if user is None:
        return
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    ip = xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR')
    AuditLog.objects.create(
        user=user,
        username=user.username,
        ip_address=ip,
        action=AuditLog.Action.LOGOUT,
        severity=AuditLog.Severity.INFO,
        module='auth',
        description=f"User {user.username} logged out",
    )


@receiver(user_login_failed)
def audit_login_failed(sender, credentials, request, **kwargs):
    from core.models import AuditLog
    username = credentials.get('username', 'unknown')
    ip = None
    ua = ''
    if request:
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        ip = xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR')
        ua = request.META.get('HTTP_USER_AGENT', '')[:500]
    AuditLog.objects.create(
        username=username,
        ip_address=ip,
        user_agent=ua,
        action=AuditLog.Action.LOGIN_FAILED,
        severity=AuditLog.Severity.WARNING,
        module='auth',
        description=f"Failed login attempt for '{username}'",
    )
