from rest_framework import serializers
from .models import (
    Faculty, Department, Programme, Specialization,
    ProgrammeUnit, UnitOffering, ProgrammeEnrollment, UnitRegistration
)


class FacultySerializer(serializers.ModelSerializer):
    department_count = serializers.SerializerMethodField()
    dean_name = serializers.CharField(source='dean.get_full_name', read_only=True, allow_null=True)

    class Meta:
        model = Faculty
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_department_count(self, obj):
        return obj.departments.filter(is_active=True).count()


class DepartmentSerializer(serializers.ModelSerializer):
    faculty_name = serializers.CharField(source='faculty.name', read_only=True, allow_null=True)
    head_name = serializers.CharField(source='head.get_full_name', read_only=True, allow_null=True)
    programme_count = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_programme_count(self, obj):
        return obj.programmes.filter(is_active=True).count()


class SpecializationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Specialization
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']


class ProgrammeUnitSerializer(serializers.ModelSerializer):
    unit_type_display = serializers.CharField(source='get_unit_type_display', read_only=True)
    semester_display = serializers.CharField(source='get_semester_offered_display', read_only=True)
    specialization_name = serializers.CharField(source='specialization.name', read_only=True, allow_null=True)

    class Meta:
        model = ProgrammeUnit
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']


class ProgrammeSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.name', read_only=True, allow_null=True)
    level_display = serializers.CharField(read_only=True)
    duration_label = serializers.CharField(read_only=True)
    unit_count = serializers.SerializerMethodField()
    enrollment_count = serializers.SerializerMethodField()
    specializations = SpecializationSerializer(many=True, read_only=True)

    class Meta:
        model = Programme
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_unit_count(self, obj):
        return obj.units.filter(is_active=True).count()

    def get_enrollment_count(self, obj):
        return obj.enrollments.filter(status='active').count()


class ProgrammeCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Programme
        fields = [
            'department', 'name', 'code', 'level', 'duration', 'duration_type',
            'total_credit_units', 'description', 'minimum_entry_requirements',
            'has_specialization', 'is_active',
        ]


class UnitOfferingSerializer(serializers.ModelSerializer):
    unit_name = serializers.CharField(source='unit.name', read_only=True)
    unit_code = serializers.CharField(source='unit.code', read_only=True)
    intake_name = serializers.CharField(source='intake.name', read_only=True)
    semester_name = serializers.CharField(source='semester.name', read_only=True)
    lecturer_name = serializers.CharField(source='lecturer.get_full_name', read_only=True, allow_null=True)

    class Meta:
        model = UnitOffering
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']


class ProgrammeEnrollmentSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.student.get_full_name', read_only=True)
    programme_name = serializers.CharField(source='programme.name', read_only=True)
    programme_code = serializers.CharField(source='programme.code', read_only=True)
    specialization_name = serializers.CharField(source='specialization.name', read_only=True, allow_null=True)
    intake_name = serializers.CharField(source='intake.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = ProgrammeEnrollment
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'gpa']


class UnitRegistrationSerializer(serializers.ModelSerializer):
    unit_name = serializers.CharField(source='offering.unit.name', read_only=True)
    unit_code = serializers.CharField(source='offering.unit.code', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = UnitRegistration
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']
