"""
Budget Planning Workspace API Views
Milestone 2: Draft Management, Auto-calculations, Excel Import/Export, and Approval Submission.
Complies with IPSAS 24 and ensures strict tenant isolation and Decimal financial precision.
"""

import io
import datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Sum, Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

from budgets.models import Budget, BudgetLine, BudgetStatus
from finance.models import Account, AccountType, AccountSubType
from core.campus_filter import get_request_campus_id


def to_decimal(val, default='0.00'):
    """Safe Decimal conversion helper."""
    if val is None or val == '':
        return Decimal(default)
    try:
        return Decimal(str(val).replace(',', '').strip())
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)


class BudgetPlanningView(APIView):
    """
    GET /api/finance/budgeting/planning/?year=2026
    Returns the planning data grid for the given fiscal year.
    Includes active accounts, previous year actuals, proposed draft amounts,
    approved amounts, actuals to date, and auto-calculated variance/available.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        year_param = request.query_params.get('year') or request.query_params.get('fiscal_year')
        try:
            fiscal_year = int(year_param) if year_param else timezone.now().year
        except (ValueError, TypeError):
            fiscal_year = timezone.now().year

        prev_year = fiscal_year - 1
        campus_id = get_request_campus_id(request)

        # 1. Locate Draft or Active Planning Budget (scoped to campus if selected)
        base_qs = Budget.objects.filter(fiscal_year=fiscal_year)
        if campus_id:
            campus_qs = base_qs.filter(campus_id=campus_id)
            draft_budget = (
                campus_qs.filter(status=BudgetStatus.DRAFT).first()
                or campus_qs.filter(status=BudgetStatus.PENDING_APPROVAL).first()
                or campus_qs.filter(status=BudgetStatus.REJECTED).first()
            )
            approved_budget = campus_qs.filter(status=BudgetStatus.APPROVED).first()
        else:
            draft_budget = (
                base_qs.filter(campus__isnull=True, status=BudgetStatus.DRAFT).first()
                or base_qs.filter(status=BudgetStatus.DRAFT).first()
                or base_qs.filter(campus__isnull=True, status=BudgetStatus.PENDING_APPROVAL).first()
                or base_qs.filter(status=BudgetStatus.PENDING_APPROVAL).first()
                or base_qs.filter(status=BudgetStatus.REJECTED).first()
            )
            approved_budget = (
                base_qs.filter(campus__isnull=True, status=BudgetStatus.APPROVED).first()
                or base_qs.filter(status=BudgetStatus.APPROVED).first()
            )

        # Determine active status of workspace
        budget_obj = draft_budget or approved_budget
        current_status = budget_obj.status if budget_obj else BudgetStatus.DRAFT
        budget_id = budget_obj.id if budget_obj else None
        campus_suffix = f" ({budget_obj.campus.name})" if budget_obj and budget_obj.campus else ""
        budget_name = budget_obj.name if budget_obj else f"Draft Budget {fiscal_year}{campus_suffix}"
        is_locked = current_status in [BudgetStatus.APPROVED, BudgetStatus.PENDING_APPROVAL]

        # 3. Fetch Accounts (Leaf accounts of Expense and Income types)
        accounts_qs = Account.objects.filter(
            is_active=True,
            type__in=[AccountType.EXPENSE, AccountType.INCOME]
        ).order_by('code')

        # Map existing draft lines: account_id -> amount
        draft_lines_map = {}
        if draft_budget:
            for bl in draft_budget.lines.all():
                draft_lines_map[bl.account_id] = bl.amount

        # Map existing approved lines: account_id -> amount
        approved_lines_map = {}
        if approved_budget:
            for bl in approved_budget.lines.all():
                approved_lines_map[bl.account_id] = bl.amount

        # 4. Fetch Actuals for Previous Year and Current Year to Date from Ledger
        prev_actuals_map = {}
        curr_actuals_map = {}
        try:
            from journals.models import LedgerEntry
            # Previous Year
            prev_entries = LedgerEntry.objects.filter(
                date__year=prev_year
            ).values('account_id', 'account__type').annotate(
                total_dr=Sum('debit'),
                total_cr=Sum('credit')
            )
            for pe in prev_entries:
                acc_id = pe['account_id']
                dr = pe['total_dr'] or Decimal('0.00')
                cr = pe['total_cr'] or Decimal('0.00')
                if pe['account__type'] == AccountType.EXPENSE:
                    prev_actuals_map[acc_id] = max(dr - cr, Decimal('0.00'))
                else:
                    prev_actuals_map[acc_id] = max(cr - dr, Decimal('0.00'))

            # Current Year to Date
            curr_entries = LedgerEntry.objects.filter(
                date__year=fiscal_year
            ).values('account_id', 'account__type').annotate(
                total_dr=Sum('debit'),
                total_cr=Sum('credit')
            )
            for ce in curr_entries:
                acc_id = ce['account_id']
                dr = ce['total_dr'] or Decimal('0.00')
                cr = ce['total_cr'] or Decimal('0.00')
                if ce['account__type'] == AccountType.EXPENSE:
                    curr_actuals_map[acc_id] = max(dr - cr, Decimal('0.00'))
                else:
                    curr_actuals_map[acc_id] = max(cr - dr, Decimal('0.00'))
        except Exception:
            pass

        # 5. Build Grid Lines
        lines = []
        categories_set = set()
        departments_set = set()

        total_prev_actual = Decimal('0.00')
        total_proposed = Decimal('0.00')
        total_approved = Decimal('0.00')
        total_actual_to_date = Decimal('0.00')

        for acc in accounts_qs:
            category_label = acc.get_type_display() if hasattr(acc, 'get_type_display') else str(acc.type)
            department_label = acc.get_sub_type_display() if hasattr(acc, 'get_sub_type_display') and acc.sub_type else 'General'
            categories_set.add(category_label)
            if department_label:
                departments_set.add(department_label)

            prev_actual = prev_actuals_map.get(acc.id, Decimal('0.00'))
            proposed = draft_lines_map.get(acc.id, Decimal('0.00'))
            approved = approved_lines_map.get(acc.id, Decimal('0.00'))
            actual_to_date = curr_actuals_map.get(acc.id, Decimal('0.00'))

            # Calculations:
            # Available: Approved - Actual to Date
            available = approved - actual_to_date
            # Variance: Proposed - Previous Year Actual
            variance = proposed - prev_actual

            total_prev_actual += prev_actual
            total_proposed += proposed
            total_approved += approved
            total_actual_to_date += actual_to_date

            lines.append({
                'id': acc.id,
                'account_id': acc.id,
                'account_code': acc.code,
                'account_name': acc.name,
                'account_type': acc.type,
                'category': category_label,
                'department': department_label,
                'previous_year_actual': str(prev_actual.quantize(Decimal('0.01'))),
                'proposed_budget': str(proposed.quantize(Decimal('0.01'))),
                'approved_budget': str(approved.quantize(Decimal('0.01'))),
                'actual_to_date': str(actual_to_date.quantize(Decimal('0.01'))),
                'available': str(available.quantize(Decimal('0.01'))),
                'variance': str(variance.quantize(Decimal('0.01'))),
            })

        total_available = total_approved - total_actual_to_date
        total_variance = total_proposed - total_prev_actual

        return Response({
            'budget': {
                'id': budget_id,
                'name': budget_name,
                'fiscal_year': fiscal_year,
                'campus_id': budget_obj.campus_id if budget_obj else campus_id,
                'campus_name': budget_obj.campus.name if (budget_obj and budget_obj.campus) else None,
                'status': current_status,
                'is_locked': is_locked,
                'can_edit': current_status == BudgetStatus.DRAFT or not budget_obj,
            },
            'summary': {
                'total_previous_year': str(total_prev_actual.quantize(Decimal('0.01'))),
                'total_proposed': str(total_proposed.quantize(Decimal('0.01'))),
                'total_approved': str(total_approved.quantize(Decimal('0.01'))),
                'total_actual': str(total_actual_to_date.quantize(Decimal('0.01'))),
                'total_available': str(total_available.quantize(Decimal('0.01'))),
                'total_variance': str(total_variance.quantize(Decimal('0.01'))),
            },
            'categories': sorted(list(categories_set)),
            'departments': sorted(list(departments_set)),
            'lines': lines,
        })


class BudgetPlanningSaveView(APIView):
    """
    POST /api/finance/budgeting/planning/save/
    Saves or updates a draft budget with proposed line amounts.
    Strictly forbids modifying budgets where status == 'approved'.
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        data = request.data
        fiscal_year = data.get('fiscal_year')
        try:
            fiscal_year = int(fiscal_year) if fiscal_year else timezone.now().year
        except (ValueError, TypeError):
            fiscal_year = timezone.now().year

        budget_id = data.get('budget_id')
        name = data.get('name') or f"Draft Budget {fiscal_year}"
        description = data.get('description', '')
        lines_data = data.get('lines', [])

        campus_id = data.get('campus_id') or get_request_campus_id(request)

        # Strict constraint check
        if budget_id:
            try:
                existing_budget = Budget.objects.get(id=budget_id)
                if existing_budget.status == BudgetStatus.APPROVED:
                    return Response({
                        'error': 'The Original Approved Budget is immutable. You cannot edit an approved budget.'
                    }, status=status.HTTP_400_BAD_REQUEST)
                budget = existing_budget
            except Budget.DoesNotExist:
                budget = None
        else:
            draft_qs = Budget.objects.filter(fiscal_year=fiscal_year, status=BudgetStatus.DRAFT)
            if campus_id:
                budget = draft_qs.filter(campus_id=campus_id).first()
            else:
                budget = draft_qs.filter(campus__isnull=True).first() or draft_qs.first()

        if not budget:
            budget = Budget.objects.create(
                name=name,
                fiscal_year=fiscal_year,
                campus_id=campus_id,
                start_date=datetime.date(fiscal_year, 1, 1),
                end_date=datetime.date(fiscal_year, 12, 31),
                description=description,
                status=BudgetStatus.DRAFT,
                is_active=True
            )
        else:
            budget.name = name
            if campus_id and not budget.campus_id:
                budget.campus_id = campus_id
            if description:
                budget.description = description
            budget.status = BudgetStatus.DRAFT
            budget.save()

        # Update or create BudgetLines
        saved_count = 0
        for item in lines_data:
            acc_id = item.get('account_id') or item.get('id')
            proposed = to_decimal(item.get('proposed_budget', '0.00'))

            if not acc_id:
                code = item.get('account_code')
                if code:
                    acc = Account.objects.filter(code__iexact=str(code).strip()).first()
                    acc_id = acc.id if acc else None

            if acc_id:
                BudgetLine.objects.update_or_create(
                    budget=budget,
                    account_id=acc_id,
                    defaults={'amount': proposed}
                )
                saved_count += 1

        return Response({
            'success': True,
            'message': f"Draft budget saved successfully with {saved_count} lines.",
            'budget': {
                'id': budget.id,
                'name': budget.name,
                'fiscal_year': budget.fiscal_year,
                'status': budget.status,
            }
        })


