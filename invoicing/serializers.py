from rest_framework import serializers
from .models import Customer, Invoice, InvoiceLine

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = '__all__'

class InvoiceLineSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    
    class Meta:
        model = InvoiceLine
        fields = ['id', 'description', 'quantity', 'unit_price', 'amount', 'income_account']

class InvoiceSerializer(serializers.ModelSerializer):
    lines = InvoiceLineSerializer(many=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    
    class Meta:
        model = Invoice
        fields = [
            'id', 'customer', 'customer_name', 'invoice_number', 'date_issued', 
            'due_date', 'status', 'is_recurring', 'subtotal', 'tax_total', 'total_amount', 
            'notes', 'created_at', 'lines'
        ]
        read_only_fields = ['subtotal', 'tax_total', 'total_amount', 'created_at']

    def create(self, validated_data):
        lines_data = validated_data.pop('lines')
        invoice = Invoice.objects.create(**validated_data)
        
        total = 0
        for line_data in lines_data:
            line_data['amount'] = line_data['quantity'] * line_data['unit_price']
            total += line_data['amount']
            InvoiceLine.objects.create(invoice=invoice, **line_data)
        
        invoice.total_amount = total
        invoice.subtotal = total # Assuming no tax logic yet
        invoice.save()
        return invoice

    def update(self, instance, validated_data):
        lines_data = validated_data.pop('lines', None)
        
        # Update scalar fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        if lines_data is not None:
            # Simple replace logic for lines: delete old, create new
            instance.lines.all().delete()
            total = 0
            for line_data in lines_data:
                line_data['amount'] = line_data['quantity'] * line_data['unit_price']
                total += line_data['amount']
                InvoiceLine.objects.create(invoice=instance, **line_data)
            
            instance.total_amount = total
            instance.subtotal = total
            
        instance.save()
        return instance
