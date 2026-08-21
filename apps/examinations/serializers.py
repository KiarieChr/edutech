from rest_framework import serializers
from django.db.models import Avg, Max, Min, Count, Q
from decimal import Decimal

from .models import (
    GradingScale, GradingLevel, AssessmentType, Examination,
    StudentMark, TermResult, TermSubjectResult, ReportCardTemplate
)


# =============================================================================
# GRADING SCALE & LEVELS
# =============================================================================

class GradingLevelSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = GradingLevel
        fields = [
            'id', 'grade', 'label', 'min_mark', 'max_mark',
            'points', 'order', 'color_hex'
        ]


class GradingScaleListSerializer(serializers.ModelSerializer):
    curriculum_name = serializers.CharField(source='curriculum.name', read_only=True)
    curriculum_code = serializers.CharField(source='curriculum.code', read_only=True)
    level_name = serializers.CharField(source='curriculum_level.name', read_only=True, default=None)
    level_count = serializers.IntegerField(source='levels.count', read_only=True)

    class Meta:
        model = GradingScale
        fields = [
            'id', 'name', 'code', 'curriculum', 'curriculum_name', 'curriculum_code',
            'curriculum_level', 'level_name', 'scale_type', 'max_mark',
            'pass_mark', 'is_active', 'level_count'
        ]


