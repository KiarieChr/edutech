from rest_framework import serializers
from student_management.models.application import Application

class ApplicationSerializer(serializers.ModelSerializer):
    intake_name = serializers.CharField(source='intake.name', read_only=True)
    curriculum_name = serializers.CharField(source='applying_for_curriculum.name', read_only=True)
    level_name = serializers.CharField(source='applying_for_level.name', read_only=True, allow_null=True)
    grade_name = serializers.CharField(source='applying_for_grade.name', read_only=True, allow_null=True)
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = Application
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')
        extra_kwargs = {
            'applying_for_level': {'required': False, 'allow_null': True},
            'applying_for_grade': {'required': False, 'allow_null': True},
            # Make new fields optional for backward compatibility
            'middle_name': {'required': False},
            'birth_certificate_number': {'required': False},
            'nationality': {'required': False},
            'religion': {'required': False},
            'home_address': {'required': False},
            'county': {'required': False},
            'sub_county': {'required': False},
            'guardian_relationship': {'required': False},
            'guardian_id_number': {'required': False},
            'guardian_occupation': {'required': False},
            'guardian_address': {'required': False},
            'guardian2_name': {'required': False},
            'guardian2_relationship': {'required': False},
            'guardian2_phone': {'required': False},
            'guardian2_email': {'required': False},
            'emergency_contact_name': {'required': False},
            'emergency_contact_phone': {'required': False},
            'emergency_contact_relationship': {'required': False},
            'medical_conditions': {'required': False},
            'allergies': {'required': False},
            'special_needs': {'required': False},
            'blood_group': {'required': False},
            'doctor_name': {'required': False},
            'doctor_phone': {'required': False},
            'health_insurance': {'required': False},
            'previous_school_name': {'required': False},
            'previous_school_address': {'required': False},
            'previous_class': {'required': False},
            'previous_school_contact': {'required': False},
            'transfer_reason': {'required': False},
            'previous_school_leaving_date': {'required': False},
            'is_transfer': {'required': False},
            'assessment_score': {'required': False},
            'birth_certificate': {'required': False},
            'previous_report_card': {'required': False},
            'transfer_letter': {'required': False},
            'passport_photo': {'required': False},
            'medical_report': {'required': False},
            'referral_source': {'required': False},
        }
    
    def get_full_name(self, obj):
        parts = [obj.first_name]
        if obj.middle_name:
            parts.append(obj.middle_name)
        parts.append(obj.last_name)
        return ' '.join(parts)
