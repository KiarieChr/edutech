from django.db import models
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import Student, Parent
from .models import Assignment, AssignmentSubmission
from .serializers import (
    AssignmentListSerializer, AssignmentCreateSerializer,
    SubmissionListSerializer, SubmissionCreateSerializer,
    SubmissionGradeSerializer, PortalAssignmentSerializer,
)


# ═══════════════════════════════════════════════════════════
#  ADMIN / TEACHER VIEWS
# ═══════════════════════════════════════════════════════════

class AssignmentViewSet(viewsets.ModelViewSet):
    """CRUD for assignments — used by teachers / admin."""
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return AssignmentCreateSerializer
        return AssignmentListSerializer

    def get_queryset(self):
        qs = Assignment.objects.select_related(
            'subject', 'class_session', 'created_by'
        ).all()

        class_session = self.request.query_params.get('class_session')
        if class_session:
            qs = qs.filter(class_session_id=class_session)

        subject = self.request.query_params.get('subject')
        if subject:
            qs = qs.filter(subject_id=subject)

        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        assignment_type = self.request.query_params.get('assignment_type')
        if assignment_type:
            qs = qs.filter(assignment_type=assignment_type)

        return qs

    @action(detail=True, methods=['post'], url_path='publish')
    def publish(self, request, pk=None):
        assignment = self.get_object()
        assignment.status = 'published'
        assignment.save(update_fields=['status', 'updated_at'])
        return Response({'detail': 'Assignment published.'})

    @action(detail=True, methods=['post'], url_path='close')
    def close(self, request, pk=None):
        assignment = self.get_object()
        assignment.status = 'closed'
        assignment.save(update_fields=['status', 'updated_at'])
        return Response({'detail': 'Assignment closed.'})

    @action(detail=True, methods=['get'], url_path='submissions')
    def submissions(self, request, pk=None):
        assignment = self.get_object()
        subs = assignment.submissions.select_related('student__student').all()
        serializer = SubmissionListSerializer(subs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='stats')
    def stats(self, request, pk=None):
        assignment = self.get_object()
        subs = assignment.submissions.all()
        total_students = 0
        try:
            from student_management.models import Enrollment
            total_students = Enrollment.objects.filter(
                class_session=assignment.class_session, status='active'
            ).count()
        except Exception:
            pass

        return Response({
            'total_students': total_students,
            'submissions': subs.count(),
            'graded': subs.filter(status='graded').count(),
            'pending': subs.filter(status='submitted').count(),
            'late': subs.filter(status='late').count(),
            'average_score': subs.filter(
                score__isnull=False
            ).aggregate(avg=models.Avg('score'))['avg'],
        })


class SubmissionViewSet(viewsets.ModelViewSet):
    """CRUD for submissions — teacher grading view."""
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_serializer_class(self):
        if self.action in ('create',):
            return SubmissionCreateSerializer
        return SubmissionListSerializer

    def get_queryset(self):
        qs = AssignmentSubmission.objects.select_related(
            'assignment', 'student__student'
        ).all()

        assignment = self.request.query_params.get('assignment')
        if assignment:
            qs = qs.filter(assignment_id=assignment)

        return qs

    @action(detail=True, methods=['patch'], url_path='grade')
    def grade(self, request, pk=None):
        submission = self.get_object()
        serializer = SubmissionGradeSerializer(
            submission, data=request.data, partial=True,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(SubmissionListSerializer(submission).data)


# ═══════════════════════════════════════════════════════════
#  STUDENT PORTAL ENDPOINTS
# ═══════════════════════════════════════════════════════════

def _get_student(user):
    try:
        return Student.objects.select_related('student').get(student=user)
    except Student.DoesNotExist:
        return None


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_assignments(request):
    """Get assignments for the logged-in student."""
    student = _get_student(request.user)
    if not student:
        return Response({'detail': 'Student profile not found.'}, status=404)

    # Get class sessions the student is enrolled in
    from academics.models import StudentSessionEnrollment
    enrollments = StudentSessionEnrollment.objects.filter(
        student=student, is_active=True
    ).values_list('session_id', flat=True)

    assignments = Assignment.objects.filter(
        class_session_id__in=enrollments,
        status='published',
    ).select_related('subject', 'class_session', 'created_by').order_by('-created_at')

    serializer = PortalAssignmentSerializer(
        assignments, many=True, context={'student': student}
    )
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_assignment(request, assignment_id):
    """Student submits work for an assignment."""
    student = _get_student(request.user)
    if not student:
        return Response({'detail': 'Student profile not found.'}, status=404)

    try:
        assignment = Assignment.objects.get(pk=assignment_id, status='published')
    except Assignment.DoesNotExist:
        return Response({'detail': 'Assignment not found.'}, status=404)

    # Check duplicate
    if AssignmentSubmission.objects.filter(assignment=assignment, student=student).exists():
        return Response({'detail': 'You have already submitted this assignment.'}, status=400)

    data = request.data.copy()
    data['assignment'] = assignment.id
    serializer = SubmissionCreateSerializer(data=data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=201)


# ═══════════════════════════════════════════════════════════
#  PARENT PORTAL ENDPOINTS
# ═══════════════════════════════════════════════════════════

def _get_parent(user):
    try:
        return Parent.objects.select_related('user').get(user=user)
    except Parent.DoesNotExist:
        return None


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def parent_child_assignments(request, student_id):
    """Parent views assignments for a specific child."""
    parent = _get_parent(request.user)
    if not parent:
        return Response({'detail': 'Parent profile not found.'}, status=404)

    # Verify this child belongs to this parent
    try:
        student = Student.objects.get(pk=student_id, parents__user=parent.user)
    except Student.DoesNotExist:
        return Response({'detail': 'Child not found.'}, status=404)

    from student_management.models import Enrollment
    enrollments = Enrollment.objects.filter(
        student=student, status='active'
    ).values_list('class_session_id', flat=True)

    assignments = Assignment.objects.filter(
        class_session_id__in=enrollments,
        status='published',
    ).select_related('subject', 'class_session', 'created_by').order_by('-created_at')

    serializer = PortalAssignmentSerializer(
        assignments, many=True, context={'student': student}
    )
    return Response(serializer.data)
