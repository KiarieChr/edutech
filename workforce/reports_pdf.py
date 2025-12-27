"""
HR & Payroll PDF Report Generators
Part 1: PDF Reports using ReportLab
"""

from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, PageBreak, Image, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from io import BytesIO
from decimal import Decimal


class PDFReportGenerator:
    """Base class for PDF report generation"""
    
    def __init__(self):
        self.buffer = BytesIO()
        self.pagesize = A4
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        """Setup custom paragraph styles"""
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#1a237e'),
            spaceAfter=30,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))
        
        self.styles.add(ParagraphStyle(
            name='CustomHeading',
            parent=self.styles['Heading2'],
            fontSize=12,
            textColor=colors.HexColor('#283593'),
            spaceAfter=12,
            fontName='Helvetica-Bold'
        ))
        
        self.styles.add(ParagraphStyle(
            name='RightAlign',
            parent=self.styles['Normal'],
            alignment=TA_RIGHT
        ))
    
    def _create_header(self, title, subtitle=None):
        """Create report header"""
        elements = []
        
        # Company logo (if available)
        # elements.append(Image('path/to/logo.png', width=2*inch, height=1*inch))
        # elements.append(Spacer(1, 0.2*inch))
        
        # Title
        elements.append(Paragraph(title, self.styles['CustomTitle']))
        
        if subtitle:
            elements.append(Paragraph(subtitle, self.styles['Normal']))
        
        # Date
        date_style = ParagraphStyle(
            name='DateStyle',
            parent=self.styles['Normal'],
            alignment=TA_RIGHT,
            fontSize=9
        )
        elements.append(Paragraph(
            f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M')}",
            date_style
        ))
        elements.append(Spacer(1, 0.3*inch))
        
        return elements
    
    def _create_table(self, data, col_widths=None, style=None):
        """Create a formatted table"""
        table = Table(data, colWidths=col_widths)
        
        if style is None:
            style = TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3f51b5')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
            ])
        
        table.setStyle(style)
        return table
    
    def generate_response(self, filename):
        """Generate HTTP response with PDF"""
        self.buffer.seek(0)
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.write(self.buffer.getvalue())
        self.buffer.close()
        return response


class PayslipPDFGenerator(PDFReportGenerator):
    """Generate payslip PDF"""
    
    def generate(self, payroll_calculation):
        """Generate payslip for a payroll calculation"""
        doc = SimpleDocTemplate(
            self.buffer,
            pagesize=self.pagesize,
            rightMargin=0.5*inch,
            leftMargin=0.5*inch,
            topMargin=0.5*inch,
            bottomMargin=0.5*inch
        )
        
        elements = []
        
        # Header
        elements.extend(self._create_header(
            'PAYSLIP',
            f"Period: {payroll_calculation.payroll_period.period_name}"
        ))
        
        # Employee Information
        emp = payroll_calculation.employee
        emp_data = [
            ['Employee No:', emp.employee_no, 'Name:', emp.get_full_name()],
            ['Department:', emp.department.name if emp.department else 'N/A',
             'Job Title:', emp.job_grade.name if emp.job_grade else 'N/A'],
            ['Payment Date:', 
             payroll_calculation.payroll_period.payment_date.strftime('%Y-%m-%d'),
             'Payment Method:', payroll_calculation.get_payment_method_display()]
        ]
        
        emp_table = Table(emp_data, colWidths=[1.5*inch, 2*inch, 1.5*inch, 2*inch])
        emp_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
        ]))
        
        elements.append(emp_table)
        elements.append(Spacer(1, 0.3*inch))
        
        # Earnings Section
        elements.append(Paragraph('EARNINGS', self.styles['CustomHeading']))
        
        details = payroll_calculation.details.filter(item_type='earning')
        earnings_data = [['Description', 'Amount']]
        
        for detail in details:
            earnings_data.append([
                detail.description,
                f"{payroll_calculation.payroll_period.currency if hasattr(payroll_calculation.payroll_period, 'currency') else '$'} {detail.amount:,.2f}"
            ])
        
        earnings_data.append(['GROSS PAY', f"$ {payroll_calculation.gross_pay:,.2f}"])
        
        earnings_table = self._create_table(
            earnings_data,
            col_widths=[4.5*inch, 2*inch]
        )
        elements.append(earnings_table)
        elements.append(Spacer(1, 0.2*inch))
        
        # Deductions Section
        elements.append(Paragraph('DEDUCTIONS', self.styles['CustomHeading']))
        
        deduction_details = payroll_calculation.details.filter(item_type='deduction')
        deductions_data = [['Description', 'Amount']]
        
        for detail in deduction_details:
            deductions_data.append([
                detail.description,
                f"$ {detail.amount:,.2f}"
            ])
        
        deductions_data.append([
            'TOTAL DEDUCTIONS',
            f"$ {payroll_calculation.total_deductions:,.2f}"
        ])
        
        deductions_table = self._create_table(
            deductions_data,
            col_widths=[4.5*inch, 2*inch]
        )
        elements.append(deductions_table)
        elements.append(Spacer(1, 0.3*inch))
        
        # Net Pay (Highlighted)
        net_pay_data = [[
            'NET PAY',
            f"$ {payroll_calculation.net_pay:,.2f}"
        ]]
        
        net_pay_table = Table(net_pay_data, colWidths=[4.5*inch, 2*inch])
        net_pay_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#4caf50')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 14),
            ('GRID', (0, 0), (-1, -1), 2, colors.black),
        ]))
        
        elements.append(net_pay_table)
        
        # Footer
        elements.append(Spacer(1, 0.5*inch))
        footer_style = ParagraphStyle(
            name='Footer',
            parent=self.styles['Normal'],
            fontSize=8,
            alignment=TA_CENTER,
            textColor=colors.grey
        )
        elements.append(Paragraph(
            "This is a computer-generated payslip and does not require a signature.",
            footer_style
        ))
        
        # Build PDF
        doc.build(elements)
        
        return self.generate_response(
            f"payslip_{emp.employee_no}_{payroll_calculation.payroll_period.period_name}.pdf"
        )


