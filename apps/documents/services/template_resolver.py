"""
Document Template Resolver.
Responsible for resolving published templates or immutable version snapshots
for a given document category or explicit template ID, strictly scoped to the active tenant.
"""
from typing import Optional, List, Tuple
from django.core.exceptions import ObjectDoesNotExist
from documents.models import DocumentTemplate, DocumentTemplateVersion


class TemplateResolutionError(Exception):
    """Raised when a suitable document template cannot be resolved."""
    pass


class DocumentTemplateResolver:
    """
    Tenant-scoped resolver that finds published templates, evaluates category defaults,
    and resolves immutable historical snapshots for document generation.
    """

    @classmethod
    def resolve_template(
        cls,
        category: str,
        template_id: Optional[int] = None,
        version_number: Optional[int] = None,
        allow_draft: bool = False,
    ) -> Tuple[DocumentTemplate, Optional[DocumentTemplateVersion]]:
        """
        Resolves the DocumentTemplate and optional DocumentTemplateVersion.

        Returns:
            Tuple of (template_instance, version_snapshot_or_none)
        Raises:
            TemplateResolutionError: If no suitable published template is available.
        """
        # 1. Explicit template ID requested
        if template_id:
            try:
                template = DocumentTemplate.objects.get(pk=template_id)
            except DocumentTemplate.DoesNotExist:
                raise TemplateResolutionError(
                    f"Document template with ID {template_id} does not exist for the active institution."
                )

            # Check status
            if template.status != DocumentTemplate.Status.PUBLISHED and not allow_draft:
                raise TemplateResolutionError(
                    f"Template '{template.name}' is currently in draft mode. "
                    "Only published templates can be used for official document generation."
                )

            # If specific version requested
            version = None
            if version_number:
                version = template.versions.filter(version_number=version_number).first()
                if not version:
                    raise TemplateResolutionError(
                        f"Version {version_number} of template '{template.name}' was not found."
                    )
            else:
                # Latest published version snapshot if available
                version = template.versions.order_by("-version_number").first()

            return template, version

        # 2. Category resolution: Look for default published template in this category
        published_qs = DocumentTemplate.objects.filter(
            category=category,
            status=DocumentTemplate.Status.PUBLISHED,
        )

        template = published_qs.filter(is_default=True).first()
        if not template:
            # Fall back to any published template in this category
            template = published_qs.order_by("-updated_at").first()

        # 3. Fallback to General category published template if none in category
        if not template and category != DocumentTemplate.Category.GENERAL:
            template = DocumentTemplate.objects.filter(
                category=DocumentTemplate.Category.GENERAL,
                status=DocumentTemplate.Status.PUBLISHED,
                is_default=True,
            ).first() or DocumentTemplate.objects.filter(
                category=DocumentTemplate.Category.GENERAL,
                status=DocumentTemplate.Status.PUBLISHED,
            ).order_by("-updated_at").first()

        # 4. If no published template exists at all
        if not template:
            raise TemplateResolutionError(
                f"No published document template found for category '{category}'. "
                "Please publish a document template in the Document Design Studio before generating official documents."
            )

        latest_version = template.versions.order_by("-version_number").first()
        return template, latest_version

    @classmethod
    def get_available_templates(cls, category: Optional[str] = None) -> List[DocumentTemplate]:
        """
        Returns list of published templates available for user selection.
        If category is provided, includes category templates and general templates.
        """
        qs = DocumentTemplate.objects.filter(status=DocumentTemplate.Status.PUBLISHED)
        if category:
            qs = qs.filter(category__in=[category, DocumentTemplate.Category.GENERAL])
        return list(qs.order_by("-is_default", "name"))
