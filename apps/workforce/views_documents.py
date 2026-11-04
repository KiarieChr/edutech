"""
Workforce Document Generation Views (Milestone 1).
Integrates WeasyPrint Document Studio PDF generation for:
- Employee Payslips (/api/workforce/documents/payslip/{calculation_id}/)
- Employment Contracts (/api/workforce/documents/contract/{contract_id}/)
- KRA P9 Tax Deduction Cards (/api/workforce/documents/p9/{employee_id}/)
"""
from datetime import datetime
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django_tenants.utils import schema_context, get_public_schema_name

from tenants.models import Client
from core.campus_filter import get_request_campus_id
from documents.models import DocumentTemplate
from documents.services.document_generator import DocumentGeneratorService
from documents.services.template_resolver import TemplateResolutionError
from workforce.core_models import Employee, EmployeeContract
from workforce.models import PayrollCalculation
from workforce.documents.payslip import PayslipDataProvider
from workforce.documents.contract import EmployeeContractDataProvider
from workforce.documents.p9_form import P9FormDataProvider


def resolve_tenant_for_document_request(request, model_class=None, object_id=None):
    """
    Resolves the appropriate tenant schema for workforce document requests.
    Handles:
    1. request.tenant if present and not public.
    2. HTTP headers (X-Tenant-Schema, X-Tenant).
    3. Query parameters (?tenant=..., ?schema=...).
    4. Authenticated user's associated tenant(s).
    5. Fallback object lookup across tenant schemas (for dev / test harnesses / direct API calls).
    6. Fallback to first active non-public tenant.
    """
    public_schema = get_public_schema_name()
    current_tenant = getattr(request, 'tenant', None)
    if current_tenant and getattr(current_tenant, 'schema_name', None) != public_schema:
        return current_tenant

    schema_name = (
        request.headers.get('X-Tenant-Schema')
        or request.headers.get('X-Tenant')
        or request.META.get('HTTP_X_TENANT_SCHEMA')
        or request.META.get('HTTP_X_TENANT')
        or request.query_params.get('tenant')
        or request.query_params.get('schema')
    )
    if schema_name and schema_name != public_schema:
        try:
            return Client.objects.get(schema_name=schema_name)
        except Client.DoesNotExist:
            pass

    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        user_tenant = user.tenants.exclude(schema_name=public_schema).first()
        if user_tenant:
            return user_tenant

    if model_class and object_id:
        for tenant in Client.objects.exclude(schema_name=public_schema):
            try:
                with schema_context(tenant.schema_name):
                    if model_class.objects.filter(pk=object_id).exists():
                        return tenant
            except Exception:
                continue

    fallback = Client.objects.exclude(schema_name=public_schema).first()
    if fallback:
        return fallback

    return current_tenant


def _ensure_category_template(category: str, default_name: str) -> DocumentTemplate:
    """Helper to ensure at least one published template exists for the category."""
    tpl = DocumentTemplate.objects.filter(
        category=category, status=DocumentTemplate.Status.PUBLISHED
    ).first()
    if not tpl:
        tpl, _ = DocumentTemplate.objects.get_or_create(
            name=default_name,
            category=category,
            defaults={
                "status": DocumentTemplate.Status.PUBLISHED,
                "is_default": True,
                "description": f"Standard institutional template for {default_name}",
            }
        )
        if tpl.status != DocumentTemplate.Status.PUBLISHED or not tpl.is_default:
            tpl.status = DocumentTemplate.Status.PUBLISHED
            tpl.is_default = True
            tpl.save()
    return tpl