class EmployeeReportPDFGenerator(PDFReportGenerator):
    """Generate employee report PDF"""
    
    def generate(self, employees, filters=None):
        """Generate employee listing report"""
        doc = SimpleDocTemplate(
            self.buffer,
            pagesize=A4,
            rightMargin=0.5*inch,
            leftMargin=0.5*inch,
            topMargin=0.5*inch,
            bottomMargin=0.5*inch
        )
        
        elements = []
        
        # Header
        subtitle = f"Total Employees: {employees.count()}"
        if filters:
            subtitle += f" | Filters: {filters}"
        
        elements.extend(self._create_header('EMPLOYEE REPORT', subtitle))
        
        # Employee Table
        data = [['Emp No', 'Name', 'Department', 'Status', 'Hire Date']]
        
        for emp in employees:
            data.append([
                emp.employee_no,
                emp.get_full_name()[:25],
                emp.department.name[:20] if emp.department else 'N/A',
                emp.get_employment_status_display(),
                emp.hire_date.strftime('%Y-%m-%d')
            ])
        
        table = self._create_table(
            data,
            col_widths=[1*inch, 2*inch, 1.8*inch, 1.2*inch, 1*inch]
        )
        elements.append(table)
        
        # Summary
        elements.append(Spacer(1, 0.3*inch))
        elements.append(Paragraph('SUMMARY', self.styles['CustomHeading']))
        
        from django.db.models import Count
        status_summary = employees.values('employment_status').annotate(
            count=Count('id')
        )
        
        summary_data = [['Status', 'Count']]
        for item in status_summary:
            summary_data.append([
                item['employment_status'].replace('_', ' ').title(),
                str(item['count'])
            ])
        
        summary_table = self._create_table(summary_data, col_widths=[3*inch, 2*inch])
        elements.append(summary_table)
        
        # Build PDF
        doc.build(elements)
        
        return self.generate_response(
            f"employee_report_{timezone.now().strftime('%Y%m%d')}.pdf"
        )


class PayrollRegisterPDFGenerator(PDFReportGenerator):
    """Generate payroll register PDF"""
    
    def generate(self, payroll_period):
        """Generate payroll register for a period"""
        doc = SimpleDocTemplate(
            self.buffer,
            pagesize=A4,
            rightMargin=0.3*inch,
            leftMargin=0.3*inch,
            topMargin=0.5*inch,
            bottomMargin=0.5*inch
        )
        
        elements = []
        
        # Header
        elements.extend(self._create_header(
            'PAYROLL REGISTER',
            f"Period: {payroll_period.period_name} | Payment Date: {payroll_period.payment_date}"
        ))
        
        # Payroll Data
        calculations = payroll_period.calculations.select_related(
            'employee'
        ).order_by('employee__employee_no')
        
        data = [['Emp No', 'Name', 'Gross', 'Deductions', 'Net Pay']]
        
        total_gross = Decimal('0')
        total_deductions = Decimal('0')
        total_net = Decimal('0')
        
        for calc in calculations:
            data.append([
                calc.employee.employee_no,
                calc.employee.get_full_name()[:20],
                f"${calc.gross_pay:,.2f}",
                f"${calc.total_deductions:,.2f}",
                f"${calc.net_pay:,.2f}"
            ])
            
            total_gross += calc.gross_pay
            total_deductions += calc.total_deductions
            total_net += calc.net_pay
        
        # Totals row
        data.append([
            'TOTAL',
            f"{calculations.count()} employees",
            f"${total_gross:,.2f}",
            f"${total_deductions:,.2f}",
            f"${total_net:,.2f}"
        ])
        
        table = self._create_table(
            data,
            col_widths=[1*inch, 2*inch, 1.3*inch, 1.3*inch, 1.3*inch]
        )
        
        # Highlight totals row
        table_style = table.getStyle()
        table_style.add('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e3f2fd'))
        table_style.add('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold')
        
        elements.append(table)
        
        # Summary Section
        elements.append(Spacer(1, 0.3*inch))
        elements.append(Paragraph('PAYMENT SUMMARY', self.styles['CustomHeading']))
        
        summary_data = [
            ['Total Gross Pay', f"${total_gross:,.2f}"],
            ['Total Deductions', f"${total_deductions:,.2f}"],
            ['Total Net Pay', f"${total_net:,.2f}"],
            ['Number of Employees', str(calculations.count())],
            ['Average Net Pay', f"${(total_net / calculations.count() if calculations.count() > 0 else 0):,.2f}"]
        ]
        
        summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
        summary_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
        ]))
        
        elements.append(summary_table)
        
        # Build PDF
        doc.build(elements)
        
        return self.generate_response(
            f"payroll_register_{payroll_period.period_name}.pdf"
        )


