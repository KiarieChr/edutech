"""
Accounts Payable Views

API ViewSets for:
- Supplier management
- Supplier Invoices with approval/posting
- Payment Vouchers with approval workflow
- Imprest Retirement
- Approval Thresholds
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Sum
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import (
    Vendor, Bill,  # Legacy
    Supplier, ApprovalThreshold, SupplierInvoice, SupplierInvoiceLine,
    PaymentVoucher, PaymentVoucherLine, VoucherApproval,
    ImprestRetirement, ImprestRetirementLine
)
from .serializers import (
    VendorSerializer, BillSerializer,  # Legacy
    SupplierListSerializer, SupplierDetailSerializer,
    ApprovalThresholdSerializer,
    SupplierInvoiceListSerializer, SupplierInvoiceDetailSerializer,
    PaymentVoucherListSerializer, PaymentVoucherDetailSerializer,
    VoucherApprovalActionSerializer,
    ImprestRetirementListSerializer, ImprestRetirementDetailSerializer
)
from .services import (
    SupplierInvoiceService,
    PaymentVoucherService,
    ImprestService
)


# =============================================================================
# SUPPLIER VIEWSET
# =============================================================================

class SupplierViewSet(viewsets.ModelViewSet):
    """
    API endpoint for supplier management.
    
    list:     GET    /api/payables/suppliers/
    create:   POST   /api/payables/suppliers/
    retrieve: GET    /api/payables/suppliers/{id}/
    update:   PUT    /api/payables/suppliers/{id}/
    partial:  PATCH  /api/payables/suppliers/{id}/
    delete:   DELETE /api/payables/suppliers/{id}/
    """
    queryset = Supplier.objects.select_related('ap_account').all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active', 'vat_registered', 'payment_terms']
    search_fields = ['code', 'name', 'kra_pin', 'email']
    ordering_fields = ['name', 'code', 'created_at']
    ordering = ['name']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return SupplierListSerializer
        return SupplierDetailSerializer
    
    def perform_create(self, serializer):
        """Auto-populate ap_account from FinanceSettings if not provided."""
        from finance.models import FinanceSettings
        
        # Get ap_account from request data or use default from settings
        ap_account = serializer.validated_data.get('ap_account')
        if not ap_account:
            settings = FinanceSettings.load()
            ap_account = settings.default_payable_account
        
        serializer.save(
            ap_account=ap_account,
            created_by=self.request.user
        )
    
    @action(detail=True, methods=['get'])
    def outstanding(self, request, pk=None):
        """Get outstanding invoices for a supplier."""
        supplier = self.get_object()
        invoices = supplier.invoices.filter(
            status__in=['POSTED', 'APPROVED'],
            balance__gt=0
        ).order_by('due_date')
        
        serializer = SupplierInvoiceListSerializer(invoices, many=True)
        return Response({
            'supplier': supplier.name,
            'total_outstanding': sum(inv.balance for inv in invoices),
            'invoices': serializer.data
        })


# =============================================================================
# APPROVAL THRESHOLD VIEWSET
# =============================================================================

class ApprovalThresholdViewSet(viewsets.ModelViewSet):
    """
    API endpoint for approval threshold configuration.
    """
    queryset = ApprovalThreshold.objects.all()
    serializer_class = ApprovalThresholdSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['is_active']


# =============================================================================
# SUPPLIER INVOICE VIEWSET
# =============================================================================

class SupplierInvoiceViewSet(viewsets.ModelViewSet):
    """
    API endpoint for supplier invoices.
    
    Custom actions:
    - approve: POST /api/payables/supplier-invoices/{id}/approve/
    - post:    POST /api/payables/supplier-invoices/{id}/post/
    - void:    POST /api/payables/supplier-invoices/{id}/void/
    """
    queryset = SupplierInvoice.objects.select_related(
        'supplier', 'approved_by', 'posted_by', 'journal_entry'
    ).prefetch_related('lines').all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['supplier', 'status', 'source']
    search_fields = ['invoice_number', 'supplier__name', 'purchase_order_ref']
    ordering_fields = ['invoice_date', 'due_date', 'total_amount', 'created_at']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return SupplierInvoiceListSerializer
        return SupplierInvoiceDetailSerializer
    
    def create(self, request, *args, **kwargs):
        """Handle both JSON and multipart/form-data requests."""
        import json
        
        data = request.data.copy()
        
        # Handle FormData where lines is a JSON string
        if isinstance(data.get('lines'), str):
            try:
                data['lines'] = json.loads(data['lines'])
            except json.JSONDecodeError:
                return Response({'error': 'Invalid lines JSON'}, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a draft invoice."""
        invoice = self.get_object()
        try:
            invoice = SupplierInvoiceService.approve_invoice(invoice, request.user)
            serializer = self.get_serializer(invoice)
            return Response(serializer.data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def post(self, request, pk=None):
        """Post an approved invoice to the GL."""
        invoice = self.get_object()
        try:
            invoice = SupplierInvoiceService.post_invoice(invoice, request.user)
            serializer = self.get_serializer(invoice)
            return Response(serializer.data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def void(self, request, pk=None):
        """Void an invoice."""
        invoice = self.get_object()
        reason = request.data.get('reason', '')
        try:
            invoice = SupplierInvoiceService.void_invoice(invoice, request.user, reason)
            serializer = self.get_serializer(invoice)
            return Response(serializer.data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def overdue(self, request):
        """Get list of overdue invoices."""
        from django.utils import timezone
        today = timezone.now().date()
        
        invoices = self.get_queryset().filter(
            status__in=['POSTED', 'APPROVED'],
            due_date__lt=today,
            balance__gt=0
        ).order_by('due_date')
        
        serializer = SupplierInvoiceListSerializer(invoices, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def aging(self, request):
        """Get AP aging report."""
        from django.utils import timezone
        from datetime import timedelta
        
        today = timezone.now().date()
        
        # Define aging buckets
        buckets = {
            'current': (0, 30),
            '31_60': (31, 60),
            '61_90': (61, 90),
            'over_90': (91, 9999)
        }
        
        result = {}
        for bucket_name, (min_days, max_days) in buckets.items():
            start_date = today - timedelta(days=max_days)
            end_date = today - timedelta(days=min_days)
            
            total = SupplierInvoice.objects.filter(
                status__in=['POSTED', 'APPROVED'],
                balance__gt=0,
                invoice_date__range=[start_date, end_date]
            ).aggregate(total=Sum('balance'))['total'] or 0
            
            result[bucket_name] = total
        
        result['total'] = sum(result.values())
        return Response(result)


# =============================================================================
# PAYMENT VOUCHER VIEWSET
# =============================================================================

class PaymentVoucherViewSet(viewsets.ModelViewSet):
    """
    API endpoint for payment vouchers.
    
    Custom actions:
    - approve:          POST /api/payables/payment-vouchers/{id}/approve/
    - pay:              POST /api/payables/payment-vouchers/{id}/pay/
    - void:             POST /api/payables/payment-vouchers/{id}/void/
    - pending_approval: GET  /api/payables/payment-vouchers/pending_approval/
    """
    queryset = PaymentVoucher.objects.select_related(
        'supplier_invoice', 'supplier_invoice__supplier',
        'staff_member', 'bank_account', 'imprest_account',
        'prepared_by', 'paid_by', 'journal_entry'
    ).prefetch_related('lines', 'approvals').all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['voucher_type', 'status', 'payment_method']
    search_fields = ['voucher_number', 'payee_name', 'description', 'cheque_number']
    ordering_fields = ['payment_date', 'amount', 'created_at']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return PaymentVoucherListSerializer
        return PaymentVoucherDetailSerializer
    
    def perform_create(self, serializer):
        """Create voucher using service for proper approval chain setup."""
        from .services import PaymentVoucherService
        
        data = serializer.validated_data.copy()
        data['lines'] = serializer.initial_data.get('lines', [])
        
        voucher = PaymentVoucherService.create_voucher(data, self.request.user)
        # Return the voucher to be serialized
        serializer.instance = voucher
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Process approval decision."""
        voucher = self.get_object()
        serializer = VoucherApprovalActionSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            voucher = PaymentVoucherService.process_approval(
                voucher,
                request.user,
                serializer.validated_data['decision'],
                serializer.validated_data.get('comments')
            )
            return Response(PaymentVoucherDetailSerializer(voucher).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def pay(self, request, pk=None):
        """Post payment to GL."""
        voucher = self.get_object()
        try:
            voucher = PaymentVoucherService.post_payment(voucher, request.user)
            return Response(PaymentVoucherDetailSerializer(voucher).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def void(self, request, pk=None):
        """Void voucher."""
        voucher = self.get_object()
        reason = request.data.get('reason', '')
        try:
            voucher = PaymentVoucherService.void_voucher(voucher, request.user, reason)
            return Response(PaymentVoucherDetailSerializer(voucher).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def pending_approval(self, request):
        """Get vouchers pending the current user's approval."""
        user_roles = [g.name.upper() for g in request.user.groups.all()]
        
        # Find vouchers where next approval role matches user's roles
        vouchers = self.get_queryset().filter(status='PENDING_APPROVAL')
        
        # Filter by approval chain
        pending = []
        for voucher in vouchers:
            next_role = voucher.next_approval_role
            if next_role and next_role.upper() in user_roles:
                pending.append(voucher)
        
        serializer = PaymentVoucherListSerializer(pending, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def by_type(self, request):
        """Get voucher count and amount summary by type."""
        from django.db.models import Count
        
        result = PaymentVoucher.objects.values('voucher_type').annotate(
            count=Count('id'),
            total_amount=Sum('amount')
        ).order_by('voucher_type')
        
        return Response(list(result))


# =============================================================================
# IMPREST RETIREMENT VIEWSET
# =============================================================================

class ImprestRetirementViewSet(viewsets.ModelViewSet):
    """
    API endpoint for imprest retirements.
    
    Custom actions:
    - approve: POST /api/payables/imprest-retirements/{id}/approve/
    - post:    POST /api/payables/imprest-retirements/{id}/post/
    """
    queryset = ImprestRetirement.objects.select_related(
        'voucher', 'voucher__staff_member',
        'submitted_by', 'approved_by', 'posted_by', 'journal_entry'
    ).prefetch_related('lines').all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status']
    search_fields = ['voucher__voucher_number', 'voucher__staff_member__first_name']
    ordering_fields = ['retirement_date', 'created_at']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return ImprestRetirementListSerializer
        return ImprestRetirementDetailSerializer
    
    def perform_create(self, serializer):
        """Create retirement using service."""
        voucher_id = serializer.validated_data.get('voucher').id
        voucher = PaymentVoucher.objects.get(id=voucher_id)
        
        data = {
            'retirement_date': serializer.validated_data.get('retirement_date'),
            'surrender_amount': serializer.validated_data.get('surrender_amount', 0),
            'notes': serializer.validated_data.get('notes', ''),
            'lines': serializer.initial_data.get('lines', [])
        }
        
        retirement = ImprestService.submit_retirement(voucher, data, self.request.user)
        serializer.instance = retirement
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a submitted retirement."""
        retirement = self.get_object()
        try:
            retirement = ImprestService.approve_retirement(retirement, request.user)
            return Response(ImprestRetirementDetailSerializer(retirement).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def post(self, request, pk=None):
        """Post approved retirement to GL."""
        retirement = self.get_object()
        try:
            retirement = ImprestService.post_retirement(retirement, request.user)
            return Response(ImprestRetirementDetailSerializer(retirement).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def pending(self, request):
        """Get retirements pending approval or posting."""
        retirements = self.get_queryset().filter(
            status__in=['SUBMITTED', 'APPROVED']
        ).order_by('retirement_date')
        
        serializer = ImprestRetirementListSerializer(retirements, many=True)
        return Response(serializer.data)


# =============================================================================
# LEGACY VIEWSETS (kept for backward compatibility)
# =============================================================================

class VendorViewSet(viewsets.ModelViewSet):
    """Legacy Vendor ViewSet."""
    queryset = Vendor.objects.all()
    serializer_class = VendorSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['name', 'email', 'tax_id']
    ordering = ['name']


class BillViewSet(viewsets.ModelViewSet):
    """Legacy Bill ViewSet."""
    queryset = Bill.objects.select_related('vendor').prefetch_related('lines').all()
    serializer_class = BillSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['vendor', 'status']
    search_fields = ['bill_number', 'vendor__name', 'notes']
    ordering = ['-date_received']
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
