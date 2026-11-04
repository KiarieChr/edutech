"""
OpenPyXL Excel Generator for Student Management Reports
"""
from io import BytesIO
from typing import Dict, Any
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


class ReportExcelGenerator:
    """Generates styled .xlsx workbooks with cell typing and injection defense."""

    @classmethod
    def sanitize_value(cls, val: Any) -> Any:
        """Prevent Excel/CSV formula injection by escaping leading special characters."""
        if isinstance(val, str) and len(val) > 0:
            if val[0] in ("=", "+", "-", "@"):
                return f"'{val}"
        return val

    @classmethod
    def generate(cls, export_data: Dict[str, Any]) -> bytes:
        wb = openpyxl.Workbook()
        ws = wb.active
        metadata = export_data.get("metadata", {})
        title = metadata.get("title", "Report")
        ws.title = title[:30].replace("/", "-").replace("\\", "-")

        # Fonts & Fills
        header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        title_font = Font(name="Calibri", size=14, bold=True, color="1E3A8A")
        sub_font = Font(name="Calibri", size=9, italic=True, color="64748B")
        summary_label_font = Font(name="Calibri", size=9, bold=True, color="334155")
        summary_val_font = Font(name="Calibri", size=9, color="0F172A")
        cell_font = Font(name="Calibri", size=10, color="0F172A")
        alt_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

        thin_border = Border(
            left=Side(style="thin", color="E2E8F0"),
            right=Side(style="thin", color="E2E8F0"),
            top=Side(style="thin", color="E2E8F0"),
            bottom=Side(style="thin", color="E2E8F0"),
        )

        # 1. Title & Meta
        ws.cell(row=1, column=1, value="FAHARI ACADEMIA").font = sub_font
        ws.cell(row=2, column=1, value=title).font = title_font
        ws.cell(row=3, column=1, value=f"Generated: {metadata.get('generated_at', '')}").font = sub_font

        # 2. Summary stats block
        summaries = export_data.get("summaries", {})
        col_offset = 1
        for k, v in summaries.items():
            cell_k = ws.cell(row=5, column=col_offset, value=k.replace("_", " ").title())
            cell_k.font = summary_label_font
            cell_v = ws.cell(row=5, column=col_offset + 1, value=v)
            cell_v.font = summary_val_font
            col_offset += 2

        # 3. Table Column Headers
        columns = export_data.get("columns", [])
        start_row = 7
        for c_idx, col in enumerate(columns, 1):
            cell = ws.cell(row=start_row, column=c_idx, value=col["label"])
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = thin_border

        # 4. Table Data Rows
        results = export_data.get("results", [])
        current_row = start_row + 1
        for r_idx, item in enumerate(results):
            is_alt = (r_idx % 2 == 1)
            for c_idx, col in enumerate(columns, 1):
                raw_val = item.get(col["key"])
                val = cls.sanitize_value(raw_val if raw_val is not None else "—")
                cell = ws.cell(row=current_row, column=c_idx, value=val)
                cell.font = cell_font
                cell.border = thin_border
                if is_alt:
                    cell.fill = alt_fill

                align = col.get("align", "left")
                cell.alignment = Alignment(horizontal="center" if align == "center" else "left", vertical="center")
            current_row += 1

        # 5. Auto Column Widths
        for c_idx, col in enumerate(columns, 1):
            letter = get_column_letter(c_idx)
            max_len = max(len(col["label"]), 12)
            ws.column_dimensions[letter].width = min(max_len + 5, 40)

        # Freeze Panes under table header
        ws.freeze_panes = f"A{start_row + 1}"

        buf = BytesIO()
        wb.save(buf)
        return buf.getvalue()
