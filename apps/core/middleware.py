from django.http import Http404
# pyrefly: ignore [missing-import]
from django_tenants.middleware.main import TenantMainMiddleware
# pyrefly: ignore [missing-import]
from django_tenants.utils import get_public_schema_name
from tenants.models import Client

class CustomTenantMiddleware(TenantMainMiddleware):
    """
    Custom Tenant Middleware for robust subdomain routing.
    If a requested subdomain (tenant) is not found, instead of throwing a 404,
    it falls back to the public schema so the user can be routed to the landing page
    or shown a friendly "Tenant not found" page.
    """
    
    @staticmethod
    def tenant_not_found(request, hostname):
        """
        Called when a tenant for the given hostname is not found.
        We override this to set the tenant to the public schema instead of raising Http404.
        """
        public_schema_name = get_public_schema_name()
        
        # We need a fallback tenant and domain object representing the public schema
        try:
            fallback_tenant = Client.objects.get(schema_name=public_schema_name)
        except Client.DoesNotExist:
            # If even the public schema is missing, fallback to 404
            raise Http404("Public schema not found. Please run migrations and create the public tenant.")
            
        request.tenant = fallback_tenant
        request.tenant.domain_url = hostname
