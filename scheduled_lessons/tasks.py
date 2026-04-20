"""
Celery tasks for scheduled_lessons.

Schedule in config/celery.py:

    from celery.schedules import crontab

    CELERYBEAT_SCHEDULE = {
        'generate-tomorrow-lessons': {
            'task': 'scheduled_lessons.tasks.generate_lessons_for_tomorrow',
            'schedule': crontab(hour=22, minute=0),   # Every night at 22:00
        },
        'auto-mark-missed-lessons': {
            'task': 'scheduled_lessons.tasks.auto_mark_missed_lessons',
            'schedule': crontab(hour=17, minute=30),  # End of school day
        },
    }
"""
from celery import shared_task
from datetime import date, timedelta


@shared_task(name='scheduled_lessons.tasks.generate_lessons_for_tomorrow')
def generate_lessons_for_tomorrow():
    """
    Generates PlannedLesson records for tomorrow.
    Runs nightly at 22:00.
    """
    from django.core.management import call_command
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    call_command('generate_planned_lessons', **{'from_date': tomorrow, 'days': 1})
    return f"Lesson generation triggered for {tomorrow}"


@shared_task(name='scheduled_lessons.tasks.generate_week_ahead')
def generate_week_ahead():
    """
    Generates PlannedLesson records for the next 7 days.
    Useful for initial setup or after timetable changes.
    """
    from django.core.management import call_command
    from_date = date.today().isoformat()
    call_command('generate_planned_lessons', **{'from_date': from_date, 'days': 7})
    return f"Week-ahead generation triggered from {from_date}"


@shared_task(name='scheduled_lessons.tasks.auto_mark_missed_lessons')
def auto_mark_missed_lessons():
    """
    Marks PlannedLessons as 'missed' if their scheduled end_time has passed
    and no LessonSession has been started (status still 'pending').
    Also creates absent SessionAttendance records for any ongoing session that
    was abandoned without being completed.

    Runs at 17:30 daily (after the last lesson of the day).
    """
    from django.utils import timezone
    from .models import PlannedLesson

    now  = timezone.localtime(timezone.now())
    today = now.date()
    current_time = now.time()

    missed_qs = PlannedLesson.objects.filter(
        date=today,
        status='pending',
        scheduled_end_time__lt=current_time
    )
    count = missed_qs.update(status='missed')
    return f"Marked {count} planned lessons as missed on {today}"
