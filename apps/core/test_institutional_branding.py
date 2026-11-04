"""
Automated Test Suite for Institutional Branding Profile (Phase 1).
Covers identity, logos, colors, typography, permissions, file validations,
and cross-tenant isolation in accordance with project specification.
"""
import io
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.db import connection
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import BaseTenantRequestFactory
from django_tenants.utils import schema_context, get_public_schema_name

from core.models import InstitutionProfile, AuditLog
from tenants.models import Client, Domain

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


def create_in_memory_image(format='PNG', size=(100, 100), color=(23, 54, 93)):
    """Helper to generate a valid in-memory image for upload testing."""
    file_obj = io.BytesIO()
    image = Image.new('RGB', size, color=color)
    image.save(file_obj, format=format)
    file_obj.seek(0)
    ext = format.lower()
    if ext == 'jpeg':
        ext = 'jpg'
    return SimpleUploadedFile(
        name=f"test_logo.{ext}",
        content=file_obj.read(),
        content_type=f"image/{format.lower()}"
    )


class InstitutionalBrandingTests(FastTenantTestCase):
    """
    Tests for Institutional Branding Profile within tenant schema.
    """

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = 'Test Branding Tenant'
        tenant.save()

    @classmethod
    def setup_domain(cls, domain):
        domain.is_primary = True

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        self.client = TenantAPIClient(self.tenant)

        # Admin user belonging to this tenant
        self.admin_user, _ = User.objects.get_or_create(
            username='branding_admin',
            defaults={'email': 'admin@school.ac.ke', 'is_staff': True, 'is_superuser': False}
        )
        self.admin_user.set_password('Password123!')
        self.admin_user.save()
        self.admin_user.tenants.add(self.tenant)

        # Standard non-staff user belonging to this tenant
        self.regular_user, _ = User.objects.get_or_create(
            username='standard_teacher',
            defaults={'email': 'teacher@school.ac.ke', 'is_staff': False, 'is_superuser': False}
        )
        self.regular_user.set_password('Password123!')
        self.regular_user.save()
        self.regular_user.tenants.add(self.tenant)

        # Initialize profile
        self.profile = InstitutionProfile.get_instance()
        self.profile.name = "Fahari Academy High School"
        self.profile.motto = "Excellence Through Discipline"
        self.profile.save()

    # -------------------------------------------------------------------------
    # 1. Profile Creation & Singleton Enforcement
    # -------------------------------------------------------------------------
    def test_singleton_guarantee(self):
        """Ensure only one InstitutionProfile can ever exist per tenant schema."""
        instance1 = InstitutionProfile.get_instance()
        self.assertEqual(instance1.pk, 1)

        # Attempt to save a second instance
        second = InstitutionProfile(name="Rogue Secondary School")
        second.save()
        self.assertEqual(second.pk, 1)
        self.assertEqual(InstitutionProfile.objects.count(), 1)
        self.assertEqual(InstitutionProfile.get_instance().name, "Rogue Secondary School")

    # -------------------------------------------------------------------------
    # 2. Authentication & Authorization
    # -------------------------------------------------------------------------
    def test_unauthenticated_requests_rejected(self):
        """Unauthenticated requests to branding endpoints must be rejected."""
        url = reverse('institution-branding-detail')
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        update_url = reverse('institution-branding-update')
        res_update = self.client.patch(update_url, {'display_name': 'Hacked'}, format='json')
        self.assertEqual(res_update.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_regular_user_cannot_update_branding(self):
        """Non-admin/non-staff users must not be permitted to update branding settings."""
        self.client.force_authenticate(user=self.regular_user)
        update_url = reverse('institution-branding-update')
        res = self.client.patch(update_url, {'motto': 'New Motto'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_authenticated_user_can_read_branding(self):
        """Any authenticated user belonging to the tenant can view the branding profile."""
        self.client.force_authenticate(user=self.regular_user)
        url = reverse('institution-branding-detail')
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['name'], "Fahari Academy High School")
        self.assertIn('primary_color', res.data)
        self.assertIn('font_family', res.data)

    # -------------------------------------------------------------------------
    # 3. Identity and Contact Updates
    # -------------------------------------------------------------------------
    def test_update_identity_and_contact_fields(self):
        """Admin can update official name, display name, legal name, motto, and contacts."""
        self.client.force_authenticate(user=self.admin_user)
        update_url = reverse('institution-branding-update')
        payload = {
            'name': 'Fahari Senior Academy',
            'display_name': 'Fahari Academy',
            'registered_name': 'Fahari Academy Educational Trust Ltd',
            'motto': 'Knowledge is Power',
            'registration_number': 'MOE/SEC/2026/099',
            'phone': '+254712345678',
            'phone_alt': '+254798765432',
            'email': 'info@fahari.ac.ke',
            'website': 'https://fahari.ac.ke',
            'postal_address': 'P.O. Box 45000 - 00100, Nairobi',
            'city': 'Nairobi',
            'county': 'Nairobi County',
            'country': 'Kenya',
            'additional_contact_info': 'Admin offices open Monday to Friday, 8:00 AM - 5:00 PM.'
        }
        res = self.client.patch(update_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.name, 'Fahari Senior Academy')
        self.assertEqual(self.profile.display_name, 'Fahari Academy')
        self.assertEqual(self.profile.registered_name, 'Fahari Academy Educational Trust Ltd')
        self.assertEqual(self.profile.phone_alt, '+254798765432')
        self.assertEqual(self.profile.postal_address, 'P.O. Box 45000 - 00100, Nairobi')
        self.assertEqual(self.profile.additional_contact_info, payload['additional_contact_info'])
        self.assertEqual(self.profile.updated_by, self.admin_user)

    # -------------------------------------------------------------------------
    # 4. Brand Colours Validation
    # -------------------------------------------------------------------------
    def test_save_valid_brand_colors(self):
        """Admin can save custom hexadecimal brand palette."""
        self.client.force_authenticate(user=self.admin_user)
        update_url = reverse('institution-branding-update')
        payload = {
            'primary_color': '#0F2942',
            'secondary_color': '#107C41',
            'accent_color': '#D83B01',
            'text_color': '#1B1B1B',
            'background_color': '#F4F6F8'
        }
        res = self.client.patch(update_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.primary_color, '#0F2942')
        self.assertEqual(self.profile.secondary_color, '#107C41')
        self.assertEqual(self.profile.accent_color, '#D83B01')
        self.assertEqual(self.profile.text_color, '#1B1B1B')
        self.assertEqual(self.profile.background_color, '#F4F6F8')

    def test_reject_invalid_hex_colors(self):
        """Invalid hexadecimal color strings must be rejected with 400 Bad Request."""
        self.client.force_authenticate(user=self.admin_user)
        update_url = reverse('institution-branding-update')

        invalid_colors = ['red', '#12345', '123456', '#GGGGGG', '#1234567']
        for bad_color in invalid_colors:
            res = self.client.patch(update_url, {'primary_color': bad_color}, format='json')
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST, f"Failed to reject: {bad_color}")
            self.assertIn('primary_color', res.data)

    # -------------------------------------------------------------------------
    # 5. Typography Preferences Validation
    # -------------------------------------------------------------------------
    def test_save_valid_typography_settings(self):
        """Admin can save supported typography preferences within valid bounds."""
        self.client.force_authenticate(user=self.admin_user)
        update_url = reverse('institution-branding-update')
        payload = {
            'font_family': 'Merriweather',
            'font_size_body': 15,
            'font_size_heading': 26,
        }
        res = self.client.patch(update_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.font_family, 'Merriweather')
        self.assertEqual(self.profile.font_size_body, 15)
        self.assertEqual(self.profile.font_size_heading, 26)

    def test_reject_out_of_range_typography(self):
        """Font sizes outside bounds or unknown font families must be rejected."""
        self.client.force_authenticate(user=self.admin_user)
        update_url = reverse('institution-branding-update')

        # Body size too small (< 9)
        res1 = self.client.patch(update_url, {'font_size_body': 7}, format='json')
        self.assertEqual(res1.status_code, status.HTTP_400_BAD_REQUEST)

        # Body size too large (> 20)
        res2 = self.client.patch(update_url, {'font_size_body': 28}, format='json')
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)

        # Heading size too small (< 16)
        res3 = self.client.patch(update_url, {'font_size_heading': 12}, format='json')
        self.assertEqual(res3.status_code, status.HTTP_400_BAD_REQUEST)

        # Heading size too large (> 48)
        res4 = self.client.patch(update_url, {'font_size_heading': 64}, format='json')
        self.assertEqual(res4.status_code, status.HTTP_400_BAD_REQUEST)

        # Unsupported font family
        res5 = self.client.patch(update_url, {'font_family': 'Comic Sans MS'}, format='json')
        self.assertEqual(res5.status_code, status.HTTP_400_BAD_REQUEST)

    # -------------------------------------------------------------------------
    # 6. Logo Management: Upload, Replace, Remove, and Validations
    # -------------------------------------------------------------------------
    def test_upload_valid_logos(self):
        """Upload valid PNG, JPEG, and WebP logos for primary, dark, and secondary emblem."""
        self.client.force_authenticate(user=self.admin_user)
        url = reverse('institution-branding-logo-dispatch')

        # 1. Primary logo (PNG)
        png_file = create_in_memory_image(format='PNG')
        res_primary = self.client.post(url, {'type': 'primary', 'file': png_file}, format='multipart')
        self.assertEqual(res_primary.status_code, status.HTTP_200_OK)
        self.assertTrue(res_primary.data['success'])
        self.assertIsNotNone(res_primary.data['url'])

        # 2. Dark background logo (JPEG)
        jpg_file = create_in_memory_image(format='JPEG')
        res_dark = self.client.post(url, {'type': 'dark', 'file': jpg_file}, format='multipart')
        self.assertEqual(res_dark.status_code, status.HTTP_200_OK)

        # 3. Secondary emblem (WebP)
        webp_file = create_in_memory_image(format='WEBP')
        res_secondary = self.client.post(url, {'type': 'secondary', 'file': webp_file}, format='multipart')
        self.assertEqual(res_secondary.status_code, status.HTTP_200_OK)

        self.profile.refresh_from_db()
        self.assertTrue(bool(self.profile.logo))
        self.assertTrue(bool(self.profile.logo_dark))
        self.assertTrue(bool(self.profile.secondary_logo))

    def test_reject_unsupported_file_types_and_fake_images(self):
        """Text or script files disguised as images must be rejected with 400."""
        self.client.force_authenticate(user=self.admin_user)
        url = reverse('institution-branding-logo-dispatch')

        # Fake image file (text content inside a .png file)
        fake_file = SimpleUploadedFile(
            name="malicious.png",
            content=b"<?php echo 'malicious code'; ?>",
            content_type="image/png"
        )
        res = self.client.post(url, {'type': 'primary', 'file': fake_file}, format='multipart')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', res.data)

        # Unsupported extension (.exe or .txt)
        txt_file = SimpleUploadedFile(
            name="notes.txt",
            content=b"plain text notes",
            content_type="text/plain"
        )
        res_txt = self.client.post(url, {'type': 'primary', 'file': txt_file}, format='multipart')
        self.assertEqual(res_txt.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reject_oversized_images(self):
        """Images exceeding the 5MB file-size limit must be rejected."""
        self.client.force_authenticate(user=self.admin_user)
        url = reverse('institution-branding-logo-dispatch')

        # Fake 6MB payload with png extension
        large_bytes = b"0" * (6 * 1024 * 1024)
        large_file = SimpleUploadedFile(
            name="large_logo.png",
            content=large_bytes,
            content_type="image/png"
        )
        res = self.client.post(url, {'type': 'primary', 'file': large_file}, format='multipart')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('exceeds the maximum allowed limit of 5.00 MB', res.data['error'])

    def test_remove_logo(self):
        """Admin can remove an existing logo via DELETE request."""
        self.client.force_authenticate(user=self.admin_user)
        dispatch_url = reverse('institution-branding-logo-dispatch')

        # First upload
        png_file = create_in_memory_image(format='PNG')
        self.client.post(dispatch_url, {'type': 'primary', 'file': png_file}, format='multipart')
        self.profile.refresh_from_db()
        self.assertTrue(bool(self.profile.logo))

        # Delete primary logo
        res_del = self.client.delete(f"{dispatch_url}?type=primary")
        self.assertEqual(res_del.status_code, status.HTTP_200_OK)
        self.profile.refresh_from_db()
        self.assertFalse(bool(self.profile.logo))

    # -------------------------------------------------------------------------
    # 7. Preserving Unrelated Institution Settings
    # -------------------------------------------------------------------------
    def test_preserve_unrelated_institution_settings(self):
        """Updating branding settings must preserve templates, principal, and modules."""
        self.profile.business_sector = InstitutionProfile.BusinessSector.EDUCATION
        self.profile.enabled_modules = ['academics', 'finance', 'workforce']
        self.profile.principal_name = 'Dr. Margaret Otieno'
        self.profile.principal_title = 'CHIEF PRINCIPAL'
        self.profile.offer_letter_template = '<h1>Conditional Offer</h1><p>Welcome</p>'
        self.profile.save()

        self.client.force_authenticate(user=self.admin_user)
        update_url = reverse('institution-branding-update')
        res = self.client.patch(update_url, {
            'display_name': 'New Campus Brand',
            'primary_color': '#112233'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.display_name, 'New Campus Brand')
        self.assertEqual(self.profile.primary_color, '#112233')
        # Check that unrelated settings are fully preserved
        self.assertEqual(self.profile.business_sector, InstitutionProfile.BusinessSector.EDUCATION)
        self.assertEqual(self.profile.enabled_modules, ['academics', 'finance', 'workforce'])
        self.assertEqual(self.profile.principal_name, 'Dr. Margaret Otieno')
        self.assertEqual(self.profile.principal_title, 'CHIEF PRINCIPAL')
        self.assertEqual(self.profile.offer_letter_template, '<h1>Conditional Offer</h1><p>Welcome</p>')


class MultiTenantIsolationTests(FastTenantTestCase):
    """
    Tests ensuring strict cross-tenant data isolation and preventing unauthorized access.
    """

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = 'Test Tenant A'
        tenant.save()

    @classmethod
    def setup_domain(cls, domain):
        domain.is_primary = True

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        self.client = TenantAPIClient(self.tenant)

        # Create a second tenant to test cross-tenant isolation in the public schema
        with schema_context(get_public_schema_name()):
            self.second_tenant, _ = Client.objects.get_or_create(
                schema_name='rivalschool',
                defaults={'name': 'Rival Academy'}
            )
            Domain.objects.get_or_create(
                domain='rivalschool.localhost',
                tenant=self.second_tenant,
                defaults={'is_primary': True}
            )

        connection.set_tenant(self.tenant)

        # Admin user for Tenant A (self.tenant)
        self.tenant_a_admin, _ = User.objects.get_or_create(
            username='tenant_a_admin',
            defaults={'email': 'admin_a@fahari.ac.ke', 'is_staff': True}
        )
        self.tenant_a_admin.set_password('Password123!')
        self.tenant_a_admin.save()
        self.tenant_a_admin.tenants.add(self.tenant)

        # Admin user strictly belonging to Tenant B (self.second_tenant)
        self.tenant_b_admin, _ = User.objects.get_or_create(
            username='tenant_b_admin',
            defaults={'email': 'admin_b@rival.ac.ke', 'is_staff': True}
        )
        self.tenant_b_admin.set_password('Password123!')
        self.tenant_b_admin.save()
        self.tenant_b_admin.tenants.add(self.second_tenant)

    def test_tenant_b_user_cannot_access_tenant_a_branding(self):
        """
        User belonging strictly to Tenant B cannot access or modify Tenant A's branding.
        TenantAccessPermission rejects the user when requesting against Tenant A.
        """
        # Authenticate as Tenant B's admin against Tenant A's connection
        self.client.force_authenticate(user=self.tenant_b_admin)

        detail_url = reverse('institution-branding-detail')
        res = self.client.get(detail_url)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("You do not have access to this tenant/school", str(res.data))

        update_url = reverse('institution-branding-update')
        res_update = self.client.patch(update_url, {'display_name': 'Hacked Name'}, format='json')
        self.assertEqual(res_update.status_code, status.HTTP_403_FORBIDDEN)

    def test_client_cannot_tamper_with_institution_id(self):
        """
        Passing an arbitrary institution ID or tenant ID in request payloads does not alter
        the server-side resolved profile or breach tenant boundaries.
        """
        self.client.force_authenticate(user=self.tenant_a_admin)
        update_url = reverse('institution-branding-update')

        # Try to supply a rogue id: 9999 or tenant_id
        res = self.client.patch(update_url, {
            'id': 9999,
            'name': 'Legitimate Tenant A Update'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Verify the active profile remains id=1 (singleton in this tenant's schema)
        active_profile = InstitutionProfile.get_instance()
        self.assertEqual(active_profile.pk, 1)
        self.assertEqual(active_profile.name, 'Legitimate Tenant A Update')
