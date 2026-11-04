from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from .models import DocumentTemplate, DocumentTemplateVersion


class DocumentTemplateVersionSerializer(serializers.ModelSerializer):
    published_by_name = serializers.SerializerMethodField()

    class Meta:
        model = DocumentTemplateVersion
        fields = [
            "id",
            "version_number",
            "snapshot",
            "published_at",
            "published_by",
            "published_by_name",
        ]
        read_only_fields = ["id", "version_number", "published_at", "published_by"]

    def get_published_by_name(self, obj):
        if obj.published_by:
            full = obj.published_by.get_full_name
            return full if full else obj.published_by.username
        return None


class DocumentTemplateSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source="get_category_display", read_only=True)
    created_by_name = serializers.SerializerMethodField()
    updated_by_name = serializers.SerializerMethodField()
    versions_count = serializers.SerializerMethodField()
    latest_version_number = serializers.SerializerMethodField()

    class Meta:
        model = DocumentTemplate
        fields = [
            "id",
            "institution",
            "name",
            "category",
            "category_display",
            "description",
            "header_config",
            "footer_config",
            "watermark_config",
            "page_config",
            "table_config",
            "status",
            "is_default",
            "created_at",
            "updated_at",
            "created_by",
            "created_by_name",
            "updated_by",
            "updated_by_name",
            "versions_count",
            "latest_version_number",
        ]
        read_only_fields = [
            "id",
            "institution",
            "status",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]

    def get_created_by_name(self, obj):
        if obj.created_by:
            full = obj.created_by.get_full_name
            return full if full else obj.created_by.username
        return None

    def get_updated_by_name(self, obj):
        if obj.updated_by:
            full = obj.updated_by.get_full_name
            return full if full else obj.updated_by.username
        return None

    def get_versions_count(self, obj):
        return obj.versions.count()

    def get_latest_version_number(self, obj):
        latest = obj.versions.order_by("-version_number").first()
        return latest.version_number if latest else None

    def validate_name(self, value):
        val = (value or "").strip()
        if not val:
            raise serializers.ValidationError(_("Template name cannot be empty."))
        return val

    def validate_watermark_config(self, value):
        if isinstance(value, dict) and "opacity" in value:
            try:
                op = float(value["opacity"])
                if op < 0.0 or op > 1.0:
                    raise serializers.ValidationError(_("Watermark opacity must be between 0.0 and 1.0."))
            except (ValueError, TypeError):
                raise serializers.ValidationError(_("Watermark opacity must be a valid number."))
        return value
