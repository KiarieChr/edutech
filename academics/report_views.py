"""
academics/report_views.py
Student Management Reporting API — read-only analytics endpoints.
All endpoints require authentication and return JSON summaries suitable
for charts and tables in the frontend StudentReportsDashboard.
"""

from django.db.models import (
    Sum, Count, Q, F, Value, CharField, DecimalField,
    Case, When, IntegerField, FloatField, Avg, Max, Min,
)
from django.db.models.functions import Coalesce, TruncMonth, TruncYear
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Student
from academics.models import ClassSession, StudentSessionEnrollment
from fees.models import FeeInvoice, FeeStructure, FeeItem
from finance.models import Receipt, StudentPrepayment
from lesson_sessions.models import SessionAttendance
from student_management.models import Application
from student_settings.models import AcademicYear, Term


# ─── helpers ────────────────────────────────────────────────────────────────

def _year_filter(qs, year_id, field='academic_year_id'):
    if year_id:
        qs = qs.filter(**{field: year_id})
    return qs


def _term_filter(qs, term_id, field='term_id'):
    if term_id:
        qs = qs.filter(**{field: term_id})
    return qs


# ─── 1. Overview KPIs ────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_overview(request):
    """KPI summary cards for the reports dashboard header."""
    year_id = request.query_params.get('academic_year')
    term_id = request.query_params.get('term')

    students = Student.objects.all()
    enrollments = StudentSessionEnrollment.objects.filter(is_active=True)
    if year_id:
        enrollments = enrollments.filter(session__academic_year_id=year_id)
    if term_id:
        enrollments = enrollments.filter(session__term_id=term_id)

    total_students = students.count()
    active_students = students.filter(status='active').count()
    new_admissions = students.filter(status='active').count()  # proxy

    apps = Application.objects.all()
    if year_id:
        apps = apps.filter(intake__academic_year_id=year_id)

    applicants_total = apps.count()
    applicants_pending = apps.filter(status='pending').count()
    applicants_accepted = apps.filter(status='accepted').count()

    enrolled_count = enrollments.count()

    return Response({
        'total_students': total_students,
        'active_students': active_students,
        'enrolled_this_period': enrolled_count,
        'applicants_total': applicants_total,
        'applicants_pending': applicants_pending,
        'applicants_accepted': applicants_accepted,
    })


# ─── 2. Student List ──────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_student_list(request):
    """Paginated student list with filters for class, stream, status, intake."""
    year_id = request.query_params.get('academic_year')
    term_id = request.query_params.get('term')
    session_id = request.query_params.get('session')
    status_filter = request.query_params.get('status')
    search = request.query_params.get('search', '').strip()
    page = int(request.query_params.get('page', 1))
    page_size = int(request.query_params.get('page_size', 50))

    students = Student.objects.select_related(
        'student', 'intake', 'campus',
    ).order_by('student__last_name', 'student__first_name')

    if status_filter:
        students = students.filter(status=status_filter)
    if search:
        students = students.filter(
            Q(admission_number__icontains=search) |
            Q(student__first_name__icontains=search) |
            Q(student__last_name__icontains=search)
        )

    # Filter by session/class
    if session_id or year_id or term_id:
        enrolled_ids = StudentSessionEnrollment.objects.filter(is_active=True)
        if session_id:
            enrolled_ids = enrolled_ids.filter(session_id=session_id)
        if year_id:
            enrolled_ids = enrolled_ids.filter(session__academic_year_id=year_id)
        if term_id:
            enrolled_ids = enrolled_ids.filter(session__term_id=term_id)
        students = students.filter(
            id__in=enrolled_ids.values('student_id')
        )

    total = students.count()
    start = (page - 1) * page_size
    results = students[start:start + page_size]

    data = []
    for s in results:
        data.append({
            'id': s.id,
            'admission_number': s.admission_number,
            'name': s.student.get_full_name,
            'gender': s.student.gender,
            'status': s.status,
            'admission_date': s.admission_date.isoformat() if s.admission_date else None,
            'intake': s.intake.name if s.intake else None,
            'campus': s.campus.name if s.campus else None,
        })

    return Response({'count': total, 'results': data})


