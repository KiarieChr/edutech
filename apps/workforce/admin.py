"""
HR & Payroll Django Admin Configuration
Part 1: Core Employee & Address Management
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .core_models import (
    Employee, Country, County, SubCounty, Village,
    EmployeeAddress, EmergencyContact
)
from .models import (
    # Shifts & Timetables
    ShiftType, ShiftSchedule, EmployeeShiftAssignment,
    ShiftSwapRequest, TeachingTimetable, TimetableSubstitution,
    ShiftAttendance, TeachingLoadSummary,
    # Performance
    PerformanceMetric, PerformanceIndicatorTemplate,
    TemplateMetricMapping, AppraisalCycle, EmployeeAppraisal,
    AppraisalMetricScore, AcademicProductivity, Publication,
    ResearchGrant, Peer360Feedback, StudentFeedback, DevelopmentPlan,
    # Payroll
    PayrollPeriod, PayProfile, EarningType, DeductionType,
    PayProfileComponent, EmployeePayProfile, EmployeeEarning,
    EmployeeDeduction, PayrollCalculation, PayrollCalculationDetail,
    Payslip, PayrollAuditLog
)


# ============================================================================
# ADMIN CONFIGURATION BASE CLASSES
# ============================================================================

class BaseModelAdmin(admin.ModelAdmin):
    """Base admin with common configurations"""
    save_on_top = True
    list_per_page = 50
    
    def get_readonly_fields(self, request, obj=None):
        """Make created_at, updated_at readonly"""
        readonly = list(super().get_readonly_fields(request, obj))
        if hasattr(self.model, 'created_at'):
            readonly.extend(['created_at', 'updated_at'])
        return readonly


# ============================================================================
# CORE EMPLOYEE ADMIN
# ============================================================================

class EmployeeAddressInline(admin.TabularInline):
    """Inline for employee addresses"""
    model = EmployeeAddress
    extra = 0
    fields = [
        'address_type', 'country', 'county', 'city', 
        'is_primary', 'is_verified', 'effective_from', 'effective_to'
    ]
    readonly_fields = ['is_verified', 'verified_date', 'verified_by']


class EmergencyContactInline(admin.TabularInline):
    """Inline for emergency contacts"""
    model = EmergencyContact
    extra = 0
    fields = ['contact_name', 'relationship', 'phone_primary', 'is_primary']


@admin.register(Employee)
class EmployeeAdmin(BaseModelAdmin):
    """Employee admin with comprehensive display"""
    
    list_display = [
        'employee_no', 'get_full_name_display', 'employee_category',
        'employment_status', 'department', 'hire_date', 'status_badge'
    ]
    list_filter = [
        'employment_status', 'employee_category', 'payroll_type',
        'gender', 'department', 'hire_date'
    ]
    search_fields = [
        'employee_no', 'first_name', 'last_name', 'middle_name',
        'national_id', 'personal_email', 'official_email'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'employee_no', 
                ('first_name', 'middle_name', 'last_name'),
                ('date_of_birth', 'gender'),
                ('national_id', 'passport_number')
            )
        }),
        ('Contact Information', {
            'fields': (
                ('personal_email', 'official_email'),
                ('phone_primary', 'phone_secondary')
            )
        }),
        ('Employment Details', {
            'fields': (
                ('employee_category', 'payroll_type'),
                ('employment_status', 'job_grade'),
                'department'
            )
        }),
        ('Important Dates', {
            'fields': (
                ('hire_date', 'confirmation_date'),
                'termination_date'
            )
        }),
        ('Audit Information', {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at', 'created_by', 'updated_by')
        })
    )
    
    inlines = [EmployeeAddressInline, EmergencyContactInline]
    
    readonly_fields = ['created_at', 'updated_at']
    
    actions = ['activate_employees', 'suspend_employees']
    
    def get_full_name_display(self, obj):
        """Display full name"""
        return obj.get_full_name()
    get_full_name_display.short_description = 'Full Name'
    
    def status_badge(self, obj):
        """Display colored status badge"""
        colors = {
            'active': 'green',
            'probation': 'orange',
            'suspended': 'red',
            'terminated': 'gray',
            'resigned': 'gray',
            'retired': 'blue'
        }
        color = colors.get(obj.employment_status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_employment_status_display()
        )
    status_badge.short_description = 'Status'
    
    def activate_employees(self, request, queryset):
        """Bulk activate employees"""
        count = queryset.update(employment_status='active')
        self.message_user(request, f'{count} employees activated.')
    activate_employees.short_description = 'Activate selected employees'
    
    def suspend_employees(self, request, queryset):
        """Bulk suspend employees"""
        count = queryset.update(employment_status='suspended')
        self.message_user(request, f'{count} employees suspended.')
    suspend_employees.short_description = 'Suspend selected employees'


# ============================================================================
# ADDRESS & LOCATION ADMIN
# ============================================================================

@admin.register(Country)
class CountryAdmin(BaseModelAdmin):
    """Country admin"""
    list_display = ['code', 'name', 'phone_code', 'is_active']
    list_filter = ['is_active']
    search_fields = ['code', 'name']
    ordering = ['name']


class SubCountyInline(admin.TabularInline):
    """Inline for sub-counties"""
    model = SubCounty
    extra = 0
    fields = ['code', 'name']


@admin.register(County)
class CountyAdmin(BaseModelAdmin):
    """County admin with sub-county inline"""
    list_display = ['code', 'name', 'country', 'is_active']
    list_filter = ['country', 'is_active']
    search_fields = ['code', 'name']
    ordering = ['country', 'name']
    inlines = [SubCountyInline]


class VillageInline(admin.TabularInline):
    """Inline for villages"""
    model = Village
    extra = 0
    fields = ['name']


@admin.register(SubCounty)
class SubCountyAdmin(BaseModelAdmin):
    """Sub-county admin with village inline"""
    list_display = ['code', 'name', 'county', 'get_country']
    list_filter = ['county__country']
    search_fields = ['code', 'name', 'county__name']
    ordering = ['county', 'name']
    inlines = [VillageInline]
    
    def get_country(self, obj):
        return obj.county.country.name
    get_country.short_description = 'Country'
    get_country.admin_order_field = 'county__country__name'


@admin.register(Village)
class VillageAdmin(BaseModelAdmin):
    """Village admin"""
    list_display = ['name', 'subcounty', 'get_county', 'get_country']
    list_filter = ['subcounty__county__country']
    search_fields = ['name', 'subcounty__name']
    ordering = ['subcounty', 'name']
    
    def get_county(self, obj):
        return obj.subcounty.county.name
    get_county.short_description = 'County'
    
    def get_country(self, obj):
        return obj.subcounty.county.country.name
    get_country.short_description = 'Country'


@admin.register(EmployeeAddress)
class EmployeeAddressAdmin(BaseModelAdmin):
    """Employee address admin"""
    list_display = [
        'employee', 'address_type', 'city', 'county', 
        'is_primary', 'is_verified', 'effective_from', 'effective_to'
    ]
    list_filter = [
        'address_type', 'is_primary', 'is_verified', 
        'country', 'effective_from'
    ]
    search_fields = [
        'employee__employee_no', 'employee__first_name', 
        'employee__last_name', 'city', 'street_address'
    ]
    
    fieldsets = (
        ('Employee & Type', {
            'fields': ('employee', 'address_type')
        }),
        ('Location Hierarchy', {
            'fields': (
                'country', 'county', 'subcounty', 'village'
            )
        }),
        ('Address Details', {
            'fields': (
                'street_address', 'building_name', 
                ('city', 'postal_code'),
                'landmark'
            )
        }),
        ('GPS Coordinates', {
            'classes': ('collapse',),
            'fields': (('latitude', 'longitude'),)
        }),
        ('Status & Verification', {
            'fields': (
                'is_primary', 'is_verified',
                ('verified_date', 'verified_by'),
                ('effective_from', 'effective_to')
            )
        })
    )
    
    readonly_fields = ['verified_date', 'verified_by']
    
    raw_id_fields = ['employee']
    autocomplete_fields = ['country', 'county', 'subcounty', 'village']
    
    actions = ['verify_addresses', 'mark_as_primary']
    
    def verify_addresses(self, request, queryset):
        """Bulk verify addresses"""
        from django.utils import timezone
        count = queryset.update(
            is_verified=True,
            verified_by=request.user,
            verified_date=timezone.now().date()
        )
        self.message_user(request, f'{count} addresses verified.')
    verify_addresses.short_description = 'Verify selected addresses'
    
    def mark_as_primary(self, request, queryset):
        """Mark first address as primary"""
        if queryset.count() == 1:
            address = queryset.first()
            EmployeeAddress.objects.filter(
                employee=address.employee,
                address_type=address.address_type
            ).update(is_primary=False)
            address.is_primary = True
            address.save()
            self.message_user(request, 'Address marked as primary.')
        else:
            self.message_user(request, 'Select only one address.', level='error')
    mark_as_primary.short_description = 'Mark as primary address'


@admin.register(EmergencyContact)
class EmergencyContactAdmin(BaseModelAdmin):
    """Emergency contact admin"""
    list_display = [
        'employee', 'contact_name', 'relationship', 
        'phone_primary', 'is_primary', 'can_make_medical_decisions'
    ]
    list_filter = ['is_primary', 'can_make_medical_decisions', 'relationship']
    search_fields = [
        'employee__employee_no', 'employee__first_name',
        'contact_name', 'phone_primary', 'email'
    ]
    
    fieldsets = (
        ('Employee', {
            'fields': ('employee',)
        }),
        ('Contact Information', {
            'fields': (
                'contact_name', 'relationship',
                ('phone_primary', 'phone_secondary'),
                'email'
            )
        }),
        ('Address', {
            'fields': ('address',)
        }),
        ('Settings', {
            'fields': (
                'is_primary', 'can_make_medical_decisions',
                'notes'
            )
        })
    )
    
    raw_id_fields = ['employee', 'address']

@admin.register(ShiftType)
class ShiftTypeAdmin(admin.ModelAdmin):
    """Shift type admin"""
    list_display = [
        'code', 'name', 'shift_category', 'start_time',
        'end_time', 'duration_hours', 'shift_multiplier', 'is_active'
    ]
    list_filter = ['shift_category', 'is_overnight', 'is_active']
    search_fields = ['code', 'name']


@admin.register(ShiftSchedule)
class ShiftScheduleAdmin(admin.ModelAdmin):
    """Shift schedule admin"""
    list_display = [
        'name', 'department', 'shift_pattern',
        'rotation_cycle_days', 'effective_from', 'is_active'
    ]
    list_filter = ['shift_pattern', 'department', 'is_active']
    search_fields = ['name']


@admin.register(EmployeeShiftAssignment)
class EmployeeShiftAssignmentAdmin(admin.ModelAdmin):
    """Employee shift assignment admin"""
    list_display = [
        'employee', 'shift_type', 'assignment_date',
        'start_time', 'end_time', 'campus', 'status'
    ]
    list_filter = ['status', 'shift_type', 'campus', 'assignment_date']
    search_fields = ['employee__employee_no', 'employee__first_name']
    date_hierarchy = 'assignment_date'
    raw_id_fields = ['employee']


@admin.register(ShiftSwapRequest)
class ShiftSwapRequestAdmin(admin.ModelAdmin):
    """Shift swap request admin"""
    list_display = [
        'requesting_employee', 'target_employee',
        'request_date', 'status', 'approved_by'
    ]
    list_filter = ['status', 'request_date']
    search_fields = [
        'requesting_employee__employee_no',
        'target_employee__employee_no'
    ]
    raw_id_fields = ['requesting_employee', 'target_employee']


@admin.register(TeachingTimetable)
class TeachingTimetableAdmin(admin.ModelAdmin):
    """Teaching timetable admin"""
    list_display = [
        'employee', 'day_of_week', 'start_time', 'end_time',
        'duration_hours', 'session_type', 'campus', 'status'
    ]
    list_filter = [
        'day_of_week', 'session_type', 'campus',
        'status', 'is_recurring'
    ]
    search_fields = ['employee__employee_no', 'employee__first_name']
    raw_id_fields = ['employee']


@admin.register(TimetableSubstitution)
class TimetableSubstitutionAdmin(admin.ModelAdmin):
    """Timetable substitution admin"""
    list_display = [
        'original_lecturer', 'substitute_lecturer',
        'substitution_date', 'substitution_type',
        'compensation_type', 'compensation_amount'
    ]
    list_filter = [
        'substitution_type', 'compensation_type', 'substitution_date'
    ]
    search_fields = [
        'original_lecturer__employee_no',
        'substitute_lecturer__employee_no'
    ]
    raw_id_fields = ['original_lecturer', 'substitute_lecturer']


@admin.register(TeachingLoadSummary)
class TeachingLoadSummaryAdmin(admin.ModelAdmin):
    """Teaching load summary admin"""
    list_display = [
        'employee', 'academic_term_id', 'total_weekly_hours',
        'lecture_hours', 'lab_hours', 'overload_hours',
        'courses_count'
    ]
    list_filter = ['academic_term_id']
    search_fields = ['employee__employee_no', 'employee__first_name']
    raw_id_fields = ['employee']


# ============================================================================
# PERFORMANCE & APPRAISAL ADMIN
# ============================================================================

@admin.register(PerformanceMetric)
class PerformanceMetricAdmin(admin.ModelAdmin):
    """Performance metric admin"""
    list_display = [
        'code', 'name', 'metric_category', 'measurement_type',
        'weight_percentage', 'applies_to_category', 'is_active'
    ]
    list_filter = [
        'metric_category', 'measurement_type',
        'applies_to_category', 'is_active'
    ]
    search_fields = ['code', 'name']


class TemplateMetricMappingInline(admin.TabularInline):
    """Inline for template metrics"""
    model = TemplateMetricMapping
    extra = 0
    fields = [
        'metric', 'target_value', 'weight_percentage',
        'is_mandatory'
    ]


@admin.register(PerformanceIndicatorTemplate)
class PerformanceIndicatorTemplateAdmin(admin.ModelAdmin):
    """Performance indicator template admin"""
    list_display = [
        'name', 'job_title', 'department',
        'effective_from', 'is_active'
    ]
    list_filter = ['job_title', 'department', 'is_active']
    search_fields = ['name']
    inlines = [TemplateMetricMappingInline]


@admin.register(AppraisalCycle)
class AppraisalCycleAdmin(admin.ModelAdmin):
    """Appraisal cycle admin"""
    list_display = [
        'name', 'cycle_type', 'start_date', 'end_date',
        'status', 'appraisal_count'
    ]
    list_filter = ['cycle_type', 'status', 'start_date']
    search_fields = ['name']
    date_hierarchy = 'start_date'
    
    def appraisal_count(self, obj):
        """Count appraisals in this cycle"""
        return obj.employeeappraisal_set.count()
    appraisal_count.short_description = 'Appraisals'


class AppraisalMetricScoreInline(admin.TabularInline):
    """Inline for metric scores"""
    model = AppraisalMetricScore
    extra = 0
    fields = [
        'metric', 'self_rating', 'supervisor_rating',
        'agreed_rating', 'weight_percentage', 'weighted_score'
    ]
    readonly_fields = ['weighted_score']


@admin.register(EmployeeAppraisal)
class EmployeeAppraisalAdmin(admin.ModelAdmin):
    """Employee appraisal admin"""
    list_display = [
        'employee', 'appraisal_cycle', 'appraiser',
        'final_rating_badge', 'final_score', 'status',
        'recommended_action'
    ]
    list_filter = [
        'final_rating', 'status', 'recommended_action',
        'appraisal_cycle'
    ]
    search_fields = [
        'employee__employee_no', 'employee__first_name',
        'appraiser__employee_no'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'employee', 'appraisal_cycle',
                'template', 'appraiser'
            )
        }),
        ('Review Period', {
            'fields': (
                ('review_period_start', 'review_period_end'),
            )
        }),
        ('Assessment Status', {
            'fields': (
                ('self_assessment_status', 'self_assessment_date'),
                ('supervisor_assessment_status', 'supervisor_assessment_date'),
                ('hod_review_status', 'hod_review_date')
            )
        }),
        ('Final Rating', {
            'fields': (
                'final_rating', 'final_score',
                'overall_comments'
            )
        }),
        ('Feedback', {
            'fields': (
                'strengths', 'areas_for_improvement',
                'development_plan'
            )
        }),
        ('Recommendations', {
            'fields': (
                'recommended_action',
                'recommended_increment_percentage'
            )
        }),
        ('Status & Disputes', {
            'fields': (
                'status', 'disputed',
                'dispute_reason', 'dispute_resolution'
            )
        }),
        ('Approval', {
            'fields': (
                ('approved_by', 'approval_date'),
            )
        })
    )
    
    inlines = [AppraisalMetricScoreInline]
    raw_id_fields = ['employee', 'appraiser']
    readonly_fields = ['appraisal_date', 'approval_date']
    
    def final_rating_badge(self, obj):
        """Display final rating badge"""
        if not obj.final_rating:
            return '-'
        colors = {
            'outstanding': 'purple',
            'exceeds_expectations': 'green',
            'meets_expectations': 'blue',
            'needs_improvement': 'orange',
            'unsatisfactory': 'red'
        }
        color = colors.get(obj.final_rating, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px; font-weight: bold;">{}</span>',
            color,
            obj.get_final_rating_display()
        )
    final_rating_badge.short_description = 'Rating'


@admin.register(AcademicProductivity)
class AcademicProductivityAdmin(admin.ModelAdmin):
    """Academic productivity admin"""
    list_display = [
        'employee', 'academic_year', 'publications_count',
        'journal_articles_count', 'research_grants_value',
        'phd_students_supervised'
    ]
    list_filter = ['academic_year']
    search_fields = ['employee__employee_no', 'employee__first_name']
    raw_id_fields = ['employee']


@admin.register(Publication)
class PublicationAdmin(admin.ModelAdmin):
    """Publication admin"""
    list_display = [
        'employee', 'title_short', 'publication_type',
        'publication_date', 'is_peer_reviewed', 'impact_factor',
        'is_verified'
    ]
    list_filter = [
        'publication_type', 'is_peer_reviewed',
        'is_verified', 'indexing'
    ]
    search_fields = [
        'employee__employee_no', 'title',
        'journal_name', 'doi'
    ]
    date_hierarchy = 'publication_date'
    raw_id_fields = ['employee']
    
    def title_short(self, obj):
        """Display short title"""
        return obj.title[:50] + '...' if len(obj.title) > 50 else obj.title
    title_short.short_description = 'Title'


@admin.register(ResearchGrant)
class ResearchGrantAdmin(admin.ModelAdmin):
    """Research grant admin"""
    list_display = [
        'grant_title_short', 'principal_investigator',
        'funding_agency', 'grant_amount', 'start_date',
        'end_date', 'status'
    ]
    list_filter = ['status', 'start_date']
    search_fields = [
        'grant_title', 'funding_agency',
        'principal_investigator__employee_no'
    ]
    raw_id_fields = ['principal_investigator']
    
    def grant_title_short(self, obj):
        return obj.grant_title[:40] + '...' if len(obj.grant_title) > 40 else obj.grant_title
    grant_title_short.short_description = 'Grant Title'


@admin.register(StudentFeedback)
class StudentFeedbackAdmin(admin.ModelAdmin):
    """Student feedback admin"""
    list_display = [
        'employee', 'course_id', 'academic_term_id',
        'total_responses', 'average_rating',
        'teaching_effectiveness', 'overall_satisfaction'
    ]
    list_filter = ['academic_term_id']
    search_fields = ['employee__employee_no', 'employee__first_name']
    raw_id_fields = ['employee']


# ============================================================================
# PAYROLL CORE ADMIN
# ============================================================================

@admin.register(PayrollPeriod)
class PayrollPeriodAdmin(admin.ModelAdmin):
    """Payroll period admin"""
    list_display = [
        'period_name', 'period_type', 'start_date', 'end_date',
        'payment_date', 'status_badge', 'employee_count',
        'total_net_pay_display', 'locked'
    ]
    list_filter = ['status', 'period_type', 'locked', 'start_date']
    search_fields = ['period_name']
    date_hierarchy = 'start_date'
    
    fieldsets = (
        ('Period Information', {
            'fields': (
                'period_name', 'period_type',
                ('start_date', 'end_date'),
                'payment_date'
            )
        }),
        ('Status', {
            'fields': ('status', 'locked')
        }),
        ('Totals', {
            'fields': (
                'total_gross_pay', 'total_deductions',
                'total_net_pay', 'employee_count'
            )
        }),
        ('Processing', {
            'fields': (
                ('processing_started_at', 'processing_completed_at'),
            )
        }),
        ('Approval', {
            'fields': (
                ('approved_by', 'approved_date'),
                'notes'
            )
        })
    )
    
    readonly_fields = [
        'total_gross_pay', 'total_deductions', 'total_net_pay',
        'employee_count', 'processing_started_at', 'processing_completed_at'
    ]
    
    actions = ['lock_periods', 'unlock_periods', 'close_periods']
    
    def status_badge(self, obj):
        """Display status badge"""
        colors = {
            'open': 'blue',
            'processing': 'orange',
            'calculated': 'purple',
            'approved': 'green',
            'paid': 'teal',
            'closed': 'gray'
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def total_net_pay_display(self, obj):
        """Display formatted net pay"""
        return f"${obj.total_net_pay:,.2f}"
    total_net_pay_display.short_description = 'Total Net Pay'
    
    def lock_periods(self, request, queryset):
        """Lock payroll periods"""
        count = queryset.update(locked=True)
        self.message_user(request, f'{count} periods locked.')
    lock_periods.short_description = 'Lock selected periods'
    
    def unlock_periods(self, request, queryset):
        """Unlock payroll periods"""
        count = queryset.update(locked=False)
        self.message_user(request, f'{count} periods unlocked.')
    unlock_periods.short_description = 'Unlock selected periods'


@admin.register(EarningType)
class EarningTypeAdmin(admin.ModelAdmin):
    """Earning type admin"""
    list_display = [
        'code', 'name', 'category', 'is_taxable',
        'is_pensionable', 'gl_account_code', 'is_active'
    ]
    list_filter = ['category', 'is_taxable', 'is_pensionable', 'is_active']
    search_fields = ['code', 'name', 'gl_account_code']
    ordering = ['sort_order', 'name']


@admin.register(DeductionType)
class DeductionTypeAdmin(admin.ModelAdmin):
    """Deduction type admin"""
    list_display = [
        'code', 'name', 'category', 'is_mandatory',
        'gl_account_code', 'is_active'
    ]
    list_filter = ['category', 'is_mandatory', 'is_active']
    search_fields = ['code', 'name', 'gl_account_code']
    ordering = ['sort_order', 'name']


class PayProfileComponentInline(admin.TabularInline):
    """Inline for pay profile components"""
    model = PayProfileComponent
    extra = 0
    fields = [
        'earning_type', 'calculation_method', 'amount',
        'percentage', 'is_taxable', 'is_pensionable'
    ]


@admin.register(PayProfile)
class PayProfileAdmin(admin.ModelAdmin):
    """Pay profile admin"""
    list_display = [
        'code', 'name', 'job_grade', 'employee_category',
        'basic_salary', 'pay_frequency', 'is_active'
    ]
    list_filter = ['employee_category', 'pay_frequency', 'is_active']
    search_fields = ['code', 'name']
    inlines = [PayProfileComponentInline]


@admin.register(EmployeePayProfile)
class EmployeePayProfileAdmin(admin.ModelAdmin):
    """Employee pay profile admin"""
    list_display = [
        'employee', 'pay_profile', 'basic_salary',
        'effective_from', 'effective_to', 'is_active'
    ]
    list_filter = ['is_active', 'effective_from']
    search_fields = ['employee__employee_no', 'employee__first_name']
    raw_id_fields = ['employee']


@admin.register(EmployeeEarning)
class EmployeeEarningAdmin(admin.ModelAdmin):
    """Employee earning admin"""
    list_display = [
        'employee', 'earning_type', 'amount', 'is_recurring',
        'is_one_time', 'status', 'effective_from'
    ]
    list_filter = [
        'earning_type', 'status', 'is_recurring',
        'is_one_time', 'is_taxable'
    ]
    search_fields = ['employee__employee_no', 'employee__first_name']
    raw_id_fields = ['employee']


@admin.register(EmployeeDeduction)
class EmployeeDeductionAdmin(admin.ModelAdmin):
    """Employee deduction admin"""
    list_display = [
        'employee', 'deduction_type', 'amount', 'is_recurring',
        'balance_remaining', 'status', 'effective_from'
    ]
    list_filter = [
        'deduction_type', 'status', 'is_recurring', 'is_one_time'
    ]
    search_fields = ['employee__employee_no', 'employee__first_name']
    raw_id_fields = ['employee']


class PayrollCalculationDetailInline(admin.TabularInline):
    """Inline for payroll calculation details"""
    model = PayrollCalculationDetail
    extra = 0
    fields = [
        'item_type', 'description', 'amount',
        'is_taxable', 'is_pensionable'
    ]
    readonly_fields = ['item_type', 'description', 'amount']
    can_delete = False


@admin.register(PayrollCalculation)
class PayrollCalculationAdmin(admin.ModelAdmin):
    """Payroll calculation admin"""
    list_display = [
        'employee', 'payroll_period', 'gross_pay',
        'total_deductions', 'net_pay', 'payment_status'
    ]
    list_filter = [
        'payroll_period', 'payment_status',
        'payment_method'
    ]
    search_fields = [
        'employee__employee_no', 'employee__first_name'
    ]
    
    fieldsets = (
        ('Employee & Period', {
            'fields': ('employee', 'payroll_period')
        }),
        ('Earnings', {
            'fields': (
                'basic_salary', 'total_allowances',
                'total_overtime', 'total_bonuses',
                'total_earnings', 'gross_pay'
            )
        }),
        ('Deductions', {
            'fields': (
                'total_statutory_deductions',
                'total_voluntary_deductions',
                'total_loan_deductions',
                'total_deductions'
            )
        }),
        ('Tax & Pension', {
            'fields': (
                'taxable_income', 'tax_amount',
                ('pension_employee', 'pension_employer')
            )
        }),
        ('Net Pay & Cost', {
            'fields': ('net_pay', 'employer_cost')
        }),
        ('Payment Details', {
            'fields': (
                'payment_method', 'bank_account_number',
                'payment_status',
                ('payment_date', 'payment_reference')
            )
        }),
        ('Processing', {
            'fields': (
                ('calculated_at', 'calculated_by'),
                ('approved_at', 'approved_by'),
                'notes'
            )
        })
    )
    
    inlines = [PayrollCalculationDetailInline]
    raw_id_fields = ['employee']
    readonly_fields = [
        'calculated_at', 'calculated_by',
        'approved_at', 'approved_by'
    ]


@admin.register(Payslip)
class PayslipAdmin(admin.ModelAdmin):
    """Payslip admin"""
    list_display = [
        'payslip_number', 'employee', 'payroll_period',
        'generation_date', 'email_sent', 'downloaded'
    ]
    list_filter = ['email_sent', 'downloaded', 'generation_date']
    search_fields = [
        'payslip_number', 'employee__employee_no',
        'employee__first_name'
    ]
    raw_id_fields = ['employee']
    readonly_fields = ['generation_date']


@admin.register(PayrollAuditLog)
class PayrollAuditLogAdmin(admin.ModelAdmin):
    """Payroll audit log admin"""
    list_display = [
        'payroll_period', 'employee', 'action',
        'performed_by', 'performed_at'
    ]
    list_filter = ['action', 'performed_at']
    search_fields = [
        'payroll_period__period_name',
        'employee__employee_no', 'reason'
    ]
    date_hierarchy = 'performed_at'
    readonly_fields = ['performed_at']
    
    def has_add_permission(self, request):
        """Audit logs cannot be added manually"""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Audit logs cannot be deleted"""
        return False
# ============================================================================
# ADMIN SITE CUSTOMIZATION
# ============================================================================

# Customize admin site header and title
admin.site.site_header = 'HR & Payroll Management System'
admin.site.site_title = 'HR & Payroll Admin'
admin.site.index_title = 'Administration Dashboard'