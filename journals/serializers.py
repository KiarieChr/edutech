from rest_framework import serializers
from .models import JournalEntry, JournalLine
from finance.serializers import AccountSerializer
from finance.models import Account

class JournalLineSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source='account.code', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)
    
    class Meta:
        model = JournalLine
        fields = ['id', 'account', 'account_code', 'account_name', 'debit', 'credit', 'description']

class JournalEntrySerializer(serializers.ModelSerializer):
    lines = JournalLineSerializer(many=True)
    total_debit = serializers.SerializerMethodField()
    total_credit = serializers.SerializerMethodField()

    class Meta:
        model = JournalEntry
        fields = [
            'id', 'date', 'description', 'journal_type', 'reference', 
            'status', 'created_at', 'updated_at', 'lines',
            'total_debit', 'total_credit'
        ]
        read_only_fields = ['status', 'created_at', 'updated_at']

    def get_total_debit(self, obj):
        return sum(line.debit for line in obj.lines.all())

    def get_total_credit(self, obj):
        return sum(line.credit for line in obj.lines.all())

    def create(self, validated_data):
        lines_data = validated_data.pop('lines')
        entry = JournalEntry.objects.create(**validated_data)
        for line_data in lines_data:
            JournalLine.objects.create(entry=entry, **line_data)
        return entry

    def update(self, instance, validated_data):
        if instance.status == 'POSTED':
             raise serializers.ValidationError("Cannot edit a posted journal entry.")
             
        lines_data = validated_data.pop('lines', None)
        instance = super().update(instance, validated_data)
        
        if lines_data is not None:
            instance.lines.all().delete()
            for line_data in lines_data:
                JournalLine.objects.create(entry=instance, **line_data)
                
        return instance
