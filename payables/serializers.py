from rest_framework import serializers
from .models import Vendor, Bill, BillLine

class VendorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = '__all__'

class BillLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillLine
        fields = ['id', 'description', 'amount', 'expense_account']

class BillSerializer(serializers.ModelSerializer):
    lines = BillLineSerializer(many=True)
    vendor_name = serializers.CharField(source='vendor.name', read_only=True)
    
    class Meta:
        model = Bill
        fields = [
            'id', 'vendor', 'vendor_name', 'bill_number', 'date_received', 
            'due_date', 'status', 'total_amount', 'notes', 'created_at', 'lines'
        ]
        read_only_fields = ['total_amount', 'created_at']

    def create(self, validated_data):
        lines_data = validated_data.pop('lines')
        bill = Bill.objects.create(**validated_data)
        
        total = 0
        for line_data in lines_data:
            total += line_data['amount']
            BillLine.objects.create(bill=bill, **line_data)
        
        bill.total_amount = total
        bill.save()
        return bill

    def update(self, instance, validated_data):
        lines_data = validated_data.pop('lines', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
            
        if lines_data is not None:
            instance.lines.all().delete()
            total = 0
            for line_data in lines_data:
                total += line_data['amount']
                BillLine.objects.create(bill=instance, **line_data)
            instance.total_amount = total
            
        instance.save()
        return instance
