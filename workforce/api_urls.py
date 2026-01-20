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