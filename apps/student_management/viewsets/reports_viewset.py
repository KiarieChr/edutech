from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.renderers import BaseRenderer, JSONRenderer, BrowsableAPIRenderer
from django.db.models import Count, Q
from student_management.models import Student
from student_settings.models import Enrollment

class PassthroughRenderer(BaseRenderer):
    media_type = '*/*'
    format = ''
    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data

class PDFRenderer(BaseRenderer):
    media_type = 'application/pdf'
    format = 'pdf'
    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data

class ExcelRenderer(BaseRenderer):
    media_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    format = 'excel'
    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data

class XLSXRenderer(BaseRenderer):
    media_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    format = 'xlsx'
    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data

class DOCXRenderer(BaseRenderer):
    media_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    format = 'docx'
    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data

class WordRenderer(BaseRenderer):
    media_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    format = 'word'
    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data

class StudentReportsViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]
    renderer_classes = [
        JSONRenderer,
        BrowsableAPIRenderer,
        PDFRenderer,
        ExcelRenderer,
        XLSXRenderer,
        DOCXRenderer,
        WordRenderer,
        PassthroughRenderer,
    ]

    @action(detail=False, methods=['get'], url_path='overview-stats')
    def overview_stats(self, request):
        """
        Calculates and returns aggregated Overview Dashboard statistics for the current tenant.
        Strict tenant isolation is guaranteed by django_tenants schema context.
        1. Total Students: Total count of active students.
        2. New Admissions (This Term): Count of students admitted within current term date range.
        3. Gender Breakdown: Count of Male vs Female (and other) active students.
        4. Class Distribution: Summary of top 5 classes with highest enrollment.
        5. Transfers/Exits: Count of students with status 'Transferred' or 'Withdrawn' in current academic year.
        """
        from student_management.models import Student
        from student_settings.models import Enrollment, Term, AcademicYear
        from django.utils import timezone
        from core.campus_filter import get_effective_campus_id

        effective_campus_id = get_effective_campus_id(request)

        # 1. Total Active Students
        active_qs = Student.objects.filter(status='active')
        if effective_campus_id:
            active_qs = active_qs.filter(campus_id=effective_campus_id)
        total_students = active_qs.count()

        # 2. Gender Breakdown (Active Students)
        # student__gender comes from User model
        gender_counts = dict(
            active_qs.values_list('student__gender').annotate(count=Count('id'))
        )
        male_count = (
            gender_counts.get('M', 0)
            + gender_counts.get('Male', 0)
            + gender_counts.get('male', 0)
        )
        female_count = (
            gender_counts.get('F', 0)
            + gender_counts.get('Female', 0)
            + gender_counts.get('female', 0)
        )
        other_count = sum(
            c for g, c in gender_counts.items()
            if g not in ('M', 'Male', 'male', 'F', 'Female', 'female')
        )

        # 3. Current Term & Academic Year
        current_term = Term.objects.filter(is_current=True).first()
        if not current_term:
            current_term = Term.objects.filter(status='active').first()

        current_ay = getattr(current_term, 'academic_year', None) or AcademicYear.objects.filter(is_current=True).first()

        # New Admissions (This Term)
        new_admissions = 0
        admissions_qs = Student.objects.all()
        if effective_campus_id:
            admissions_qs = admissions_qs.filter(campus_id=effective_campus_id)
        if current_term and current_term.start_date:
            admissions_filter = Q(admission_date__gte=current_term.start_date)
            if current_term.end_date:
                admissions_filter &= Q(admission_date__lte=current_term.end_date)
            new_admissions = admissions_qs.filter(admissions_filter).count()
        else:
            now = timezone.now()
            new_admissions = admissions_qs.filter(admission_date__year=now.year).count()

        # 4. Class Distribution (Top 5 classes by active enrollment)
        enrollment_qs = Enrollment.objects.filter(is_active=True, is_deleted=False, grade__isnull=False)
        if effective_campus_id:
            enrollment_qs = enrollment_qs.filter(campus_id=effective_campus_id)
        class_dist_qs = (
            enrollment_qs
            .values('grade__name')
            .annotate(count=Count('id'))
            .order_by('-count')[:5]
        )
        class_distribution = [
            {
                "class_name": item['grade__name'],
                "grade__name": item['grade__name'],
                "count": item['count'],
            }
            for item in class_dist_qs
        ]

        # 5. Transfers & Exits
        exit_qs = Student.objects.filter(status__in=['transferred', 'withdrawn'])
        if effective_campus_id:
            exit_qs = exit_qs.filter(campus_id=effective_campus_id)
        transfers_out = exit_qs.filter(status='transferred').count()
        dropouts = exit_qs.filter(status='withdrawn').count()
        transfers_exits = exit_qs.count()

        # In case there are transfer records in future
        transfers_in = 0

        return Response({
            "total_students": total_students,
            "active_students": total_students,
            "new_admissions": new_admissions,
            "gender_breakdown": {
                "male": male_count,
                "female": female_count,
                "other": other_count
            },
            "class_distribution": class_distribution,
            "transfers_exits": transfers_exits,
            "transfers_in": transfers_in,
            "transfers_out": transfers_out,
            "dropouts": dropouts,
            "current_term": {
                "id": current_term.id if current_term else None,
                "name": current_term.name if current_term else None,
                "start_date": str(current_term.start_date) if current_term and current_term.start_date else None,
                "end_date": str(current_term.end_date) if current_term and current_term.end_date else None,
            } if current_term else None,
            "academic_year": {
                "id": current_ay.id if current_ay else None,
                "name": current_ay.name if current_ay else None,
            } if current_ay else None,
        })

    @action(detail=False, methods=['get'], url_path='overview_stats')
    def overview_stats_alias(self, request):
        """Snake_case alias for overview-stats."""
        return self.overview_stats(request)

    @action(detail=False, methods=['get'])
    def nominal_roll(self, request):
        """
        Retrieves the nominal roll (active students).
        Supports filtering by academic_year, term, grade, stream, gender, status, campus.
        Optimized with select_related to eliminate N+1 queries on User.
        """
        from datetime import date

        queryset = Enrollment.objects.filter(is_active=True, is_deleted=False).select_related(
            'student__student', 'grade', 'stream', 'term', 'academic_year', 'campus'
        )

        academic_year = request.query_params.get('academic_year')
        term = request.query_params.get('term')
        grade = request.query_params.get('grade')
        stream = request.query_params.get('stream')
        gender = request.query_params.get('gender')
        status = request.query_params.get('status')
        campus = request.query_params.get('campus')

        if academic_year:
            queryset = queryset.filter(academic_year_id=academic_year)
        if term:
            queryset = queryset.filter(term_id=term)
        if grade:
            queryset = queryset.filter(grade_id=grade)
        if stream:
            queryset = queryset.filter(stream_id=stream)
        if gender:
            queryset = queryset.filter(student__student__gender=gender)
        if status:
            queryset = queryset.filter(status=status)

        # Enforce server-side campus restriction
        from core.campus_filter import get_effective_campus_id
        effective_campus_id = get_effective_campus_id(request)
        if effective_campus_id:
            queryset = queryset.filter(campus_id=effective_campus_id)

        queryset = queryset.order_by('grade__level_order', 'student__student__first_name')

        today = date.today()
        data = []
        for enr in queryset:
            student = enr.student
            user_obj = student.student
            age = None
            if student.date_of_birth:
                dob = student.date_of_birth
                age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

            full_name = f"{user_obj.first_name} {user_obj.last_name}".strip() or user_obj.username
            data.append({
                'id': student.id,
                'admission_number': student.admission_number,
                'first_name': user_obj.first_name,
                'last_name': user_obj.last_name,
                'full_name': full_name,
                'gender': user_obj.gender,
                'grade': enr.grade.name if enr.grade else 'N/A',
                'stream': enr.stream.name if enr.stream else 'N/A',
                'admission_date': student.admission_date,
                'status': enr.get_status_display(),
                'age': age,
            })

        return Response(data)

    @action(detail=False, methods=['get'])
    def demographics(self, request):
        """
        Retrieves demographic data for reporting (campus-scoped).
        """
        from core.campus_filter import get_effective_campus_id
        effective_cid = get_effective_campus_id(request)
        base_all = Student.objects.filter(campus_id=effective_cid) if effective_cid else Student.objects.all()
        queryset = base_all.filter(status='active')
        
        # Gender breakdown
        gender_stats = queryset.values('student__gender').annotate(count=Count('id'))
        
        # Nationality and religion
        nationality_stats = queryset.values('nationality').annotate(count=Count('id'))
        religion_stats = queryset.values('religion').annotate(count=Count('id'))
        
        # Enrollment status
        status_stats = base_all.values('status').annotate(count=Count('id'))

        return Response({
            'gender': gender_stats,
            'nationality': nationality_stats,
            'religion': religion_stats,
            'status': status_stats,
        })

    @action(detail=False, methods=['get'])
    def enrollment_trends(self, request):
        """
        Retrieves admission and enrollment trends (campus-scoped).
        """
        from django.db.models.functions import TruncMonth, TruncYear
        from core.campus_filter import get_effective_campus_id
        effective_cid = get_effective_campus_id(request)
        base_qs = Student.objects.filter(campus_id=effective_cid) if effective_cid else Student.objects.all()
        
        admissions_by_year = base_qs\
            .annotate(year=TruncYear('admission_date'))\
            .values('year')\
            .annotate(count=Count('id'))\
            .order_by('year')
            
        return Response({
            'admissions_by_year': admissions_by_year,
        })
        
    @action(detail=False, methods=['get'])
    def class_distribution(self, request):
        """
        Retrieves class and stream capacity distribution (campus-scoped).
        """
        from core.campus_filter import get_effective_campus_id
        effective_cid = get_effective_campus_id(request)
        enr_base = Enrollment.objects.filter(is_active=True, is_deleted=False)
        if effective_cid:
            enr_base = enr_base.filter(campus_id=effective_cid)

        distribution = enr_base\
            .values('grade__name')\
            .annotate(count=Count('id'))\
            .order_by('grade__level_order')
            
        stream_distribution = enr_base.filter(stream__isnull=False)\
            .values('grade__name', 'stream__name')\
            .annotate(count=Count('id'))\
            .order_by('grade__level_order', 'stream__name')
            
        return Response({
            'grade_distribution': distribution,
            'stream_distribution': stream_distribution,
        })
        
    @action(detail=False, methods=['get'])
    def progression_transitions(self, request):
        """
        Retrieves student progression stats (promotions, repetitions) (campus-scoped).
        """
        from core.campus_filter import get_effective_campus_id
        effective_cid = get_effective_campus_id(request)
        enr_base = Enrollment.objects.filter(is_deleted=False)
        if effective_cid:
            enr_base = enr_base.filter(campus_id=effective_cid)
        status_stats = enr_base\
            .values('status')\
            .annotate(count=Count('id'))
            
        return Response({
            'progression': status_stats,
        })

    # ── Phase 2 Complete Reports Endpoints ────────────────────────────────────

    def _generate_report_table_html(self, export_data: dict) -> str:
        from django.utils.html import escape
        metadata = export_data.get('metadata', {})
        summaries = export_data.get('summaries', {})
        columns = export_data.get('columns', [])
        results = export_data.get('results', [])

        title = escape(metadata.get('title', 'Student Management Report'))
        desc = escape(metadata.get('description', ''))

        # Summary badges / chips
        summary_chips = []
        for k, v in summaries.items():
            label = escape(k.replace('_', ' ').title())
            summary_chips.append(
                f'<span style="display: inline-block; background-color: #f1f5f9; border: 1px solid #cbd5e1; '
                f'padding: 3px 8px; border-radius: 4px; margin-right: 8px; margin-bottom: 4px; font-size: 8pt; color: #334155;">'
                f'<strong>{label}:</strong> {escape(str(v))}'
                f'</span>'
            )
        chips_html = "".join(summary_chips)

        header_th = []
        for col in columns:
            align = col.get("align", "left")
            label = escape(col.get("label", ""))
            header_th.append(f'<th style="text-align: {align}; padding: 6px 8px; font-size: 8pt;">{label}</th>')

        rows_tr = []
        for row in results:
            cells_td = []
            for col in columns:
                align = col.get("align", "left")
                raw_val = row.get(col["key"])
                val = escape(str(raw_val if raw_val is not None else "—"))
                cells_td.append(f'<td style="text-align: {align}; padding: 5px 8px; font-size: 8pt;">{val}</td>')
            rows_tr.append(f'<tr>{"".join(cells_td)}</tr>')

        html = f"""
        <div style="margin-bottom: 12px;">
            <h2 style="font-size: 13pt; font-weight: 800; color: #1e3a8a; margin: 0 0 4px 0;">{title}</h2>
            {f'<p style="font-size: 8.5pt; color: #64748b; margin: 0 0 6px 0;">{desc}</p>' if desc else ''}
            {f'<div style="margin-top: 6px; margin-bottom: 8px;">{chips_html}</div>' if chips_html else ''}
        </div>
        <table class="report-table data-table" style="width: 100%; border-collapse: collapse;">
            <thead>
                <tr>{"".join(header_th)}</tr>
            </thead>
            <tbody>
                {"".join(rows_tr) if rows_tr else f'<tr><td colspan="{len(columns)}" style="text-align: center; color: #94a3b8; padding: 20px;">No records matching filter criteria.</td></tr>'}
            </tbody>
        </table>
        """
        return html

    def _handle_report_export(self, report_instance, filename_prefix: str, request, orientation: str = "portrait"):
        import copy
        from django.http import HttpResponse
        from student_management.reports.exporters.excel_generator import ReportExcelGenerator
        from student_management.reports.exporters.word_generator import ReportWordGenerator
        from documents.models import (
            DocumentTemplate, get_default_header_config, get_default_footer_config,
            get_default_watermark_config, get_default_page_config, get_default_table_config
        )
        from documents.rendering.pdf import render_pdf_bytes, get_default_context
        from core.models import InstitutionProfile

        params = getattr(request, 'query_params', getattr(request, 'GET', {}))
        fmt = params.get('format', 'pdf').lower()
        export_data = report_instance.get_export_data()

        if fmt == 'excel' or fmt == 'xlsx':
            content = ReportExcelGenerator.generate(export_data)
            resp = HttpResponse(
                content,
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            resp['Content-Disposition'] = f'attachment; filename="{filename_prefix}_{export_data["metadata"]["report_id"]}.xlsx"'
            return resp

        elif fmt == 'word' or fmt == 'docx':
            content = ReportWordGenerator.generate(export_data)
            resp = HttpResponse(
                content,
                content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )
            resp['Content-Disposition'] = f'attachment; filename="{filename_prefix}_{export_data["metadata"]["report_id"]}.docx"'
            return resp

        else:  # Default PDF using Document Design Studio template
            template_id = params.get('template_id')
            template = None
            if template_id:
                try:
                    template = DocumentTemplate.objects.filter(id=int(template_id)).first()
                except (ValueError, TypeError):
                    template = None

            if not template:
                template = DocumentTemplate.objects.filter(
                    category=DocumentTemplate.Category.STUDENT_REPORT,
                    status=DocumentTemplate.Status.PUBLISHED,
                ).order_by('-is_default', '-updated_at').first()

            if not template:
                # Fall back to general published template
                template = DocumentTemplate.objects.filter(
                    category=DocumentTemplate.Category.GENERAL,
                    status=DocumentTemplate.Status.PUBLISHED,
                ).order_by('-is_default', '-updated_at').first()

            if not template:
                # Auto-provision standard default published template for student reports so exports always succeed
                inst = InstitutionProfile.get_instance()
                page_cfg = get_default_page_config()
                page_cfg["orientation"] = orientation or "landscape"
                template, _ = DocumentTemplate.objects.get_or_create(
                    category=DocumentTemplate.Category.STUDENT_REPORT,
                    status=DocumentTemplate.Status.PUBLISHED,
                    defaults={
                        "name": "Official Student Academic & Register Report",
                        "institution": inst,
                        "description": "Standard institutional template for student reports and registers.",
                        "header_config": get_default_header_config(),
                        "footer_config": get_default_footer_config(),
                        "watermark_config": get_default_watermark_config(),
                        "page_config": page_cfg,
                        "table_config": get_default_table_config(),
                        "is_default": True,
                    }
                )

            # Ensure page config matches report orientation
            effective_template = copy.copy(template)
            if orientation and effective_template.page_config:
                effective_template.page_config = copy.deepcopy(effective_template.page_config)
                effective_template.page_config["orientation"] = orientation

            inst = InstitutionProfile.get_instance()
            context = get_default_context(inst)
            context["document_title"] = export_data.get("metadata", {}).get("title", "Student Report")

            body_html = self._generate_report_table_html(export_data)
            pdf_bytes = render_pdf_bytes(effective_template, context=context, html_body=body_html)

            inline = params.get('inline') in ['1', 'true', True] or params.get('view') in ['1', 'true', True]
            disposition = 'inline' if inline else f'attachment; filename="{filename_prefix}_{export_data["metadata"]["report_id"]}.pdf"'
            resp = HttpResponse(pdf_bytes, content_type='application/pdf')
            resp['Content-Disposition'] = disposition
            return resp

    @action(detail=False, methods=['get'])
    def master_register_preview(self, request):
        """On-screen preview for the Student Master Register with pagination and full-set summaries."""
        from student_management.reports.services.master_register_report import StudentMasterRegisterReport
        params = getattr(request, 'query_params', getattr(request, 'GET', {}))
        report = StudentMasterRegisterReport(request.user, params)
        page = params.get('page', 1)
        page_size = params.get('page_size', 50)
        return Response(report.get_preview_data(page=page, page_size=page_size))

    @action(detail=False, methods=['get'])
    def master_register_export(self, request):
        """Export the Student Master Register in PDF, Excel, or Word."""
        from student_management.reports.services.master_register_report import StudentMasterRegisterReport
        params = getattr(request, 'query_params', getattr(request, 'GET', {}))
        report = StudentMasterRegisterReport(request.user, params)
        return self._handle_report_export(report, "master_register", request, orientation="landscape")

    @action(detail=False, methods=['get'])
    def class_list_preview(self, request):
        """On-screen preview for the Official Class List with pagination and full-set summaries."""
        from student_management.reports.services.class_list_report import OfficialClassListReport
        params = getattr(request, 'query_params', getattr(request, 'GET', {}))
        report = OfficialClassListReport(request.user, params)
        page = params.get('page', 1)
        page_size = params.get('page_size', 50)
        return Response(report.get_preview_data(page=page, page_size=page_size))

    @action(detail=False, methods=['get'])
    def class_list_export(self, request):
        """Export the Official Class List in PDF, Excel, or Word."""
        from student_management.reports.services.class_list_report import OfficialClassListReport
        params = getattr(request, 'query_params', getattr(request, 'GET', {}))
        report = OfficialClassListReport(request.user, params)
        return self._handle_report_export(report, "class_list", request, orientation="portrait")

    @action(detail=False, methods=['get'])
    def contact_directory_preview(self, request):
        """On-screen preview for the Student & Guardian Contact Directory."""
        from student_management.reports.services.contact_directory_report import ContactDirectoryReport
        params = getattr(request, 'query_params', getattr(request, 'GET', {}))
        report = ContactDirectoryReport(request.user, params)
        page = params.get('page', 1)
        page_size = params.get('page_size', 50)
        return Response(report.get_preview_data(page=page, page_size=page_size))

    @action(detail=False, methods=['get'])
    def contact_directory_export(self, request):
        """Export the Student & Guardian Contact Directory in PDF, Excel, or Word."""
        from student_management.reports.services.contact_directory_report import ContactDirectoryReport
        params = getattr(request, 'query_params', getattr(request, 'GET', {}))
        report = ContactDirectoryReport(request.user, params)
        return self._handle_report_export(report, "contact_directory", request, orientation="landscape")

    @action(detail=False, methods=['get'])
    def admissions_register_preview(self, request):
        """On-screen preview for the Official Admissions Register."""
        from student_management.reports.services.admissions_register_report import AdmissionsRegisterReport
        params = getattr(request, 'query_params', getattr(request, 'GET', {}))
        report = AdmissionsRegisterReport(request.user, params)
        page = params.get('page', 1)
        page_size = params.get('page_size', 50)
        return Response(report.get_preview_data(page=page, page_size=page_size))

    @action(detail=False, methods=['get'])
    def admissions_register_export(self, request):
        """Export the Official Admissions Register in PDF, Excel, or Word."""
        from student_management.reports.services.admissions_register_report import AdmissionsRegisterReport
        params = getattr(request, 'query_params', getattr(request, 'GET', {}))
        report = AdmissionsRegisterReport(request.user, params)
        return self._handle_report_export(report, "admissions_register", request, orientation="landscape")

    @action(detail=False, methods=['get'], url_path='campus-comparison')
    def campus_comparison(self, request):
        """
        Mode C: Cross-Campus Comparative & Consolidated Reporting across:
        - Student Management (Enrolment, Active, Admissions, Gender, Attendance)
        - Student Finance (Invoiced, Collected, Outstanding Arrears, Defaulters, Collection Rate)
        - Academic Performance (Exam Entries, Mean Score, Pass Rate)
        - Human Resources & Operations (Total Staff, Active Staff, Teaching/Non-Teaching, Student-Staff Ratio, Departments)

        Enforces multi-campus authorization and computes percentages/averages from raw numerators and denominators.
        Supports JSON response and CSV/Excel/PDF exports via ?export_format=csv|excel|pdf.
        """
        import csv
        from decimal import Decimal
        from django.db.models import Sum, Avg
        from django.http import HttpResponse
        from django.utils import timezone
        from core.campus_filter import is_user_institution_admin, get_user_allowed_campus_ids
        from core.models import InstitutionProfile
        from workforce.models import Campus, Department
        from workforce.core_models import Employee
        from fees.models import FeeInvoice
        from student_settings.models import AcademicYear, Term

        user = request.user
        is_inst_admin = is_user_institution_admin(user)
        allowed_ids = get_user_allowed_campus_ids(user)

        if not is_inst_admin and len(allowed_ids) < 2:
            return Response(
                {'detail': 'Campus comparison requires Institution Administrator access or authorization for at least two campuses.'},
                status=403
            )

        campuses_qs = Campus.objects.filter(is_active=True).order_by('name')
        if not is_inst_admin:
            campuses_qs = campuses_qs.filter(id__in=allowed_ids)

        raw_campus_ids = request.query_params.get('campus_ids', '').strip()
        if raw_campus_ids:
            req_ids = []
            for part in raw_campus_ids.split(','):
                part = part.strip()
                if part.isdigit():
                    req_ids.append(int(part))
            if req_ids:
                campuses_qs = campuses_qs.filter(id__in=req_ids)

        academic_year_id = request.query_params.get('academic_year')
        term_id = request.query_params.get('term')
        ay_obj = AcademicYear.objects.filter(id=academic_year_id).first() if academic_year_id and str(academic_year_id).isdigit() else None
        term_obj = Term.objects.filter(id=term_id).first() if term_id and str(term_id).isdigit() else None

        campuses = list(campuses_qs)

        # Accumulators for true consolidated institution totals (raw numerators/denominators)
        tot_students = 0
        tot_active_students = 0
        tot_new_admissions = 0
        tot_male = 0
        tot_female = 0
        tot_exits = 0
        tot_att_present = 0
        tot_att_records = 0

        tot_invoiced = Decimal('0.00')
        tot_collected = Decimal('0.00')
        tot_arrears = Decimal('0.00')
        tot_defaulters = 0

        tot_exam_entries = 0
        tot_weighted_mark_sum = 0.0
        tot_exam_passes = 0

        tot_staff = 0
        tot_active_staff = 0
        tot_teaching = 0
        tot_non_teaching = 0
        tot_departments = 0

        campus_rows = []
        for camp in campuses:
            # 1. Student metrics
            st_qs = Student.objects.filter(campus=camp)
            c_total_students = st_qs.count()
            c_active_qs = st_qs.filter(status='active')
            c_active_students = c_active_qs.count()

            if term_obj and term_obj.start_date:
                adm_q = Q(admission_date__gte=term_obj.start_date)
                if term_obj.end_date:
                    adm_q &= Q(admission_date__lte=term_obj.end_date)
                c_new_adm = st_qs.filter(adm_q).count()
            elif ay_obj and ay_obj.start_date:
                adm_q = Q(admission_date__gte=ay_obj.start_date)
                if ay_obj.end_date:
                    adm_q &= Q(admission_date__lte=ay_obj.end_date)
                c_new_adm = st_qs.filter(adm_q).count()
            else:
                c_new_adm = st_qs.filter(admission_date__year=timezone.now().year).count()

            g_counts = dict(c_active_qs.values_list('student__gender').annotate(c=Count('id')))
            c_male = g_counts.get('M', 0) + g_counts.get('Male', 0) + g_counts.get('male', 0)
            c_female = g_counts.get('F', 0) + g_counts.get('Female', 0) + g_counts.get('female', 0)
            c_exits = st_qs.filter(status__in=['transferred', 'withdrawn']).count()

            c_att_total = 0
            c_att_present = 0
            try:
                from student_management.models.class_session import SessionAttendance
                att_qs = SessionAttendance.objects.filter(student__campus=camp)
                if term_obj and term_obj.start_date:
                    att_qs = att_qs.filter(date__gte=term_obj.start_date)
                    if term_obj.end_date:
                        att_qs = att_qs.filter(date__lte=term_obj.end_date)
                c_att_total = att_qs.count()
                c_att_present = att_qs.filter(status='present').count()
            except Exception:
                pass
            c_att_rate = round((c_att_present / c_att_total) * 100, 1) if c_att_total > 0 else 0.0

            # 2. Finance metrics
            inv_qs = FeeInvoice.objects.filter(student__campus=camp).exclude(status='VOID')
            if ay_obj:
                inv_qs = inv_qs.filter(academic_year=ay_obj)
            if term_obj:
                inv_qs = inv_qs.filter(term=term_obj)
            inv_agg = inv_qs.aggregate(
                invoiced=Sum('total_amount'),
                collected=Sum('paid_amount'),
                arrears=Sum('balance'),
            )
            c_invoiced = inv_agg['invoiced'] or Decimal('0.00')
            c_collected = inv_agg['collected'] or Decimal('0.00')
            c_arrears = inv_agg['arrears'] or Decimal('0.00')
            c_defaulters = inv_qs.filter(balance__gt=0).values('student').distinct().count()
            c_collection_rate = round(float(c_collected) / float(c_invoiced) * 100, 1) if c_invoiced > 0 else 0.0
            c_avg_fee = round(float(c_invoiced) / c_active_students, 2) if c_active_students > 0 else 0.0

            # 3. Academic performance metrics
            c_exam_entries = 0
            c_mean_score = 0.0
            c_pass_count = 0
            c_pass_rate = 0.0
            try:
                from examinations.models import TermSubjectResult
                ex_qs = TermSubjectResult.objects.filter(term_result__student__campus=camp)
                if ay_obj:
                    ex_qs = ex_qs.filter(term_result__academic_year=ay_obj)
                if term_obj:
                    ex_qs = ex_qs.filter(term_result__term=term_obj)
                c_exam_entries = ex_qs.count()
                if c_exam_entries > 0:
                    c_mean_score = round(float(ex_qs.aggregate(avg=Avg('weighted_mark'))['avg'] or 0.0), 1)
                    c_pass_count = ex_qs.filter(weighted_mark__gte=50).count()
                    c_pass_rate = round((c_pass_count / c_exam_entries) * 100, 1)
            except Exception:
                pass

            # 4. HR & Workforce metrics
            emp_qs = Employee.objects.filter(campus=camp)
            c_staff = emp_qs.count()
            c_active_staff = emp_qs.filter(employment_status='active').count()
            c_teaching = emp_qs.filter(employee_category='teaching').count()
            c_non_teaching = emp_qs.filter(employee_category='non_teaching').count()
            c_depts = Department.objects.filter(campus=camp).count()
            c_ratio = round(c_active_students / c_active_staff, 1) if c_active_staff > 0 else 0.0

            # Accumulate raw totals
            tot_students += c_total_students
            tot_active_students += c_active_students
            tot_new_admissions += c_new_adm
            tot_male += c_male
            tot_female += c_female
            tot_exits += c_exits
            tot_att_present += c_att_present
            tot_att_records += c_att_total

            tot_invoiced += c_invoiced
            tot_collected += c_collected
            tot_arrears += c_arrears
            tot_defaulters += c_defaulters

            tot_exam_entries += c_exam_entries
            tot_weighted_mark_sum += (c_mean_score * c_exam_entries)
            tot_exam_passes += c_pass_count

            tot_staff += c_staff
            tot_active_staff += c_active_staff
            tot_teaching += c_teaching
            tot_non_teaching += c_non_teaching
            tot_departments += c_depts

            campus_rows.append({
                'campus_id': camp.id,
                'campus_name': camp.name,
                'campus_code': camp.code,
                'operational_status': camp.operational_status,
                'students': {
                    'total_students': c_total_students,
                    'active_students': c_active_students,
                    'new_admissions': c_new_adm,
                    'male': c_male,
                    'female': c_female,
                    'transfers_exits': c_exits,
                    'attendance_rate_pct': c_att_rate,
                    'enrolment_share_pct': 0.0,
                },
                'finance': {
                    'total_invoiced': float(c_invoiced),
                    'total_collected': float(c_collected),
                    'outstanding_arrears': float(c_arrears),
                    'defaulter_count': c_defaulters,
                    'collection_rate_pct': c_collection_rate,
                    'average_fee_per_student': c_avg_fee,
                    'revenue_share_pct': 0.0,
                    'collection_rate_variance': 0.0,
                },
                'academics': {
                    'exam_entries': c_exam_entries,
                    'mean_score': c_mean_score,
                    'pass_rate_pct': c_pass_rate,
                    'mean_score_variance': 0.0,
                },
                'workforce': {
                    'total_staff': c_staff,
                    'active_staff': c_active_staff,
                    'teaching_staff': c_teaching,
                    'non_teaching_staff': c_non_teaching,
                    'departments_count': c_depts,
                    'student_to_staff_ratio': c_ratio,
                },
            })

        # Compute consolidated institutional metrics from raw numerators/denominators
        inst_att_rate = round((tot_att_present / tot_att_records) * 100, 1) if tot_att_records > 0 else 0.0
        inst_collection_rate = round(float(tot_collected) / float(tot_invoiced) * 100, 1) if tot_invoiced > 0 else 0.0
        inst_avg_fee = round(float(tot_invoiced) / tot_active_students, 2) if tot_active_students > 0 else 0.0
        inst_mean_score = round(tot_weighted_mark_sum / tot_exam_entries, 1) if tot_exam_entries > 0 else 0.0
        inst_pass_rate = round((tot_exam_passes / tot_exam_entries) * 100, 1) if tot_exam_entries > 0 else 0.0
        inst_ratio = round(tot_active_students / tot_active_staff, 1) if tot_active_staff > 0 else 0.0

        # Populate shares and variances relative to institutional consolidated figures
        for row in campus_rows:
            row['students']['enrolment_share_pct'] = (
                round((row['students']['active_students'] / tot_active_students) * 100, 1)
                if tot_active_students > 0 else 0.0
            )
            row['finance']['revenue_share_pct'] = (
                round((row['finance']['total_collected'] / float(tot_collected)) * 100, 1)
                if tot_collected > 0 else 0.0
            )
            row['finance']['collection_rate_variance'] = round(
                row['finance']['collection_rate_pct'] - inst_collection_rate, 1
            )
            row['academics']['mean_score_variance'] = round(
                row['academics']['mean_score'] - inst_mean_score, 1
            )

        consolidated = {
            'students': {
                'total_students': tot_students,
                'active_students': tot_active_students,
                'new_admissions': tot_new_admissions,
                'male': tot_male,
                'female': tot_female,
                'transfers_exits': tot_exits,
                'attendance_rate_pct': inst_att_rate,
            },
            'finance': {
                'total_invoiced': float(tot_invoiced),
                'total_collected': float(tot_collected),
                'outstanding_arrears': float(tot_arrears),
                'defaulter_count': tot_defaulters,
                'collection_rate_pct': inst_collection_rate,
                'average_fee_per_student': inst_avg_fee,
            },
            'academics': {
                'exam_entries': tot_exam_entries,
                'mean_score': inst_mean_score,
                'pass_rate_pct': inst_pass_rate,
            },
            'workforce': {
                'total_staff': tot_staff,
                'active_staff': tot_active_staff,
                'teaching_staff': tot_teaching,
                'non_teaching_staff': tot_non_teaching,
                'departments_count': tot_departments,
                'student_to_staff_ratio': inst_ratio,
            },
        }

        inst_profile = InstitutionProfile.get_instance()
        metadata = {
            'report_id': 'CMP-01',
            'title': 'Multi-Campus Comparative Performance Report',
            'institution_name': inst_profile.name if inst_profile else 'Fahari Academia',
            'report_scope': 'Cross-Campus Comparison & Consolidated Summary',
            'compared_campuses': [f"{c.name} ({c.code})" for c in campuses],
            'academic_year': ay_obj.name if ay_obj else 'All Academic Years',
            'term': term_obj.name if term_obj else 'All Terms',
            'generated_by': (user.get_full_name() if callable(getattr(user, 'get_full_name', None)) else getattr(user, 'get_full_name', '')) or user.username,
            'generated_at': timezone.now().isoformat(),
        }

        export_fmt = (request.query_params.get('export_format') or request.query_params.get('format') or '').lower()
        if export_fmt in ('csv', 'excel', 'xlsx', 'pdf'):
            flat_rows = []
            for r in campus_rows:
                flat_rows.append({
                    'campus': f"{r['campus_name']} ({r['campus_code']})",
                    'active_students': r['students']['active_students'],
                    'enrolment_share': f"{r['students']['enrolment_share_pct']}%",
                    'new_admissions': r['students']['new_admissions'],
                    'invoiced': f"{r['finance']['total_invoiced']:,.2f}",
                    'collected': f"{r['finance']['total_collected']:,.2f}",
                    'arrears': f"{r['finance']['outstanding_arrears']:,.2f}",
                    'collection_rate': f"{r['finance']['collection_rate_pct']}%",
                    'mean_score': r['academics']['mean_score'],
                    'active_staff': r['workforce']['active_staff'],
                    'student_staff_ratio': f"{r['workforce']['student_to_staff_ratio']}:1",
                })
            flat_rows.append({
                'campus': 'INSTITUTION CONSOLIDATED TOTAL',
                'active_students': consolidated['students']['active_students'],
                'enrolment_share': '100.0%',
                'new_admissions': consolidated['students']['new_admissions'],
                'invoiced': f"{consolidated['finance']['total_invoiced']:,.2f}",
                'collected': f"{consolidated['finance']['total_collected']:,.2f}",
                'arrears': f"{consolidated['finance']['outstanding_arrears']:,.2f}",
                'collection_rate': f"{consolidated['finance']['collection_rate_pct']}%",
                'mean_score': consolidated['academics']['mean_score'],
                'active_staff': consolidated['workforce']['active_staff'],
                'student_staff_ratio': f"{consolidated['workforce']['student_to_staff_ratio']}:1",
            })

            columns = [
                {'key': 'campus', 'label': 'Campus', 'align': 'left'},
                {'key': 'active_students', 'label': 'Active Students', 'align': 'right'},
                {'key': 'enrolment_share', 'label': 'Enrolment Share', 'align': 'right'},
                {'key': 'new_admissions', 'label': 'New Admissions', 'align': 'right'},
                {'key': 'invoiced', 'label': 'Total Invoiced (KES)', 'align': 'right'},
                {'key': 'collected', 'label': 'Total Collected (KES)', 'align': 'right'},
                {'key': 'arrears', 'label': 'Arrears (KES)', 'align': 'right'},
                {'key': 'collection_rate', 'label': 'Collection Rate', 'align': 'right'},
                {'key': 'mean_score', 'label': 'Mean Exam Score', 'align': 'right'},
                {'key': 'active_staff', 'label': 'Active Staff', 'align': 'right'},
                {'key': 'student_staff_ratio', 'label': 'Student:Staff', 'align': 'right'},
            ]

            if export_fmt == 'csv':
                resp = HttpResponse(content_type='text/csv')
                resp['Content-Disposition'] = 'attachment; filename="campus_comparison_report.csv"'
                writer = csv.writer(resp)
                writer.writerow([metadata['title']])
                writer.writerow([
                    f"Institution: {metadata['institution_name']}",
                    f"Scope: {', '.join(metadata['compared_campuses'])}",
                    f"Period: {metadata['academic_year']} - {metadata['term']}",
                    f"Generated By: {metadata['generated_by']}",
                ])
                writer.writerow([])
                writer.writerow([c['label'] for c in columns])
                for fr in flat_rows:
                    writer.writerow([fr.get(c['key'], '') for c in columns])
                return resp

            export_payload = {
                'metadata': {
                    **metadata,
                    'description': f"Comparative analysis across {len(campuses)} campuses ({', '.join(metadata['compared_campuses'])}) for {metadata['academic_year']} ({metadata['term']}).",
                },
                'summaries': {
                    'campuses_compared': len(campuses),
                    'consolidated_students': consolidated['students']['active_students'],
                    'consolidated_invoiced': f"KES {consolidated['finance']['total_invoiced']:,.2f}",
                    'consolidated_collected': f"KES {consolidated['finance']['total_collected']:,.2f}",
                    'consolidated_collection_rate': f"{consolidated['finance']['collection_rate_pct']}%",
                    'consolidated_staff': consolidated['workforce']['active_staff'],
                },
                'columns': columns,
                'results': flat_rows,
            }

            class _ComparisonExportAdapter:
                def get_export_data(self):
                    return export_payload

            return self._handle_report_export(_ComparisonExportAdapter(), "campus_comparison", request, orientation="landscape")

        return Response({
            'metadata': metadata,
            'consolidated': consolidated,
            'campuses': campus_rows,
        })
