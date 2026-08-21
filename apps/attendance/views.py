from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Q
from django.utils import timezone

from .models import DailyAttendance
from .serializers import (
    DailyAttendanceSerializer,
    BulkAttendanceSerializer,
    AttendanceSummarySerializer,
)
from academics.models import StudentSessionEnrollment


class DailyAttendanceViewSet(viewsets.ModelViewSet):
    serializer_class = DailyAttendanceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = DailyAttendance.objects.select_related(
            'student__student', 'class_session', 'marked_by'
        )
        class_session = self.request.query_params.get('class_session')
        date = self.request.query_params.get('date')
        student = self.request.query_params.get('student')

        if class_session:
            qs = qs.filter(class_session_id=class_session)
        if date:
            qs = qs.filter(date=date)
        if student:
            qs = qs.filter(student_id=student)
        return qs

    def perform_create(self, serializer):
        serializer.save(marked_by=self.request.user)

    @action(detail=False, methods=['get'])
    def register(self, request):
        """
        GET /api/attendance/daily/register/?class_session=X&date=Y
        Returns all enrolled students with their attendance status for the day.
        Creates blank (absent) records for students not yet marked.
        """
        class_session_id = request.query_params.get('class_session')
        date = request.query_params.get('date', timezone.localdate().isoformat())

        if not class_session_id:
            return Response(
                {'error': 'class_session is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get all actively enrolled students
        enrollments = StudentSessionEnrollment.objects.filter(
            session_id=class_session_id,
            is_active=True,
        ).select_related('student__student')

        # Get existing records for this date
        existing = {
            att.student_id: att
            for att in DailyAttendance.objects.filter(
                class_session_id=class_session_id,
                date=date,
            ).select_related('student__student', 'marked_by')
        }

        results = []
        for enrollment in enrollments:
            student = enrollment.student
            user = student.student  # User object
            if student.id in existing:
                att = existing[student.id]
                results.append({
                    'id': att.id,
                    'student_id': student.id,
                    'student_name': f"{user.first_name} {user.last_name}",
                    'admission_number': student.admission_number,
                    'status': att.status,
                    'arrival_time': att.arrival_time,
                    'notes': att.notes,
                    'marked_at': att.marked_at,
                    'stream': enrollment.stream.name if enrollment.stream else None,
                })
            else:
                results.append({
                    'id': None,
                    'student_id': student.id,
                    'student_name': f"{user.first_name} {user.last_name}",
                    'admission_number': student.admission_number,
                    'status': 'unmarked',
                    'arrival_time': None,
                    'notes': '',
                    'marked_at': None,
                    'stream': enrollment.stream.name if enrollment.stream else None,
                })

        # Sort by name
        results.sort(key=lambda r: r['student_name'])

        return Response({
            'date': date,
            'class_session': int(class_session_id),
            'total_students': len(results),
            'marked': len(existing),
            'unmarked': len(results) - len(existing),
            'students': results,
        })

    @action(detail=False, methods=['post'])
    def bulk_mark(self, request):
        """
        POST /api/attendance/daily/bulk_mark/
        Body: { class_session, date, records: [{student_id, status, arrival_time?, notes?}] }
        Creates or updates attendance for each student.
        """
        serializer = BulkAttendanceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        class_session_id = serializer.validated_data['class_session']
        date = serializer.validated_data['date']
        records = serializer.validated_data['records']

        created = 0
        updated = 0

        for record in records:
            defaults = {
                'status': record['status'],
                'marked_by': request.user,
            }
            if 'arrival_time' in record and record['arrival_time']:
                defaults['arrival_time'] = record['arrival_time']
            if 'notes' in record:
                defaults['notes'] = record['notes']

            _, was_created = DailyAttendance.objects.update_or_create(
                student_id=record['student_id'],
                class_session_id=class_session_id,
                date=date,
                defaults=defaults,
            )
            if was_created:
                created += 1
            else:
                updated += 1

        return Response({
            'success': True,
            'created': created,
            'updated': updated,
            'total': len(records),
        })

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        GET /api/attendance/daily/summary/?class_session=X&date_from=Y&date_to=Z
        Returns per-student attendance summary for the date range.
        """
        class_session_id = request.query_params.get('class_session')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')

        if not class_session_id:
            return Response(
                {'error': 'class_session is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        qs = DailyAttendance.objects.filter(class_session_id=class_session_id)
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)

        stats = qs.values('student', 'student__student__first_name', 'student__student__last_name', 'student__admission_number').annotate(
            total_days=Count('id'),
            present=Count('id', filter=Q(status='present')),
            absent=Count('id', filter=Q(status='absent')),
            late=Count('id', filter=Q(status='late')),
            excused=Count('id', filter=Q(status='excused')),
            half_day=Count('id', filter=Q(status='half_day')),
        ).order_by('student__student__last_name')

        results = []
        for row in stats:
            total = row['total_days'] or 1
            attended = row['present'] + row['late'] + row['half_day']
            results.append({
                'student_id': row['student'],
                'student_name': f"{row['student__student__first_name']} {row['student__student__last_name']}",
                'admission_number': row['student__admission_number'],
                'total_days': row['total_days'],
                'present': row['present'],
                'absent': row['absent'],
                'late': row['late'],
                'excused': row['excused'],
                'half_day': row['half_day'],
                'attendance_rate': round((attended / total) * 100, 1),
            })

        return Response(results)
