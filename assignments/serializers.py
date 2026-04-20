from rest_framework import serializers
from .models import Assignment, AssignmentSubmission


class AssignmentListSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    subject_code = serializers.CharField(source='subject.code', read_only=True)
    class_session_name = serializers.CharField(source='class_session.name', read_only=True)
    created_by_name = serializers.SerializerMethodField()
    assignment_type_display = serializers.CharField(source='get_assignment_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    submission_count = serializers.IntegerField(read_only=True)
    graded_count = serializers.IntegerField(read_only=True)
    is_past_due = serializers.BooleanField(read_only=True)

    class Meta:
        model = Assignment
        fields = [
            'id', 'title', 'description', 'assignment_type', 'assignment_type_display',
            'status', 'status_display', 'class_session', 'class_session_name',
            'subject', 'subject_name', 'subject_code',
            'created_by', 'created_by_name', 'file', 'max_score',
            'due_date', 'is_past_due', 'submission_count', 'graded_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at']

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name or obj.created_by.username
        return None


class AssignmentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Assignment
        fields = [
            'id', 'title', 'description', 'assignment_type', 'status',
            'class_session', 'subject', 'file', 'max_score', 'due_date',
        ]

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class SubmissionListSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    student_admission_number = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    assignment_title = serializers.CharField(source='assignment.title', read_only=True)

    class Meta:
        model = AssignmentSubmission
        fields = [
            'id', 'assignment', 'assignment_title',
            'student', 'student_name', 'student_admission_number',
            'file', 'text_response', 'score', 'teacher_remarks',
            'status', 'status_display', 'submitted_at', 'graded_at',
        ]
        read_only_fields = ['submitted_at', 'graded_at']

    def get_student_name(self, obj):
        return obj.student.student.get_full_name or obj.student.student.username

    def get_student_admission_number(self, obj):
        return getattr(obj.student, 'id_number', None) or str(obj.student.id)


class SubmissionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssignmentSubmission
        fields = ['id', 'assignment', 'file', 'text_response']

    def create(self, validated_data):
        from accounts.models import Student
        student = Student.objects.get(student=self.context['request'].user)
        validated_data['student'] = student
        return super().create(validated_data)


class SubmissionGradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssignmentSubmission
        fields = ['score', 'teacher_remarks', 'status']

    def update(self, instance, validated_data):
        from django.utils import timezone
        validated_data['graded_at'] = timezone.now()
        validated_data['graded_by'] = self.context['request'].user
        if 'status' not in validated_data:
            validated_data['status'] = 'graded'
        return super().update(instance, validated_data)


# ── Portal serializers (read-only, for students/parents) ──

class PortalAssignmentSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    subject_code = serializers.CharField(source='subject.code', read_only=True)
    class_session_name = serializers.CharField(source='class_session.name', read_only=True)
    teacher_name = serializers.SerializerMethodField()
    assignment_type_display = serializers.CharField(source='get_assignment_type_display', read_only=True)
    is_past_due = serializers.BooleanField(read_only=True)
    my_submission = serializers.SerializerMethodField()

    class Meta:
        model = Assignment
        fields = [
            'id', 'title', 'description', 'assignment_type', 'assignment_type_display',
            'subject', 'subject_name', 'subject_code',
            'class_session', 'class_session_name',
            'teacher_name', 'file', 'max_score',
            'due_date', 'is_past_due', 'created_at',
            'my_submission',
        ]

    def get_teacher_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name or obj.created_by.username
        return None

    def get_my_submission(self, obj):
        student = self.context.get('student')
        if not student:
            return None
        try:
            sub = obj.submissions.get(student=student)
            return {
                'id': sub.id,
                'file': sub.file.url if sub.file else None,
                'score': str(sub.score) if sub.score is not None else None,
                'status': sub.status,
                'teacher_remarks': sub.teacher_remarks,
                'submitted_at': sub.submitted_at.isoformat(),
            }
        except AssignmentSubmission.DoesNotExist:
            return None
