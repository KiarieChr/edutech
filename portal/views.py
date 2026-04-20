from datetime import date, timedelta

from django.db.models import Sum, Count, Q, F, Value, CharField, DecimalField
from django.db.models.functions import Coalesce
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import Student, Parent
from fees.models import FeeInvoice
from finance.models import Receipt, StudentPrepayment
from result.models import TakenCourse, Result
from scheduled_lessons.models import PlannedLesson
from lesson_sessions.models import SessionAttendance
from core.models import NewsAndEvents
from examinations.models import TermResult, StudentMark

from .serializers import (
    PortalProfileSerializer, PortalProfileUpdateSerializer,
    PortalInvoiceSerializer, PortalReceiptSerializer,
    PortalTakenCourseSerializer, PortalResultSerializer,
    PortalTimetableSerializer, PortalAttendanceSerializer,
    PortalAnnouncementSerializer,
    ParentProfileSerializer, ParentChildSummarySerializer,
    PortalTermResultSerializer, PortalExamMarkSerializer,
)


# ─── Helpers ──────────────────────────────────────────────

def _get_student(user):
    """Return the Student object for the current user, or None."""
    if not hasattr(user, 'student_profile'):
        try:
            return Student.objects.select_related(
                'student', 'campus', 'intake',
            ).get(student=user)
        except Student.DoesNotExist:
            return None
    return user.student_profile


def _get_parent(user):
    """Return the Parent object for the current user, or None."""
    try:
        return Parent.objects.select_related('user').get(user=user)
    except Parent.DoesNotExist:
        return None


def _get_children(parent):
    """Return queryset of Student objects linked to this parent."""
    return Student.objects.filter(parents__user=parent.user, status='active')


# ═══════════════════════════════════════════════════════════
#  STUDENT PORTAL ENDPOINTS
# ═══════════════════════════════════════════════════════════

