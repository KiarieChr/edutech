from rest_framework import serializers
from .models import LessonSession, SessionAttendance, TeacherSubstitution, CurriculumCoverage


class LessonSessionSerializer(serializers.ModelSerializer):
    status_display       = serializers.CharField(source='get_status_display', read_only=True)
    delivery_mode_display = serializers.CharField(source='get_delivery_mode_display', read_only=True)
    actual_teacher_name  = serializers.SerializerMethodField()
    subject_name         = serializers.CharField(source='subject.name', read_only=True)
    subject_color        = serializers.CharField(source='subject.color_hex', read_only=True)
    class_session_name   = serializers.CharField(source='class_session.name', read_only=True)
    room_name            = serializers.CharField(source='room.name', read_only=True, default=None)
    actual_duration_minutes = serializers.IntegerField(read_only=True)
    start_delay_minutes  = serializers.IntegerField(read_only=True)
    attendance_summary   = serializers.SerializerMethodField()

    class Meta:
        model = LessonSession
        fields = [
            'id', 'planned_lesson',
            'status', 'status_display',
            'delivery_mode', 'delivery_mode_display',
            'actual_teacher', 'actual_teacher_name',
            'actual_start_time', 'actual_end_time',
            'actual_duration_minutes', 'start_delay_minutes',
            'class_session', 'class_session_name',
            'subject', 'subject_name', 'subject_color',
            'room', 'room_name',
            'date', 'topic_taught', 'lesson_notes', 'homework_given',
            'curriculum_unit',
            'started_by', 'completed_by',
            'cancellation_reason',
            'attendance_summary',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'actual_duration_minutes', 'start_delay_minutes',
            'attendance_summary', 'created_at', 'updated_at',
        ]

    def get_actual_teacher_name(self, obj):
        t = obj.actual_teacher
        return f"{t.first_name} {t.last_name}".strip() or t.username

    def get_attendance_summary(self, obj):
        qs = obj.attendances.all()
        if not qs.exists():
            return None
        total   = qs.count()
        present = qs.filter(status='present').count()
        absent  = qs.filter(status='absent').count()
        late    = qs.filter(status='late').count()
        excused = qs.filter(status='excused').count()
        return {
            'total': total,
            'present': present,
            'absent': absent,
            'late': late,
            'excused': excused,
            'attendance_rate': round(((present + late) / total) * 100, 1) if total else 0,
        }


class StartSessionSerializer(serializers.Serializer):
    """Payload for POST /api/lesson-sessions/start/"""
    planned_lesson_id = serializers.IntegerField(required=False, allow_null=True)
    # Required when planned_lesson_id is not provided (ad-hoc session)
    class_session_id  = serializers.IntegerField(required=False)
    subject_id        = serializers.IntegerField(required=False)
    room_id           = serializers.IntegerField(required=False, allow_null=True)
    delivery_mode     = serializers.ChoiceField(
        choices=['physical', 'online', 'hybrid'], default='physical'
    )

    def validate(self, data):
        if not data.get('planned_lesson_id'):
            if not data.get('class_session_id') or not data.get('subject_id'):
                raise serializers.ValidationError(
                    "Either planned_lesson_id or (class_session_id + subject_id) is required."
                )
        return data


class CompleteSessionSerializer(serializers.Serializer):
    """Payload for POST /api/lesson-sessions/{id}/complete/"""
    topic_taught      = serializers.CharField(required=False, default='', allow_blank=True)
    lesson_notes      = serializers.CharField(required=False, default='', allow_blank=True)
    homework_given    = serializers.CharField(required=False, default='', allow_blank=True)
    curriculum_unit_id = serializers.IntegerField(required=False, allow_null=True)


class SessionAttendanceSerializer(serializers.ModelSerializer):
    student_name  = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = SessionAttendance
        fields = [
            'id', 'lesson_session', 'student', 'student_name',
            'status', 'status_display',
            'marked_at', 'minutes_late', 'is_locked', 'notes',
        ]
        read_only_fields = ['marked_at', 'is_locked', 'lesson_session']

    def get_student_name(self, obj):
        s = obj.student
        try:
            return f"{s.student.first_name} {s.student.last_name}".strip()
        except AttributeError:
            return str(s)


class TeacherSubstitutionSerializer(serializers.ModelSerializer):
    original_teacher_name   = serializers.SerializerMethodField()
    substitute_teacher_name = serializers.SerializerMethodField()
    reason_display          = serializers.CharField(source='get_reason_display', read_only=True)

    class Meta:
        model = TeacherSubstitution
        fields = [
            'id', 'planned_lesson',
            'original_teacher', 'original_teacher_name',
            'substitute_teacher', 'substitute_teacher_name',
            'approved_by', 'reason', 'reason_display',
            'reason_notes', 'requested_at', 'approved_at',
        ]
        read_only_fields = ['requested_at']

    def get_original_teacher_name(self, obj):
        t = obj.original_teacher
        return f"{t.first_name} {t.last_name}".strip() or t.username

    def get_substitute_teacher_name(self, obj):
        t = obj.substitute_teacher
        return f"{t.first_name} {t.last_name}".strip() or t.username


class CurriculumCoverageSerializer(serializers.ModelSerializer):
    unit_title          = serializers.CharField(source='curriculum_unit.title', read_only=True)
    subject_name        = serializers.CharField(
        source='curriculum_unit.subject.name', read_only=True
    )
    class_session_name  = serializers.CharField(
        source='curriculum_unit.class_session.name', read_only=True
    )

    class Meta:
        model = CurriculumCoverage
        fields = [
            'id', 'curriculum_unit', 'unit_title', 'subject_name', 'class_session_name',
            'lesson_session', 'coverage_percent', 'teacher_notes', 'recorded_at',
        ]
        read_only_fields = ['recorded_at']
