from django.contrib import admin
from .models import FeeStructure, FeeItem, VoteHead, GradeBand, FeeTemplate, TemplateLineItem, StudentFeeProfile

class FeeItemInline(admin.TabularInline):
    model = FeeItem
    extra = 1

@admin.register(FeeStructure)
class FeeStructureAdmin(admin.ModelAdmin):
    list_display = ('grade', 'term', 'academic_year', 'total_amount')
    list_filter = ('academic_year', 'term', 'grade')
    inlines = [FeeItemInline]


# ── Template Architecture ──────────────────────────────────

@admin.register(VoteHead)
class VoteHeadAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'default_account', 'frequency', 'is_optional', 'is_active')
    list_filter = ('is_active', 'is_optional', 'frequency')
    search_fields = ('name', 'code')

@admin.register(GradeBand)
class GradeBandAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active')
    filter_horizontal = ('grades',)

class TemplateLineItemInline(admin.TabularInline):
    model = TemplateLineItem
    extra = 1

@admin.register(FeeTemplate)
class FeeTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'grade_band', 'term', 'academic_year', 'status', 'total_amount')
    list_filter = ('status', 'academic_year', 'term')
    filter_horizontal = ('grades',)
    inlines = [TemplateLineItemInline]

@admin.register(StudentFeeProfile)
class StudentFeeProfileAdmin(admin.ModelAdmin):
    list_display = ('student', 'is_boarder', 'uses_transport')
    list_filter = ('is_boarder', 'uses_transport')
    filter_horizontal = ('custom_items',)
