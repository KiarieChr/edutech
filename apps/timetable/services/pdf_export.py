"""
Timetable PDF Export Service
Generates print-ready, branded, institutional timetable PDF documents using WeasyPrint.
Supports Class Timetables, Faculty/Teacher Timetables, and Room Timetables.
"""
import os
import base64
from datetime import datetime
from django.apps import apps
from django.utils.html import escape
import weasyprint

DAY_NAMES = [
    (0, "Monday"),
    (1, "Tuesday"),
    (2, "Wednesday"),
    (3, "Thursday"),
    (4, "Friday"),
    (5, "Saturday"),
]


class TimetablePDFGenerator:
    """
    Renders structured timetable schedules into high-quality PDF bytes
    styled with institutional branding.
    """

    def __init__(self, entity_type: str, entity_id: int):
        self.entity_type = entity_type.lower()
        self.entity_id = entity_id

    def generate(self) -> tuple[bytes, str]:
        """
        Returns (pdf_bytes, filename).
        """
        ClassSession = apps.get_model('academics', 'ClassSession')
        TimetableSlot = apps.get_model('timetable', 'TimetableSlot')
        TimePeriod = apps.get_model('timetable', 'TimePeriod')
        Room = apps.get_model('timetable', 'Room')
        InstitutionProfile = apps.get_model('core', 'InstitutionProfile')
        from django.contrib.auth import get_user_model
        User = get_user_model()
        Employee = apps.get_model('workforce', 'Employee')

        # 1. Institutional Branding
        inst = InstitutionProfile.objects.first()
        school_name = (inst.display_name or inst.name) if inst else "Fahari Academia"
        motto = (inst.motto or "") if inst else ""
        primary_color = (getattr(inst, 'primary_color', None) or "#1e3a8a").strip()
        secondary_color = (getattr(inst, 'secondary_color', None) or "#0f766e").strip()
        contact_info_parts = []
        if inst:
            if getattr(inst, 'email', None):
                contact_info_parts.append(inst.email)
            if getattr(inst, 'phone_primary', None):
                contact_info_parts.append(inst.phone_primary)
            if getattr(inst, 'website', None):
                contact_info_parts.append(inst.website)
        contact_line = " • ".join(contact_info_parts)

        # Logo handling (convert to base64 data URI if available)
        logo_html = ""
        if inst and getattr(inst, 'logo', None):
            try:
                logo_file = inst.logo
                if logo_file and hasattr(logo_file, 'path') and os.path.exists(logo_file.path):
                    with open(logo_file.path, 'rb') as f:
                        ext = os.path.splitext(logo_file.path)[1].lower().replace('.', '')
                        mime = f"image/{ext if ext != 'jpg' else 'jpeg'}"
                        b64 = base64.b64encode(f.read()).decode('utf-8')
                        logo_html = f'<img src="data:{mime};base64,{b64}" style="max-height: 52px; max-width: 140px; object-fit: contain;" alt="Logo" />'
            except Exception:
                pass

        # 2. Entity Context & Slots Resolution
        title = "OFFICIAL TIMETABLE"
        subtitle = ""
        meta_info = ""
        filename_slug = "timetable"
        slots_qs = TimetableSlot.objects.filter(is_active=True).select_related(
            'subject', 'teacher', 'room', 'class_session'
        )

        if self.entity_type == 'class':
            session = ClassSession.objects.filter(id=self.entity_id).first()
            if not session:
                raise ValueError(f"Class session #{self.entity_id} not found")
            title = "CLASS TIMETABLE"
            subtitle = session.name
            academic_year = getattr(session.academic_year, 'name', '') if session.academic_year else ''
            term = getattr(session.term, 'name', '') if session.term else ''
            curriculum = getattr(session.curriculum, 'name', '') if getattr(session, 'curriculum', None) else ''
            meta_info = f"Academic Year: {academic_year} | Term: {term} | Curriculum: {curriculum}"
            filename_slug = f"class_{session.name.lower().replace(' ', '_')}"
            slots_qs = slots_qs.filter(class_session=session)

        elif self.entity_type == 'teacher':
            # Resolve user or employee
            user = User.objects.filter(id=self.entity_id).first()
            emp = None
            if not user:
                emp = Employee.objects.filter(id=self.entity_id).first()
                if emp and emp.user:
                    user = emp.user
            else:
                emp = getattr(user, 'employee_profile', None)

            if not user and not emp:
                raise ValueError(f"Faculty / Teacher #{self.entity_id} not found")

            teacher_name = ""
            if emp:
                fn = getattr(emp, 'get_full_name', None)
                teacher_name = fn() if callable(fn) else (str(fn) if fn else "")
            if not teacher_name and user:
                fn = getattr(user, 'get_full_name', None)
                teacher_name = fn() if callable(fn) else (str(fn) if fn else (user.username or ""))
            title = "FACULTY WORKLOAD TIMETABLE"
            subtitle = f"Educator: {teacher_name}"
            emp_no = getattr(emp, 'employee_no', '') if emp else ''
            meta_info = f"Staff ID: {emp_no}" if emp_no else "Weekly Teaching Schedule"
            filename_slug = f"teacher_{teacher_name.lower().replace(' ', '_')}"
            slots_qs = slots_qs.filter(teacher=user)

        elif self.entity_type == 'room':
            room = Room.objects.filter(id=self.entity_id).first()
            if not room:
                raise ValueError(f"Room #{self.entity_id} not found")
            title = "ROOM OCCUPANCY TIMETABLE"
            subtitle = f"Learning Space: {room.name}"
            meta_info = f"Type: {room.get_room_type_display()} | Seating Capacity: {room.capacity} students"
            filename_slug = f"room_{room.name.lower().replace(' ', '_')}"
            slots_qs = slots_qs.filter(room=room)

        slots = list(slots_qs.order_by('day_of_week', 'start_time'))

        # 3. Periods Resolution
        periods = list(TimePeriod.objects.filter(is_active=True).order_by('order', 'start_time'))
        if not periods and slots:
            # Derive virtual periods from unique start/end times in slots
            seen_times = set()
            for s in sorted(slots, key=lambda x: x.start_time):
                key = (s.start_time, s.end_time)
                if key not in seen_times:
                    seen_times.add(key)
                    periods.append(type('VirtualPeriod', (), {
                        'id': len(seen_times),
                        'name': f"Period {len(seen_times)}",
                        'short_name': f"P{len(seen_times)}",
                        'start_time': s.start_time,
                        'end_time': s.end_time,
                        'is_schedulable': True,
                        'period_type': 'lesson',
                        'applies_to_days': None,
                    })())

        # 4. Check if Saturday has slots
        has_saturday_slots = any(s.day_of_week == 5 for s in slots)
        days_to_render = DAY_NAMES if has_saturday_slots else DAY_NAMES[:5]

        # 5. Build Slot Matrix lookup: (day_of_week, start_time_str) -> slot
        slot_matrix = {}
        for s in slots:
            start_hhmm = s.start_time.strftime('%H:%M')
            slot_matrix[(s.day_of_week, start_hhmm)] = s

        # 6. Render Table HTML
        # Header Row
        col_width_percent = 84.0 / max(1, len(periods))
        period_headers_html = []
        for idx, p in enumerate(periods):
            p_start = p.start_time.strftime('%H:%M')
            p_end = p.end_time.strftime('%H:%M')
            p_name = getattr(p, 'short_name', None) or getattr(p, 'name', f"Period {idx + 1}")
            is_break = not getattr(p, 'is_schedulable', True)
            bg_col = "#fef3c7" if is_break else "#f8fafc"
            text_col = "#92400e" if is_break else "#334155"
            period_headers_html.append(
                f'<th style="width: {col_width_percent:.1f}%; background-color: {bg_col}; color: {text_col}; '
                f'text-align: center; border: 1px solid #cbd5e1; padding: 6px 3px;">'
                f'<div style="font-size: 8.5pt; font-weight: 700;">{escape(p_name)}</div>'
                f'<div style="font-size: 7pt; font-weight: 400; opacity: 0.9; margin-top: 1px;">{p_start}–{p_end}</div>'
                f'</th>'
            )

        # Day Rows
        day_rows_html = []
        for day_idx, day_name in days_to_render:
            cell_tds = [
                f'<td style="width: 16%; font-weight: 800; font-size: 8.5pt; background-color: #f1f5f9; '
                f'text-align: center; vertical-align: middle; color: {primary_color}; border: 1px solid #cbd5e1; padding: 6px 4px;">'
                f'{day_name}'
                f'</td>'
            ]

            for p in periods:
                p_start = p.start_time.strftime('%H:%M')
                is_break = not getattr(p, 'is_schedulable', True)

                if is_break:
                    cell_tds.append(
                        f'<td style="text-align: center; vertical-align: middle; border: 1px solid #cbd5e1; '
                        f'background-color: #fffbeb; color: #b45309; font-size: 7.5pt; font-weight: 700; letter-spacing: 0.5px;">'
                        f'{escape(p.name or "BREAK")}'
                        f'</td>'
                    )
                    continue

                slot = slot_matrix.get((day_idx, p_start))
                if slot:
                    subj_name = slot.subject.name
                    subj_code = slot.subject.code
                    teacher_name = ''
                    if slot.teacher:
                        t_name = getattr(slot.teacher, 'get_full_name', None)
                        teacher_name = t_name() if callable(t_name) else (str(t_name) if t_name else getattr(slot.teacher, 'username', ''))
                    room_name = slot.room.name if slot.room else ''
                    color_hex = slot.subject.color_hex or primary_color

                    cell_tds.append(
                        f'<td style="text-align: center; vertical-align: middle; border: 1px solid #cbd5e1; '
                        f'background-color: #ffffff; padding: 5px 3px;">'
                        f'<div style="font-size: 8pt; font-weight: 800; color: {color_hex}; line-height: 1.15;">'
                        f'{escape(subj_code)}'
                        f'</div>'
                        f'<div style="font-size: 7.5pt; font-weight: 600; color: #1e293b; margin-top: 1px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">'
                        f'{escape(subj_name)}'
                        f'</div>'
                        f'<div style="font-size: 6.5pt; color: #64748b; margin-top: 2px;">'
                        f'{escape(teacher_name)} {f"• {escape(room_name)}" if room_name else ""}'
                        f'</div>'
                        f'</td>'
                    )
                else:
                    cell_tds.append(
                        f'<td style="text-align: center; vertical-align: middle; border: 1px solid #e2e8f0; '
                        f'background-color: #f8fafc; color: #cbd5e1; font-size: 8pt;">'
                        f'—'
                        f'</td>'
                    )

            day_rows_html.append(f'<tr>{"".join(cell_tds)}</tr>')

        generated_date_str = datetime.now().strftime('%d %B %Y at %H:%M')

        full_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{escape(title)} - {escape(subtitle)}</title>
    <style>
        @page {{
            size: A4 landscape;
            margin: 10mm 12mm 12mm 12mm;
            @bottom-left {{
                content: "Fahari Academia Timetabling Engine • Certified Academic Schedule";
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                font-size: 7.5pt;
                color: #64748b;
            }}
            @bottom-right {{
                content: "Page " counter(page) " of " counter(pages);
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                font-size: 7.5pt;
                color: #64748b;
            }}
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            color: #0f172a;
            margin: 0;
            padding: 0;
            font-size: 8pt;
        }}

        .header-container {{
            display: table;
            width: 100%;
            border-bottom: 2px solid {primary_color};
            padding-bottom: 8px;
            margin-bottom: 10px;
        }}

        .header-logo-cell {{
            display: table-cell;
            vertical-align: middle;
            width: 15%;
        }}

        .header-info-cell {{
            display: table-cell;
            vertical-align: middle;
            text-align: center;
            width: 70%;
        }}

        .header-date-cell {{
            display: table-cell;
            vertical-align: middle;
            text-align: right;
            width: 15%;
            font-size: 7pt;
            color: #64748b;
        }}

        .school-name {{
            font-size: 15pt;
            font-weight: 900;
            color: {primary_color};
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin: 0;
        }}

        .school-motto {{
            font-size: 8pt;
            font-style: italic;
            color: {secondary_color};
            margin-top: 1px;
        }}

        .doc-title {{
            font-size: 11pt;
            font-weight: 800;
            color: #1e293b;
            letter-spacing: 0.3px;
            margin-top: 4px;
        }}

        .doc-subtitle {{
            font-size: 9.5pt;
            font-weight: 700;
            color: {primary_color};
            margin-top: 1px;
        }}

        .doc-meta {{
            font-size: 7.5pt;
            color: #475569;
            margin-top: 2px;
        }}

        table.timetable-matrix {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 6px;
            table-layout: fixed;
        }}

        .endorsement-container {{
            margin-top: 20px;
            display: table;
            width: 100%;
            font-size: 7.5pt;
            page-break-inside: avoid;
        }}

        .endorsement-box {{
            display: table-cell;
            width: 48%;
            vertical-align: bottom;
        }}

        .sign-line {{
            border-bottom: 1px solid #94a3b8;
            height: 25px;
            width: 80%;
        }}

        .sign-title {{
            margin-top: 4px;
            font-weight: 700;
            color: #334155;
        }}
    </style>
