import rest_framework
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views import defaults as default_views

# pyrefly: ignore [missing-import]
from core.api_views import api_landing

admin.site.site_header = "Fahari Academia Public Admin"

urlpatterns = [
    path("", api_landing, name="api-landing"),
    path("admin/", admin.site.urls),
    # Tenant provisioning endpoints
    path('api/public/tenants/', include('tenants.urls')),
    # Authentication endpoints
    path('api/', include('accounts.api_urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
