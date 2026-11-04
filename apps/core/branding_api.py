"""
Institutional Branding Profile API Views and Serializers (Phase 1).
Provides endpoints for retrieving and managing institutional identity,
logos, color palette, typography preferences, and contact information.
"""
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError as DjangoValidationError

from .models import InstitutionProfile
from .permissions import TenantAccessPermission
from .branding_utils import (
    validate_hex_color,
    validate_branding_image,
    delete_old_logo_file,
)


class CanManageBrandingPermission(BasePermission):
    """
    Enforces that only authorized institution administrators (staff or superusers)
    who belong to the current tenant can modify branding settings or assets.
    """
    message = "You do not have administrative permissions to modify institutional branding."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        # Must be staff member of this tenant
        if not request.user.is_staff:
            return False
        # Verify tenant membership if inside a tenant schema
        if hasattr(request, 'tenant') and request.tenant.schema_name != 'public':
            return request.user.tenants.filter(id=request.tenant.id).exists()
        return True


class InstitutionBrandingSerializer(serializers.ModelSerializer):
    """
    Serializer for institutional identity, logos, brand colors, typography,
    and official contact information.
    """
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    website = serializers.URLField(required=False, allow_blank=True, allow_null=True)
    portal_url = serializers.URLField(required=False, allow_blank=True, allow_null=True)
    updated_by_name = serializers.SerializerMethodField(read_only=True)
    logo_url = serializers.SerializerMethodField(read_only=True)
    logo_dark_url = serializers.SerializerMethodField(read_only=True)
    secondary_logo_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = InstitutionProfile
        fields = [
            'id',
            # Identity
            'name',
            'display_name',
            'registered_name',
            'short_name',
            'motto',
            'institution_type',
            'registration_number',
            'established_date',
            # Logos
            'logo',
            'logo_url',
            'logo_dark',
            'logo_dark_url',
            'secondary_logo',
            'secondary_logo_url',
            # Contact
            'phone',
            'phone_alt',
            'email',
            'website',
            'portal_url',
            # Physical & Postal Address
            'address_line_1',
            'address_line_2',
            'postal_address',
            'city',
            'county',
            'postal_code',
            'country',
            'additional_contact_info',
            # Brand Colors
            'primary_color',
            'secondary_color',
            'accent_color',
            'text_color',
            'background_color',
            # Typography Preferences
            'font_family',
            'font_size_body',
            'font_size_heading',
            # Metadata
            'created_at',
            'updated_at',
            'updated_by',
            'updated_by_name',
        ]
        read_only_fields = [
            'id',
            'created_at',
            'updated_at',
            'updated_by',
            'updated_by_name',
            'logo',
            'logo_dark',
            'secondary_logo',
            'logo_url',
            'logo_dark_url',
            'secondary_logo_url',
        ]

    def get_updated_by_name(self, obj):
        if obj.updated_by:
            full = obj.updated_by.get_full_name
            return full if full else obj.updated_by.username
        return None

    def get_logo_url(self, obj):
        return obj.logo.url if obj.logo else None

    def get_logo_dark_url(self, obj):
        return obj.logo_dark.url if obj.logo_dark else None

    def get_secondary_logo_url(self, obj):
        return obj.secondary_logo.url if obj.secondary_logo else None

    def validate_name(self, value):
        val = (value or '').strip()
        if not val:
            raise serializers.ValidationError(_("Official institution name cannot be blank."))
        return val

    def validate_primary_color(self, value):
        try:
            return validate_hex_color(value, "Primary color")
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message)

    def validate_secondary_color(self, value):
        try:
            return validate_hex_color(value, "Secondary color")
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message)

    def validate_accent_color(self, value):
        try:
            return validate_hex_color(value, "Accent color")
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message)

    def validate_text_color(self, value):
        try:
            return validate_hex_color(value, "Text color")
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message)

    def validate_background_color(self, value):
        try:
            return validate_hex_color(value, "Background color")
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message)

    def validate_font_family(self, value):
        if not value:
            return InstitutionProfile.FontFamily.INTER
        valid_choices = [c[0] for c in InstitutionProfile.FontFamily.choices]
        if value not in valid_choices:
            raise serializers.ValidationError(
                _(f"Invalid font family '{value}'. Must be one of: {', '.join(valid_choices)}.")
            )
        return value

    def validate_font_size_body(self, value):
        if value is not None and (value < 9 or value > 20):
            raise serializers.ValidationError(_("Body font size must be between 9 and 20 pt/px."))
        return value

    def validate_font_size_heading(self, value):
        if value is not None and (value < 16 or value > 48):
            raise serializers.ValidationError(_("Heading font size must be between 16 and 48 pt/px."))
        return value

    def to_internal_value(self, data):
        data = data.copy() if hasattr(data, 'copy') else dict(data)
        if 'established_date' in data and data['established_date'] == '':
            data['established_date'] = None
        for field in ('email', 'website', 'portal_url', 'phone', 'phone_alt', 'postal_address'):
            if field in data and data[field] is None:
                data[field] = ''
        return super().to_internal_value(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated, TenantAccessPermission])
