from rest_framework import serializers
from student_management.models.admission import Admission
from student_management.models.class_session import StudentPlacement
from student_settings.models import Intake
from django.utils import timezone

class AdmissionSerializer(serializers.ModelSerializer):
    applicant_name = serializers.SerializerMethodField()
    student_name = serializers.CharField(source='student.student.get_full_name', read_only=True)
    
    # Enrollment details - making them writable
    intake = serializers.PrimaryKeyRelatedField(queryset=Intake.objects.all(), source='student.intake', required=False, allow_null=True)
    grade_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    stream_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    
    # Read-only for display
    grade = serializers.SerializerMethodField()
    stream = serializers.SerializerMethodField()

    class_name = serializers.SerializerMethodField()
    entry_type = serializers.SerializerMethodField()
    status = serializers.CharField(source='student.status', required=False) # Changed to writable source

    class Meta:
        model = Admission
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'updated_by', 'admission_number')

    def get_applicant_name(self, obj):
        return f"{obj.application.first_name} {obj.application.last_name}"

    def get_grade(self, obj):
        last_placement = obj.student.placements.filter(session_status='active').last()
        return last_placement.grade.id if last_placement else None

    def get_stream(self, obj):
        last_placement = obj.student.placements.filter(session_status='active').last()
        return last_placement.stream.id if last_placement and last_placement.stream else None

    def get_class_name(self, obj):
        last_placement = obj.student.placements.filter(session_status='active').last()
        if last_placement:
            return f"{last_placement.grade.name} {last_placement.stream.name if last_placement.stream else ''}".strip()
        return "N/A"

    def get_entry_type(self, obj):
        if getattr(obj.application, 'is_transfer', False):
            return "Transfer In"
        return "New Admission"

    def update(self, instance, validated_data):
        # Handle student status if provided
        student_data = validated_data.pop('student', {})
        student_status = student_data.get('status')
        intake = student_data.get('intake')
        
        if student_status:
            instance.student.status = student_status
            instance.student.save()
            
        if intake:
            instance.student.intake = intake
            instance.student.save()

        # Handle grade/stream update (creating/updating StudentPlacement)
        grade_id = validated_data.pop('grade_id', None)
        stream_id = validated_data.pop('stream_id', None)

        if grade_id or stream_id:
            # Update the student's active placement or create one
            active_placement = instance.student.placements.filter(session_status='active').last()
            
            if active_placement:
                if grade_id:
                    active_placement.grade_id = grade_id
                if stream_id:
                    active_placement.stream_id = stream_id
                active_placement.save()
            else:
                # Create a new one if none exists (best effort)
                # Need academic year and term - fallback to current
                from student_settings.models import AcademicYear, Term
                year = AcademicYear.objects.filter(is_current=True).first()
                term = Term.objects.filter(academic_year=year, is_current=True).first()
                
                if year and term and grade_id:
                    StudentPlacement.objects.create(
                        student=instance.student,
                        intake=intake or instance.student.intake,
                        academic_year=year,
                        term=term,
                        grade_id=grade_id,
                        stream_id=stream_id,
                        curriculum_id=instance.application.applying_for_curriculum_id,
                        start_date=term.start_date,
                        session_type='reporting',
                        session_status='active'
                    )

        return super().update(instance, validated_data)