# ─── 3. Class List ────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_class_list(request):
    """Classes/sessions with enrollment counts."""
    year_id = request.query_params.get('academic_year')
    term_id = request.query_params.get('term')

    sessions = ClassSession.objects.select_related(
        'grade', 'term', 'academic_year', 'curriculum', 'curriculum_level',
    ).annotate(
        total_enrolled=Count(
            'student_enrollments',
            filter=Q(student_enrollments__is_active=True),
        ),
        male_count=Count(
            'student_enrollments',
            filter=Q(
                student_enrollments__is_active=True,
                student_enrollments__student__student__gender='M',
            ),
        ),
        female_count=Count(
            'student_enrollments',
            filter=Q(
                student_enrollments__is_active=True,
                student_enrollments__student__student__gender='F',
            ),
        ),
    ).order_by('academic_year__start_date', 'term__order', 'grade__level_order')

    if year_id:
        sessions = sessions.filter(academic_year_id=year_id)
    if term_id:
        sessions = sessions.filter(term_id=term_id)

    data = []
    for s in sessions:
        data.append({
            'id': s.id,
            'name': s.name,
            'grade': s.grade.name if s.grade else None,
            'term': s.term.name if s.term else None,
            'academic_year': s.academic_year.name if s.academic_year else None,
            'curriculum': s.curriculum.name if s.curriculum else None,
            'curriculum_level': s.curriculum_level.name if s.curriculum_level else None,
            'status': s.status,
            'total_enrolled': s.total_enrolled,
            'male_count': s.male_count,
            'female_count': s.female_count,
            'start_date': s.start_date.isoformat() if s.start_date else None,
            'end_date': s.end_date.isoformat() if s.end_date else None,
        })

    return Response({'count': len(data), 'results': data})


# ─── 4. Fee Collections Projection ───────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_fee_collections(request):
    """Per-session fee collection projection vs actuals."""
    year_id = request.query_params.get('academic_year')
    term_id = request.query_params.get('term')

    sessions = ClassSession.objects.select_related(
        'grade', 'term', 'academic_year',
    ).annotate(
        total_enrolled=Count(
            'student_enrollments',
            filter=Q(student_enrollments__is_active=True),
        ),
        expected_amount=Coalesce(Sum(
            'student_enrollments__student__fee_invoices__total_amount',
            filter=Q(
                student_enrollments__is_active=True,
                student_enrollments__student__fee_invoices__class_session=F('id'),
            ),
        ), Value(0), output_field=DecimalField()),
        invoiced_amount=Coalesce(Sum(
            'feeinvoice__total_amount',
            filter=~Q(feeinvoice__status='VOID'),
        ), Value(0), output_field=DecimalField()),
        collected_amount=Coalesce(Sum(
            'feeinvoice__paid_amount',
            filter=~Q(feeinvoice__status='VOID'),
        ), Value(0), output_field=DecimalField()),
        outstanding_amount=Coalesce(Sum(
            'feeinvoice__balance',
            filter=~Q(feeinvoice__status='VOID'),
        ), Value(0), output_field=DecimalField()),
    ).order_by('academic_year__start_date', 'term__order', 'grade__level_order')

    if year_id:
        sessions = sessions.filter(academic_year_id=year_id)
    if term_id:
        sessions = sessions.filter(term_id=term_id)

    # Also get fee structure expected amounts
    structures = {}
    fs_qs = FeeStructure.objects.filter(status='ACTIVE').prefetch_related('items')
    if year_id:
        fs_qs = fs_qs.filter(academic_year_id=year_id)
    if term_id:
        fs_qs = fs_qs.filter(term_id=term_id)
    for fs in fs_qs:
        total = sum(item.amount for item in fs.items.filter(is_optional=False))
        key = (str(fs.academic_year_id), str(fs.term_id), str(fs.grade_id))
        structures[key] = float(total)

    data = []
    for s in sessions:
        key = (str(s.academic_year_id), str(s.term_id), str(s.grade_id))
        structure_per_student = structures.get(key, 0)
        projected = structure_per_student * s.total_enrolled

        invoiced = float(s.invoiced_amount)
        collected = float(s.collected_amount)
        outstanding = float(s.outstanding_amount)

        data.append({
            'id': s.id,
            'session_name': s.name,
            'grade': s.grade.name if s.grade else None,
            'term': s.term.name if s.term else None,
            'academic_year': s.academic_year.name if s.academic_year else None,
            'enrolled': s.total_enrolled,
            'fee_per_student': structure_per_student,
            'projected': projected,
            'invoiced': invoiced,
            'collected': collected,
            'outstanding': outstanding,
            'collection_rate': round(collected / invoiced * 100, 1) if invoiced > 0 else 0,
        })

    totals = {
        'projected': sum(r['projected'] for r in data),
        'invoiced': sum(r['invoiced'] for r in data),
        'collected': sum(r['collected'] for r in data),
        'outstanding': sum(r['outstanding'] for r in data),
    }
    totals['collection_rate'] = round(
        totals['collected'] / totals['invoiced'] * 100, 1
    ) if totals['invoiced'] > 0 else 0

    return Response({'totals': totals, 'results': data})


