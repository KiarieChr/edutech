from django.core.management.base import BaseCommand
from recruitment.models import InterviewRound, JobOpening

class Command(BaseCommand):
    help = 'Populates standard interview rounds for all job openings'

    def handle(self, *args, **kwargs):
        job_openings = JobOpening.objects.all()
        
        if not job_openings.exists():
            self.stdout.write(self.style.WARNING('No job openings found using default manager. Checking filtering...'))
            # If standard manager filters out non-published, try getting raw or check if any exist at all
            if JobOpening.objects.count() == 0:
                self.stdout.write(self.style.ERROR('No job openings exist in the database. Please create some job openings first.'))
                return

        created_count = 0
        
        standard_rounds = [
            {
                'sequence': 1,
                'round_name': 'Initial Screening',
                'round_type': InterviewRound.RoundType.TELEPHONIC,
                'duration_minutes': 30,
                'description': 'Basic screening of candidate background and availability'
            },
            {
                'sequence': 2,
                'round_name': 'Technical Interview',
                'round_type': InterviewRound.RoundType.TECHNICAL,
                'duration_minutes': 60,
                'description': 'In-depth assessment of technical skills'
            },
            {
                'sequence': 3,
                'round_name': 'Managerial Round',
                'round_type': InterviewRound.RoundType.VIDEO,
                'duration_minutes': 45,
                'description': 'Discussion with hiring manager'
            },
            {
                'sequence': 4,
                'round_name': 'HR Discussion',
                'round_type': InterviewRound.RoundType.HR,
                'duration_minutes': 30,
                'description': 'Salary negotiation and cultural fit'
            }
        ]

        for job in job_openings:
            # Check if rounds already exist for this job
            if job.interview_rounds.exists():
                self.stdout.write(f'Skipping {job.title} ({job.reference_number}) - already has rounds')
                continue

            self.stdout.write(f'Creating rounds for {job.title}...')
            
            for round_data in standard_rounds:
                InterviewRound.objects.create(
                    job_opening=job,
                    **round_data
                )
            
            created_count += 1

        self.stdout.write(self.style.SUCCESS(f'Successfully populated rounds for {created_count} job openings'))
