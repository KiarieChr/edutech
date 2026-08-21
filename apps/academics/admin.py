from django.contrib import admin
from .models import ClassSession, StudentSessionEnrollment

@admin.register(ClassSession)
class ClassSessionAdmin(admin.ModelAdmin):
    list_display = ('name', 'grade', 'term', 'academic_year', 'status', 'start_date', 'end_date')
    list_filter = ('status', 'academic_year', 'term', 'grade__curriculum', 'grade')
    search_fields = ('name', 'grade__name')
    autocomplete_fields = ['grade', 'term', 'academic_year']

@admin.register(StudentSessionEnrollment)
class StudentSessionEnrollmentAdmin(admin.ModelAdmin):
    list_display = ('student', 'session', 'status', 'progression_status', 'is_active')
    list_filter = ('status', 'progression_status', 'is_active', 'session__academic_year')
    search_fields = ('student__first_name', 'student__last_name', 'student__admission_number', 'session__name')
    autocomplete_fields = ['student', 'session', 'intake', 'stream']
