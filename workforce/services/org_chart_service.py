# ============================================================================
# ORG CHART SERVICE
# ============================================================================
"""
Service for generating organization chart data structures.
"""

from django.db.models import Count, Q, Prefetch
from django.core.cache import cache
from typing import Optional, Dict, List, Any

from workforce.core_models import Employee
from workforce.models import Department, Position, Campus


class OrgChartService:
    """
    Service for generating hierarchical organization chart data.
    Supports both department-based and position-based org charts.
    """
    
    CACHE_TIMEOUT = 300  # 5 minutes
    
    def get_department_tree(
        self,
        root_department: Optional[Department] = None,
        include_employees: bool = True,
        include_headcount: bool = True,
    ) -> List[Dict]:
        """
        Get department hierarchy as a tree structure.
        
        Args:
            root_department: Starting department (None for all root departments)
            include_employees: Include employee details
            include_headcount: Include headcount statistics
            
        Returns:
            List of department dictionaries with nested children
        """
        cache_key = f"org_chart_dept_{root_department.id if root_department else 'all'}_{include_employees}_{include_headcount}"
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        if root_department:
            departments = [root_department]
        else:
            departments = Department.objects.filter(
                parent_department__isnull=True,
                is_active=True
            ).select_related('head_of_department', 'campus', 'faculty')
        
        result = [self._build_department_node(dept, include_employees, include_headcount) 
                  for dept in departments]
        
        cache.set(cache_key, result, self.CACHE_TIMEOUT)
        return result
    
    def _build_department_node(
        self,
        department: Department,
        include_employees: bool,
        include_headcount: bool,
    ) -> Dict:
        """
        Build a single department node with children recursively.
        """
        node = {
            'id': department.id,
            'code': getattr(department, 'code', None),
            'name': department.name,
            'department_type': department.department_type,
            'level': self._get_department_level(department),
        }
        
        # Add head of department
        if department.head_of_department:
            node['head'] = {
                'id': department.head_of_department.id,
                'employee_no': department.head_of_department.employee_no,
                'name': department.head_of_department.get_full_name(),
            }
        else:
            node['head'] = None
        
        # Add campus info
        if department.campus:
            node['campus'] = {
                'id': department.campus.id,
                'name': department.campus.name,
            }
        
        # Add headcount statistics
        if include_headcount:
            node['headcount'] = self._get_department_headcount(department)
        
        # Add employees list
        if include_employees:
            node['employees'] = self._get_department_employees(department)
        
        # Add children recursively
        children = Department.objects.filter(
            parent_department=department,
            is_active=True
        ).select_related('head_of_department', 'campus')
        
        node['children'] = [
            self._build_department_node(child, include_employees, include_headcount)
            for child in children
        ]
        
        return node
    
    def _get_department_level(self, department: Department) -> int:
        """Calculate department level in hierarchy (0 = root)."""
        level = 0
        current = department
        while current.parent_department:
            level += 1
            current = current.parent_department
            if level > 10:  # Safety limit
                break
        return level
    
    def _get_department_headcount(self, department: Department) -> Dict:
        """Get headcount statistics for a department."""
        employees = Employee.objects.filter(
            department=department,
            employment_status__in=['active', 'probation']
        )
        
        total = employees.count()
        
        # By category
        by_category = employees.values('employee_category').annotate(count=Count('id'))
        
        # By status
        by_status = employees.values('employment_status').annotate(count=Count('id'))
        
        # Positions
        positions = Position.objects.filter(department=department, is_active=True)
        total_positions = positions.count()
        vacant_positions = positions.filter(vacancy_status='vacant').count()
        
        return {
            'total_employees': total,
            'total_positions': total_positions,
            'vacant_positions': vacant_positions,
            'fill_rate': round((total / total_positions * 100) if total_positions > 0 else 0, 2),
            'by_category': {item['employee_category']: item['count'] for item in by_category},
            'by_status': {item['employment_status']: item['count'] for item in by_status},
        }
    
    def _get_department_employees(self, department: Department) -> List[Dict]:
        """Get list of employees in a department."""
        employees = Employee.objects.filter(
            department=department,
            employment_status__in=['active', 'probation']
        ).select_related('job_grade').order_by('first_name', 'last_name')[:50]  # Limit for performance
        
        return [
            {
                'id': emp.id,
                'employee_no': emp.employee_no,
                'name': emp.get_full_name(),
                'job_grade': emp.job_grade.name if emp.job_grade else None,
                'status': emp.employment_status,
                'category': emp.employee_category,
            }
            for emp in employees
        ]
    
    def get_position_hierarchy(
        self,
        department: Optional[Department] = None,
        root_position: Optional[Position] = None,
    ) -> List[Dict]:
        """
        Get position hierarchy as a tree structure.
        
        Args:
            department: Filter by department
            root_position: Starting position (None for all root positions)
            
        Returns:
            List of position dictionaries with nested subordinates
        """
        if root_position:
            positions = [root_position]
        else:
            positions = Position.objects.filter(
                reports_to_position__isnull=True,
                is_active=True
            )
            if department:
                positions = positions.filter(department=department)
            
            positions = positions.select_related(
                'job_title', 'department', 'campus', 'current_employee'
            )
        
        return [self._build_position_node(pos) for pos in positions]
    
    def _build_position_node(self, position: Position) -> Dict:
        """Build a single position node with subordinates recursively."""
        node = {
            'id': position.id,
            'position_code': position.position_code,
            'title': position.title,
            'job_title': position.job_title.title if position.job_title else None,
            'department': position.department.name if position.department else None,
            'campus': position.campus.name if position.campus else None,
            'vacancy_status': position.vacancy_status,
            'funding_status': position.funding_status,
            'is_critical': position.is_critical,
        }
        
        # Add current holder
        if position.current_employee:
            node['holder'] = {
                'id': position.current_employee.id,
                'employee_no': position.current_employee.employee_no,
                'name': position.current_employee.get_full_name(),
                'email': position.current_employee.official_email,
            }
        else:
            node['holder'] = None
        
        # Add subordinate positions recursively
        subordinates = Position.objects.filter(
            reports_to_position=position,
            is_active=True
        ).select_related('job_title', 'department', 'campus', 'current_employee')
        
        node['subordinates'] = [
            self._build_position_node(sub) for sub in subordinates
        ]
        
        return node
    
    def get_reporting_chain(self, employee: Employee) -> List[Dict]:
        """
        Get the reporting chain (upward hierarchy) for an employee.
        
        Args:
            employee: The employee to get chain for
            
        Returns:
            List from employee up to top of hierarchy
        """
        chain = []
        
        # Get employee's position
        current_position = Position.objects.filter(
            current_employee=employee,
            vacancy_status=Position.VacancyStatus.OCCUPIED
        ).select_related('reports_to_position').first()
        
        if not current_position:
            return chain
        
        # Add current position
        chain.append({
            'position_code': current_position.position_code,
            'title': current_position.title,
            'employee_no': employee.employee_no,
            'name': employee.get_full_name(),
            'level': 0,
        })
        
        # Traverse upward
        current = current_position.reports_to_position
        level = 1
        
        while current and level < 20:  # Safety limit
            emp = current.current_employee
            chain.append({
                'position_code': current.position_code,
                'title': current.title,
                'employee_no': emp.employee_no if emp else None,
                'name': emp.get_full_name() if emp else 'Vacant',
                'level': level,
            })
            current = current.reports_to_position
            level += 1
        
        return chain
    
    def get_direct_reports(self, employee: Employee) -> List[Dict]:
        """
        Get direct reports for an employee.
        
        Args:
            employee: The manager employee
            
        Returns:
            List of direct reports
        """
        # Get employee's position
        manager_position = Position.objects.filter(
            current_employee=employee,
            vacancy_status=Position.VacancyStatus.OCCUPIED
        ).first()
        
        if not manager_position:
            return []
        
        # Get subordinate positions
        subordinate_positions = Position.objects.filter(
            reports_to_position=manager_position,
            is_active=True
        ).select_related('current_employee', 'job_title', 'department')
        
        return [
            {
                'position_code': pos.position_code,
                'title': pos.title,
                'department': pos.department.name if pos.department else None,
                'employee': {
                    'id': pos.current_employee.id,
                    'employee_no': pos.current_employee.employee_no,
                    'name': pos.current_employee.get_full_name(),
                    'email': pos.current_employee.official_email,
                } if pos.current_employee else None,
                'is_vacant': pos.vacancy_status == Position.VacancyStatus.VACANT,
            }
            for pos in subordinate_positions
        ]
    
    def search_org_chart(self, query: str) -> Dict:
        """
        Search the organization chart.
        
        Args:
            query: Search query
            
        Returns:
            Dict with matching departments, positions, and employees
        """
        query = query.strip().lower()
        
        # Search departments
        departments = Department.objects.filter(
            Q(name__icontains=query) | Q(code__icontains=query),
            is_active=True
        )[:10]
        
        # Search positions
        positions = Position.objects.filter(
            Q(position_code__icontains=query) | Q(title__icontains=query),
            is_active=True
        ).select_related('department', 'current_employee')[:10]
        
        # Search employees
        employees = Employee.objects.filter(
            Q(employee_no__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(official_email__icontains=query),
            employment_status__in=['active', 'probation']
        ).select_related('department')[:10]
        
        return {
            'departments': [
                {'id': d.id, 'name': d.name, 'code': getattr(d, 'code', None)}
                for d in departments
            ],
            'positions': [
                {
                    'id': p.id,
                    'position_code': p.position_code,
                    'title': p.title,
                    'department': p.department.name if p.department else None,
                    'holder': p.current_employee.get_full_name() if p.current_employee else 'Vacant',
                }
                for p in positions
            ],
            'employees': [
                {
                    'id': e.id,
                    'employee_no': e.employee_no,
                    'name': e.get_full_name(),
                    'department': e.department.name if e.department else None,
                }
                for e in employees
            ],
        }
    
    def invalidate_cache(self) -> None:
        """Invalidate all org chart caches."""
        # This would need a more sophisticated implementation
        # for production use with cache key patterns
        pass
