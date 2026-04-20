from django.contrib import admin
from .models import Assignment, AssignmentSubmission


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ['title', 'subject', 'class_session', 'assignment_type', 'status', 'due_date', 'created_by']
    list_filter = ['status', 'assignment_type', 'class_session', 'subject']
    search_fields = ['title', 'description']
    raw_id_fields = ['class_session', 'subject', 'created_by']


@admin.register(AssignmentSubmission)
class AssignmentSubmissionAdmin(admin.ModelAdmin):
    list_display = ['assignment', 'student', 'status', 'score', 'submitted_at', 'graded_at']
    list_filter = ['status']
    raw_id_fields = ['assignment', 'student', 'graded_by']
