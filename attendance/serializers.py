from rest_framework import serializers
from .models import DailyAttendance


class DailyAttendanceSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    admission_number = serializers.SerializerMethodField()
    marked_by_name = serializers.SerializerMethodField()

    class Meta:
        model = DailyAttendance
        fields = [
            'id', 'student', 'class_session', 'date', 'status',
            'arrival_time', 'notes', 'marked_by', 'marked_at',
            'student_name', 'admission_number', 'marked_by_name',
        ]
        read_only_fields = ['marked_by', 'marked_at']

    def get_student_name(self, obj):
        user = obj.student.student
        return f"{user.first_name} {user.last_name}"

    def get_admission_number(self, obj):
        return obj.student.admission_number

    def get_marked_by_name(self, obj):
        if obj.marked_by:
            return f"{obj.marked_by.first_name} {obj.marked_by.last_name}"
        return None


class BulkAttendanceSerializer(serializers.Serializer):
    """Accepts a list of attendance records for bulk marking."""
    class_session = serializers.IntegerField()
    date = serializers.DateField()
    records = serializers.ListField(
        child=serializers.DictField(),
        help_text="List of {student_id, status, arrival_time?, notes?}",
    )

    def validate_records(self, value):
        for record in value:
            if 'student_id' not in record or 'status' not in record:
                raise serializers.ValidationError(
                    "Each record must have 'student_id' and 'status'."
                )
            if record['status'] not in dict(DailyAttendance.STATUS_CHOICES):
                raise serializers.ValidationError(
                    f"Invalid status: {record['status']}"
                )
        return value


class AttendanceSummarySerializer(serializers.Serializer):
    """Read-only summary for a student over a date range."""
    student_id = serializers.IntegerField()
    student_name = serializers.CharField()
    admission_number = serializers.CharField()
    total_days = serializers.IntegerField()
    present = serializers.IntegerField()
    absent = serializers.IntegerField()
    late = serializers.IntegerField()
    excused = serializers.IntegerField()
    half_day = serializers.IntegerField()
    attendance_rate = serializers.FloatField()
