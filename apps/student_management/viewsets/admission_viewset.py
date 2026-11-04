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