# ─── 5. Attendance Statistics ─────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_attendance(request):
    """Attendance stats grouped by session/stream/curriculum."""
    year_id = request.query_params.get('academic_year')
    term_id = request.query_params.get('term')
    session_id = request.query_params.get('session')
    group_by = request.query_params.get('group_by', 'session')  # session|stream|curriculum_level|curriculum

    att = SessionAttendance.objects.select_related(
        'lesson_session__class_session__grade',
        'lesson_session__class_session__term',
        'lesson_session__class_session__academic_year',
        'lesson_session__class_session__curriculum',
        'lesson_session__class_session__curriculum_level',
        'student__stream',
    )

    if year_id:
        att = att.filter(lesson_session__class_session__academic_year_id=year_id)
    if term_id:
        att = att.filter(lesson_session__class_session__term_id=term_id)
    if session_id:
        att = att.filter(lesson_session__class_session_id=session_id)

    # Aggregate per group
    if group_by == 'stream':
        rows = att.values(
            group_label=F('student__stream__name'),
        )
    elif group_by == 'curriculum_level':
        rows = att.values(
            group_label=F('lesson_session__class_session__curriculum_level__name'),
        )
    elif group_by == 'curriculum':
        rows = att.values(
            group_label=F('lesson_session__class_session__curriculum__name'),
        )
    else:
        rows = att.values(
            group_label=F('lesson_session__class_session__name'),
        )

    rows = rows.annotate(
        total=Count('id'),
        present=Count('id', filter=Q(status='present')),
        absent=Count('id', filter=Q(status='absent')),
        late=Count('id', filter=Q(status='late')),
        excused=Count('id', filter=Q(status='excused')),
    ).order_by('-total')

    results = []
    for r in rows:
        total = r['total'] or 1
        present = r['present'] + r['late']
        rate = round(present / total * 100, 1)
        results.append({
            'label': r['group_label'] or 'Unknown',
            'total': r['total'],
            'present': r['present'],
            'absent': r['absent'],
            'late': r['late'],
            'excused': r['excused'],
            'attendance_rate': rate,
        })

    overall_total = sum(r['total'] for r in results)
    overall_present = sum(r['present'] + r['late'] for r in results)
    overall_rate = round(overall_present / overall_total * 100, 1) if overall_total else 0

    return Response({
        'group_by': group_by,
        'overall_rate': overall_rate,
        'results': results,
    })


# ─── 6. Class Statistics ──────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_class_statistics(request):
    """Enrollment overview per class session."""
    year_id = request.query_params.get('academic_year')
    term_id = request.query_params.get('term')

    sessions = ClassSession.objects.select_related(
        'grade', 'term', 'academic_year', 'curriculum_level',
    ).annotate(
        total=Count('student_enrollments', filter=Q(student_enrollments__is_active=True)),
        male=Count(
            'student_enrollments',
            filter=Q(
                student_enrollments__is_active=True,
                student_enrollments__student__student__gender='M',
            ),
        ),
        female=Count(
            'student_enrollments',
            filter=Q(
                student_enrollments__is_active=True,
                student_enrollments__student__student__gender='F',
            ),
        ),
        promoted=Count(
            'student_enrollments',
            filter=Q(
                student_enrollments__is_active=True,
                student_enrollments__progression_status='promoted',
            ),
        ),
        retained=Count(
            'student_enrollments',
            filter=Q(
                student_enrollments__is_active=True,
                student_enrollments__progression_status='retained',
            ),
        ),
        graduated=Count(
            'student_enrollments',
            filter=Q(
                student_enrollments__is_active=True,
                student_enrollments__progression_status='graduated',
            ),
        ),
    ).order_by('grade__level_order', 'term__order')

    if year_id:
        sessions = sessions.filter(academic_year_id=year_id)
    if term_id:
        sessions = sessions.filter(term_id=term_id)

    data = []
    for s in sessions:
        data.append({
            'id': s.id,
            'name': s.name,
            'grade': s.grade.name if s.grade else None,
            'term': s.term.name if s.term else None,
            'academic_year': s.academic_year.name if s.academic_year else None,
            'curriculum_level': s.curriculum_level.name if s.curriculum_level else None,
            'status': s.status,
            'total': s.total,
            'male': s.male,
            'female': s.female,
            'promoted': s.promoted,
            'retained': s.retained,
            'graduated': s.graduated,
        })

    return Response({'count': len(data), 'results': data})


