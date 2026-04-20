# ============================================================================
# POSITION SERVICE
# ============================================================================
"""
Service for managing organizational positions and headcount.
"""

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.core.exceptions import ValidationError
from typing import Optional, Dict, List, Any
from decimal import Decimal

from workforce.core_models import Employee
from workforce.models import Position, Department, JobTitle, Campus


class PositionService:
    """
    Service class for position management operations.
    """
    
    @staticmethod
    def generate_position_code(department: Department, job_title: JobTitle) -> str:
        """
        Generate a unique position code.
        
        Format: POS-{DEPT_CODE}-{JOB_CODE}-{SEQUENCE}
        Example: POS-ACAD-SLEC-001
        """
        dept_code = department.code if hasattr(department, 'code') else str(department.id)[:4].upper()
        job_code = job_title.code if hasattr(job_title, 'code') else str(job_title.id)[:4].upper()
        
        # Get next sequence number
        existing_count = Position.objects.filter(
            department=department,
            job_title=job_title
        ).count()
        
        sequence = str(existing_count + 1).zfill(3)
        
        return f"POS-{dept_code}-{job_code}-{sequence}"
    
    @transaction.atomic
    def create_position(
        self,
        job_title: JobTitle,
        department: Department,
        campus: Campus,
        position_type: str = Position.PositionType.PERMANENT,
        budgeted_salary: Optional[Decimal] = None,
        budget_code: str = '',
        fiscal_year: Optional[int] = None,
        reports_to_position: Optional[Position] = None,
        is_critical: bool = False,
        effective_from=None,
        notes: str = '',
    ) -> Position:
        """
        Create a new position.
        
        Args:
            job_title: The job title for this position
            department: The department
            campus: The campus
            position_type: Type of position (permanent, contract, etc.)
            budgeted_salary: Budgeted salary amount
            budget_code: Budget code for finance integration
            fiscal_year: Fiscal year for budget
            reports_to_position: Reporting position in hierarchy
            is_critical: Whether position is critical (needs succession plan)
            effective_from: Effective start date
            notes: Additional notes
            
        Returns:
            Position: The created position
        """
        if effective_from is None:
            effective_from = timezone.now().date()
        
        # Generate position code
        position_code = self.generate_position_code(department, job_title)
        
        # Use job title as default position title
        title = job_title.title
        
        # Use job grade salary range as default if not provided
        if budgeted_salary is None and job_title.job_grade:
            budgeted_salary = job_title.job_grade.min_salary
        
        position = Position.objects.create(
            position_code=position_code,
            title=title,
            job_title=job_title,
            department=department,
            campus=campus,
            reports_to_position=reports_to_position,
            position_type=position_type,
            funding_status=Position.FundingStatus.FUNDED,
            vacancy_status=Position.VacancyStatus.VACANT,
            budgeted_salary=budgeted_salary,
            budget_code=budget_code,
            fiscal_year=fiscal_year or timezone.now().year,
            effective_from=effective_from,
            is_critical=is_critical,
            notes=notes,
        )
        
        return position
    
    @transaction.atomic
    def assign_employee(
        self,
        position: Position,
        employee: Employee,
    ) -> Position:
        """
        Assign an employee to a position.
        
        Args:
            position: The position to fill
            employee: The employee to assign
            
        Returns:
            Position: The updated position
        """
        if position.vacancy_status == Position.VacancyStatus.OCCUPIED:
            raise ValidationError(
                f"Position {position.position_code} is already occupied by "
                f"{position.current_employee.employee_no if position.current_employee else 'unknown'}"
            )
        
        position.current_employee = employee
        position.vacancy_status = Position.VacancyStatus.OCCUPIED
        position.save()
        
        return position
    
    @transaction.atomic
    def vacate_position(self, position: Position) -> Position:
        """
        Mark a position as vacant.
        """
        position.current_employee = None
        position.vacancy_status = Position.VacancyStatus.VACANT
        position.save()
        
        return position
    
    @transaction.atomic
    def freeze_position(self, position: Position, reason: str = '') -> Position:
        """
        Freeze a position (budget cut, reorganization, etc.)
        """
        if position.vacancy_status == Position.VacancyStatus.OCCUPIED:
            raise ValidationError(
                "Cannot freeze an occupied position. Please transfer or remove the employee first."
            )
        
        position.funding_status = Position.FundingStatus.FROZEN
        position.vacancy_status = Position.VacancyStatus.ON_HOLD
        if reason:
            position.notes = f"{position.notes}\n[FROZEN] {reason}".strip()
        position.save()
        
        return position
    
    @transaction.atomic
    def unfreeze_position(self, position: Position) -> Position:
        """
        Unfreeze a position.
        """
        if position.funding_status != Position.FundingStatus.FROZEN:
            raise ValidationError("Position is not frozen")
        
        position.funding_status = Position.FundingStatus.FUNDED
        position.vacancy_status = Position.VacancyStatus.VACANT
        position.save()
        
        return position
    
    def get_vacant_positions(
        self,
        department: Optional[Department] = None,
        campus: Optional[Campus] = None,
        job_title: Optional[JobTitle] = None,
    ):
        """
        Get all vacant positions with optional filters.
        """
        queryset = Position.objects.filter(
            vacancy_status=Position.VacancyStatus.VACANT,
            is_active=True
        )
        
        if department:
            queryset = queryset.filter(department=department)
        if campus:
            queryset = queryset.filter(campus=campus)
        if job_title:
            queryset = queryset.filter(job_title=job_title)
        
        return queryset.select_related(
            'job_title', 'department', 'campus', 'reports_to_position'
        )
    
    def get_headcount_summary(self, department: Optional[Department] = None) -> Dict[str, Any]:
        """
        Get headcount summary statistics.
        
        Returns:
            Dict with headcount statistics
        """
        queryset = Position.objects.filter(is_active=True)
        
        if department:
            queryset = queryset.filter(department=department)
        
        total = queryset.count()
        occupied = queryset.filter(vacancy_status=Position.VacancyStatus.OCCUPIED).count()
        vacant = queryset.filter(vacancy_status=Position.VacancyStatus.VACANT).count()
        on_hold = queryset.filter(vacancy_status=Position.VacancyStatus.ON_HOLD).count()
        
        funded = queryset.filter(funding_status=Position.FundingStatus.FUNDED).count()
        unfunded = queryset.filter(funding_status=Position.FundingStatus.UNFUNDED).count()
        frozen = queryset.filter(funding_status=Position.FundingStatus.FROZEN).count()
        
        # By position type
        by_type = queryset.values('position_type').annotate(count=Count('id'))
        
        # By department
        by_department = queryset.values(
            'department__id', 'department__name'
        ).annotate(
            total=Count('id'),
            occupied=Count('id', filter=Q(vacancy_status=Position.VacancyStatus.OCCUPIED)),
            vacant=Count('id', filter=Q(vacancy_status=Position.VacancyStatus.VACANT)),
        )
        
        return {
            'total_positions': total,
            'occupied': occupied,
            'vacant': vacant,
            'on_hold': on_hold,
            'vacancy_rate': round((vacant / total * 100) if total > 0 else 0, 2),
            'funding': {
                'funded': funded,
                'unfunded': unfunded,
                'frozen': frozen,
            },
            'by_type': list(by_type),
            'by_department': list(by_department),
        }
    
    def get_position_hierarchy(self, department: Optional[Department] = None) -> List[Dict]:
        """
        Get position hierarchy as a nested tree structure.
        
        Returns:
            List of position dictionaries with nested children
        """
        queryset = Position.objects.filter(
            is_active=True,
            reports_to_position__isnull=True  # Top-level positions
        ).select_related(
            'job_title', 'department', 'campus', 'current_employee'
        )
        
        if department:
            queryset = queryset.filter(department=department)
        
        def build_tree(position):
            """Recursively build position tree."""
            children = Position.objects.filter(
                reports_to_position=position,
                is_active=True
            ).select_related(
                'job_title', 'department', 'campus', 'current_employee'
            )
            
            return {
                'id': position.id,
                'position_code': position.position_code,
                'title': position.title,
                'job_title': position.job_title.title,
                'department': position.department.name,
                'campus': position.campus.name,
                'vacancy_status': position.vacancy_status,
                'current_employee': {
                    'id': position.current_employee.id,
                    'employee_no': position.current_employee.employee_no,
                    'name': position.current_employee.get_full_name(),
                } if position.current_employee else None,
                'is_critical': position.is_critical,
                'children': [build_tree(child) for child in children]
            }
        
        return [build_tree(pos) for pos in queryset]
    
    def get_critical_positions(self):
        """
        Get all critical positions that need succession planning.
        """
        return Position.objects.filter(
            is_critical=True,
            is_active=True
        ).select_related(
            'job_title', 'department', 'campus', 'current_employee'
        )
    
    def bulk_create_positions(
        self,
        positions_data: List[Dict[str, Any]],
        created_by=None,
    ) -> List[Position]:
        """
        Bulk create positions from a list of data.
        
        Args:
            positions_data: List of dicts with position data
            created_by: User creating the positions
            
        Returns:
            List of created Position instances
        """
        created_positions = []
        
        for data in positions_data:
            job_title = JobTitle.objects.get(id=data['job_title_id'])
            department = Department.objects.get(id=data['department_id'])
            campus = Campus.objects.get(id=data['campus_id'])
            
            reports_to = None
            if data.get('reports_to_position_id'):
                reports_to = Position.objects.get(id=data['reports_to_position_id'])
            
            position = self.create_position(
                job_title=job_title,
                department=department,
                campus=campus,
                position_type=data.get('position_type', Position.PositionType.PERMANENT),
                budgeted_salary=data.get('budgeted_salary'),
                budget_code=data.get('budget_code', ''),
                fiscal_year=data.get('fiscal_year'),
                reports_to_position=reports_to,
                is_critical=data.get('is_critical', False),
                effective_from=data.get('effective_from'),
                notes=data.get('notes', ''),
            )
            created_positions.append(position)
        
        return created_positions
