from rest_framework.permissions import BasePermission
from core.models import InstitutionProfile

class ModuleRequiredPermission(BasePermission):
    """
    Grants access if the tenant's InstitutionProfile has the required module enabled.
    The view must define a `required_module` attribute.
    """
    message = "This module is not enabled for your business."

    def has_permission(self, request, view):
        required_module = getattr(view, 'required_module', None)
        
        # If view doesn't specify a required module, allow by default
        if not required_module:
            return True

        profile = InstitutionProfile.get_instance()
        modules = profile.enabled_modules or []
        
        if required_module in modules:
            return True
            
        return False

class TenantAccessPermission(BasePermission):
    """
    Ensures that the authenticated user actually has access to the current tenant.
    Superusers are exempt from this restriction.
    """
    message = "You do not have access to this tenant/school."

    def has_permission(self, request, view):
        # Let standard auth/permissions handle unauthenticated users
        if not request.user or not request.user.is_authenticated:
            return True
            
        # Superusers can access any tenant
        if request.user.is_superuser:
            return True
            
        # If we are in a specific tenant, ensure the user belongs to it
        if hasattr(request, 'tenant') and request.tenant.schema_name != 'public':
            if not request.user.tenants.filter(id=request.tenant.id).exists():
                return False
                
        return True
