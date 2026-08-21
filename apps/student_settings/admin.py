from django.contrib import admin
from .models import AcademicYear, Term, Curriculum, CurriculumLevel, GradeStructure, Stream, Intake, StudentStatus, PromotionRule

@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_date', 'end_date', 'status', 'is_current')
    search_fields = ('name',)

@admin.register(Term)
class TermAdmin(admin.ModelAdmin):
    list_display = ('name', 'academic_year', 'status', 'is_current')
    list_filter = ('academic_year',)
    search_fields = ('name', 'academic_year__name')

@admin.register(Curriculum)
class CurriculumAdmin(admin.ModelAdmin):
    list_display = ('name', 'status')
    search_fields = ('name',)

@admin.register(CurriculumLevel)
class CurriculumLevelAdmin(admin.ModelAdmin):
    list_display = ('name', 'curriculum', 'order')
    list_filter = ('curriculum',)
    search_fields = ('name', 'curriculum__name')

@admin.register(GradeStructure)
class GradeStructureAdmin(admin.ModelAdmin):
    list_display = ('name', 'curriculum', 'level_order')
    list_filter = ('curriculum',)
    search_fields = ('name', 'curriculum__name')

@admin.register(Stream)
class StreamAdmin(admin.ModelAdmin):
    list_display = ('name', 'grade', 'class_teacher')
    list_filter = ('grade',)
    search_fields = ('name', 'grade__name')

@admin.register(Intake)
class IntakeAdmin(admin.ModelAdmin):
    list_display = ('name', 'academic_year', 'start_date', 'status')
    list_filter = ('status',)
    search_fields = ('name', 'code')

@admin.register(StudentStatus)
class StudentStatusAdmin(admin.ModelAdmin):
    pass

@admin.register(PromotionRule)
class PromotionRuleAdmin(admin.ModelAdmin):
    pass
