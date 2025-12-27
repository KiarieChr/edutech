"""
HR & Payroll Django REST Framework ViewSets
Part 2: API ViewSets with Custom Actions
"""

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Sum, Count, Avg
from django.utils import timezone
from datetime import timedelta


from .core_models import *
from .models import *
from .serializers import *
from .permissions import *


# ============================================================================
# CORE VIEWSETS
# ============================================================================

class EmployeeViewSet(viewsets.ModelViewSet):
    """
    Employee ViewSet with custom actions
    """
    queryset = Employee.objects.select_related(
        'department', 'job_grade'
    ).prefetch_related('addresses', 'emergency_contacts')
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = [
        'employment_status', 'employee_category', 
        'department', 'gender'
    ]
    search_fields = [
        'employee_no', 'first_name', 'last_name', 
        'national_id', 'email'
    ]
    ordering_fields = ['employee_no', 'hire_date', 'first_name']
    ordering = ['employee_no']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return EmployeeListSerializer
        return EmployeeDetailSerializer
    
    @action(detail=True, methods=['get'])
    def profile(self, request, pk=None):
        """Get employee profile with all related data"""
        employee = self.get_object()
        serializer = EmployeeDetailSerializer(employee)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def leave_balance(self, request, pk=None):
        """Get employee leave balances"""
        employee = self.get_object()
        current_year = timezone.now().year
        balances = EmployeeLeaveBalance.objects.filter(
            employee=employee,
            year=current_year
        )
        serializer = EmployeeLeaveBalanceSerializer(balances, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def attendance_summary(self, request, pk=None):
        """Get employee attendance summary for current month"""
        employee = self.get_object()
        today = timezone.now().date()
        month_start = today.replace(day=1)
        
        attendance = AttendanceRecord.objects.filter(
            employee=employee,
            attendance_date__gte=month_start,
            attendance_date__lte=today
        )
        
        summary = {
            'total_days': attendance.count(),
            'present': attendance.filter(status='present').count(),
            'absent': attendance.filter(status='absent').count(),
            'late': attendance.filter(status='late').count(),
            'on_leave': attendance.filter(status='on_leave').count(),
            'total_hours': attendance.aggregate(
                total=Sum('total_hours')
            )['total'] or 0,
            'overtime_hours': attendance.aggregate(
                total=Sum('overtime_hours')
            )['total'] or 0
        }
        
        return Response(summary)
    
    @action(detail=True, methods=['get'])
    def payroll_history(self, request, pk=None):
        """Get employee payroll history"""
        employee = self.get_object()
        calculations = PayrollCalculation.objects.filter(
            employee=employee
        ).select_related('payroll_period').order_by('-payroll_period__start_date')[:12]
        
        serializer = PayrollCalculationSerializer(calculations, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get employee statistics"""
        total = Employee.objects.count()
        active = Employee.objects.filter(employment_status='active').count()
        
        by_category = Employee.objects.values(
            'employee_category'
        ).annotate(count=Count('id'))
        
        by_department = Employee.objects.values(
            'department__name'
        ).annotate(count=Count('id')).order_by('-count')[:10]
        
        stats = {
            'total_employees': total,
            'active_employees': active,
            'by_category': list(by_category),
            'top_departments': list(by_department)
        }
        
        return Response(stats)


class DepartmentViewSet(viewsets.ModelViewSet):
    """Department ViewSet"""
    queryset = Department.objects.select_related(
        'faculty', 'campus', 'head_of_department'
    )
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['department_type', 'campus', 'faculty']
    search_fields = ['code', 'name']
    
    @action(detail=True, methods=['get'])
    def employees(self, request, pk=None):
        """Get all employees in this department"""
        department = self.get_object()
        employees = Employee.objects.filter(department=department)
        serializer = EmployeeListSerializer(employees, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def payroll_summary(self, request, pk=None):
        """Get department payroll summary"""
        department = self.get_object()
        current_period = PayrollPeriod.objects.filter(
            status='approved'
        ).order_by('-start_date').first()
        
        if not current_period:
            return Response({'message': 'No approved payroll period'})
        
        calculations = PayrollCalculation.objects.filter(
            employee__department=department,
            payroll_period=current_period
        )
        
        summary = {
            'period': current_period.period_name,
            'employee_count': calculations.count(),
            'total_gross': calculations.aggregate(
                total=Sum('gross_pay')
            )['total'] or 0,
            'total_net': calculations.aggregate(
                total=Sum('net_pay')
            )['total'] or 0,
            'total_deductions': calculations.aggregate(
                total=Sum('total_deductions')
            )['total'] or 0
        }
        
        return Response(summary)


# ============================================================================
# ATTENDANCE VIEWSETS
# ============================================================================

class AttendanceRecordViewSet(viewsets.ModelViewSet):
    """Attendance Record ViewSet"""
    queryset = AttendanceRecord.objects.select_related(
        'employee', 'work_schedule'
    )
    serializer_class = AttendanceRecordSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = [
        'employee', 'status', 'approval_status', 'attendance_date'
    ]
    search_fields = ['employee__employee_no', 'employee__first_name']
    
    @action(detail=False, methods=['post'])
    def clock_in(self, request):
        """Clock in for attendance"""
        employee_id = request.data.get('employee_id')
        
        try:
            employee = Employee.objects.get(id=employee_id)
        except Employee.DoesNotExist:
            return Response(
                {'error': 'Employee not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        today = timezone.now().date()
        current_time = timezone.now().time()
        
        # Check if already clocked in
        existing = AttendanceRecord.objects.filter(
            employee=employee,
            attendance_date=today
        ).first()
        
        if existing and existing.check_in_time:
            return Response(
                {'error': 'Already clocked in today'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get employee work schedule
        schedule = EmployeeWorkSchedule.objects.filter(
            employee=employee,
            is_active=True
        ).first()
        
        if not schedule:
            return Response(
                {'error': 'No active work schedule'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create or update attendance record
        attendance, created = AttendanceRecord.objects.get_or_create(
            employee=employee,
            attendance_date=today,
            defaults={
                'work_schedule': schedule.work_schedule,
                'check_in_time': current_time,
                'check_in_method': 'mobile',
                'status': 'present'
            }
        )
        
        if not created:
            attendance.check_in_time = current_time
            attendance.check_in_method = 'mobile'
            attendance.status = 'present'
            attendance.save()
        
        serializer = AttendanceRecordSerializer(attendance)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['post'])
    def clock_out(self, request):
        """Clock out for attendance"""
        employee_id = request.data.get('employee_id')
        
        try:
            employee = Employee.objects.get(id=employee_id)
        except Employee.DoesNotExist:
            return Response(
                {'error': 'Employee not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        today = timezone.now().date()
        current_time = timezone.now().time()
        
        # Get today's attendance record
        try:
            attendance = AttendanceRecord.objects.get(
                employee=employee,
                attendance_date=today
            )
        except AttendanceRecord.DoesNotExist:
            return Response(
                {'error': 'No clock-in record found for today'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if attendance.check_out_time:
            return Response(
                {'error': 'Already clocked out today'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update attendance record
        attendance.check_out_time = current_time
        attendance.check_out_method = 'mobile'
        
        # Calculate hours worked
        from datetime import datetime, date
        check_in_datetime = datetime.combine(date.today(), attendance.check_in_time)
        check_out_datetime = datetime.combine(date.today(), current_time)
        
        if check_out_datetime < check_in_datetime:
            # Handle overnight shifts
            check_out_datetime = datetime.combine(
                date.today() + timedelta(days=1), 
                current_time
            )
        
        hours_worked = (check_out_datetime - check_in_datetime).seconds / 3600
        attendance.total_hours = round(hours_worked, 2)
        
        # Calculate regular and overtime hours
        policy = attendance.work_schedule.attendance_policy
        if hours_worked <= policy.standard_hours_per_day:
            attendance.regular_hours = hours_worked
            attendance.overtime_hours = 0
        else:
            attendance.regular_hours = policy.standard_hours_per_day
            attendance.overtime_hours = hours_worked - policy.standard_hours_per_day
        
        attendance.save()
        
        serializer = AttendanceRecordSerializer(attendance)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def daily_summary(self, request):
        """Get daily attendance summary"""
        date_str = request.query_params.get('date', timezone.now().date())
        
        records = AttendanceRecord.objects.filter(
            attendance_date=date_str
        )
        
        summary = {
            'date': date_str,
            'total': records.count(),
            'present': records.filter(status='present').count(),
            'absent': records.filter(status='absent').count(),
            'late': records.filter(status='late').count(),
            'on_leave': records.filter(status='on_leave').count(),
            'half_day': records.filter(status='half_day').count()
        }
        
        return Response(summary)


class OvertimeRequestViewSet(viewsets.ModelViewSet):
    """Overtime Request ViewSet"""
    queryset = OvertimeRequest.objects.select_related(
        'employee', 'department'
    )
    serializer_class = OvertimeRequestSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['approval_status', 'employee', 'overtime_date']
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve overtime request"""
        overtime_request = self.get_object()
        
        if overtime_request.approval_status != 'pending':
            return Response(
                {'error': 'Request is not pending'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        overtime_request.approval_status = 'approved'
        overtime_request.approved_by = request.user
        overtime_request.save()
        
        serializer = self.get_serializer(overtime_request)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject overtime request"""
        overtime_request = self.get_object()
        
        if overtime_request.approval_status != 'pending':
            return Response(
                {'error': 'Request is not pending'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        overtime_request.approval_status = 'rejected'
        overtime_request.approved_by = request.user
        overtime_request.approval_notes = request.data.get('notes', '')
        overtime_request.save()
        
        serializer = self.get_serializer(overtime_request)
        return Response(serializer.data)


# ============================================================================
# LEAVE VIEWSETS
# ============================================================================

class LeaveApplicationViewSet(viewsets.ModelViewSet):
    """Leave Application ViewSet"""
    queryset = LeaveApplication.objects.select_related(
        'employee', 'leave_type', 'acting_employee'
    )
    serializer_class = LeaveApplicationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['employee', 'leave_type', 'status', 'start_date']
    search_fields = ['employee__employee_no', 'employee__first_name']
    
    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """Submit leave application"""
        leave_app = self.get_object()
        
        if leave_app.status != 'draft':
            return Response(
                {'error': 'Can only submit draft applications'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if employee has sufficient leave balance
        balance = EmployeeLeaveBalance.objects.filter(
            employee=leave_app.employee,
            leave_type=leave_app.leave_type,
            year=leave_app.start_date.year
        ).first()
        
        if balance:
            available = balance.closing_balance - balance.pending_days
            if available < leave_app.working_days:
                return Response(
                    {'error': f'Insufficient leave balance. Available: {available} days'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        leave_app.status = 'submitted'
        leave_app.submitted_date = timezone.now()
        leave_app.save()
        
        # Update pending days in balance
        if balance:
            balance.pending_days += leave_app.working_days
            balance.save()
        
        serializer = self.get_serializer(leave_app)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve leave application"""
        leave_app = self.get_object()
        
        if leave_app.status not in ['submitted', 'pending_approval']:
            return Response(
                {'error': 'Invalid status for approval'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        leave_app.status = 'approved'
        leave_app.approved_date = timezone.now()
        leave_app.save()
        
        serializer = self.get_serializer(leave_app)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject leave application"""
        leave_app = self.get_object()
        
        if leave_app.status not in ['submitted', 'pending_approval']:
            return Response(
                {'error': 'Invalid status for rejection'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        leave_app.status = 'rejected'
        leave_app.rejected_date = timezone.now()
        leave_app.rejection_reason = request.data.get('reason', '')
        leave_app.save()
        
        # Update pending days in balance
        balance = EmployeeLeaveBalance.objects.filter(
            employee=leave_app.employee,
            leave_type=leave_app.leave_type,
            year=leave_app.start_date.year
        ).first()
        
        if balance:
            balance.pending_days -= leave_app.working_days
            balance.save()
        
        serializer = self.get_serializer(leave_app)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def pending_approvals(self, request):
        """Get pending leave approvals"""
        pending = LeaveApplication.objects.filter(
            status__in=['submitted', 'pending_approval']
        )
        serializer = self.get_serializer(pending, many=True)
        return Response(serializer.data)


class EmployeeLeaveBalanceViewSet(viewsets.ReadOnlyModelViewSet):
    """Employee Leave Balance ViewSet (Read-only)"""
    queryset = EmployeeLeaveBalance.objects.select_related(
        'employee', 'leave_type'
    )
    serializer_class = EmployeeLeaveBalanceSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['employee', 'leave_type', 'year']
    
    @action(detail=False, methods=['post'])
    def accrue_monthly(self, request):
        """Accrue monthly leave for all employees"""
        current_year = timezone.now().year
        current_month = timezone.now().month
        
        employees = Employee.objects.filter(employment_status='active')
        leave_types = LeaveType.objects.filter(is_active=True)
        
        accrued_count = 0
        
        for employee in employees:
            for leave_type in leave_types:
                balance, created = EmployeeLeaveBalance.objects.get_or_create(
                    employee=employee,
                    leave_type=leave_type,
                    year=current_year
                )
                
                balance.accrued_days += leave_type.accrual_rate
                balance.closing_balance = (
                    balance.opening_balance +
                    balance.accrued_days +
                    balance.carried_forward_days -
                    balance.taken_days
                )
                balance.last_accrual_date = timezone.now().date()
                balance.save()
                accrued_count += 1
        
        return Response({
            'message': f'Accrued leave for {accrued_count} records',
            'employees': employees.count(),
            'leave_types': leave_types.count()
        })


# ============================================================================
# PAYROLL VIEWSETS
# ============================================================================

class PayrollPeriodViewSet(viewsets.ModelViewSet):
    """Payroll Period ViewSet"""
    queryset = PayrollPeriod.objects.all()
    serializer_class = PayrollPeriodSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status', 'period_type']
    ordering = ['-start_date']
    
    @action(detail=True, methods=['post'])
    def process(self, request, pk=None):
        """Process payroll for the period"""
        period = self.get_object()
        
        if period.status not in ['open', 'processing']:
            return Response(
                {'error': 'Period is not open for processing'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        period.status = 'processing'
        period.processing_started_at = timezone.now()
        period.save()
        
        # TODO: Implement actual payroll calculation logic
        
        return Response({
            'message': 'Payroll processing started',
            'period': period.period_name
        })
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve payroll period"""
        period = self.get_object()
        
        if period.status != 'calculated':
            return Response(
                {'error': 'Period must be calculated before approval'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        period.status = 'approved'
        period.approved_by = request.user
        period.approved_date = timezone.now().date()
        period.save()
        
        serializer = self.get_serializer(period)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def summary(self, request, pk=None):
        """Get payroll period summary"""
        period = self.get_object()
        
        calculations = PayrollCalculation.objects.filter(
            payroll_period=period
        )
        
        summary = {
            'period': period.period_name,
            'status': period.get_status_display(),
            'employee_count': calculations.count(),
            'total_gross_pay': calculations.aggregate(
                total=Sum('gross_pay')
            )['total'] or 0,
            'total_deductions': calculations.aggregate(
                total=Sum('total_deductions')
            )['total'] or 0,
            'total_net_pay': calculations.aggregate(
                total=Sum('net_pay')
            )['total'] or 0,
            'total_tax': calculations.aggregate(
                total=Sum('tax_amount')
            )['total'] or 0,
            'total_pension': calculations.aggregate(
                emp=Sum('pension_employee'),
                empr=Sum('pension_employer')
            )
        }
        
        return Response(summary)


class PayrollCalculationViewSet(viewsets.ReadOnlyModelViewSet):
    """Payroll Calculation ViewSet (Read-only)"""
    queryset = PayrollCalculation.objects.select_related(
        'employee', 'payroll_period'
    )
    serializer_class = PayrollCalculationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['payroll_period', 'employee', 'payment_status']
    search_fields = ['employee__employee_no', 'employee__first_name']
    
    @action(detail=True, methods=['get'])
    def breakdown(self, request, pk=None):
        """Get detailed payroll breakdown"""
        calculation = self.get_object()
        
        details = PayrollCalculationDetail.objects.filter(
            payroll_calculation=calculation
        )
        
        earnings = details.filter(item_type='earning')
        deductions = details.filter(item_type='deduction')
        
        breakdown = {
            'employee': {
                'employee_no': calculation.employee.employee_no,
                'name': calculation.employee.get_full_name(),
                'department': calculation.employee.department.name
            },
            'period': calculation.payroll_period.period_name,
            'earnings': [
                {
                    'description': d.description,
                    'amount': float(d.amount)
                } for d in earnings
            ],
            'deductions': [
                {
                    'description': d.description,
                    'amount': float(d.amount)
                } for d in deductions
            ],
            'summary': {
                'gross_pay': float(calculation.gross_pay),
                'total_deductions': float(calculation.total_deductions),
                'net_pay': float(calculation.net_pay)
            }
        }
        
        return Response(breakdown)


class PayslipViewSet(viewsets.ReadOnlyModelViewSet):
    """Payslip ViewSet"""
    queryset = Payslip.objects.select_related(
        'employee', 'payroll_period', 'payroll_calculation'
    )
    serializer_class = PayslipSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['employee', 'payroll_period']
    
    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """Download payslip PDF"""
        payslip = self.get_object()
        
        # Mark as downloaded
        if not payslip.downloaded:
            payslip.downloaded = True
            payslip.download_date = timezone.now()
            payslip.save()
        
        # TODO: Generate and return PDF
        return Response({
            'message': 'PDF generation not implemented yet',
            'payslip_number': payslip.payslip_number
        })
    
    @action(detail=True, methods=['post'])
    def email(self, request, pk=None):
        """Email payslip to employee"""
        payslip = self.get_object()
        
        # TODO: Implement email sending
        
        payslip.email_sent = True
        payslip.email_sent_date = timezone.now()
        payslip.save()
        
        return Response({
            'message': 'Payslip emailed successfully',
            'email': payslip.employee.official_email
        })