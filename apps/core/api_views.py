"""
API endpoint for running whitelisted management commands.
Superuser-only. Returns stdout/stderr output.
Also: InstitutionProfile singleton CRUD.
Also: AuditLog read-only API + SystemConfiguration CRUD.
"""
import io

from django.core.management import call_command, get_commands
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser, AllowAny
from rest_framework.response import Response
from rest_framework import status, serializers
from rest_framework.viewsets import ReadOnlyModelViewSet, ModelViewSet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import InstitutionProfile, AuditLog, SystemConfiguration


# ---------------------------------------------------------------------------
# Institution Profile Serializer & Views
# ---------------------------------------------------------------------------

class InstitutionProfileSerializer(serializers.ModelSerializer):
    # Allow empty strings for optional fields — frontend sends '' when cleared
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    website = serializers.URLField(required=False, allow_blank=True, allow_null=True)
    portal_url = serializers.URLField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = InstitutionProfile
        fields = '__all__'

    def to_internal_value(self, data):
        # Convert empty string dates to None before field-level validation
        if 'established_date' in data and data['established_date'] == '':
            data = data.copy()
            data['established_date'] = None
        # Convert null to empty string for text fields that don't allow null in DB
        for field in ('email', 'website', 'portal_url'):
            if field in data and data[field] is None:
                data = data.copy() if not isinstance(data, dict) else data
                data[field] = ''
        return super().to_internal_value(data)


@api_view(['GET'])
@permission_classes([AllowAny])
def institution_profile_detail(request):
    """Return the singleton institution profile (public)."""
    profile = InstitutionProfile.get_instance()
    serializer = InstitutionProfileSerializer(profile)
    return Response(serializer.data)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAdminUser])
def institution_profile_update(request):
    """Update the singleton institution profile (admin only)."""
    profile = InstitutionProfile.get_instance()
    partial = request.method == 'PATCH'
    serializer = InstitutionProfileSerializer(profile, data=request.data, partial=partial)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


# Only these commands can be triggered from the frontend.
ALLOWED_COMMANDS = {
    'seed_kenya_curriculum': {
        'label': 'Seed Kenya Curriculum',
        'description': 'Creates CBC & 8-4-4 curricula with levels, grades, learning areas, and subjects.',
        'app': 'student_settings',
    },
    'seed_academic_years': {
        'label': 'Seed Academic Years',
        'description': 'Creates academic years 2015-2029 with 3 terms each.',
        'app': 'student_settings',
    },
    'setup_initial_settings': {
        'label': 'Setup Initial Settings',
        'description': 'Seeds student statuses, demographic config, admission config, and promotion rules.',
        'app': 'student_settings',
    },
    'seed_leave_types': {
        'label': 'Seed Leave Types',
        'description': 'Creates standard employee leave categories (Annual, Sick, Maternity/Paternity, Compassionate, etc.).',
        'app': 'workforce',
    },
    'check_future_enrollments': {
        'label': 'Check & Fix Future Enrollments',
        'description': 'Scans for students admitted in the past but whose active enrollments are in future terms. Will auto-generate missing historical enrollments using their current grade.',
        'app': 'student_management',
    },
    'seed_system_config': {
        'label': 'Seed System Configuration',
        'description': 'Creates default system config entries (M-Pesa, timetable, grading, security, etc.).',
        'app': 'core',
    },
    'seed_roles': {
        'label': 'Seed Default Roles',
        'description': 'Creates default user roles (Teacher, Lecturer, Parent, Finance Manager, Bursar, HR Manager, Registrar, etc.) with appropriate permissions.',
        'app': 'accounts',
    },
    'seed_coa': {
        'label': 'Seed Chart of Accounts',
        'description': 'Seeds the full standard Chart of Accounts (Assets, Liabilities, Equity, Income, Expenses) required for the Finance module to function.',
        'app': 'finance',
    },
    'seed_student_accounts': {
        'label': 'Seed Student Fee Accounts',
        'description': 'Seeds student-related sub-accounts (fee vote heads, student receivables, prepayments). Run AFTER Seed COA.',
        'app': 'finance',
    },
}



