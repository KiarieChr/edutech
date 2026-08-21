from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction

from .models import (
    Subject, Room, TimetableSlot, TimetableException, CurriculumUnit,
    TimePeriod, WorkAllocation, TeacherAvailability, TimetableLock, TimetableVersion,
    GradeSubjectMapping
)
from .serializers import (
    SubjectSerializer, RoomSerializer, TimetableSlotSerializer,
    TimetableExceptionSerializer, CurriculumUnitSerializer,
    TimePeriodSerializer, WorkAllocationSerializer, WorkAllocationCreateSerializer,
    TeacherAvailabilitySerializer, TimetableLockSerializer,
    TimetableVersionSerializer, TimetableVersionListSerializer,
    TimetableSlotCreateSerializer, TimetableSlotDetailSerializer,
    SchedulingResultSerializer, GradeSubjectMappingSerializer,
)


class SubjectViewSet(viewsets.ModelViewSet):
    queryset = Subject.objects.select_related('curriculum', 'curriculum_level')
    serializer_class = SubjectSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['curriculum', 'curriculum_level', 'is_active']
    search_fields = ['name', 'code']
    ordering_fields = ['name', 'code']


class GradeSubjectMappingViewSet(viewsets.ModelViewSet):
    queryset = GradeSubjectMapping.objects.select_related('grade', 'subject')
    serializer_class = GradeSubjectMappingSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['grade', 'subject', 'is_core']
    
    @action(detail=False, methods=['post'], url_path='bulk-update')
    def bulk_update(self, request):
        grade_id = request.data.get('grade')
        subject_ids = request.data.get('subjects', [])
        
        if not grade_id:
            return Response({'error': 'grade is required'}, status=status.HTTP_400_BAD_REQUEST)
            
        with transaction.atomic():
            GradeSubjectMapping.objects.filter(grade_id=grade_id).delete()
            mappings = [
                GradeSubjectMapping(grade_id=grade_id, subject_id=s_id)
                for s_id in subject_ids
            ]
            GradeSubjectMapping.objects.bulk_create(mappings)
            
        return Response({'status': 'success', 'mapped_count': len(mappings)})


class RoomViewSet(viewsets.ModelViewSet):
    queryset = Room.objects.select_related('campus')
    serializer_class = RoomSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['room_type', 'campus', 'is_active']
    search_fields = ['name']


class TimetableSlotViewSet(viewsets.ModelViewSet):
    serializer_class = TimetableSlotSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['class_session', 'subject', 'teacher', 'day_of_week', 'is_active']
    search_fields = ['subject__name', 'subject__code']
    ordering_fields = ['day_of_week', 'start_time']

    def get_queryset(self):
        return TimetableSlot.objects.select_related(
            'class_session', 'subject', 'teacher', 'room'
        ).filter(is_active=True)

    @action(detail=False, methods=['post'], url_path='replace-slot')
    def replace_slot(self, request):
        """
        Mid-term timetable edit endpoint.
        Expires the old slot and creates a new one, then triggers regeneration
        of future PlannedLessons.

        Payload: { old_slot_id, ...new_slot_fields }
        """
        from django.utils import timezone
        from datetime import timedelta

        old_slot_id = request.data.get('old_slot_id')
        if not old_slot_id:
            return Response({'error': 'old_slot_id is required'}, status=400)

        try:
            old_slot = TimetableSlot.objects.get(pk=old_slot_id, is_active=True)
        except TimetableSlot.DoesNotExist:
            return Response({'error': 'Slot not found'}, status=404)

        today = timezone.localdate()

        # Expire the old slot
        old_slot.effective_until = today - timedelta(days=1)
        old_slot.is_active = False
        old_slot.save(update_fields=['effective_until', 'is_active'])

        # Create new slot
        new_data = {k: v for k, v in request.data.items() if k != 'old_slot_id'}
        new_data['effective_from'] = str(today)
        new_data['created_by'] = request.user.pk

        serializer = self.get_serializer(data=new_data)
        serializer.is_valid(raise_exception=True)
        new_slot = serializer.save()

        # Delete future pending PlannedLessons for the old slot and regenerate
        from scheduled_lessons.models import PlannedLesson
        deleted_count, _ = PlannedLesson.objects.filter(
            timetable_slot=old_slot,
            date__gte=today,
            status='pending'
        ).delete()

        # Trigger regeneration for the next 90 days from new slot
        from django.core.management import call_command
        call_command(
            'generate_planned_lessons',
            **{'from_date': str(today), 'days': 90, 'class_session': old_slot.class_session_id}
        )

        return Response({
            'old_slot_expired': old_slot_id,
            'new_slot': TimetableSlotSerializer(new_slot).data,
            'planned_lessons_deleted': deleted_count,
            'regeneration': 'triggered for next 90 days',
        }, status=201)

    @action(detail=False, methods=['get'], url_path='weekly-view')
    def weekly_view(self, request):
        """
        Returns timetable slots grouped by day_of_week for a given class_session.
        Query: ?class_session=<id>
        """
        class_session_id = request.query_params.get('class_session')
        if not class_session_id:
            return Response({'error': 'class_session query param required'}, status=400)

        slots = TimetableSlot.objects.filter(
            class_session_id=class_session_id, is_active=True
        ).select_related('subject', 'teacher', 'room').order_by('day_of_week', 'start_time')

        from collections import defaultdict
        grouped = defaultdict(list)
        serializer = TimetableSlotSerializer(slots, many=True)
        for slot_data in serializer.data:
            grouped[slot_data['day_of_week']].append(slot_data)

        return Response(dict(grouped))


