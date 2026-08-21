from rest_framework import serializers
from .models import Customer, Invoice, InvoiceLine
from .services import InvoiceService

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = '__all__'

class InvoiceLineSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    income_account_name = serializers.CharField(source='income_account.name', read_only=True)
    
    class Meta:
        model = InvoiceLine
        fields = ['id', 'description', 'quantity', 'unit_price', 'amount', 'income_account', 'income_account_name']

class InvoiceSerializer(serializers.ModelSerializer):
    lines = InvoiceLineSerializer(many=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    auto_post = serializers.BooleanField(write_only=True, required=False, default=False)
    
    class Meta:
        model = Invoice
        fields = [
            'id', 'customer', 'customer_name', 'invoice_number', 'date_issued', 
            'due_date', 'status', 'is_recurring', 'subtotal', 'tax_total', 'total_amount', 
            'notes', 'created_at', 'lines', 'auto_post', 'journal_entry'
        ]
        read_only_fields = ['subtotal', 'tax_total', 'total_amount', 'created_at', 'journal_entry']

    def create(self, validated_data):
        lines_data = validated_data.pop('lines')
        auto_post = validated_data.pop('auto_post', False)
        user = self.context.get('request').user if self.context.get('request') else None
        
        invoice = Invoice.objects.create(**validated_data)
        
        total = 0
        for line_data in lines_data:
            line_data['amount'] = line_data['quantity'] * line_data['unit_price']
            total += line_data['amount']
            InvoiceLine.objects.create(invoice=invoice, **line_data)
        
        invoice.total_amount = total
        invoice.subtotal = total
        invoice.save()
        
        # Auto-post if requested and status is DRAFT (not PROFORMA)
        if auto_post and invoice.status == 'DRAFT':
            try:
                invoice = InvoiceService.post_invoice(invoice, user=user)
            except Exception as e:
                # Log error but don't fail the invoice creation
                import logging
                logging.warning(f"Auto-post failed for invoice {invoice.invoice_number}: {e}")
        
        return invoice

    def update(self, instance, validated_data):
        lines_data = validated_data.pop('lines', None)
        validated_data.pop('auto_post', None)  # Remove if present
        
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
