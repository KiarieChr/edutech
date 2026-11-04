"""
Employment Contract Data Provider.
Integrates EmployeeContract records with Document Studio and WeasyPrint paged PDF engine.
"""
from datetime import datetime, date
from typing import Dict, Any, Optional
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.utils.html import escape

from documents.models import DocumentTemplate
from documents.services.base_provider import BaseDocumentDataProvider
from workforce.core_models import EmployeeContract
from workforce.reports_pdf import get_tenant_currency


class EmployeeContractDataProvider(BaseDocumentDataProvider):
    """
    Data provider for Official Institutional Employment Contracts.
    Accepts a workforce.EmployeeContract instance.
    """

    def __init__(self, entity: Any, context: Optional[Dict[str, Any]] = None):
        self.contract: Optional[EmployeeContract] = None

        if isinstance(entity, EmployeeContract):
            self.contract = entity
        else:
            raise ValidationError(
                f"Unsupported entity type '{type(entity).__name__}'. "
                "EmployeeContractDataProvider requires a workforce.EmployeeContract instance."
            )

        super().__init__(entity, context=context)

    def get_document_type(self) -> str:
        return "employment_contract"

    def get_document_title(self) -> str:
        return "OFFICIAL EMPLOYMENT CONTRACT AGREEMENT"

    def get_category(self) -> str:
        return DocumentTemplate.Category.EMPLOYMENT_CONTRACT

    def validate(self) -> None:
        super().validate()
        if not self.contract:
            raise ValidationError("A valid workforce.EmployeeContract instance is required.")

    def get_context_data(self) -> Dict[str, Any]:
        c = self.contract
        emp = c.employee
        currency = get_tenant_currency()

        role_title = "Staff Member"
        try:
            assignment = emp.job_assignments.filter(
                is_primary_assignment=True, effective_to__isnull=True
            ).first()
            if assignment and assignment.job_title:
                role_title = assignment.job_title.title
        except Exception:
            pass

        start_str = c.start_date.strftime("%d %B %Y") if c.start_date else datetime.now().strftime("%d %B %Y")
        end_str = c.end_date.strftime("%d %B %Y") if c.end_date else "Indefinite / Permanent"

        doc_ref = f"CTR/{emp.employee_no}/{c.id:04d}"

        return {
            "document_ref": doc_ref,
            "currency": currency,
            "contract": {
                "id": c.id,
                "contract_type": c.get_contract_type_display(),
                "start_date": start_str,
                "end_date": end_str,
                "gross_salary": f"{float(c.gross_salary):,.2f}",
                "gross_salary_num": float(c.gross_salary),
                "status": c.get_status_display(),
            },
            "employee": {
                "employee_no": emp.employee_no,
                "full_name": emp.get_full_name(),
                "national_id": emp.national_id or "N/A",
                "passport_number": emp.passport_number or "N/A",
                "email": emp.official_email or emp.personal_email or "N/A",
                "phone": emp.phone_primary or "N/A",
                "kra_pin": getattr(emp, "kra_pin", "") or getattr(emp, "tax_pin", "") or "N/A",
                "nssf_number": getattr(emp, "nssf_number", "") or "N/A",
                "nhif_number": getattr(emp, "nhif_number", "") or "N/A",
                "bank_name": getattr(emp, "bank_name", "") or "N/A",
                "bank_account_number": getattr(emp, "bank_account_number", "") or "N/A",
                "department": emp.department.name if emp.department else "General Administration",
                "campus": emp.campus.name if emp.campus else "Main Campus",
                "role_title": role_title,
                "notice_period_days": getattr(emp, "notice_period_days", 30) or 30,
            }
        }

    def render_body_html(self, context: Dict[str, Any]) -> str:
        ctr = context.get("contract", {})
        emp = context.get("employee", {})
        inst = context.get("institution", {})
        currency = context.get("currency", "KES")
        brand_primary = context.get("brand", {}).get("primary", "#17365D")
        brand_secondary = context.get("brand", {}).get("secondary", "#1F6B4F")

        inst_name = inst.get("name", "Fahari Academy")
        inst_address = inst.get("address", "P.O. Box Nairobi, Kenya")

        return f"""
        <div class="report-header" style="text-align: center; margin-bottom: 20px;">
            <h1 class="doc-title" style="font-size: 16pt; font-weight: 800; color: {brand_primary}; margin: 0 0 6px 0; text-transform: uppercase;">
                {escape(self.get_document_title())}
            </h1>
            <p class="doc-meta" style="font-size: 9pt; color: #475569; margin: 0;">
                Contract Ref: <strong>{escape(context.get('document_ref', ''))}</strong> | 
                Terms: <strong>{escape(ctr.get('contract_type', ''))}</strong> | 
                Effective Date: <strong>{escape(ctr.get('start_date', ''))}</strong>
            </p>
        </div>

        <!-- Preamble Section -->
        <div style="font-size: 9pt; line-height: 1.6; color: #1e293b; margin-bottom: 18px; text-align: justify;">
            <p>
                This Employment Agreement (the <strong>"Agreement"</strong>) is entered into as of 
                <strong>{escape(ctr.get('start_date', ''))}</strong>, by and between:
            </p>
            <div style="background: #f8fafc; border-left: 3.5px solid {brand_primary}; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px;">
                <strong>1. THE EMPLOYER:</strong> <strong>{escape(inst_name)}</strong>, located at {escape(inst_address)} (hereinafter referred to as the <em>"Employer"</em> or the <em>"Institution"</em>), and
            </div>
            <div style="background: #f8fafc; border-left: 3.5px solid {brand_secondary}; padding: 10px 14px; border-radius: 4px;">
                <strong>2. THE EMPLOYEE:</strong> <strong>{escape(emp.get('full_name', ''))}</strong>, National ID / Passport No: <strong>{escape(emp.get('national_id', 'N/A'))}</strong>, KRA PIN: <strong>{escape(emp.get('kra_pin', 'N/A'))}</strong> (hereinafter referred to as the <em>"Employee"</em>).
            </div>
        </div>

        <!-- Agreement Terms & Clauses -->
        <div style="font-size: 9pt; line-height: 1.6; color: #1e293b;">
            
            <!-- Clause 1 -->
            <div style="margin-bottom: 14px;">
                <h3 style="font-size: 10pt; font-weight: 700; color: {brand_primary}; margin: 0 0 4px 0;">
                    1. APPOINTMENT AND SCOPE OF WORK
                </h3>
                <p style="margin: 0; text-align: justify;">
                    The Employer hereby engages the Employee, and the Employee accepts employment, in the position of 
                    <strong>{escape(emp.get('role_title', 'Staff Member'))}</strong> within the Department of 
                    <strong>{escape(emp.get('department', 'General Administration'))}</strong> at 
                    <strong>{escape(emp.get('campus', 'Main Campus'))}</strong>. 
                    The Employee will perform all duties customarily associated with this position and other tasks assigned in furtherance of the Institution's mission.
                </p>
            </div>

            <!-- Clause 2 -->
            <div style="margin-bottom: 14px;">
                <h3 style="font-size: 10pt; font-weight: 700; color: {brand_primary}; margin: 0 0 4px 0;">
                    2. COMMENCEMENT AND DURATION
                </h3>
                <p style="margin: 0; text-align: justify;">
                    This appointment commences on <strong>{escape(ctr.get('start_date', ''))}</strong> and shall operate on a 
                    <strong>{escape(ctr.get('contract_type', ''))}</strong> basis. 
                    {'For fixed-term engagement, this contract expires on <strong>' + escape(ctr.get('end_date', '')) + '</strong> unless renewed in writing.' if ctr.get('contract_type') != 'Permanent' else 'The engagement shall continue until terminated in accordance with the provisions of this Agreement and Kenyan Employment Law.'}
                </p>
            </div>

            <!-- Clause 3: Remuneration Box -->
            <div style="margin-bottom: 16px;">
                <h3 style="font-size: 10pt; font-weight: 700; color: {brand_primary}; margin: 0 0 6px 0;">
                    3. REMUNERATION AND COMPENSATION
                </h3>
                <div style="background: #f1f5f9; border: 1.5px solid {brand_primary}; border-radius: 6px; padding: 12px 18px; margin-bottom: 6px; display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <span style="font-size: 8pt; color: #475569; text-transform: uppercase; font-weight: bold;">Monthly Gross Salary</span>
                        <div style="font-size: 8pt; color: #64748b; margin-top: 2px;">Payable monthly in arrears via designated bank account</div>
                    </div>
                    <div style="text-align: right;">
                        <span style="font-size: 14pt; font-weight: 900; color: {brand_primary};">
                            {currency} {escape(ctr.get('gross_salary', '0.00'))}
                        </span>
                    </div>
                </div>
                <p style="margin: 0; text-align: justify; font-size: 8.5pt; color: #475569;">
                    The gross salary is subject to statutory deductions required by the laws of the Republic of Kenya, including Pay As You Earn (P.A.Y.E.), National Social Security Fund (N.S.S.F.), Social Health Insurance Fund (S.H.I.F. / N.H.I.F.), and the Affordable Housing Levy.
                </p>
            </div>

            <!-- Clause 4 -->
            <div style="margin-bottom: 14px;">
                <h3 style="font-size: 10pt; font-weight: 700; color: {brand_primary}; margin: 0 0 4px 0;">
                    4. WORKING HOURS AND CODE OF ETHICS
                </h3>
                <p style="margin: 0; text-align: justify;">
                    Standard working hours and duties shall align with the official Institutional Staff Handbook. 
                    The Employee pledges adherence to professional academic and corporate conduct, maintaining the highest standards of integrity, child safety, student welfare, and confidentiality regarding proprietary institutional data.
                </p>
            </div>

            <!-- Clause 5 -->
            <div style="margin-bottom: 20px;">
                <h3 style="font-size: 10pt; font-weight: 700; color: {brand_primary}; margin: 0 0 4px 0;">
                    5. TERMINATION AND NOTICE
                </h3>
                <p style="margin: 0; text-align: justify;">
                    Either party may terminate this employment agreement by tendering 
                    <strong>{escape(str(emp.get('notice_period_days', 30)))} days</strong> prior written notice, 
                    or by paying an equivalent salary in lieu of notice, except in cases of gross misconduct warranting summary dismissal under the Employment Act 2007.
                </p>
            </div>
        </div>

        <!-- Signature Execution Blocks -->
        <div style="margin-top: 36px; page-break-inside: avoid; border-top: 2px solid {brand_primary}; padding-top: 20px;">
            <p style="font-size: 9pt; font-weight: bold; color: {brand_primary}; text-transform: uppercase; margin-bottom: 16px;">
                IN WITNESS WHEREOF, the parties hereto have duly executed this Agreement:
            </p>
            <table class="grid-table" style="width: 100%; font-size: 8.5pt;">
                <tr>
                    <td style="width: 45%; vertical-align: top;">
                        <div style="border-bottom: 1px solid #64748b; height: 40px; margin-bottom: 6px;"></div>
                        <div><strong>Signed for and on behalf of Employer:</strong></div>
                        <div style="color: #475569; margin-top: 2px;">Authorized Signatory / Principal</div>
                        <div style="color: #64748b; font-size: 8pt; margin-top: 4px;">Date: ________________________</div>
                    </td>
                    <td style="width: 10%;"></td>
                    <td style="width: 45%; vertical-align: top;">
                        <div style="border-bottom: 1px solid #64748b; height: 40px; margin-bottom: 6px;"></div>
                        <div><strong>Signed by the Employee:</strong></div>
                        <div style="color: #475569; margin-top: 2px;">{escape(emp.get('full_name', ''))}</div>
                        <div style="color: #64748b; font-size: 8pt; margin-top: 4px;">Date: ________________________</div>
                    </td>
                </tr>
            </table>
        </div>
        """
