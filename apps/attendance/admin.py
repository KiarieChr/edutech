from django.contrib import admin
from .models import DailyAttendance


@admin.register(DailyAttendance)
class DailyAttendanceAdmin(admin.ModelAdmin):
    list_display = ['student', 'date', 'status', 'class_session', 'marked_by', 'marked_at']
    list_filter = ['status', 'date', 'class_session']
    search_fields = [
        'student__student__first_name',
        'student__student__last_name',
        'student__admission_number',
    ]
    date_hierarchy = 'date'
    raw_id_fields = ['student', 'class_session', 'marked_by']
