"""
Comprehensive Test Suite for Phase 3: Document Integration & Export Engine.
Tests:
- Institutional Header Resolution (institutional, custom, none)
- Document Template Resolver (by id, by category, defaults, fallbacks, errors)
- AdmissionLetterDataProvider (validation, field handling, context extraction)
- DocumentGeneratorService (binary PDF rendering, preview HTML generation)
- Multi-Tenant Isolation & Security across schemas
- AdmissionViewSet document endpoints (/generate_document, /available_templates)
"""
from datetime import date, datetime
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import BaseTenantRequestFactory
from django_tenants.utils import schema_context, get_public_schema_name
from rest_framework import status
from rest_framework.test import APIClient

from core.models import InstitutionProfile
from tenants.models import Client, Domain
from documents.models import DocumentTemplate, DocumentTemplateVersion
from documents.services import (
    DocumentGeneratorService,
    DocumentTemplateResolver,
    TemplateResolutionError,
)
from student_management.models import Admission, Student, Application
from student_management.documents import AdmissionLetterDataProvider
from student_settings.models import Intake, GradeStructure, Curriculum

User = get_user_model()


class TenantAPIClient(BaseTenantRequestFactory, APIClient):
    def generic(self, *args, **kwargs):
        if "HTTP_HOST" not in kwargs:
            try:
                domain_obj = self.tenant.domains.filter(is_primary=True).first() or self.tenant.domains.first()
                kwargs["HTTP_HOST"] = domain_obj.domain if domain_obj else f"{self.tenant.schema_name}.localhost"
            except Exception:
                kwargs["HTTP_HOST"] = f"{self.tenant.schema_name}.localhost"
        request = super().generic(*args, **kwargs)
        request.tenant = self.tenant
        return request


