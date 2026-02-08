from rest_framework import viewsets
from .models import Customer, Invoice
from .serializers import CustomerSerializer, InvoiceSerializer

class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer

class InvoiceViewSet(viewsets.ModelViewSet):
    queryset = Invoice.objects.all()
    serializer_class = InvoiceSerializer
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