class GradingScaleDetailSerializer(serializers.ModelSerializer):
    curriculum_name = serializers.CharField(source='curriculum.name', read_only=True)
    curriculum_code = serializers.CharField(source='curriculum.code', read_only=True)
    level_name = serializers.CharField(source='curriculum_level.name', read_only=True, default=None)
    levels = GradingLevelSerializer(many=True)

    class Meta:
        model = GradingScale
        fields = [
            'id', 'name', 'code', 'curriculum', 'curriculum_name', 'curriculum_code',
            'curriculum_level', 'level_name', 'scale_type', 'max_mark',
            'pass_mark', 'description', 'is_active', 'levels'
        ]

    def create(self, validated_data):
        levels_data = validated_data.pop('levels', [])
        scale = GradingScale.objects.create(**validated_data)
        for level_data in levels_data:
            GradingLevel.objects.create(scale=scale, **level_data)
        return scale

    def update(self, instance, validated_data):
        levels_data = validated_data.pop('levels', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if levels_data is not None:
            existing_ids = set(instance.levels.values_list('id', flat=True))
            incoming_ids = set()

            for level_data in levels_data:
                level_id = level_data.get('id')
                if level_id and level_id in existing_ids:
                    level = GradingLevel.objects.get(id=level_id, scale=instance)
                    for attr, value in level_data.items():
                        setattr(level, attr, value)
                    level.save()
                    incoming_ids.add(level_id)
                else:
                    new_level = GradingLevel.objects.create(scale=instance, **level_data)
                    incoming_ids.add(new_level.id)

            # Delete removed levels
            to_delete = existing_ids - incoming_ids
            instance.levels.filter(id__in=to_delete).delete()

        return instance


# =============================================================================
# ASSESSMENT TYPES
# =============================================================================

class AssessmentTypeSerializer(serializers.ModelSerializer):
    curriculum_name = serializers.CharField(source='curriculum.name', read_only=True)
    curriculum_code = serializers.CharField(source='curriculum.code', read_only=True)
    level_name = serializers.CharField(source='curriculum_level.name', read_only=True, default=None)

    class Meta:
        model = AssessmentType
        fields = [
            'id', 'name', 'code', 'curriculum', 'curriculum_name', 'curriculum_code',
            'curriculum_level', 'level_name', 'category', 'weight',
            'max_mark', 'order', 'is_active'
        ]


# =============================================================================
# EXAMINATION
# =============================================================================

class ExaminationListSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    subject_code = serializers.CharField(source='subject.code', read_only=True)
    assessment_type_name = serializers.CharField(source='assessment_type.name', read_only=True)
    grade_name = serializers.CharField(source='class_session.grade.name', read_only=True)
    term_name = serializers.CharField(source='class_session.term.name', read_only=True)
    academic_year_name = serializers.CharField(source='class_session.academic_year.name', read_only=True)
    curriculum_code = serializers.CharField(source='class_session.curriculum.code', read_only=True)
    grading_scale_name = serializers.CharField(source='grading_scale.name', read_only=True)
    marks_count = serializers.IntegerField(source='marks.count', read_only=True)
    teacher_name = serializers.SerializerMethodField()

    class Meta:
        model = Examination
        fields = [
            'id', 'name', 'class_session', 'subject', 'subject_name', 'subject_code',
            'assessment_type', 'assessment_type_name', 'grading_scale', 'grading_scale_name',
            'grade_name', 'term_name', 'academic_year_name', 'curriculum_code',
            'exam_date', 'start_time', 'duration_minutes', 'max_mark',
            'status', 'teacher', 'teacher_name', 'marks_count'
        ]

    def get_teacher_name(self, obj):
        if obj.teacher:
            return obj.teacher.get_full_name() or obj.teacher.username
        return None


class ExaminationDetailSerializer(ExaminationListSerializer):
    marks = serializers.SerializerMethodField()

    class Meta(ExaminationListSerializer.Meta):
        fields = ExaminationListSerializer.Meta.fields + ['remarks', 'marks']

    def get_marks(self, obj):
        marks = obj.marks.select_related('student__student', 'stream').all()
        return StudentMarkSerializer(marks, many=True).data


# =============================================================================
# STUDENT MARKS
# =============================================================================

class StudentMarkSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    admission_number = serializers.CharField(source='student.admission_number', read_only=True)
    stream_name = serializers.CharField(source='stream.name', read_only=True, default=None)

    class Meta:
        model = StudentMark
        fields = [
            'id', 'examination', 'student', 'student_name', 'admission_number',
            'stream', 'stream_name', 'raw_mark', 'normalized_mark',
            'grade', 'points', 'grade_label',
            'is_absent', 'is_exempted', 'teacher_remark',
            'entered_by'
        ]
        read_only_fields = ['normalized_mark', 'grade', 'points', 'grade_label']

    def get_student_name(self, obj):
        user = obj.student.student
        return f"{user.first_name} {user.last_name}".strip() or user.username


class BulkMarksSerializer(serializers.Serializer):
    """Input serializer for bulk marks entry."""
    marks = serializers.ListField(
        child=serializers.DictField(),
        help_text='List of {student: id, raw_mark: float, is_absent: bool, teacher_remark: str}'
    )


# =============================================================================
# TERM RESULTS
# =============================================================================

class TermSubjectResultSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    subject_code = serializers.CharField(source='subject.code', read_only=True)

    class Meta:
        model = TermSubjectResult
        fields = [
            'id', 'subject', 'subject_name', 'subject_code',
            'weighted_mark', 'grade', 'points', 'grade_label',
            'assessment_breakdown', 'teacher_remark',
            'subject_rank', 'total_in_subject'
        ]


class TermResultListSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    admission_number = serializers.CharField(source='student.admission_number', read_only=True)
    grade_name = serializers.CharField(source='class_session.grade.name', read_only=True)
    term_name = serializers.CharField(source='class_session.term.name', read_only=True)
    stream_name = serializers.CharField(source='stream.name', read_only=True, default=None)

    class Meta:
        model = TermResult
        fields = [
            'id', 'student', 'student_name', 'admission_number',
            'class_session', 'grade_name', 'term_name', 'stream', 'stream_name',
            'total_marks', 'total_points', 'average_mark', 'average_points',
            'subjects_taken', 'overall_grade', 'overall_grade_label',
            'class_rank', 'stream_rank', 'grade_rank',
            'total_in_class', 'total_in_stream', 'total_in_grade',
            'is_published'
        ]

    def get_student_name(self, obj):
        user = obj.student.student
        return f"{user.first_name} {user.last_name}".strip() or user.username


class TermResultDetailSerializer(TermResultListSerializer):
    subject_results = TermSubjectResultSerializer(many=True, read_only=True)

    class Meta(TermResultListSerializer.Meta):
        fields = TermResultListSerializer.Meta.fields + [
            'class_teacher_remark', 'principal_remark',
            'published_at', 'subject_results'
        ]


# =============================================================================
# REPORT CARD TEMPLATE
# =============================================================================

class ReportCardTemplateSerializer(serializers.ModelSerializer):
    curriculum_name = serializers.CharField(source='curriculum.name', read_only=True)
    level_name = serializers.CharField(source='curriculum_level.name', read_only=True, default=None)

    class Meta:
        model = ReportCardTemplate
        fields = [
            'id', 'name', 'curriculum', 'curriculum_name',
            'curriculum_level', 'level_name',
            'show_marks', 'show_grades', 'show_points', 'show_rank',
            'show_grade_distribution', 'show_attendance',
            'show_teacher_remarks', 'show_principal_remarks',
            'show_assessment_breakdown', 'show_previous_terms',
            'show_class_average', 'show_highest_mark', 'show_lowest_mark',
            'is_active'
        ]


# =============================================================================
# ANALYSIS SERIALIZERS (read-only, computed)
# =============================================================================

class ExamAnalysisSerializer(serializers.Serializer):
    """Output-only serializer for exam analysis."""
    exam_id = serializers.IntegerField()
    exam_name = serializers.CharField()
    subject_name = serializers.CharField()
    total_students = serializers.IntegerField()
    marks_entered = serializers.IntegerField()
    absent = serializers.IntegerField()
    mean_mark = serializers.FloatField()
    median_mark = serializers.FloatField(allow_null=True)
    highest_mark = serializers.FloatField(allow_null=True)
    lowest_mark = serializers.FloatField(allow_null=True)
    pass_rate = serializers.FloatField()
    grade_distribution = serializers.DictField()


class ClassAnalysisSerializer(serializers.Serializer):
    """Output-only serializer for class-wide analysis."""
    class_session_id = serializers.IntegerField()
    class_name = serializers.CharField()
    term_name = serializers.CharField()
    total_students = serializers.IntegerField()
    subjects = serializers.ListField()
    overall_mean = serializers.FloatField()
    subject_means = serializers.ListField()
    grade_distribution = serializers.DictField()
    top_students = serializers.ListField()
