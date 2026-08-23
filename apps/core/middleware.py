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
    
    def get_tenant(self, domain_model, hostname):
        """
        Attempt to get the tenant for the domain. If it fails, fallback to the public tenant.
        """
        try:
            return super().get_tenant(domain_model, hostname)
        except domain_model.DoesNotExist:
            # Attempt to extract subdomain from hostname (e.g., 'demo' from 'demo.localhost')
            subdomain = hostname.split('.')[0]
            
            try:
                # If a tenant exists with this schema name, return it
                tenant = Client.objects.get(schema_name=subdomain)
                
                # Auto-create the domain mapping so future lookups are fast and django-tenants utils work
                domain_model.objects.get_or_create(
                    domain=hostname,
                    tenant=tenant,
                    defaults={'is_primary': False}
                )
                return tenant
            except Client.DoesNotExist:
                # Otherwise, fallback to the public tenant
                public_schema_name = get_public_schema_name()
                try:
                    return Client.objects.get(schema_name=public_schema_name)
                except Client.DoesNotExist:
                    raise Http404("Public schema not found. Please run migrations and create the public tenant.") 
