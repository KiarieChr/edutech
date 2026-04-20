from rest_framework import serializers
from student_management.models.admission import Admission
from student_settings.models import Intake, Enrollment
from django.utils import timezone

class AdmissionSerializer(serializers.ModelSerializer):
    applicant_name = serializers.SerializerMethodField()
    student_name = serializers.CharField(source='student.student.get_full_name', read_only=True)
    
    # Enrollment details - making them writable
    intake = serializers.PrimaryKeyRelatedField(queryset=Intake.objects.all(), source='student.intake', required=False, allow_null=True)
    grade_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    stream_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    academic_year_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    curriculum_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    curriculum_level_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    
    # Read-only for display
    grade = serializers.SerializerMethodField()
    stream = serializers.SerializerMethodField()
    academic_year = serializers.SerializerMethodField()
    curriculum = serializers.SerializerMethodField()
    curriculum_level = serializers.SerializerMethodField()

    class_name = serializers.SerializerMethodField()
    entry_type = serializers.SerializerMethodField()
    status = serializers.CharField(source='student.status', required=False) # Changed to writable source

    # --- Document generation fields (read-only) ---
    passport_photo_url = serializers.SerializerMethodField()
    guardian_name = serializers.CharField(source='application.guardian_name', read_only=True, default='')
    guardian_relationship = serializers.CharField(source='application.guardian_relationship', read_only=True, default='')
    guardian_phone = serializers.CharField(source='application.phone_number', read_only=True, default='')
    guardian_email = serializers.EmailField(source='application.email', read_only=True, default=None, allow_null=True)
    student_dob = serializers.DateField(source='application.date_of_birth', read_only=True, default=None, allow_null=True)
    student_gender = serializers.CharField(source='application.gender', read_only=True, default='')
    student_nationality = serializers.CharField(source='application.nationality', read_only=True, default='Kenyan')
    applying_for_grade_name = serializers.SerializerMethodField()
    applying_for_curriculum_name = serializers.SerializerMethodField()

    class Meta:
        model = Admission
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'updated_by', 'admission_number')

    def get_applicant_name(self, obj):
        return f"{obj.application.first_name} {obj.application.last_name}"

    def get_passport_photo_url(self, obj):
        request = self.context.get('request')
        photo = getattr(obj.application, 'passport_photo', None)
        if photo and photo.name:
            return request.build_absolute_uri(photo.url) if request else photo.url
        return None

    def get_applying_for_grade_name(self, obj):
        grade = getattr(obj.application, 'applying_for_grade', None)
        return grade.name if grade else ''

    def get_applying_for_curriculum_name(self, obj):
        curriculum = getattr(obj.application, 'applying_for_curriculum', None)
        return curriculum.name if curriculum else ''

    def get_grade(self, obj):
        active_enrollment = obj.student.enrollments.filter(status='active', is_active=True).last()
        return active_enrollment.grade.id if active_enrollment else None

    def get_stream(self, obj):
        active_enrollment = obj.student.enrollments.filter(status='active', is_active=True).last()
        return active_enrollment.stream.id if active_enrollment and active_enrollment.stream else None

    def get_class_name(self, obj):
        active_enrollment = obj.student.enrollments.filter(status='active', is_active=True).last()
        if active_enrollment:
            return f"{active_enrollment.grade.name} {active_enrollment.stream.name if active_enrollment.stream else ''}".strip()
        return "N/A"

    def get_entry_type(self, obj):
        if getattr(obj.application, 'is_transfer', False):
            return "Transfer In"
        return "New Admission"

    def get_academic_year(self, obj):
        active_enrollment = obj.student.enrollments.filter(status='active', is_active=True).last()
        return active_enrollment.academic_year_id if active_enrollment else None

    def get_curriculum(self, obj):
        active_enrollment = obj.student.enrollments.filter(status='active', is_active=True).last()
        return active_enrollment.curriculum_id if active_enrollment else None

    def get_curriculum_level(self, obj):
        active_enrollment = obj.student.enrollments.filter(status='active', is_active=True).last()
        return active_enrollment.curriculum_level_id if active_enrollment else None

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

        # Handle grade/stream/academic_year/curriculum update on Enrollment
        grade_id = validated_data.pop('grade_id', None)
        stream_id = validated_data.pop('stream_id', None)
        academic_year_id = validated_data.pop('academic_year_id', None)
        curriculum_id = validated_data.pop('curriculum_id', None)
        curriculum_level_id = validated_data.pop('curriculum_level_id', None)

        enrollment_updates = {}
        if grade_id is not None:
            enrollment_updates['grade_id'] = grade_id
        if stream_id is not None:
            enrollment_updates['stream_id'] = stream_id
        if academic_year_id is not None:
            enrollment_updates['academic_year_id'] = academic_year_id
        if curriculum_id is not None:
            enrollment_updates['curriculum_id'] = curriculum_id
        if curriculum_level_id is not None:
            enrollment_updates['curriculum_level_id'] = curriculum_level_id

        if enrollment_updates:
            # Update the student's active enrollment or create one
            active_enrollment = instance.student.enrollments.filter(status='active', is_active=True).last()
            
            if active_enrollment:
                # If academic year changed, update term to match the new year
                new_year_id = enrollment_updates.get('academic_year_id')
                if new_year_id and new_year_id != active_enrollment.academic_year_id:
                    from student_settings.models import Term as TermModel
                    matching_term = TermModel.objects.filter(
                        academic_year_id=new_year_id, is_current=True, is_deleted=False
                    ).first()
                    if not matching_term:
                        matching_term = TermModel.objects.filter(
                            academic_year_id=new_year_id, is_deleted=False
                        ).order_by('start_date').first()
                    if matching_term:
                        enrollment_updates['term_id'] = matching_term.id

                for field, value in enrollment_updates.items():
                    setattr(active_enrollment, field, value)
                active_enrollment.save()
            else:
                # Create a new one if none exists (best effort)
                from student_settings.models import AcademicYear, Term
                year_id = enrollment_updates.get('academic_year_id')
                if not year_id:
                    year = AcademicYear.objects.filter(is_current=True).first()
                    year_id = year.pk if year else None
                
                term = Term.objects.filter(academic_year_id=year_id, is_current=True).first()
                final_grade_id = enrollment_updates.get('grade_id')
                
                if year_id and term and final_grade_id:
                    Enrollment.objects.create(
                        student=instance.student,
                        intake=intake or getattr(instance.student, 'intake', None),
                        academic_year_id=year_id,
                        term=term,
                        grade_id=final_grade_id,
                        stream_id=enrollment_updates.get('stream_id'),
                        campus=instance.campus,
                        curriculum_id=enrollment_updates.get('curriculum_id') or instance.application.applying_for_curriculum_id,
                        curriculum_level_id=enrollment_updates.get('curriculum_level_id'),
                        enrollment_type='new_admission',
                        status='active',
                        is_active=True,
                        enrollment_date=timezone.now().date()
                    )

        return super().update(instance, validated_data)
