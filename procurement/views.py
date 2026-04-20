from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import (
    PurchaseRequisition, RequisitionLine,
    RequestForQuotation, RFQLine, RFQSupplierInvitation,
    SupplierQuotation, SupplierQuotationLine,
    PurchaseOrder, PurchaseOrderLine,
    SupplierContract, ContractMilestone,
)
from .serializers import (
    PurchaseRequisitionListSerializer, PurchaseRequisitionDetailSerializer,
    PurchaseRequisitionCreateSerializer, RequisitionLineSerializer,
    RFQListSerializer, RFQDetailSerializer, RFQCreateSerializer,
    RFQSupplierInvitationSerializer,
    SupplierQuotationSerializer, SupplierQuotationLineSerializer,
    PublicQuotationSubmitSerializer,
    PurchaseOrderListSerializer, PurchaseOrderDetailSerializer,
    PurchaseOrderCreateSerializer, PurchaseOrderLineSerializer,
    SupplierContractListSerializer, SupplierContractDetailSerializer,
    SupplierContractCreateSerializer, ContractMilestoneSerializer,
)


# =============================================================================
# PURCHASE REQUISITION
# =============================================================================

class PurchaseRequisitionViewSet(viewsets.ModelViewSet):
    queryset = PurchaseRequisition.objects.select_related(
        'requested_by', 'approved_by', 'suggested_supplier'
    ).prefetch_related('lines')
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'priority', 'department', 'requested_by']
    search_fields = ['requisition_number', 'justification', 'notes']
    ordering_fields = ['created_at', 'date_needed', 'priority']

    def get_serializer_class(self):
        if self.action == 'list':
            return PurchaseRequisitionListSerializer
        if self.action in ('create', 'update', 'partial_update'):
            return PurchaseRequisitionCreateSerializer
        return PurchaseRequisitionDetailSerializer

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        req = self.get_object()
        if req.status != 'DRAFT':
            return Response({'detail': 'Only draft requisitions can be submitted.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if not req.lines.exists():
            return Response({'detail': 'Add at least one line item before submitting.'},
                            status=status.HTTP_400_BAD_REQUEST)
        req.status = 'SUBMITTED'
        req.save(update_fields=['status'])
        return Response(PurchaseRequisitionDetailSerializer(req).data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        req = self.get_object()
        if req.status != 'SUBMITTED':
            return Response({'detail': 'Only submitted requisitions can be approved.'},
                            status=status.HTTP_400_BAD_REQUEST)
        req.status = 'APPROVED'
        req.approved_by = request.user
        req.approved_at = timezone.now()
        req.save(update_fields=['status', 'approved_by', 'approved_at'])
        return Response(PurchaseRequisitionDetailSerializer(req).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        req = self.get_object()
        if req.status != 'SUBMITTED':
            return Response({'detail': 'Only submitted requisitions can be rejected.'},
                            status=status.HTTP_400_BAD_REQUEST)
        req.status = 'REJECTED'
        req.approved_by = request.user
        req.approved_at = timezone.now()
        req.rejection_reason = request.data.get('reason', '')
        req.save(update_fields=['status', 'approved_by', 'approved_at', 'rejection_reason'])
        return Response(PurchaseRequisitionDetailSerializer(req).data)

    @action(detail=True, methods=['post'])
    def convert_to_po(self, request, pk=None):
        """Create a Purchase Order from an approved requisition."""
        req = self.get_object()
        if req.status != 'APPROVED':
            return Response({'detail': 'Only approved requisitions can be converted to PO.'},
                            status=status.HTTP_400_BAD_REQUEST)
        supplier_id = request.data.get('supplier_id') or (
            req.suggested_supplier_id
        )
        if not supplier_id:
            return Response({'detail': 'Supplier is required to create a PO.'},
                            status=status.HTTP_400_BAD_REQUEST)

        po = PurchaseOrder.objects.create(
            supplier_id=supplier_id,
            requisition=req,
            budget_line=req.budget_line,
            created_by=request.user,
            notes=f"Created from {req.requisition_number}",
        )
        for line in req.lines.all():
            PurchaseOrderLine.objects.create(
                purchase_order=po,
                item=line.item,
                description=line.description,
                quantity=line.quantity,
                unit_of_measure=line.unit_of_measure,
                unit_price=line.estimated_unit_cost,
            )
        po.recalculate_totals()
        req.status = 'CONVERTED'
        req.save(update_fields=['status'])
        return Response(PurchaseOrderDetailSerializer(po).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        qs = self.get_queryset()
        return Response({
            'total': qs.count(),
            'draft': qs.filter(status='DRAFT').count(),
            'submitted': qs.filter(status='SUBMITTED').count(),
            'approved': qs.filter(status='APPROVED').count(),
            'rejected': qs.filter(status='REJECTED').count(),
            'converted': qs.filter(status='CONVERTED').count(),
        })


class RequisitionLineViewSet(viewsets.ModelViewSet):
    serializer_class = RequisitionLineSerializer

    def get_queryset(self):
        return RequisitionLine.objects.filter(
            requisition_id=self.kwargs['requisition_pk']
        )

    def perform_create(self, serializer):
        serializer.save(requisition_id=self.kwargs['requisition_pk'])


# =============================================================================
# RFQ
# =============================================================================

class RFQViewSet(viewsets.ModelViewSet):
    queryset = RequestForQuotation.objects.select_related(
        'requisition', 'created_by'
    ).prefetch_related('lines', 'invitations')
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status']
    search_fields = ['rfq_number', 'title', 'description']
    ordering_fields = ['created_at', 'deadline']

    def get_serializer_class(self):
        if self.action == 'list':
            return RFQListSerializer
        if self.action in ('create', 'update', 'partial_update'):
            return RFQCreateSerializer
        return RFQDetailSerializer

    @action(detail=True, methods=['post'])
    def send_to_suppliers(self, request, pk=None):
        rfq = self.get_object()
        if rfq.status != 'DRAFT':
            return Response({'detail': 'Only draft RFQs can be sent.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if not rfq.invitations.exists():
            return Response({'detail': 'Add at least one supplier before sending.'},
                            status=status.HTTP_400_BAD_REQUEST)
        rfq.status = 'SENT'
        rfq.save(update_fields=['status'])
        return Response(RFQDetailSerializer(rfq).data)

    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        rfq = self.get_object()
        if rfq.status != 'SENT':
            return Response({'detail': 'Only sent RFQs can be closed.'},
                            status=status.HTTP_400_BAD_REQUEST)
        rfq.status = 'CLOSED'
        rfq.save(update_fields=['status'])
        return Response(RFQDetailSerializer(rfq).data)

    @action(detail=True, methods=['post'])
    def add_supplier(self, request, pk=None):
        rfq = self.get_object()
        supplier_id = request.data.get('supplier_id')
        if not supplier_id:
            return Response({'detail': 'supplier_id is required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if rfq.invitations.filter(supplier_id=supplier_id).exists():
            return Response({'detail': 'Supplier already invited.'},
                            status=status.HTTP_400_BAD_REQUEST)
        invitation = RFQSupplierInvitation.objects.create(
            rfq=rfq, supplier_id=supplier_id
        )
        return Response(RFQSupplierInvitationSerializer(invitation).data,
                        status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def quotations(self, request, pk=None):
        rfq = self.get_object()
        quotes = SupplierQuotation.objects.filter(
            invitation__rfq=rfq
        ).select_related('invitation__supplier').prefetch_related('lines')
        return Response(SupplierQuotationSerializer(quotes, many=True).data)

    @action(detail=True, methods=['post'])
    def award(self, request, pk=None):
        """Award the RFQ to a specific quotation and optionally create a PO."""
        rfq = self.get_object()
        quotation_id = request.data.get('quotation_id')
        if not quotation_id:
            return Response({'detail': 'quotation_id is required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            quote = SupplierQuotation.objects.get(id=quotation_id, invitation__rfq=rfq)
        except SupplierQuotation.DoesNotExist:
            return Response({'detail': 'Quotation not found for this RFQ.'},
                            status=status.HTTP_404_NOT_FOUND)

        # Mark this quote as selected, others as rejected
        SupplierQuotation.objects.filter(invitation__rfq=rfq).exclude(id=quotation_id).update(
            status='REJECTED', reviewed_at=timezone.now(), reviewed_by=request.user
        )
        quote.status = 'SELECTED'
        quote.reviewed_at = timezone.now()
        quote.reviewed_by = request.user
        quote.save(update_fields=['status', 'reviewed_at', 'reviewed_by'])

        rfq.status = 'AWARDED'
        rfq.save(update_fields=['status'])

        # Create PO if requested
        create_po = request.data.get('create_po', True)
        po_data = None
        if create_po:
            po = PurchaseOrder.objects.create(
                supplier=quote.supplier,
                requisition=rfq.requisition,
                rfq=rfq,
                quotation=quote,
                currency=quote.currency,
                payment_terms=quote.payment_terms or '',
                created_by=request.user,
                notes=f"Created from RFQ {rfq.rfq_number}",
            )
            for qline in quote.lines.all():
                PurchaseOrderLine.objects.create(
                    purchase_order=po,
                    description=qline.description,
                    quantity=qline.quantity,
                    unit_price=qline.unit_price,
                    vat_rate=qline.vat_rate,
                )
            po.recalculate_totals()
            po_data = PurchaseOrderDetailSerializer(po).data

        return Response({
            'rfq': RFQDetailSerializer(rfq).data,
            'quotation': SupplierQuotationSerializer(quote).data,
            'purchase_order': po_data,
        })


# =============================================================================
# PUBLIC QUOTATION SUBMISSION (No auth required)
# =============================================================================

@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def public_rfq_detail(request, token):
    """Public view for a supplier to see the RFQ details via their unique token."""
    invitation = get_object_or_404(
        RFQSupplierInvitation.objects.select_related('rfq', 'supplier'),
        token=token
    )
    # Mark as viewed
    if not invitation.viewed_at:
        invitation.viewed_at = timezone.now()
        invitation.save(update_fields=['viewed_at'])

    rfq = invitation.rfq
    if rfq.status not in ('SENT', 'CLOSED'):
        return Response({'detail': 'This RFQ is not currently accepting quotations.'},
                        status=status.HTTP_403_FORBIDDEN)

    # Check if already submitted
    existing = hasattr(invitation, 'quotation')

    lines = [{
        'id': l.id,
        'description': l.description,
        'specification': l.specification,
        'quantity': str(l.quantity),
        'unit_of_measure': l.unit_of_measure,
    } for l in rfq.lines.all()]

    return Response({
        'rfq_number': rfq.rfq_number,
        'title': rfq.title,
        'description': rfq.description,
        'deadline': rfq.deadline,
        'terms_and_conditions': rfq.terms_and_conditions,
        'supplier_name': invitation.supplier.name,
        'lines': lines,
        'already_submitted': existing,
        'existing_quotation': SupplierQuotationSerializer(invitation.quotation).data if existing else None,
    })


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def public_quotation_submit(request, token):
    """Public endpoint for a supplier to submit their quotation."""
    invitation = get_object_or_404(RFQSupplierInvitation, token=token)
    rfq = invitation.rfq

    if rfq.status not in ('SENT',):
        return Response({'detail': 'This RFQ is no longer accepting quotations.'},
                        status=status.HTTP_403_FORBIDDEN)

    if rfq.is_past_deadline:
        return Response({'detail': 'The submission deadline has passed.'},
                        status=status.HTTP_403_FORBIDDEN)

    if hasattr(invitation, 'quotation'):
        return Response({'detail': 'You have already submitted a quotation for this RFQ.'},
                        status=status.HTTP_400_BAD_REQUEST)

    serializer = PublicQuotationSubmitSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    lines_data = data.pop('lines', [])

    quote = SupplierQuotation.objects.create(
        invitation=invitation,
        quotation_reference=data.get('quotation_reference', ''),
        delivery_period=data.get('delivery_period', ''),
        payment_terms=data.get('payment_terms', ''),
        validity_days=data.get('validity_days', 30),
        notes=data.get('notes', ''),
        document=data.get('document'),
    )

    total = 0
    for line_data in lines_data:
        line = SupplierQuotationLine.objects.create(
            quotation=quote,
            rfq_line_id=line_data.get('rfq_line'),
            description=line_data['description'],
            quantity=line_data['quantity'],
            unit_price=line_data['unit_price'],
            vat_rate=line_data.get('vat_rate', 16),
        )
        total += line.total_with_vat

    quote.total_amount = total
    quote.save(update_fields=['total_amount'])

    return Response(
        SupplierQuotationSerializer(quote).data,
        status=status.HTTP_201_CREATED
    )


# =============================================================================
# SUPPLIER QUOTATION (Internal management)
# =============================================================================

class SupplierQuotationViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only internal view of all quotations. Submissions happen via public link."""
    queryset = SupplierQuotation.objects.select_related(
        'invitation__supplier', 'invitation__rfq', 'reviewed_by'
    ).prefetch_related('lines')
    serializer_class = SupplierQuotationSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['status']
    search_fields = ['quotation_reference', 'invitation__supplier__name']

    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        quote = self.get_object()
        new_status = request.data.get('status')
        if new_status not in ('UNDER_REVIEW', 'SELECTED', 'REJECTED'):
            return Response({'detail': 'Invalid status.'}, status=status.HTTP_400_BAD_REQUEST)
        quote.status = new_status
        quote.reviewed_at = timezone.now()
        quote.reviewed_by = request.user
        quote.save(update_fields=['status', 'reviewed_at', 'reviewed_by'])
        return Response(SupplierQuotationSerializer(quote).data)


# =============================================================================
# PURCHASE ORDER
# =============================================================================

class PurchaseOrderViewSet(viewsets.ModelViewSet):
    queryset = PurchaseOrder.objects.select_related(
        'supplier', 'requisition', 'rfq', 'quotation', 'contract',
        'approved_by', 'created_by'
    ).prefetch_related('lines')
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'supplier']
    search_fields = ['po_number', 'notes']
    ordering_fields = ['created_at', 'order_date', 'total_amount']

    def get_serializer_class(self):
        if self.action == 'list':
            return PurchaseOrderListSerializer
        if self.action in ('create', 'update', 'partial_update'):
            return PurchaseOrderCreateSerializer
        return PurchaseOrderDetailSerializer

    @action(detail=True, methods=['post'])
    def submit_for_approval(self, request, pk=None):
        po = self.get_object()
        if po.status != 'DRAFT':
            return Response({'detail': 'Only draft POs can be submitted.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if not po.lines.exists():
            return Response({'detail': 'Add at least one line item.'},
                            status=status.HTTP_400_BAD_REQUEST)
        po.status = 'PENDING_APPROVAL'
        po.save(update_fields=['status'])
        return Response(PurchaseOrderDetailSerializer(po).data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        po = self.get_object()
        if po.status != 'PENDING_APPROVAL':
            return Response({'detail': 'Only pending POs can be approved.'},
                            status=status.HTTP_400_BAD_REQUEST)
        po.status = 'APPROVED'
        po.approved_by = request.user
        po.approved_at = timezone.now()
        po.save(update_fields=['status', 'approved_by', 'approved_at'])
        return Response(PurchaseOrderDetailSerializer(po).data)

    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        po = self.get_object()
        if po.status != 'APPROVED':
            return Response({'detail': 'Only approved POs can be sent.'},
                            status=status.HTTP_400_BAD_REQUEST)
        po.status = 'SENT'
        po.save(update_fields=['status'])
        return Response(PurchaseOrderDetailSerializer(po).data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        po = self.get_object()
        if po.status in ('FULLY_RECEIVED', 'CLOSED'):
            return Response({'detail': 'Cannot cancel a received/closed PO.'},
                            status=status.HTTP_400_BAD_REQUEST)
        po.status = 'CANCELLED'
        po.save(update_fields=['status'])
        return Response(PurchaseOrderDetailSerializer(po).data)

    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        po = self.get_object()
        po.status = 'CLOSED'
        po.save(update_fields=['status'])
        return Response(PurchaseOrderDetailSerializer(po).data)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        qs = self.get_queryset()
        from django.db.models import Sum
        totals = qs.exclude(status='CANCELLED').aggregate(
            total_value=Sum('total_amount')
        )
        return Response({
            'total': qs.count(),
            'draft': qs.filter(status='DRAFT').count(),
            'pending_approval': qs.filter(status='PENDING_APPROVAL').count(),
            'approved': qs.filter(status='APPROVED').count(),
            'sent': qs.filter(status='SENT').count(),
            'partially_received': qs.filter(status='PARTIALLY_RECEIVED').count(),
            'fully_received': qs.filter(status='FULLY_RECEIVED').count(),
            'closed': qs.filter(status='CLOSED').count(),
            'cancelled': qs.filter(status='CANCELLED').count(),
            'total_value': totals['total_value'] or 0,
        })


class PurchaseOrderLineViewSet(viewsets.ModelViewSet):
    serializer_class = PurchaseOrderLineSerializer

    def get_queryset(self):
        return PurchaseOrderLine.objects.filter(
            purchase_order_id=self.kwargs['po_pk']
        )

    def perform_create(self, serializer):
        line = serializer.save(purchase_order_id=self.kwargs['po_pk'])
        line.purchase_order.recalculate_totals()

    def perform_destroy(self, instance):
        po = instance.purchase_order
        instance.delete()
        po.recalculate_totals()


# =============================================================================
# SUPPLIER CONTRACT
# =============================================================================

class SupplierContractViewSet(viewsets.ModelViewSet):
    queryset = SupplierContract.objects.select_related(
        'supplier', 'created_by'
    ).prefetch_related('milestones')
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'contract_type', 'supplier']
    search_fields = ['contract_number', 'title', 'description']
    ordering_fields = ['created_at', 'end_date', 'contract_value']
    parser_classes = [MultiPartParser, FormParser]

    def get_serializer_class(self):
        if self.action == 'list':
            return SupplierContractListSerializer
        if self.action in ('create', 'update', 'partial_update'):
            return SupplierContractCreateSerializer
        return SupplierContractDetailSerializer

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        contract = self.get_object()
        if contract.status != 'DRAFT':
            return Response({'detail': 'Only draft contracts can be activated.'},
                            status=status.HTTP_400_BAD_REQUEST)
        contract.status = 'ACTIVE'
        contract.save(update_fields=['status'])
        return Response(SupplierContractDetailSerializer(contract).data)

    @action(detail=True, methods=['post'])
    def terminate(self, request, pk=None):
        contract = self.get_object()
        contract.status = 'TERMINATED'
        contract.save(update_fields=['status'])
        return Response(SupplierContractDetailSerializer(contract).data)

    @action(detail=True, methods=['post'])
    def renew(self, request, pk=None):
        contract = self.get_object()
        new_end = request.data.get('new_end_date')
        if not new_end:
            return Response({'detail': 'new_end_date is required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        contract.status = 'RENEWED'
        contract.save(update_fields=['status'])
        # Create renewed contract
        new_contract = SupplierContract.objects.create(
            title=f"{contract.title} (Renewed)",
            supplier=contract.supplier,
            contract_type=contract.contract_type,
            start_date=contract.end_date,
            end_date=new_end,
            contract_value=contract.contract_value,
            currency=contract.currency,
            terms_and_conditions=contract.terms_and_conditions,
            description=contract.description,
            renewal_reminder_days=contract.renewal_reminder_days,
            created_by=request.user,
        )
        return Response(SupplierContractDetailSerializer(new_contract).data,
                        status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'])
    def expiring_soon(self, request):
        """Contracts needing renewal attention."""
        contracts = self.get_queryset().filter(status='ACTIVE')
        expiring = [c for c in contracts if c.needs_renewal_reminder]
        return Response(SupplierContractListSerializer(expiring, many=True).data)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        qs = self.get_queryset()
        from django.db.models import Sum
        return Response({
            'total': qs.count(),
            'active': qs.filter(status='ACTIVE').count(),
            'draft': qs.filter(status='DRAFT').count(),
            'expired': qs.filter(status='EXPIRED').count(),
            'total_value': qs.filter(status='ACTIVE').aggregate(
                v=Sum('contract_value'))['v'] or 0,
        })


class ContractMilestoneViewSet(viewsets.ModelViewSet):
    serializer_class = ContractMilestoneSerializer

    def get_queryset(self):
        return ContractMilestone.objects.filter(
            contract_id=self.kwargs['contract_pk']
        )

    def perform_create(self, serializer):
        serializer.save(contract_id=self.kwargs['contract_pk'])

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None, contract_pk=None):
        milestone = self.get_object()
        milestone.status = 'COMPLETED'
        milestone.completed_at = timezone.now()
        milestone.save(update_fields=['status', 'completed_at'])
        return Response(ContractMilestoneSerializer(milestone).data)
