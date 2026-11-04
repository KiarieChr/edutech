from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from core.models import InstitutionProfile


def get_default_page_config():
    return {
        "size": "A4",
        "orientation": "portrait",
        "margin_top": "24mm",
        "margin_bottom": "20mm",
        "margin_left": "15mm",
        "margin_right": "15mm",
    }


def get_default_header_config():
    return {
        "mode": "institutional",  # 'institutional' (shared branding), 'custom', or 'none'
        "show_header": True,
        "height": "32mm",
        "columns": {
            "left": {
                "width": "25%",
                "alignment": "left",
                "elements": [
                    {
                        "id": "h-logo",
                        "type": "logo",
                        "logo_type": "primary",
                        "width": 80,
                        "max_height": 70,
                    }
                ],
            },
            "center": {
                "width": "50%",
                "alignment": "center",
                "elements": [
                    {
                        "id": "h-name",
                        "type": "text",
                        "content": "{{institution.name}}",
                        "font_size": 18,
                        "font_weight": "bold",
                        "color": "{{brand.primary}}",
                    },
                    {
                        "id": "h-motto",
                        "type": "text",
                        "content": "{{institution.motto}}",
                        "font_size": 11,
                        "font_style": "italic",
                        "color": "{{brand.secondary}}",
                    },
                    {
                        "id": "h-address",
                        "type": "text",
                        "content": "{{institution.address}} | Tel: {{institution.phone}}",
                        "font_size": 9,
                        "color": "{{brand.text}}",
                    },
                ],
            },
            "right": {
                "width": "25%",
                "alignment": "right",
                "elements": [
                    {
                        "id": "h-email",
                        "type": "text",
                        "content": "{{institution.email}}",
                        "font_size": 9,
                        "color": "{{brand.text}}",
                    },
                    {
                        "id": "h-web",
                        "type": "text",
                        "content": "{{institution.website}}",
                        "font_size": 9,
                        "color": "{{brand.primary}}",
                    },
                ],
            },
        },
        "divider": {
            "enabled": True,
            "color": "{{brand.accent}}",
            "width": 2,
            "style": "solid",
            "margin_top": 8,
        },
    }


def get_default_footer_config():
    return {
        "show_footer": True,
        "height": "16mm",
        "columns": {
            "left": {
                "width": "35%",
                "alignment": "left",
                "elements": [
                    {
                        "id": "f-inst",
                        "type": "text",
                        "content": "Official Document — {{institution.name}}",
                        "font_size": 8,
                        "color": "#64748b",
                    }
                ],
            },
            "center": {
                "width": "30%",
                "alignment": "center",
                "elements": [
                    {
                        "id": "f-motto",
                        "type": "text",
                        "content": "{{institution.motto}}",
                        "font_size": 8,
                        "font_style": "italic",
                        "color": "#94a3b8",
                    }
                ],
            },
            "right": {
                "width": "35%",
                "alignment": "right",
                "elements": [
                    {
                        "id": "f-page",
                        "type": "pagination",
                        "format": "Page {{page}} of {{pages}}",
                        "font_size": 8,
                        "font_weight": "bold",
                        "color": "{{brand.primary}}",
                    }
                ],
            },
        },
        "divider": {
            "enabled": True,
            "color": "#e2e8f0",
            "width": 1,
            "style": "solid",
            "margin_bottom": 6,
        },
    }


def get_default_watermark_config():
    return {
        "enabled": True,
        "type": "image",  # 'image' or 'text'
        "logo_type": "primary",  # 'primary' or 'secondary'
        "text_content": "OFFICIAL",
        "opacity": 0.06,
        "scale": 0.55,
        "rotation": -30,
    }


def get_default_table_config():
    return {
        "header_bg": "{{brand.primary}}",
        "header_text": "#ffffff",
        "header_font_size": 8.5,
        "header_font_weight": "bold",
        "body_text": "#1e293b",
        "body_font_size": 8.5,
        "alt_row_bg": "#f8fafc",
        "border_color": "#cbd5e1",
        "border_width": "0.5pt",
        "cell_padding": "6px 10px",
        "text_align": "left",
        "repeat_header": True,
    }


