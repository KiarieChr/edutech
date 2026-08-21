from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from workforce.reports_pdf import PDFReportGenerator
from datetime import datetime

class MonthlyTimetablePDFGenerator(PDFReportGenerator):
    def __init__(self):
        super().__init__()
        self.pagesize = landscape(A4)

    def generate(self, year, month, schedule_data, entity_name):
        doc = SimpleDocTemplate(
            self.buffer,
            pagesize=self.pagesize,
            rightMargin=0.5*inch,
            leftMargin=0.5*inch,
            topMargin=0.5*inch,
            bottomMargin=0.5*inch
        )
        elements = []
        month_name = datetime(year, month, 1).strftime('%B')
        
        elements.extend(self._create_header(
            'MONTHLY TIMETABLE',
            f"{entity_name} - {month_name} {year}"
        ))

        data = [['Date', 'Day', 'Schedule']]
        
        # Avoid extremely long texts breaking table cells, ReportLab handles string wrapping with Paragraph objects, 
        # but for simple tables, we'll keep strings relatively short or use Paragraphs for the schedule.
        from reportlab.lib.styles import getSampleStyleSheet
        styles = getSampleStyleSheet()
        normal_style = styles['Normal']
        
        for date_str, day_data in sorted(schedule_data.items()):
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            day_name = date_obj.strftime('%A')
            
            if day_data.get('exception'):
                sched_text = f"EXCEPTION: {day_data['exception']['type']} - {day_data['exception']['reason']}"
            elif not day_data.get('slots'):
                sched_text = "No slots scheduled"
            else:
                lines = []
                for s in day_data['slots']:
                    lines.append(f"{s['start_time']}-{s['end_time']}: {s['subject_name']} ({s['room_name'] or 'No Room'}) - {s['teacher_name']} - {s['class_session_name']}")
                sched_text = "<br/>".join(lines)
                
            data.append([
                date_str,
                day_name,
                Paragraph(sched_text, normal_style)
            ])
            
        table = self._create_table(data, col_widths=[1.0*inch, 1.0*inch, 8.5*inch])
        # Override table style to allow vertical alignment for paragraphs
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3f51b5')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('INNERGRID', (0,0), (-1,-1), 0.25, colors.black),
        ]))
        
        elements.append(table)
        
        doc.build(elements)
        return self.generate_response(f"timetable_{year}_{month}.pdf")
