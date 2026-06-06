from workforce.reports_excel import ExcelReportGenerator
from django.utils import timezone
from datetime import datetime

class MonthlyTimetableExcelGenerator(ExcelReportGenerator):
    def generate(self, year, month, schedule_data, entity_name):
        self.worksheet.title = 'Monthly Timetable'
        
        month_name = datetime(year, month, 1).strftime('%B')
        
        self._merge_and_style_header(1, 1, 8, 'MONTHLY TIMETABLE', 'title')
        self._merge_and_style_header(2, 1, 8, f"{entity_name} - {month_name} {year}", 'subheader')
        
        headers = ['Date', 'Day', 'Start Time', 'End Time', 'Subject', 'Teacher', 'Class', 'Room']
        
        row = 4
        for col, header in enumerate(headers, 1):
            cell = self.worksheet.cell(row=row, column=col)
            cell.value = header
            cell.font = self.header_font
            cell.fill = self.header_fill
            cell.alignment = self.center_alignment
            cell.border = self.border
            
        row = 5
        for date_str, day_data in sorted(schedule_data.items()):
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            day_name = date_obj.strftime('%A')
            
            if day_data.get('exception'):
                cell = self.worksheet.cell(row=row, column=1)
                cell.value = date_str
                self.worksheet.cell(row=row, column=2).value = day_name
                self.worksheet.cell(row=row, column=3).value = f"EXCEPTION: {day_data['exception']['type']} - {day_data['exception']['reason']}"
                row += 1
            elif not day_data.get('slots'):
                cell = self.worksheet.cell(row=row, column=1)
                cell.value = date_str
                self.worksheet.cell(row=row, column=2).value = day_name
                self.worksheet.cell(row=row, column=3).value = "No slots scheduled"
                row += 1
            else:
                for s in day_data['slots']:
                    data = [
                        date_str,
                        day_name,
                        s['start_time'],
                        s['end_time'],
                        s['subject_name'],
                        s['teacher_name'],
                        s['class_session_name'],
                        s['room_name'] or 'N/A'
                    ]
                    for col, val in enumerate(data, 1):
                        c = self.worksheet.cell(row=row, column=col)
                        c.value = val
                        c.border = self.border
                    row += 1
                    
        self._set_column_widths([15, 15, 12, 12, 25, 20, 20, 15])
        return self.generate_response(f"timetable_{year}_{month}.xlsx")
