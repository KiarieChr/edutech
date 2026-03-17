from django.contrib import admin
from .models import FeeStructure, FeeItem

class FeeItemInline(admin.TabularInline):
    model = FeeItem
    extra = 1

@admin.register(FeeStructure)
class FeeStructureAdmin(admin.ModelAdmin):
    list_display = ('grade', 'term', 'academic_year', 'total_amount')
    list_filter = ('academic_year', 'term', 'grade')
    inlines = [FeeItemInline]
