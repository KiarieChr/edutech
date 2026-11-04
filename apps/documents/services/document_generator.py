"""
Document Generator Service.
Coordinates:
  Application Data Provider -> Template Resolution -> Context Merging -> WeasyPrint PDF Renderer
Produces professional, institution-branded binary PDFs or HTML previews.
"""
from typing import Optional, Dict, Any, Tuple
from core.models import InstitutionProfile
from documents.models import DocumentTemplate, DocumentTemplateVersion
from documents.rendering.pdf import render_pdf_bytes, generate_document_html, get_default_context
from .base_provider import BaseDocumentDataProvider
from .template_resolver import DocumentTemplateResolver, TemplateResolutionError


class DocumentGeneratorService:
    """
    Central orchestration service for generating print-grade documents
    from operational data across any Fahari Academia module.
    """

    @classmethod
    def resolve_effective_template(
        cls,
        provider: BaseDocumentDataProvider,
        template_id: Optional[int] = None,
        version_number: Optional[int] = None,
        allow_draft: bool = False,
    ) -> Tuple[DocumentTemplate, Optional[DocumentTemplateVersion]]:
        """
        Resolves the appropriate template or version snapshot for the provider.
        """
        return DocumentTemplateResolver.resolve_template(
            category=provider.get_category(),
            template_id=template_id,
            version_number=version_number,
            allow_draft=allow_draft,
        )

    @classmethod
    def build_composite_context(
        cls,
        provider: BaseDocumentDataProvider,
        institution_profile: Optional[InstitutionProfile] = None,
        context_overrides: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Builds the complete multi-layer rendering context:
          Layer 1: Base Institutional Profile (name, logos, brand palette, contact)
          Layer 2: Operational Data Provider Context (student info, admission dates, amounts)
          Layer 3: Caller overrides (optional metadata, references)
        """
        base_context = get_default_context(institution_profile)
        provider_data = provider.get_context_data()

        # Merge provider data into context under its document domain
        composite = {**base_context}
        composite.update(provider_data)

        # Ensure document title and document reference exist at root
        composite["document_title"] = provider.get_document_title()
        if "document_ref" in provider_data:
            composite["document_ref"] = provider_data["document_ref"]

        if context_overrides:
            composite.update(context_overrides)

        return composite

    @classmethod
    def generate_pdf(
        cls,
        provider: BaseDocumentDataProvider,
        template_id: Optional[int] = None,
        version_number: Optional[int] = None,
        context_overrides: Optional[Dict[str, Any]] = None,
        allow_draft: bool = False,
    ) -> bytes:
        """
        Renders and returns genuine binary PDF bytes using WeasyPrint.
        """
        template, version = cls.resolve_effective_template(
            provider, template_id=template_id, version_number=version_number, allow_draft=allow_draft
        )

        # If a version snapshot exists, apply snapshot configurations
        effective_template = template
        if version and version.snapshot:
            snap = version.snapshot
            effective_template = DocumentTemplate(
                id=template.id,
                name=snap.get("name", template.name),
                category=snap.get("category", template.category),
                header_config=snap.get("header_config", template.header_config),
                footer_config=snap.get("footer_config", template.footer_config),
                watermark_config=snap.get("watermark_config", template.watermark_config),
                page_config=snap.get("page_config", template.page_config),
                table_config=snap.get("table_config", getattr(template, "table_config", None)),
            )

        context = cls.build_composite_context(provider, context_overrides=context_overrides)
        body_html = provider.render_body_html(context)

        return render_pdf_bytes(effective_template, context=context, html_body=body_html)

    @classmethod
    def generate_preview_html(
        cls,
        provider: BaseDocumentDataProvider,
        template_id: Optional[int] = None,
        version_number: Optional[int] = None,
        context_overrides: Optional[Dict[str, Any]] = None,
        allow_draft: bool = False,
    ) -> Dict[str, Any]:
        """
        Generates HTML preview representation and metadata for client modals.
        """
        template, version = cls.resolve_effective_template(
            provider, template_id=template_id, version_number=version_number, allow_draft=allow_draft
        )

        effective_template = template
        if version and version.snapshot:
            snap = version.snapshot
            effective_template = DocumentTemplate(
                id=template.id,
                name=snap.get("name", template.name),
                category=snap.get("category", template.category),
                header_config=snap.get("header_config", template.header_config),
                footer_config=snap.get("footer_config", template.footer_config),
                watermark_config=snap.get("watermark_config", template.watermark_config),
                page_config=snap.get("page_config", template.page_config),
                table_config=snap.get("table_config", getattr(template, "table_config", None)),
            )

        context = cls.build_composite_context(provider, context_overrides=context_overrides)
        body_html = provider.render_body_html(context)
        document_html = generate_document_html(effective_template, context=context, html_body=body_html)

        return {
            "html": document_html,
            "template_id": template.id,
            "template_name": template.name,
            "template_category": template.category,
            "version_number": version.version_number if version else None,
            "document_title": provider.get_document_title(),
            "context_summary": {
                "student_name": context.get("student", {}).get("full_name"),
                "admission_number": context.get("admission", {}).get("admission_number"),
                "document_ref": context.get("document_ref"),
            },
        }
