from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.shortcuts import get_object_or_404

from .models import LessonSession, SessionAttendance, TeacherSubstitution, CurriculumCoverage
from .serializers import (
    LessonSessionSerializer, StartSessionSerializer, CompleteSessionSerializer,
    SessionAttendanceSerializer, TeacherSubstitutionSerializer, CurriculumCoverageSerializer,
)


class LessonSessionViewSet(viewsets.ModelViewSet):
    serializer_class = LessonSessionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['date', 'status', 'class_session', 'subject', 'actual_teacher']
    ordering_fields = ['date', 'actual_start_time', 'status']
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        return LessonSession.objects.select_related(
            'planned_lesson', 'actual_teacher', 'class_session',
            'subject', 'room', 'curriculum_unit',
        ).prefetch_related('attendances')

    @action(detail=False, methods=['post'], url_path='start')
    def start(self, request):
        """
        Start a lesson session.

        If planned_lesson_id is provided, derives context from the PlannedLesson.
        If not provided (ad-hoc), class_session_id and subject_id must be given.

        Automatically creates SessionAttendance records (default: absent) for
        all active students enrolled in the class_session.
        """
        serializer = StartSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Conflict: teacher already in another ongoing session
        if LessonSession.objects.filter(
            actual_teacher=request.user, status='ongoing'
        ).exists():
            return Response(
                {'error': 'You already have an ongoing session. End it before starting another.'},
                status=400
            )

        planned = None
        if data.get('planned_lesson_id'):
            from scheduled_lessons.models import PlannedLesson
            planned = get_object_or_404(PlannedLesson, pk=data['planned_lesson_id'])
            if planned.status not in ('pending',):
                return Response(
                    {'error': f"Planned lesson status is '{planned.status}'. Cannot start."},
                    status=400
                )
            class_session_id = planned.class_session_id
            subject_id       = planned.subject_id
            room_id          = planned.room_id
        else:
            class_session_id = data['class_session_id']
            subject_id       = data['subject_id']
            room_id          = data.get('room_id')

        lesson = LessonSession.objects.create(
            planned_lesson    = planned,
            actual_teacher    = request.user,
            actual_start_time = timezone.now(),
            class_session_id  = class_session_id,
            subject_id        = subject_id,
            room_id           = room_id,
            date              = timezone.localdate(),
            delivery_mode     = data.get('delivery_mode', 'physical'),
            started_by        = request.user,
            status            = 'ongoing',
        )

        # Auto-create absent attendance for all enrolled students
        from academics.models import StudentSessionEnrollment
        enrollments = StudentSessionEnrollment.objects.filter(
            session_id=class_session_id, status='active'
        ).select_related('student')

        SessionAttendance.objects.bulk_create([
            SessionAttendance(
                lesson_session=lesson,
                student=e.student,
                status='absent',
            )
            for e in enrollments
        ], ignore_conflicts=True)

        return Response(LessonSessionSerializer(lesson).data, status=201)

    @action(detail=True, methods=['post'], url_path='complete')
    def complete(self, request, pk=None):
        """
        End a lesson session, lock attendance, update planned lesson and curriculum coverage.
        """
        lesson = self.get_object()
        if lesson.status != 'ongoing':
            return Response(
                {'error': f"Cannot complete a session with status '{lesson.status}'."},
                status=400
            )

        serializer = CompleteSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        curriculum_unit = None
        if d.get('curriculum_unit_id'):
            from timetable.models import CurriculumUnit
            curriculum_unit = get_object_or_404(CurriculumUnit, pk=d['curriculum_unit_id'])

        lesson.complete(
            completed_by_user=request.user,
            topic_taught=d.get('topic_taught', ''),
            lesson_notes=d.get('lesson_notes', ''),
            homework_given=d.get('homework_given', ''),
            curriculum_unit=curriculum_unit,
        )
        return Response(LessonSessionSerializer(lesson).data)

    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel(self, request, pk=None):
        lesson = self.get_object()
        if lesson.status not in ('ongoing',):
            return Response(
                {'error': f"Cannot cancel a session with status '{lesson.status}'."},
                status=400
            )
        lesson.status = 'cancelled'
        lesson.cancellation_reason = request.data.get('reason', '')
        lesson.save(update_fields=['status', 'cancellation_reason'])
        return Response(LessonSessionSerializer(lesson).data)

    @action(detail=True, methods=['get', 'post'], url_path='attendance')
    def attendance(self, request, pk=None):
        lesson = self.get_object()

        if request.method == 'GET':
            records = lesson.attendances.select_related('student', 'student__student')
            return Response(SessionAttendanceSerializer(records, many=True).data)

        if request.method == 'POST':
            # Bulk update attendance: [{ student_id, status, minutes_late, notes }, ...]
            if lesson.status == 'completed':
                return Response({'error': 'Attendance is locked for completed sessions.'}, status=400)
            updates = request.data if isinstance(request.data, list) else [request.data]
            results = []
            for item in updates:
                record = get_object_or_404(
                    SessionAttendance, lesson_session=lesson, student_id=item['student_id']
                )
                record.status       = item.get('status', record.status)
                record.minutes_late = item.get('minutes_late', record.minutes_late)
                record.notes        = item.get('notes', record.notes)
                record.marked_by    = request.user
                record.save()
                results.append(SessionAttendanceSerializer(record).data)
            return Response(results)

    @action(detail=False, methods=['get'], url_path='today')
    def today(self, request):
        """My sessions today (for the authenticated teacher)."""
        today = timezone.localdate()
        qs = self.get_queryset().filter(actual_teacher=request.user, date=today)
        return Response(LessonSessionSerializer(qs, many=True).data)

    @action(detail=False, methods=['get'], url_path='analytics')
    def analytics(self, request):
        """
        Planned vs actual analytics for a class_session and date range.
        Query: ?class_session=<id>&from_date=YYYY-MM-DD&to_date=YYYY-MM-DD
        """
        from .analytics import AcademicAnalytics
        from datetime import date

        class_session_id = request.query_params.get('class_session')
        from_date = request.query_params.get('from_date', date.today().replace(day=1).isoformat())
        to_date   = request.query_params.get('to_date', date.today().isoformat())

        return Response({
            'planned_vs_actual': AcademicAnalytics.planned_vs_actual(
                class_session_id, from_date, to_date
            ),
            'curriculum_coverage': AcademicAnalytics.curriculum_coverage_summary(
                class_session_id
            ) if class_session_id else [],
        })