# ─── 7. Session Statistics ────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_session_statistics(request):
    """Statistics grouped by academic year / term."""
    year_id = request.query_params.get('academic_year')

    # Sessions per academic year with totals
    years = AcademicYear.objects.all().order_by('-start_date')
    if year_id:
        years = years.filter(id=year_id)

    data = []
    for year in years:
        sessions = ClassSession.objects.filter(academic_year=year)
        enrollments = StudentSessionEnrollment.objects.filter(
            session__academic_year=year, is_active=True,
        )
        invoices = FeeInvoice.objects.filter(
            academic_year=year,
        ).exclude(status='VOID')

        # Per-term breakdown
        terms = Term.objects.filter(
            id__in=sessions.values_list('term_id', flat=True),
        ).distinct().order_by('order')

        term_data = []
        for term in terms:
            t_enroll = enrollments.filter(session__term=term).count()
            t_sessions = sessions.filter(term=term).count()
            t_invoiced = float(
                invoices.filter(term=term).aggregate(s=Sum('total_amount'))['s'] or 0
            )
            t_collected = float(
                invoices.filter(term=term).aggregate(s=Sum('paid_amount'))['s'] or 0
            )
            term_data.append({
                'term': term.name,
                'sessions': t_sessions,
                'enrollments': t_enroll,
                'invoiced': t_invoiced,
                'collected': t_collected,
                'collection_rate': round(t_collected / t_invoiced * 100, 1) if t_invoiced else 0,
            })

        total_enrolled = enrollments.count()
        total_invoiced = float(invoices.aggregate(s=Sum('total_amount'))['s'] or 0)
        total_collected = float(invoices.aggregate(s=Sum('paid_amount'))['s'] or 0)

        data.append({
            'academic_year': year.name,
            'academic_year_id': year.id,
            'total_sessions': sessions.count(),
            'total_enrollments': total_enrolled,
            'total_invoiced': total_invoiced,
            'total_collected': total_collected,
            'collection_rate': round(total_collected / total_invoiced * 100, 1) if total_invoiced else 0,
            'terms': term_data,
        })

    return Response({'results': data})


# ─── 8. Applicant Statistics ──────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_applicant_statistics(request):
    """Application counts by status, intake, campus, with year-on-year comparison."""
    year_id = request.query_params.get('academic_year')

    apps = Application.objects.all()
    if year_id:
        apps = apps.filter(intake__academic_year_id=year_id)

    # By status
    by_status = list(
        apps.values('application_status').annotate(count=Count('id')).order_by('-count')
    )

    # By gender
    by_gender = list(
        apps.values('gender').annotate(count=Count('id')).order_by('-count')
    )

    # By applying_for_level
    by_level = list(
        apps.values(
            level=F('applying_for_level__name'),
        ).annotate(count=Count('id')).order_by('-count')
    )

    # By campus
    by_campus = list(
        apps.values(
            campus_name=F('campus__name'),
        ).annotate(count=Count('id')).order_by('-count')
    )

    # Monthly trend
    monthly = list(
        apps.annotate(month=TruncMonth('created_at')).values('month').annotate(
            count=Count('id'),
            accepted=Count('id', filter=Q(application_status='accepted')),
            rejected=Count('id', filter=Q(application_status='rejected')),
        ).order_by('month')
    )
    for row in monthly:
        if row['month']:
            row['month'] = row['month'].strftime('%Y-%m')

    # Year-on-year comparison (last 3 years)
    yoy = list(
        Application.objects.annotate(year=TruncYear('created_at')).values('year').annotate(
            total=Count('id'),
            accepted=Count('id', filter=Q(application_status='accepted')),
            rejected=Count('id', filter=Q(application_status='rejected')),
            pending=Count('id', filter=Q(application_status='pending')),
        ).order_by('year')
    )
    for row in yoy:
        if row['year']:
            row['year'] = row['year'].strftime('%Y')

    totals = {
        'total': apps.count(),
        'pending': apps.filter(application_status='pending').count(),
        'accepted': apps.filter(application_status='accepted').count(),
        'rejected': apps.filter(application_status='rejected').count(),
        'waitlist': apps.filter(application_status='waitlist').count(),
        'interview': apps.filter(application_status='interview').count(),
    }

    return Response({
        'totals': totals,
        'by_status': by_status,
        'by_gender': by_gender,
        'by_level': by_level,
        'by_campus': by_campus,
        'monthly_trend': monthly,
        'year_on_year': yoy,
    })


