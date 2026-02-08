from django.contrib import admin
from django.utils.html import format_html
from .models import *

@admin.register(RecruitmentSource)
class RecruitmentSourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'source_type', 'contact_person', 'is_active')
    list_filter = ('source_type', 'is_active')
    search_fields = ('name', 'contact_person', 'contact_email')


@admin.register(JobOpening)
class JobOpeningAdmin(admin.ModelAdmin):
    list_display = ('reference_number', 'title', 'department', 'status', 'opening_date', 'closing_date')
    list_filter = ('status', 'department', 'campus', 'opening_type')
    search_fields = ('title', 'description', 'reference_number')
    filter_horizontal = ('recruitment_sources',)
    readonly_fields = ('reference_number', 'created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('reference_number', 'title', 'job_title', 'department', 'campus', 'opening_type')
        }),
        ('Details', {
            'fields': ('description', 'responsibilities', 'requirements', 'benefits', 'key_skills')
        }),
        ('Position Details', {
            'fields': ('number_of_positions', 'min_salary', 'max_salary', 'is_remote_allowed', 'travel_requirement')
        }),
        ('Dates', {
            'fields': ('opening_date', 'closing_date', 'expected_joining_date')
        }),
        ('Approval', {
            'fields': ('status', 'requested_by', 'hiring_manager', 'hr_approver', 'final_approver')
        }),
        ('Recruitment', {
            'fields': ('recruitment_sources', 'publish_date', 'published_by')
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at', 'created_by', 'updated_by')
        }),
    )


class ApplicationEducationInline(admin.TabularInline):
    model = ApplicationEducation
    extra = 0


class ApplicationExperienceInline(admin.TabularInline):
    model = ApplicationExperience
    extra = 0


class ApplicationSkillInline(admin.TabularInline):
    model = ApplicationSkill
    extra = 0


class ApplicationCertificateInline(admin.TabularInline):
    model = ApplicationCertificate
    extra = 0


@admin.register(JobApplication)
class JobApplicationAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'email', 'job_opening', 'application_status', 'application_date')
    list_filter = ('application_status', 'application_source', 'job_opening')
    search_fields = ('first_name', 'last_name', 'email', 'phone')
    readonly_fields = ('application_date', 'created_at', 'updated_at')
    inlines = [
        ApplicationEducationInline,
        ApplicationExperienceInline,
        ApplicationSkillInline,
        ApplicationCertificateInline
    ]
    
    fieldsets = (
        ('Personal Information', {
            'fields': (
                'first_name', 'middle_name', 'last_name', 'email', 'phone',
                'alternate_phone', 'address', 'city', 'state', 'country',
                'postal_code', 'gender', 'date_of_birth', 'nationality'
            )
        }),
        ('Application Details', {
            'fields': (
                'job_opening', 'application_source', 'referral_employee',
                'recruitment_source', 'application_status', 'application_date'
            )
        }),
        ('Professional Information', {
            'fields': (
                'highest_education', 'total_experience_years',
                'current_employer', 'current_position', 'current_salary',
                'expected_salary', 'notice_period_days'
            )
        }),
        ('Documents', {
            'fields': ('resume', 'cover_letter')
        }),
        ('Communication', {
            'fields': ('preferred_contact_method', 'linkedin_profile', 'portfolio_url', 'github_profile')
        }),
        ('Consent', {
            'fields': ('consent_to_process_data', 'consent_to_store_data', 'privacy_policy_accepted')
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at', 'created_by', 'updated_by')
        }),
    )
    
    def full_name(self, obj):
        return obj.full_name
    full_name.admin_order_field = 'last_name'


@admin.register(InterviewSchedule)
class InterviewScheduleAdmin(admin.ModelAdmin):
    list_display = ('application', 'interview_round', 'interview_date', 'start_time', 'status')
    list_filter = ('status', 'interview_mode', 'interview_round')
    filter_horizontal = ('interviewers',)


@admin.register(OfferLetter)
class OfferLetterAdmin(admin.ModelAdmin):
    list_display = ('offer_reference', 'application', 'status', 'offer_date', 'joining_date')
    list_filter = ('status', 'currency')
    readonly_fields = ('offer_reference', 'created_at', 'updated_at')


# Register other models
admin.site.register(InterviewRound)
admin.site.register(InterviewEvaluation)
admin.site.register(AssessmentTest)
admin.site.register(CandidateAssessment)
admin.site.register(BackgroundCheck)
admin.site.register(ReferenceCheck)
admin.site.register(RecruitmentWorkflow)
admin.site.register(ApplicationWorkflow)
admin.site.register(RecruitmentAnalytics)
admin.site.register(RecruitmentEmailTemplate)
admin.site.register(RecruitmentCommunication)