# ============================================================================
# EMPLOYEE LIFECYCLE SERVICE
# ============================================================================
"""
Handles all employee state transitions with validation and logging.
Implements a state machine for employee lifecycle management.
"""

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from typing import Optional, Dict, Any
from decimal import Decimal

from workforce.core_models import Employee
from workforce.models import (
    EmployeeLifecycleLog, 
    Position, 
    Department,
    JobGrade,
    EmployeeJobAssignment,
)


class EmployeeLifecycleService:
    """
    Service class for managing employee lifecycle transitions.
    All state changes go through this service for consistency and audit logging.
    """
    
    # Valid state transitions
    VALID_TRANSITIONS = {
        'probation': ['active', 'terminated', 'resigned'],
        'active': ['suspended', 'resigned', 'terminated', 'retired'],
        'suspended': ['active', 'terminated', 'resigned'],
        'resigned': [],  # Terminal state
        'terminated': [],  # Terminal state
        'retired': [],  # Terminal state
    }
    
    def __init__(self, initiated_by_user):
        """
        Initialize the service with the user performing the action.
        
        Args:
            initiated_by_user: The User instance performing the lifecycle action
        """
        self.initiated_by = initiated_by_user
    
    def _validate_transition(self, employee: Employee, new_status: str) -> bool:
        """
        Validate if the status transition is allowed.
        
        Args:
            employee: The employee instance
            new_status: The target status
            
        Returns:
            bool: True if transition is valid
            
        Raises:
            ValidationError: If transition is not allowed
        """
        current_status = employee.employment_status
        allowed_transitions = self.VALID_TRANSITIONS.get(current_status, [])
        
        if new_status not in allowed_transitions:
            raise ValidationError(
                f"Cannot transition from '{current_status}' to '{new_status}'. "
                f"Allowed transitions: {allowed_transitions}"
            )
        return True
    
    def _create_lifecycle_log(
        self,
        employee: Employee,
        event_type: str,
        effective_date,
        reason: str,
        old_status: str = '',
        new_status: str = '',
        old_department: Optional[Department] = None,
        new_department: Optional[Department] = None,
        old_position: Optional[Position] = None,
        new_position: Optional[Position] = None,
        old_job_grade: Optional[JobGrade] = None,
        new_job_grade: Optional[JobGrade] = None,
        old_salary: Optional[Decimal] = None,
        new_salary: Optional[Decimal] = None,
        reference_number: str = '',
        metadata: Optional[Dict] = None,
        approved_by=None,
    ) -> EmployeeLifecycleLog:
        """
        Create a lifecycle log entry.
        """
        return EmployeeLifecycleLog.objects.create(
            employee=employee,
            event_type=event_type,
            event_date=timezone.now().date(),
            effective_date=effective_date,
            old_status=old_status,
            new_status=new_status,
            old_department=old_department,
            new_department=new_department,
            old_position=old_position,
            new_position=new_position,
            old_job_grade=old_job_grade,
            new_job_grade=new_job_grade,
            old_salary=old_salary,
            new_salary=new_salary,
            reason=reason,
            reference_number=reference_number,
            initiated_by=self.initiated_by,
            approved_by=approved_by,
            approval_date=timezone.now() if approved_by else None,
            metadata=metadata or {},
        )
    
    @transaction.atomic
    def hire_employee(
        self,
        employee: Employee,
        position: Position,
        effective_date,
        salary: Decimal,
        reason: str = "New hire",
        approved_by=None,
    ) -> EmployeeLifecycleLog:
        """
        Record hiring of a new employee.
        
        Args:
            employee: The newly created employee
            position: The position being filled
            effective_date: Start date
            salary: Starting salary
            reason: Hiring reason/notes
            approved_by: User who approved the hire
            
        Returns:
            EmployeeLifecycleLog: The created log entry
        """
        # Update position
        position.assign_employee(employee)
        
        # Update employee
        employee.hire_date = effective_date
        employee.employment_status = Employee.EmploymentStatus.PROBATION
        employee.save()
        
        # Create log
        return self._create_lifecycle_log(
            employee=employee,
            event_type=EmployeeLifecycleLog.EventType.HIRED,
            effective_date=effective_date,
            reason=reason,
            new_status=employee.employment_status,
            new_department=position.department,
            new_position=position,
            new_salary=salary,
            approved_by=approved_by,
            metadata={
                'position_code': position.position_code,
                'hire_type': 'new_hire',
            }
        )
    
    @transaction.atomic
    def confirm_probation(
        self,
        employee: Employee,
        confirmation_date,
        remarks: str,
        approved_by=None,
    ) -> EmployeeLifecycleLog:
        """
        Confirm an employee after successful probation.
        
        Args:
            employee: The employee to confirm
            confirmation_date: Date of confirmation
            remarks: Confirmation notes
            approved_by: User who approved
            
        Returns:
            EmployeeLifecycleLog: The created log entry
        """
        if employee.employment_status != Employee.EmploymentStatus.PROBATION:
            raise ValidationError(
                f"Employee {employee.employee_no} is not on probation"
            )
        
        old_status = employee.employment_status
        employee.employment_status = Employee.EmploymentStatus.ACTIVE
        employee.confirmation_date = confirmation_date
        employee.save()
        
        return self._create_lifecycle_log(
            employee=employee,
            event_type=EmployeeLifecycleLog.EventType.PROBATION_CONFIRMED,
            effective_date=confirmation_date,
            reason=remarks,
            old_status=old_status,
            new_status=employee.employment_status,
            approved_by=approved_by,
        )
    
    @transaction.atomic
    def extend_probation(
        self,
        employee: Employee,
        new_end_date,
        extension_months: int,
        reason: str,
        approved_by=None,
    ) -> EmployeeLifecycleLog:
        """
        Extend an employee's probation period.
        """
        if employee.employment_status != Employee.EmploymentStatus.PROBATION:
            raise ValidationError(
                f"Employee {employee.employee_no} is not on probation"
            )
        
        old_end_date = employee.probation_end_date
        employee.probation_end_date = new_end_date
        employee.probation_period_months += extension_months
        employee.save()
        
        return self._create_lifecycle_log(
            employee=employee,
            event_type=EmployeeLifecycleLog.EventType.PROBATION_EXTENDED,
            effective_date=timezone.now().date(),
            reason=reason,
            old_status=employee.employment_status,
            new_status=employee.employment_status,
            approved_by=approved_by,
            metadata={
                'old_end_date': str(old_end_date) if old_end_date else None,
                'new_end_date': str(new_end_date),
                'extension_months': extension_months,
            }
        )
    
    @transaction.atomic
    def promote(
        self,
        employee: Employee,
        new_position: Position,
        new_salary: Decimal,
        effective_date,
        reason: str,
        approved_by=None,
    ) -> EmployeeLifecycleLog:
        """
        Promote an employee to a new position.
        
        Args:
            employee: The employee to promote
            new_position: The new position
            new_salary: New salary
            effective_date: Promotion effective date
            reason: Promotion reason
            approved_by: User who approved
            
        Returns:
            EmployeeLifecycleLog: The created log entry
        """
        # Get current position
        current_positions = employee.held_positions.filter(
            vacancy_status=Position.VacancyStatus.OCCUPIED
        )
        old_position = current_positions.first()
        old_job_grade = employee.job_grade
        old_department = employee.department
        
        # Estimate old salary from pay profile
        current_pay = employee.pay_profiles.filter(is_active=True).first()
        old_salary = current_pay.basic_salary if current_pay else None
        
        # Vacate old position
        if old_position:
            old_position.vacate()
        
        # Assign new position
        new_position.assign_employee(employee)
        
        # Update employee
        employee.department = new_position.department
        employee.job_grade = new_position.job_title.job_grade
        employee.last_promotion_date = effective_date
        employee.save()
        
        return self._create_lifecycle_log(
            employee=employee,
            event_type=EmployeeLifecycleLog.EventType.PROMOTION,
            effective_date=effective_date,
            reason=reason,
            old_status=employee.employment_status,
            new_status=employee.employment_status,
            old_department=old_department,
            new_department=new_position.department,
            old_position=old_position,
            new_position=new_position,
            old_job_grade=old_job_grade,
            new_job_grade=new_position.job_title.job_grade,
            old_salary=old_salary,
            new_salary=new_salary,
            approved_by=approved_by,
            metadata={
                'promotion_type': 'standard',
            }
        )
    
    @transaction.atomic
    def transfer(
        self,
        employee: Employee,
        new_department: Department,
        new_position: Optional[Position],
        effective_date,
        reason: str,
        approved_by=None,
    ) -> EmployeeLifecycleLog:
        """
        Transfer an employee to a new department.
        """
        old_department = employee.department
        old_positions = employee.held_positions.filter(
            vacancy_status=Position.VacancyStatus.OCCUPIED
        )
        old_position = old_positions.first()
        
        # Vacate old position
        if old_position:
            old_position.vacate()
        
        # Assign new position if provided
        if new_position:
            new_position.assign_employee(employee)
        
        # Update employee
        employee.department = new_department
        employee.save()
        
        return self._create_lifecycle_log(
            employee=employee,
            event_type=EmployeeLifecycleLog.EventType.TRANSFER,
            effective_date=effective_date,
            reason=reason,
            old_status=employee.employment_status,
            new_status=employee.employment_status,
            old_department=old_department,
            new_department=new_department,
            old_position=old_position,
            new_position=new_position,
            approved_by=approved_by,
        )
    
    @transaction.atomic
    def suspend(
        self,
        employee: Employee,
        effective_date,
        reason: str,
        reference_number: str = '',
        approved_by=None,
    ) -> EmployeeLifecycleLog:
        """
        Suspend an employee.
        """
        self._validate_transition(employee, Employee.EmploymentStatus.SUSPENDED)
        
        old_status = employee.employment_status
        employee.employment_status = Employee.EmploymentStatus.SUSPENDED
        employee.save()
        
        return self._create_lifecycle_log(
            employee=employee,
            event_type=EmployeeLifecycleLog.EventType.SUSPENDED,
            effective_date=effective_date,
            reason=reason,
            old_status=old_status,
            new_status=employee.employment_status,
            reference_number=reference_number,
            approved_by=approved_by,
        )
    
    @transaction.atomic
    def reinstate(
        self,
        employee: Employee,
        effective_date,
        reason: str,
        position: Optional[Position] = None,
        approved_by=None,
    ) -> EmployeeLifecycleLog:
        """
        Reinstate a suspended employee.
        """
        if employee.employment_status != Employee.EmploymentStatus.SUSPENDED:
            raise ValidationError(
                f"Employee {employee.employee_no} is not suspended"
            )
        
        old_status = employee.employment_status
        employee.employment_status = Employee.EmploymentStatus.ACTIVE
        employee.save()
        
        # Reassign position if provided
        if position:
            position.assign_employee(employee)
        
        return self._create_lifecycle_log(
            employee=employee,
            event_type=EmployeeLifecycleLog.EventType.REINSTATED,
            effective_date=effective_date,
            reason=reason,
            old_status=old_status,
            new_status=employee.employment_status,
            new_position=position,
            approved_by=approved_by,
        )
    
    @transaction.atomic
    def resign(
        self,
        employee: Employee,
        resignation_date,
        last_working_day,
        reason: str,
        approved_by=None,
    ) -> EmployeeLifecycleLog:
        """
        Record employee resignation.
        """
        self._validate_transition(employee, Employee.EmploymentStatus.RESIGNED)
        
        old_status = employee.employment_status
        
        # Vacate position
        for position in employee.held_positions.filter(
            vacancy_status=Position.VacancyStatus.OCCUPIED
        ):
            position.vacate()
        
        # Update employee
        employee.employment_status = Employee.EmploymentStatus.RESIGNED
        employee.resignation_date = resignation_date
        employee.resignation_reason = reason
        employee.last_working_day = last_working_day
        employee.save()
        
        return self._create_lifecycle_log(
            employee=employee,
            event_type=EmployeeLifecycleLog.EventType.RESIGNED,
            effective_date=last_working_day,
            reason=reason,
            old_status=old_status,
            new_status=employee.employment_status,
            approved_by=approved_by,
            metadata={
                'resignation_date': str(resignation_date),
                'last_working_day': str(last_working_day),
            }
        )
    
    @transaction.atomic
    def terminate(
        self,
        employee: Employee,
        termination_date,
        reason: str,
        reference_number: str = '',
        approved_by=None,
    ) -> EmployeeLifecycleLog:
        """
        Terminate an employee.
        """
        self._validate_transition(employee, Employee.EmploymentStatus.TERMINATED)
        
        old_status = employee.employment_status
        
        # Vacate position
        for position in employee.held_positions.filter(
            vacancy_status=Position.VacancyStatus.OCCUPIED
        ):
            position.vacate()
        
        # Update employee
        employee.employment_status = Employee.EmploymentStatus.TERMINATED
        employee.termination_date = termination_date
        employee.termination_reason = reason
        employee.last_working_day = termination_date
        employee.save()
        
        return self._create_lifecycle_log(
            employee=employee,
            event_type=EmployeeLifecycleLog.EventType.TERMINATED,
            effective_date=termination_date,
            reason=reason,
            old_status=old_status,
            new_status=employee.employment_status,
            reference_number=reference_number,
            approved_by=approved_by,
        )
    
    @transaction.atomic
    def retire(
        self,
        employee: Employee,
        retirement_date,
        reason: str = "Retirement",
        approved_by=None,
    ) -> EmployeeLifecycleLog:
        """
        Record employee retirement.
        """
        self._validate_transition(employee, Employee.EmploymentStatus.RETIRED)
        
        old_status = employee.employment_status
        
        # Vacate position
        for position in employee.held_positions.filter(
            vacancy_status=Position.VacancyStatus.OCCUPIED
        ):
            position.vacate()
        
        # Update employee
        employee.employment_status = Employee.EmploymentStatus.RETIRED
        employee.last_working_day = retirement_date
        employee.save()
        
        return self._create_lifecycle_log(
            employee=employee,
            event_type=EmployeeLifecycleLog.EventType.RETIRED,
            effective_date=retirement_date,
            reason=reason,
            old_status=old_status,
            new_status=employee.employment_status,
            approved_by=approved_by,
        )
    
    @transaction.atomic
    def change_salary(
        self,
        employee: Employee,
        new_salary: Decimal,
        effective_date,
        reason: str,
        approved_by=None,
    ) -> EmployeeLifecycleLog:
        """
        Record a salary change.
        """
        current_pay = employee.pay_profiles.filter(is_active=True).first()
        old_salary = current_pay.basic_salary if current_pay else None
        
        return self._create_lifecycle_log(
            employee=employee,
            event_type=EmployeeLifecycleLog.EventType.SALARY_CHANGE,
            effective_date=effective_date,
            reason=reason,
            old_status=employee.employment_status,
            new_status=employee.employment_status,
            old_salary=old_salary,
            new_salary=new_salary,
            approved_by=approved_by,
        )
    
    @transaction.atomic
    def renew_contract(
        self,
        employee: Employee,
        new_start_date,
        new_end_date,
        reason: str,
        approved_by=None,
    ) -> EmployeeLifecycleLog:
        """
        Renew a contract employee's contract.
        """
        old_end_date = employee.contract_end_date
        
        employee.contract_start_date = new_start_date
        employee.contract_end_date = new_end_date
        employee.contract_renewal_count += 1
        employee.save()
        
        return self._create_lifecycle_log(
            employee=employee,
            event_type=EmployeeLifecycleLog.EventType.CONTRACT_RENEWED,
            effective_date=new_start_date,
            reason=reason,
            old_status=employee.employment_status,
            new_status=employee.employment_status,
            approved_by=approved_by,
            metadata={
                'old_end_date': str(old_end_date) if old_end_date else None,
                'new_start_date': str(new_start_date),
                'new_end_date': str(new_end_date),
                'renewal_count': employee.contract_renewal_count,
            }
        )
    
    def get_lifecycle_history(self, employee: Employee):
        """
        Get complete lifecycle history for an employee.
        
        Args:
            employee: The employee instance
            
        Returns:
            QuerySet of EmployeeLifecycleLog
        """
        return EmployeeLifecycleLog.objects.filter(
            employee=employee
        ).order_by('-event_date', '-created_at')
