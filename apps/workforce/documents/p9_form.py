"""
Official KRA P9 Form Data Provider.
Aggregates employee monthly payroll calculations across a calendar year
into the standard Kenya Revenue Authority (KRA) P9A Tax Deduction Card.
"""
from datetime import datetime, date
from typing import Dict, Any, Optional, List
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.utils.html import escape

from documents.models import DocumentTemplate
from documents.services.base_provider import BaseDocumentDataProvider
from workforce.core_models import Employee
from workforce.models import PayrollCalculation
from workforce.reports_pdf import get_tenant_currency


MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]


class P9FormDataProvider(BaseDocumentDataProvider):
    """
    Data provider for Official KRA P9 Tax Deduction Card.
    Accepts a workforce.Employee instance and optional year in extra_context.
    """

    def __init__(self, entity: Any, context: Optional[Dict[str, Any]] = None):
        self.employee: Optional[Employee] = None

        if isinstance(entity, Employee):
            self.employee = entity
        else:
            raise ValidationError(
                f"Unsupported entity type '{type(entity).__name__}'. "
                "P9FormDataProvider requires a workforce.Employee instance."
            )

        super().__init__(entity, context=context)

    def get_document_type(self) -> str:
        return "kra_p9_form"

    def get_document_title(self) -> str:
        return "KENYA REVENUE AUTHORITY — TAX DEDUCTION CARD (P9A)"

    def get_category(self) -> str:
        return DocumentTemplate.Category.P9_FORM

    def validate(self) -> None:
        super().validate()
        if not self.employee:
            raise ValidationError("A valid workforce.Employee instance is required.")

    def get_context_data(self) -> Dict[str, Any]:
        emp = self.employee
        target_year = int(self.extra_context.get("year", datetime.now().year))
        currency = get_tenant_currency()

        # Query all calculations for this employee for the target calendar year
        calcs = PayrollCalculation.objects.filter(
            employee=emp,
            payroll_period__start_date__year=target_year
        ).select_related('payroll_period').prefetch_related('details')

        # Index calculations by calendar month (1..12)
        calcs_by_month = {}
        for c in calcs:
            m = c.payroll_period.start_date.month
            calcs_by_month[m] = c

        monthly_rows: List[Dict[str, Any]] = []
        tot_basic = 0.0
        tot_benefits = 0.0
        tot_quarters = 0.0
        tot_gross = 0.0
        tot_e1 = 0.0
        tot_e2 = 0.0
        tot_e3 = 0.0
        tot_allowable_pension = 0.0
        tot_interest = 0.0
        tot_retirement_and_interest = 0.0
        tot_chargeable = 0.0
        tot_tax_charged = 0.0
        tot_relief = 0.0
        tot_paye = 0.0

        for month_idx in range(1, 13):
            month_name = MONTH_NAMES[month_idx - 1]
            calc = calcs_by_month.get(month_idx)

            if calc:
                basic = float(calc.basic_salary or 0.0)
                gross = float(calc.gross_pay or basic)
                benefits = max(0.0, gross - basic)
                quarters = 0.0

                # Pension / NSSF contributions
                pension_contrib = float(calc.pension_employee or 0.0)
                if pension_contrib <= 0.0:
                    # check deduction details
                    for d in calc.details.all():
                        if d.item_type == 'deduction' and ('nssf' in d.description.lower() or 'pension' in d.description.lower()):
                            pension_contrib += float(d.amount or 0.0)

                # Col E1: 30% of Basic Pay
                e1 = basic * 0.30
                # Col E2: Actual Contribution
                e2 = pension_contrib
                # Col E3: Statutory Limit (KES 20,000 / month)
                e3 = 20000.00
                # Col E: Allowable Retirement Contribution (lowest of E1, E2, E3)
                col_e = min(e1, e2, e3) if e2 > 0 else 0.0

                owner_interest = 0.0
                col_g = col_e + owner_interest
                chargeable = float(calc.taxable_income or max(0.0, gross - col_g))

                paye = float(calc.tax_amount or 0.0)
                # Standard personal relief per month in Kenya is KES 2,400.00
                personal_relief = 2400.00 if paye > 0 else 0.0
                tax_charged = paye + personal_relief
            else:
                basic = 0.0
                benefits = 0.0
                quarters = 0.0
                gross = 0.0
                col_e = 0.0
                col_g = 0.0
                chargeable = 0.0
                tax_charged = 0.0
                personal_relief = 0.0
                paye = 0.0

            # Accumulate totals
            tot_basic += basic
            tot_benefits += benefits
            tot_quarters += quarters
            tot_gross += gross
            tot_allowable_pension += col_e
            tot_retirement_and_interest += col_g
            tot_chargeable += chargeable
            tot_tax_charged += tax_charged
            tot_relief += personal_relief
            tot_paye += paye

            monthly_rows.append({
                "month": month_name,
                "basic": f"{basic:,.2f}",
                "benefits": f"{benefits:,.2f}",
                "quarters": f"{quarters:,.2f}",
                "gross": f"{gross:,.2f}",
                "pension": f"{col_e:,.2f}",
                "interest": "0.00",
                "retire_and_interest": f"{col_g:,.2f}",
                "chargeable": f"{chargeable:,.2f}",
                "tax_charged": f"{tax_charged:,.2f}",
                "relief": f"{personal_relief:,.2f}",
                "paye": f"{paye:,.2f}",
            })

        doc_ref = f"P9/{emp.employee_no}/{target_year}"

        return {
            "document_ref": doc_ref,
            "currency": currency,
            "tax_year": target_year,
            "employee": {
                "name": emp.get_full_name(),
                "employee_no": emp.employee_no,
                "kra_pin": getattr(emp, "kra_pin", "") or getattr(emp, "tax_pin", "") or "A000000000Z",
                "national_id": emp.national_id or "N/A",
                "department": emp.department.name if emp.department else "General Administration",
            },
            "rows": monthly_rows,
            "totals": {
                "basic": f"{tot_basic:,.2f}",
                "benefits": f"{tot_benefits:,.2f}",
                "quarters": f"{tot_quarters:,.2f}",
                "gross": f"{tot_gross:,.2f}",
                "pension": f"{tot_allowable_pension:,.2f}",
                "interest": "0.00",
                "retire_and_interest": f"{tot_retirement_and_interest:,.2f}",
                "chargeable": f"{tot_chargeable:,.2f}",
                "tax_charged": f"{tot_tax_charged:,.2f}",
                "relief": f"{tot_relief:,.2f}",
                "paye": f"{tot_paye:,.2f}",
            }
        }

    def render_body_html(self, context: Dict[str, Any]) -> str:
        emp = context.get("employee", {})
        inst = context.get("institution", {})
        year = context.get("tax_year", 2026)
        rows = context.get("rows", [])
        tot = context.get("totals", {})
        brand_primary = context.get("brand", {}).get("primary", "#17365D")

        inst_name = inst.get("name", "Fahari Academy")
        inst_pin = getattr(inst, "registration_number", "") or "P051000000X"

        table_rows = []
        for r in rows:
            table_rows.append(f"""
            <tr>
                <td style="font-weight: 600; text-align: left; padding: 4px 6px;">{r['month']}</td>
                <td style="text-align: right; padding: 4px 6px;">{r['basic']}</td>
                <td style="text-align: right; padding: 4px 6px;">{r['benefits']}</td>
                <td style="text-align: right; padding: 4px 6px;">{r['quarters']}</td>
                <td style="text-align: right; font-weight: 600; padding: 4px 6px;">{r['gross']}</td>
                <td style="text-align: right; padding: 4px 6px;">{r['pension']}</td>
                <td style="text-align: right; padding: 4px 6px;">{r['retire_and_interest']}</td>
                <td style="text-align: right; font-weight: 600; padding: 4px 6px;">{r['chargeable']}</td>
                <td style="text-align: right; padding: 4px 6px;">{r['tax_charged']}</td>
                <td style="text-align: right; padding: 4px 6px;">{r['relief']}</td>
                <td style="text-align: right; font-weight: 700; color: #b91c1c; padding: 4px 6px;">{r['paye']}</td>
            </tr>
            """)

        return f"""
        <div class="report-header" style="text-align: center; margin-bottom: 12px;">
            <div style="font-size: 13pt; font-weight: 900; color: #1e293b; letter-spacing: 0.5px; text-transform: uppercase;">
                KENYA REVENUE AUTHORITY — DOMESTIC TAXES DEPARTMENT
            </div>
            <div style="font-size: 12pt; font-weight: 800; color: {brand_primary}; margin-top: 2px;">
                TAX DEDUCTION CARD (P9A) — YEAR {year}
            </div>
            <p style="font-size: 8pt; color: #64748b; margin: 2px 0 0 0;">
                Document Reference: <strong>{escape(context.get('document_ref', ''))}</strong>
            </p>
        </div>

        <!-- Particulars of Employer and Employee -->
        <table style="width: 100%; font-size: 8.5pt; border: 1.5px solid #cbd5e1; border-collapse: collapse; margin-bottom: 12px; background: #f8fafc;">
            <tr>
                <td style="width: 50%; padding: 8px 12px; border-right: 1px solid #cbd5e1; vertical-align: top;">
                    <div><strong>Employer's Name:</strong> {escape(inst_name)}</div>
                    <div style="margin-top: 4px;"><strong>Employer's PIN:</strong> {escape(inst_pin)}</div>
                </td>
                <td style="width: 50%; padding: 8px 12px; vertical-align: top;">
                    <div><strong>Employee's Name:</strong> {escape(emp.get('name', ''))}</div>
                    <div style="margin-top: 4px;"><strong>Employee's PIN:</strong> {escape(emp.get('kra_pin', ''))} | <strong>Payroll No:</strong> {escape(emp.get('employee_no', ''))}</div>
                </td>
            </tr>
        </table>

        <!-- Standard P9 Tax Deduction Table -->
        <table class="data-table" style="width: 100%; font-size: 7.5pt; border-collapse: collapse; border: 1px solid #94a3b8;">
            <thead>
                <tr style="background: {brand_primary}; color: #ffffff; text-align: center;">
                    <th style="padding: 5px; width: 10%;">MONTH</th>
                    <th style="padding: 5px; width: 9%;">Basic Salary<br>(A)</th>
                    <th style="padding: 5px; width: 8%;">Benefits Non-Cash<br>(B)</th>
                    <th style="padding: 5px; width: 7%;">Value of Quarters<br>(C)</th>
                    <th style="padding: 5px; width: 10%;">Total Gross Pay<br>(D)</th>
                    <th style="padding: 5px; width: 9%;">Defined Pension<br>(E)</th>
                    <th style="padding: 5px; width: 9%;">Total Deduction<br>(G)</th>
                    <th style="padding: 5px; width: 10%;">Taxable Pay<br>(H)</th>
                    <th style="padding: 5px; width: 9%;">Tax Charged<br>(J)</th>
                    <th style="padding: 5px; width: 9%;">Personal Relief<br>(K)</th>
                    <th style="padding: 5px; width: 10%;">P.A.Y.E. Tax<br>(L)</th>
                </tr>
            </thead>
            <tbody>
                {''.join(table_rows)}
            </tbody>
            <tfoot>
                <tr style="background: #e2e8f0; font-weight: 800; border-top: 2px solid {brand_primary};">
                    <td style="text-align: left; padding: 6px;">TOTALS</td>
                    <td style="text-align: right; padding: 6px;">{tot.get('basic', '0.00')}</td>
                    <td style="text-align: right; padding: 6px;">{tot.get('benefits', '0.00')}</td>
                    <td style="text-align: right; padding: 6px;">{tot.get('quarters', '0.00')}</td>
                    <td style="text-align: right; padding: 6px; color: {brand_primary};">{tot.get('gross', '0.00')}</td>
                    <td style="text-align: right; padding: 6px;">{tot.get('pension', '0.00')}</td>
                    <td style="text-align: right; padding: 6px;">{tot.get('retire_and_interest', '0.00')}</td>
                    <td style="text-align: right; padding: 6px; color: {brand_primary};">{tot.get('chargeable', '0.00')}</td>
                    <td style="text-align: right; padding: 6px;">{tot.get('tax_charged', '0.00')}</td>
                    <td style="text-align: right; padding: 6px;">{tot.get('relief', '0.00')}</td>
                    <td style="text-align: right; padding: 6px; color: #b91c1c;">{tot.get('paye', '0.00')}</td>
                </tr>
            </tfoot>
        </table>

        <!-- Employer Certification Footer -->
        <div style="margin-top: 24px; page-break-inside: avoid; border: 1px solid #cbd5e1; background: #f8fafc; padding: 12px 16px; border-radius: 4px;">
            <div style="font-size: 8pt; font-weight: bold; color: {brand_primary}; text-transform: uppercase; margin-bottom: 6px;">
                Employer's Certificate of Tax Deductions
            </div>
            <p style="font-size: 7.5pt; color: #475569; margin: 0 0 16px 0; text-align: justify;">
                I/We certify that the particulars entered above are correct and that the total tax amounting to 
                <strong>KES {tot.get('paye', '0.00')}</strong> has been deducted and remitted to the Kenya Revenue Authority in accordance with the Income Tax Act.
            </p>
            <table style="width: 100%; font-size: 8pt;">
                <tr>
                    <td style="width: 45%;">
                        <div><strong>Employer's Signature:</strong> _____________________________</div>
                        <div style="margin-top: 4px; color: #64748b;">Authorized Signatory / Principal</div>
                    </td>
                    <td style="width: 20%;"></td>
                    <td style="width: 35%; text-align: right;">
                        <div><strong>Date:</strong> ______________________</div>
                        <div style="margin-top: 4px; color: #64748b;">Official Institutional Stamp</div>
                    </td>
                </tr>
            </table>
        </div>
        """
