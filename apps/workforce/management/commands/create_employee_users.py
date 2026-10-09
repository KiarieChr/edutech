from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

class Command(BaseCommand):
    help = 'Creates user accounts for employees who do not have one'

    def handle(self, *args, **options):
        from django.apps import apps
        from django.db import connection
        
        try:
            from django_tenants.utils import get_tenant_model
            TenantModel = get_tenant_model()
            tenants = TenantModel.objects.exclude(schema_name='public')
            is_multitenant = True
        except (ImportError, Exception):
            is_multitenant = False

        if is_multitenant:
            for tenant in tenants:
                self.stdout.write(self.style.WARNING(f"\nProcessing Tenant: {tenant.name} ({tenant.schema_name})"))
                connection.set_tenant(tenant)
                self.process_schema()
        else:
            self.process_schema()

    def process_schema(self):
        from django.apps import apps
        Employee = apps.get_model('workforce', 'Employee')
        User = get_user_model()
        
        try:
            employees_without_user = Employee.objects.filter(user__isnull=True)
            count = employees_without_user.count()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Could not query employees: {e}"))
            return

        if count == 0:
            self.stdout.write(self.style.SUCCESS("All employees already have user accounts in this schema."))
            return

        self.stdout.write(f"Found {count} employees without user accounts. Creating...")

        created_count = 0
        skipped_count = 0

        for employee in employees_without_user:
            if not employee.official_email:
                self.stdout.write(self.style.WARNING(f"Skipping {employee.employee_no} - No official email provided."))
                skipped_count += 1
                continue

            email = employee.official_email
            username = email.split('@')[0]
            base_username = username
            counter = 1
            
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1
            
            try:
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    first_name=employee.first_name,
                    last_name=employee.last_name,
                    password=employee.employee_no  # Default password is their employee number
                )
                
                # Set roles based on category
                if employee.employee_category == 'teaching':
                    user.is_lecturer = True
                else:
                    user.is_staff = True
                    
                user.save()
                
                employee.user = user
                employee.save()
                
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"Created user account for {employee.first_name} {employee.last_name} ({username})"))
            
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to create user for {employee.employee_no}: {str(e)}"))
                skipped_count += 1

        self.stdout.write(self.style.SUCCESS(f"\nDone! Created {created_count} user accounts. Skipped {skipped_count} employees."))
