"""
python-docx Word Generator for Student Management Reports
"""
from io import BytesIO
from typing import Dict, Any

try:
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False


def set_cell_background(cell, fill_hex):
    """Sets background hex color for a table cell in docx."""
    if not HAS_DOCX:
        return
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), fill_hex)
    tcPr.append(shd)


class ReportWordGenerator:
    """Generates styled Microsoft Word (.docx) documents."""

    @classmethod
    def generate(cls, export_data: Dict[str, Any]) -> bytes:
        if not HAS_DOCX:
            raise RuntimeError("python-docx is not installed in the environment. Please run: pip install python-docx")
        doc = Document()

        # Adjust Margins
        sections = doc.sections
        for section in sections:
            section.top_margin = Inches(0.5)
            section.bottom_margin = Inches(0.5)
            section.left_margin = Inches(0.5)
            section.right_margin = Inches(0.5)

        metadata = export_data.get("metadata", {})
        title = metadata.get("title", "Student Report")
        summaries = export_data.get("summaries", {})
        columns = export_data.get("columns", [])
        results = export_data.get("results", [])

        # Header Info
        inst_p = doc.add_paragraph()
        inst_run = inst_p.add_run("FAHARI ACADEMIA")
        inst_run.font.name = "Calibri"
        inst_run.font.size = Pt(9)
        inst_run.font.color.rgb = RGBColor(100, 116, 139)

        title_p = doc.add_paragraph()
        title_run = title_p.add_run(title)
        title_run.font.name = "Calibri"
        title_run.font.size = Pt(16)
        title_run.font.bold = True
        title_run.font.color.rgb = RGBColor(30, 58, 138)
        title_p.paragraph_format.space_after = Pt(2)

        meta_p = doc.add_paragraph()
        gen_run = meta_p.add_run(f"Generated: {metadata.get('generated_at', '')}  |  ")
        gen_run.font.size = Pt(8.5)
        gen_run.font.color.rgb = RGBColor(71, 85, 105)

        for k, v in summaries.items():
            s_run = meta_p.add_run(f"{k.replace('_', ' ').title()}: {v}   ")
            s_run.font.size = Pt(8.5)
            s_run.font.bold = True
            s_run.font.color.rgb = RGBColor(15, 23, 42)

        meta_p.paragraph_format.space_after = Pt(12)

        # Build Table
        table = doc.add_table(rows=1, cols=len(columns))
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = True

        # Header Row
        hdr_cells = table.rows[0].cells
        for i, col in enumerate(columns):
            hdr_cells[i].text = col["label"]
            set_cell_background(hdr_cells[i], "1E3A8A")
            p = hdr_cells[i].paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in p.runs:
                run.font.name = "Calibri"
                run.font.bold = True
                run.font.size = Pt(8.5)
                run.font.color.rgb = RGBColor(255, 255, 255)

        # Set repeat header row property on XML level
        trPr = table.rows[0]._tr.get_or_add_trPr()
        trPr.append(OxmlElement('w:tblHeader'))

        # Data Rows
        for r_idx, item in enumerate(results):
            row_cells = table.add_row().cells
            is_alt = (r_idx % 2 == 1)
            for c_idx, col in enumerate(columns):
                val = str(item.get(col["key"], "") or "—")
                row_cells[c_idx].text = val
                p = row_cells[c_idx].paragraphs[0]
                align = col.get("align", "left")
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER if align == "center" else WD_ALIGN_PARAGRAPH.LEFT
                for run in p.runs:
                    run.font.name = "Calibri"
                    run.font.size = Pt(8)
                    run.font.color.rgb = RGBColor(30, 41, 59)
                if is_alt:
                    set_cell_background(row_cells[c_idx], "F8FAFC")

        buf = BytesIO()
        doc.save(buf)
        return buf.getvalue()
