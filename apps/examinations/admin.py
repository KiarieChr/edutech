from django.contrib import admin
from .models import (
    GradingScale, GradingLevel, AssessmentType, Examination,
    StudentMark, TermResult, TermSubjectResult, ReportCardTemplate
)


class GradingLevelInline(admin.TabularInline):
    model = GradingLevel
    extra = 1
    ordering = ['order']


@admin.register(GradingScale)
class GradingScaleAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'curriculum', 'curriculum_level', 'scale_type', 'is_active']
    list_filter = ['curriculum', 'scale_type', 'is_active']
    inlines = [GradingLevelInline]


@admin.register(AssessmentType)
class AssessmentTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'curriculum', 'curriculum_level', 'category', 'weight', 'is_active']
    list_filter = ['curriculum', 'category', 'is_active']


@admin.register(Examination)
class ExaminationAdmin(admin.ModelAdmin):
    list_display = ['name', 'class_session', 'subject', 'assessment_type', 'status', 'exam_date']
    list_filter = ['status', 'assessment_type', 'class_session__academic_year']
    search_fields = ['name', 'subject__name']


@admin.register(StudentMark)
class StudentMarkAdmin(admin.ModelAdmin):
    list_display = ['student', 'examination', 'raw_mark', 'grade', 'points', 'is_absent']
    list_filter = ['examination__status', 'grade', 'is_absent']
    search_fields = ['student__student__first_name', 'student__student__last_name']


@admin.register(TermResult)
class TermResultAdmin(admin.ModelAdmin):
    list_display = ['student', 'class_session', 'average_mark', 'overall_grade', 'class_rank', 'is_published']
    list_filter = ['is_published', 'class_session__academic_year']


@admin.register(TermSubjectResult)
class TermSubjectResultAdmin(admin.ModelAdmin):
    list_display = ['term_result', 'subject', 'weighted_mark', 'grade', 'points']


@admin.register(ReportCardTemplate)
class ReportCardTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'curriculum', 'curriculum_level', 'is_active']
    list_filter = ['curriculum', 'is_active']
