from rest_framework import serializers
from student_management.models.application import Application

class ApplicationSerializer(serializers.ModelSerializer):
    intake_name = serializers.CharField(source='intake.name', read_only=True)
    curriculum_name = serializers.CharField(source='applying_for_curriculum.name', read_only=True)
    level_name = serializers.CharField(source='applying_for_level.name', read_only=True)
    grade_name = serializers.CharField(source='applying_for_grade.name', read_only=True)

    class Meta:
        model = Application
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')
        extra_kwargs = {
            'applying_for_level': {'required': False, 'allow_null': True}
        }
