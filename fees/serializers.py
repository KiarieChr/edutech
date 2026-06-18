from rest_framework import serializers
from .models import FeeStructure, FeeItem
from student_settings.serializers import AcademicYearSerializer, TermSerializer, GradeStructureSerializer
from finance.models import Account

class FeeItemSerializer(serializers.ModelSerializer):
    account_name = serializers.ReadOnlyField(source='account.name')
    is_mandatory = serializers.ReadOnlyField()  # Computed property: not is_optional
    
    class Meta:
        model = FeeItem
        fields = ['id', 'name', 'amount', 'is_mandatory', 'is_optional', 'frequency', 'priority', 'account', 'account_name']

    def validate_account(self, value):
        if not value.is_student_related:
            raise serializers.ValidationError("Account must be flagged as Student Related.")
        if value.type not in ['INCOME', 'LIABILITY']:
            raise serializers.ValidationError("Account must be Income or Liability.")
        return value

from student_settings.models import Curriculum

class FeeStructureSerializer(serializers.ModelSerializer):
    items = FeeItemSerializer(many=True, read_only=True)
    academic_year_details = AcademicYearSerializer(source='academic_year', read_only=True)
    term_details = TermSerializer(source='term', read_only=True)
    grade_details = GradeStructureSerializer(source='grade', read_only=True)
    
    # Fix: UniqueTogetherValidator requires curriculum since it's in unique_together.
    # Provide a default to prevent "The field curriculum is required" error.
    curriculum = serializers.PrimaryKeyRelatedField(
        queryset=Curriculum.objects.all(), 
        required=False, 
        allow_null=True, 
        default=None
    )
    
    # Write-only field for cloning
    clone_from_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    
    class Meta:
        model = FeeStructure
        fields = [
            'id', 'academic_year', 'academic_year_details',
            'term', 'term_details',
            'grade', 'grade_details',
            'curriculum', 
            'currency', 'status',
            'created_at', 'updated_at',
            'items', 'total_amount',
            'clone_from_id'
        ]
        read_only_fields = ['created_at', 'updated_at', 'total_amount']

    def create(self, validated_data):
        clone_from_id = validated_data.pop('clone_from_id', None)
        instance = super().create(validated_data)
        
        if clone_from_id:
            try:
                source = FeeStructure.objects.get(pk=clone_from_id)
                instance.clone_from(source)
            except FeeStructure.DoesNotExist:
                pass # Ignore if source invalid? Or raise error? REST framework 400 better.
                # Ideally validate in validation step.
        
        return instance

class FeeItemCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeeItem
        fields = '__all__'
        
    def validate_account(self, value):
        if not value.is_student_related:
            raise serializers.ValidationError("Account must be flagged as Student Related.")
        if value.type not in ['INCOME', 'LIABILITY']:
            raise serializers.ValidationError("Account must be Income or Liability.")
        return value

from .models import FeeInvoice, FeeInvoiceItem

class FeeInvoiceItemSerializer(serializers.ModelSerializer):
    amount_paid = serializers.SerializerMethodField()
    balance = serializers.SerializerMethodField()
    fee_category = serializers.IntegerField(source='fee_item.id', read_only=True)
    fee_item_name = serializers.CharField(source='fee_item.name', read_only=True)

    class Meta:
        model = FeeInvoiceItem
        fields = ['id', 'fee_category', 'fee_item_name', 'description', 'amount', 'amount_paid', 'balance', 'is_mandatory']

    def get_amount_paid(self, obj):
        # Sum allocations for this item
        from finance.models import ReceiptAllocation
        # Need to handle potential import loop? 
        # Ideally ReceiptAllocation should be in fees or handled carefully.
        # But ReceiptAllocation is in finance.models.
        # Let's import inside method.
        allocations = obj.allocations.all()
        return sum(a.amount for a in allocations)

    def get_balance(self, obj):
        paid = self.get_amount_paid(obj)
        return obj.amount - paid

class FeeInvoiceSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.student.get_full_name', read_only=True)
    admission_number = serializers.CharField(source='student.admission_number', read_only=True)
    term_name = serializers.CharField(source='term.name', read_only=True)
    year_name = serializers.CharField(source='academic_year.name', read_only=True)
    class_name = serializers.CharField(source='class_session.name', read_only=True)
    items = FeeInvoiceItemSerializer(many=True, read_only=True)

    class Meta:
        model = FeeInvoice
        fields = [
            'id', 'invoice_number', 'student', 'student_name', 'admission_number',
            'term', 'term_name',
            'academic_year', 'year_name',
            'class_session', 'class_name',
            'date_issued', 'due_date', 'status', 
            'total_amount', 'paid_amount', 'balance',
            'items'
        ]


# ============================================================
# FEE TEMPLATE SERIALIZERS
# ============================================================

from .models import VoteHead, GradeBand, FeeTemplate, TemplateLineItem, StudentFeeProfile


class VoteHeadSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source='default_account.name', read_only=True)
    account_code = serializers.CharField(source='default_account.code', read_only=True)
    usage_count = serializers.SerializerMethodField()

    class Meta:
        model = VoteHead
        fields = [
            'id', 'name', 'code', 'default_account', 'account_name', 'account_code',
            'frequency', 'is_optional', 'description', 'is_active',
            'usage_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_usage_count(self, obj):
        return obj.template_lines.count()

    def validate_default_account(self, value):
        if not value.is_student_related:
            raise serializers.ValidationError("Account must be flagged as Student Related.")
        if value.type not in ['INCOME', 'LIABILITY']:
            raise serializers.ValidationError("Account must be Income or Liability.")
        return value


class GradeBandSerializer(serializers.ModelSerializer):
    grade_names = serializers.ReadOnlyField()
    grade_count = serializers.SerializerMethodField()

    class Meta:
        model = GradeBand
        fields = [
            'id', 'name', 'grades', 'grade_names', 'grade_count',
            'description', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_grade_count(self, obj):
        return obj.grades.count()


class TemplateLineItemSerializer(serializers.ModelSerializer):
    vote_head_name = serializers.CharField(source='vote_head.name', read_only=True)
    vote_head_code = serializers.CharField(source='vote_head.code', read_only=True)
    effective_account_name = serializers.SerializerMethodField()
    effective_account_id = serializers.SerializerMethodField()

    class Meta:
        model = TemplateLineItem
        fields = [
            'id', 'template', 'vote_head', 'vote_head_name', 'vote_head_code',
            'amount', 'override_account', 'effective_account_name', 'effective_account_id',
            'is_mandatory', 'is_optional', 'applies_to', 'priority'
        ]
        read_only_fields = ['is_optional']

    def get_effective_account_name(self, obj):
        acc = obj.effective_account
        return f"{acc.code} - {acc.name}" if acc else None

    def get_effective_account_id(self, obj):
        acc = obj.effective_account
        return acc.id if acc else None


class TemplateLineItemWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemplateLineItem
        fields = ['id', 'template', 'vote_head', 'amount', 'override_account', 'is_mandatory', 'applies_to', 'priority']


class FeeTemplateSerializer(serializers.ModelSerializer):
    line_items = TemplateLineItemSerializer(many=True, read_only=True)
    term_name = serializers.CharField(source='term.name', read_only=True)
    year_name = serializers.CharField(source='academic_year.name', read_only=True)
    grade_band_name = serializers.CharField(source='grade_band.name', read_only=True, default=None)
    covered_grades = serializers.SerializerMethodField()
    student_count = serializers.SerializerMethodField()
    total_amount = serializers.ReadOnlyField()
    mandatory_total = serializers.ReadOnlyField()

    class Meta:
        model = FeeTemplate
        fields = [
            'id', 'name',
            'grade_band', 'grade_band_name', 'grades', 'covered_grades',
            'curriculum', 'term', 'term_name', 'academic_year', 'year_name',
            'status', 'currency',
            'parent_template',
            'line_items', 'total_amount', 'mandatory_total',
            'student_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'total_amount', 'mandatory_total']

    def get_covered_grades(self, obj):
        grades = obj.get_covered_grades()
        return [{'id': g.id, 'name': g.name} for g in grades]

    def get_student_count(self, obj):
        """Count enrolled students across all covered grades for this term/year."""
        from academics.models import StudentSessionEnrollment, ClassSession
        grade_ids = [g.id for g in obj.get_covered_grades()]
        sessions = ClassSession.objects.filter(
            grade_id__in=grade_ids,
            term=obj.term,
            academic_year=obj.academic_year
        )
        return StudentSessionEnrollment.objects.filter(
            session__in=sessions,
            is_active=True
        ).values('student_id').distinct().count()


class NestedLineItemSerializer(serializers.Serializer):
    """Nested serializer for line items within FeeTemplate create/update."""
    id = serializers.IntegerField(required=False)
    vote_head = serializers.PrimaryKeyRelatedField(queryset=VoteHead.objects.all())
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    is_mandatory = serializers.BooleanField(default=True)
    applies_to = serializers.ChoiceField(
        choices=TemplateLineItem.APPLIES_TO_CHOICES, default='ALL'
    )
    override_account = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.filter(is_student_related=True),
        required=False, allow_null=True
    )
    priority = serializers.IntegerField(default=0)


class FeeTemplateWriteSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating FeeTemplate with nested line items."""
    line_items = NestedLineItemSerializer(many=True, required=False)

    class Meta:
        model = FeeTemplate
        fields = [
            'id', 'name', 'grade_band', 'grades', 'curriculum',
            'term', 'academic_year', 'status', 'currency', 'parent_template',
            'line_items',
        ]

    def create(self, validated_data):
        line_items_data = validated_data.pop('line_items', [])
        grades_data = validated_data.pop('grades', [])
        template = FeeTemplate.objects.create(**validated_data)
        if grades_data:
            template.grades.set(grades_data)
        for li_data in line_items_data:
            li_data.pop('id', None)
            TemplateLineItem.objects.create(template=template, **li_data)
        return template

    def update(self, instance, validated_data):
        line_items_data = validated_data.pop('line_items', None)
        grades_data = validated_data.pop('grades', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if grades_data is not None:
            instance.grades.set(grades_data)
        if line_items_data is not None:
            # Replace all line items
            instance.line_items.all().delete()
            for li_data in line_items_data:
                li_data.pop('id', None)
                TemplateLineItem.objects.create(template=instance, **li_data)
        return instance


class StudentFeeProfileSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    custom_item_names = serializers.SerializerMethodField()

    class Meta:
        model = StudentFeeProfile
        fields = [
            'id', 'student', 'student_name',
            'is_boarder', 'uses_transport',
            'custom_items', 'custom_item_names',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_student_name(self, obj):
        return str(obj.student)

    def get_custom_item_names(self, obj):
        return list(obj.custom_items.values_list('name', flat=True))