class TeacherSubstitutionViewSet(viewsets.ModelViewSet):
    serializer_class = TeacherSubstitutionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['planned_lesson', 'original_teacher', 'substitute_teacher', 'reason']
    ordering_fields = ['requested_at', 'planned_lesson__date']
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_queryset(self):
        return TeacherSubstitution.objects.select_related(
            'planned_lesson', 'original_teacher', 'substitute_teacher', 'approved_by'
        )

    def perform_create(self, serializer):
        serializer.save(approved_by=self.request.user)


class CurriculumCoverageViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CurriculumCoverageSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['curriculum_unit', 'lesson_session']

    def get_queryset(self):
        return CurriculumCoverage.objects.select_related(
            'curriculum_unit', 'curriculum_unit__subject', 'curriculum_unit__class_session',
            'lesson_session',
        )

    @action(detail=False, methods=['get'], url_path='subject-summary')
    def subject_summary(self, request):
        """
        Returns completion % per subject for a given class_session.
        Query: ?class_session=<id>
        """
        class_session_id = request.query_params.get('class_session')
        if not class_session_id:
            return Response({'error': 'class_session query param required'}, status=400)

        from .analytics import AcademicAnalytics
        return Response(AcademicAnalytics.curriculum_coverage_summary(class_session_id))


class TeacherWorkloadView(APIView):
    """
    GET /api/lesson-sessions/teacher-workload/?teacher=<id>&from_date=&to_date=
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .analytics import AcademicAnalytics
        from datetime import date
        teacher_id = request.query_params.get('teacher', request.user.pk)
        from_date  = request.query_params.get('from_date', date.today().replace(day=1).isoformat())
        to_date    = request.query_params.get('to_date', date.today().isoformat())
        return Response(AcademicAnalytics.teacher_workload(teacher_id, from_date, to_date))
