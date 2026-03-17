from rest_framework import serializers
from .models import (
    Subject, Room, TimetableSlot, TimetableException, CurriculumUnit,
    TimePeriod, WorkAllocation, TeacherAvailability, TimetableLock, TimetableVersion
)


class SubjectSerializer(serializers.ModelSerializer):
    curriculum_name = serializers.CharField(source='curriculum.name', read_only=True)
    curriculum_level_name = serializers.CharField(source='curriculum_level.name', read_only=True, allow_null=True)
    learning_area_name = serializers.CharField(source='learning_area.name', read_only=True, allow_null=True)
    subject_type_display = serializers.CharField(source='get_subject_type_display', read_only=True)

    class Meta:
        model = Subject
        fields = [
            'id', 'name', 'code', 'curriculum', 'curriculum_name',
            'curriculum_level', 'curriculum_level_name', 
            'learning_area', 'learning_area_name',
            'subject_type', 'subject_type_display', 'weekly_lessons',
            'color_hex', 'is_active', 'created_at',
        ]
        read_only_fields = ['created_at']


class RoomSerializer(serializers.ModelSerializer):
    room_type_display = serializers.CharField(source='get_room_type_display', read_only=True)
    campus_name = serializers.CharField(source='campus.name', read_only=True, default=None)

    class Meta:
        model = Room
        fields = [
            'id', 'name', 'room_type', 'room_type_display',
            'campus', 'campus_name', 'capacity', 'is_active', 'notes',
        ]


