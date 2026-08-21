from django.core.management.base import BaseCommand
from tenants.models import Client, Domain

class Command(BaseCommand):
    help = 'List all tenants and their primary domains'

    def handle(self, *args, **options):
        tenants = Client.objects.all().prefetch_related('domains')
        
        if not tenants.exists():
            self.stdout.write(self.style.WARNING("No tenants found."))
            return

        self.stdout.write(self.style.SUCCESS(f"Found {tenants.count()} tenants:\n"))
        
        for tenant in tenants:
            domains = tenant.domains.all()
            primary_domain = domains.filter(is_primary=True).first()
            primary_str = primary_domain.domain if primary_domain else "No primary domain"
            status = primary_domain.status if primary_domain else "unknown"
            
            self.stdout.write(
                f"- Schema: {tenant.schema_name} | "
                f"Name: {tenant.name} | "
                f"Domain: {primary_str} | "
                f"Status: {status}"
            )
