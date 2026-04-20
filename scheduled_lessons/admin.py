from django.contrib import admin
from .models import PlannedLesson


@admin.register(PlannedLesson)
class PlannedLessonAdmin(admin.ModelAdmin):
    list_display  = [
        'date', 'class_session', 'subject', 'expected_teacher',
        'scheduled_start_time', 'scheduled_end_time', 'status'
    ]
    list_filter   = ['status', 'date', 'class_session', 'subject']
    search_fields = ['subject__name', 'expected_teacher__first_name', 'expected_teacher__last_name']
    readonly_fields = ['generated_at', 'generated_by']
    date_hierarchy  = 'date'
    ordering       = ['-date', 'scheduled_start_time']