class AttendanceReportPDFGenerator(PDFReportGenerator):
    """Generate attendance report PDF"""
    
    def generate(self, records, start_date, end_date):
        """Generate attendance report"""
        doc = SimpleDocTemplate(
            self.buffer,
            pagesize=A4,
            rightMargin=0.5*inch,
            leftMargin=0.5*inch,
            topMargin=0.5*inch,
            bottomMargin=0.5*inch
        )
        
        elements = []
        
        # Header
        elements.extend(self._create_header(
            'ATTENDANCE REPORT',
            f"Period: {start_date} to {end_date}"
        ))
        
        # Attendance Data
        data = [['Employee', 'Present', 'Absent', 'Late', 'Leave', 'Total Hours']]
        
        from django.db.models import Count, Sum
        
        # Group by employee
        employees = {}
        for record in records:
            emp_id = record.employee.id
            if emp_id not in employees:
                employees[emp_id] = {
                    'name': record.employee.get_full_name(),
                    'present': 0,
                    'absent': 0,
                    'late': 0,
                    'leave': 0,
                    'total_hours': Decimal('0')
                }
            
            if record.status == 'present':
                employees[emp_id]['present'] += 1
            elif record.status == 'absent':
                employees[emp_id]['absent'] += 1
            elif record.status == 'late':
                employees[emp_id]['late'] += 1
            elif record.status == 'on_leave':
                employees[emp_id]['leave'] += 1
            
            employees[emp_id]['total_hours'] += record.total_hours or Decimal('0')
        
        for emp_data in employees.values():
            data.append([
                emp_data['name'][:25],
                str(emp_data['present']),
                str(emp_data['absent']),
                str(emp_data['late']),
                str(emp_data['leave']),
                f"{emp_data['total_hours']:.2f}"
            ])
        
        table = self._create_table(
            data,
            col_widths=[2*inch, 1*inch, 1*inch, 1*inch, 1*inch, 1*inch]
        )
        elements.append(table)
        
        # Build PDF
        doc.build(elements)
        
        return self.generate_response(
            f"attendance_report_{start_date}_{end_date}.pdf"
        )


class LeaveReportPDFGenerator(PDFReportGenerator):
    """Generate leave report PDF"""
    
    def generate(self, leave_applications, year=None):
        """Generate leave report"""
        doc = SimpleDocTemplate(
            self.buffer,
            pagesize=A4,
            rightMargin=0.5*inch,
            leftMargin=0.5*inch,
            topMargin=0.5*inch,
            bottomMargin=0.5*inch
        )
        
        elements = []
        
        # Header
        year_str = year or timezone.now().year
        elements.extend(self._create_header(
            'LEAVE REPORT',
            f"Year: {year_str}"
        ))
        
        # Leave Data
        data = [['Employee', 'Leave Type', 'Start Date', 'Days', 'Status']]
        
        for leave in leave_applications:
            data.append([
                leave.employee.get_full_name()[:20],
                leave.leave_type.name[:15],
                leave.start_date.strftime('%Y-%m-%d'),
                str(leave.working_days),
                leave.get_status_display()
            ])
        
        table = self._create_table(
            data,
            col_widths=[2*inch, 1.5*inch, 1.2*inch, 0.8*inch, 1.5*inch]
        )
        elements.append(table)
        
        # Summary
        elements.append(Spacer(1, 0.3*inch))
        elements.append(Paragraph('SUMMARY', self.styles['CustomHeading']))
        
        from django.db.models import Count, Sum
        
        summary_by_type = leave_applications.values(
            'leave_type__name'
        ).annotate(
            count=Count('id'),
            total_days=Sum('working_days')
        )
        
        summary_data = [['Leave Type', 'Applications', 'Total Days']]
        for item in summary_by_type:
            summary_data.append([
                item['leave_type__name'],
                str(item['count']),
                str(item['total_days'] or 0)
            ])
        
        summary_table = self._create_table(
            summary_data,
            col_widths=[3*inch, 1.5*inch, 1.5*inch]
        )
        elements.append(summary_table)
        
        # Build PDF
        doc.build(elements)
        
        return self.generate_response(
            f"leave_report_{year_str}.pdf"
        )
