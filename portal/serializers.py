from rest_framework import serializers
from django.db.models import Sum
from accounts.models import Student, Parent
from fees.models import FeeInvoice, FeeInvoiceItem
from finance.models import Receipt, ReceiptAllocation
from result.models import TakenCourse, Result
from scheduled_lessons.models import PlannedLesson
from lesson_sessions.models import SessionAttendance, LessonSession
from core.models import NewsAndEvents
from examinations.models import (
    TermResult, TermSubjectResult, StudentMark, Examination,
)


# ─── Profile ──────────────────────────────────────────────

class PortalProfileSerializer(serializers.ModelSerializer):
    """Full student profile for the logged-in student."""
    user_id = serializers.IntegerField(source='student.id', read_only=True)
    username = serializers.CharField(source='student.username', read_only=True)
    email = serializers.EmailField(source='student.email', read_only=True)
    first_name = serializers.CharField(source='student.first_name', read_only=True)
    last_name = serializers.CharField(source='student.last_name', read_only=True)
    full_name = serializers.CharField(source='student.get_full_name', read_only=True)
    gender = serializers.CharField(source='student.gender', read_only=True)
    phone = serializers.CharField(source='student.phone', read_only=True)
    picture_url = serializers.SerializerMethodField()

    # Current enrollment
    current_grade_name = serializers.CharField(
        source='current_grade.name', read_only=True, allow_null=True
    )
    current_stream_name = serializers.CharField(
        source='current_stream.name', read_only=True, allow_null=True
    )
    current_academic_year_name = serializers.CharField(
        source='current_academic_year.name', read_only=True, allow_null=True
    )
    current_term_name = serializers.CharField(
        source='current_term.name', read_only=True, allow_null=True
    )

    # Campus
    campus_name = serializers.CharField(
        source='campus.name', read_only=True, allow_null=True
    )

    class Meta:
        model = Student
        fields = [
            'id', 'user_id', 'username', 'email', 'first_name', 'last_name',
            'full_name', 'gender', 'phone', 'picture_url',
            'admission_number', 'date_of_birth', 'nationality', 'religion',
            'birth_certificate_number', 'home_address',
            'medical_conditions', 'allergies', 'special_needs', 'blood_group',
            'emergency_contact_name', 'emergency_contact_phone',
            'emergency_contact_relationship',
            'current_grade_name', 'current_stream_name',
            'current_academic_year_name', 'current_term_name',
            'campus_name', 'admission_date', 'status',
        ]

    def get_picture_url(self, obj):
        try:
            return obj.student.get_picture()
        except Exception:
            return None


class PortalProfileUpdateSerializer(serializers.ModelSerializer):
    """Fields the student is allowed to edit."""
    class Meta:
        model = Student
        fields = [
            'home_address', 'emergency_contact_name',
            'emergency_contact_phone', 'emergency_contact_relationship',
        ]


# ─── Fees ─────────────────────────────────────────────────

class PortalInvoiceItemSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = FeeInvoiceItem
        fields = ['id', 'name', 'description', 'amount', 'is_optional']

    def get_name(self, obj):
        if obj.vote_head:
            return obj.vote_head.name
        if obj.fee_item:
            return obj.fee_item.name
        return obj.description or '—'


class PortalInvoiceSerializer(serializers.ModelSerializer):
    items = PortalInvoiceItemSerializer(many=True, read_only=True)
    term_name = serializers.CharField(source='term.name', read_only=True)
    year_name = serializers.CharField(source='academic_year.name', read_only=True)
    grade_name = serializers.SerializerMethodField()

    class Meta:
        model = FeeInvoice
        fields = [
            'id', 'invoice_number', 'date_issued', 'due_date', 'status',
            'total_amount', 'paid_amount', 'balance',
            'term_name', 'year_name', 'grade_name', 'items',
        ]

    def get_grade_name(self, obj):
        try:
            return obj.class_session.grade.name
        except Exception:
            return None


class PortalReceiptAllocationSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(
        source='invoice.invoice_number', read_only=True, allow_null=True
    )

    class Meta:
        model = ReceiptAllocation
        fields = ['id', 'invoice_number', 'amount']


class PortalReceiptSerializer(serializers.ModelSerializer):
    allocations = PortalReceiptAllocationSerializer(many=True, read_only=True)
    payment_method_name = serializers.CharField(
        source='payment_method.name', read_only=True
    )
    term_name = serializers.CharField(
        source='term.name', read_only=True, allow_null=True
    )
    year_name = serializers.CharField(
        source='academic_year.name', read_only=True, allow_null=True
    )

    class Meta:
        model = Receipt
        fields = [
            'id', 'receipt_number', 'receipt_type', 'payer_name',
            'amount_received', 'amount_allocated',
            'payment_method_name', 'reference', 'received_date',
            'term_name', 'year_name', 'status', 'allocations',
        ]


# ─── Results ──────────────────────────────────────────────

class PortalTakenCourseSerializer(serializers.ModelSerializer):
    subject_name = serializers.SerializerMethodField()

    class Meta:
        model = TakenCourse
        fields = [
            'id', 'subject_name',
            'assignment', 'mid_exam', 'quiz', 'attendance',
            'final_exam', 'total', 'grade', 'point', 'comment',
        ]

    def get_subject_name(self, obj):
        try:
            return obj.course.title
        except Exception:
            return str(obj.course)


class PortalResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = Result
        fields = ['id', 'gpa', 'cgpa', 'session']


# ─── Timetable ────────────────────────────────────────────

class PortalTimetableSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    teacher_name = serializers.SerializerMethodField()
    room_name = serializers.SerializerMethodField()
    day_of_week = serializers.SerializerMethodField()

    class Meta:
        model = PlannedLesson
        fields = [
            'id', 'date', 'status',
            'subject_name', 'teacher_name', 'room_name',
            'scheduled_start_time', 'scheduled_end_time',
            'day_of_week',
        ]

    def get_teacher_name(self, obj):
        try:
            return obj.expected_teacher.get_full_name()
        except Exception:
            return None

    def get_room_name(self, obj):
        try:
            return obj.room.name
        except Exception:
            return None

    def get_day_of_week(self, obj):
        if obj.date:
            return obj.date.strftime('%A')
        return None


# ─── Attendance ───────────────────────────────────────────

class PortalAttendanceSerializer(serializers.ModelSerializer):
    subject_name = serializers.SerializerMethodField()
    date = serializers.SerializerMethodField()

    class Meta:
        model = SessionAttendance
        fields = ['id', 'status', 'date', 'subject_name', 'minutes_late', 'notes']

    def get_subject_name(self, obj):
        try:
            return obj.lesson_session.subject.name
        except Exception:
            return None

    def get_date(self, obj):
        try:
            return obj.lesson_session.date
        except Exception:
            return None


# ─── Announcements ────────────────────────────────────────

class PortalAnnouncementSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsAndEvents
        fields = ['id', 'title', 'summary', 'posted_as', 'upload_time']


# ─── Parent portal ────────────────────────────────────────

class ParentChildSummarySerializer(serializers.ModelSerializer):
    """Summary card for each child linked to a parent."""
    full_name = serializers.CharField(source='student.get_full_name', read_only=True)
    picture_url = serializers.SerializerMethodField()
    current_grade_name = serializers.CharField(
        source='current_grade.name', read_only=True, allow_null=True
    )
    current_stream_name = serializers.CharField(
        source='current_stream.name', read_only=True, allow_null=True
    )
    fee_balance = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = [
            'id', 'admission_number', 'full_name', 'picture_url',
            'current_grade_name', 'current_stream_name',
            'status', 'fee_balance',
        ]

    def get_picture_url(self, obj):
        try:
            return obj.student.get_picture()
        except Exception:
            return None

    def get_fee_balance(self, obj):
        total = obj.fee_invoices.exclude(
            status='VOID'
        ).aggregate(
            bal=Sum('balance')
        )['bal']
        return float(total) if total else 0


class ParentProfileSerializer(serializers.ModelSerializer):
    """Parent's own profile."""
    full_name = serializers.SerializerMethodField()
    email = serializers.EmailField(source='user.email', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    children = serializers.SerializerMethodField()

    class Meta:
        model = Parent
        fields = [
            'id', 'username', 'email', 'full_name',
            'first_name', 'last_name', 'phone',
            'relation_ship', 'children',
        ]

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"

    def get_children(self, obj):
        # After migration: obj.children.all()
        # Before migration (OneToOne): wrap single student
        students = []
        if hasattr(obj, 'children'):
            students = list(obj.children.filter(status='active'))
        elif obj.student:
            students = [obj.student]
        return ParentChildSummarySerializer(students, many=True).data


# ─── Examination Results (new examinations app) ──────────

class PortalSubjectResultSerializer(serializers.ModelSerializer):
    """Per-subject result within a term."""
    subject_name = serializers.CharField(source='subject.name', read_only=True)

    class Meta:
        model = TermSubjectResult
        fields = [
            'id', 'subject_name', 'weighted_mark', 'grade', 'points',
            'grade_label', 'assessment_breakdown', 'teacher_remark',
            'subject_rank', 'total_in_subject',
        ]


class PortalTermResultSerializer(serializers.ModelSerializer):
    """Aggregated term result with subject breakdowns."""
    subject_results = PortalSubjectResultSerializer(many=True, read_only=True)
    term_name = serializers.CharField(source='class_session.term.name', read_only=True)
    year_name = serializers.CharField(source='class_session.academic_year.name', read_only=True)
    grade_name = serializers.CharField(source='class_session.grade.name', read_only=True)
    stream_name = serializers.SerializerMethodField()

    class Meta:
        model = TermResult
        fields = [
            'id', 'term_name', 'year_name', 'grade_name', 'stream_name',
            'total_marks', 'total_points', 'average_mark', 'average_points',
            'subjects_taken', 'overall_grade', 'overall_grade_label',
            'class_rank', 'stream_rank', 'grade_rank',
            'total_in_class', 'total_in_stream', 'total_in_grade',
            'class_teacher_remark', 'principal_remark',
            'is_published', 'subject_results',
        ]

    def get_stream_name(self, obj):
        try:
            return obj.stream.name if obj.stream else None
        except Exception:
            return None


class PortalExamMarkSerializer(serializers.ModelSerializer):
    """Individual exam mark for the student (used for detailed view)."""
    subject_name = serializers.CharField(source='examination.subject.name', read_only=True)
    assessment_name = serializers.CharField(source='examination.assessment_type.name', read_only=True)
    exam_name = serializers.CharField(source='examination.name', read_only=True)
    max_mark = serializers.DecimalField(
        source='examination.max_mark', max_digits=5, decimal_places=2, read_only=True
    )

    class Meta:
        model = StudentMark
        fields = [
            'id', 'subject_name', 'assessment_name', 'exam_name',
            'raw_mark', 'normalized_mark', 'max_mark',
            'grade', 'points', 'grade_label',
            'is_absent', 'teacher_remark',
        ]