class TimetableSlotSerializer(serializers.ModelSerializer):
    day_display     = serializers.CharField(source='get_day_of_week_display', read_only=True)
    subject_name    = serializers.CharField(source='subject.name', read_only=True)
    subject_color   = serializers.CharField(source='subject.color_hex', read_only=True)
    teacher_name    = serializers.SerializerMethodField()
    room_name       = serializers.CharField(source='room.name', read_only=True, default=None)
    class_session_name = serializers.CharField(source='class_session.name', read_only=True)

    class Meta:
        model = TimetableSlot
        fields = [
            'id', 'class_session', 'class_session_name',
            'subject', 'subject_name', 'subject_color',
            'teacher', 'teacher_name',
            'room', 'room_name',
            'day_of_week', 'day_display',
            'start_time', 'end_time', 'duration_minutes',
            'effective_from', 'effective_until', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['duration_minutes', 'created_at', 'updated_at']

    def get_teacher_name(self, obj):
        return f"{obj.teacher.first_name} {obj.teacher.last_name}".strip() or obj.teacher.username


class TimetableExceptionSerializer(serializers.ModelSerializer):
    exception_type_display = serializers.CharField(
        source='get_exception_type_display', read_only=True
    )

    class Meta:
        model = TimetableException
        fields = [
            'id', 'date_from', 'date_to', 'reason',
            'exception_type', 'exception_type_display',
            'affects_all_classes', 'class_sessions', 'created_at',
        ]
        read_only_fields = ['created_at']


class CurriculumUnitSerializer(serializers.ModelSerializer):
    subject_name       = serializers.CharField(source='subject.name', read_only=True)
    class_session_name = serializers.CharField(source='class_session.name', read_only=True)

    class Meta:
        model = CurriculumUnit
        fields = [
            'id', 'subject', 'subject_name',
            'class_session', 'class_session_name',
            'title', 'description', 'planned_lessons',
            'sequence_order', 'is_compulsory', 'created_at',
        ]
        read_only_fields = ['created_at']


# =============================================================================
# NEW SERIALIZERS FOR ENHANCED TIMETABLING
# =============================================================================

class TimePeriodSerializer(serializers.ModelSerializer):
    """Serializer for school-wide period definitions."""
    period_type_display = serializers.CharField(source='get_period_type_display', read_only=True)
    duration_display = serializers.SerializerMethodField()

    class Meta:
        model = TimePeriod
        fields = [
            'id', 'name', 'short_name', 'order',
            'start_time', 'end_time',
            'period_type', 'period_type_display',
            'is_schedulable', 'days_applicable',
            'is_active', 'duration_display',
        ]
        read_only_fields = ['duration_display']

    def get_duration_display(self, obj):
        duration = (
            obj.end_time.hour * 60 + obj.end_time.minute
        ) - (
            obj.start_time.hour * 60 + obj.start_time.minute
        )
        return f"{duration} min"


class WorkAllocationSerializer(serializers.ModelSerializer):
    """Serializer for teacher-subject-class work allocations."""
    teacher_name = serializers.SerializerMethodField()
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    subject_code = serializers.CharField(source='subject.code', read_only=True)
    class_session_name = serializers.CharField(source='class_session.name', read_only=True)
    room_type_display = serializers.SerializerMethodField()
    scheduled_lessons = serializers.IntegerField(read_only=True)
    remaining_lessons = serializers.IntegerField(read_only=True)
    allocation_percentage = serializers.FloatField(read_only=True)
    is_fully_allocated = serializers.BooleanField(read_only=True)

    class Meta:
        model = WorkAllocation
        fields = [
            'id', 'teacher', 'teacher_name',
            'subject', 'subject_name', 'subject_code',
            'class_session', 'class_session_name',
            'lessons_per_week', 'scheduled_lessons', 'remaining_lessons',
            'allocation_percentage', 'is_fully_allocated',
            'required_room_type', 'room_type_display',
            'notes', 'is_active', 'created_at',
        ]
        read_only_fields = [
            'scheduled_lessons', 'remaining_lessons', 
            'allocation_percentage', 'is_fully_allocated', 'created_at'
        ]

    def get_teacher_name(self, obj):
        return obj.teacher.get_full_name() or obj.teacher.username

    def get_room_type_display(self, obj):
        if obj.required_room_type:
            return obj.get_required_room_type_display()
        return None


class WorkAllocationCreateSerializer(serializers.ModelSerializer):
    """Simplified serializer for creating work allocations."""
    class Meta:
        model = WorkAllocation
        fields = [
            'teacher', 'subject', 'class_session',
            'lessons_per_week', 'required_room_type', 'notes',
        ]

    def validate(self, data):
        # Check for duplicate allocation
        existing = WorkAllocation.objects.filter(
            teacher=data['teacher'],
            subject=data['subject'],
            class_session=data['class_session'],
            is_active=True,
        ).exists()
        if existing:
            raise serializers.ValidationError(
                "This teacher is already allocated to this subject for this class."
            )
        return data


class TeacherAvailabilitySerializer(serializers.ModelSerializer):
    """Serializer for teacher availability records."""
    teacher_name = serializers.SerializerMethodField()
    availability_type_display = serializers.CharField(
        source='get_availability_type_display', read_only=True
    )
    recurrence_display = serializers.CharField(
        source='get_recurrence_display', read_only=True
    )

    class Meta:
        model = TeacherAvailability
        fields = [
            'id', 'teacher', 'teacher_name',
            'availability_type', 'availability_type_display',
            'day_of_week', 'specific_date',
            'start_time', 'end_time',
            'recurrence', 'recurrence_display',
            'reason', 'is_active', 'created_at',
        ]
        read_only_fields = ['created_at']

    def get_teacher_name(self, obj):
        return obj.teacher.get_full_name() or obj.teacher.username

    def validate(self, data):
        # Validate time range
        if data.get('start_time') and data.get('end_time'):
            if data['start_time'] >= data['end_time']:
                raise serializers.ValidationError({
                    'end_time': 'End time must be after start time.'
                })

        # Validate day or date based on recurrence
        recurrence = data.get('recurrence', 'weekly')
        if recurrence == 'weekly' and data.get('day_of_week') is None:
            raise serializers.ValidationError({
                'day_of_week': 'Day of week is required for weekly recurrence.'
            })
        if recurrence == 'once' and not data.get('specific_date'):
            raise serializers.ValidationError({
                'specific_date': 'Specific date is required for one-time unavailability.'
            })

        return data


class TimetableLockSerializer(serializers.ModelSerializer):
    """Serializer for timetable lock status."""
    class_session_name = serializers.CharField(source='class_session.name', read_only=True)
    lock_level_display = serializers.CharField(source='get_lock_level_display', read_only=True)
    locked_by_name = serializers.SerializerMethodField()
    is_editable = serializers.BooleanField(read_only=True)

    class Meta:
        model = TimetableLock
        fields = [
            'id', 'class_session', 'class_session_name',
            'lock_level', 'lock_level_display', 'is_editable',
            'locked_by', 'locked_by_name', 'locked_at',
            'notes', 'created_at', 'updated_at',
        ]
        read_only_fields = ['locked_by', 'locked_at', 'is_editable', 'created_at', 'updated_at']

    def get_locked_by_name(self, obj):
        if obj.locked_by:
            return obj.locked_by.get_full_name() or obj.locked_by.username
        return None


class TimetableVersionSerializer(serializers.ModelSerializer):
    """Serializer for timetable version snapshots."""
    class_session_name = serializers.CharField(source='class_session.name', read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = TimetableVersion
        fields = [
            'id', 'class_session', 'class_session_name',
            'version_number', 'label', 'description',
            'snapshot_data', 'slots_count',
            'created_by', 'created_by_name', 'created_at',
        ]
        read_only_fields = [
            'version_number', 'snapshot_data', 'slots_count',
            'created_by', 'created_at'
        ]

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return None


class TimetableVersionListSerializer(serializers.ModelSerializer):
    """Lighter serializer for listing versions (without full snapshot data)."""
    class_session_name = serializers.CharField(source='class_session.name', read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = TimetableVersion
        fields = [
            'id', 'class_session', 'class_session_name',
            'version_number', 'label', 'description',
            'slots_count', 'created_by_name', 'created_at',
        ]

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return None


# =============================================================================
# ENHANCED TIMETABLE SLOT SERIALIZERS
# =============================================================================

class TimetableSlotDetailSerializer(TimetableSlotSerializer):
    """Extended slot serializer with conflict checking."""
    conflicts = serializers.SerializerMethodField()
    warnings = serializers.SerializerMethodField()

    class Meta(TimetableSlotSerializer.Meta):
        fields = TimetableSlotSerializer.Meta.fields + ['conflicts', 'warnings']

    def get_conflicts(self, obj):
        # Returns empty list for existing slots (they wouldn't exist if they had conflicts)
        return []

    def get_warnings(self, obj):
        # Could add soft constraint warnings here
        return []


class TimetableSlotCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating slots with validation."""
    class Meta:
        model = TimetableSlot
        fields = [
            'class_session', 'subject', 'teacher', 'room',
            'day_of_week', 'start_time', 'end_time',
            'effective_from', 'effective_until',
        ]

    def validate(self, data):
        from timetable.services.conflict_engine import ConflictEngine
        
        engine = ConflictEngine()
        result = engine.check_slot_creation(
            class_session=data['class_session'],
            subject=data['subject'],
            teacher=data['teacher'],
            day_of_week=data['day_of_week'],
            start_time=data['start_time'],
            end_time=data['end_time'],
            room=data.get('room'),
            effective_from=data.get('effective_from'),
        )

        if not result.is_valid:
            errors = {
                'non_field_errors': [c.message for c in result.conflicts]
            }
            raise serializers.ValidationError(errors)

        # Store warnings for response
        self._warnings = result.warnings
        return data

    def create(self, validated_data):
        instance = super().create(validated_data)
        # Attach warnings to instance for response
        instance._validation_warnings = getattr(self, '_warnings', [])
        return instance


# =============================================================================
# BULK/NESTED SERIALIZERS
# =============================================================================

class ClassTimetableSerializer(serializers.Serializer):
    """Serializer for full class timetable view."""
    class_session_id = serializers.IntegerField()
    class_session_name = serializers.CharField()
    days = serializers.DictField(child=serializers.ListField())
    coverage = serializers.DictField()


class TeacherTimetableSerializer(serializers.Serializer):
    """Serializer for teacher's full timetable view."""
    teacher_id = serializers.IntegerField()
    teacher_name = serializers.CharField()
    days = serializers.DictField(child=serializers.ListField())
    workload_summary = serializers.DictField()


class RoomTimetableSerializer(serializers.Serializer):
    """Serializer for room's full timetable view."""
    room_id = serializers.IntegerField()
    room_name = serializers.CharField()
    days = serializers.DictField(child=serializers.ListField())
    utilization = serializers.DictField()


class AvailableSlotsSerializer(serializers.Serializer):
    """Serializer for available slots response."""
    day_of_week = serializers.IntegerField()
    day_name = serializers.CharField()
    period_id = serializers.IntegerField()
    period_name = serializers.CharField()
    start_time = serializers.CharField()
    end_time = serializers.CharField()
    is_available = serializers.BooleanField()
    conflicts = serializers.ListField()
    warnings = serializers.ListField()


class SchedulingResultSerializer(serializers.Serializer):
    """Serializer for scheduling operation results."""
    success = serializers.BooleanField()
    placed_count = serializers.IntegerField()
    total_allocations = serializers.IntegerField()
    placement_percentage = serializers.FloatField()
    created_slots = serializers.ListField(child=serializers.IntegerField())
    unplaced = serializers.ListField()
    warnings = serializers.ListField(child=serializers.CharField())
    execution_time_ms = serializers.FloatField()