class TimetableExceptionViewSet(viewsets.ModelViewSet):
    queryset = TimetableException.objects.prefetch_related('class_sessions')
    serializer_class = TimetableExceptionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['exception_type', 'affects_all_classes']
    ordering_fields = ['date_from']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class CurriculumUnitViewSet(viewsets.ModelViewSet):
    serializer_class = CurriculumUnitSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['subject', 'class_session', 'is_compulsory']
    search_fields = ['title', 'description']
    ordering_fields = ['sequence_order', 'subject']

    def get_queryset(self):
        return CurriculumUnit.objects.select_related(
            'subject', 'class_session'
        ).order_by('class_session', 'subject', 'sequence_order')


# =============================================================================
# NEW VIEWSETS FOR ENHANCED TIMETABLING
# =============================================================================

class TimePeriodViewSet(viewsets.ModelViewSet):
    """
    API endpoint for school-wide time period definitions.
    
    Periods define the school's standard schedule (Period 1, Break, etc.)
    and are used across all timetables.
    """
    queryset = TimePeriod.objects.all().order_by('order')
    serializer_class = TimePeriodSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['period_type', 'is_schedulable', 'is_active']
    ordering_fields = ['order', 'start_time']

    @action(detail=False, methods=['get'])
    def schedulable(self, request):
        """Return only periods that can have lessons scheduled."""
        periods = self.queryset.filter(is_schedulable=True, is_active=True)
        serializer = self.get_serializer(periods, many=True)
        return Response(serializer.data)


