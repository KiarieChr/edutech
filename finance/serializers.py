from rest_framework import serializers
from .models import Account, AccountType, AccountSubType

class AccountSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(source='get_type_display', read_only=True)
    sub_type_display = serializers.CharField(source='get_sub_type_display', read_only=True)
    normal_balance = serializers.CharField(read_only=True)
    
    class Meta:
        model = Account
        fields = [
            'id', 'code', 'name', 'type', 'type_display', 
            'sub_type', 'sub_type_display', 'description', 
            'parent', 'is_active', 'is_student_related',
            'created_at', 'updated_at', 'normal_balance'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate(self, data):
        # Basic validation handled by model, but we can add more here if needed
        return data

class AccountTypeOptionSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()

class AccountSubTypeOptionSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()

from .models import Tax, FinanceSettings, FiscalPeriod, Cashbook, PaymentMethod

class TaxSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tax
        fields = '__all__'

class FiscalPeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = FiscalPeriod
        fields = '__all__'

class CashbookSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source='account.name', read_only=True)
    class Meta:
        model = Cashbook
        fields = ['id', 'name', 'currency', 'account', 'account_name', 'low_cash_threshold', 'created_at', 
                  'opening_balance', 'opening_balance_date', 'is_opening_balance_posted',
                  'is_active', 'is_default', 'voucher_prefix']

class PaymentMethodSerializer(serializers.ModelSerializer):
    account_name = serializers.ReadOnlyField(source='account.name')
    class Meta:
        model = PaymentMethod
        fields = '__all__'

class FinanceSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinanceSettings
        fields = '__all__'
    
    def create(self, validated_data):
        # Override create to ensure singleton behavior via API if needed, 
        # though View should handle retrieving the single instance.
        instance, created = FinanceSettings.objects.get_or_create(pk=1, defaults=validated_data)
        if not created:
            return super().update(instance, validated_data)
        return instance
