from rest_framework import serializers
from .models import ClassSession, StudentSessionEnrollment

class ClassSessionSerializer(serializers.ModelSerializer):
    grade_name = serializers.CharField(source='grade.name', read_only=True)
    term_name = serializers.CharField(source='term.name', read_only=True)
    academic_year_name = serializers.CharField(source='academic_year.name', read_only=True)
    curriculum_name = serializers.CharField(source='curriculum.name', read_only=True)
    curriculum_level_name = serializers.CharField(source='curriculum_level.name', read_only=True, allow_null=True)
    grade_level_order = serializers.IntegerField(source='grade.level_order', read_only=True, allow_null=True)
    enrollment_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = ClassSession
        fields = [
            'id', 'name', 
            'grade', 'grade_name',
            'grade_level_order',
            'term', 'term_name',
            'academic_year', 'academic_year_name',
            'curriculum', 'curriculum_name',
            'curriculum_level', 'curriculum_level_name',
            'status', 'start_date', 'end_date',
            'enrollment_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'name']

class StudentSessionEnrollmentSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.student.full_name', read_only=True)
    admission_number = serializers.CharField(source='student.admission_number', read_only=True)
    session_name = serializers.CharField(source='session.name', read_only=True)
    intake_name = serializers.CharField(source='intake.name', read_only=True)
    stream_name = serializers.CharField(source='stream.name', read_only=True, allow_null=True)

    class Meta:
        model = StudentSessionEnrollment
        fields = [
            'id', 'student', 'student_name', 'admission_number',
            'session', 'session_name',
            'intake', 'intake_name',
            'status', 'progression_status', 'is_active',
            'reporting_date', 'completion_date',
            'stream', 'stream_name',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
