from rest_framework import serializers
from student_management.models.class_session import StudentPlacement

class StudentPlacementSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.student.get_full_name', read_only=True)
    admission_number = serializers.CharField(source='student.admission_number', read_only=True)
    
    academic_year_name = serializers.CharField(source='academic_year.name', read_only=True)
    term_name = serializers.CharField(source='term.name', read_only=True)
    curriculum_code = serializers.CharField(source='curriculum.code', read_only=True)
    level_name = serializers.CharField(source='curriculum_level.name', read_only=True)
    grade_name = serializers.CharField(source='grade.name', read_only=True)
    stream_name = serializers.CharField(source='stream.name', read_only=True)

    class Meta:
        model = StudentPlacement
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')
