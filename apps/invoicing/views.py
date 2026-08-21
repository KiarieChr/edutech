from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .models import Customer, Invoice
from .serializers import CustomerSerializer, InvoiceSerializer
from .services import InvoiceService

class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['name', 'email', 'tax_id']
    ordering = ['name']

class InvoiceViewSet(viewsets.ModelViewSet):
    queryset = Invoice.objects.select_related('customer', 'journal_entry').prefetch_related('lines').all()
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['customer', 'status', 'is_recurring']
    search_fields = ['invoice_number', 'customer__name', 'notes']
    ordering = ['-date_issued']
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def post_to_ledger(self, request, pk=None):
        """Manually post a DRAFT invoice to the General Ledger."""
        invoice = self.get_object()
        try:
            invoice = InvoiceService.post_invoice(invoice, user=request.user)
            return Response(InvoiceSerializer(invoice, context={'request': request}).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def void(self, request, pk=None):
        """Void an invoice."""
        invoice = self.get_object()
        if invoice.status == 'PAID':
            return Response({'error': 'Cannot void a paid invoice'}, status=status.HTTP_400_BAD_REQUEST)
        
        invoice.status = 'VOID'
        invoice.save()
        return Response(InvoiceSerializer(invoice, context={'request': request}).data)
    
    @action(detail=True, methods=['post'])
    def issue(self, request, pk=None):
        """Convert a PROFORMA invoice to ISSUED status so it can be posted."""
        invoice = self.get_object()
        if invoice.status != 'PROFORMA':
            return Response({'error': 'Only PROFORMA invoices can be issued'}, status=status.HTTP_400_BAD_REQUEST)
        
        invoice.status = 'ISSUED'
        invoice.save()
        return Response(InvoiceSerializer(invoice, context={'request': request}).data)
