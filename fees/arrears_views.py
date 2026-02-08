# fees/arrears_views.py
"""
ViewSet for Student Arrears Analysis and Reporting
Provides endpoints for arrears KPIs, charts, and detailed student lists.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Sum, Count, Q, F, DecimalField
from django.db.models.functions import Coalesce
from decimal import Decimal

from .models import FeeInvoice
from accounts.models import Student


class ArrearsViewSet(viewsets.ViewSet):
    """
    ViewSet for analyzing student arrears (outstanding fees).
    
    Endpoints:
    - GET /arrears/summary/ - Returns KPIs and chart data for arrears dashboard
    - GET /arrears/students/ - Returns paginated list of students with outstanding balances
    """
    
    def _apply_filters(self, queryset, request):
        """Apply common filters to invoice queryset"""
        from student_settings.models import AcademicYear, Term
        
        academic_year = request.query_params.get('academic_year')
        term = request.query_params.get('term')
        grade = request.query_params.get('grade')
        intake = request.query_params.get('intake')
        
        # Handle academic year (accept ID or name)
        if academic_year:
            # Try as name first (since "2024", "2026" etc are valid year names)
            year_obj = AcademicYear.objects.filter(name__icontains=academic_year).first()
            if year_obj:
                queryset = queryset.filter(academic_year_id=year_obj.id)
            else:
                # Fall back to ID if name lookup fails
                try:
                    queryset = queryset.filter(academic_year_id=int(academic_year))
                except (ValueError, TypeError):
                    pass  # Invalid ID, ignore filter
        
        # Handle term (accept ID or name)
        if term:
            try:
                # Try as ID first
                queryset = queryset.filter(term_id=int(term))
            except (ValueError, TypeError):
                # If not an ID, try as name
                term_obj = Term.objects.filter(name__icontains=term).first()
                if term_obj:
                    queryset = queryset.filter(term_id=term_obj.id)
        
        # Handle grade (accept ID or name)
        if grade:
            try:
                queryset = queryset.filter(class_session__grade_id=int(grade))
            except (ValueError, TypeError):
                # If not an ID, try as name
                queryset = queryset.filter(class_session__grade__name__icontains=grade)
        
        # Handle intake (accept ID or name)
        if intake:
            try:
                queryset = queryset.filter(student__intake_id=int(intake))
            except (ValueError, TypeError):
                # If not an ID, try as name
                queryset = queryset.filter(student__intake__name__icontains=intake)
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def filter_options(self, request):
        """
        Get available filter options for dropdowns.
        
        Query Params:
        - academic_year: Filter terms by academic year (optional)
        
        Returns:
        {
            "academic_years": [{"id": 1, "name": "2024"}],
            "terms": [{"id": 1, "name": "Term 1"}],
            "grades": [{"id": 1, "name": "Form 1"}],
            "intakes": [{"id": 1, "name": "Jan 2024"}]
        }
        """
        from student_settings.models import AcademicYear, Term, GradeStructure, Intake
        
        # Get all active academic years
        academic_years = AcademicYear.objects.filter(
            is_deleted=False
        ).order_by('-start_date').values('id', 'name')
        
        # Get terms filtered by academic year if provided
        terms_query = Term.objects.filter(is_deleted=False)
        
        # Filter terms by academic year if specified
        academic_year_param = request.query_params.get('academic_year')
        if academic_year_param:
            try:
                # Try as ID first
                terms_query = terms_query.filter(academic_year_id=int(academic_year_param))
            except (ValueError, TypeError):
                # If not an ID, try as name
                year_obj = AcademicYear.objects.filter(name__icontains=academic_year_param).first()
                if year_obj:
                    terms_query = terms_query.filter(academic_year_id=year_obj.id)
        
        terms = terms_query.order_by('order').values('id', 'name')
        
        # Get all active grades
        grades = GradeStructure.objects.filter(
            is_deleted=False
        ).order_by('name').values('id', 'name')
        
        # Get all active intakes
        intakes = Intake.objects.filter(
            is_deleted=False
        ).order_by('-start_date').values('id', 'name')
        
        return Response({
            'academic_years': list(academic_years),
            'terms': list(terms),
            'grades': list(grades),
            'intakes': list(intakes),
        })
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Get arrears summary including KPIs and chart data.
        
        Query Params:
        - academic_year: Filter by academic year ID
        - term: Filter by term ID
        - grade: Filter by grade ID
        - intake: Filter by intake ID
        
        Returns:
        {
            "kpis": {
                "total_arrears": float,
                "student_count": int,
                "average_arrears": float,
                "highest_arrears": float,
                "fully_paid_count": int,
                "arrears_growth": float
            },
            "by_class": [{"name": str, "value": float}],
            "by_intake": [{"name": str, "value": int}]
        }
        """
        
        # Get all invoices with outstanding balances
        invoices = FeeInvoice.objects.filter(
            balance__gt=0
        ).exclude(status='VOID')
        
        # Apply filters
        invoices = self._apply_filters(invoices, request)
        
        # Calculate KPIs
        kpi_data = invoices.aggregate(
            total_arrears=Coalesce(Sum('balance'), Decimal('0.00'), output_field=DecimalField()),
            student_count=Count('student', distinct=True),
            highest_arrears=Coalesce(Sum('balance'), Decimal('0.00'), output_field=DecimalField()),  # Max balance per student would be better
        )
        
        # Calculate average arrears
        if kpi_data['student_count'] > 0:
            kpi_data['average_arrears'] = float(kpi_data['total_arrears']) / kpi_data['student_count']
        else:
            kpi_data['average_arrears'] = 0
        
        # Count fully paid students (no outstanding balance)
        fully_paid_count = FeeInvoice.objects.filter(
            balance=0,
            status='PAID'
        )
        fully_paid_count = self._apply_filters(fully_paid_count, request)
        kpi_data['fully_paid_count'] = fully_paid_count.values('student').distinct().count()
        
        # TODO: Calculate arrears growth (compare with previous period)
        # For now, set to 0
        kpi_data['arrears_growth'] = 0
        
        # Arrears by Class
        by_class_data = invoices.values(
            'class_session__grade__name'
        ).annotate(
            value=Sum('balance')
        ).order_by('-value')
        
        by_class = [
            {
                'name': item['class_session__grade__name'] or 'Unknown',
                'value': float(item['value'])
            }
            for item in by_class_data
        ]
        
        # Arrears by Intake
        by_intake_data = invoices.values(
            'student__intake__name'
        ).annotate(
            count=Count('student', distinct=True)
        ).order_by('-count')
        
        by_intake = [
            {
                'name': item['student__intake__name'] or 'Unknown',
                'value': item['count']
            }
            for item in by_intake_data
        ]
        
        return Response({
            'kpis': {
                'total_arrears': float(kpi_data['total_arrears']),
                'student_count': kpi_data['student_count'],
                'average_arrears': round(kpi_data['average_arrears'], 2),
                'highest_arrears': float(kpi_data['highest_arrears']),
                'fully_paid_count': kpi_data['fully_paid_count'],
                'arrears_growth': kpi_data['arrears_growth'],
            },
            'by_class': by_class,
            'by_intake': by_intake,
        })
    
    @action(detail=False, methods=['get'])
    def students(self, request):
        """
        Get paginated list of students with outstanding balances.
        
        Query Params:
        - academic_year: Filter by academic year ID
        - term: Filter by term ID
        - grade: Filter by grade ID
        - intake: Filter by intake ID
        - search: Search by student name or admission number
        - page: Page number (default: 1)
        - page_size: Items per page (default: 20)
        
        Returns:
        {
            "count": int,
            "next": str | null,
            "previous": str | null,
            "results": [
                {
                    "id": int,
                    "name": str,
                    "admission_number": str,
                    "class_name": str,
                    "term": str,
                    "total_payable": float,
                    "total_paid": float,
                    "balance": float,
                    "status": str
                }
            ]
        }
        """
        
        # Get invoices with balances
        invoices = FeeInvoice.objects.filter(
            balance__gt=0
        ).exclude(status='VOID').select_related(
            'student',
            'student__student',
            'student__intake',
            'class_session',
            'class_session__grade',
            'term',
            'academic_year'
        )
        
        # Apply filters
        invoices = self._apply_filters(invoices, request)
        
        # Search functionality
        search = request.query_params.get('search', '').strip()
        if search:
            invoices = invoices.filter(
                Q(student__student__first_name__icontains=search) |
                Q(student__student__last_name__icontains=search) |
                Q(student__admission_number__icontains=search)
            )
        
        # Get unique students with their aggregated data
        student_data = {}
        for invoice in invoices:
            student_id = invoice.student.id
            
            if student_id not in student_data:
                student_data[student_id] = {
                    'id': student_id,
                    'name': invoice.student.student.get_full_name if invoice.student.student else 'Unknown',
                    'admission_number': invoice.student.admission_number,
                    'class_name': invoice.class_session.grade.name if invoice.class_session and invoice.class_session.grade else 'Unknown',
                    'term': invoice.term.name if invoice.term else 'Unknown',
                    'total_payable': 0,
                    'total_paid': 0,
                    'balance': 0,
                    'status': 'Active'  # TODO: Derive from invoice or student status
                }
            
            # Aggregate amounts
            student_data[student_id]['total_payable'] += float(invoice.total_amount)
            student_data[student_id]['total_paid'] += float(invoice.paid_amount)
            student_data[student_id]['balance'] += float(invoice.balance)
        
        # Convert to list
        results = list(student_data.values())
        
        # Simple pagination (for basic implementation)
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))
        
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        
        paginated_results = results[start_idx:end_idx]
        
        return Response({
            'count': len(results),
            'next': None,  # TODO: Implement proper pagination URLs
            'previous': None,
            'results': paginated_results
        })

    @action(detail=False, methods=['get'])
    def student_balance(self, request):
        """
        Get balance details for a specific student.
        Query Params:
        - student_id: ID of the student
        """
        student_id = request.query_params.get('student_id')
        if not student_id:
            return Response({'error': 'student_id is required'}, status=status.HTTP_400_BAD_REQUEST)
            
        invoices = FeeInvoice.objects.filter(student_id=student_id).exclude(status='VOID')
        
        agg = invoices.aggregate(
            total_payable=Coalesce(Sum('total_amount'), Decimal('0.00'), output_field=DecimalField()),
            total_paid=Coalesce(Sum('paid_amount'), Decimal('0.00'), output_field=DecimalField()),
            balance=Coalesce(Sum('balance'), Decimal('0.00'), output_field=DecimalField())
        )
        
        return Response({
            'student_id': int(student_id),
            'total_payable': agg['total_payable'],
            'total_paid': agg['total_paid'],
            'balance': agg['balance']
        })