class DocumentTemplate(models.Model):
    """
    Tenant-scoped Document Template managing document header, footer, watermark,
    and page geometries for institutional exports and reporting.
    """

    class Category(models.TextChoices):
        GENERAL = "general", _("General Document")
        STUDENT_REPORT = "student_report", _("Student Academic Report")
        INVOICE = "invoice", _("Fee Invoice / Bill")
        RECEIPT = "receipt", _("Official Receipt")
        LETTER = "letter", _("Official Letterhead")
        CERTIFICATE = "certificate", _("Certificate / Award")
        TRANSCRIPT = "transcript", _("Official Transcript")
        TIMETABLE = "timetable", _("Class / Exam Timetable")
        PAYSLIP = "payslip", _("Employee Payslip")
        EMPLOYMENT_CONTRACT = "employment_contract", _("Employment Contract")
        P9_FORM = "p9_form", _("Tax Deduction Card (P9 Form)")

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PUBLISHED = "published", _("Published")

    institution = models.ForeignKey(
        InstitutionProfile,
        on_delete=models.CASCADE,
        related_name="document_templates",
        null=True,
        blank=True,
        help_text=_("Institution profile associated with this template."),
    )
    name = models.CharField(max_length=255, verbose_name=_("Template Name"))
    category = models.CharField(
        max_length=50,
        choices=Category.choices,
        default=Category.GENERAL,
        verbose_name=_("Document Category"),
    )
    description = models.TextField(blank=True, default="", verbose_name=_("Description"))
    header_config = models.JSONField(
        default=get_default_header_config, verbose_name=_("Header Configuration")
    )
    footer_config = models.JSONField(
        default=get_default_footer_config, verbose_name=_("Footer Configuration")
    )
    watermark_config = models.JSONField(
        default=get_default_watermark_config, verbose_name=_("Watermark Configuration")
    )
    page_config = models.JSONField(
        default=get_default_page_config, verbose_name=_("Page Configuration")
    )
    table_config = models.JSONField(
        default=get_default_table_config, verbose_name=_("Table Configuration")
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name=_("Status"),
    )
    is_default = models.BooleanField(
        default=False,
        verbose_name=_("Is Default for Category"),
        help_text=_("When true, this template is automatically applied to documents in this category."),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_document_templates",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_document_templates",
    )

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = _("Document Template")
        verbose_name_plural = _("Document Templates")

    def __str__(self):
        return f"{self.name} ({self.get_category_display()}) - {self.status.capitalize()}"

    def save(self, *args, **kwargs):
        # Auto-link to active tenant's InstitutionProfile if omitted
        if not self.institution_id:
            profile = InstitutionProfile.get_instance()
            self.institution = profile

        # Ensure single default per category within tenant schema
        if self.is_default:
            DocumentTemplate.objects.filter(
                category=self.category, is_default=True
            ).exclude(pk=self.pk).update(is_default=False)

        super().save(*args, **kwargs)

    def create_version_snapshot(self, published_by=None):
        """
        Creates an immutable historical version snapshot of the current configuration.
        """
        latest_version = self.versions.order_by("-version_number").first()
        new_version_number = (latest_version.version_number + 1) if latest_version else 1

        snapshot = {
            "name": self.name,
            "category": self.category,
            "header_config": self.header_config,
            "footer_config": self.footer_config,
            "watermark_config": self.watermark_config,
            "page_config": self.page_config,
            "table_config": self.table_config,
        }

        version = DocumentTemplateVersion.objects.create(
            template=self,
            version_number=new_version_number,
            snapshot=snapshot,
            published_by=published_by,
        )

        self.status = DocumentTemplate.Status.PUBLISHED
        self.save(update_fields=["status", "updated_at"])
        return version


class DocumentTemplateVersion(models.Model):
    """
    Immutable version snapshot of a published DocumentTemplate for rollbacks,
    auditing, and consistent historical document rendering.
    """

    template = models.ForeignKey(
        DocumentTemplate, on_delete=models.CASCADE, related_name="versions"
    )
    version_number = models.IntegerField(verbose_name=_("Version Number"))
    snapshot = models.JSONField(verbose_name=_("Configuration Snapshot"))
    published_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Published At"))
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="published_template_versions",
    )

    class Meta:
        ordering = ["-version_number"]
        unique_together = ("template", "version_number")
        verbose_name = _("Document Template Version")
        verbose_name_plural = _("Document Template Versions")

    def __str__(self):
        return f"{self.template.name} v{self.version_number} ({self.published_at:%Y-%m-%d %H:%M})"
