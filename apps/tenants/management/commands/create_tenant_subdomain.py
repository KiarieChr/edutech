import re
from django.core.management.base import BaseCommand
from tenants.models import Client, Domain, PublicConfiguration

class Command(BaseCommand):
    help = 'Create a new tenant with a specific subdomain'

    def add_arguments(self, parser):
        parser.add_argument('--schema_name', type=str, required=True, help='Schema name for the tenant (alphanumeric and underscores)')
        parser.add_argument('--name', type=str, required=True, help='Display name for the tenant')
        parser.add_argument('--description', type=str, default='', help='Description of the tenant')

    def handle(self, *args, **options):
        schema_name = options['schema_name']
        name = options['name']
        description = options['description']

        if not re.match(r'^[a-zA-Z0-9_]+$', schema_name):
            self.stdout.write(self.style.ERROR('Schema name can only contain alphanumeric characters and underscores.'))
            return

        if Client.objects.filter(schema_name=schema_name).exists():
            self.stdout.write(self.style.ERROR(f'Tenant with schema "{schema_name}" already exists.'))
            return

        try:
            # Create the tenant
            tenant = Client(schema_name=schema_name, name=name, description=description)
            tenant.save() # Automatically creates schema and runs migrations

            # Create the domain
            config = PublicConfiguration.get_instance()
            domain_url = f"{schema_name}.{config.base_domain}"
            domain = Domain(domain=domain_url, tenant=tenant, is_primary=True)
            domain.save()

            self.stdout.write(self.style.SUCCESS(f'Successfully created tenant "{name}" at {domain_url}'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Failed to create tenant: {str(e)}'))
