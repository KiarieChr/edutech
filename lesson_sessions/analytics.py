"""
Analytics Engine for the Lesson Sessions module.

All aggregations are derived from two tables:
  - scheduled_lessons.PlannedLesson  (what was expected)
  - lesson_sessions.LessonSession    (what actually happened)

Never mixed with timetable (planning) data.
"""
from django.db.models import Count, Q, Sum, F, Avg
from django.db.models.functions import TruncDate

from .models import LessonSession, TeacherSubstitution, CurriculumCoverage


class AcademicAnalytics:

    @staticmethod
    def planned_vs_actual(class_session_id, from_date, to_date):
        """
        Summary of planned vs executed lessons for a date range.
        Optionally scoped to a specific class_session.
        """
        from scheduled_lessons.models import PlannedLesson

        qs = PlannedLesson.objects.filter(date__range=(from_date, to_date))
        if class_session_id:
            qs = qs.filter(class_session_id=class_session_id)

        total     = qs.count()
        executed  = qs.filter(status='executed').count()
        missed    = qs.filter(status='missed').count()
        cancelled = qs.filter(status='cancelled').count()
        pending   = qs.filter(status='pending').count()
        holiday   = qs.filter(status='holiday').count()

        return {
            'total_planned':   total,
            'executed':        executed,
            'missed':          missed,
            'cancelled':       cancelled,
            'pending':         pending,
            'holiday':         holiday,
            'execution_rate':  round((executed / max(total, 1)) * 100, 1),
            'miss_rate':       round((missed   / max(total, 1)) * 100, 1),
        }

    @staticmethod
    def teacher_workload(teacher_id, from_date, to_date):
        """
        How many lessons a teacher conducted in the date range, including
        minutes delivered and how many were as a substitute.
        """
        sessions = LessonSession.objects.filter(
            actual_teacher_id=teacher_id,
            date__range=(from_date, to_date),
            status='completed'
        )
        total_minutes = sum(s.actual_duration_minutes or 0 for s in sessions)
        substitution_count = TeacherSubstitution.objects.filter(
            substitute_teacher_id=teacher_id,
            planned_lesson__date__range=(from_date, to_date)
        ).count()
        sessions_missed = TeacherSubstitution.objects.filter(
            original_teacher_id=teacher_id,
            planned_lesson__date__range=(from_date, to_date)
        ).count()

        return {
            'sessions_conducted':    sessions.count(),
            'total_minutes_taught':  total_minutes,
            'substitute_sessions':   substitution_count,
            'sessions_missed':       sessions_missed,
        }

    @staticmethod
    def curriculum_coverage_summary(class_session_id):
        """
        Per-subject completion % for a given class_session (Grade+Term container).
        """
        if not class_session_id:
            return []
        from timetable.models import Subject, CurriculumUnit

        subjects = Subject.objects.filter(
            curriculum_units__class_session_id=class_session_id
        ).distinct()

        return [
            {
                'subject_id':          s.id,
                'subject_name':        s.name,
                'subject_code':        s.code,
                'completion_percent':  CurriculumCoverage.subject_completion_percent(
                    s.id, class_session_id
                ),
            }
            for s in subjects
        ]

    @staticmethod
    def substitute_frequency_report(from_date, to_date):
        """
        Ranks teachers by how often they were substituted out in the date range.
        """
        return list(
            TeacherSubstitution.objects.filter(
                planned_lesson__date__range=(from_date, to_date)
            ).values(
                teacher_id=F('original_teacher_id'),
                teacher_name=F('original_teacher__first_name'),
                teacher_last=F('original_teacher__last_name'),
            ).annotate(
                substitution_count=Count('id')
            ).order_by('-substitution_count')
        )

    @staticmethod
    def daily_timeline(class_session_id, target_date):
        """
        Full day timeline for a class_session — planned lessons with execution status.
        Used to power the "Today's Sessions" panel on the dashboard.
        """
        from scheduled_lessons.models import PlannedLesson

        planned = PlannedLesson.objects.filter(
            class_session_id=class_session_id,
            date=target_date,
        ).select_related(
            'subject', 'expected_teacher', 'room', 'lesson_session'
        ).order_by('scheduled_start_time')

        result = []
        for pl in planned:
            entry = {
                'planned_lesson_id':   pl.id,
                'subject_name':        pl.subject.name,
                'subject_color':       pl.subject.color_hex,
                'expected_teacher':    (
                    f"{pl.expected_teacher.first_name} {pl.expected_teacher.last_name}".strip()
                ),
                'room':                pl.room.name if pl.room else None,
                'scheduled_start':     pl.scheduled_start_time,
                'scheduled_end':       pl.scheduled_end_time,
                'status':              pl.status,
                'lesson_session':      None,
            }
            try:
                ls = pl.lesson_session
                entry['lesson_session'] = {
                    'id':                ls.id,
                    'actual_teacher':    (
                        f"{ls.actual_teacher.first_name} {ls.actual_teacher.last_name}".strip()
                    ),
                    'actual_start':      ls.actual_start_time,
                    'actual_end':        ls.actual_end_time,
                    'topic_taught':      ls.topic_taught,
                    'status':            ls.status,
                    'delivery_mode':     ls.delivery_mode,
                    'attendance_rate':   None,
                }
                # Attendance summary
                total = ls.attendances.count()
                if total:
                    present = ls.attendances.filter(
                        status__in=('present', 'late')
                    ).count()
                    entry['lesson_session']['attendance_rate'] = round(
                        present / total * 100, 1
                    )
            except LessonSession.DoesNotExist:
                pass
            except AttributeError:
                pass
            result.append(entry)

        return result