# ─── 9. Enrollment Statistics ────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_enrollment_statistics(request):
    """Enrollment stats and comparisons across years/terms."""
    year_id = request.query_params.get('academic_year')
    term_id = request.query_params.get('term')

    enroll = StudentSessionEnrollment.objects.select_related(
        'session__academic_year', 'session__term', 'session__grade',
        'session__curriculum', 'student__student', 'stream',
    )

    if year_id:
        enroll = enroll.filter(session__academic_year_id=year_id)
    if term_id:
        enroll = enroll.filter(session__term_id=term_id)

    # By class session
    by_session = list(
        enroll.values(
            session_name=F('session__name'),
            grade_name=F('session__grade__name'),
        ).annotate(
            total=Count('id', filter=Q(is_active=True)),
            male=Count('id', filter=Q(is_active=True, student__student__gender='M')),
            female=Count('id', filter=Q(is_active=True, student__student__gender='F')),
            new_students=Count('id', filter=Q(is_active=True, progression_status='new')),
            promoted=Count('id', filter=Q(is_active=True, progression_status='promoted')),
        ).order_by('grade_name')
    )

    # By progression status
    by_progression = list(
        enroll.filter(is_active=True).values('progression_status').annotate(
            count=Count('id')
        ).order_by('-count')
    )

    # Monthly enrollment trend
    monthly = list(
        enroll.annotate(month=TruncMonth('reporting_date')).values('month').annotate(
            count=Count('id')
        ).order_by('month')
    )
    for row in monthly:
        if row['month']:
            row['month'] = row['month'].strftime('%Y-%m')

    # Year-on-year (all time)
    yoy = list(
        StudentSessionEnrollment.objects.annotate(
            year=TruncYear('reporting_date'),
        ).values('year').annotate(
            total=Count('id'),
            active=Count('id', filter=Q(is_active=True)),
        ).order_by('year')
    )
    for row in yoy:
        if row['year']:
            row['year'] = row['year'].strftime('%Y')

    # Summary
    summary = enroll.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(is_active=True)),
        male=Count('id', filter=Q(is_active=True, student__student__gender='M')),
        female=Count('id', filter=Q(is_active=True, student__student__gender='F')),
    )

    return Response({
        'summary': summary,
        'by_session': by_session,
        'by_progression': by_progression,
        'monthly_trend': monthly,
        'year_on_year': yoy,
    })