class WorkAllocationViewSet(viewsets.ModelViewSet):
    """
    API endpoint for teacher work allocations.
    
    Work allocations define how many lessons per week a teacher should 
    teach for a subject in a class. The scheduler uses these to generate
    timetables.
    """
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['teacher', 'subject', 'class_session', 'is_active']
    search_fields = ['subject__name', 'subject__code', 'teacher__first_name', 'teacher__last_name']
    ordering_fields = ['class_session', 'subject']

    def get_queryset(self):
        return WorkAllocation.objects.select_related(
            'teacher', 'subject', 'class_session'
        ).order_by('class_session', 'subject')

    def get_serializer_class(self):
        if self.action == 'create':
            return WorkAllocationCreateSerializer
        return WorkAllocationSerializer

    @action(detail=False, methods=['get'], url_path='by-class/(?P<class_id>[^/.]+)')
    def by_class(self, request, class_id=None):
        """Get all allocations for a specific class."""
        allocations = self.get_queryset().filter(class_session_id=class_id, is_active=True)
        serializer = WorkAllocationSerializer(allocations, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='by-teacher/(?P<teacher_id>[^/.]+)')
    def by_teacher(self, request, teacher_id=None):
        """Get all allocations for a specific teacher."""
        allocations = self.get_queryset().filter(teacher_id=teacher_id, is_active=True)
        serializer = WorkAllocationSerializer(allocations, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def available_slots(self, request, pk=None):
        """Get available time slots for this allocation."""
        from .services.conflict_engine import ConflictEngine
        
        allocation = self.get_object()
        engine = ConflictEngine()
        slots = engine.get_available_slots(
            class_session=allocation.class_session,
            teacher=allocation.teacher,
            subject=allocation.subject,
        )
        return Response(slots)


class TeacherAvailabilityViewSet(viewsets.ModelViewSet):
    """
    API endpoint for teacher availability records.
    
    Used to mark times when teachers are unavailable for scheduling
    (meetings, training, etc.)
    """
    serializer_class = TeacherAvailabilitySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['teacher', 'availability_type', 'recurrence', 'is_active']
    ordering_fields = ['day_of_week', 'start_time']

    def get_queryset(self):
        return TeacherAvailability.objects.select_related('teacher').filter(is_active=True)

    @action(detail=False, methods=['get'], url_path='by-teacher/(?P<teacher_id>[^/.]+)')
    def by_teacher(self, request, teacher_id=None):
        """Get all availability records for a teacher."""
        records = self.get_queryset().filter(teacher_id=teacher_id)
        serializer = self.get_serializer(records, many=True)
        return Response(serializer.data)


class TimetableLockViewSet(viewsets.ModelViewSet):
    """
    API endpoint for timetable lock management.
    
    Locks prevent unauthorized modifications to finalized timetables.
    """
    serializer_class = TimetableLockSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['class_session', 'lock_level']

    def get_queryset(self):
        return TimetableLock.objects.select_related(
            'class_session', 'locked_by'
        )

    @action(detail=True, methods=['post'])
    def lock(self, request, pk=None):
        """Lock a timetable (set to 'locked' level)."""
        lock = self.get_object()
        try:
            lock.lock(request.user)
            return Response({
                'status': 'success',
                'message': f'Timetable locked for {lock.class_session.name}',
                'lock_level': lock.lock_level,
            })
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def unlock(self, request, pk=None):
        """Unlock a timetable (set to 'draft' level)."""
        lock = self.get_object()
        try:
            reason = request.data.get('reason', '')
            lock.unlock(request.user, reason)
            return Response({
                'status': 'success',
                'message': f'Timetable unlocked for {lock.class_session.name}',
                'lock_level': lock.lock_level,
            })
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class TimetableVersionViewSet(viewsets.ModelViewSet):
    """
    API endpoint for timetable version history.
    
    Versions store snapshots of timetables for rollback and "what-if" analysis.
    """
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['class_session']
    ordering_fields = ['version_number', 'created_at']

    def get_queryset(self):
        return TimetableVersion.objects.select_related(
            'class_session', 'created_by'
        ).order_by('-version_number')

    def get_serializer_class(self):
        if self.action == 'list':
            return TimetableVersionListSerializer
        return TimetableVersionSerializer

    @action(detail=False, methods=['post'], url_path='create-snapshot')
    def create_snapshot(self, request):
        """Create a new snapshot of a class timetable."""
        class_session_id = request.data.get('class_session')
        label = request.data.get('label', f'Snapshot')
        description = request.data.get('description', '')

        if not class_session_id:
            return Response(
                {'error': 'class_session is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            from academics.models import ClassSession
            class_session = ClassSession.objects.get(pk=class_session_id)
        except ClassSession.DoesNotExist:
            return Response(
                {'error': 'Class session not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        version = TimetableVersion.create_snapshot(
            class_session=class_session,
            name=label,
            user=request.user,
            description=description,
        )

        return Response(
            TimetableVersionSerializer(version).data,
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        """Restore timetable from this version."""
        version = self.get_object()
        
        try:
            restored_slots = version.restore()
            return Response({
                'status': 'success',
                'message': f'Restored {len(restored_slots)} slots from version {version.version_number}',
                'restored_slot_ids': [s.id for s in restored_slots],
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


# =============================================================================
# SCHEDULING & CONFLICT API VIEWS
# =============================================================================

class ConflictCheckView(APIView):
    """
    API endpoint for checking conflicts before slot creation.
    
    POST /api/timetable/check-conflict/
    {
        "class_session": 1,
        "subject": 2,
        "teacher": 3,
        "day_of_week": 1,
        "start_time": "08:00",
        "end_time": "08:40",
        "room": 5  // optional
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .services.conflict_engine import ConflictEngine
        from academics.models import ClassSession
        from django.contrib.auth import get_user_model
        from datetime import datetime
        
        User = get_user_model()

        # Parse required fields
        required = ['class_session', 'subject', 'teacher', 'day_of_week', 'start_time', 'end_time']
        for field in required:
            if field not in request.data:
                return Response(
                    {'error': f'{field} is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        try:
            class_session = ClassSession.objects.get(pk=request.data['class_session'])
            subject = Subject.objects.get(pk=request.data['subject'])
            teacher = User.objects.get(pk=request.data['teacher'])
            room = Room.objects.get(pk=request.data['room']) if request.data.get('room') else None
            start_time = datetime.strptime(request.data['start_time'], '%H:%M').time()
            end_time = datetime.strptime(request.data['end_time'], '%H:%M').time()
        except (ClassSession.DoesNotExist, Subject.DoesNotExist, User.DoesNotExist, Room.DoesNotExist) as e:
            return Response(
                {'error': f'Invalid reference: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except ValueError as e:
            return Response(
                {'error': f'Invalid time format: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        engine = ConflictEngine()
        result = engine.check_slot_creation(
            class_session=class_session,
            subject=subject,
            teacher=teacher,
            day_of_week=request.data['day_of_week'],
            start_time=start_time,
            end_time=end_time,
            room=room,
        )

        return Response(result.to_dict())


class SchedulingView(APIView):
    """
    API endpoint for semi-automatic timetable generation.
    
    POST /api/timetable/generate/
    {
        "class_session": 1,
        "mode": "semi_auto",  // or "suggestions_only"
        "preferences": {
            "prefer_morning": true,
            "spread_subjects": true
        }
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .services.scheduling_service import SchedulingService, SchedulingMode, SchedulingPreferences
        from academics.models import ClassSession

        class_session_id = request.data.get('class_session')
        if not class_session_id:
            return Response(
                {'error': 'class_session is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            class_session = ClassSession.objects.get(pk=class_session_id)
        except ClassSession.DoesNotExist:
            return Response(
                {'error': 'Class session not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Parse mode
        mode_str = request.data.get('mode', 'semi_auto')
        try:
            mode = SchedulingMode(mode_str)
        except ValueError:
            mode = SchedulingMode.SEMI_AUTO

        # Parse preferences
        prefs_data = request.data.get('preferences', {})
        preferences = SchedulingPreferences(
            prefer_morning=prefs_data.get('prefer_morning', True),
            spread_subjects=prefs_data.get('spread_subjects', True),
            max_same_subject_per_day=prefs_data.get('max_same_subject_per_day', 1),
        )

        service = SchedulingService()
        result = service.generate_timetable(
            class_session=class_session,
            mode=mode,
            preferences=preferences,
        )

        return Response(result.to_dict())


class AnalyticsView(APIView):
    """
    API endpoint for timetable analytics.
    
    GET /api/timetable/analytics/dashboard/
    GET /api/timetable/analytics/workloads/
    GET /api/timetable/analytics/coverage/<class_id>/
    GET /api/timetable/analytics/rooms/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, report_type=None, entity_id=None):
        from .services.analytics import TimetableAnalytics
        from academics.models import ClassSession

        analytics = TimetableAnalytics()

        if report_type == 'dashboard':
            return Response(analytics.get_dashboard_summary())

        elif report_type == 'workloads':
            return Response(analytics.get_teacher_workloads())

        elif report_type == 'teacher' and entity_id:
            return Response(analytics.get_teacher_detail(entity_id))

        elif report_type == 'coverage' and entity_id:
            try:
                class_session = ClassSession.objects.get(pk=entity_id)
                return Response(analytics.get_class_coverage(class_session))
            except ClassSession.DoesNotExist:
                return Response(
                    {'error': 'Class session not found'},
                    status=status.HTTP_404_NOT_FOUND
                )

        elif report_type == 'rooms':
            return Response(analytics.get_room_utilization())

        elif report_type == 'room' and entity_id:
            return Response(analytics.get_room_schedule(entity_id))

        elif report_type == 'periods':
            return Response(analytics.get_period_utilization())

        elif report_type == 'conflicts':
            return Response(analytics.get_conflict_summary())

        else:
            return Response({
                'available_reports': [
                    'dashboard', 'workloads', 'teacher/<id>', 
                    'coverage/<class_id>', 'rooms', 'room/<id>',
                    'periods', 'conflicts'
                ]
            })


class ClassTimetableView(APIView):
    """
    Get the complete timetable for a class in a structured format.
    
    GET /api/timetable/class/<class_id>/full/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, class_id):
        from .services.analytics import TimetableAnalytics
        from academics.models import ClassSession

        try:
            class_session = ClassSession.objects.get(pk=class_id)
        except ClassSession.DoesNotExist:
            return Response(
                {'error': 'Class session not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get slots grouped by day
        slots = TimetableSlot.objects.filter(
            class_session=class_session,
            is_active=True,
        ).select_related('subject', 'teacher', 'room').order_by('day_of_week', 'start_time')

        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
        days = {day: [] for day in day_names}

        for slot in slots:
            days[day_names[slot.day_of_week]].append({
                'id': slot.id,
                'subject': slot.subject.name,
                'subject_code': slot.subject.code,
                'subject_color': slot.subject.color_hex,
                'teacher': slot.teacher.get_full_name or slot.teacher.username,
                'room': slot.room.name if slot.room else None,
                'start_time': slot.start_time.strftime('%H:%M'),
                'end_time': slot.end_time.strftime('%H:%M'),
            })

        # Get coverage info
        analytics = TimetableAnalytics()
        coverage = analytics.get_class_coverage(class_session)

        return Response({
            'class_session': {
                'id': class_session.id,
                'name': class_session.name,
            },
            'days': days,
            'coverage': coverage['summary'],
        })


class TeacherTimetableView(APIView):
    """
    Get the complete timetable for a teacher.
    
    GET /api/timetable/teacher/<teacher_id>/full/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, teacher_id):
        from .services.analytics import TimetableAnalytics
        
        analytics = TimetableAnalytics()
        return Response(analytics.get_teacher_detail(teacher_id))


class RoomTimetableView(APIView):
    """
    Get the complete timetable for a room.
    
    GET /api/timetable/room/<room_id>/full/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, room_id):
        from .services.analytics import TimetableAnalytics
        
        analytics = TimetableAnalytics()
        return Response(analytics.get_room_schedule(room_id))


class GenerateForTermView(APIView):
    """
    Generate timetable slots for multiple classes in a term.
    
    POST /api/timetable/generate-for-term/
    {
        "term_id": 3,
        "class_sessions": [1, 2, 3],  // Optional
        "mode": "semi_auto",
        "effective_from": "2026-09-01"
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from academics.models import ClassSession, Term
        from .services.scheduling_service import SchedulingService, SchedulingMode, SchedulingPreferences
        from datetime import datetime
        
        term_id = request.data.get('term_id')
        if not term_id:
            return Response({'error': 'term_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        class_session_ids = request.data.get('class_sessions')
        if class_session_ids:
            class_sessions = ClassSession.objects.filter(pk__in=class_session_ids, is_active=True)
        else:
            class_sessions = ClassSession.objects.filter(term_id=term_id, is_active=True)

        mode_str = request.data.get('mode', 'semi_auto')
        try:
            mode = SchedulingMode(mode_str)
        except ValueError:
            mode = SchedulingMode.SEMI_AUTO

        effective_from_str = request.data.get('effective_from')
        effective_from = None
        if effective_from_str:
            try:
                effective_from = datetime.strptime(effective_from_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        service = SchedulingService()
        preferences = SchedulingPreferences(
            prefer_morning=True,
            spread_subjects=True,
            max_same_subject_per_day=1,
        )

        results = []
        total_placed = 0
        total_allocations = 0

        for cs in class_sessions:
            res = service.generate_timetable(
                class_session=cs,
                mode=mode,
                preferences=preferences,
                effective_from=effective_from
            )
            res_dict = res.to_dict()
            total_placed += res_dict.get('placed_count', 0)
            total_allocations += res_dict.get('total_allocations', 0)
            
            results.append({
                'class_session_id': cs.id,
                'class_session_name': cs.name,
                'result': res_dict
            })

        return Response({
            'status': 'success',
            'summary': {
                'total_placed': total_placed,
                'total_allocations': total_allocations,
                'percentage': round(total_placed / total_allocations * 100 if total_allocations > 0 else 0, 1)
            },
            'class_results': results
        })


class MonthlyTimetableView(APIView):
    """
    Get timetable mapped to actual dates for a specific month.
    
    GET /api/timetable/monthly-view/?year=2026&month=6&class_session=5
    GET /api/timetable/monthly-view/?year=2026&month=6&teacher=12
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from datetime import date, timedelta
        import calendar

        year = request.query_params.get('year')
        month = request.query_params.get('month')
        class_session_id = request.query_params.get('class_session')
        teacher_id = request.query_params.get('teacher')

        if not year or not month:
            return Response({'error': 'year and month are required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            year = int(year)
            month = int(month)
        except ValueError:
            return Response({'error': 'invalid year or month'}, status=status.HTTP_400_BAD_REQUEST)

        # Build slots query
        queryset = TimetableSlot.objects.filter(is_active=True).select_related('subject', 'teacher', 'room', 'class_session')
        if class_session_id:
            queryset = queryset.filter(class_session_id=class_session_id)
        elif teacher_id:
            queryset = queryset.filter(teacher_id=teacher_id)
        else:
            return Response({'error': 'Either class_session or teacher is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Get all slots grouped by day of week
        slots = list(queryset)
        slots_by_dow = {i: [] for i in range(7)}
        for slot in slots:
            slots_by_dow[slot.day_of_week].append(slot)

        # Fetch exceptions for the month
        start_date = date(year, month, 1)
        _, last_day = calendar.monthrange(year, month)
        end_date = date(year, month, last_day)

        exceptions = TimetableException.objects.filter(
            Q(date_from__lte=end_date) & Q(date_to__gte=start_date)
        )
        
        # Build exception map for fast lookup
        exception_dates = {}
        for ex in exceptions:
            current = ex.date_from
            while current <= ex.date_to:
                # Check applicability
                applies = False
                if ex.affects_all_classes:
                    applies = True
                elif class_session_id and ex.class_sessions.filter(id=class_session_id).exists():
                    applies = True
                
                if applies:
                    exception_dates[current] = {
                        'reason': ex.reason,
                        'type': ex.exception_type
                    }
                current += timedelta(days=1)

        # Generate calendar
        monthly_schedule = {}
        for day in range(1, last_day + 1):
            current_date = date(year, month, day)
            date_str = current_date.isoformat()
            dow = current_date.weekday() # 0 = Monday, 6 = Sunday
            
            # Map Python DOW to Model DOW if needed. They match: 0=Mon, 5=Sat.
            if dow > 5: # Sunday
                monthly_schedule[date_str] = {'slots': [], 'exception': None}
                continue

            exception = exception_dates.get(current_date)
            
            day_slots = []
            if not exception:
                for slot in slots_by_dow.get(dow, []):
                    # Check effective dates
                    if slot.effective_from and slot.effective_from > current_date:
                        continue
                    if slot.effective_until and slot.effective_until < current_date:
                        continue
                        
                    day_slots.append({
                        'id': slot.id,
                        'subject_name': slot.subject.name,
                        'subject_color': slot.subject.color_hex,
                        'teacher_name': slot.teacher.get_full_name() or slot.teacher.username,
                        'class_session_name': slot.class_session.name,
                        'room_name': slot.room.name if slot.room else None,
                        'start_time': slot.start_time.strftime('%H:%M'),
                        'end_time': slot.end_time.strftime('%H:%M'),
                    })
                
                # Sort slots by time
                day_slots.sort(key=lambda s: s['start_time'])

            monthly_schedule[date_str] = {
                'slots': day_slots,
                'exception': exception
            }

        export = request.query_params.get('export')
        if export in ['pdf', 'excel']:
            from academics.models import ClassSession
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            entity_name = "Timetable"
            if class_session_id:
                try:
                    cs = ClassSession.objects.get(pk=class_session_id)
                    entity_name = f"Class {cs.name}"
                except:
                    pass
            elif teacher_id:
                try:
                    t = User.objects.get(pk=teacher_id)
                    entity_name = f"Teacher {t.get_full_name() or t.username}"
                except:
                    pass
                    
            if export == 'pdf':
                from .reports_pdf import MonthlyTimetablePDFGenerator
                return MonthlyTimetablePDFGenerator().generate(year, month, monthly_schedule, entity_name)
            elif export == 'excel':
                from .reports_excel import MonthlyTimetableExcelGenerator
                return MonthlyTimetableExcelGenerator().generate(year, month, monthly_schedule, entity_name)

        return Response({
            'year': year,
            'month': month,
            'days': monthly_schedule
        })
