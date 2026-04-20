from django.contrib import admin
from .models import Subject, Room, TimetableSlot, TimetableException, CurriculumUnit


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display  = ['code', 'name', 'curriculum', 'is_active']
    list_filter   = ['curriculum', 'is_active']
    search_fields = ['name', 'code']


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display  = ['name', 'room_type', 'campus', 'capacity', 'is_active']
    list_filter   = ['room_type', 'campus', 'is_active']
    search_fields = ['name']


@admin.register(TimetableSlot)
class TimetableSlotAdmin(admin.ModelAdmin):
    list_display  = [
        'class_session', 'subject', 'teacher', 'room',
        'day_of_week', 'start_time', 'end_time', 'effective_from', 'is_active'
    ]
    list_filter   = ['day_of_week', 'is_active', 'class_session']
    search_fields = ['subject__name', 'teacher__first_name', 'teacher__last_name']
    raw_id_fields = ['teacher', 'class_session']


@admin.register(TimetableException)
class TimetableExceptionAdmin(admin.ModelAdmin):
    list_display  = ['exception_type', 'date_from', 'date_to', 'reason', 'affects_all_classes']
    list_filter   = ['exception_type', 'affects_all_classes']
    filter_horizontal = ['class_sessions']


@admin.register(CurriculumUnit)
class CurriculumUnitAdmin(admin.ModelAdmin):
    list_display  = ['sequence_order', 'subject', 'class_session', 'title', 'planned_lessons', 'is_compulsory']
    list_filter   = ['subject', 'class_session', 'is_compulsory']
    search_fields = ['title']
    ordering      = ['class_session', 'subject', 'sequence_order']