# ─── 10. Student Statement of Account (admin view) ───────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_student_statement(request):
    """
    Full financial statement for a specific student.
    Requires ?student_id=X query parameter.
    Returns chronological debits/credits with running balance.
    """
    student_id = request.query_params.get('student_id')
    if not student_id:
        return Response({'detail': 'student_id is required.'}, status=400)

    try:
        student = Student.objects.select_related('student').get(pk=student_id)
    except Student.DoesNotExist:
        return Response({'detail': 'Student not found.'}, status=404)

    year_id = request.query_params.get('academic_year')
    term_id = request.query_params.get('term')

    invoices = FeeInvoice.objects.filter(
        student=student,
    ).exclude(status='VOID').select_related('term', 'academic_year', 'class_session__grade')
    if year_id:
        invoices = invoices.filter(academic_year_id=year_id)
    if term_id:
        invoices = invoices.filter(term_id=term_id)

    receipts = Receipt.objects.filter(
        student=student,
    ).exclude(status='REVERSED').select_related('payment_method', 'term', 'academic_year')
    if year_id:
        receipts = receipts.filter(academic_year_id=year_id)
    if term_id:
        receipts = receipts.filter(term_id=term_id)

    entries = []
    for inv in invoices:
        entries.append({
            'date': inv.date_issued.isoformat(),
            'type': 'INVOICE',
            'reference': inv.invoice_number,
            'description': 'Fee Invoice – {} {}'.format(
                inv.term.name if inv.term else '',
                inv.academic_year.name if inv.academic_year else '',
            ).strip(),
            'debit': float(inv.total_amount),
            'credit': 0,
            'term': inv.term.name if inv.term else None,
            'grade': inv.class_session.grade.name if inv.class_session and inv.class_session.grade else None,
        })

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
            'term': rcpt.term.name if rcpt.term else None,
        })

    entries.sort(key=lambda e: e['date'])

    running = 0
    for e in entries:
        running += e['debit'] - e['credit']
        e['balance'] = round(running, 2)

    prepayment_credit = float(
        StudentPrepayment.objects.filter(
            student=student, is_fully_used=False,
        ).aggregate(total=Sum('balance'))['total'] or 0
    )

    total_invoiced = sum(e['debit'] for e in entries)
    total_paid = sum(e['credit'] for e in entries)

    return Response({
        'student': {
            'id': student.id,
            'name': student.student.get_full_name,
            'admission_number': student.admission_number,
            'status': student.status,
        },
        'summary': {
            'total_invoiced': round(total_invoiced, 2),
            'total_paid': round(total_paid, 2),
            'invoice_balance': round(running, 2),
            'prepayment_credit': prepayment_credit,
            'net_balance': round(running - prepayment_credit, 2),
        },
        'entries': entries,
    })


# ─── 11. Academic Performance ────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_academic(request):
    """Average exam marks by class and by subject, with current vs previous term."""
    from examinations.models import StudentMark, TermResult, TermSubjectResult

    year_id = request.query_params.get('academic_year')
    term_id = request.query_params.get('term')

    marks = StudentMark.objects.select_related(
        'examination__class_session__grade',
        'examination__class_session__term',
        'examination__subject',
    ).filter(is_absent=False)

    if year_id:
        marks = marks.filter(examination__class_session__academic_year_id=year_id)
    if term_id:
        marks = marks.filter(examination__class_session__term_id=term_id)

    # Mean score by class (compare current term vs previous)
    by_class_raw = list(
        marks.values(
            grade_name=F('examination__class_session__grade__name'),
            session_id=F('examination__class_session__id'),
        ).annotate(avg=Avg('raw_mark'), hi=Max('raw_mark'), lo=Min('raw_mark'))
        .order_by('grade_name')
    )

    # Build previous term comparison using TermResult
    term_results = TermResult.objects.select_related('class_session__grade', 'class_session__term')
    if year_id:
        term_results = term_results.filter(class_session__academic_year_id=year_id)

    prev_avgs = {}
    if term_id:
        # Get term order to find previous
        try:
            from student_settings.models import Term as TermModel
            current_term = TermModel.objects.get(pk=term_id)
            prev_term = TermModel.objects.filter(
                academic_year=current_term.academic_year,
                order__lt=current_term.order,
            ).order_by('-order').first()
            if prev_term:
                prev_rows = TermResult.objects.filter(
                    class_session__academic_year=current_term.academic_year,
                    class_session__term=prev_term,
                ).values(grade_name=F('class_session__grade__name')).annotate(avg=Avg('average_mark'))
                prev_avgs = {r['grade_name']: round(float(r['avg']), 1) for r in prev_rows}
        except Exception:
            pass

    mean_score = []
    seen_grades = set()
    for r in by_class_raw:
        grade = r['grade_name'] or 'Unknown'
        if grade not in seen_grades:
            seen_grades.add(grade)
            mean_score.append({
                'class': grade,
                'current': round(float(r['avg'] or 0), 1),
                'previous': prev_avgs.get(grade, 0),
            })

    # Average by subject
    by_subject = list(
        marks.values(subject=F('examination__subject__name'))
        .annotate(avg=Avg('raw_mark'))
        .order_by('-avg')
    )
    subject_performance = [
        {'subject': r['subject'] or 'Unknown', 'avg': round(float(r['avg'] or 0), 1)}
        for r in by_subject
    ]

    # Detailed table: class + subject
    table_raw = list(
        marks.values(
            grade_name=F('examination__class_session__grade__name'),
            subject=F('examination__subject__name'),
        ).annotate(
            avg=Avg('raw_mark'),
            hi=Max('raw_mark'),
            lo=Min('raw_mark'),
        ).order_by('grade_name', '-avg')
    )

    table = []
    for r in table_raw:
        avg = round(float(r['avg'] or 0), 1)
        rating = 'Good' if avg >= 70 else ('Average' if avg >= 50 else 'Poor')
        table.append({
            'class': r['grade_name'] or 'Unknown',
            'subject': r['subject'] or 'Unknown',
            'avg': avg,
            'high': round(float(r['hi'] or 0), 1),
            'low': round(float(r['lo'] or 0), 1),
            'rating': rating,
        })

    return Response({
        'meanScore': mean_score,
        'subjectPerformance': subject_performance,
        'table': table,
    })


