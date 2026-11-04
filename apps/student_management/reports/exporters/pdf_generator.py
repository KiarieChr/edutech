"""
ReportLab PDF Generator for Student Management Reports
"""
from io import BytesIO
from typing import Dict, Any, List
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, KeepTogether
)
from reportlab.pdfgen import canvas


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically compute and print 'Page X of Y' along with generation footer.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))
        
        page_w, page_h = self._pagesize
        # Running footer line
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.5)
        self.line(36, 30, page_w - 36, 30)

        footer_text = "Fahari Academia — Official Student Management Report"
        self.drawString(36, 18, footer_text)

        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(page_w - 36, 18, page_str)
        self.restoreState()


class ReportPDFGenerator:
    """Generates professional A4 PDF documents from structured report data."""

    @classmethod
    def generate(cls, export_data: Dict[str, Any], orientation: str = "portrait") -> bytes:
        buffer = BytesIO()
        pagesize = landscape(A4) if orientation == "landscape" else A4
        doc = SimpleDocTemplate(
            buffer,
            pagesize=pagesize,
            leftMargin=36,
            rightMargin=36,
            topMargin=36,
            bottomMargin=45
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            name="RepTitle",
            parent=styles["Heading1"],
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#1E3A8A"),
            fontName="Helvetica-Bold",
            spaceAfter=4
        )
        meta_style = ParagraphStyle(
            name="RepMeta",
            parent=styles["Normal"],
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#475569")
        )
        th_style = ParagraphStyle(
            name="RepTH",
            parent=styles["Normal"],
            fontSize=8,
            leading=10,
            fontName="Helvetica-Bold",
            textColor=colors.white,
            alignment=1  # Center
        )
        td_style = ParagraphStyle(
            name="RepTD",
            parent=styles["Normal"],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#1E293B")
        )

        elements = []
        metadata = export_data.get("metadata", {})
        title = metadata.get("title", "Student Report")
        gen_at = metadata.get("generated_at", "")
        summaries = export_data.get("summaries", {})
        columns = export_data.get("columns", [])
        results = export_data.get("results", [])

        # Header block
        elements.append(Paragraph(f"<b>FAHARI ACADEMIA</b>", ParagraphStyle(name="Inst", fontSize=10, textColor=colors.HexColor("#64748B"), spaceAfter=2)))
        elements.append(Paragraph(title, title_style))

        # Metadata & Summary Chips
        summary_str = " &nbsp;|&nbsp; ".join([f"<b>{k.replace('_', ' ').title()}:</b> {v}" for k, v in summaries.items()])
        elements.append(Paragraph(f"Generated on: {gen_at} &nbsp;&nbsp;&nbsp;&nbsp; {summary_str}", meta_style))
        elements.append(Spacer(1, 12))

        # Build Table
        header_row = [Paragraph(col["label"], th_style) for col in columns]
        table_data = [header_row]

        for item in results:
            row = []
            for col in columns:
                val = str(item.get(col["key"], "") or "—")
                row.append(Paragraph(val, td_style))
            table_data.append(row)

        col_count = len(columns)
        printable_width = pagesize[0] - 72
        col_widths = [printable_width / col_count] * col_count if col_count else None
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ]))

        elements.append(table)
        doc.build(elements, canvasmaker=NumberedCanvas)
        return buffer.getvalue()
