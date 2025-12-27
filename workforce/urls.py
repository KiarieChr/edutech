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

# Attendance
router.register(r'attendance', AttendanceRecordViewSet, basename='attendance')
router.register(r'overtime-requests', OvertimeRequestViewSet, basename='overtime-request')

# Leave
router.register(r'leave-applications', LeaveApplicationViewSet, basename='leave-application')
router.register(r'leave-balances', EmployeeLeaveBalanceViewSet, basename='leave-balance')

# Payroll
router.register(r'payroll-periods', PayrollPeriodViewSet, basename='payroll-period')
router.register(r'payroll-calculations', PayrollCalculationViewSet, basename='payroll-calculation')
router.register(r'payslips', PayslipViewSet, basename='payslip')

app_name = 'hr_payroll'

urlpatterns = [
    path('', views.hr_dashboard, name='hr_dashboard'),
    path('payroll-dashboard/', views.payroll_dashboard, name='payroll_dashboard'),
    
    # Employees
    path('employees/', views.employee_list, name='employee_list'),
    path('employees/create/', views.employee_create, name='employee_create'),
    path('employees/<int:employee_id>/', views.employee_detail, name='employee_detail'),
    path('employees/<int:employee_id>/edit/', views.employee_edit, name='employee_edit'),
    
    # Attendance
    path('attendance/', views.attendance_list, name='attendance_list'),
    path('attendance/mark/', views.attendance_mark, name='attendance_mark'),
    
    # Leave
    path('leave/', views.leave_application_list, name='leave_application_list'),
    path('leave/create/', views.leave_application_create, name='leave_application_create'),
    path('leave/<int:application_id>/approve/', views.leave_application_approve, name='leave_application_approve'),
    path('leave/<int:application_id>/reject/', views.leave_application_reject, name='leave_application_reject'),
    path('leave/balances/', views.leave_balance_view, name='leave_balance_view'),
    
    # Payroll
    path('payroll/', views.payroll_period_list, name='payroll_period_list'),
    path('payroll/<int:period_id>/', views.payroll_period_detail, name='payroll_period_detail'),
    path('payroll/calculation/<int:calculation_id>/', views.payroll_calculation_detail, name='payroll_calculation_detail'),
    
    # Reports
    path('reports/payslip/<int:calculation_id>/pdf/', views.download_payslip_pdf, name='download_payslip_pdf'),
    path('reports/employees/excel/', views.download_employee_list_excel, name='download_employee_list_excel'),
    path('reports/payroll/<int:period_id>/excel/', views.download_payroll_register_excel, name='download_payroll_register_excel'),
    path('reports/attendance/excel/', views.download_attendance_report_excel, name='download_attendance_report_excel'),

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