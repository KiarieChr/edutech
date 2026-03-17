from rest_framework import serializers
from .models import PlannedLesson


class PlannedLessonSerializer(serializers.ModelSerializer):
    status_display       = serializers.CharField(source='get_status_display', read_only=True)
    subject_name         = serializers.CharField(source='subject.name', read_only=True)
    subject_color        = serializers.CharField(source='subject.color_hex', read_only=True)
    class_session_name   = serializers.CharField(source='class_session.name', read_only=True)
    expected_teacher_name = serializers.SerializerMethodField()
    room_name            = serializers.CharField(source='room.name', read_only=True, default=None)
    scheduled_duration_minutes = serializers.IntegerField(read_only=True)
    has_lesson_session   = serializers.SerializerMethodField()

    class Meta:
        model = PlannedLesson
        fields = [
            'id', 'timetable_slot', 'date', 'status', 'status_display',
            'class_session', 'class_session_name',
            'subject', 'subject_name', 'subject_color',
            'room', 'room_name',
            'expected_teacher', 'expected_teacher_name',
            'scheduled_start_time', 'scheduled_end_time', 'scheduled_duration_minutes',
            'has_lesson_session', 'generated_at', 'generated_by',
        ]
        read_only_fields = [
            'generated_at', 'generated_by', 'scheduled_duration_minutes',
            'has_lesson_session',
        ]

    def get_expected_teacher_name(self, obj):
        t = obj.expected_teacher
        return f"{t.first_name} {t.last_name}".strip() or t.username

    def get_has_lesson_session(self, obj):
        return hasattr(obj, 'lesson_session') and obj.lesson_session is not None
