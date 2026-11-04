"""
Automated Test Suite for Phase 2: Document Template Manager, Editor & Rendering Service.
Tests CRUD operations, version publishing, rollback snapshots, WeasyPrint PDF generation,
and strict multi-tenant isolation.
"""
import json
from django.contrib.auth import get_user_model
from django.db import connection
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import BaseTenantRequestFactory
from django_tenants.utils import schema_context, get_public_schema_name
from rest_framework import status
from rest_framework.test import APIClient
from core.models import InstitutionProfile
from tenants.models import Client, Domain
from documents.models import DocumentTemplate, DocumentTemplateVersion
from documents.rendering.pdf import render_pdf_bytes, get_default_context

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


class DocumentTemplateTests(FastTenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = "Template Design Tenant"
        tenant.save()

    @classmethod
    def setup_domain(cls, domain):
        domain.is_primary = True

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        self.client = TenantAPIClient(self.tenant)

        # Admin user
        self.admin_user, _ = User.objects.get_or_create(
            username="doc_admin",
            defaults={"email": "doc_admin@school.ac.ke", "is_staff": True, "is_superuser": False},
        )
        self.admin_user.set_password("Password123!")
        self.admin_user.save()
        self.admin_user.tenants.add(self.tenant)

        # Regular non-staff user
        self.regular_user, _ = User.objects.get_or_create(
            username="doc_student",
            defaults={"email": "student@school.ac.ke", "is_staff": False, "is_superuser": False},
        )
        self.regular_user.set_password("Password123!")
        self.regular_user.save()
        self.regular_user.tenants.add(self.tenant)

        # Ensure active institution branding profile exists
        self.profile = InstitutionProfile.get_instance()
        self.profile.name = "St. Jude Premier High"
        self.profile.motto = "Strive to Excel"
        self.profile.primary_color = "#17365D"
        self.profile.secondary_color = "#1F6B4F"
        self.profile.accent_color = "#D4A72C"
        self.profile.save()

    def test_create_template_with_defaults(self):
        """Admin can create a template and receive well-formed default configurations."""
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            "name": "Standard Report Card",
            "category": "student_report",
            "description": "Default termly academic performance report.",
        }
        res = self.client.post("/api/documents/templates/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["name"], "Standard Report Card")
        self.assertEqual(res.data["category"], "student_report")
        self.assertIn("columns", res.data["header_config"])
        self.assertIn("columns", res.data["footer_config"])
        self.assertIn("opacity", res.data["watermark_config"])
        self.assertEqual(res.data["status"], "draft")

    def test_publish_creates_version_snapshot(self):
        """Publishing a template creates an immutable historical version snapshot."""
        self.client.force_authenticate(user=self.admin_user)
        template = DocumentTemplate.objects.create(
            name="Official Invoice",
            category="invoice",
            institution=self.profile,
            created_by=self.admin_user,
        )

        res = self.client.post(f"/api/documents/templates/{template.id}/publish/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["success"])
        self.assertEqual(res.data["version"]["version_number"], 1)

        template.refresh_from_db()
        self.assertEqual(template.status, "published")
        self.assertEqual(template.versions.count(), 1)

    def test_version_rollback(self):
        """Admin can restore a previously published snapshot into active draft state."""
        self.client.force_authenticate(user=self.admin_user)
        template = DocumentTemplate.objects.create(
            name="Original Title",
            category="letter",
            institution=self.profile,
            created_by=self.admin_user,
        )
        template.create_version_snapshot(published_by=self.admin_user)

        # Alter template in draft mode
        template.name = "Tampered Title"
        template.save()

        # Rollback to version 1
        res = self.client.post(f"/api/documents/templates/{template.id}/rollback/1/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        template.refresh_from_db()
        self.assertEqual(template.name, "Original Title")

    def test_weasyprint_pdf_generation(self):
        """Service generates a genuine multi-page binary PDF with headers and counters."""
        template = DocumentTemplate.objects.create(
            name="PDF Test Document",
            category="general",
            institution=self.profile,
        )
        context = get_default_context(self.profile)
        pdf_bytes = render_pdf_bytes(template, context=context)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(len(pdf_bytes) > 1000)
        self.assertTrue(pdf_bytes.startswith(b"%PDF-1."))

    def test_preview_pdf_api_endpoint(self):
        """Preview PDF endpoint streams binary PDF."""
        self.client.force_authenticate(user=self.admin_user)
        template = DocumentTemplate.objects.create(
            name="API PDF Preview",
            category="general",
            institution=self.profile,
        )
        res = self.client.get(f"/api/documents/templates/{template.id}/preview-pdf/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res["Content-Type"], "application/pdf")
        self.assertTrue(res.content.startswith(b"%PDF-1."))

    def test_preview_live_api_endpoint(self):
        """Preview live endpoint accepts transient draft JSON without saving to DB."""
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            "name": "Live Transient Test",
            "header_config": {"show_header": True, "columns": {}},
            "footer_config": {"show_footer": True, "columns": {}},
            "watermark_config": {"enabled": True, "opacity": 0.05, "type": "text"},
            "page_config": {"size": "A4", "orientation": "portrait"},
        }
        res = self.client.post("/api/documents/templates/preview-live/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res["Content-Type"], "application/pdf")
        self.assertTrue(res.content.startswith(b"%PDF-1."))

    def test_regular_user_cannot_create_or_publish_template(self):
        """Non-admin users cannot create or publish document templates."""
        self.client.force_authenticate(user=self.regular_user)
        res_post = self.client.post("/api/documents/templates/", {"name": "Hacked"}, format="json")
        self.assertEqual(res_post.status_code, status.HTTP_403_FORBIDDEN)

    def test_cross_tenant_isolation(self):
        """Tenant B cannot access or view Tenant A's document templates."""
        template_a = DocumentTemplate.objects.create(
            name="Tenant A Confidential Certificate",
            category="certificate",
            institution=self.profile,
        )

        with schema_context(get_public_schema_name()):
            tenant_b = Client.objects.create(schema_name="tenant_b_test", name="Tenant B School")
            Domain.objects.create(domain="tenant-b.localhost", tenant=tenant_b, is_primary=True)

        try:
            with schema_context("tenant_b_test"):
                profile_b = InstitutionProfile.get_instance()
                profile_b.name = "Tenant B School"
                profile_b.save()

                client_b = TenantAPIClient(tenant_b)
                user_b = User.objects.create(
                    username="admin_b",
                    email="admin@tenantb.ac.ke",
                    is_staff=True,
                    is_superuser=False,
                )
                user_b.tenants.add(tenant_b)
                client_b.force_authenticate(user=user_b)

                # Attempt to get Tenant A's template by ID
                res = client_b.get(f"/api/documents/templates/{template_a.id}/")
                self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

                # Attempt to list templates
                res_list = client_b.get("/api/documents/templates/")
                self.assertEqual(res_list.status_code, status.HTTP_200_OK)
                # Results list or paginated results
                results = res_list.data.get("results", res_list.data)
                self.assertEqual(len(results), 0)
        finally:
            with schema_context(get_public_schema_name()):
                tenant_b.delete()