</head>
<body>
    <div class="header-container">
        <div class="header-logo-cell">
            {logo_html}
        </div>
        <div class="header-info-cell">
            <h1 class="school-name">{escape(school_name)}</h1>
            {f'<div class="school-motto">"{escape(motto)}"</div>' if motto else ''}
            <div class="doc-title">{escape(title)}</div>
            <div class="doc-subtitle">{escape(subtitle)}</div>
            {f'<div class="doc-meta">{escape(meta_info)}</div>' if meta_info else ''}
        </div>
        <div class="header-date-cell">
            <div><strong>Generated:</strong></div>
            <div>{generated_date_str}</div>
            <div style="margin-top: 4px;">{escape(contact_line)}</div>
        </div>
    </div>

    <!-- Timetable Grid -->
    <table class="timetable-matrix">
        <thead>
            <tr>
                <th style="width: 16%; background-color: #f1f5f9; color: {primary_color}; text-align: center; border: 1px solid #cbd5e1; padding: 6px 4px; font-size: 8.5pt;">
                    Day / Period
                </th>
                {''.join(period_headers_html)}
            </tr>
        </thead>
        <tbody>
            {''.join(day_rows_html)}
        </tbody>
    </table>

    <!-- Endorsements -->
    <div class="endorsement-container">
        <div class="endorsement-box">
            <div class="sign-line"></div>
            <div class="sign-title">Director of Studies / Timetable Coordinator</div>
        </div>
        <div style="display: table-cell; width: 4%;"></div>
        <div class="endorsement-box" style="text-align: right;">
            <div class="sign-line" style="margin-left: auto;"></div>
            <div class="sign-title">Principal's Official Stamp & Signature</div>
        </div>
    </div>
</body>
</html>
"""
        wp = weasyprint.HTML(string=full_html)
        pdf_bytes = wp.write_pdf()
        filename = f"{filename_slug}_{datetime.now().strftime('%Y%m%d')}.pdf"
        return pdf_bytes, filename
