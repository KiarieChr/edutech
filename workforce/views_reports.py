from django.views.generic import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.utils import timezone
from datetime import datetime, timedelta
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import *
from .reports_pdf import *
from .reports_excel import *


# ============================================================================
# PDF REPORT VIEWS
# ============================================================================

class PayslipPDFView(LoginRequiredMixin, View):
    """Generate payslip PDF"""
    
    def get(self, request, calculation_id):
        try:
            calculation = PayrollCalculation.objects.select_related(
                'employee', 'payroll_period'
            ).prefetch_related('details').get(id=calculation_id)
            
            generator = PayslipPDFGenerator()
            return generator.generate(calculation)
            
        except PayrollCalculation.DoesNotExist:
            return JsonResponse({'error': 'Payroll calculation not found'}, status=404)


class EmployeeReportPDFView(LoginRequiredMixin, View):
    """Generate employee report PDF"""
    
    def get(self, request):
        # Get filter parameters
        status = request.GET.get('status')
        category = request.GET.get('category')
        department_id = request.GET.get('department')
        
        employees = Employee.objects.select_related('department', 'job_grade')
        
        filters = []
        if status:
            employees = employees.filter(employment_status=status)
            filters.append(f"Status: {status}")
        
        if category:
            employees = employees.filter(employee_category=category)
            filters.append(f"Category: {category}")
        
        if department_id:
            employees = employees.filter(department_id=department_id)
            dept = Department.objects.get(id=department_id)
            filters.append(f"Department: {dept.name}")
        
        filter_str = ', '.join(filters) if filters else 'All Employees'
        
        generator = EmployeeReportPDFGenerator()
        return generator.generate(employees, filter_str)


class PayrollRegisterPDFView(LoginRequiredMixin, View):
    """Generate payroll register PDF"""
    
    def get(self, request, period_id):
        try:
            period = PayrollPeriod.objects.prefetch_related(
                'calculations__employee'
            ).get(id=period_id)
            
            generator = PayrollRegisterPDFGenerator()
            return generator.generate(period)
            
        except PayrollPeriod.DoesNotExist:
            return JsonResponse({'error': 'Payroll period not found'}, status=404)


class AttendanceReportPDFView(LoginRequiredMixin, View):
    """Generate attendance report PDF"""
    
    def get(self, request):
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        if not start_date or not end_date:
            today = timezone.now().date()
            start_date = today.replace(day=1)
            end_date = today
        else:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        records = AttendanceRecord.objects.filter(
            attendance_date__range=[start_date, end_date]
        ).select_related('employee')
        
        generator = AttendanceReportPDFGenerator()
        return generator.generate(records, start_date, end_date)


class LeaveReportPDFView(LoginRequiredMixin, View):
    """Generate leave report PDF"""
    
    def get(self, request):
        year = request.GET.get('year', timezone.now().year)
        
        applications = LeaveApplication.objects.filter(
            start_date__year=year
        ).select_related('employee', 'leave_type')
        
        generator = LeaveReportPDFGenerator()
        return generator.generate(applications, year)


# ============================================================================
# EXCEL REPORT VIEWS
# ============================================================================

class PayrollRegisterExcelView(LoginRequiredMixin, View):
    """Generate payroll register Excel"""
    
    def get(self, request, period_id):
        try:
            period = PayrollPeriod.objects.prefetch_related(
                'calculations__employee__department'
            ).get(id=period_id)
            
            generator = PayrollRegisterExcelGenerator()
            return generator.generate(period)
            
        except PayrollPeriod.DoesNotExist:
            return JsonResponse({'error': 'Payroll period not found'}, status=404)


class EmployeeListExcelView(LoginRequiredMixin, View):
    """Generate employee list Excel"""
    
    def get(self, request):
        # Get filter parameters
        status = request.GET.get('status')
        category = request.GET.get('category')
        department_id = request.GET.get('department')
        
        employees = Employee.objects.select_related('department', 'job_grade')
        
        if status:
            employees = employees.filter(employment_status=status)
        
        if category:
            employees = employees.filter(employee_category=category)
        
        if department_id:
            employees = employees.filter(department_id=department_id)
        
        generator = EmployeeListExcelGenerator()
        return generator.generate(employees)


class AttendanceReportExcelView(LoginRequiredMixin, View):
    """Generate attendance report Excel"""
    
    def get(self, request):
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        if not start_date or not end_date:
            today = timezone.now().date()
            start_date = today.replace(day=1)
            end_date = today
        else:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        records = AttendanceRecord.objects.filter(
            attendance_date__range=[start_date, end_date]
        ).select_related('employee', 'employee__department')
        
        generator = AttendanceReportExcelGenerator()
        return generator.generate(records, start_date, end_date)


class LeaveBalanceExcelView(LoginRequiredMixin, View):
    """Generate leave balance Excel"""
    
    def get(self, request):
        year = request.GET.get('year', timezone.now().year)
        
        balances = EmployeeLeaveBalance.objects.filter(
            year=year
        ).select_related('employee', 'leave_type')
        
        generator = LeaveBalanceExcelGenerator()
        return generator.generate(balances, year)


