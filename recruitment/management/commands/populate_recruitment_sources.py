from django.core.management.base import BaseCommand
from recruitment.models import RecruitmentSource

class Command(BaseCommand):
    help = 'Populate default recruitment sources'

    def handle(self, *args, **kwargs):
        sources = [
            {
                'name': 'Proprietary Career Portal',
                'source_type': RecruitmentSource.SourceType.PORTAL,
                'website': 'https://careers.company.com'
            },
            {
                'name': 'LinkedIn',
                'source_type': RecruitmentSource.SourceType.SOCIAL,
                'website': 'https://linkedin.com'
            },
            {
                'name': 'Internal Referral',
                'source_type': RecruitmentSource.SourceType.REFERRAL,
                'notes': 'Employee referral program'
            },
            {
                'name': 'University Campus Drive',
                'source_type': RecruitmentSource.SourceType.CAMPUS,
                'notes': 'Fall semester recruitment'
            },
            {
                'name': 'Recruitment Agency Alpha',
                'source_type': RecruitmentSource.SourceType.AGENCY,
                'contact_person': 'John Doe',
                'contact_email': 'john@alphaagency.com'
            },
            {
                'name': 'Newspaper Ad',
                'source_type': RecruitmentSource.SourceType.NEWSPAPER,
            }
        ]

        count = 0
        for source_data in sources:
            source, created = RecruitmentSource.objects.get_or_create(
                name=source_data['name'],
                defaults=source_data
            )
            if created:
                count += 1
                self.stdout.write(self.style.SUCCESS(f'Created source: {source.name}'))
            else:
                self.stdout.write(f'Source already exists: {source.name}')

        self.stdout.write(self.style.SUCCESS(f'Successfully populated {count} recruitment sources'))
