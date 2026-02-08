from rest_framework import serializers
from .models import FeeStructure, FeeItem
from student_settings.serializers import AcademicYearSerializer, TermSerializer, GradeStructureSerializer
from finance.models import Account

class FeeItemSerializer(serializers.ModelSerializer):
    account_name = serializers.ReadOnlyField(source='account.name')
    
    class Meta:
        model = FeeItem
        fields = ['id', 'name', 'amount', 'is_mandatory', 'is_optional', 'frequency', 'priority', 'account', 'account_name']

    def validate_account(self, value):
        if not value.is_student_related:
            raise serializers.ValidationError("Account must be flagged as Student Related.")
        if value.type not in ['INCOME', 'LIABILITY']:
            raise serializers.ValidationError("Account must be Income or Liability.")
        return value

class FeeStructureSerializer(serializers.ModelSerializer):
    items = FeeItemSerializer(many=True, read_only=True)
    academic_year_details = AcademicYearSerializer(source='academic_year', read_only=True)
    term_details = TermSerializer(source='term', read_only=True)
    grade_details = GradeStructureSerializer(source='grade', read_only=True)
    
    # Write-only field for cloning
    clone_from_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    
    class Meta:
        model = FeeStructure
        fields = [
            'id', 'academic_year', 'academic_year_details',
            'term', 'term_details',
            'grade', 'grade_details',
            'curriculum', 
            'currency', 'status', 'is_active',
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
