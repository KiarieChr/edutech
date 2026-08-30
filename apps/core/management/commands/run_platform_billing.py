from django.core.management.base import BaseCommand
# pyrefly: ignore [missing-import]
from django_q.tasks import async_task
from tenants.models import Client

class Command(BaseCommand):
    help = 'Schedules monthly billing generation for all active tenants'

    def handle(self, *args, **options):
        # Exclude public schema
        tenants = Client.objects.exclude(schema_name='public')
        count = 0
        
        for tenant in tenants:
            async_task('core.tasks.run_monthly_billing_task', tenant.schema_name)
            count += 1
            
        self.stdout.write(self.style.SUCCESS(f'Successfully scheduled billing task for {count} tenants.'))
