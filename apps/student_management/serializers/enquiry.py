from rest_framework import serializers
from student_management.models.enquiry import Enquiry
from student_management.models.application import Application


class EnquirySerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    source_display = serializers.CharField(source='get_source_display', read_only=True)
    intake_name = serializers.CharField(source='intake.name', read_only=True, allow_null=True)
    grade_name = serializers.CharField(source='grade.name', read_only=True, allow_null=True)
    campus_name = serializers.CharField(source='campus.name', read_only=True, allow_null=True)
    curriculum_name = serializers.CharField(source='curriculum.name', read_only=True, allow_null=True)
    assigned_to_name = serializers.CharField(source='assigned_to.get_full_name', read_only=True, allow_null=True)
    converted_application_id = serializers.PrimaryKeyRelatedField(
        source='converted_application', read_only=True, allow_null=True
    )

    class Meta:
        model = Enquiry
        fields = [
            'id', 'full_name', 'child_name', 'phone_number', 'email',
            'intake', 'intake_name', 'curriculum', 'curriculum_name',
            'grade', 'grade_name', 'campus', 'campus_name',
            'message', 'source', 'source_display',
            'status', 'status_display',
            'assigned_to', 'assigned_to_name',
            'follow_up_date', 'follow_up_notes',
            'converted_application_id', 'converted_at',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'converted_application_id', 'converted_at', 'created_at', 'updated_at']


class EnquiryCreateSerializer(serializers.ModelSerializer):
    """Lightweight serializer for creating/updating an enquiry."""
    class Meta:
        model = Enquiry
        fields = [
            'full_name', 'child_name', 'phone_number', 'email',
            'intake', 'curriculum', 'grade', 'campus',
            'message', 'source', 'assigned_to', 'follow_up_date',
        ]


class EnquiryConvertSerializer(serializers.Serializer):
    """
    Input serializer for the convert/ action.
    The caller optionally passes the ID of an existing Application to link,
    or leaves it empty and the viewset creates a new one from enquiry data.
    """
    existing_application_id = serializers.PrimaryKeyRelatedField(
        queryset=Application.objects.all(),
        required=False,
        allow_null=True,
        help_text='Link to an existing Application instead of creating a new one.'
    )
