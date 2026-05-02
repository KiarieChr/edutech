from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import *
from .views_reports import *
from .viewsets import *
from . import views

# Create router for ViewSets
router = DefaultRouter()

# Core
router.register(r'employees', EmployeeViewSet, basename='employee')
router.register(r'departments', DepartmentViewSet, basename='department')
router.register(r'campuses', CampusViewSet, basename='campus')
router.register(r'job-titles', JobTitleViewSet, basename='job-title')
router.register(r'job-grades', JobGradeViewSet, basename='job-grade')

# Attendance
router.register(r'attendance', AttendanceRecordViewSet, basename='attendance')
router.register(r'attendance-policies', AttendancePolicyViewSet, basename='attendance-policy')
router.register(r'employee-attendance-access-profiles', EmployeeAttendanceAccessProfileViewSet, basename='employee-attendance-access-profile')
router.register(r'work-schedules', WorkScheduleViewSet, basename='work-schedule')
router.register(r'employee-work-schedules', EmployeeWorkScheduleViewSet, basename='employee-work-schedule')
router.register(r'biometric-devices', BiometricDeviceViewSet, basename='biometric-device')
router.register(r'overtime-requests', OvertimeRequestViewSet, basename='overtime-request')

# Leave
router.register(r'leave-applications', LeaveApplicationViewSet, basename='leave-application')
router.register(r'leave-balances', EmployeeLeaveBalanceViewSet, basename='leave-balance')

# Payroll
router.register(r'payroll-periods', PayrollPeriodViewSet, basename='payroll-period')
router.register(r'payroll-calculations', PayrollCalculationViewSet, basename='payroll-calculation')
router.register(r'payslips', PayslipViewSet, basename='payslip')
router.register(r'payslip-templates', PayslipTemplateViewSet, basename='payslip-template')
router.register(r'pay-grade-steps', PayGradeStepViewSet, basename='pay-grade-step')
router.register(r'payroll-accounts', PayrollAccountViewSet, basename='payroll-account')
router.register(r'employee-pay-profiles', EmployeePayProfileViewSet, basename='employee-pay-profile')
router.register(r'employee-earnings', EmployeeEarningViewSet, basename='employee-earning')
router.register(r'employee-deductions', EmployeeDeductionViewSet, basename='employee-deduction')
router.register(r'group-earnings', GroupEarningViewSet, basename='group-earning')
router.register(r'group-deductions', GroupDeductionViewSet, basename='group-deduction')
router.register(r'pension-schemes', PensionSchemeViewSet, basename='pension-scheme')
router.register(r'pension-grade-rates', PensionSchemeGradeRateViewSet, basename='pension-grade-rate')
router.register(r'pension-enrollments', EmployeePensionEnrollmentViewSet, basename='pension-enrollment')
router.register(r'pension-contributions', PensionContributionViewSet, basename='pension-contribution')

# HRMS Enhancement Routes
router.register(r'positions', PositionViewSet, basename='position')
router.register(r'lifecycle-logs', EmployeeLifecycleLogViewSet, basename='lifecycle-log')
router.register(r'employee-lifecycle', EmployeeLifecycleViewSet, basename='employee-lifecycle')
router.register(r'bulk-imports', BulkImportSessionViewSet, basename='bulk-import')
router.register(r'employee-documents', EmployeeDocumentViewSet, basename='employee-document')
router.register(r'automation-rules', HRAutomationRuleViewSet, basename='automation-rule')
router.register(r'notification-preferences', HRNotificationPreferenceViewSet, basename='notification-preference')
router.register(r'org-chart', OrgChartViewSet, basename='org-chart')
router.register(r'hr-analytics', HRAnalyticsViewSet, basename='hr-analytics')
router.register(r'payroll-dashboard', PayrollDashboardViewSet, basename='payroll-dashboard')
router.register(r'payroll-settings', PayrollSettingsViewSet, basename='payroll-settings')


urlpatterns = [
    # API endpoints
    path('api/', include(router.urls)),

    # ========================================================================
    # PDF REPORTS
    # ========================================================================
    path('reports/pdf/payslip/<int:calculation_id>/', 
         PayslipPDFView.as_view(), 
         name='payslip-pdf'),
    
    path('reports/pdf/employees/', 
         EmployeeReportPDFView.as_view(), 
         name='employee-report-pdf'),
    
    path('reports/pdf/payroll-register/<int:period_id>/', 
         PayrollRegisterPDFView.as_view(), 
         name='payroll-register-pdf'),
    
    path('reports/pdf/attendance/', 
         AttendanceReportPDFView.as_view(), 
         name='attendance-report-pdf'),
    
    path('reports/pdf/leave/', 
         LeaveReportPDFView.as_view(), 
         name='leave-report-pdf'),
    
    # ========================================================================
    # EXCEL REPORTS
    # ========================================================================
    path('reports/excel/payroll-register/<int:period_id>/', 
         PayrollRegisterExcelView.as_view(), 
         name='payroll-register-excel'),
    
    path('reports/excel/employees/', 
         EmployeeListExcelView.as_view(), 
         name='employee-list-excel'),
    
    path('reports/excel/attendance/', 
         AttendanceReportExcelView.as_view(), 
         name='attendance-report-excel'),
    
    path('reports/excel/leave-balance/', 
         LeaveBalanceExcelView.as_view(), 
         name='leave-balance-excel'),
    
    path('reports/excel/payroll-comparison/', 
         PayrollComparisonExcelView.as_view(), 
         name='payroll-comparison-excel'),
    
    # ========================================================================
    # REPORT API ENDPOINTS
    # ========================================================================
    path('api/reports/generate/', 
         generate_report, 
         name='api-generate-report'),
    
    path('api/reports/available/', 
         available_reports, 
         name='api-available-reports'),
    
    path('api/reports/batch-payslips/', 
         batch_generate_payslips, 
         name='api-batch-payslips'),
]