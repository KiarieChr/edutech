from django.core.management.base import BaseCommand
from student_settings.models import StudentStatus, DemographicConfig, AdmissionConfig, PromotionRule

class Command(BaseCommand):
    help = 'Populate initial student settings data'

    def handle(self, *args, **options):
        # 1. Default Statuses
        statuses = [
            ('Active', True),
            ('Alumni', False),
            ('Transferred', False),
            ('Suspended', False),
            ('Expelled', False),
            ('Deceased', False),
            ('On Leave', False),
        ]
        for name, active in statuses:
            StudentStatus.objects.get_or_create(name=name, defaults={'is_active_state': active})

        # 2. Demographic Config
        fields = [
            'Date of Birth',
            'Birth Certificate Number',
            'Nationality',
            'Religion',
            'Special Needs',
            'Guardian Information',
            'Student Photo',
        ]
        for field in fields:
            DemographicConfig.objects.get_or_create(field_name=field, defaults={'is_required': True})

        # 3. Global Admission Config
        AdmissionConfig.objects.get_or_create(id=1, defaults={'prefix': 'SCH/'})

        # 4. Promotion Rules
        PromotionRule.objects.get_or_create(id=1, defaults={'promotion_method': 'manual'})

        self.stdout.write(self.style.SUCCESS('Successfully populated initial settings'))
