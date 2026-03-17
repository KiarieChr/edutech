"""
Management command: generate_planned_lessons

Reads all active TimetableSlots and generates PlannedLesson records for the
specified date range. Respects TimetableException (holidays/closures) and
the slot's effective_from/effective_until validity window.

Usage examples:
    python manage.py generate_planned_lessons
    python manage.py generate_planned_lessons --from-date 2026-03-01 --days 30
    python manage.py generate_planned_lessons --class-session 5 --days 7
    python manage.py generate_planned_lessons --from-date 2026-03-01 --days 90 --force
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date, timedelta

from timetable.models import TimetableSlot, TimetableException
from scheduled_lessons.models import PlannedLesson


class Command(BaseCommand):
    help = "Generate PlannedLesson records from TimetableSlots for a date range."

    def add_arguments(self, parser):
        parser.add_argument(
            '--from-date', type=str, default=None,
            help='Start date YYYY-MM-DD (default: today)',
        )
        parser.add_argument(
            '--days', type=int, default=1,
            help='Number of calendar days to generate forward (default: 1)',
        )
        parser.add_argument(
            '--class-session', type=int, default=None,
            help='Restrict generation to a specific ClassSession ID',
        )
        parser.add_argument(
            '--force', action='store_true',
            help='Delete existing pending future PlannedLessons before regenerating',
        )

    def handle(self, *args, **options):
        start_date = (
            date.fromisoformat(options['from_date'])
            if options['from_date']
            else date.today()
        )
        days       = options['days']
        forced     = options['force']

        dates_to_generate = [start_date + timedelta(days=i) for i in range(days)]

        # Load all exceptions upfront (avoid N+1 in the loop)
        all_exceptions = list(TimetableException.objects.prefetch_related('class_sessions').all())

        # Determine which dates are globally blocked
        global_blocked_dates = set()
        for ex in all_exceptions:
            if ex.affects_all_classes:
                current = ex.date_from
                while current <= ex.date_to:
                    global_blocked_dates.add(current)
                    current += timedelta(days=1)

        # Build class-session-specific blocked dates: {class_session_id: {date, ...}}
        from collections import defaultdict
        session_blocked_dates = defaultdict(set)
        for ex in all_exceptions:
            if not ex.affects_all_classes:
                for cs in ex.class_sessions.all():
                    current = ex.date_from
                    while current <= ex.date_to:
                        session_blocked_dates[cs.id].add(current)
                        current += timedelta(days=1)

        # Load timetable slots
        slots_qs = TimetableSlot.objects.filter(is_active=True).select_related(
            'class_session', 'subject', 'teacher', 'room'
        )
        if options['class_session']:
            slots_qs = slots_qs.filter(class_session_id=options['class_session'])

        slots = list(slots_qs)

        created  = 0
        skipped  = 0
        holiday  = 0
        regenerated = 0

        for target_date in dates_to_generate:
            day_of_week = target_date.weekday()  # 0=Monday, 5=Saturday

            # Only process weekdays (Monday–Saturday) unless slot explicitly targets Sunday
            if day_of_week == 6:
                continue

            for slot in slots:
                # Skip slots that are not valid for this date
                if slot.effective_from > target_date:
                    continue
                if slot.effective_until and slot.effective_until < target_date:
                    continue
                # Skip slots not scheduled for this day
                if slot.day_of_week != day_of_week:
                    continue

                # Check if this date is blocked
                is_holiday = (
                    target_date in global_blocked_dates
                    or target_date in session_blocked_dates.get(slot.class_session_id, set())
                )

                if forced:
                    # Delete pending future records before regenerating
                    deleted, _ = PlannedLesson.objects.filter(
                        timetable_slot=slot,
                        date=target_date,
                        status='pending'
                    ).delete()
                    regenerated += deleted

                planned_status = 'holiday' if is_holiday else 'pending'

                obj, was_created = PlannedLesson.objects.get_or_create(
                    timetable_slot=slot,
                    date=target_date,
                    defaults={
                        'status':                planned_status,
                        'class_session':         slot.class_session,
                        'subject':               slot.subject,
                        'room':                  slot.room,
                        'expected_teacher':      slot.teacher,
                        'scheduled_start_time':  slot.start_time,
                        'scheduled_end_time':    slot.end_time,
                        'generated_by':          'scheduler',
                    }
                )
                if was_created:
                    if is_holiday:
                        holiday += 1
                    else:
                        created += 1
                else:
                    skipped += 1

        date_range = (
            f"{dates_to_generate[0]}"
            if len(dates_to_generate) == 1
            else f"{dates_to_generate[0]} → {dates_to_generate[-1]}"
        )
        msg = (
            f"Created: {created} | Holiday: {holiday} | "
            f"Skipped (existing): {skipped}"
        )
        if forced:
            msg += f" | Regenerated: {regenerated}"
        msg += f" | Range: {date_range}"

        self.stdout.write(self.style.SUCCESS(msg))
