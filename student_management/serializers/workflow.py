from rest_framework import serializers
from student_management.models.application_fee import ApplicationFeePayment
from student_management.models.interview import InterviewSchedule
from student_management.models.reporting import ReportingRecord


# ─────────────────────────────────────────────────────────────────────────────
# Application Fee Payment
# ─────────────────────────────────────────────────────────────────────────────

class ApplicationFeePaymentSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payment_method_display = serializers.CharField(
        source='get_payment_method_display', read_only=True, allow_null=True
    )
    is_cleared = serializers.BooleanField(read_only=True)
    recorded_by_name = serializers.CharField(
        source='recorded_by.get_full_name', read_only=True, allow_null=True
    )

    class Meta:
        model = ApplicationFeePayment
        fields = '__all__'
        read_only_fields = ['id', 'application', 'created_at', 'updated_at']


class RecordFeePaymentSerializer(serializers.Serializer):
    """Input for the record_fee_payment action."""
    payment_method = serializers.ChoiceField(choices=ApplicationFeePayment.PAYMENT_METHOD_CHOICES)
    payment_date = serializers.DateField()
    payment_reference = serializers.CharField(max_length=100, required=False, allow_blank=True)
    receipt_number = serializers.CharField(max_length=100, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class WaiveFeeSerializer(serializers.Serializer):
    """Input for waiving the fee."""
    waiver_reason = serializers.CharField(min_length=10, help_text='Reason must be at least 10 characters.')


# ─────────────────────────────────────────────────────────────────────────────
# Interview Schedule
# ─────────────────────────────────────────────────────────────────────────────

class InterviewScheduleSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    outcome_display = serializers.CharField(source='get_outcome_display', read_only=True)
    is_passed = serializers.BooleanField(read_only=True)
    interviewer_name = serializers.CharField(
        source='interviewer.get_full_name', read_only=True, allow_null=True
    )
    completed_by_name = serializers.CharField(
        source='completed_by.get_full_name', read_only=True, allow_null=True
    )

    class Meta:
        model = InterviewSchedule
        fields = '__all__'
        read_only_fields = ['id', 'application', 'created_at', 'updated_at']


class ScheduleInterviewSerializer(serializers.Serializer):
    """Input for scheduling an interview."""
    scheduled_date = serializers.DateTimeField(help_text='ISO-8601 datetime, e.g. 2026-06-15T09:00:00')
    venue = serializers.CharField(max_length=200, required=False, allow_blank=True)
    duration_minutes = serializers.IntegerField(default=30, min_value=5)
    interviewer = serializers.IntegerField(required=False, allow_null=True, help_text='User ID of the interviewer')
    panel_members = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list,
        help_text='List of User IDs for additional panel members'
    )


class RecordInterviewOutcomeSerializer(serializers.Serializer):
    """Input for recording interview outcome."""
    outcome = serializers.ChoiceField(choices=[('pass', 'Pass'), ('conditional', 'Conditional Pass'), ('fail', 'Fail')])
    score = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    max_score = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    feedback_to_applicant = serializers.CharField(required=False, allow_blank=True)
    status = serializers.ChoiceField(
        choices=['completed', 'no_show', 'cancelled'],
        default='completed'
    )


# ─────────────────────────────────────────────────────────────────────────────
# Reporting Record
# ─────────────────────────────────────────────────────────────────────────────

class ReportingRecordSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    is_cleared = serializers.BooleanField(read_only=True)
    received_by_name = serializers.CharField(
        source='received_by.get_full_name', read_only=True, allow_null=True
    )

    class Meta:
        model = ReportingRecord
        fields = '__all__'
        read_only_fields = ['id', 'application', 'created_at', 'updated_at']


class ScheduleReportingSerializer(serializers.Serializer):
    """Input for scheduling a reporting day."""
    expected_date = serializers.DateField()
    notes = serializers.CharField(required=False, allow_blank=True)


class RecordReportingSerializer(serializers.Serializer):
    """Input for marking a student as reported."""
    actual_date = serializers.DateField()
    documents_received = serializers.BooleanField(default=False)
    document_status = serializers.DictField(
        child=serializers.ChoiceField(choices=['received', 'missing', 'partial']),
        required=False,
        help_text='Map of document name → status: {"Birth Certificate": "received", ...}'
    )
    missing_documents = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    status = serializers.ChoiceField(
        choices=['reported', 'absent', 'deferred'],
        default='reported'
    )