@api_view(['GET'])
@permission_classes([IsAdminUser])
def list_commands(request):
    """Return the list of runnable commands."""
    commands = [
        {'name': name, **meta}
        for name, meta in ALLOWED_COMMANDS.items()
    ]
    return Response(commands)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def run_command(request):
    """
    Run a whitelisted management command.
    Body: { "command": "seed_kenya_curriculum" }
    """
    command_name = request.data.get('command', '').strip()

    if not command_name:
        return Response(
            {'error': 'Missing "command" field.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if command_name not in ALLOWED_COMMANDS:
        return Response(
            {'error': f'Command "{command_name}" is not allowed.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Verify the command actually exists in Django's registry
    if command_name not in get_commands():
        return Response(
            {'error': f'Command "{command_name}" not found in the project.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    stdout = io.StringIO()
    stderr = io.StringIO()

    try:
        if command_name == 'check_future_enrollments':
            call_command(command_name, '--auto-fix', stdout=stdout, stderr=stderr)
        else:
            call_command(command_name, stdout=stdout, stderr=stderr)
            
        return Response({
            'command': command_name,
            'status': 'success',
            'output': stdout.getvalue(),
            'errors': stderr.getvalue() or None,
        })
    except Exception as exc:
        return Response({
            'command': command_name,
            'status': 'error',
            'output': stdout.getvalue(),
            'error': str(exc),
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ---------------------------------------------------------------------------
# Audit Log Serializer & ViewSet (read-only)
# ---------------------------------------------------------------------------

class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = [
            'id', 'user', 'username', 'ip_address', 'user_agent',
            'action', 'severity', 'module', 'model_name',
            'object_id', 'object_repr', 'request_method', 'request_path',
            'response_code', 'changes', 'description', 'timestamp',
        ]


class AuditLogViewSet(ReadOnlyModelViewSet):
    """
    Read-only audit log API.  Admin-only.
    Supports filtering by action, module, severity, user, and date range.
    """
    serializer_class = AuditLogSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['action', 'severity', 'module', 'model_name', 'username']
    search_fields = ['username', 'description', 'object_repr', 'request_path']
    ordering_fields = ['timestamp', 'action', 'severity']
    ordering = ['-timestamp']

    def get_queryset(self):
        qs = AuditLog.objects.all()
        # Date range filters
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if date_from:
            qs = qs.filter(timestamp__date__gte=date_from)
        if date_to:
            qs = qs.filter(timestamp__date__lte=date_to)
        return qs


# ---------------------------------------------------------------------------
# System Configuration Serializer & ViewSet
# ---------------------------------------------------------------------------

class SystemConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemConfiguration
        fields = [
            'id', 'key', 'value', 'value_type', 'group',
            'label', 'description', 'is_editable', 'display_order',
            'updated_at',
        ]
        read_only_fields = ['key', 'value_type', 'group', 'label', 'description',
                            'is_editable', 'display_order', 'updated_at']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Mask secrets — only show last 4 chars
        if instance.value_type == SystemConfiguration.ValueType.SECRET and instance.value:
            data['value'] = '••••••••' + instance.value[-4:] if len(instance.value) > 4 else '••••'
        return data


class SystemConfigurationViewSet(ModelViewSet):
    """
    System config CRUD.  Admin-only.
    GET returns all configs grouped. PATCH updates a single key's value.
    """
    serializer_class = SystemConfigurationSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['group']
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        return SystemConfiguration.objects.all()

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def bulk_update_config(request):
    """
    Bulk update multiple config keys at once.
    Body: { "configs": { "mpesa_consumer_key": "abc", "mpesa_shortcode": "174379" } }
    """
    configs = request.data.get('configs', {})
    if not isinstance(configs, dict):
        return Response({'error': 'configs must be a dict'}, status=status.HTTP_400_BAD_REQUEST)

    updated = []
    for key, value in configs.items():
        try:
            obj = SystemConfiguration.objects.get(key=key)
            if not obj.is_editable:
                continue
            obj.value = str(value)
            obj.updated_by = request.user
            obj.save()
            updated.append(key)
        except SystemConfiguration.DoesNotExist:
            pass

    return Response({'updated': updated, 'count': len(updated)})


# ---------------------------------------------------------------------------
# Billing Settings: SystemSubscription & SMSPricingBand
# ---------------------------------------------------------------------------

from .models import SystemSubscription, SMSPricingBand

class SystemSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemSubscription
        fields = '__all__'

@api_view(['GET'])
@permission_classes([IsAdminUser])
def system_subscription_detail(request):
    subscription = SystemSubscription.get_instance()
    serializer = SystemSubscriptionSerializer(subscription)
    return Response(serializer.data)

@api_view(['PUT', 'PATCH'])
@permission_classes([IsAdminUser])
def system_subscription_update(request):
    subscription = SystemSubscription.get_instance()
    partial = request.method == 'PATCH'
    serializer = SystemSubscriptionSerializer(subscription, data=request.data, partial=partial)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)

class SMSPricingBandSerializer(serializers.ModelSerializer):
    class Meta:
        model = SMSPricingBand
        fields = '__all__'

class SMSPricingBandViewSet(ModelViewSet):
    serializer_class = SMSPricingBandSerializer
    permission_classes = [IsAdminUser]
    queryset = SMSPricingBand.objects.all()
    ordering = ['max_sms']


# ─── API Landing page ─────────────────────────────────────────────────────────

API_MODULES = [
    {'name': 'Authentication',    'prefix': '/api/users/',            'description': 'Login, logout, token refresh, session management, user profile'},
    {'name': 'Academics',         'prefix': '/api/academics/',        'description': 'Academic years, terms, class sessions, enrolments, reports'},
    {'name': 'Student Management','prefix': '/api/student-management/','description': 'Students, guardians, admissions, transfers'},
    {'name': 'Fees',              'prefix': '/api/fees/',             'description': 'Fee structures, invoices, payments, receipts, arrears'},
    {'name': 'Finance',           'prefix': '/api/finance/',          'description': 'Ledger, trial balance, income statement, cash flow'},
    {'name': 'Journals',          'prefix': '/api/journals/',         'description': 'Journal entries and approvals'},
    {'name': 'Finance Reports',   'prefix': '/api/finance-reports/',  'description': 'Exportable financial report endpoints'},
    {'name': 'Invoicing',         'prefix': '/api/invoicing/',        'description': 'Supplier invoices and debit notes'},
    {'name': 'Payables',          'prefix': '/api/payables/',         'description': 'Accounts payable, supplier management'},
    {'name': 'Budgets',           'prefix': '/api/budgets/',          'description': 'Budget creation, tracking, variance analysis'},
    {'name': 'Procurement',       'prefix': '/api/procurement/',      'description': 'Purchase orders, requisitions, suppliers'},
    {'name': 'Inventory',         'prefix': '/api/inventory/',        'description': 'Stock items, stores, stock movements'},
    {'name': 'Timetable',         'prefix': '/api/timetable/',        'description': 'Timetable slots, analytics, coverage reports'},
    {'name': 'Scheduled Lessons', 'prefix': '/api/scheduled/',        'description': 'Lesson scheduling and planning'},
    {'name': 'Lesson Sessions',   'prefix': '/api/lesson-sessions/',  'description': 'Live lesson tracking and teacher notes'},
    {'name': 'Attendance',        'prefix': '/api/attendance/',       'description': 'Daily class attendance, absentee reports'},
    {'name': 'Examinations',      'prefix': '/api/examinations/',     'description': 'Exams, marks entry, grade computation'},
    {'name': 'Assignments',       'prefix': '/api/assignments/',      'description': 'Assignment creation, submissions, grading'},
    {'name': 'Payments',          'prefix': '/payments/',             'description': 'M-Pesa (Daraja), Paystack, SMS, transaction log'},
    {'name': 'Recruitment',       'prefix': '/api/recruitment/',      'description': 'Job postings, applications, interviews'},
    {'name': 'Workforce / HR',    'prefix': '/workforce/',            'description': 'Employees, payroll, leave, appraisals'},
    {'name': 'Student Portal',    'prefix': '/api/portal/',           'description': 'Parent/student self-service portal'},
    {'name': 'Settings',          'prefix': '/api/settings/',         'description': 'Institution settings, grades, curricula, terms'},
    {'name': 'System',            'prefix': '/api/system/',           'description': 'Management commands, audit logs, configuration'},
    {'name': 'Admin UI',          'prefix': '/admin/',                'description': 'Django admin — superuser only'},
]

_LANDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Fahari Academia — API</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #0f1117; color: #e2e8f0; min-height: 100vh; }}
  header {{ background: linear-gradient(135deg, #1a202c 0%, #2d3748 100%); border-bottom: 1px solid #4a5568; padding: 2rem 2.5rem; display: flex; align-items: center; gap: 1.5rem; }}
  .logo {{ width: 48px; height: 48px; background: linear-gradient(135deg, #667eea, #764ba2); border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 1.5rem; flex-shrink: 0; }}
  header h1 {{ font-size: 1.6rem; font-weight: 700; color: #fff; }}
  header p {{ color: #a0aec0; font-size: 0.9rem; margin-top: 0.25rem; }}
  .badge {{ display: inline-block; padding: 0.2rem 0.7rem; border-radius: 999px; font-size: 0.72rem; font-weight: 600; letter-spacing: 0.05em; }}
  .badge-green {{ background: #22543d; color: #68d391; }}
  .badge-blue  {{ background: #1a365d; color: #63b3ed; }}
  main {{ max-width: 1100px; margin: 0 auto; padding: 2.5rem 2rem; }}
  .meta {{ display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 2.5rem; }}
  .meta-card {{ background: #1a202c; border: 1px solid #2d3748; border-radius: 10px; padding: 1rem 1.4rem; flex: 1; min-width: 160px; }}
  .meta-card .val {{ font-size: 1.4rem; font-weight: 700; color: #fff; }}
  .meta-card .lbl {{ font-size: 0.78rem; color: #718096; margin-top: 0.2rem; }}
  h2 {{ font-size: 1.1rem; color: #a0aec0; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 1rem; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1rem; }}
  .card {{ background: #1a202c; border: 1px solid #2d3748; border-radius: 10px; padding: 1.1rem 1.3rem; transition: border-color .15s, transform .15s; text-decoration: none; color: inherit; display: block; }}
  .card:hover {{ border-color: #667eea; transform: translateY(-2px); }}
  .card-top {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.4rem; }}
  .card-name {{ font-weight: 600; color: #e2e8f0; font-size: 0.95rem; }}
  .card-prefix {{ font-family: monospace; font-size: 0.78rem; color: #667eea; }}
  .card-desc {{ font-size: 0.82rem; color: #718096; line-height: 1.4; }}
  footer {{ text-align: center; padding: 2rem; color: #4a5568; font-size: 0.8rem; border-top: 1px solid #2d3748; margin-top: 3rem; }}
  .pill {{ background: #2d3748; border-radius: 6px; padding: 0.15rem 0.5rem; font-family: monospace; font-size: 0.78rem; color: #90cdf4; }}
</style>
</head>
<body>
<header>
  <div class="logo">🎓</div>
  <div>
    <div style="display:flex;align-items:center;gap:.7rem;">
      <h1>Fahari Academia</h1>
      <span class="badge badge-green">API</span>
      <span class="badge badge-blue">v1</span>
    </div>
    <p>Fahari Academia Management System — RESTful API Backend</p>
  </div>
</header>
<main>
  <div class="meta">
    <div class="meta-card"><div class="val">{module_count}</div><div class="lbl">API Modules</div></div>
    <div class="meta-card"><div class="val">DRF</div><div class="lbl">Framework</div></div>
    <div class="meta-card"><div class="val">Token</div><div class="lbl">Authentication</div></div>
    <div class="meta-card" style="flex:2"><div class="val" style="font-size:.95rem;font-family:monospace;color:#90cdf4">{base_url}</div><div class="lbl">Base URL</div></div>
  </div>
  <h2>Available Modules</h2>
  <div class="grid">
    {cards}
  </div>
  <div style="margin-top:2.5rem;background:#1a202c;border:1px solid #2d3748;border-radius:10px;padding:1.2rem 1.4rem;">
    <h2 style="margin-bottom:.8rem">Quick Start</h2>
    <p style="color:#718096;font-size:.85rem;line-height:1.8">
      1. Obtain a token: <span class="pill">POST /api/users/login/</span> with <span class="pill">email</span> + <span class="pill">password</span><br>
      2. Include it in every request header: <span class="pill">Authorization: Token &lt;your-token&gt;</span><br>
      3. All endpoints return JSON. Errors use standard HTTP status codes.
    </p>
  </div>
</main>
<footer>Fahari Academia API &mdash; All rights reserved &mdash; {year}</footer>
</body>
</html>"""


@api_view(['GET'])
@permission_classes([AllowAny])
def api_landing(request):
    """
    Root landing page.
    - Browsers receive a styled HTML overview.
    - API clients (Accept: application/json) receive a JSON module index.
    """
    from django.utils import timezone as tz

    accept = request.META.get('HTTP_ACCEPT', '')
    wants_json = 'application/json' in accept and 'text/html' not in accept

    if wants_json:
        return Response({
            'service': 'Fahari Academia API',
            'version': 'v1',
            'status': 'operational',
            'authentication': 'Token — POST /api/users/login/ to obtain',
            'modules': API_MODULES,
        })

    # Build HTML cards
    cards_html = '\n'.join(
        f'<a class="card" href="{m["prefix"]}">'
        f'  <div class="card-top"><span class="card-name">{m["name"]}</span>'
        f'  <span class="card-prefix">{m["prefix"]}</span></div>'
        f'  <div class="card-desc">{m["description"]}</div>'
        f'</a>'
        for m in API_MODULES
    )
    base_url = request.build_absolute_uri('/').rstrip('/')
    html = _LANDING_HTML.format(
        module_count=len(API_MODULES),
        base_url=base_url,
        cards=cards_html,
        year=tz.now().year,
    )
    from django.http import HttpResponse
    return HttpResponse(html, content_type='text/html')