def institution_branding_detail(request):
    """
    Retrieve the current tenant's institutional branding profile.
    Guaranteed to execute within the active tenant schema resolved server-side.
    """
    profile = InstitutionProfile.get_instance()
    serializer = InstitutionBrandingSerializer(profile)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated, TenantAccessPermission, CanManageBrandingPermission])
def institution_branding_update(request):
    """
    Update the current tenant's institutional branding profile.
    Only authorized institution administrators may update settings.
    Audit fields (updated_by) are set server-side.
    """
    profile = InstitutionProfile.get_instance()
    partial = request.method == 'PATCH'
    serializer = InstitutionBrandingSerializer(profile, data=request.data, partial=partial)
    serializer.is_valid(raise_exception=True)
    instance = serializer.save()

    # Track who updated the branding settings
    if request.user and request.user.is_authenticated:
        instance.updated_by = request.user
        instance.save(update_fields=['updated_by', 'updated_at'])

    return Response(InstitutionBrandingSerializer(instance).data, status=status.HTTP_200_OK)


def _handle_logo_upload(request):
    """
    Upload or replace an institutional logo asset.
    Supports logo types: 'primary' (default), 'dark', or 'secondary'.
    Validates file format (PNG, JPEG, WebP), dimensions, and payload integrity.
    Safely cleans up any previously saved asset.
    """
    logo_type = request.data.get('type') or request.query_params.get('type') or 'primary'
    field_map = {
        'primary': 'logo',
        'dark': 'logo_dark',
        'secondary': 'secondary_logo',
    }
    if logo_type not in field_map:
        return Response(
            {'error': f"Invalid logo type '{logo_type}'. Must be 'primary', 'dark', or 'secondary'."},
            status=status.HTTP_400_BAD_REQUEST
        )

    field_name = field_map[logo_type]
    file = (
        request.FILES.get('file')
        or request.FILES.get('logo')
        or request.FILES.get(field_name)
    )

    if not file:
        return Response(
            {'error': "No image file was provided in the request payload."},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        validate_branding_image(file)
    except DjangoValidationError as e:
        return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)

    profile = InstitutionProfile.get_instance()

    # Delete existing logo file if present
    old_file = getattr(profile, field_name)
    delete_old_logo_file(old_file)

    # Attach new file and record auditing
    setattr(profile, field_name, file)
    if request.user and request.user.is_authenticated:
        profile.updated_by = request.user

    profile.save()

    saved_file = getattr(profile, field_name)
    return Response({
        'success': True,
        'message': f"{logo_type.capitalize()} logo uploaded successfully.",
        'logo_type': logo_type,
        'url': saved_file.url if saved_file else None,
        'profile': InstitutionBrandingSerializer(profile).data,
    }, status=status.HTTP_200_OK)


def _handle_logo_remove(request):
    """
    Safely remove an institutional logo asset and delete it from storage.
    Type specified via query param or body ?type=primary|dark|secondary (default: primary).
    """
    logo_type = (
        request.query_params.get('type')
        or (hasattr(request, 'data') and request.data.get('type'))
        or 'primary'
    ).lower()
    field_map = {
        'primary': 'logo',
        'dark': 'logo_dark',
        'secondary': 'secondary_logo',
    }
    if logo_type not in field_map:
        return Response(
            {'error': f"Invalid logo type '{logo_type}'. Must be 'primary', 'dark', or 'secondary'."},
            status=status.HTTP_400_BAD_REQUEST
        )

    field_name = field_map[logo_type]
    profile = InstitutionProfile.get_instance()

    old_file = getattr(profile, field_name)
    if old_file:
        delete_old_logo_file(old_file)
        setattr(profile, field_name, None)
        if request.user and request.user.is_authenticated:
            profile.updated_by = request.user
        profile.save()

    return Response({
        'success': True,
        'message': f"{logo_type.capitalize()} logo removed successfully.",
        'logo_type': logo_type,
        'profile': InstitutionBrandingSerializer(profile).data,
    }, status=status.HTTP_200_OK)


@api_view(['POST', 'DELETE'])
@permission_classes([IsAuthenticated, TenantAccessPermission, CanManageBrandingPermission])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def institution_branding_logo_dispatch(request):
    """
    Unified logo endpoint handling POST (upload/replace) and DELETE (remove).
    """
    if request.method == 'POST':
        return _handle_logo_upload(request)
    elif request.method == 'DELETE':
        return _handle_logo_remove(request)
    return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


@api_view(['POST'])
@permission_classes([IsAuthenticated, TenantAccessPermission, CanManageBrandingPermission])
@parser_classes([MultiPartParser, FormParser])
def institution_branding_logo_upload(request):
    return _handle_logo_upload(request)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, TenantAccessPermission, CanManageBrandingPermission])
def institution_branding_logo_remove(request):
    return _handle_logo_remove(request)


