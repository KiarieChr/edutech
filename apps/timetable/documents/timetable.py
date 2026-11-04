"""
Official Class / Institutional Timetable Data Provider (Phase 3).
Extracts, structures, and renders print-grade class and examination timetables
from timetable and academics records using Document Design Studio and WeasyPrint.
"""
from datetime import datetime, date
from typing import Dict, Any, Optional, List
from django.core.exceptions import ValidationError
from django.utils.html import escape

from documents.models import DocumentTemplate
from documents.services.base_provider import BaseDocumentDataProvider
from academics.models import ClassSession
from timetable.models import TimetableSlot, TimePeriod


class TimetableDataProvider(BaseDocumentDataProvider):
    """
    Data provider for Official Class and Examination Timetables.
    Accepts a ClassSession instance (or any entity associated with a class session).
    """

    DAYS = [
        (0, "Monday"),
        (1, "Tuesday"),
        (2, "Wednesday"),
        (3, "Thursday"),
        (4, "Friday"),
    ]

    def __init__(self, entity: Any, context: Optional[Dict[str, Any]] = None):
        self.class_session: Optional[ClassSession] = None

        if isinstance(entity, ClassSession):
            self.class_session = entity
        elif hasattr(entity, "class_session"):
            self.class_session = getattr(entity, "class_session")
        else:
            raise ValidationError(
                f"Unsupported entity type '{type(entity).__name__}'. "
                "TimetableDataProvider requires a ClassSession instance."
            )

        super().__init__(entity, context=context)

    def get_document_type(self) -> str:
        return "class_timetable"

    def get_document_title(self) -> str:
        return "OFFICIAL CLASS TIMETABLE"

    def get_category(self) -> str:
        return DocumentTemplate.Category.TIMETABLE

    def validate(self) -> None:
        super().validate()
        if not self.class_session:
            raise ValidationError("A valid ClassSession is required for timetable generation.")

    def get_context_data(self) -> Dict[str, Any]:
        """
        Organizes scheduled TimetableSlots into a structured weekly matrix by day and time slot.
        """
        cs = self.class_session
        grade_obj = getattr(cs, "grade_structure", None)
        grade_name = getattr(grade_obj, "name", "") or getattr(cs, "class_name", "") or getattr(cs, "name", "General")
        curriculum_obj = getattr(grade_obj, "curriculum", None)
        curriculum_name = getattr(curriculum_obj, "name", "") or "Standard"

        academic_year_obj = getattr(cs, "academic_year", None)
        academic_year_name = getattr(academic_year_obj, "name", "") or str(datetime.now().year)

        term_obj = getattr(cs, "term", None)
        term_name = getattr(term_obj, "name", "") or "Term 1"

        # Fetch active slots for this class session
        slots = (
            TimetableSlot.objects.filter(class_session=cs, is_active=True)
            .select_related("subject", "teacher", "room")
            .order_by("day_of_week", "start_time")
        )

        # Collect distinct time periods / time slots
        time_slot_set = set()
        for slot in slots:
            time_slot_set.add((slot.start_time, slot.end_time))

        # Also inspect standard TimePeriods if defined
        periods = TimePeriod.objects.filter(is_active=True).order_by("order", "start_time")
        if periods.exists():
            for p in periods:
                time_slot_set.add((p.start_time, p.end_time))

        # Sorted list of unique time intervals
        sorted_time_slots = sorted(list(time_slot_set), key=lambda x: x[0])
        if not sorted_time_slots:
            # Fallback default school periods if none created yet
            from datetime import time
            sorted_time_slots = [
                (time(8, 0), time(8, 45)),
                (time(8, 50), time(9, 35)),
                (time(9, 40), time(10, 25)),
                (time(10, 55), time(11, 40)),
                (time(11, 45), time(12, 30)),
                (time(14, 0), time(14, 45)),
            ]

        # Group slots by (day_idx, start_time)
        slot_matrix = {}
        for s in slots:
            key = (s.day_of_week, s.start_time)
            teacher_name = getattr(s.teacher, "get_full_name", lambda: "")() or getattr(s.teacher, "username", "")
            slot_matrix[key] = {
                "subject_code": s.subject.code,
                "subject_name": s.subject.name,
                "teacher": teacher_name,
                "room": s.room.name if s.room else "",
                "color_hex": s.subject.color_hex or "#6366f1",
            }

        # Build grid rows for each day
        grid_days = []
        for day_idx, day_name in self.DAYS:
            day_cells = []
            for start_t, end_t in sorted_time_slots:
                slot_info = slot_matrix.get((day_idx, start_t))
                day_cells.append({
                    "start_time": start_t.strftime("%H:%M"),
                    "end_time": end_t.strftime("%H:%M"),
                    "slot": slot_info,
                })
            grid_days.append({
                "day_index": day_idx,
                "day_name": day_name,
                "cells": day_cells,
            })

        formatted_time_headers = [
            f"{st.strftime('%H:%M')} – {et.strftime('%H:%M')}" for st, et in sorted_time_slots
        ]

        doc_ref = f"TBL/{academic_year_name}/{grade_name.replace(' ', '_')}"

        return {
            "document_ref": doc_ref,
            "timetable": {
                "class_name": grade_name,
                "academic_year": academic_year_name,
                "term": term_name,
                "curriculum": curriculum_name,
                "time_headers": formatted_time_headers,
                "days": grid_days,
                "total_scheduled_lessons": slots.count(),
            }
        }

    def render_body_html(self, context: Dict[str, Any]) -> str:
        """
        Renders the weekly timetable grid with clear headers, day rows, and styled cells.
        """
        tb = context.get("timetable", {})
        time_headers = tb.get("time_headers", [])
        days = tb.get("days", [])
        brand_primary = context.get("brand", {}).get("primary", "#17365D")
        brand_secondary = context.get("brand", {}).get("secondary", "#1F6B4F")
        brand_accent = context.get("brand", {}).get("accent", "#D4A72C")

        # Header Columns
        header_th_list = ['<th style="width: 14%; text-align: center;">Day / Period</th>']
        col_w = f"{86 / max(1, len(time_headers)):.1f}%"
        for idx, th in enumerate(time_headers):
            header_th_list.append(
                f'<th style="width: {col_w}; text-align: center; font-size: 8pt;">'
                f'<div style="font-weight: 800;">Lesson {idx + 1}</div>'
                f'<div style="font-size: 7.5pt; font-weight: 400; opacity: 0.9;">{escape(th)}</div>'
                f'</th>'
            )
        headers_html = "".join(header_th_list)

        # Body Rows
        rows_list = []
        for d in days:
            cell_td_list = [
                f'<td style="font-weight: 800; background-color: #f1f5f9; text-align: center; vertical-align: middle; color: {brand_primary}; border-right: 1.5px solid #cbd5e1;">'
                f'{escape(d["day_name"])}'
                f'</td>'
            ]
            for cell in d.get("cells", []):
                sl = cell.get("slot")
                if sl:
                    cell_html = f"""
                    <td style="text-align: center; vertical-align: middle; padding: 6px 4px; border: 0.5pt solid #cbd5e1; background-color: #ffffff;">
                        <div style="font-size: 8.5pt; font-weight: 800; color: {brand_primary}; line-height: 1.2;">
                            {escape(sl['subject_code'])}
                        </div>
                        <div style="font-size: 7.5pt; font-weight: 500; color: #334155; margin-top: 1px;">
                            {escape(sl['subject_name'])}
                        </div>
                        <div style="font-size: 7pt; color: #64748b; margin-top: 2px;">
                            {escape(sl['teacher'])} {f"• {escape(sl['room'])}" if sl.get('room') else ''}
                        </div>
                    </td>
                    """
                else:
                    cell_html = """
                    <td style="text-align: center; vertical-align: middle; padding: 6px 4px; border: 0.5pt solid #e2e8f0; background-color: #fafafa; color: #cbd5e1; font-size: 7.5pt;">
                        —
                    </td>
                    """
                cell_td_list.append(cell_html)
            rows_list.append(f"<tr>{''.join(cell_td_list)}</tr>")

        body_rows_html = "".join(rows_list)

        return f"""
        <div class="report-header">
            <h1 class="doc-title">{escape(self.get_document_title())}</h1>
            <p class="doc-meta">
                Class: <strong>{escape(tb.get('class_name', ''))}</strong> | 
                Academic Year: <strong>{escape(tb.get('academic_year', ''))}</strong> | 
                Term: <strong>{escape(tb.get('term', ''))}</strong> | 
                Curriculum: <strong>{escape(tb.get('curriculum', ''))}</strong>
            </p>
        </div>

        <!-- Weekly Timetable Grid Table -->
        <table class="data-table" style="margin-top: 10px; margin-bottom: 20px;">
            <thead>
                <tr>
                    {headers_html}
                </tr>
            </thead>
            <tbody>
                {body_rows_html}
            </tbody>
        </table>

        <!-- Timetable Notes and Policy -->
        <div style="margin-top: 20px; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px 14px; background: #f8fafc; font-size: 8pt; color: #475569;">
            <div style="font-weight: 700; color: {brand_secondary}; margin-bottom: 3px;">Timetable Guidelines:</div>
            <ul style="margin: 0; padding-left: 18px; line-height: 1.5;">
                <li>All students and subject teachers must be present in designated rooms promptly at scheduled period start times.</li>
                <li>Mid-term lesson swaps or room reallocations must be approved by the Deputy Principal / Dean of Studies.</li>
                <li>Assembly periods and school announcements precede Period 1 on designated days.</li>
            </ul>
        </div>

        <div style="margin-top: 35px; page-break-inside: avoid;">
            <table class="grid-table" style="width: 100%; font-size: 8.5pt;">
                <tr>
                    <td style="width: 40%; vertical-align: bottom;">
                        <div style="border-bottom: 1px solid #94a3b8; width: 85%; height: 35px;"></div>
                        <div style="margin-top: 5px; font-weight: 700; color: #334155;">Director of Studies / Timetable Master</div>
                    </td>
                    <td style="width: 20%;"></td>
                    <td style="width: 40%; text-align: right; vertical-align: bottom;">
                        <div style="border-bottom: 1px solid #94a3b8; width: 85%; margin-left: auto; height: 35px;"></div>
                        <div style="margin-top: 5px; font-weight: 700; color: #334155;">Principal Endorsement & Date</div>
                    </td>
                </tr>
            </table>
        </div>
        """