class WorkforcePayslipDocumentView(APIView):
    """
    Generates an official institutional employee payslip via WeasyPrint.
    GET /api/workforce/documents/payslip/{calculation_id}/?template_id=X&preview=false
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, calculation_id: int):
        tenant = resolve_tenant_for_document_request(request, model_class=PayrollCalculation, object_id=calculation_id)
        schema_name = getattr(tenant, 'schema_name', None) or get_public_schema_name()

        with schema_context(schema_name):
            calculation = PayrollCalculation.objects.select_related(
                'employee', 'payroll_period', 'employee__department', 'employee__campus'
            ).prefetch_related('details').filter(pk=calculation_id).first()

            if not calculation:
                return Response(
                    {"detail": "No PayrollCalculation matches the given query."},
                    status=status.HTTP_404_NOT_FOUND
                )

            campus_id = get_request_campus_id(request)
            if campus_id is not None and calculation.employee:
                if calculation.employee.campus_id is not None and str(calculation.employee.campus_id) != str(campus_id):
                    return Response(
                        {"detail": "Employee exists but does not belong to the currently selected campus."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            template_id = request.query_params.get('template_id')
            if template_id:
                try:
                    template_id = int(template_id)
                except (ValueError, TypeError):
                    template_id = None

            is_preview = request.query_params.get('preview', 'false').lower() in ('true', '1')

            try:
                provider = PayslipDataProvider(calculation)

                if is_preview:
                    preview_data = DocumentGeneratorService.generate_preview_html(
                        provider, template_id=template_id
                    )
                    return Response(preview_data, status=status.HTTP_200_OK)

                try:
                    pdf_bytes = DocumentGeneratorService.generate_pdf(provider, template_id=template_id)
                except TemplateResolutionError:
                    # Self-healing: create default published template for PAYSLIP
                    _ensure_category_template(DocumentTemplate.Category.PAYSLIP, "Standard Employee Payslip")
                    pdf_bytes = DocumentGeneratorService.generate_pdf(provider, template_id=template_id)

                filename = f"payslip_{calculation.employee.employee_no}_{calculation.id}.pdf"
                response = HttpResponse(pdf_bytes, content_type='application/pdf')
                response['Content-Disposition'] = f'inline; filename="{filename}"'
                return response

            except Exception as exc:
                return Response(
                    {'error': str(exc), 'code': 'DOCUMENT_GENERATION_FAILED'},
                    status=status.HTTP_400_BAD_REQUEST
                )


class WorkforceContractDocumentView(APIView):
    """
    Generates an official employment contract agreement PDF via WeasyPrint.
    GET /api/workforce/documents/contract/{contract_id}/?template_id=X&preview=false
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, contract_id: int):
        tenant = resolve_tenant_for_document_request(request, model_class=EmployeeContract, object_id=contract_id)
        schema_name = getattr(tenant, 'schema_name', None) or get_public_schema_name()

        with schema_context(schema_name):
            contract = EmployeeContract.objects.select_related(
                'employee', 'employee__department', 'employee__campus'
            ).filter(pk=contract_id).first()

            if not contract:
                return Response(
                    {"detail": "No EmployeeContract matches the given query."},
                    status=status.HTTP_404_NOT_FOUND
                )

            campus_id = get_request_campus_id(request)
            if campus_id is not None and contract.employee:
                if contract.employee.campus_id is not None and str(contract.employee.campus_id) != str(campus_id):
                    return Response(
                        {"detail": "Employee exists but does not belong to the currently selected campus."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            template_id = request.query_params.get('template_id')
            if template_id:
                try:
                    template_id = int(template_id)
                except (ValueError, TypeError):
                    template_id = None

            is_preview = request.query_params.get('preview', 'false').lower() in ('true', '1')

            try:
                provider = EmployeeContractDataProvider(contract)

                if is_preview:
                    preview_data = DocumentGeneratorService.generate_preview_html(
                        provider, template_id=template_id
                    )
                    return Response(preview_data, status=status.HTTP_200_OK)

                try:
                    pdf_bytes = DocumentGeneratorService.generate_pdf(provider, template_id=template_id)
                except TemplateResolutionError:
                    # Self-healing: create default published template for EMPLOYMENT_CONTRACT
                    _ensure_category_template(
                        DocumentTemplate.Category.EMPLOYMENT_CONTRACT, "Standard Employment Contract"
                    )
                    pdf_bytes = DocumentGeneratorService.generate_pdf(provider, template_id=template_id)

                filename = f"contract_{contract.employee.employee_no}_{contract.id}.pdf"
                response = HttpResponse(pdf_bytes, content_type='application/pdf')
                response['Content-Disposition'] = f'inline; filename="{filename}"'
                return response

            except Exception as exc:
                return Response(
                    {'error': str(exc), 'code': 'DOCUMENT_GENERATION_FAILED'},
                    status=status.HTTP_400_BAD_REQUEST
                )


class WorkforceP9DocumentView(APIView):
    """
    Generates a standard Kenya Revenue Authority (KRA) P9A Tax Deduction Card via WeasyPrint.
    GET /api/workforce/documents/p9/{employee_id}/?year=2026&template_id=X&preview=false
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, employee_id: int):
        tenant = resolve_tenant_for_document_request(request, model_class=Employee, object_id=employee_id)
        schema_name = getattr(tenant, 'schema_name', None) or get_public_schema_name()

        with schema_context(schema_name):
            employee = Employee.objects.select_related('department', 'campus').filter(pk=employee_id).first()
            if not employee:
                return Response(
                    {"detail": "No Employee matches the given query."},
                    status=status.HTTP_404_NOT_FOUND
                )

            campus_id = get_request_campus_id(request)
            if campus_id is not None:
                if employee.campus_id is not None and str(employee.campus_id) != str(campus_id):
                    return Response(
                        {"detail": "Employee exists but does not belong to the currently selected campus."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            year_param = request.query_params.get('year', str(datetime.now().year))
            try:
                year = int(year_param)
            except (ValueError, TypeError):
                year = datetime.now().year

            template_id = request.query_params.get('template_id')
            if template_id:
                try:
                    template_id = int(template_id)
                except (ValueError, TypeError):
                    template_id = None

            is_preview = request.query_params.get('preview', 'false').lower() in ('true', '1')

            try:
                provider = P9FormDataProvider(employee, context={'year': year})

                if is_preview:
                    preview_data = DocumentGeneratorService.generate_preview_html(
                        provider, template_id=template_id
                    )
                    return Response(preview_data, status=status.HTTP_200_OK)

                try:
                    pdf_bytes = DocumentGeneratorService.generate_pdf(provider, template_id=template_id)
                except TemplateResolutionError:
                    # Self-healing: create default published template for P9_FORM
                    _ensure_category_template(
                        DocumentTemplate.Category.P9_FORM, "Standard KRA P9 Tax Card"
                    )
                    pdf_bytes = DocumentGeneratorService.generate_pdf(provider, template_id=template_id)

                filename = f"p9_form_{employee.employee_no}_{year}.pdf"
                response = HttpResponse(pdf_bytes, content_type='application/pdf')
                response['Content-Disposition'] = f'inline; filename="{filename}"'
                return response

            except Exception as exc:
                return Response(
                    {'error': str(exc), 'code': 'DOCUMENT_GENERATION_FAILED'},
                    status=status.HTTP_400_BAD_REQUEST
                )
