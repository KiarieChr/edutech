"""
Audit Middleware — automatically logs every mutating API request.
Captures: user, IP, path, method, response code, and model changes.
"""
import json
import threading

from django.utils.deprecation import MiddlewareMixin

_local = threading.local()


def get_current_request():
    """Access the current request from anywhere (signal handlers)."""
    return getattr(_local, 'request', None)


class AuditMiddleware(MiddlewareMixin):
    """
    Logs POST / PUT / PATCH / DELETE API requests to AuditLog.
    GET requests are not logged to avoid overwhelming the table.
    Auth events (login/logout) are handled by signals in audit_signals.py.
    """

    # Paths to skip (health checks, static, admin assets, etc.)
    SKIP_PREFIXES = (
        '/static/', '/media/', '/admin/jsi18n/', '/favicon',
        '/api/audit-logs/',  # don't log reads of the audit log itself
    )

    def process_request(self, request):
        _local.request = request

    def process_response(self, request, response):
        try:
            self._maybe_log(request, response)
        except Exception:
            pass  # never break the response for audit logging
        finally:
            _local.request = None
        return response

    def _maybe_log(self, request, response):
        # Only log mutating methods on API paths
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return
        if not request.path.startswith('/api/') and not request.path.startswith('/workforce/'):
            return
        if any(request.path.startswith(p) for p in self.SKIP_PREFIXES):
            return

        from core.models import AuditLog

        action = {
            'POST': AuditLog.Action.CREATE,
            'PUT': AuditLog.Action.UPDATE,
            'PATCH': AuditLog.Action.UPDATE,
            'DELETE': AuditLog.Action.DELETE,
        }.get(request.method, AuditLog.Action.OTHER)

        user = request.user if hasattr(request, 'user') and request.user.is_authenticated else None

        # Determine module from URL path
        module = self._extract_module(request.path)

        # Severity based on response code
        severity = AuditLog.Severity.INFO
        if response.status_code >= 500:
            severity = AuditLog.Severity.ERROR
        elif response.status_code >= 400:
            severity = AuditLog.Severity.WARNING

        AuditLog.objects.create(
            user=user,
            username=getattr(user, 'username', '') if user else '',
            ip_address=self._get_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            action=action,
            severity=severity,
            module=module,
            request_method=request.method,
            request_path=request.path[:500],
            response_code=response.status_code,
            description=self._build_description(request, response),
        )

    @staticmethod
    def _get_ip(request):
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        if xff:
            return xff.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')

    @staticmethod
    def _extract_module(path):
        """Extract the Django app name from the URL path."""
        parts = [p for p in path.strip('/').split('/') if p]
        # /api/student-management/... → student-management
        # /workforce/api/... → workforce
        if len(parts) >= 2 and parts[0] == 'api':
            return parts[1]
        if parts:
            return parts[0]
        return ''

    @staticmethod
    def _build_description(request, response):
        """Short human-readable description of the action."""
        status_text = 'OK' if response.status_code < 400 else f'HTTP {response.status_code}'
        return f"{request.method} {request.path} → {status_text}"
