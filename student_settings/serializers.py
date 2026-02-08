from rest_framework import serializers
from .models import (
    AcademicYear, Term, Curriculum, GradeStructure, Stream,
    AdmissionConfig, StudentStatus, PromotionRule, DemographicConfig, SchoolCalendar, Intake,
    CurriculumLevel
)

class AcademicYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcademicYear
        fields = '__all__'

class IntakeSerializer(serializers.ModelSerializer):
    """Serializer for Intake model with read-only computed fields"""
    academic_year_name = serializers.CharField(source='academic_year.name', read_only=True)
    year_name = serializers.CharField(read_only=True)
    entry_grade_name = serializers.CharField(source='entry_grade.name', read_only=True)
    student_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Intake
        fields = [
            'id', 'academic_year', 'academic_year_name', 'year_name',
            'name', 'code', 'start_date', 'description', 'is_active',
            'entry_grade', 'entry_grade_name',
            'student_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

class IntakeCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating Intake"""
    
    class Meta:
        model = Intake
        fields = ['academic_year', 'name', 'code', 'start_date', 'description', 'is_active', 'entry_grade']
    
    def validate_code(self, value):
        """Ensure code is uppercase and unique"""
        value = value.upper()
        instance = self.instance
        if instance:
            # Updating existing intake
            if Intake.objects.filter(code=value).exclude(pk=instance.pk).exists():
                raise serializers.ValidationError("An intake with this code already exists.")
        else:
            # Creating new intake
            if Intake.objects.filter(code=value).exists():
                raise serializers.ValidationError("An intake with this code already exists.")
        return value


class TermSerializer(serializers.ModelSerializer):
    academic_year_name = serializers.ReadOnlyField(source='academic_year.name')

    class Meta:
        model = Term
        fields = '__all__'

class CurriculumSerializer(serializers.ModelSerializer):
    class Meta:
        model = Curriculum
        fields = '__all__'

class CurriculumLevelSerializer(serializers.ModelSerializer):
    curriculum_name = serializers.ReadOnlyField(source='curriculum.name')
    
    class Meta:
        model = CurriculumLevel
        fields = '__all__'

class StreamSerializer(serializers.ModelSerializer):
    grade_name = serializers.ReadOnlyField(source='grade.name')
    class_teacher_name = serializers.ReadOnlyField(source='class_teacher.get_full_name')

    class Meta:
        model = Stream
        fields = '__all__'

class GradeStructureSerializer(serializers.ModelSerializer):
    curriculum_name = serializers.ReadOnlyField(source='curriculum.name')
    level_name = serializers.ReadOnlyField(source='curriculum_level.name', allow_null=True)
    streams = StreamSerializer(many=True, read_only=True)

    class Meta:
        model = GradeStructure
        fields = '__all__'
        fields = '__all__'

class AdmissionConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdmissionConfig
        fields = '__all__'

class StudentStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentStatus
        fields = '__all__'

class PromotionRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = PromotionRule
        fields = '__all__'

class DemographicConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = DemographicConfig
        fields = '__all__'

class SchoolCalendarSerializer(serializers.ModelSerializer):
    curriculum_name = serializers.ReadOnlyField(source='curriculum.name')
    grade_name = serializers.ReadOnlyField(source='grade.name')

    class Meta:
        model = SchoolCalendar
        fields = '__all__'

# Enrollment Serializers
from .models import Enrollment

class EnrollmentSerializer(serializers.ModelSerializer):
    """Full enrollment serializer with nested related data"""
    student_name = serializers.CharField(source='student.student.get_full_name', read_only=True)
    student_id_number = serializers.CharField(source='student.id', read_only=True)
    academic_year_name = serializers.CharField(source='academic_year.name', read_only=True)
    term_name = serializers.CharField(source='term.name', read_only=True)
    curriculum_name = serializers.CharField(source='curriculum.name', read_only=True)
    grade_name = serializers.CharField(source='grade.name', read_only=True)
    stream_name = serializers.CharField(source='stream.name', read_only=True, allow_null=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    enrollment_type_display = serializers.CharField(source='get_enrollment_type_display', read_only=True)
    
    class Meta:
        model = Enrollment
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']

class EnrollmentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating new enrollments with validation"""
    
    class Meta:
        model = Enrollment
        fields = [
            'student', 'academic_year', 'term', 'curriculum', 'grade', 'stream',
            'enrollment_type', 'enrollment_date', 'remarks', 'previous_enrollment',
            'stay_status', 'reporting_reason'
        ]
    
    def validate(self, data):
        """Validate enrollment data"""
        # Check if student already has an active enrollment for this term
        if Enrollment.objects.filter(
            student=data['student'],
            academic_year=data['academic_year'],
            term=data['term'],
            is_active=True,
            is_deleted=False
        ).exists():
            raise serializers.ValidationError(
                "Student already has an active enrollment for this academic year and term."
            )
        
        # Validate term belongs to academic year
        if data['term'].academic_year != data['academic_year']:
            raise serializers.ValidationError({
                'term': f"Term {data['term'].name} does not belong to academic year {data['academic_year'].name}."
            })
        
        # Validate grade belongs to curriculum
        if data['grade'].curriculum != data['curriculum']:
            raise serializers.ValidationError({
                'grade': f"Grade {data['grade'].name} does not belong to curriculum {data['curriculum'].name}."
            })
        
        # Validate stream belongs to grade (if provided)
        if data.get('stream') and data['stream'].grade != data['grade']:
            raise serializers.ValidationError({
                'stream': f"Stream {data['stream'].name} does not belong to grade {data['grade'].name}."
            })
        
        return data

class EnrollmentUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating enrollments"""
    
    class Meta:
        model = Enrollment
        fields = ['stream', 'status', 'exit_date', 'remarks', 'is_active']

class EnrollmentTimelineSerializer(serializers.ModelSerializer):
    """Compact serializer for timeline display"""
    academic_year = serializers.CharField(source='academic_year.name')
    term = serializers.CharField(source='term.name')
    curriculum = serializers.CharField(source='curriculum.name')
    grade = serializers.CharField(source='grade.name')
    stream = serializers.CharField(source='stream.name', allow_null=True)
    status_display = serializers.CharField(source='get_status_display')
    type_display = serializers.CharField(source='get_enrollment_type_display')
    
    class Meta:
        model = Enrollment
        fields = [
            'id', 'academic_year', 'term', 'curriculum', 'grade', 'stream',
            'status', 'status_display', 'enrollment_type', 'type_display',
            'enrollment_date', 'exit_date', 'is_active', 'stay_status'
        ]

class PromotionSerializer(serializers.Serializer):
    """Serializer for promotion action"""
    student_ids = serializers.ListField(
        child=serializers.IntegerField(),
        help_text="List of student IDs to promote"
    )
    target_academic_year = serializers.PrimaryKeyRelatedField(
        queryset=AcademicYear.objects.all(),
        help_text="Target academic year"
    )
    target_term = serializers.PrimaryKeyRelatedField(
        queryset=Term.objects.all(),
        help_text="Target term"
    )
    target_grade = serializers.PrimaryKeyRelatedField(
        queryset=GradeStructure.objects.all(),
        required=False,
        allow_null=True,
        help_text="Target grade (optional, will auto-calculate if not provided)"
    )
    remarks = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Remarks for the promotion"
    )
    
    def validate(self, data):
        """Validate promotion data"""
        # Validate term belongs to academic year
        if data['target_term'].academic_year != data['target_academic_year']:
            raise serializers.ValidationError({
                'target_term': f"Term {data['target_term'].name} does not belong to academic year {data['target_academic_year'].name}."
            })
        
        return data

class RepeatSerializer(serializers.Serializer):
    """Serializer for repeat action"""
    student_id = serializers.IntegerField(help_text="Student ID to repeat")
    academic_year = serializers.PrimaryKeyRelatedField(
        queryset=AcademicYear.objects.all(),
        help_text="Academic year for repeat"
    )
    term = serializers.PrimaryKeyRelatedField(
        queryset=Term.objects.all(),
        help_text="Term for repeat"
    )
    remarks = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Reason for repeating"
    )
    
    def validate(self, data):
        """Validate repeat data"""
        # Validate term belongs to academic year
        if data['term'].academic_year != data['academic_year']:
            raise serializers.ValidationError({
                'term': f"Term {data['term'].name} does not belong to academic year {data['academic_year'].name}."
            })
        
        return data

class CurriculumChangeSerializer(serializers.Serializer):
    """Serializer for curriculum change action"""
    student_id = serializers.IntegerField(help_text="Student ID")
    new_curriculum = serializers.PrimaryKeyRelatedField(
        queryset=Curriculum.objects.all(),
        help_text="New curriculum"
    )
    new_grade = serializers.PrimaryKeyRelatedField(
        queryset=GradeStructure.objects.all(),
        help_text="New grade in the new curriculum"
    )
    academic_year = serializers.PrimaryKeyRelatedField(
        queryset=AcademicYear.objects.all(),
        help_text="Academic year for the change"
    )
    term = serializers.PrimaryKeyRelatedField(
        queryset=Term.objects.all(),
        help_text="Term for the change"
    )
    remarks = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Reason for curriculum change"
    )
    
    def validate(self, data):
        """Validate curriculum change data"""
        # Validate term belongs to academic year
        if data['term'].academic_year != data['academic_year']:
            raise serializers.ValidationError({
                'term': f"Term {data['term'].name} does not belong to academic year {data['academic_year'].name}."
            })
        
        # Validate grade belongs to new curriculum
        if data['new_grade'].curriculum != data['new_curriculum']:
            raise serializers.ValidationError({
                'new_grade': f"Grade {data['new_grade'].name} does not belong to curriculum {data['new_curriculum'].name}."
            })
        
        return data