@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def my_profile(request):
    """GET: full student profile. PATCH: update editable fields."""
    student = _get_student(request.user)
    if not student:
        return Response(
            {'detail': 'No student profile linked to this account.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == 'PATCH':
        serializer = PortalProfileUpdateSerializer(
            student, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        # Return full profile after update
        return Response(PortalProfileSerializer(student).data)

    return Response(PortalProfileSerializer(student).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_fees(request):
    """Fee statement: invoices list + balance summary."""
    student = _get_student(request.user)
    if not student:
        return Response({'detail': 'No student profile.'}, status=404)

    invoices = FeeInvoice.objects.filter(
        student=student,
    ).exclude(
        status='VOID',
    ).select_related(
        'term', 'academic_year', 'class_session__grade',
    ).prefetch_related(
        'items__fee_item', 'items__vote_head',
    ).order_by('-date_issued')

    # Optional year filter
    year_id = request.query_params.get('academic_year')
    if year_id:
        invoices = invoices.filter(academic_year_id=year_id)

    term_id = request.query_params.get('term')
    if term_id:
        invoices = invoices.filter(term_id=term_id)

    # Aggregate
    totals = invoices.aggregate(
        total_invoiced=Sum('total_amount'),
        total_paid=Sum('paid_amount'),
        total_balance=Sum('balance'),
    )

    # Include prepayment credits (unused overpayments)
    prepayment_credit = StudentPrepayment.objects.filter(
        student=student, is_fully_used=False,
    ).aggregate(total=Sum('balance'))['total'] or 0

    invoice_balance = float(totals['total_balance'] or 0)
    net_balance = invoice_balance - float(prepayment_credit)

    return Response({
        'summary': {
            'total_invoiced': float(totals['total_invoiced'] or 0),
            'total_paid': float(totals['total_paid'] or 0),
            'total_balance': net_balance,
            'invoice_balance': invoice_balance,
            'prepayment_credit': float(prepayment_credit),
        },
        'invoices': PortalInvoiceSerializer(invoices, many=True).data,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_payments(request):
    """Payment history: receipts with allocations."""
    student = _get_student(request.user)
    if not student:
        return Response({'detail': 'No student profile.'}, status=404)

    receipts = Receipt.objects.filter(
        student=student,
    ).exclude(
        status='REVERSED',
    ).select_related(
        'payment_method', 'term', 'academic_year',
    ).prefetch_related(
        'allocations__invoice',
    ).order_by('-received_date')

    year_id = request.query_params.get('academic_year')
    if year_id:
        receipts = receipts.filter(academic_year_id=year_id)

    total_paid = receipts.aggregate(total=Sum('amount_received'))['total'] or 0

    return Response({
        'total_paid': float(total_paid),
        'receipts': PortalReceiptSerializer(receipts, many=True).data,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_results(request):
    """Academic results: old taken courses + new exam term results."""
    student = _get_student(request.user)
    if not student:
        return Response({'detail': 'No student profile.'}, status=404)

    # Legacy: TakenCourse results
    taken = TakenCourse.objects.filter(
        student=student,
    ).select_related('course').order_by('-id')

    session = request.query_params.get('session')
    if session:
        taken = taken.filter(course__semester__session=session)

    results = Result.objects.filter(student=student).order_by('-id')

    # New: Exam term results (only published)
    term_results = TermResult.objects.filter(
        student=student,
        is_published=True,
    ).select_related(
        'class_session__term', 'class_session__academic_year',
        'class_session__grade', 'stream',
    ).prefetch_related(
        'subject_results__subject',
    ).order_by('-class_session__academic_year__start_date', '-class_session__term__order')

    return Response({
        'courses': PortalTakenCourseSerializer(taken, many=True).data,
        'results': PortalResultSerializer(results, many=True).data,
        'term_results': PortalTermResultSerializer(term_results, many=True).data,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_exam_results(request):
    """Detailed exam marks for the current student."""
    student = _get_student(request.user)
    if not student:
        return Response({'detail': 'No student profile.'}, status=404)

    marks = StudentMark.objects.filter(
        student=student,
        examination__status='published',
    ).select_related(
        'examination__subject',
        'examination__assessment_type',
        'examination__class_session__term',
        'examination__class_session__academic_year',
    ).order_by(
        '-examination__class_session__academic_year__start_date',
        '-examination__class_session__term__order',
        'examination__subject__name',
    )

    # Optional filters
    year_id = request.query_params.get('academic_year')
    if year_id:
        marks = marks.filter(examination__class_session__academic_year_id=year_id)

    term_id = request.query_params.get('term')
    if term_id:
        marks = marks.filter(examination__class_session__term_id=term_id)

    return Response({
        'marks': PortalExamMarkSerializer(marks, many=True).data,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_timetable(request):
    """Weekly timetable: planned lessons for current enrollment's class session."""
    student = _get_student(request.user)
    if not student:
        return Response({'detail': 'No student profile.'}, status=404)

    enrollment = student.current_enrollment
    if not enrollment:
        return Response({'detail': 'No active enrollment.', 'lessons': []})

    # Get the class session from enrollment
    class_session_id = None
    if hasattr(enrollment, 'session_id'):
        class_session_id = enrollment.session_id
    elif hasattr(enrollment, 'session'):
        class_session_id = enrollment.session.id if enrollment.session else None

    if not class_session_id:
        return Response({'detail': 'No class session found.', 'lessons': []})

    # Default: this week
    week_start = request.query_params.get('week_start')
    if week_start:
        try:
            start = date.fromisoformat(week_start)
        except ValueError:
            start = date.today() - timedelta(days=date.today().weekday())
    else:
        start = date.today() - timedelta(days=date.today().weekday())

    end = start + timedelta(days=6)

    lessons = PlannedLesson.objects.filter(
        class_session_id=class_session_id,
        date__gte=start,
        date__lte=end,
    ).select_related(
        'subject', 'expected_teacher', 'room',
    ).order_by('date', 'scheduled_start_time')

    return Response({
        'week_start': start.isoformat(),
        'week_end': end.isoformat(),
        'lessons': PortalTimetableSerializer(lessons, many=True).data,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_attendance(request):
    """Attendance summary + recent records."""
    student = _get_student(request.user)
    if not student:
        return Response({'detail': 'No student profile.'}, status=404)

    qs = SessionAttendance.objects.filter(
        student=student,
    ).select_related(
        'lesson_session__subject', 'lesson_session',
    )

    # Summary counts
    summary = qs.aggregate(
        total=Count('id'),
        present=Count('id', filter=Q(status='present')),
        absent=Count('id', filter=Q(status='absent')),
        late=Count('id', filter=Q(status='late')),
        excused=Count('id', filter=Q(status='excused')),
    )
    total = summary['total'] or 1
    summary['attendance_rate'] = round(
        (summary['present'] + summary['late']) / total * 100, 1
    )

    # Recent 20 records
    recent = qs.order_by('-lesson_session__date')[:20]

    return Response({
        'summary': summary,
        'records': PortalAttendanceSerializer(recent, many=True).data,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def announcements(request):
    """School-wide news & events, most recent first."""
    qs = NewsAndEvents.objects.all().order_by('-upload_time')[:20]
    return Response(PortalAnnouncementSerializer(qs, many=True).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def student_dashboard_stats(request):
    """Aggregated stats for the student dashboard cards."""
    student = _get_student(request.user)
    if not student:
        return Response({'detail': 'No student profile.'}, status=404)

    # Subjects count
    subjects_count = TakenCourse.objects.filter(student=student).values(
        'course'
    ).distinct().count()

    # Average score — prefer new exam system, fall back to old
    latest_term_result = TermResult.objects.filter(
        student=student, is_published=True,
    ).order_by('-class_session__academic_year__start_date', '-class_session__term__order').first()

    if latest_term_result:
        avg_score = round(float(latest_term_result.average_mark), 1)
        subjects_count = max(subjects_count, latest_term_result.subjects_taken)
    else:
        avg = TakenCourse.objects.filter(student=student).aggregate(
            avg_total=Sum('total') / Count('id')
        )
        avg_score = round(float(avg['avg_total'] or 0), 1)

    # Fee balance
    invoice_balance = FeeInvoice.objects.filter(
        student=student,
    ).exclude(status='VOID').aggregate(
        bal=Sum('balance')
    )['bal'] or 0

    prepayment_credit = StudentPrepayment.objects.filter(
        student=student, is_fully_used=False,
    ).aggregate(total=Sum('balance'))['total'] or 0

    fee_balance = float(invoice_balance) - float(prepayment_credit)

    # Attendance rate
    att = SessionAttendance.objects.filter(student=student).aggregate(
        total=Count('id'),
        present=Count('id', filter=Q(status__in=['present', 'late'])),
    )
    att_rate = round(att['present'] / max(att['total'], 1) * 100, 1)

    # Today's lessons
    enrollment = student.current_enrollment
    today_lessons = 0
    if enrollment:
        session_id = getattr(enrollment, 'session_id', None)
        if session_id:
            today_lessons = PlannedLesson.objects.filter(
                class_session_id=session_id,
                date=date.today(),
                status='pending',
            ).count()

    # Recent announcements count
    recent_announcements = NewsAndEvents.objects.filter(
        upload_time__gte=date.today() - timedelta(days=30)
    ).count()

    return Response({
        'subjects_count': subjects_count,
        'avg_score': avg_score,
        'fee_balance': float(fee_balance),
        'attendance_rate': att_rate,
        'today_lessons': today_lessons,
        'recent_announcements': recent_announcements,
    })


# ═══════════════════════════════════════════════════════════
#  PARENT PORTAL ENDPOINTS
# ═══════════════════════════════════════════════════════════

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def parent_profile(request):
    """Parent profile with children summary."""
    parent = _get_parent(request.user)
    if not parent:
        return Response(
            {'detail': 'No parent profile linked to this account.'},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response(ParentProfileSerializer(parent).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def parent_children(request):
    """List all children linked to the parent."""
    parent = _get_parent(request.user)
    if not parent:
        return Response({'detail': 'No parent profile.'}, status=404)

    children = _get_children(parent)
    return Response(ParentChildSummarySerializer(children, many=True).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def parent_child_fees(request, student_id):
    """Fee statement for one of the parent's children."""
    parent = _get_parent(request.user)
    if not parent:
        return Response({'detail': 'No parent profile.'}, status=404)

    children = _get_children(parent)
    if not children.filter(pk=student_id).exists():
        return Response({'detail': 'Not your child.'}, status=403)

    invoices = FeeInvoice.objects.filter(
        student_id=student_id,
    ).exclude(status='VOID').select_related(
        'term', 'academic_year', 'class_session__grade',
    ).prefetch_related(
        'invoice_items__fee_item', 'invoice_items__vote_head',
    ).order_by('-date_issued')

    totals = invoices.aggregate(
        total_invoiced=Sum('total_amount'),
        total_paid=Sum('paid_amount'),
        total_balance=Sum('balance'),
    )

    prepayment_credit = StudentPrepayment.objects.filter(
        student_id=student_id, is_fully_used=False,
    ).aggregate(total=Sum('balance'))['total'] or 0

    invoice_balance = float(totals['total_balance'] or 0)
    net_balance = invoice_balance - float(prepayment_credit)

    return Response({
        'summary': {
            'total_invoiced': float(totals['total_invoiced'] or 0),
            'total_paid': float(totals['total_paid'] or 0),
            'total_balance': net_balance,
            'invoice_balance': invoice_balance,
            'prepayment_credit': float(prepayment_credit),
        },
        'invoices': PortalInvoiceSerializer(invoices, many=True).data,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def parent_child_results(request, student_id):
    """Results for one of the parent's children (old + new exam system)."""
    parent = _get_parent(request.user)
    if not parent:
        return Response({'detail': 'No parent profile.'}, status=404)

    children = _get_children(parent)
    if not children.filter(pk=student_id).exists():
        return Response({'detail': 'Not your child.'}, status=403)

    taken = TakenCourse.objects.filter(
        student_id=student_id,
    ).select_related('course').order_by('-id')

    results = Result.objects.filter(student_id=student_id).order_by('-id')

    # New exam term results (published only)
    term_results = TermResult.objects.filter(
        student_id=student_id,
        is_published=True,
    ).select_related(
        'class_session__term', 'class_session__academic_year',
        'class_session__grade', 'stream',
    ).prefetch_related(
        'subject_results__subject',
    ).order_by('-class_session__academic_year__start_date', '-class_session__term__order')

    return Response({
        'courses': PortalTakenCourseSerializer(taken, many=True).data,
        'results': PortalResultSerializer(results, many=True).data,
        'term_results': PortalTermResultSerializer(term_results, many=True).data,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def parent_child_attendance(request, student_id):
    """Attendance for one of the parent's children."""
    parent = _get_parent(request.user)
    if not parent:
        return Response({'detail': 'No parent profile.'}, status=404)

    children = _get_children(parent)
    if not children.filter(pk=student_id).exists():
        return Response({'detail': 'Not your child.'}, status=403)

    qs = SessionAttendance.objects.filter(
        student_id=student_id,
    ).select_related('lesson_session__subject')

    summary = qs.aggregate(
        total=Count('id'),
        present=Count('id', filter=Q(status='present')),
        absent=Count('id', filter=Q(status='absent')),
        late=Count('id', filter=Q(status='late')),
        excused=Count('id', filter=Q(status='excused')),
    )
    total = summary['total'] or 1
    summary['attendance_rate'] = round(
        (summary['present'] + summary['late']) / total * 100, 1
    )

    recent = qs.order_by('-lesson_session__date')[:20]

    return Response({
        'summary': summary,
        'records': PortalAttendanceSerializer(recent, many=True).data,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def parent_dashboard_stats(request):
    """Aggregated stats for parent dashboard."""
    parent = _get_parent(request.user)
    if not parent:
        return Response({'detail': 'No parent profile.'}, status=404)

    children = _get_children(parent)
    children_count = children.count()

    total_balance = FeeInvoice.objects.filter(
        student__in=children,
    ).exclude(status='VOID').aggregate(
        bal=Sum('balance')
    )['bal'] or 0

    # Average performance across all children
    avg = TakenCourse.objects.filter(
        student__in=children,
    ).aggregate(
        avg_total=Sum('total') / Count('id'),
    )
    avg_score = round(float(avg['avg_total'] or 0), 1)

    recent_announcements = NewsAndEvents.objects.filter(
        upload_time__gte=date.today() - timedelta(days=30),
    ).count()

    return Response({
        'children_count': children_count,
        'total_fee_balance': float(total_balance),
        'avg_performance': avg_score,
        'recent_announcements': recent_announcements,
    })


# ═══════════════════════════════════════════════════════════
#  STUDENT ASSIGNMENTS PORTAL
# ═══════════════════════════════════════════════════════════

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_assignments_portal(request):
    """Get published assignments for the logged-in student."""
    from assignments.views import my_assignments as _fn
    return _fn(request._request)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_assignment_portal(request, assignment_id):
    """Student submits work for an assignment."""
    from assignments.views import submit_assignment as _fn
    return _fn(request._request, assignment_id)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def parent_child_assignments_portal(request, student_id):
    """Parent views assignments for a specific child."""
    from assignments.views import parent_child_assignments as _fn
    return _fn(request._request, student_id)


# ═══════════════════════════════════════════════════════════
#  STUDENT FINANCIAL STATEMENT
# ═══════════════════════════════════════════════════════════

def _build_statement(student, params):
    """Build a chronological financial statement for a student.

    params: dict with optional keys 'academic_year', 'term', 'type' (summary|detailed).
    Returns dict with student info, summary totals, and entries list.
    """
    statement_type = params.get('type', 'summary')
    year_id = params.get('academic_year')
    term_id = params.get('term')

    # Invoices
    invoices = FeeInvoice.objects.filter(
        student=student,
    ).exclude(status='VOID').select_related('term', 'academic_year', 'class_session__grade')

    if statement_type == 'detailed':
        invoices = invoices.prefetch_related('items__vote_head', 'items__fee_item')

    if year_id:
        invoices = invoices.filter(academic_year_id=year_id)
    if term_id:
        invoices = invoices.filter(term_id=term_id)

    # Receipts
    receipts = Receipt.objects.filter(
        student=student,
    ).exclude(status='REVERSED').select_related('payment_method', 'term', 'academic_year')

    if year_id:
        receipts = receipts.filter(academic_year_id=year_id)
    if term_id:
        receipts = receipts.filter(term_id=term_id)

    # Build entries
    entries = []

    for inv in invoices:
        entry = {
            'date': inv.date_issued.isoformat(),
            'type': 'INVOICE',
            'reference': inv.invoice_number,
            'description': 'Fee Invoice – {} {}'.format(
                inv.term.name if inv.term else '',
                inv.academic_year.name if inv.academic_year else '',
            ).strip(),
            'debit': float(inv.total_amount),
            'credit': 0,
        }
        if statement_type == 'detailed':
            entry['items'] = [
                {
                    'description': item.description,
                    'vote_head': item.vote_head.name if item.vote_head else None,
                    'amount': float(item.amount),
                }
                for item in inv.items.all()
            ]
        entries.append(entry)

    for rcpt in receipts:
        entries.append({
            'date': rcpt.received_date.isoformat(),
            'type': 'RECEIPT',
            'reference': rcpt.receipt_number,
            'description': 'Payment – {} {}'.format(
                rcpt.payment_method.name if rcpt.payment_method else 'Cash',
                rcpt.reference or '',
            ).strip(),
            'debit': 0,
            'credit': float(rcpt.amount_received),
        })

    # Sort chronologically
    entries.sort(key=lambda e: e['date'])

    # Running balance
    running = 0
    for entry in entries:
        running += entry['debit'] - entry['credit']
        entry['balance'] = round(running, 2)

    total_invoiced = sum(e['debit'] for e in entries)
    total_paid = sum(e['credit'] for e in entries)

    prepayment_credit = float(
        StudentPrepayment.objects.filter(
            student=student, is_fully_used=False,
        ).aggregate(total=Sum('balance'))['total'] or 0
    )

    return {
        'student_name': student.student.get_full_name,
        'admission_number': student.admission_number,
        'summary': {
            'total_invoiced': round(total_invoiced, 2),
            'total_paid': round(total_paid, 2),
            'balance': round(running, 2),
            'prepayment_credit': prepayment_credit,
            'net_balance': round(running - prepayment_credit, 2),
        },
        'entries': entries,
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_statement(request):
    """Student financial statement.

    Query Params:
    - academic_year: Filter by academic year ID
    - term: Filter by term ID
    - type: 'summary' (default) or 'detailed'
    """
    student = _get_student(request.user)
    if not student:
        return Response({'detail': 'No student profile.'}, status=404)
    return Response(_build_statement(student, request.query_params))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def parent_child_statement(request, student_id):
    """Financial statement for one of the parent's children."""
    parent = _get_parent(request.user)
    if not parent:
        return Response({'detail': 'No parent profile.'}, status=404)

    children = _get_children(parent)
    if not children.filter(pk=student_id).exists():
        return Response({'detail': 'Not your child.'}, status=403)

    student = children.get(pk=student_id)
    return Response(_build_statement(student, request.query_params))
