from decimal import Decimal
import datetime
from django.utils import timezone
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from core.campus_filter import get_request_campus_id
from finance.services.budget_report_service import BudgetReportService


class BudgetVsActualReportExportView(APIView):
    """
    GET /api/finance/budgeting/reports/budget-vs-actual/
    Query parameters:
    - year / fiscal_year: int (e.g. 2026)
    - campus_id: int | 'all'
    - format: 'pdf' | 'xlsx' (default: 'pdf')
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        now = timezone.now()
        year_param = request.query_params.get('year') or request.query_params.get('fiscal_year')
        try:
            fiscal_year = int(year_param) if year_param else now.year
        except (ValueError, TypeError):
            fiscal_year = now.year

        campus_id = get_request_campus_id(request)
        export_format = (request.query_params.get('format') or 'pdf').lower()

        try:
            if export_format == 'xlsx' or export_format == 'excel':
                content_bytes, filename = BudgetReportService.export_budget_vs_actual_excel(fiscal_year, campus_id)
                content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            else:
                content_bytes, filename = BudgetReportService.export_budget_vs_actual_pdf(fiscal_year, campus_id)
                content_type = 'application/pdf'

            response = HttpResponse(content_bytes, content_type=content_type)
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            response['Access-Control-Expose-Headers'] = 'Content-Disposition'
            return response

        except Exception as e:
            return Response({
                'error': f'Failed to generate Budget vs. Actual report: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdjustmentHistoryReportExportView(APIView):
    """
    GET /api/finance/budgeting/reports/adjustments/
    Query parameters:
    - year / fiscal_year: int (e.g. 2026)
    - campus_id: int | 'all'
    - format: 'pdf' | 'xlsx' (default: 'pdf')
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        now = timezone.now()
        year_param = request.query_params.get('year') or request.query_params.get('fiscal_year')
        try:
            fiscal_year = int(year_param) if year_param else now.year
        except (ValueError, TypeError):
            fiscal_year = now.year

        campus_id = get_request_campus_id(request)
        export_format = (request.query_params.get('format') or 'pdf').lower()

        try:
            if export_format == 'xlsx' or export_format == 'excel':
                content_bytes, filename = BudgetReportService.export_adjustments_excel(fiscal_year, campus_id)
                content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            else:
                content_bytes, filename = BudgetReportService.export_adjustments_pdf(fiscal_year, campus_id)
                content_type = 'application/pdf'

            response = HttpResponse(content_bytes, content_type=content_type)
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            response['Access-Control-Expose-Headers'] = 'Content-Disposition'
            return response

        except Exception as e:
            return Response({
                'error': f'Failed to generate Adjustment History report: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BudgetReportsMetadataView(APIView):
    """
    GET /api/finance/budgeting/reports/metadata/
    Returns real-time summaries and telemetry for the Reports & Analytics dashboard cards.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        now = timezone.now()
        year_param = request.query_params.get('year') or request.query_params.get('fiscal_year')
        try:
            fiscal_year = int(year_param) if year_param else now.year
        except (ValueError, TypeError):
            fiscal_year = now.year

        campus_id = get_request_campus_id(request)
        b_data = BudgetReportService.get_budget_vs_actual_data(fiscal_year, campus_id)
        adj_data = BudgetReportService.get_adjustment_history_data(fiscal_year, campus_id)

        return Response({
            'success': True,
            'fiscal_year': fiscal_year,
            'budget_vs_actual': {
                'lines_count': len(b_data['lines']),
                'total_original': str(b_data['totals']['original']),
                'total_controlled': str(b_data['totals']['controlled']),
                'total_spend': str(b_data['totals']['spend']),
                'total_available': str(b_data['totals']['available']),
                'burn_rate': b_data['totals']['burn_rate'],
            },
            'adjustments': {
                'count': len(adj_data['items']),
                'latest': adj_data['items'][0] if adj_data['items'] else None,
            }
        })
