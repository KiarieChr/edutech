"""
setup_periods.py — Management command for setting up default time periods.

Creates the standard school day structure with:
- Morning periods
- Break times
- Afternoon periods

Usage:
------
    # Create default 8-period day
    python manage.py setup_periods
    
    # Clear and recreate
    python manage.py setup_periods --clear
    
    # Custom lesson duration (40 minutes)
    python manage.py setup_periods --lesson-duration=40
    
    # Different start time
    python manage.py setup_periods --start-time=8:00
"""
from django.core.management.base import BaseCommand
from datetime import time, datetime, timedelta


class Command(BaseCommand):
    help = 'Set up default time periods for the school day'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing periods before creating new ones'
        )
        parser.add_argument(
            '--start-time',
            type=str,
            default='07:30',
            help='School day start time (default: 07:30)'
        )
        parser.add_argument(
            '--lesson-duration',
            type=int,
            default=40,
            help='Lesson duration in minutes (default: 40)'
        )
        parser.add_argument(
            '--break-duration',
            type=int,
            default=20,
            help='Short break duration in minutes (default: 20)'
        )
        parser.add_argument(
            '--lunch-duration',
            type=int,
            default=60,
            help='Lunch break duration in minutes (default: 60)'
        )
        parser.add_argument(
            '--periods-before-break',
            type=int,
            default=3,
            help='Number of periods before morning break (default: 3)'
        )
        parser.add_argument(
            '--periods-before-lunch',
            type=int,
            default=5,
            help='Total periods before lunch (default: 5)'
        )
        parser.add_argument(
            '--total-periods',
            type=int,
            default=8,
            help='Total lesson periods per day (default: 8)'
        )

    def handle(self, *args, **options):
        from timetable.models import TimePeriod

        if options['clear']:
            deleted, _ = TimePeriod.objects.all().delete()
            self.stdout.write(f"Cleared {deleted} existing periods")

        # Parse start time
        start_dt = datetime.strptime(options['start_time'], '%H:%M')
        current_time = start_dt

        lesson_duration = timedelta(minutes=options['lesson_duration'])
        break_duration = timedelta(minutes=options['break_duration'])
        lunch_duration = timedelta(minutes=options['lunch_duration'])

        periods_created = []
        order = 1
        lesson_number = 1

        total_periods = options['total_periods']
        break_after = options['periods_before_break']
        lunch_after = options['periods_before_lunch']

        while lesson_number <= total_periods:
            # Create lesson period
            period_end = current_time + lesson_duration
            
            period = TimePeriod.objects.create(
                name=f'Period {lesson_number}',
                short_name=f'P{lesson_number}',
                start_time=current_time.time(),
                end_time=period_end.time(),
                period_type='lesson',
                is_schedulable=True,
                order=order,
            )
            periods_created.append(period)
            self.stdout.write(
                f"  Created: {period.name} "
                f"({period.start_time.strftime('%H:%M')}-{period.end_time.strftime('%H:%M')})"
            )

            current_time = period_end
            order += 1
            lesson_number += 1

            # Add break after specified lessons
            if lesson_number - 1 == break_after and lesson_number <= total_periods:
                break_end = current_time + break_duration
                break_period = TimePeriod.objects.create(
                    name='Morning Break',
                    short_name='Break',
                    start_time=current_time.time(),
                    end_time=break_end.time(),
                    period_type='break',
                    is_schedulable=False,
                    order=order,
                )
                periods_created.append(break_period)
                self.stdout.write(self.style.WARNING(
                    f"  Created: {break_period.name} "
                    f"({break_period.start_time.strftime('%H:%M')}-{break_period.end_time.strftime('%H:%M')})"
                ))
                current_time = break_end
                order += 1

            # Add lunch after specified lessons
            elif lesson_number - 1 == lunch_after and lesson_number <= total_periods:
                lunch_end = current_time + lunch_duration
                lunch_period = TimePeriod.objects.create(
                    name='Lunch Break',
                    short_name='Lunch',
                    start_time=current_time.time(),
                    end_time=lunch_end.time(),
                    period_type='lunch',
                    is_schedulable=False,
                    order=order,
                )
                periods_created.append(lunch_period)
                self.stdout.write(self.style.WARNING(
                    f"  Created: {lunch_period.name} "
                    f"({lunch_period.start_time.strftime('%H:%M')}-{lunch_period.end_time.strftime('%H:%M')})"
                ))
                current_time = lunch_end
                order += 1

        # Summary
        self.stdout.write(self.style.SUCCESS(
            f"\nCreated {len(periods_created)} periods"
        ))
        self.stdout.write(f"School day: {options['start_time']} - {current_time.strftime('%H:%M')}")