class PayrollComparisonExcelView(LoginRequiredMixin, View):
    """Generate payroll comparison Excel"""
    
    def get(self, request):
        # Get last 6 periods
        periods = PayrollPeriod.objects.filter(
            status__in=['approved', 'paid', 'closed']
        ).order_by('-start_date')[:6]
        
        periods = list(reversed(periods))  # Chronological order
        
        generator = PayrollComparisonExcelGenerator()
        return generator.generate(periods)


# ============================================================================
# API ENDPOINTS FOR REPORT GENERATION
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def generate_report(request):
    """
    Generic report generation endpoint
    
    Query parameters:
    - report_type: payslip, employee_list, payroll_register, attendance, leave
    - format: pdf, excel
    - Additional parameters based on report type
    """
    report_type = request.GET.get('report_type')
    format_type = request.GET.get('format', 'pdf')
    
    if not report_type:
        return Response({'error': 'report_type is required'}, status=400)
    
    # Route to appropriate view
    if report_type == 'payslip':
        calc_id = request.GET.get('calculation_id')
        if not calc_id:
            return Response({'error': 'calculation_id is required'}, status=400)
        
        try:
            calculation = PayrollCalculation.objects.get(id=calc_id)
            generator = PayslipPDFGenerator()
            return generator.generate(calculation)
        except PayrollCalculation.DoesNotExist:
            return Response({'error': 'Calculation not found'}, status=404)
    
    elif report_type == 'employee_list':
        employees = Employee.objects.all()
        
        if format_type == 'excel':
            generator = EmployeeListExcelGenerator()
        else:
            generator = EmployeeReportPDFGenerator()
        
        return generator.generate(employees)
    
    elif report_type == 'payroll_register':
        period_id = request.GET.get('period_id')
        if not period_id:
            return Response({'error': 'period_id is required'}, status=400)
        
        try:
            period = PayrollPeriod.objects.get(id=period_id)
            
            if format_type == 'excel':
                generator = PayrollRegisterExcelGenerator()
            else:
                generator = PayrollRegisterPDFGenerator()
            
            return generator.generate(period)
        except PayrollPeriod.DoesNotExist:
            return Response({'error': 'Period not found'}, status=404)
    
    else:
        return Response({'error': 'Invalid report_type'}, status=400)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def available_reports(request):
    """Get list of available reports"""
    reports = {
        'payroll_reports': [
            {
                'name': 'Payslip',
                'type': 'payslip',
                'formats': ['pdf'],
                'required_params': ['calculation_id'],
                'description': 'Individual employee payslip'
            },
            {
                'name': 'Payroll Register',
                'type': 'payroll_register',
                'formats': ['pdf', 'excel'],
                'required_params': ['period_id'],
                'description': 'Complete payroll for a period'
            },
            {
                'name': 'Payroll Comparison',
                'type': 'payroll_comparison',
                'formats': ['excel'],
                'required_params': [],
                'description': 'Compare multiple payroll periods'
            }
        ],
        'employee_reports': [
            {
                'name': 'Employee List',
                'type': 'employee_list',
                'formats': ['pdf', 'excel'],
                'optional_params': ['status', 'category', 'department'],
                'description': 'List of all employees with filters'
            }
        ],
        'attendance_reports': [
            {
                'name': 'Attendance Report',
                'type': 'attendance',
                'formats': ['pdf', 'excel'],
                'optional_params': ['start_date', 'end_date'],
                'description': 'Attendance records for a period'
            }
        ],
        'leave_reports': [
            {
                'name': 'Leave Report',
                'type': 'leave',
                'formats': ['pdf'],
                'optional_params': ['year'],
                'description': 'Leave applications for a year'
            },
            {
                'name': 'Leave Balance',
                'type': 'leave_balance',
                'formats': ['excel'],
                'optional_params': ['year'],
                'description': 'Employee leave balances'
            }
        ]
    }
    
    return Response(reports)


# ============================================================================
# BATCH REPORT GENERATION
# ============================================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def batch_generate_payslips(request):
    """
    Generate payslips for all employees in a period
    """
    period_id = request.data.get('period_id')
    
    if not period_id:
        return Response({'error': 'period_id is required'}, status=400)
    
    try:
        period = PayrollPeriod.objects.get(id=period_id)
    except PayrollPeriod.DoesNotExist:
        return Response({'error': 'Period not found'}, status=404)
    
    calculations = PayrollCalculation.objects.filter(
        payroll_period=period
    ).select_related('employee')
    
    generated = []
    errors = []
    
    for calc in calculations:
        try:
            # Check if payslip already exists
            payslip, created = Payslip.objects.get_or_create(
                payroll_calculation=calc,
                defaults={
                    'employee': calc.employee,
                    'payroll_period': period,
                    'payslip_number': f"PS-{period.id}-{calc.employee.employee_no}"
                }
            )
            
            if created:
                # Generate PDF
                generator = PayslipPDFGenerator()
                # In production, save to file storage
                # payslip.pdf_path = generated_file_path
                # payslip.save()
                
                generated.append({
                    'employee_no': calc.employee.employee_no,
                    'payslip_number': payslip.payslip_number
                })
        
        except Exception as e:
            errors.append({
                'employee_no': calc.employee.employee_no,
                'error': str(e)
            })
    
    return Response({
        'success': True,
        'generated': len(generated),
        'errors': len(errors),
        'details': {
            'generated': generated,
            'errors': errors
        }
    })
