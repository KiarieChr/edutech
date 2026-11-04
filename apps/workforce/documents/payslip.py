"""
Official Employee Payslip Data Provider.
Integrates HR/Payroll calculations with Document Studio and WeasyPrint paged PDF engine.
"""
from datetime import datetime, date
from typing import Dict, Any, Optional
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.utils.html import escape

from documents.models import DocumentTemplate
from documents.services.base_provider import BaseDocumentDataProvider
from workforce.models import PayrollCalculation, PayrollCalculationDetail
from workforce.reports_pdf import get_tenant_currency


class PayslipDataProvider(BaseDocumentDataProvider):
    """
    Data provider for Official Archival and Distributed Employee Payslips.
    Accepts a workforce.PayrollCalculation instance.
    """

    def __init__(self, entity: Any, context: Optional[Dict[str, Any]] = None):
        self.calculation: Optional[PayrollCalculation] = None

        if isinstance(entity, PayrollCalculation):
            self.calculation = entity
        else:
            raise ValidationError(
                f"Unsupported entity type '{type(entity).__name__}'. "
                "PayslipDataProvider requires a workforce.PayrollCalculation instance."
            )

        super().__init__(entity, context=context)

    def get_document_type(self) -> str:
        return "official_payslip"

    def get_document_title(self) -> str:
        return "OFFICIAL EMPLOYEE PAYSLIP"

    def get_category(self) -> str:
        return DocumentTemplate.Category.PAYSLIP

    def validate(self) -> None:
        super().validate()
        if not self.calculation:
            raise ValidationError("A valid workforce.PayrollCalculation instance is required.")

    def get_context_data(self) -> Dict[str, Any]:
        calc = self.calculation
        emp = calc.employee
        period = calc.payroll_period
        currency = getattr(period, "currency", None) or get_tenant_currency()

        # Gather employee assignment / role if available
        role_title = "Staff Member"
        try:
            assignment = emp.job_assignments.filter(
                is_primary_assignment=True, effective_to__isnull=True
            ).first()
            if assignment and assignment.job_title:
                role_title = assignment.job_title.title
        except Exception:
            pass

        # Details grouping
        all_details = list(calc.details.all())
        earnings = []
        deductions = []

        for d in all_details:
            amt = float(d.amount or 0.0)
            if d.item_type == "earning":
                earnings.append({
                    "description": d.description,
                    "amount": f"{amt:,.2f}",
                    "amount_num": amt,
                    "is_taxable": d.is_taxable,
                })
            else:
                deductions.append({
                    "description": d.description,
                    "amount": f"{amt:,.2f}",
                    "amount_num": amt,
                })

        # Ensure Basic Pay is in earnings if not represented in details
        has_basic_in_details = any("basic" in e["description"].lower() for e in earnings)
        if not has_basic_in_details and calc.basic_salary and float(calc.basic_salary) > 0:
            earnings.insert(0, {
                "description": "Basic Salary",
                "amount": f"{float(calc.basic_salary):,.2f}",
                "amount_num": float(calc.basic_salary),
                "is_taxable": True,
            })

        # Ensure PAYE is listed in deductions if tax_amount > 0 and not in details
        has_tax_in_details = any("paye" in d["description"].lower() or "income tax" in d["description"].lower() for d in deductions)
        if not has_tax_in_details and calc.tax_amount and float(calc.tax_amount) > 0:
            deductions.append({
                "description": "P.A.Y.E. (Income Tax)",
                "amount": f"{float(calc.tax_amount):,.2f}",
                "amount_num": float(calc.tax_amount),
            })

        # Bank info
        bank_name = getattr(emp, "bank_name", "") or "Direct Transfer"
        bank_branch = getattr(emp, "bank_branch", "") or ""
        bank_acc = calc.bank_account_number or getattr(emp, "bank_account_number", "") or "On File"

        doc_ref = f"PS/{period.period_name.replace(' ', '_')}/{emp.employee_no}"

        return {
            "document_ref": doc_ref,
            "currency": currency,
            "payslip": {
                "period_name": period.period_name,
                "pay_date": period.payment_date.strftime("%d %B %Y") if period.payment_date else datetime.now().strftime("%d %B %Y"),
                "start_date": period.start_date.strftime("%d %b %Y") if period.start_date else "",
                "end_date": period.end_date.strftime("%d %b %Y") if period.end_date else "",
                "employee_no": emp.employee_no,
                "employee_name": emp.get_full_name(),
                "role_title": role_title,
                "department": emp.department.name if emp.department else "General Administration",
                "campus": emp.campus.name if emp.campus else "Main Campus",
                "national_id": emp.national_id or "N/A",
                "kra_pin": getattr(emp, "kra_pin", "") or getattr(emp, "tax_pin", "") or "N/A",
                "nssf_number": getattr(emp, "nssf_number", "") or "N/A",
                "nhif_number": getattr(emp, "nhif_number", "") or "N/A",
                "bank_name": bank_name,
                "bank_branch": bank_branch,
                "bank_account_number": bank_acc,
                "payment_method": calc.get_payment_method_display() if hasattr(calc, "get_payment_method_display") else calc.payment_method,
                "basic_salary": f"{float(calc.basic_salary):,.2f}",
                "gross_pay": f"{float(calc.gross_pay):,.2f}",
                "taxable_income": f"{float(calc.taxable_income):,.2f}",
                "total_deductions": f"{float(calc.total_deductions):,.2f}",
                "net_pay": f"{float(calc.net_pay):,.2f}",
                "net_pay_num": float(calc.net_pay),
                "earnings": earnings,
                "deductions": deductions,
            }
        }

    def render_body_html(self, context: Dict[str, Any]) -> str:
        ps = context.get("payslip", {})
        currency = context.get("currency", "KES")
        brand_primary = context.get("brand", {}).get("primary", "#17365D")
        brand_secondary = context.get("brand", {}).get("secondary", "#1F6B4F")
        brand_accent = context.get("brand", {}).get("accent", "#D4A72C")

        earnings = ps.get("earnings", [])
        deductions = ps.get("deductions", [])

        # Build Earnings table rows
        earning_rows = []
        for idx, e in enumerate(earnings):
            earning_rows.append(f"""
            <tr>
                <td style="text-align: center; font-weight: 600; width: 10%;">{idx + 1}</td>
                <td style="font-weight: 600;">{escape(e['description'])}</td>
                <td style="text-align: right; font-weight: 700;">{currency} {escape(e['amount'])}</td>
            </tr>
            """)
        if not earning_rows:
            earning_rows.append(f"""
            <tr>
                <td colspan="3" style="text-align: center; color: #64748b; font-style: italic;">No separate earnings items recorded</td>
            </tr>
            """)

        # Build Deductions table rows
        deduction_rows = []
        for idx, d in enumerate(deductions):
            deduction_rows.append(f"""
            <tr>
                <td style="text-align: center; font-weight: 600; width: 10%;">{idx + 1}</td>
                <td style="font-weight: 600;">{escape(d['description'])}</td>
                <td style="text-align: right; font-weight: 700; color: #b91c1c;">{currency} {escape(d['amount'])}</td>
            </tr>
            """)
        if not deduction_rows:
            deduction_rows.append(f"""
            <tr>
                <td colspan="3" style="text-align: center; color: #64748b; font-style: italic;">No deductions recorded</td>
            </tr>
            """)

        return f"""
        <div class="report-header" style="text-align: center; margin-bottom: 16px;">
            <h1 class="doc-title" style="font-size: 16pt; font-weight: 800; color: {brand_primary}; margin: 0 0 4px 0; text-transform: uppercase;">
                {escape(self.get_document_title())}
            </h1>
            <p class="doc-meta" style="font-size: 9pt; color: #475569; margin: 0;">
                Payroll Period: <strong>{escape(ps.get('period_name', ''))}</strong> | 
                Payment Date: <strong>{escape(ps.get('pay_date', ''))}</strong> | 
                Ref: <strong>{escape(context.get('document_ref', ''))}</strong>
            </p>
        </div>

        <!-- Employee Particulars Grid Card -->
        <div class="info-card" style="margin-bottom: 16px; border-left: 3.5px solid {brand_primary}; background: #f8fafc; padding: 12px 16px; border-radius: 6px;">
            <table class="grid-table" style="width: 100%; font-size: 8.5pt; border-collapse: collapse;">
                <tr>
                    <td style="width: 50%; vertical-align: top; padding-right: 14px; border-right: 1px solid #e2e8f0;">
                        <div style="margin-bottom: 5px;"><strong>Employee Name:</strong> {escape(ps.get('employee_name', ''))}</div>
                        <div style="margin-bottom: 5px;"><strong>Employee Number:</strong> {escape(ps.get('employee_no', ''))}</div>
                        <div style="margin-bottom: 5px;"><strong>Designation / Role:</strong> {escape(ps.get('role_title', ''))}</div>
                        <div style="margin-bottom: 5px;"><strong>Department:</strong> {escape(ps.get('department', ''))}</div>
                        <div><strong>Campus:</strong> {escape(ps.get('campus', 'Main Campus'))}</div>
                    </td>
                    <td style="width: 50%; vertical-align: top; padding-left: 14px;">
                        <div style="margin-bottom: 5px;"><strong>KRA PIN:</strong> {escape(ps.get('kra_pin', 'N/A'))}</div>
                        <div style="margin-bottom: 5px;"><strong>NSSF Number:</strong> {escape(ps.get('nssf_number', 'N/A'))}</div>
                        <div style="margin-bottom: 5px;"><strong>NHIF/SHIF No:</strong> {escape(ps.get('nhif_number', 'N/A'))}</div>
                        <div style="margin-bottom: 5px;"><strong>Payment Method:</strong> {escape(ps.get('payment_method', 'Bank Transfer'))}</div>
                        <div><strong>Bank & Account:</strong> {escape(ps.get('bank_name', ''))} ({escape(ps.get('bank_account_number', ''))})</div>
                    </td>
                </tr>
            </table>
        </div>

        <!-- Dual Column Earnings & Deductions Tables -->
        <table style="width: 100%; border-collapse: separate; border-spacing: 12px 0; margin-bottom: 16px;">
            <tr>
                <!-- Earnings Column -->
                <td style="width: 50%; vertical-align: top; padding: 0;">
                    <div style="background: {brand_primary}; color: #ffffff; padding: 6px 12px; font-size: 9pt; font-weight: bold; border-radius: 4px 4px 0 0; text-transform: uppercase;">
                        Earnings (Remuneration)
                    </div>
                    <table class="data-table" style="width: 100%; font-size: 8.5pt; border: 1px solid #cbd5e1; border-top: none;">
                        <thead>
                            <tr style="background: #f1f5f9; color: #334155;">
                                <th style="width: 10%; text-align: center; padding: 6px 8px;">#</th>
                                <th style="width: 55%; text-align: left; padding: 6px 8px;">Description</th>
                                <th style="width: 35%; text-align: right; padding: 6px 8px;">Amount</th>
                            </tr>
                        </thead>
                        <tbody>
                            {''.join(earning_rows)}
                        </tbody>
                        <tfoot>
                            <tr style="background: #e2e8f0; font-weight: bold; border-top: 1.5px solid {brand_primary};">
                                <td colspan="2" style="padding: 7px 10px; text-transform: uppercase;">Total Gross Pay</td>
                                <td style="text-align: right; padding: 7px 10px; color: {brand_primary};">{currency} {escape(ps.get('gross_pay', '0.00'))}</td>
                            </tr>
                        </tfoot>
                    </table>
                </td>

                <!-- Deductions Column -->
                <td style="width: 50%; vertical-align: top; padding: 0;">
                    <div style="background: #991b1b; color: #ffffff; padding: 6px 12px; font-size: 9pt; font-weight: bold; border-radius: 4px 4px 0 0; text-transform: uppercase;">
                        Deductions & Statutory
                    </div>
                    <table class="data-table" style="width: 100%; font-size: 8.5pt; border: 1px solid #cbd5e1; border-top: none;">
                        <thead>
                            <tr style="background: #f1f5f9; color: #334155;">
                                <th style="width: 10%; text-align: center; padding: 6px 8px;">#</th>
                                <th style="width: 55%; text-align: left; padding: 6px 8px;">Description</th>
                                <th style="width: 35%; text-align: right; padding: 6px 8px;">Amount</th>
                            </tr>
                        </thead>
                        <tbody>
                            {''.join(deduction_rows)}
                        </tbody>
                        <tfoot>
                            <tr style="background: #e2e8f0; font-weight: bold; border-top: 1.5px solid #991b1b;">
                                <td colspan="2" style="padding: 7px 10px; text-transform: uppercase;">Total Deductions</td>
                                <td style="text-align: right; padding: 7px 10px; color: #991b1b;">{currency} {escape(ps.get('total_deductions', '0.00'))}</td>
                            </tr>
                        </tfoot>
                    </table>
                </td>
            </tr>
        </table>

        <!-- Net Take-Home Pay Callout Banner -->
        <div style="background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%); border: 2px solid {brand_secondary}; border-radius: 8px; padding: 14px 20px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;">
            <div>
                <span style="font-size: 8.5pt; color: #166534; text-transform: uppercase; font-weight: 800; letter-spacing: 0.5px;">Net Take-Home Pay</span>
                <div style="font-size: 8pt; color: #15803d; margin-top: 3px;">
                    Taxable Income: <strong>{currency} {escape(ps.get('taxable_income', '0.00'))}</strong>
                </div>
            </div>
            <div style="text-align: right;">
                <span style="font-size: 16pt; font-weight: 900; color: #14532d;">
                    {currency} {escape(ps.get('net_pay', '0.00'))}
                </span>
            </div>
        </div>

        <!-- Endorsement & Verification Footer -->
        <div style="margin-top: 24px; page-break-inside: avoid; border-top: 1px dashed #cbd5e1; padding-top: 16px;">
            <table style="width: 100%; font-size: 8pt; color: #475569;">
                <tr>
                    <td style="width: 50%; vertical-align: top;">
                        <p style="margin: 0 0 4px 0;"><strong>Confidential Document:</strong> This document contains private payroll details intended solely for the named employee.</p>
                        <p style="margin: 0;">Generated electronically via Fahari Academia Institutional Document Studio.</p>
                    </td>
                    <td style="width: 50%; text-align: right; vertical-align: top;">
                        <div style="display: inline-block; text-align: center;">
                            <div style="border-bottom: 1px solid #94a3b8; width: 180px; margin-bottom: 4px;"></div>
                            <span style="font-weight: 700; color: #334155;">Authorized Payroll Officer</span>
                        </div>
                    </td>
                </tr>
            </table>
        </div>
        """