class DocumentIntegrationPhase3Tests(FastTenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = "Integration Test School"
        tenant.save()

    @classmethod
    def setup_domain(cls, domain):
        domain.is_primary = True

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        self.client = TenantAPIClient(self.tenant)

        # Admin User
        self.admin_user, _ = User.objects.get_or_create(
            username="admin_p3",
            defaults={"email": "admin@school.ac.ke", "is_staff": True, "is_superuser": False},
        )
        self.admin_user.set_password("Password123!")
        self.admin_user.save()
        self.admin_user.tenants.add(self.tenant)

        # Non-staff User
        self.student_user, _ = User.objects.get_or_create(
            username="student_p3",
            defaults={"email": "student@school.ac.ke", "is_staff": False, "is_superuser": False},
        )
        self.student_user.set_password("Password123!")
        self.student_user.save()
        self.student_user.tenants.add(self.tenant)

        # Institutional Profile
        self.profile = InstitutionProfile.get_instance()
        self.profile.name = "Alliance Pioneers Academy"
        self.profile.display_name = "Alliance Pioneers"
        self.profile.motto = "Strive for Excellence and Honor"
        self.profile.primary_color = "#17365D"
        self.profile.secondary_color = "#1F6B4F"
        self.profile.accent_color = "#D4A72C"
        self.profile.principal_name = "Dr. Arthur Kimani"
        self.profile.principal_title = "CHIEF PRINCIPAL"
        self.profile.save()

        # Published Letter Template
        self.template = DocumentTemplate.objects.create(
            name="Official Letterhead Template",
            category=DocumentTemplate.Category.LETTER,
            status=DocumentTemplate.Status.PUBLISHED,
            is_default=True,
            header_config={
                "mode": "institutional",
                "show_header": True,
                "columns": {},
                "divider": {"enabled": True, "color": "#D4A72C", "width": 2},
            },
            footer_config={
                "show_footer": True,
                "divider": {"enabled": True, "color": "#e2e8f0", "width": 1},
            },
            watermark_config={
                "enabled": True,
                "type": "text",
                "text_content": "OFFICIAL",
                "opacity": 0.05,
            },
            institution=self.profile,
            created_by=self.admin_user,
        )
        self.template.create_version_snapshot(published_by=self.admin_user)

        # Operational Academic Records for Student Management
        from student_settings.models import AcademicYear
        self.academic_year = AcademicYear.objects.create(
            name="2026 Academic Year",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            is_current=True,
        )
        self.curriculum = Curriculum.objects.create(name="Competency Based Curriculum")
        self.grade = GradeStructure.objects.create(name="Grade 7", curriculum=self.curriculum, level_order=1)
        self.intake = Intake.objects.create(
            name="January 2026 Cohort",
            code="INT2026JAN",
            academic_year=self.academic_year,
            start_date=date(2026, 1, 12),
        )

        self.student_auth_user = User.objects.create(
            username="brian_otieno",
            first_name="Brian",
            last_name="Otieno",
            email="brian@student.ac.ke",
            gender="M",
        )
        self.student_auth_user.tenants.add(self.tenant)

        self.student = Student.objects.create(
            student=self.student_auth_user,
            admission_number="ADM-2026-0042",
            date_of_birth=date(2012, 5, 14),
            nationality="Kenyan",
            status="active",
        )

        self.application = Application.objects.create(
            first_name="Brian",
            middle_name="Juma",
            last_name="Otieno",
            date_of_birth=date(2012, 5, 14),
            gender="M",
            nationality="Kenyan",
            intake=self.intake,
            applying_for_curriculum=self.curriculum,
            applying_for_grade=self.grade,
            guardian_name="Grace Akinyi Otieno",
            guardian_relationship="mother",
            phone_number="+254 712 345 678",
            email="grace.otieno@gmail.com",
            guardian_address="P.O. Box 45000 - 00100 Nairobi",
            application_status="admitted",
        )

        self.admission = Admission.objects.create(
            application=self.application,
            student=self.student,
            admission_number="ADM-2026-0042",
            admission_date=date(2026, 1, 15),
            admitted_by=self.admin_user,
        )

    # ── 1. Header Resolution Tests ──────────────────────────────────────────

    def test_header_mode_institutional_dynamic_inheritance(self):
        """Institutional header dynamically inherits active profile values without altering template."""
        provider = AdmissionLetterDataProvider(self.admission)
        preview = DocumentGeneratorService.generate_preview_html(provider, template_id=self.template.id)
        
        # Verify initial institutional name appears in rendered HTML
        self.assertIn("Alliance Pioneers", preview["html"])

        # Dynamically change institution profile name
        self.profile.display_name = "Alliance Royal Academy"
        self.profile.save()

        # Re-render without touching the template: dynamic inheritance applies
        preview_updated = DocumentGeneratorService.generate_preview_html(provider, template_id=self.template.id)
        self.assertIn("Alliance Royal Academy", preview_updated["html"])

    def test_header_mode_none_suppresses_headers(self):
        """Header mode 'none' completely omits masthead and continuation headers."""
        tpl_none = DocumentTemplate.objects.create(
            name="No Header Template",
            category=DocumentTemplate.Category.LETTER,
            status=DocumentTemplate.Status.PUBLISHED,
            header_config={"mode": "none", "show_header": False},
            institution=self.profile,
            created_by=self.admin_user,
        )
        provider = AdmissionLetterDataProvider(self.admission)
        preview = DocumentGeneratorService.generate_preview_html(provider, template_id=tpl_none.id)
        self.assertNotIn("document-masthead", preview["html"])
        self.assertNotIn("running-continuation-header", preview["html"])

    def test_header_mode_custom_preserves_custom_columns(self):
        """Header mode 'custom' renders user-defined columns with institutional fallback."""
        tpl_custom = DocumentTemplate.objects.create(
            name="Custom Header Template",
            category=DocumentTemplate.Category.LETTER,
            status=DocumentTemplate.Status.PUBLISHED,
            header_config={
                "mode": "custom",
                "show_header": True,
                "columns": {
                    "left": {
                        "width": "100%",
                        "alignment": "center",
                        "elements": [
                            {"type": "text", "content": "SPECIAL ADMISSIONS OFFICE", "font_size": 16, "font_weight": "bold"}
                        ],
                    }
                },
            },
            institution=self.profile,
            created_by=self.admin_user,
        )
        provider = AdmissionLetterDataProvider(self.admission)
        preview = DocumentGeneratorService.generate_preview_html(provider, template_id=tpl_custom.id)
        self.assertIn("SPECIAL ADMISSIONS OFFICE", preview["html"])

    # ── 2. Template Resolution Tests ────────────────────────────────────────

    def test_template_resolver_by_category_default(self):
        """Resolver selects default published template for the category."""
        tpl, version = DocumentTemplateResolver.resolve_template(category=DocumentTemplate.Category.LETTER)
        self.assertEqual(tpl.id, self.template.id)
        self.assertIsNotNone(version)

    def test_template_resolver_raises_error_when_no_published_template(self):
        """Resolver raises clean TemplateResolutionError when category has no published template."""
        with self.assertRaises(TemplateResolutionError):
            DocumentTemplateResolver.resolve_template(category=DocumentTemplate.Category.TRANSCRIPT)

    def test_template_resolver_available_templates(self):
        """Resolver returns list of published templates matching category."""
        templates = DocumentTemplateResolver.get_available_templates(category=DocumentTemplate.Category.LETTER)
        self.assertTrue(len(templates) >= 1)
        self.assertIn(self.template.id, [t.id for t in templates])

    # ── 3. Data Provider Validation & Handling ──────────────────────────────

    def test_admission_data_provider_context_extraction(self):
        """Data provider extracts and normalizes all student, admission, and guardian fields."""
        provider = AdmissionLetterDataProvider(self.admission)
        ctx = provider.get_context_data()

        self.assertEqual(ctx["document_ref"], "ADM/2026/ADM-2026-0042")
        self.assertEqual(ctx["student"]["full_name"], "Brian Juma Otieno")
        self.assertEqual(ctx["admission"]["admission_number"], "ADM-2026-0042")
        self.assertEqual(ctx["admission"]["grade"], "Grade 7")
        self.assertEqual(ctx["guardian"]["name"], "Grace Akinyi Otieno")
        self.assertEqual(ctx["guardian"]["relationship"], "Mother")
        self.assertEqual(ctx["signatory"]["name"], "Dr. Arthur Kimani")
        self.assertEqual(ctx["signatory"]["title"], "CHIEF PRINCIPAL")

    def test_admission_data_provider_missing_admission_number_raises_error(self):
        """Data provider rejects records without an allocated admission number."""
        self.admission.admission_number = ""
        self.admission.save()
        self.student.admission_number = ""
        self.student.save()

        with self.assertRaises(ValidationError):
            AdmissionLetterDataProvider(self.admission)

    # ── 4. WeasyPrint PDF Generation Tests ──────────────────────────────────

    def test_generate_admission_letter_pdf_stream(self):
        """Service generates genuine binary PDF bytes for the admission letter."""
        provider = AdmissionLetterDataProvider(self.admission)
        pdf_bytes = DocumentGeneratorService.generate_pdf(provider, template_id=self.template.id)

        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(pdf_bytes.startswith(b"%PDF-1."))
        self.assertTrue(len(pdf_bytes) > 5000)

    # ── 5. API Endpoints on AdmissionViewSet ────────────────────────────────

    def test_api_generate_document_preview(self):
        """GET /api/student-management/admissions/{id}/generate_document/?preview=true returns preview JSON."""
        self.client.force_authenticate(user=self.admin_user)
        res = self.client.get(
            f"/api/student-management/admissions/{self.admission.id}/generate_document/",
            {"preview": "true", "template_id": self.template.id},
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("html", res.data)
        self.assertEqual(res.data["template_id"], self.template.id)
        self.assertIn("Brian Juma Otieno", res.data["html"])
        self.assertIn("ADM-2026-0042", res.data["html"])

    def test_api_generate_document_pdf_stream(self):
        """GET /api/student-management/admissions/{id}/generate_document/ streams application/pdf."""
        self.client.force_authenticate(user=self.admin_user)
        res = self.client.get(
            f"/api/student-management/admissions/{self.admission.id}/generate_document/",
            {"template_id": self.template.id},
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res["Content-Type"], "application/pdf")
        self.assertTrue(res.content.startswith(b"%PDF-1."))
        self.assertIn("admission_letter_ADM-2026-0042.pdf", res["Content-Disposition"])

    def test_api_available_templates(self):
        """GET /api/student-management/admissions/{id}/available_templates/ lists published templates."""
        self.client.force_authenticate(user=self.admin_user)
        res = self.client.get(f"/api/student-management/admissions/{self.admission.id}/available_templates/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(len(res.data) >= 1)
        self.assertEqual(res.data[0]["id"], self.template.id)

    # ── 6. Multi-Tenant Isolation & Security Tests ──────────────────────────

    def test_cross_tenant_document_generation_blocked(self):
        """User belonging strictly to another tenant is rejected by TenantAccessPermission with 403."""
        foreign_user = User.objects.create(
            username="rival_admin",
            email="rival@other.ac.ke",
            is_staff=True,
            is_superuser=False,
        )
        # foreign_user does NOT belong to self.tenant
        self.client.force_authenticate(user=foreign_user)
        res = self.client.get(
            f"/api/student-management/admissions/{self.admission.id}/generate_document/"
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_request_rejected(self):
        """Unauthenticated requests are strictly rejected with 401."""
        unauthed_client = TenantAPIClient(self.tenant)
        res = unauthed_client.get(
            f"/api/student-management/admissions/{self.admission.id}/generate_document/"
        )
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

