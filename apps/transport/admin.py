from django.contrib import admin
from .models import Route, Stop, FeeStructure, StudentAssignment, FeeCharge

@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ('route_code', 'route_name', 'direction', 'capacity', 'fee_model', 'status')
    search_fields = ('route_code', 'route_name', 'driver_name')
    list_filter = ('status', 'fee_model', 'direction')

@admin.register(Stop)
class StopAdmin(admin.ModelAdmin):
    list_display = ('stop_name', 'route', 'zone', 'stop_order')
    search_fields = ('stop_name', 'route__route_name')
    list_filter = ('zone', 'route')

@admin.register(FeeStructure)
class FeeStructureAdmin(admin.ModelAdmin):
    list_display = ('route', 'fee_type', 'amount', 'billing_cycle', 'academic_year', 'term')
    list_filter = ('academic_year', 'term', 'billing_cycle', 'fee_type')
    search_fields = ('route__route_name',)

@admin.register(StudentAssignment)
class StudentAssignmentAdmin(admin.ModelAdmin):
    list_display = ('student', 'route', 'stop', 'transport_type', 'is_active', 'start_date')
    search_fields = ('student__first_name', 'student__last_name', 'route__route_name')
    list_filter = ('is_active', 'transport_type', 'route')

@admin.register(FeeCharge)
class FeeChargeAdmin(admin.ModelAdmin):
    list_display = ('student', 'fee_label', 'amount_charged', 'academic_year', 'term', 'linked_to_main_fee_ledger')
    search_fields = ('student__first_name', 'student__last_name', 'fee_label')
    list_filter = ('linked_to_main_fee_ledger', 'academic_year', 'term')
