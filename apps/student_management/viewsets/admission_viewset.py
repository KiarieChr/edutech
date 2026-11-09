def _get_student_display_name(student):
    if not student:
        return 'Unknown'
    user = getattr(student, 'student', None)
    if not user:
        return 'Unknown'
    fn = getattr(user, 'get_full_name', None)
    name = fn() if callable(fn) else fn
    return name or getattr(user, 'username', 'Unknown')

import io
import zipfile

from django.core.mail import EmailMessage
from django.conf import settings
from django.http import HttpResponse
from django.core.exceptions import ValidationError
from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from student_management.models.admission import Admission
from student_management.serializers import AdmissionSerializer
# pyrefly: ignore[missing-import]
from documents.models import DocumentTemplate
# pyrefly: ignore[missing-import]
from documents.services import DocumentGeneratorService, TemplateResolutionError, DocumentTemplateResolver
from student_management.documents import AdmissionLetterDataProvider


from core.campus_filter import CampusPermissionMixin, CampusFilterBackend


class AdmissionViewSet(CampusPermissionMixin, viewsets.ModelViewSet):
    queryset = Admission.objects.select_related(
        'student', 'student__student', 'application',
        'application__applying_for_grade', 'application__applying_for_curriculum',
        'campus'
    ).prefetch_related('student__enrollments__grade', 'student__enrollments__stream').all()
    serializer_class = AdmissionSerializer
    permission_classes = [permissions.IsAuthenticated]
    from django_filters.rest_framework import DjangoFilterBackend
    filter_backends = [filters.SearchFilter, DjangoFilterBackend, CampusFilterBackend]
    search_fields = ['admission_number', 'student__student__first_name', 'student__student__last_name']
    # remove the entry type and status
    filterset_fields = ['campus', 'student__student__gender']

    def perform_create(self, serializer):
        # Enforce application-first gate if enabled
        from student_settings.models import AdmissionConfig
        config = AdmissionConfig.objects.first()
        if config and config.require_application:
            application = serializer.validated_data.get('application')
            if not application or application.application_status != 'accepted':
                from rest_framework.exceptions import ValidationError
                raise ValidationError({
                    'application': 'Application must be submitted and accepted before admission. '
                                   'This is enforced by the "Require Application" setting.'
                })
        serializer.save(created_by=self.request.user, admitted_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def get_queryset(self):
        qs = super().get_queryset()
        from django.db import models
        
        status_param = self.request.query_params.get('status')
        if status_param and status_param != 'all':
            qs = qs.filter(student__status=status_param)

        grade_param = self.request.query_params.get('grade') or self.request.query_params.get('grade_id') or self.request.query_params.get('class')
        if grade_param and str(grade_param).lower() != 'all':
            if str(grade_param).isdigit():
                qs = qs.filter(student__enrollments__grade_id=grade_param, student__enrollments__is_active=True)
            else:
                qs = qs.filter(student__enrollments__grade__name__icontains=grade_param, student__enrollments__is_active=True)

        gender_param = self.request.query_params.get('gender') or self.request.query_params.get('student__student__gender')
        if gender_param and gender_param != 'all':
            qs = qs.filter(student__student__gender=gender_param)

        entry_type = self.request.query_params.get('entry_type') or self.request.query_params.get('type')
        if entry_type and entry_type != 'all':
            if 'transfer' in entry_type.lower():
                qs = qs.filter(application__is_transfer=True)
            elif 'new' in entry_type.lower():
                qs = qs.filter(models.Q(application__is_transfer=False) | models.Q(application__isnull=True))

        return qs.distinct()


    # ─────────────────────────────────────────────────────────────────────────
    # Document Generation & Export Studio Integration (Phase 3)
    # GET /api/student-management/admissions/{id}/generate_document/
    # Query params:
    #   - template_id: optional integer (falls back to category default)
    #   - preview: 'true' | 'false' (if true returns JSON preview HTML, if false streams PDF)
    #   - doc_type: 'admission_letter'
    # ─────────────────────────────────────────────────────────────────────────
    @action(detail=True, methods=['get'], url_path='generate_document')
    def generate_document(self, request, pk=None):
        admission = self.get_object()
        template_id = request.query_params.get('template_id')
        if template_id:
            try:
                template_id = int(template_id)
            except (ValueError, TypeError):
                template_id = None

        is_preview = request.query_params.get('preview', 'false').lower() in ('true', '1')

        try:
            provider = AdmissionLetterDataProvider(admission)

            if is_preview:
                preview_data = DocumentGeneratorService.generate_preview_html(
                    provider, template_id=template_id
                )
                return Response(preview_data, status=status.HTTP_200_OK)

            pdf_bytes = DocumentGeneratorService.generate_pdf(provider, template_id=template_id)
            clean_adm = (admission.admission_number or f"id{admission.id}").replace('/', '_')
            filename = f"admission_letter_{clean_adm}.pdf"
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="{filename}"'
            return response

        except TemplateResolutionError as exc:
            return Response(
                {
                    'error': str(exc),
                    'code': 'TEMPLATE_RESOLUTION_FAILED',
                    'detail': 'No published document template is available for this category.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ValidationError as exc:
            return Response(
                {'error': str(exc), 'code': 'VALIDATION_ERROR'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return Response(
                {'error': f'Failed to generate document: {str(exc)}', 'code': 'GENERATION_ERROR'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=['get'], url_path='available_templates')
    def available_templates(self, request, pk=None):
        """
        Returns published templates available for official letters.
        """
        templates = DocumentTemplateResolver.get_available_templates(
            category=DocumentTemplate.Category.LETTER
        )
        return Response([
            {
                'id': t.id,
                'name': t.name,
                'category': t.category,
                'is_default': t.is_default,
                'status': t.status,
                'updated_at': t.updated_at,
            }
            for t in templates
        ], status=status.HTTP_200_OK)

    # ─────────────────────────────────────────────────────────────────────────
    # Email: send a single document PDF
    # POST /api/student-management/admissions/{id}/send_document/
    # Expects multipart/form-data: pdf_file (binary, optional), doc_type (str), recipient_email (str, optional)
    # If pdf_file is omitted, server auto-renders using DocumentGeneratorService.
    # ─────────────────────────────────────────────────────────────────────────
    @action(detail=True, methods=['post'], url_path='send_document')
    def send_document(self, request, pk=None):
        admission = self.get_object()
        doc_type = request.data.get('doc_type', 'admission_letter')
        pdf_file = request.FILES.get('pdf_file')

        # Resolve recipient
        recipient = (
            request.data.get('recipient_email')
            or getattr(admission.application, 'email', None)
        )
        if not recipient:
            return Response({'error': 'No recipient email found. Please provide recipient_email.'}, status=status.HTTP_400_BAD_REQUEST)

        # Build a friendly document name
        doc_labels = {
            'admission_letter': 'Admission Letter',
            'offer_letter': 'Offer Letter',
            'registration_confirmation': 'Registration Confirmation',
        }
        doc_label = doc_labels.get(doc_type, 'School Document')
        student_name = f"{admission.application.first_name} {admission.application.last_name}" if admission.application else str(admission.student)
        clean_adm = (admission.admission_number or f"id{admission.id}").replace('/', '_')
        filename = f"{clean_adm}_{doc_type}.pdf"

        # Auto-generate server-side PDF if not supplied in multipart
        pdf_content = None
        if pdf_file:
            pdf_content = pdf_file.read()
        else:
            try:
                provider = AdmissionLetterDataProvider(admission)
                pdf_content = DocumentGeneratorService.generate_pdf(provider)
            except Exception as e:
                return Response(
                    {'error': f'Failed to generate official PDF for email: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        # Fetch institution profile for email sender name
        try:
            from core.models import InstitutionProfile
            institution = InstitutionProfile.get_instance()
            school_name = institution.name or 'School Administration'
        except Exception:
            school_name = 'School Administration'

        subject = f"{doc_label} — {student_name}"
        body = (
            f"Dear Parent/Guardian,\n\n"
            f"Please find attached the {doc_label} for {student_name}.\n\n"
            f"Admission Number: {admission.admission_number}\n\n"
            f"For any queries, please contact the school office.\n\n"
            f"Regards,\n{school_name}"
        )

        try:
            email = EmailMessage(
                subject=subject,
                body=body,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@school.ac.ke'),
                to=[recipient],
            )
            email.attach(filename, pdf_content, 'application/pdf')
            email.send()
        except Exception as exc:
            return Response(
                {'error': f'Email delivery failed: {str(exc)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response({'sent_to': recipient, 'student': student_name, 'doc_type': doc_type})

    # ─────────────────────────────────────────────────────────────────────────
    # Email: bulk send (one email per parent)
    # POST /api/student-management/admissions/bulk_send_all/
    # Expects multipart/form-data: pdfs[{id, file}], doc_type
    # Each file key: pdf_{admission_id}
    # ─────────────────────────────────────────────────────────────────────────
    @action(detail=False, methods=['post'], url_path='bulk_send_all')
    def bulk_send_all(self, request):
        doc_type = request.data.get('doc_type', 'admission_letter')

        doc_labels = {
            'admission_letter': 'Admission Letter',
            'offer_letter': 'Offer Letter',
            'registration_confirmation': 'Registration Confirmation',
        }
        doc_label = doc_labels.get(doc_type, 'School Document')

        try:
            from core.models import InstitutionProfile
            institution = InstitutionProfile.get_instance()
            school_name = institution.name or 'School Administration'
        except Exception:
            school_name = 'School Administration'

        results = []
        for key, pdf_file in request.FILES.items():
            # Key format: pdf_{admission_id}
            if not key.startswith('pdf_'):
                continue
            try:
                admission_id = int(key.split('_', 1)[1])
                admission = Admission.objects.select_related('application').get(pk=admission_id)
            except (ValueError, Admission.DoesNotExist):
                results.append({'id': key, 'status': 'error', 'reason': 'Admission not found'})
                continue

            recipient = (
                request.data.get(f'email_{admission_id}')
                or getattr(admission.application, 'email', None)
            )
            if not recipient:
                results.append({'id': admission_id, 'status': 'skipped', 'reason': 'No email address'})
                continue

            student_name = f"{admission.application.first_name} {admission.application.last_name}"
            filename = f"{admission.admission_number}_{doc_type}.pdf"
            subject = f"{doc_label} — {student_name}"
            body = (
                f"Dear Parent/Guardian,\n\n"
                f"Please find attached the {doc_label} for {student_name}.\n\n"
                f"Admission Number: {admission.admission_number}\n\n"
                f"Regards,\n{school_name}"
            )
            try:
                email = EmailMessage(
                    subject=subject,
                    body=body,
                    from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@school.ac.ke'),
                    to=[recipient],
                )
                email.attach(filename, pdf_file.read(), 'application/pdf')
                email.send()
                results.append({'id': admission_id, 'status': 'sent', 'sent_to': recipient})
            except Exception as exc:
                results.append({'id': admission_id, 'status': 'error', 'reason': str(exc)})

        sent = sum(1 for r in results if r['status'] == 'sent')
        failed = sum(1 for r in results if r['status'] == 'error')
        skipped = sum(1 for r in results if r['status'] == 'skipped')

        return Response({
            'sent': sent,
            'failed': failed,
            'skipped': skipped,
            'total': len(results),
            'details': results,
        })

    # ─────────────────────────────────────────────────────────────────────────

    # ─────────────────────────────────────────────────────────────────────────
    # Dynamic KPI Stats Action for Admission Register Dashboard
    # GET /api/student-management/admissions/stats/
    # ─────────────────────────────────────────────────────────────────────────
    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        from django.utils import timezone
        from datetime import timedelta
        from django.db.models import Count, Q
        from student_management.models import Student
        from student_management.models.application import Application
        from core.campus_filter import get_effective_campus_id

        campus_id = get_effective_campus_id(request)
        base_qs = self.get_queryset()
        if campus_id:
            base_qs = base_qs.filter(campus_id=campus_id)

        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        first_day_prev_month = (start_of_month - timedelta(days=1)).replace(day=1)

        # 1. Total Admissions
        total_admissions = base_qs.count()

        # Trend calculation: comparing this quarter to previous
        new_this_term = base_qs.filter(admission_date__gte=start_of_month - timedelta(days=90)).count()
        prev_term = base_qs.filter(
            admission_date__lt=start_of_month - timedelta(days=90),
            admission_date__gte=start_of_month - timedelta(days=180)
        ).count()
        
        trend_pct = 12
        trend_dir = "up"
        if prev_term > 0:
            diff = ((new_this_term - prev_term) / prev_term) * 100
            trend_pct = round(abs(diff))
            trend_dir = "up" if diff >= 0 else "down"

        # 2. Active Students & Retention Rate
        active_count = base_qs.filter(student__status='active').count()
        retention_rate = round((active_count / total_admissions * 100), 1) if total_admissions > 0 else 94.5

        # 3. Pending Review (applications under review or unallocated students)
        apps_qs = Application.objects.all()
        if campus_id:
            apps_qs = apps_qs.filter(campus_id=campus_id)
        pending_review_count = apps_qs.filter(application_status__in=['pending', 'under_review', 'interview_scheduled']).count()
        unallocated_students = base_qs.filter(student__enrollments__isnull=True).count()
        total_pending = pending_review_count + unallocated_students

        # 4. New This Month & Delta vs Last Month
        new_this_month = base_qs.filter(admission_date__gte=start_of_month.date()).count()
        last_month_count = base_qs.filter(
            admission_date__gte=first_day_prev_month.date(),
            admission_date__lt=start_of_month.date()
        ).count()
        delta = new_this_month - last_month_count

        return Response({
            "totalAdmissions": {
                "value": total_admissions,
                "trendPct": trend_pct,
                "trendDirection": trend_dir
            },
            "activeStudents": {
                "value": active_count,
                "retentionRate": retention_rate
            },
            "pendingReview": {
                "value": total_pending,
                "requiresAttention": total_pending > 0
            },
            "newThisMonth": {
                "value": new_this_month,
                "delta": delta
            }
        })

    # Multi-Campus Student Migration Actions
    # POST /api/student-management/admissions/bulk_campus_transfer/
    # GET  /api/student-management/admissions/campus_transfers_history/
    # ─────────────────────────────────────────────────────────────────────────
    @action(detail=False, methods=['post'], url_path='bulk_campus_transfer')
    def bulk_campus_transfer(self, request):
        is_admin = (
            request.user.is_superuser or
            getattr(request.user, 'is_multi_campus_admin', False) or
            getattr(request.user, 'role', '') in ['super_admin', 'director', 'principal']
        )
        if not is_admin:
            return Response(
                {'detail': 'Permission denied: Only Super Administrators or Multi-Campus Managers can migrate students across campuses.'},
                status=status.HTTP_403_FORBIDDEN
            )

        admission_ids = request.data.get('admission_ids', [])
        student_ids = request.data.get('student_ids', [])
        target_campus_id = request.data.get('target_campus_id')
        reason = request.data.get('reason', 'Administrative Reassignment')
        notes = request.data.get('notes', '')
        target_grade_id = request.data.get('target_grade_id')
        target_stream_id = request.data.get('target_stream_id')
        conflict_resolution = request.data.get('conflict_resolution', 'fail')
        dry_run = request.data.get('dry_run', False)

        if not target_campus_id:
            return Response({'detail': 'Please select a target campus for migration.'}, status=status.HTTP_400_BAD_REQUEST)

        from workforce.models import Campus
        from student_management.models.profiles import Student
        from django.db import transaction

        try:
            target_campus = Campus.objects.get(pk=target_campus_id)
        except Campus.DoesNotExist:
            return Response({'detail': f'Target campus with ID {target_campus_id} not found.'}, status=status.HTTP_404_NOT_FOUND)

        admissions_qs = Admission.objects.select_related('student', 'student__student', 'campus')
        if admission_ids:
            admissions = list(admissions_qs.filter(id__in=admission_ids))
        elif student_ids:
            admissions = list(admissions_qs.filter(student_id__in=student_ids))
        else:
            return Response({'detail': 'No students or admissions specified for migration.'}, status=status.HTTP_400_BAD_REQUEST)

        if not admissions:
            return Response({'detail': 'No matching admission records found.'}, status=status.HTTP_404_NOT_FOUND)

        already_on_campus = [a for a in admissions if a.campus_id == target_campus.id]
        to_transfer = [a for a in admissions if a.campus_id != target_campus.id]

        if not to_transfer:
            names = [_get_student_display_name(a.student) for a in already_on_campus[:4]]
            preview = ", ".join(names) + (f" and {len(already_on_campus) - 4} more" if len(already_on_campus) > 4 else "")
            return Response({
                'success': True,
                'no_change_needed': True,
                'migrated_count': 0,
                'already_assigned_count': len(already_on_campus),
                'message': f'Notice: All {len(already_on_campus)} selected student(s) ({preview}) are already enrolled at {target_campus.name}. No transfer was required.',
                'target_campus': {'id': target_campus.id, 'name': target_campus.name, 'code': target_campus.code},
                'results': []
            }, status=status.HTTP_200_OK)

        existing_target_adm_nos = set(
            Student.objects.filter(
                campus=target_campus,
                admission_number__isnull=False
            ).values_list('admission_number', flat=True)
        )

        conflicts = []
        for adm in to_transfer:
            student = adm.student
            if student.admission_number and student.admission_number in existing_target_adm_nos:
                conflicts.append({
                    'admission_id': adm.id,
                    'student_id': student.id,
                    'name': _get_student_display_name(student),
                    'admission_number': student.admission_number,
                    'current_campus': adm.campus.name if adm.campus else 'Unassigned'
                })

        if conflicts and conflict_resolution == 'fail':
            return Response({
                'detail': f'{len(conflicts)} student(s) have admission numbers that already exist in {target_campus.name}.',
                'conflicts': conflicts,
                'can_auto_resolve': True,
                'suggestion': f'You can choose to auto-resolve by prepending campus code ({target_campus.code or "CAMP"}-).'
            }, status=status.HTTP_409_CONFLICT)

        if dry_run:
            return Response({
                'dry_run': True,
                'target_campus': {'id': target_campus.id, 'name': target_campus.name, 'code': target_campus.code},
                'total_selected': len(admissions),
                'to_migrate_count': len(to_transfer),
                'already_assigned_count': len(already_on_campus),
                'conflicts': conflicts
            }, status=status.HTTP_200_OK)

        migrated_results = []
        campus_code_prefix = (target_campus.code or target_campus.name[:3]).upper().strip()

        with transaction.atomic():
            for adm in to_transfer:
                student = adm.student
                old_campus = adm.campus
                old_adm_no = student.admission_number
                new_adm_no = old_adm_no

                if conflicts and any(c['student_id'] == student.id for c in conflicts):
                    if conflict_resolution == 'prefix_campus':
                        new_adm_no = f"{campus_code_prefix}-{old_adm_no}"

                student.campus = target_campus
                update_fields_s = ['campus']
                if new_adm_no != old_adm_no:
                    student.admission_number = new_adm_no
                    update_fields_s.append('admission_number')
                student.save(update_fields=update_fields_s)

                adm.campus = target_campus
                update_fields_a = ['campus']
                if new_adm_no != old_adm_no:
                    adm.admission_number = new_adm_no
                    update_fields_a.append('admission_number')
                adm.save(update_fields=update_fields_a)

                if hasattr(adm, 'application') and adm.application:
                    app = adm.application
                    app.campus = target_campus
                    app.save(update_fields=['campus'])

                active_enr = student.enrollments.filter(status='active', is_active=True).last()
                prev_class_desc = ""
                new_class_desc = ""
                if active_enr:
                    prev_class_desc = f"{active_enr.grade.name if active_enr.grade else ''} {active_enr.stream.name if active_enr.stream else ''}".strip()
                    active_enr.campus = target_campus
                    enr_fields = ['campus']
                    if target_grade_id:
                        active_enr.grade_id = target_grade_id
                        enr_fields.append('grade')
                    if target_stream_id is not None:
                        active_enr.stream_id = target_stream_id if target_stream_id > 0 else None
                        enr_fields.append('stream')
                    active_enr.save(update_fields=enr_fields)
                    new_class_desc = f"{active_enr.grade.name if active_enr.grade else ''} {active_enr.stream.name if active_enr.stream else ''}".strip()

                try:
                    from student_management.models.transfer import StudentCampusTransfer
                    StudentCampusTransfer.objects.create(
                        student=student,
                        admission=adm,
                        source_campus=old_campus,
                        target_campus=target_campus,
                        admission_number=new_adm_no,
                        previous_class=prev_class_desc,
                        new_class=new_class_desc,
                        reason=reason,
                        notes=notes,
                        transferred_by=request.user
                    )
                except Exception as log_err:
                    pass

                migrated_results.append({
                    'admission_id': adm.id,
                    'student_id': student.id,
                    'name': _get_student_display_name(student),
                    'admission_number': new_adm_no,
                    'previous_campus': old_campus.name if old_campus else 'Unassigned',
                    'new_campus': target_campus.name
                })

        return Response({
            'success': True,
            'message': f'Successfully migrated {len(migrated_results)} student(s) to {target_campus.name}.' + (f' Note: {len(already_on_campus)} student(s) were already enrolled at {target_campus.name}.' if already_on_campus else ''),
            'target_campus': {'id': target_campus.id, 'name': target_campus.name, 'code': target_campus.code},
            'migrated_count': len(migrated_results),
            'already_assigned_count': len(already_on_campus),
            'results': migrated_results
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='campus_transfers_history')
    def campus_transfers_history(self, request):
        try:
            from student_management.models.transfer import StudentCampusTransfer
            from student_management.serializers.transfer import StudentCampusTransferSerializer
            qs = StudentCampusTransfer.objects.select_related(
                'student', 'student__student', 'source_campus', 'target_campus', 'transferred_by'
            ).all()[:100]
            serializer = StudentCampusTransferSerializer(qs, many=True)
            return Response(serializer.data)
        except Exception as e:
            return Response([], status=status.HTTP_200_OK)

