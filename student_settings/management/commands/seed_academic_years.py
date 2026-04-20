from datetime import date
from django.core.management.base import BaseCommand
from student_settings.models import AcademicYear, Term


class Command(BaseCommand):
    help = 'Seed academic years (2015–2029) and 3 terms per year'

    def handle(self, *args, **options):
        current_year = date.today().year
        start = 2015
        end = 2029

        created_years = 0
        created_terms = 0

        for yr in range(start, end + 1):
            name = str(yr)

            year_obj, was_created = AcademicYear.objects.get_or_create(
                name=name,
                defaults={
                    'start_date': date(yr, 1, 1),
                    'end_date': date(yr, 12, 31),
                    'is_current': (yr == current_year),
                    'status': 'archived' if yr < current_year else 'active',
                },
            )

            if was_created:
                created_years += 1
                self.stdout.write(f'  + AcademicYear {name}')
            else:
                self.stdout.write(f'  = AcademicYear {name} (already exists)')

            # ── 3 terms per year ──────────────────────────────
            terms = [
                {'name': 'Term 1', 'order': 1,
                 'start_date': date(yr, 1, 6),   'end_date': date(yr, 4, 11)},
                {'name': 'Term 2', 'order': 2,
                 'start_date': date(yr, 5, 5),    'end_date': date(yr, 8, 1)},
                {'name': 'Term 3', 'order': 3,
                 'start_date': date(yr, 9, 1),    'end_date': date(yr, 11, 21)},
            ]

            for t in terms:
                is_current_term = (
                    yr == current_year
                    and t['start_date'] <= date.today() <= t['end_date']
                )

                term_obj, t_created = Term.objects.get_or_create(
                    academic_year=year_obj,
                    order=t['order'],
                    defaults={
                        'name': t['name'],
                        'start_date': t['start_date'],
                        'end_date': t['end_date'],
                        'is_current': is_current_term,
                        'status': 'closed' if yr < current_year else 'active',
                    },
                )

                if t_created:
                    created_terms += 1

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Done — {created_years} academic years created, '
            f'{created_terms} terms created '
            f'({start}–{end})'
        ))