# ─── 12. Transfers / Status Changes ─────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_transfers(request):
    """Students with transferred/dropout status changes."""
    year_id = request.query_params.get('academic_year')
    term_id = request.query_params.get('term')

    students = Student.objects.select_related('student').filter(
        status__in=['transferred', 'inactive', 'dropped'],
    ).order_by('-updated_at')

    # Also count transfer-ins (previous_school_name is set = came from another school)
    transfers_in = Student.objects.filter(
        status='active',
        previous_school_name__isnull=False,
    ).exclude(previous_school_name='').count()

    transfers_out = students.filter(status='transferred').count()
    dropouts = students.filter(status__in=['inactive', 'dropped']).count()

    table = []
    for s in students[:100]:
        status_label = {
            'transferred': 'Transfer Out',
            'inactive': 'Dropout',
            'dropped': 'Dropout',
        }.get(s.status, s.status.title())
        date_val = (
            s.leaving_date.isoformat() if hasattr(s, 'leaving_date') and s.leaving_date
            else s.updated_at.date().isoformat() if s.updated_at else ''
        )
        table.append({
            'student': s.student.get_full_name,
            'adm': s.admission_number or '',
            'status': status_label,
            'reason': s.transfer_reason or '',
            'date': date_val,
        })

    stats = [
        {'name': 'Transfer In', 'value': transfers_in, 'color': '#10B981'},
        {'name': 'Transfer Out', 'value': transfers_out, 'color': '#EF4444'},
        {'name': 'Dropout', 'value': dropouts, 'color': '#F59E0B'},
    ]

    return Response({'stats': stats, 'table': table})


# ─── 13. Demographics ────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_demographics(request):
    """Age distribution and gender breakdown of current students."""
    from django.utils import timezone
    import datetime

    year_id = request.query_params.get('academic_year')
    term_id = request.query_params.get('term')

    students = Student.objects.select_related('student').filter(status='active')

    if year_id or term_id:
        enrolled_ids = StudentSessionEnrollment.objects.filter(is_active=True)
        if year_id:
            enrolled_ids = enrolled_ids.filter(session__academic_year_id=year_id)
        if term_id:
            enrolled_ids = enrolled_ids.filter(session__term_id=term_id)
        students = students.filter(id__in=enrolled_ids.values('student_id'))

    today = timezone.now().date()
    buckets = [
        ('Under 6', 0, 5),
        ('6–8', 6, 8),
        ('9–11', 9, 11),
        ('12–14', 12, 14),
        ('15–17', 15, 17),
        ('18+', 18, 99),
    ]

    age_dist = []
    table = []
    for label, min_age, max_age in buckets:
        min_dob = today.replace(year=today.year - max_age - 1)
        max_dob = today.replace(year=today.year - min_age)
        qs = students.filter(
            student__date_of_birth__isnull=False,
            student__date_of_birth__gt=min_dob,
            student__date_of_birth__lte=max_dob,
        )
        total = qs.count()
        male = qs.filter(student__gender='M').count()
        female = qs.filter(student__gender='F').count()
        age_dist.append({'range': label, 'count': total})
        table.append({'ageGroup': f'{label} Years', 'male': male, 'female': female, 'total': total})

    # Gender overall
    total_active = students.count()
    male_total = students.filter(student__gender='M').count()
    female_total = students.filter(student__gender='F').count()
    unknown_gender = total_active - male_total - female_total

    return Response({
        'ageDistribution': age_dist,
        'table': table,
        'genderSummary': {
            'male': male_total,
            'female': female_total,
            'unknown': unknown_gender,
            'total': total_active,
        },
    })