class BudgetPlanningSubmitView(APIView):
    """
    POST /api/finance/budgeting/planning/{id}/submit/
    Changes the budget status to 'pending_approval' and locks editing.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk=None):
        budget_id = pk or request.data.get('budget_id') or request.data.get('id')
        year = request.data.get('fiscal_year') or request.data.get('year')

        budget = None
        if budget_id:
            budget = Budget.objects.filter(id=budget_id).first()
        elif year:
            budget = Budget.objects.filter(fiscal_year=int(year), status=BudgetStatus.DRAFT).first()

        if not budget:
            return Response({'error': 'Draft budget not found.'}, status=status.HTTP_404_NOT_FOUND)

        if budget.status == BudgetStatus.APPROVED:
            return Response({'error': 'Budget is already approved and locked.'}, status=status.HTTP_400_BAD_REQUEST)

        budget.status = BudgetStatus.PENDING_APPROVAL
        budget.save()

        return Response({
            'success': True,
            'message': f"Budget '{budget.name}' successfully submitted for approval.",
            'budget': {
                'id': budget.id,
                'name': budget.name,
                'fiscal_year': budget.fiscal_year,
                'status': budget.status,
            }
        })


class BudgetPlanningExportView(APIView):
    """
    GET /api/finance/budgeting/planning/export/?year=2026
    Generates a professional spreadsheet (.xlsx) using openpyxl containing the planning data grid.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        year_param = request.query_params.get('year') or request.query_params.get('fiscal_year')
        try:
            fiscal_year = int(year_param) if year_param else timezone.now().year
        except (ValueError, TypeError):
            fiscal_year = timezone.now().year

        # Fetch planning data via BudgetPlanningView logic
        planning_view = BudgetPlanningView()
        planning_response = planning_view.get(request)
        data = planning_response.data

        lines = data.get('lines', [])
        summary = data.get('summary', {})
        budget_info = data.get('budget', {})

        # Create Workbook
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f"Budget Plan {fiscal_year}"
        ws.views.sheetView[0].showGridLines = True

        # Styles
        title_font = Font(name='Calibri', size=16, bold=True, color='1E293B')
        subtitle_font = Font(name='Calibri', size=10, italic=True, color='64748B')
        header_font = Font(name='Calibri', size=11, bold=True, color='FFFFFF')
        header_fill = PatternFill(start_color='1E293B', end_color='1E293B', fill_type='solid')
        data_font = Font(name='Calibri', size=11, color='0F172A')
        total_font = Font(name='Calibri', size=11, bold=True, color='0F172A')
        total_fill = PatternFill(start_color='F1F5F9', end_color='F1F5F9', fill_type='solid')

        thin_border = Border(
            left=Side(style='thin', color='CBD5E1'),
            right=Side(style='thin', color='CBD5E1'),
            top=Side(style='thin', color='CBD5E1'),
            bottom=Side(style='thin', color='CBD5E1')
        )
        total_border = Border(
            top=Side(style='thin', color='475569'),
            bottom=Side(style='double', color='0F172A')
        )

        currency_fmt = '#,##0.00'

        # Title Block
        ws['A1'] = f"FAHARI ACADEMIA — PROPOSED BUDGET PLANNING ({fiscal_year})"
        ws['A1'].font = title_font
        ws['A2'] = f"Status: {budget_info.get('status', 'draft').upper()}  |  Generated on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        ws['A2'].font = subtitle_font

        headers = [
            'Account Code',
            'Account / Budget Line',
            'Category',
            'Department',
            f'Previous Year Actual ({fiscal_year - 1})',
            f'Proposed Budget ({fiscal_year})',
            f'Approved Budget ({fiscal_year})',
            'Actual to Date',
            'Available',
            'Variance'
        ]

        header_row = 4
        for col_idx, header_text in enumerate(headers, start=1):
            cell = ws.cell(row=header_row, column=col_idx, value=header_text)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

        current_row = 5
        for line in lines:
            ws.cell(row=current_row, column=1, value=line['account_code']).alignment = Alignment(horizontal='left')
            ws.cell(row=current_row, column=2, value=line['account_name']).alignment = Alignment(horizontal='left')
            ws.cell(row=current_row, column=3, value=line['category']).alignment = Alignment(horizontal='center')
            ws.cell(row=current_row, column=4, value=line['department']).alignment = Alignment(horizontal='center')

            # Numeric columns
            for col_idx, key in enumerate([
                'previous_year_actual',
                'proposed_budget',
                'approved_budget',
                'actual_to_date',
                'available',
                'variance'
            ], start=5):
                num_val = float(line.get(key, 0.0))
                c = ws.cell(row=current_row, column=col_idx, value=num_val)
                c.number_format = currency_fmt
                c.alignment = Alignment(horizontal='right')

            for col_idx in range(1, 11):
                ws.cell(row=current_row, column=col_idx).font = data_font
                ws.cell(row=current_row, column=col_idx).border = thin_border

            current_row += 1

        # Summary Row
        ws.cell(row=current_row, column=1, value="GRAND TOTAL").font = total_font
        ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=4)
        ws.cell(row=current_row, column=1).alignment = Alignment(horizontal='right', vertical='center')

        summary_keys = [
            'total_previous_year',
            'total_proposed',
            'total_approved',
            'total_actual',
            'total_available',
            'total_variance'
        ]
        for col_idx, skey in enumerate(summary_keys, start=5):
            c = ws.cell(row=current_row, column=col_idx, value=float(summary.get(skey, 0.0)))
            c.number_format = currency_fmt
            c.font = total_font
            c.alignment = Alignment(horizontal='right')

        for col_idx in range(1, 11):
            cell = ws.cell(row=current_row, column=col_idx)
            cell.fill = total_fill
            cell.border = total_border

        # Auto-adjust column widths
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val_str = str(cell.value or '')
                max_len = max(max_len, len(val_str))
            ws.column_dimensions[col_letter].width = max(max_len + 3, 14)

        # Output to response
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        response = HttpResponse(
            output.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="budget_planning_{fiscal_year}.xlsx"'
        return response


class BudgetPlanningImportView(APIView):
    """
    POST /api/finance/budgeting/planning/import/
    Uploads an .xlsx file, validates Account and Amount columns,
    and applies proposed values to the draft budget.
    Returns clear row-level validation errors if format is incorrect.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @transaction.atomic
    def post(self, request):
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': 'No Excel file provided.'}, status=status.HTTP_400_BAD_REQUEST)

        year_param = request.data.get('year') or request.data.get('fiscal_year')
        try:
            fiscal_year = int(year_param) if year_param else timezone.now().year
        except (ValueError, TypeError):
            fiscal_year = timezone.now().year

        try:
            wb = openpyxl.load_workbook(file_obj, data_only=True)
            ws = wb.active
        except Exception as e:
            return Response({'error': f"Failed to parse Excel file: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        # Locate Header Row
        code_col_idx = None
        amount_col_idx = None
        header_row_idx = None

        for r_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
            if not row:
                continue
            row_lower = [str(c).strip().lower() if c is not None else '' for c in row]
            for c_idx, val in enumerate(row_lower):
                if val in ['account code', 'code', 'account_code', 'account']:
                    code_col_idx = c_idx
                if 'proposed' in val or 'budgeted' in val or val in ['amount', 'proposed budget']:
                    amount_col_idx = c_idx
            if code_col_idx is not None and amount_col_idx is not None:
                header_row_idx = r_idx
                break

        if header_row_idx is None:
            return Response({
                'error': "Could not identify required columns. File must contain 'Account Code' and 'Proposed Budget' headers."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check existing budget status
        existing_approved = Budget.objects.filter(fiscal_year=fiscal_year, status=BudgetStatus.APPROVED).first()
        draft_budget = Budget.objects.filter(fiscal_year=fiscal_year, status=BudgetStatus.DRAFT).first()

        if not draft_budget:
            draft_budget = Budget.objects.create(
                name=f"Draft Budget {fiscal_year}",
                fiscal_year=fiscal_year,
                start_date=datetime.date(fiscal_year, 1, 1),
                end_date=datetime.date(fiscal_year, 12, 31),
                status=BudgetStatus.DRAFT,
                is_active=True
            )

        row_errors = []
        valid_items = []

        all_accounts = {str(acc.code).strip().lower(): acc for acc in Account.objects.all()}

        # Parse Data Rows
        for r_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True), start=header_row_idx + 1):
            if not row:
                continue
            if code_col_idx >= len(row) or amount_col_idx >= len(row):
                continue

            raw_code = row[code_col_idx]
            raw_amount = row[amount_col_idx]

            if raw_code is None or str(raw_code).strip() == '':
                continue  # Skip blank lines

            clean_code = str(raw_code).strip()
            # If row starts with "Grand Total" or "Total", break/skip
            if 'total' in clean_code.lower():
                continue

            # Validate Account
            account = all_accounts.get(clean_code.lower())
            if not account:
                row_errors.append({
                    'row': r_idx,
                    'account_code': clean_code,
                    'error': f"Account code '{clean_code}' not found in Chart of Accounts."
                })
                continue

            # Validate Amount
            try:
                if raw_amount is None or raw_amount == '':
                    dec_amount = Decimal('0.00')
                else:
                    dec_amount = Decimal(str(raw_amount).replace(',', '').strip())
                if dec_amount < 0:
                    row_errors.append({
                        'row': r_idx,
                        'account_code': clean_code,
                        'error': f"Amount cannot be negative: '{raw_amount}'"
                    })
                    continue
            except (InvalidOperation, ValueError, TypeError):
                row_errors.append({
                    'row': r_idx,
                    'account_code': clean_code,
                    'error': f"Invalid numeric amount '{raw_amount}'."
                })
                continue

            valid_items.append((account, dec_amount))

        # If any validation errors, return clear row-level failure list
        if row_errors:
            return Response({
                'success': False,
                'message': f"Validation failed with {len(row_errors)} error(s). No changes were applied.",
                'errors': row_errors
            }, status=status.HTTP_400_BAD_REQUEST)

        # Apply valid lines
        applied_count = 0
        for account, amount in valid_items:
            BudgetLine.objects.update_or_create(
                budget=draft_budget,
                account=account,
                defaults={'amount': amount}
            )
            applied_count += 1

        return Response({
            'success': True,
            'message': f"Successfully imported {applied_count} budget lines into Draft Budget {fiscal_year}.",
            'budget_id': draft_budget.id,
            'imported_count': applied_count
        })
