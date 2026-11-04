from django.http import HttpResponse
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from core.permissions import TenantAccessPermission, CanManageBrandingPermission
from core.models import InstitutionProfile
from .models import DocumentTemplate, DocumentTemplateVersion
from .serializers import DocumentTemplateSerializer, DocumentTemplateVersionSerializer
from .rendering.pdf import render_pdf_bytes, generate_document_html, get_default_context


class DocumentTemplateViewSet(viewsets.ModelViewSet):
    """
    Tenant-scoped CRUD ViewSet for institutional Document Templates.
    Enforces server-side tenant isolation and permissions.
    """
    queryset = DocumentTemplate.objects.all()
    serializer_class = DocumentTemplateSerializer
    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [IsAuthenticated(), TenantAccessPermission()]
        return [IsAuthenticated(), TenantAccessPermission(), CanManageBrandingPermission()]

    def get_queryset(self):
        # Guaranteed to execute inside the current tenant schema
        qs = DocumentTemplate.objects.all().order_by("-updated_at")
        category = self.request.query_params.get("category")
        status_param = self.request.query_params.get("status")
        if category:
            qs = qs.filter(category=category)
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    def perform_create(self, serializer):
        profile = InstitutionProfile.get_instance()
        serializer.save(
            institution=profile,
            created_by=self.request.user,
            updated_by=self.request.user,
        )

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        """
        Publishes the template, creating an immutable version snapshot.
        """
        template = self.get_object()
        version = template.create_version_snapshot(published_by=request.user)
        return Response(
            {
                "success": True,
                "message": f"Template '{template.name}' published as version {version.version_number}.",
                "version": DocumentTemplateVersionSerializer(version).data,
                "template": DocumentTemplateSerializer(template).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"])
    def versions(self, request, pk=None):
        """
        List all version snapshots for this template.
        """
        template = self.get_object()
        versions = template.versions.all().order_by("-version_number")
        serializer = DocumentTemplateVersionSerializer(versions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path=r"rollback/(?P<version_number>\d+)")
    def rollback(self, request, pk=None, version_number=None):
        """
        Restores a historical version snapshot into the active template configuration.
        """
        template = self.get_object()
        version = template.versions.filter(version_number=version_number).first()
        if not version:
            return Response(
                {"error": f"Version {version_number} does not exist for this template."},
                status=status.HTTP_404_NOT_FOUND,
            )

        snap = version.snapshot
        template.name = snap.get("name", template.name)
        template.category = snap.get("category", template.category)
        template.header_config = snap.get("header_config", template.header_config)
        template.footer_config = snap.get("footer_config", template.footer_config)
        template.watermark_config = snap.get("watermark_config", template.watermark_config)
        template.page_config = snap.get("page_config", template.page_config)
        template.updated_by = request.user
        template.save()

        return Response(
            {
                "success": True,
                "message": f"Template restored to snapshot from version {version_number}.",
                "template": DocumentTemplateSerializer(template).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get", "post"], url_path="preview-pdf")
    def preview_pdf(self, request, pk=None):
        """
        Generates and streams a binary PDF preview using WeasyPrint.
        Accepts optional POST payload to preview unsaved editor changes.
        """
        template = self.get_object()

        # If POST provided with draft configs, overlay them onto the template instance in memory
        if request.method == "POST" and request.data:
            if "header_config" in request.data:
                template.header_config = request.data["header_config"]
            if "footer_config" in request.data:
                template.footer_config = request.data["footer_config"]
            if "watermark_config" in request.data:
                template.watermark_config = request.data["watermark_config"]
            if "page_config" in request.data:
                template.page_config = request.data["page_config"]

        context = get_default_context()
        html_body = request.data.get("html_body") if request.method == "POST" else None

        try:
            pdf_bytes = render_pdf_bytes(template, context=context, html_body=html_body)
            filename = f"{template.name.replace(' ', '_').lower()}_preview.pdf"
            response = HttpResponse(pdf_bytes, content_type="application/pdf")
            response["Content-Disposition"] = f'inline; filename="{filename}"'
            return response
        except Exception as e:
            return Response(
                {"error": f"PDF Rendering failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["post"], url_path="preview-live")
    def preview_live(self, request):
        """
        Generates and streams a binary PDF directly from transient editor state.
        Allows instant PDF preview before saving the template to the database.
        """
        data = request.data
        transient_template = DocumentTemplate(
            name=data.get("name", "Document Live Preview"),
            header_config=data.get("header_config") or {},
            footer_config=data.get("footer_config") or {},
            watermark_config=data.get("watermark_config") or {},
            page_config=data.get("page_config") or {},
        )

        context = get_default_context()
        html_body = data.get("html_body")

        try:
            pdf_bytes = render_pdf_bytes(transient_template, context=context, html_body=html_body)
            response = HttpResponse(pdf_bytes, content_type="application/pdf")
            response["Content-Disposition"] = 'inline; filename="live_preview.pdf"'
            return response
        except Exception as e:
            return Response(
                {"error": f"Live PDF Rendering failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@api_view(["GET"])
@permission_classes([IsAuthenticated, TenantAccessPermission])
def document_branding_context(request):
    """
    Returns the resolved Phase 1 institutional branding context and fallbacks
    for consumption by the frontend Document Design Studio.
    """
    context = get_default_context()
    return Response(context, status=status.HTTP_200_OK)
