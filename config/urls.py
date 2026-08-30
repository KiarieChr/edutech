import rest_framework
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views import defaults as default_views
from django.conf.urls.i18n import i18n_patterns
from django.views.i18n import JavaScriptCatalog
from rest_framework.routers import DefaultRouter

# pyrefly: ignore [missing-import]
from core.api_views import (
    list_commands, run_command,
    institution_profile_detail, institution_profile_update,
    AuditLogViewSet, SystemConfigurationViewSet, bulk_update_config,
    system_subscription_detail, system_subscription_update,
    SMSPricingBandViewSet,
    api_landing,
)
# pyrefly: ignore [missing-import]
from tenants.views import TenantInfoView, DashboardStatsView

admin.site.site_header = "Fahari Academia Admin"

# ── DRF Router for core APIs ────────────────────────────────────────────────
core_router = DefaultRouter()
core_router.register(r'audit-logs', AuditLogViewSet, basename='audit-log')
core_router.register(r'system-config', SystemConfigurationViewSet, basename='system-config')
core_router.register(r'sms-pricing-bands', SMSPricingBandViewSet, basename='sms-pricing-band')

urlpatterns = [
    path("", api_landing, name="api-landing"),
    path("api/", api_landing, name="api-landing-root"),
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    path('api/system/commands/', list_commands, name='list-commands'),
    path('api/system/run-command/', run_command, name='run-command'),
    path('api/institution/', institution_profile_detail, name='institution-profile'),
    path('api/institution/update/', institution_profile_update, name='institution-profile-update'),
    path('api/system-subscription/', system_subscription_detail, name='system-subscription'),
    path('api/system-subscription/update/', system_subscription_update, name='system-subscription-update'),
    path('api/', include(core_router.urls)),
    path('api/system-config/bulk-update/', bulk_update_config, name='system-config-bulk-update'),
    path('api/settings/', include('student_settings.urls')),
    path('api/recruitment/', include('recruitment.urls')),
    path('api/student-management/', include('student_management.urls')),
    path('api/', include('accounts.api_urls')),
    path('api/finance/', include('finance.urls')),
    path('api/journals/', include('journals.urls')),
    path('api/finance-reports/', include('finance_reports.urls')),
    path('api/invoicing/', include('invoicing.urls')),
    path('api/payables/', include('payables.urls')),
    path('api/inventory/', include('inventory.urls')),
    path('api/procurement/', include('procurement.urls')),
    path('api/fleet/', include('fleet.api_urls')),
    path('api/budgets/', include('budgets.urls')),
    path('api/fees/', include('fees.urls')),
    path('api/academics/', include('academics.urls')),
    path('api/examinations/', include('examinations.urls')),
    path('api/timetable/', include('timetable.urls')),
    path('api/scheduled/', include('scheduled_lessons.urls')),
    path('api/lesson-sessions/', include('lesson_sessions.urls')),
    path('api/attendance/', include('attendance.urls')),
    path('api/portal/', include('portal.urls')),
    path('api/assignments/', include('assignments.urls')),
    path('api/programmes/', include('programmes.urls')),
    path('workforce/', include('workforce.api_urls')),
    path('api/public/tenants/', include('tenants.urls')),
    path('api/tenant/info/', TenantInfoView.as_view(), name='tenant-info'),
    path('api/tenant/dashboard/', DashboardStatsView.as_view(), name='tenant-dashboard'),
    path('api/intelligence/', include('intelligence.urls')),
    path('api/crm/', include('crm.urls')),
    #path('api/auth/', rest_framework.urls)
]

urlpatterns += i18n_patterns(
    path("jsi18n/", JavaScriptCatalog.as_view(), name="javascript-catalog"),
    path("", include("core.urls")),

    path("", include("accounts.urls")),
    path("programs/", include("course.urls")),
    path("result/", include("result.urls")),
    path("search/", include("search.urls")),
    path("quiz/", include("quiz.urls")),
    path("payments/", include("payments.urls")),
    path('workforce/', include('workforce.urls', namespace='hr_payroll')),
)


if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    # This allows the error pages to be debugged during development, just visit
    # these url in browser to see how these error pages look like.
    urlpatterns += [
        path(
            "400/",
            default_views.bad_request,
            kwargs={"exception": Exception("Bad Request!")},
        ),
        path(
            "403/",
            default_views.permission_denied,
            kwargs={"exception": Exception("Permission Denied")},
        ),
        path(
            "404/",
            default_views.page_not_found,
            kwargs={"exception": Exception("Page not Found")},
        ),
        path("500/", default_views.server_error),
    ]
