import os
import sys
import django

# Add apps to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'apps'))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

# pyrefly: ignore [missing-import]
from tenants.models import Client, Domain

def create_tenant():
    # 1. Create a tenant
    tenant, created = Client.objects.get_or_create(
        schema_name='demo_school',
        defaults={
            'name': 'Fahari Demo School',
            'description': 'Main demo tenant for testing'
        }
    )
    if created:
        print("Created tenant: demo_school")
    else:
        print("Tenant 'demo_school' already exists")

    # 2. Add domains to the tenant
    domains = ['demo.localhost', '127.0.0.1', 'app.royalsoftwares.co.ke']
    for idx, d in enumerate(domains):
        domain, d_created = Domain.objects.get_or_create(
            domain=d,
            defaults={
                'tenant': tenant,
                'is_primary': idx == 0  # First one is primary
            }
        )
        if d_created:
            print(f"Created domain '{d}' and linked to demo_school")
        else:
            print(f"Domain '{d}' already exists")

if __name__ == "__main__":
    create_tenant()
