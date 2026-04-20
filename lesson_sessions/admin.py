from django.contrib import admin
from .models import LessonSession, SessionAttendance, TeacherSubstitution, CurriculumCoverage


class SessionAttendanceInline(admin.TabularInline):
    model = SessionAttendance
    fields = ['student', 'status', 'minutes_late', 'marked_at', 'is_locked', 'notes']
    readonly_fields = ['marked_at', 'is_locked']
    extra = 0


class CurriculumCoverageInline(admin.TabularInline):
    model = CurriculumCoverage
    fields = ['curriculum_unit', 'coverage_percent', 'teacher_notes']
    extra = 0


@admin.register(LessonSession)
class LessonSessionAdmin(admin.ModelAdmin):
    list_display = [
        'date', 'class_session', 'subject', 'actual_teacher',
        'actual_start_time', 'actual_end_time', 'status', 'delivery_mode'
    ]
    list_filter  = ['status', 'delivery_mode', 'date', 'class_session']
    search_fields = [
        'actual_teacher__first_name', 'actual_teacher__last_name',
        'subject__name', 'topic_taught'
    ]
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'date'
    inlines = [SessionAttendanceInline, CurriculumCoverageInline]


@admin.register(TeacherSubstitution)
class TeacherSubstitutionAdmin(admin.ModelAdmin):
    list_display = [
        'planned_lesson', 'original_teacher', 'substitute_teacher',
        'reason', 'approved_by', 'requested_at'
    ]
    list_filter  = ['reason']
    search_fields = [
        'original_teacher__first_name', 'substitute_teacher__first_name'
    ]
    readonly_fields = ['requested_at']


@admin.register(SessionAttendance)
class SessionAttendanceAdmin(admin.ModelAdmin):
    list_display = ['lesson_session', 'student', 'status', 'minutes_late', 'is_locked']
    list_filter  = ['status', 'is_locked']
    search_fields = ['student__student__first_name', 'student__student__last_name']


@admin.register(CurriculumCoverage)
class CurriculumCoverageAdmin(admin.ModelAdmin):
    list_display = ['curriculum_unit', 'lesson_session', 'coverage_percent', 'recorded_at']
    list_filter  = ['curriculum_unit__subject']
    readonly_fields = ['recorded_at']
