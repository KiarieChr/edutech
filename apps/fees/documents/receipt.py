"""
Official Receipt Data Provider (Phase 3).
Provides formal institutional PDF receipt generation via Document Design Studio and WeasyPrint,
while fully preserving existing POS and thermal receipt printers.
"""
from datetime import datetime, date
from typing import Dict, Any, Optional
from django.core.exceptions import ValidationError
from django.utils.html import escape

from documents.models import DocumentTemplate
from documents.services.base_provider import BaseDocumentDataProvider
from finance.models import Receipt


class ReceiptDataProvider(BaseDocumentDataProvider):
    """
    Data provider for Official Archival Fee Receipts.
    Accepts a finance.Receipt instance.
    """

    def __init__(self, entity: Any, context: Optional[Dict[str, Any]] = None):
        self.receipt: Optional[Receipt] = None

        if isinstance(entity, Receipt):
            self.receipt = entity
        else:
            raise ValidationError(
                f"Unsupported entity type '{type(entity).__name__}'. "
                "ReceiptDataProvider requires a finance.Receipt instance."
            )

        super().__init__(entity, context=context)

    def get_document_type(self) -> str:
        return "official_receipt"

    def get_document_title(self) -> str:
        return "OFFICIAL FEE RECEIPT"

    def get_category(self) -> str:
        return DocumentTemplate.Category.RECEIPT

    def validate(self) -> None:
        super().validate()
        if not self.receipt:
            raise ValidationError("A valid finance.Receipt instance is required.")

    def get_context_data(self) -> Dict[str, Any]:
        r = self.receipt
        st = getattr(r, "student", None)
        user = getattr(st, "student", None) if st else None

        student_name = ""
        adm_no = ""
        class_name = ""
        if user:
            student_name = getattr(user, "get_full_name", lambda: "")() or f"{user.first_name} {user.last_name}".strip()
        if st:
            adm_no = getattr(st, "admission_number", "")
            grade_obj = getattr(st, "current_grade", None)
            class_name = getattr(grade_obj, "name", "")

        payer = r.payer_name or student_name or "Parent / Guardian"
        rcpt_no = r.receipt_number or f"REC-{r.id:06d}"
        date_str = r.received_date.strftime("%d %B %Y") if r.received_date else datetime.now().strftime("%d %B %Y")
        pay_method = r.payment_method.name if r.payment_method else "Direct Payment"
        amount = float(r.amount_received or 0.0)

        # Allocations
        allocations = []
        raw_allocs = r.allocations.select_related("invoice").all() if hasattr(r, "allocations") else []
        for a in raw_allocs:
            inv = a.invoice
            allocations.append({
                "invoice_number": inv.invoice_number if inv else "Direct Fee",
                "term": getattr(inv.term, "name", "") if inv and inv.term else "Tuition / General",
                "amount": f"{float(a.amount_allocated):,.2f}",
            })

        if not allocations:
            allocations.append({
                "invoice_number": "Fee Payment",
                "term": "General School Fees",
                "amount": f"{amount:,.2f}",
            })

        issued_by = getattr(r.received_by, "get_full_name", lambda: "")() if r.received_by else "Cashier"

        return {
            "document_ref": f"REC/{rcpt_no}",
            "receipt": {
                "receipt_number": rcpt_no,
                "date": date_str,
                "payer_name": payer,
                "student_name": student_name,
                "admission_number": adm_no,
                "class_name": class_name,
                "payment_method": pay_method,
                "reference": r.reference or "N/A",
                "amount_received": f"{amount:,.2f}",
                "amount_figure": amount,
                "status": r.get_status_display() if hasattr(r, "get_status_display") else "Posted",
                "notes": r.notes or "Fees payment received in good order.",
                "issued_by": issued_by or "Authorized Bursar",
                "allocations": allocations,
            }
        }

    def render_body_html(self, context: Dict[str, Any]) -> str:
        rc = context.get("receipt", {})
        allocations = rc.get("allocations", [])
        brand_primary = context.get("brand", {}).get("primary", "#17365D")
        brand_secondary = context.get("brand", {}).get("secondary", "#1F6B4F")

        alloc_rows = []
        for idx, a in enumerate(allocations):
            alloc_rows.append(f"""
            <tr>
                <td style="text-align: center; font-weight: bold; width: 8%;">{idx + 1}</td>
                <td style="font-weight: 600;">{escape(a['invoice_number'])}</td>
                <td>{escape(a['term'])}</td>
                <td style="text-align: right; font-weight: 700;">KES {escape(a['amount'])}</td>
            </tr>
            """)

        return f"""
        <div class="report-header">
            <h1 class="doc-title">{escape(self.get_document_title())}</h1>
            <p class="doc-meta">
                Receipt No: <strong>{escape(rc.get('receipt_number', ''))}</strong> | 
                Payment Date: <strong>{escape(rc.get('date', ''))}</strong> | 
                Status: <strong>{escape(rc.get('status', 'Posted'))}</strong>
            </p>
        </div>

        <!-- Receipt Particulars Card -->
        <div class="info-card" style="margin-bottom: 16px; border-left: 3.5px solid {brand_primary};">
            <table class="grid-table" style="width: 100%; font-size: 8.5pt;">
                <tr>
                    <td style="width: 50%; vertical-align: top; padding-right: 12px;">
                        <div style="margin-bottom: 4px;"><strong>Received From:</strong> {escape(rc.get('payer_name', ''))}</div>
                        <div style="margin-bottom: 4px;"><strong>Student Name:</strong> {escape(rc.get('student_name', 'N/A'))}</div>
                        <div><strong>Admission No:</strong> {escape(rc.get('admission_number', 'N/A'))}</div>
                    </td>
                    <td style="width: 50%; vertical-align: top; padding-left: 12px;">
                        <div style="margin-bottom: 4px;"><strong>Payment Method:</strong> {escape(rc.get('payment_method', ''))}</div>
                        <div style="margin-bottom: 4px;"><strong>Transaction Ref:</strong> {escape(rc.get('reference', ''))}</div>
                        <div><strong>Class / Grade:</strong> {escape(rc.get('class_name', 'General'))}</div>
                    </td>
                </tr>
            </table>
        </div>

        <!-- Fee Allocations Table -->
        <table class="data-table">
            <thead>
                <tr>
                    <th style="width: 8%; text-align: center;">#</th>
                    <th style="width: 37%;">Invoice / Fee Item</th>
                    <th style="width: 30%;">Description / Term</th>
                    <th style="width: 25%; text-align: right;">Amount Allocated</th>
                </tr>
            </thead>
            <tbody>
                {''.join(alloc_rows)}
            </tbody>
        </table>

        <!-- Total Box -->
        <div style="margin-top: 15px; background: #f8fafc; border: 1.5px solid {brand_primary}; border-radius: 6px; padding: 12px 18px; display: flex; justify-content: space-between; align-items: center;">
            <div>
                <span style="font-size: 8pt; color: #64748b; text-transform: uppercase; font-weight: bold;">Total Amount Received</span>
                <div style="font-size: 8pt; color: #475569; font-style: italic; margin-top: 2px;">{escape(rc.get('notes', ''))}</div>
            </div>
            <div style="text-align: right;">
                <span style="font-size: 14pt; font-weight: 900; color: {brand_primary};">KES {escape(rc.get('amount_received', '0.00'))}</span>
            </div>
        </div>

        <!-- Signatures -->
        <div style="margin-top: 40px; page-break-inside: avoid;">
            <table class="grid-table" style="width: 100%; font-size: 8.5pt;">
                <tr>
                    <td style="width: 45%;">
                        <div style="border-bottom: 1px solid #94a3b8; width: 80%; height: 35px;"></div>
                        <div style="margin-top: 5px; font-weight: 700; color: #334155;">Issued By: {escape(rc.get('issued_by', 'Cashier'))}</div>
                    </td>
                    <td style="width: 10%;"></td>
                    <td style="width: 45%; text-align: right;">
                        <div style="border-bottom: 1px solid #94a3b8; width: 80%; margin-left: auto; height: 35px;"></div>
                        <div style="margin-top: 5px; font-weight: 700; color: #334155;">Official Finance Stamp & Date</div>
                    </td>
                </tr>
            </table>
        </div>
        """
