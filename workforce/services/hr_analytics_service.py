# ============================================================================
# HR ANALYTICS SERVICE
# ============================================================================
"""
Service for HR analytics and reporting.
"""

from django.db.models import Count, Avg, Q, F
from django.db.models.functions import ExtractYear, ExtractMonth, TruncMonth
from django.utils import timezone
from django.core.cache import cache
from typing import Optional, Dict, List, Any
from datetime import timedelta, date
from decimal import Decimal

from workforce.core_models import Employee
from workforce.models import (
    Department, Position, EmployeeLifecycleLog,
    LeaveApplication, AttendanceRecord,
)


class HRAnalyticsService:
    """
    Service for generating HR analytics and dashboards.
    """
    
    CACHE_TIMEOUT = 300  # 5 minutes
    
    def get_headcount_analytics(
        self,
        department: Optional[Department] = None,
        as_of_date: Optional[date] = None,
    ) -> Dict:
        """
        Get headcount analytics.
        
        Args:
            department: Filter by department
            as_of_date: Date for point-in-time analysis (default: today)
            
        Returns:
            Dict with headcount statistics
        """
        if as_of_date is None:
            as_of_date = timezone.now().date()
        
        cache_key = f"hr_analytics_headcount_{department.id if department else 'all'}_{as_of_date}"
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        base_query = Employee.objects.filter(
            hire_date__lte=as_of_date
        ).exclude(
            Q(termination_date__isnull=False, termination_date__lt=as_of_date) |
            Q(resignation_date__isnull=False, resignation_date__lt=as_of_date)
        )
        
        if department:
            base_query = base_query.filter(department=department)
        
        # Total headcount
        total = base_query.count()
        
        # By status
        by_status = base_query.values('employment_status').annotate(
            count=Count('id')
        )
        
        # By category
        by_category = base_query.values('employee_category').annotate(
            count=Count('id')
        )
        
        # By gender
        by_gender = base_query.values('gender').annotate(
            count=Count('id')
        )
        
        # By department
        by_department = base_query.values(
            'department__id', 'department__name'
        ).annotate(count=Count('id')).order_by('-count')[:10]
        
        # New hires this month
        month_start = as_of_date.replace(day=1)
        new_hires = base_query.filter(
            hire_date__gte=month_start,
            hire_date__lte=as_of_date
        ).count()
        
        # Positions analysis
        positions = Position.objects.filter(is_active=True)
        if department:
            positions = positions.filter(department=department)
        
        total_positions = positions.count()
        vacant_positions = positions.filter(
            vacancy_status=Position.VacancyStatus.VACANT
        ).count()
        
        result = {
            'as_of_date': str(as_of_date),
            'total_headcount': total,
            'total_positions': total_positions,
            'vacant_positions': vacant_positions,
            'fill_rate': round((total / total_positions * 100) if total_positions > 0 else 0, 2),
            'new_hires_this_month': new_hires,
            'by_status': {item['employment_status']: item['count'] for item in by_status},
            'by_category': {item['employee_category']: item['count'] for item in by_category},
            'by_gender': {item['gender']: item['count'] for item in by_gender},
            'by_department': list(by_department),
        }
        
        cache.set(cache_key, result, self.CACHE_TIMEOUT)
        return result
    
    def get_turnover_analytics(
        self,
        start_date: date,
        end_date: date,
        department: Optional[Department] = None,
    ) -> Dict:
        """
        Get employee turnover analytics.
        
        Args:
            start_date: Period start
            end_date: Period end
            department: Filter by department
            
        Returns:
            Dict with turnover statistics
        """
        # Base query for employees active at start of period
        active_at_start = Employee.objects.filter(
            hire_date__lte=start_date
        ).exclude(
            Q(termination_date__isnull=False, termination_date__lt=start_date) |
            Q(resignation_date__isnull=False, resignation_date__lt=start_date)
        )
        
        if department:
            active_at_start = active_at_start.filter(department=department)
        
        start_count = active_at_start.count()
        
        # New hires during period
        new_hires = Employee.objects.filter(
            hire_date__gte=start_date,
            hire_date__lte=end_date
        )
        if department:
            new_hires = new_hires.filter(department=department)
        hire_count = new_hires.count()
        
        # Separations during period (resignations + terminations)
        separations = Employee.objects.filter(
            Q(termination_date__gte=start_date, termination_date__lte=end_date) |
            Q(resignation_date__gte=start_date, resignation_date__lte=end_date)
        )
        if department:
            separations = separations.filter(department=department)
        
        separation_count = separations.count()
        
        # Voluntary vs involuntary
        voluntary = separations.filter(resignation_date__isnull=False).count()
        involuntary = separations.filter(termination_date__isnull=False).count()
        
        # End count
        end_count = start_count + hire_count - separation_count
        
        # Average headcount
        avg_headcount = (start_count + end_count) / 2 if (start_count + end_count) > 0 else 1
        
        # Turnover rate
        turnover_rate = (separation_count / avg_headcount) * 100 if avg_headcount > 0 else 0
        
        # Monthly breakdown
        monthly_turnover = []
        current = start_date.replace(day=1)
        while current <= end_date:
            month_end = (current + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            month_separations = separations.filter(
                Q(termination_date__gte=current, termination_date__lte=month_end) |
                Q(resignation_date__gte=current, resignation_date__lte=month_end)
            ).count()
            
            monthly_turnover.append({
                'month': current.strftime('%Y-%m'),
                'separations': month_separations,
            })
            current = (current + timedelta(days=32)).replace(day=1)
        
        # Turnover by reason (from lifecycle logs)
        by_reason = EmployeeLifecycleLog.objects.filter(
            event_type__in=['resigned', 'terminated'],
            event_date__gte=start_date,
            event_date__lte=end_date,
        ).values('event_type').annotate(count=Count('id'))
        
        return {
            'period': {
                'start': str(start_date),
                'end': str(end_date),
            },
            'headcount': {
                'start': start_count,
                'end': end_count,
                'average': round(avg_headcount, 2),
            },
            'new_hires': hire_count,
            'separations': {
                'total': separation_count,
                'voluntary': voluntary,
                'involuntary': involuntary,
            },
            'turnover_rate': round(turnover_rate, 2),
            'monthly_breakdown': monthly_turnover,
            'by_reason': {item['event_type']: item['count'] for item in by_reason},
        }
    
    def get_tenure_analytics(
        self,
        department: Optional[Department] = None,
    ) -> Dict:
        """
        Get employee tenure analytics.
        
        Args:
            department: Filter by department
            
        Returns:
            Dict with tenure statistics
        """
        today = timezone.now().date()
        
        active_employees = Employee.objects.filter(
            employment_status__in=['active', 'probation']
        )
        
        if department:
            active_employees = active_employees.filter(department=department)
        
        # Calculate tenure for each employee
        tenure_data = []
        for emp in active_employees:
            days = (today - emp.hire_date).days
            years = days / 365.25
            tenure_data.append({
                'employee_id': emp.id,
                'tenure_days': days,
                'tenure_years': years,
            })
        
        if not tenure_data:
            return {
                'average_tenure_years': 0,
                'median_tenure_years': 0,
                'distribution': {},
            }
        
        # Calculate statistics
        tenures = [t['tenure_years'] for t in tenure_data]
        avg_tenure = sum(tenures) / len(tenures)
        
        sorted_tenures = sorted(tenures)
        n = len(sorted_tenures)
        if n % 2 == 0:
            median_tenure = (sorted_tenures[n//2 - 1] + sorted_tenures[n//2]) / 2
        else:
            median_tenure = sorted_tenures[n//2]
        
        # Distribution by tenure bands
        bands = {
            'less_than_1_year': 0,
            '1_to_3_years': 0,
            '3_to_5_years': 0,
            '5_to_10_years': 0,
            'more_than_10_years': 0,
        }
        
        for years in tenures:
            if years < 1:
                bands['less_than_1_year'] += 1
            elif years < 3:
                bands['1_to_3_years'] += 1
            elif years < 5:
                bands['3_to_5_years'] += 1
            elif years < 10:
                bands['5_to_10_years'] += 1
            else:
                bands['more_than_10_years'] += 1
        
        return {
            'total_employees': len(tenure_data),
            'average_tenure_years': round(avg_tenure, 2),
            'median_tenure_years': round(median_tenure, 2),
            'min_tenure_years': round(min(tenures), 2),
            'max_tenure_years': round(max(tenures), 2),
            'distribution': bands,
        }
    
    def get_demographics_analytics(
        self,
        department: Optional[Department] = None,
    ) -> Dict:
        """
        Get employee demographics analytics.
        
        Args:
            department: Filter by department
            
        Returns:
            Dict with demographics statistics
        """
        today = timezone.now().date()
        
        active_employees = Employee.objects.filter(
            employment_status__in=['active', 'probation']
        )
        
        if department:
            active_employees = active_employees.filter(department=department)
        
        total = active_employees.count()
        
        # By gender
        by_gender = active_employees.values('gender').annotate(
            count=Count('id')
        )
        
        # Age distribution
        ages = []
        for emp in active_employees.filter(date_of_birth__isnull=False):
            age = (today - emp.date_of_birth).days / 365.25
            ages.append(age)
        
        age_bands = {
            'under_25': 0,
            '25_to_34': 0,
            '35_to_44': 0,
            '45_to_54': 0,
            '55_and_above': 0,
        }
        
        for age in ages:
            if age < 25:
                age_bands['under_25'] += 1
            elif age < 35:
                age_bands['25_to_34'] += 1
            elif age < 45:
                age_bands['35_to_44'] += 1
            elif age < 55:
                age_bands['45_to_54'] += 1
            else:
                age_bands['55_and_above'] += 1
        
        avg_age = sum(ages) / len(ages) if ages else 0
        
        # By employee category
        by_category = active_employees.values('employee_category').annotate(
            count=Count('id')
        )
        
        # By payroll type
        by_payroll_type = active_employees.values('payroll_type').annotate(
            count=Count('id')
        )
        
        return {
            'total_employees': total,
            'gender': {item['gender']: item['count'] for item in by_gender},
            'gender_ratio': {
                item['gender']: round(item['count'] / total * 100, 2) if total > 0 else 0
                for item in by_gender
            },
            'age': {
                'average': round(avg_age, 1),
                'distribution': age_bands,
            },
            'category': {item['employee_category']: item['count'] for item in by_category},
            'payroll_type': {item['payroll_type']: item['count'] for item in by_payroll_type},
        }
    
    def get_probation_analytics(self) -> Dict:
        """
        Get probation status analytics.
        
        Returns:
            Dict with probation statistics
        """
        today = timezone.now().date()
        
        on_probation = Employee.objects.filter(
            employment_status='probation'
        )
        
        # Probation ending soon (next 30 days)
        threshold = today + timedelta(days=30)
        ending_soon = on_probation.filter(
            probation_end_date__isnull=False,
            probation_end_date__lte=threshold,
            probation_end_date__gte=today,
        )
        
        # Overdue probations
        overdue = on_probation.filter(
            probation_end_date__isnull=False,
            probation_end_date__lt=today,
        )
        
        # Recent confirmations (last 30 days)
        month_ago = today - timedelta(days=30)
        recent_confirmations = Employee.objects.filter(
            confirmation_date__gte=month_ago,
            confirmation_date__lte=today,
        ).count()
        
        # By department
        by_department = on_probation.values(
            'department__name'
        ).annotate(count=Count('id')).order_by('-count')
        
        return {
            'total_on_probation': on_probation.count(),
            'ending_in_30_days': ending_soon.count(),
            'overdue': overdue.count(),
            'recent_confirmations': recent_confirmations,
            'by_department': list(by_department),
            'ending_soon_list': list(ending_soon.values(
                'id', 'employee_no', 'first_name', 'last_name',
                'probation_end_date', 'department__name'
            )[:10]),
        }
    
    def get_contract_analytics(self) -> Dict:
        """
        Get contract employee analytics.
        
        Returns:
            Dict with contract statistics
        """
        today = timezone.now().date()
        
        contract_employees = Employee.objects.filter(
            employee_category='contract',
            employment_status__in=['active', 'probation'],
        )
        
        # Expiring soon (next 60 days)
        threshold = today + timedelta(days=60)
        expiring_soon = contract_employees.filter(
            contract_end_date__isnull=False,
            contract_end_date__lte=threshold,
            contract_end_date__gte=today,
        )
        
        # Expired
        expired = contract_employees.filter(
            contract_end_date__isnull=False,
            contract_end_date__lt=today,
        )
        
        return {
            'total_contracts': contract_employees.count(),
            'expiring_in_60_days': expiring_soon.count(),
            'expired': expired.count(),
            'expiring_soon_list': list(expiring_soon.values(
                'id', 'employee_no', 'first_name', 'last_name',
                'contract_end_date', 'department__name'
            )[:10]),
        }
    
    def get_dashboard_summary(self) -> Dict:
        """
        Get comprehensive HR dashboard summary.
        
        Returns:
            Dict with all key metrics
        """
        today = timezone.now().date()
        month_start = today.replace(day=1)
        year_start = today.replace(month=1, day=1)
        
        return {
            'generated_at': timezone.now().isoformat(),
            'headcount': self.get_headcount_analytics(),
            'turnover': self.get_turnover_analytics(year_start, today),
            'tenure': self.get_tenure_analytics(),
            'demographics': self.get_demographics_analytics(),
            'probation': self.get_probation_analytics(),
            'contracts': self.get_contract_analytics(),
        }
