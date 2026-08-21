"""
HR & Payroll Django Views for HTML Templates
views.py
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count, Sum, Avg
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from datetime import datetime, timedelta
from decimal import Decimal

from .models import *
from .forms import *
from .reports_pdf import *
from .reports_excel import *


# ============================================================================
# DASHBOARD VIEWS
# ============================================================================

@login_required
def hr_dashboard(request):
    """Main HR Dashboard"""
    context = {
        'page_title': 'HR Dashboard',
        'total_employees': Employee.objects.count(),
        'active_employees': Employee.objects.filter(employment_status='active').count(),
        'on_probation': Employee.objects.filter(employment_status='probation').count(),
        'pending_leaves': LeaveApplication.objects.filter(
            status__in=['submitted', 'pending_approval']
        ).count(),
    }
    
    # Employees by category
    context['employees_by_category'] = Employee.objects.values(
        'employee_category'
    ).annotate(count=Count('id'))
    
    # Recent hires (last 30 days)
    thirty_days_ago = timezone.now().date() - timedelta(days=30)
    context['recent_hires'] = Employee.objects.filter(
        hire_date__gte=thirty_days_ago
    ).order_by('-hire_date')[:5]
    
    # Pending leave applications
    context['pending_leave_applications'] = LeaveApplication.objects.filter(
        status__in=['submitted', 'pending_approval']
    ).select_related('employee', 'leave_type').order_by('-application_date')[:5]
    
    # Today's attendance summary
    today = timezone.now().date()
    attendance_today = AttendanceRecord.objects.filter(attendance_date=today)
    context['attendance_today'] = {
        'present': attendance_today.filter(status='present').count(),
        'absent': attendance_today.filter(status='absent').count(),
        'late': attendance_today.filter(status='late').count(),
        'on_leave': attendance_today.filter(status='on_leave').count(),
    }
    
    return render(request, 'hr_payroll/dashboard.html', context)


@login_required
def payroll_dashboard(request):
    """Payroll Dashboard"""
    context = {
        'page_title': 'Payroll Dashboard',
    }
    
    # Current payroll period
    current_period = PayrollPeriod.objects.filter(
        status__in=['open', 'processing', 'calculated']
    ).order_by('-start_date').first()
    
    context['current_period'] = current_period
    
    if current_period:
        calculations = PayrollCalculation.objects.filter(
            payroll_period=current_period
        )
        
        context['period_summary'] = {
            'employee_count': calculations.count(),
            'total_gross': calculations.aggregate(Sum('gross_pay'))['gross_pay__sum'] or 0,
            'total_deductions': calculations.aggregate(Sum('total_deductions'))['total_deductions__sum'] or 0,
            'total_net': calculations.aggregate(Sum('net_pay'))['net_pay__sum'] or 0,
        }
    
    # Recent payroll periods
    context['recent_periods'] = PayrollPeriod.objects.order_by('-start_date')[:6]
    
    # Pending approvals
    context['pending_approvals'] = PayrollPeriod.objects.filter(
        status='calculated'
    ).count()
    
    return render(request, 'hr_payroll/payroll_dashboard.html', context)


# ============================================================================
# EMPLOYEE VIEWS
# ============================================================================

@login_required
def employee_list(request):
    """List all employees"""
    employees = Employee.objects.select_related(
        'department', 'job_grade'
    ).order_by('employee_no')
    
    # Filters
    status = request.GET.get('status')
    category = request.GET.get('category')
    department = request.GET.get('department')
    search = request.GET.get('search')
    
    if status:
        employees = employees.filter(employment_status=status)
    
    if category:
        employees = employees.filter(employee_category=category)
    
    if department:
        employees = employees.filter(department_id=department)
    
    if search:
        employees = employees.filter(
            Q(employee_no__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search)
        )
    
    context = {
        'page_title': 'Employee List',
        'employees': employees,
        'departments': Department.objects.filter(is_active=True),
        'total_count': employees.count(),
    }
    
    return render(request, 'hr_payroll/employee_list.html', context)


@login_required
def employee_detail(request, employee_id):
    """Employee detail view"""
    employee = get_object_or_404(
        Employee.objects.select_related('department', 'job_grade'),
        id=employee_id
    )
    
    # Get related data
    addresses = employee.addresses.all()
    emergency_contacts = employee.emergency_contacts.all()
    education = employee.education.select_related('institution', 'education_level')
    certifications = employee.certifications.all()
    job_assignments = employee.job_assignments.select_related(
        'job_title', 'department'
    ).order_by('-effective_from')
    
    # Leave balance
    current_year = timezone.now().year
    leave_balances = EmployeeLeaveBalance.objects.filter(
        employee=employee,
        year=current_year
    ).select_related('leave_type')
    
    # Recent attendance
    recent_attendance = AttendanceRecord.objects.filter(
        employee=employee
    ).order_by('-attendance_date')[:10]
    
    # Recent payroll
    recent_payroll = PayrollCalculation.objects.filter(
        employee=employee
    ).select_related('payroll_period').order_by('-payroll_period__start_date')[:6]
    
    context = {
        'page_title': f'Employee: {employee.get_full_name()}',
        'employee': employee,
        'addresses': addresses,
        'emergency_contacts': emergency_contacts,
        'education': education,
        'certifications': certifications,
        'job_assignments': job_assignments,
        'leave_balances': leave_balances,
        'recent_attendance': recent_attendance,
        'recent_payroll': recent_payroll,
    }
    
    return render(request, 'hr_payroll/employee_detail.html', context)


@login_required
def employee_create(request):
    """Create new employee"""
    if request.method == 'POST':
        form = EmployeeForm(request.POST)
        if form.is_valid():
            employee = form.save(commit=False)
            employee.created_by = request.user
            employee.save()
            messages.success(request, 'Employee created successfully!')
            return redirect('employee_detail', employee_id=employee.id)
    else:
        form = EmployeeForm()
    
    context = {
        'page_title': 'Add New Employee',
        'form': form,
    }
    
    return render(request, 'hr_payroll/employee_form.html', context)


@login_required
def employee_edit(request, employee_id):
    """Edit employee"""
    employee = get_object_or_404(Employee, id=employee_id)
    
    if request.method == 'POST':
        form = EmployeeForm(request.POST, instance=employee)
        if form.is_valid():
            employee = form.save(commit=False)
            employee.updated_by = request.user
            employee.save()
            messages.success(request, 'Employee updated successfully!')
            return redirect('employee_detail', employee_id=employee.id)
    else:
        form = EmployeeForm(instance=employee)
    
    context = {
        'page_title': f'Edit: {employee.get_full_name()}',
        'form': form,
        'employee': employee,
    }
    
    return render(request, 'hr_payroll/employee_form.html', context)


# ============================================================================
# ATTENDANCE VIEWS
# ============================================================================

@login_required
def attendance_list(request):
    """List attendance records"""
    # Date range
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
    ).select_related('employee', 'employee__department').order_by('-attendance_date', 'employee__employee_no')
    
    # Filters
    status = request.GET.get('status')
    department = request.GET.get('department')
    
    if status:
        records = records.filter(status=status)
    
    if department:
        records = records.filter(employee__department_id=department)
    
    # Summary
    summary = {
        'total': records.count(),
        'present': records.filter(status='present').count(),
        'absent': records.filter(status='absent').count(),
        'late': records.filter(status='late').count(),
        'on_leave': records.filter(status='on_leave').count(),
    }
    
    context = {
        'page_title': 'Attendance Records',
        'records': records,
        'start_date': start_date,
        'end_date': end_date,
        'summary': summary,
        'departments': Department.objects.filter(is_active=True),
    }
    
    return render(request, 'hr_payroll/attendance_list.html', context)


@login_required
def attendance_mark(request):
    """Mark attendance for employees"""
    if request.method == 'POST':
        date = request.POST.get('date')
        employee_id = request.POST.get('employee_id')
        status = request.POST.get('status')
        
        employee = get_object_or_404(Employee, id=employee_id)
        
        # Get or create attendance record
        attendance, created = AttendanceRecord.objects.get_or_create(
            employee=employee,
            attendance_date=date,
            defaults={
                'status': status,
                'created_by': request.user,
            }
        )
        
        if not created:
            attendance.status = status
            attendance.updated_by = request.user
            attendance.save()
        
        messages.success(request, 'Attendance marked successfully!')
        return redirect('attendance_list')
    
    # Get all active employees
    today = timezone.now().date()
    employees = Employee.objects.filter(
        employment_status='active'
    ).select_related('department').order_by('employee_no')
    
    # Check existing attendance for today
    existing_attendance = AttendanceRecord.objects.filter(
        attendance_date=today
    ).values_list('employee_id', flat=True)
    
    context = {
        'page_title': 'Mark Attendance',
        'employees': employees,
        'today': today,
        'existing_attendance': list(existing_attendance),
    }
    
    return render(request, 'hr_payroll/attendance_mark.html', context)


# ============================================================================
# LEAVE VIEWS
# ============================================================================

@login_required
def leave_application_list(request):
    """List leave applications"""
    applications = LeaveApplication.objects.select_related(
        'employee', 'leave_type'
    ).order_by('-application_date')
    
    # Filters
    status = request.GET.get('status')
    leave_type = request.GET.get('leave_type')
    employee_id = request.GET.get('employee')
    
    if status:
        applications = applications.filter(status=status)
    
    if leave_type:
        applications = applications.filter(leave_type_id=leave_type)
    
    if employee_id:
        applications = applications.filter(employee_id=employee_id)
    
    context = {
        'page_title': 'Leave Applications',
        'applications': applications,
        'leave_types': LeaveType.objects.filter(is_active=True),
        'pending_count': applications.filter(
            status__in=['submitted', 'pending_approval']
        ).count(),
    }
    
    return render(request, 'hr_payroll/leave_list.html', context)


@login_required
def leave_application_create(request):
    """Create leave application"""
    if request.method == 'POST':
        form = LeaveApplicationForm(request.POST, request.FILES)
        if form.is_valid():
            application = form.save(commit=False)
            application.created_by = request.user
            application.save()
            messages.success(request, 'Leave application submitted successfully!')
            return redirect('leave_application_list')
    else:
        form = LeaveApplicationForm()
    
    context = {
        'page_title': 'Apply for Leave',
        'form': form,
    }
    
    return render(request, 'hr_payroll/leave_form.html', context)


@login_required
def leave_application_approve(request, application_id):
    """Approve leave application"""
    application = get_object_or_404(LeaveApplication, id=application_id)
    
    if application.status not in ['submitted', 'pending_approval']:
        messages.error(request, 'This application cannot be approved.')
        return redirect('leave_application_list')
    
    application.status = 'approved'
    application.approved_date = timezone.now()
    application.save()
    
    # Update leave balance
    balance = EmployeeLeaveBalance.objects.filter(
        employee=application.employee,
        leave_type=application.leave_type,
        year=application.start_date.year
    ).first()
    
    if balance:
        balance.taken_days += application.working_days
        balance.pending_days -= application.working_days
        balance.closing_balance = (
            balance.opening_balance + balance.accrued_days +
            balance.carried_forward_days - balance.taken_days
        )
        balance.save()
    
    messages.success(request, 'Leave application approved!')
    return redirect('leave_application_list')


@login_required
def leave_application_reject(request, application_id):
    """Reject leave application"""
    application = get_object_or_404(LeaveApplication, id=application_id)
    
    if request.method == 'POST':
        reason = request.POST.get('reason')
        
        application.status = 'rejected'
        application.rejected_date = timezone.now()
        application.rejection_reason = reason
        application.save()
        
        # Update pending days in balance
        balance = EmployeeLeaveBalance.objects.filter(
            employee=application.employee,
            leave_type=application.leave_type,
            year=application.start_date.year
        ).first()
        
        if balance:
            balance.pending_days -= application.working_days
            balance.save()
        
        messages.success(request, 'Leave application rejected.')
        return redirect('leave_application_list')
    
    context = {
        'page_title': 'Reject Leave Application',
        'application': application,
    }
    
    return render(request, 'hr_payroll/leave_reject.html', context)


@login_required
def leave_balance_view(request):
    """View leave balances"""
    year = request.GET.get('year', timezone.now().year)
    
    balances = EmployeeLeaveBalance.objects.filter(
        year=year
    ).select_related('employee', 'leave_type').order_by('employee__employee_no', 'leave_type')
    
    # Filter by employee if specified
    employee_id = request.GET.get('employee')
    if employee_id:
        balances = balances.filter(employee_id=employee_id)
    
    context = {
        'page_title': 'Leave Balances',
        'balances': balances,
        'year': year,
        'years': range(timezone.now().year - 2, timezone.now().year + 2),
    }
    
    return render(request, 'hr_payroll/leave_balance.html', context)


# ============================================================================
# PAYROLL VIEWS
# ============================================================================

@login_required
def payroll_period_list(request):
    """List payroll periods"""
    periods = PayrollPeriod.objects.order_by('-start_date')
    
    context = {
        'page_title': 'Payroll Periods',
        'periods': periods,
    }
    
    return render(request, 'hr_payroll/payroll_period_list.html', context)


@login_required
def payroll_period_detail(request, period_id):
    """Payroll period detail"""
    period = get_object_or_404(PayrollPeriod, id=period_id)
    
    calculations = PayrollCalculation.objects.filter(
        payroll_period=period
    ).select_related('employee', 'employee__department').order_by('employee__employee_no')
    
    # Summary
    summary = {
        'employee_count': calculations.count(),
        'total_gross': calculations.aggregate(Sum('gross_pay'))['gross_pay__sum'] or 0,
        'total_deductions': calculations.aggregate(Sum('total_deductions'))['total_deductions__sum'] or 0,
        'total_net': calculations.aggregate(Sum('net_pay'))['net_pay__sum'] or 0,
        'total_tax': calculations.aggregate(Sum('tax_amount'))['tax_amount__sum'] or 0,
    }
    
    context = {
        'page_title': f'Payroll: {period.period_name}',
        'period': period,
        'calculations': calculations,
        'summary': summary,
    }
    
    return render(request, 'hr_payroll/payroll_period_detail.html', context)


@login_required
def payroll_calculation_detail(request, calculation_id):
    """Payroll calculation detail (Payslip view)"""
    calculation = get_object_or_404(
        PayrollCalculation.objects.select_related(
            'employee', 'payroll_period'
        ),
        id=calculation_id
    )
    
    # Get details
    earnings = calculation.details.filter(item_type='earning')
    deductions = calculation.details.filter(item_type='deduction')
    
    context = {
        'page_title': f'Payslip: {calculation.employee.employee_no}',
        'calculation': calculation,
        'earnings': earnings,
        'deductions': deductions,
    }
    
    return render(request, 'hr_payroll/payslip_view.html', context)


# ============================================================================
# REPORT DOWNLOAD VIEWS
# ============================================================================

@login_required
def download_payslip_pdf(request, calculation_id):
    """Download payslip PDF"""
    calculation = get_object_or_404(
        PayrollCalculation.objects.select_related('employee', 'payroll_period').prefetch_related('details'),
        id=calculation_id
    )
    
    generator = PayslipPDFGenerator()
    return generator.generate(calculation)


@login_required
def download_employee_list_excel(request):
    """Download employee list Excel"""
    employees = Employee.objects.select_related('department', 'job_grade')
    
    # Apply filters
    status = request.GET.get('status')
    if status:
        employees = employees.filter(employment_status=status)
    
    generator = EmployeeListExcelGenerator()
    return generator.generate(employees)


@login_required
def download_payroll_register_excel(request, period_id):
    """Download payroll register Excel"""
    period = get_object_or_404(
        PayrollPeriod.objects.prefetch_related('calculations__employee__department'),
        id=period_id
    )
    
    generator = PayrollRegisterExcelGenerator()
    return generator.generate(period)


@login_required
def download_attendance_report_excel(request):
    """Download attendance report Excel"""
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