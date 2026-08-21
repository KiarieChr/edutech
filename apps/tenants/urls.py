from django.urls import path
from .views import CreateTenantView

app_name = 'tenants'

urlpatterns = [
    path('create/', CreateTenantView.as_view(), name='create-tenant'),
]
