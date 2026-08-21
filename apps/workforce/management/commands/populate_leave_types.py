from django.core.management.base import BaseCommand
from workforce.models import LeaveType

class Command(BaseCommand):
    help = 'Populates the database with default Leave Types'

    def handle(self, *args, **kwargs):
        defaults = [
            {
                'code': 'ANNUAL',
                'name': 'Annual Leave',
                'description': 'Standard paid time off',
                'category': 'paid',
                'is_statutory': True,
                'max_days_per_year': 21,
                'gender_specific': 'all',
                'requires_medical_certificate': False,
                'advance_notice_days': 7,
                'accrual_rate': 1.75,
                'accrual_method': 'monthly'
            },
            {
                'code': 'SICK',
                'name': 'Sick Leave',
                'description': 'Medical leave',
                'category': 'paid',
                'is_statutory': True,
                'max_days_per_year': 14,
                'gender_specific': 'all',
                'requires_medical_certificate': True,
                'advance_notice_days': 0,
                'accrual_rate': 1.17,
                'accrual_method': 'monthly'
            },
            {
                'code': 'MATERNITY',
                'name': 'Maternity Leave',
                'description': 'Maternity leave for mothers',
                'category': 'paid',
                'is_statutory': True,
                'max_days_per_year': 90,
                'gender_specific': 'female',
                'requires_medical_certificate': True,
                'advance_notice_days': 30,
                'accrual_rate': 0.00,
                'accrual_method': 'yearly'
            }
        ]
        
        created_count = 0
        self.stdout.write(self.style.NOTICE('Starting leave types population...'))
        
        for data in defaults:
            obj, created = LeaveType.objects.get_or_create(
                code=data['code'],
                defaults=data
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created leave type: {obj.name}"))
                created_count += 1
            else:
                self.stdout.write(self.style.WARNING(f"Leave type {obj.name} already exists."))
                
        self.stdout.write(self.style.SUCCESS(f'\nSuccessfully populated {created_count} new leave types.'))
