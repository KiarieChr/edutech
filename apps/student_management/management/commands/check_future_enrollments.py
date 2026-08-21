from django.core.management.base import BaseCommand
from django.utils import timezone
from student_settings.models import Enrollment, Term
from student_management.models import Student

class Command(BaseCommand):
    help = 'Check for students admitted in the past whose current enrollment records are mistakenly in a future term.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--auto-fix',
            action='store_true',
            help='Automatically generate missing historical enrollments for missed terms.',
        )

    def handle(self, *args, **kwargs):
        auto_fix = kwargs['auto_fix']
        today = timezone.now().date()
        
        self.stdout.write(self.style.NOTICE(f'Checking for future enrollments as of {today}...'))
        
        # We look for currently active enrollments
        active_enrollments = Enrollment.objects.filter(
            is_active=True,
            is_deleted=False
        ).select_related('student', 'term')
        
        anomalies_found = 0
        
        for enr in active_enrollments:
            # We assume term start_date is set. If not, skip.
            if not enr.term or not enr.term.start_date:
                continue
                
            # Check if term is in the future but the student was admitted in the past
            if enr.term.start_date > today:
                student = enr.student
                # Assuming admission date can be inferred from student creation or admission profile
                # If admission date is before today, but their active term hasn't started...
                admission_date = getattr(student, 'admission_date', student.created_at.date())
                
                if admission_date <= today:
                    self.stdout.write(
                        self.style.WARNING(
                            f"[ANOMALY DETECTED] Student: {student.full_name} ({student.admission_number}) "
                            f"admitted on {admission_date} but their ACTIVE term '{enr.term.name}' "
                            f"starts in the future on {enr.term.start_date}."
                        )
                    )
                    anomalies_found += 1
                    
                    if auto_fix:
                        self.stdout.write(self.style.NOTICE(f'  -> Auto-fixing historical records for {student.full_name}...'))
                        # Find all terms between admission_date and the active future term's start_date
                        missed_terms = Term.objects.filter(
                            start_date__gte=admission_date,
                            start_date__lt=enr.term.start_date
                        ).order_by('start_date')
                        
                        created_count = 0
                        for m_term in missed_terms:
                            # Avoid duplicates
                            exists = Enrollment.objects.filter(student=student, term=m_term).exists()
                            if not exists:
                                Enrollment.objects.create(
                                    student=student,
                                    intake=enr.intake,
                                    academic_year=m_term.academic_year,
                                    term=m_term,
                                    curriculum=enr.curriculum,
                                    curriculum_level=enr.curriculum_level,
                                    grade=enr.grade, # Fallback to current grade as requested
                                    stream=enr.stream,
                                    campus=enr.campus,
                                    enrollment_type='promotion',
                                    status='completed',
                                    is_active=False,
                                    enrollment_date=m_term.start_date
                                )
                                created_count += 1
                        
                        self.stdout.write(self.style.SUCCESS(f'  -> Successfully generated {created_count} historical enrollments.'))

        if anomalies_found == 0:
            self.stdout.write(self.style.SUCCESS('No anomalies found! All active enrollments look temporally correct.'))
        else:
            self.stdout.write(self.style.ERROR(f'Finished scan. Found {anomalies_found} anomalies.'))
