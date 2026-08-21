"""
Inventory Management Views

API ViewSets for:
- Categories
- Inventory Items (with stats, adjustments, movements, Excel upload/template)
- Goods Received Notes (with confirm and GL posting)
- Supply Issues (with approve and issue processing)
- Stock Takes (with reconciliation)
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.http import HttpResponse
from django.db.models import Q, Sum, Count, F
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from decimal import Decimal

from .models import (
    Category, InventoryItem, StockMovement,
    GoodsReceivedNote, GRNLine,
    SupplyIssue, SupplyIssueItem,
    StockTake, StockTakeLine
)
from .serializers import (
    CategorySerializer,
    InventoryItemListSerializer, InventoryItemDetailSerializer,
    StockMovementSerializer, StockAdjustmentSerializer,
    GRNListSerializer, GRNDetailSerializer,
    SupplyIssueListSerializer, SupplyIssueDetailSerializer,
    StockTakeListSerializer, StockTakeDetailSerializer
)
from .services import InventoryService


# =============================================================================
# CATEGORY VIEWSET
# =============================================================================

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # Small dataset
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['name', 'code']
    ordering = ['name']


# =============================================================================
# INVENTORY ITEM VIEWSET
# =============================================================================

class InventoryItemViewSet(viewsets.ModelViewSet):
    queryset = InventoryItem.objects.select_related(
        'category', 'supplier', 'gl_asset_account', 'gl_expense_account'
    ).all()
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category', 'item_type', 'status', 'supplier']
    search_fields = ['code', 'name', 'batch_number', 'barcode', 'location']
    ordering_fields = ['name', 'code', 'stock_quantity', 'unit_cost', 'created_at']
    ordering = ['name']

    def get_serializer_class(self):
        if self.action == 'list':
            return InventoryItemListSerializer
        return InventoryItemDetailSerializer

    # ----- Custom Actions -----

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Dashboard KPIs."""
        from django.utils import timezone
        today = timezone.now().date()

        items = InventoryItem.objects.filter(status='ACTIVE')
        all_items = InventoryItem.objects.all()

        total_items = all_items.count()
        total_stock_value = sum(i.stock_value for i in items)
        low_stock = items.filter(stock_quantity__lte=F('min_level')).count()
        out_of_stock = items.filter(stock_quantity=0).count()
        expired = items.filter(expiry_date__lt=today).count()
        capital_assets = items.filter(item_type='CAPITAL_ASSET').count()

        # Category breakdown
        categories = Category.objects.filter(is_active=True).annotate(
            item_count=Count('items'),
            total_value=Sum(F('items__stock_quantity') * F('items__unit_cost'))
        ).values('id', 'name', 'item_count', 'total_value')

        # Recent movements
        recent_movements = StockMovement.objects.select_related('item').order_by('-created_at')[:10]
        movement_data = StockMovementSerializer(recent_movements, many=True).data

        return Response({
            'total_items': total_items,
            'total_stock_value': str(total_stock_value),
            'low_stock': low_stock,
            'out_of_stock': out_of_stock,
            'expired': expired,
            'capital_assets': capital_assets,
            'categories': list(categories),
            'recent_movements': movement_data
        })

    @action(detail=True, methods=['post'])
    def adjust(self, request, pk=None):
        """Adjust stock for an item."""
        item = self.get_object()
        serializer = StockAdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            movement = InventoryService.adjust_stock(
                item=item,
                adjustment_type=serializer.validated_data['adjustment_type'],
                quantity=serializer.validated_data['quantity'],
                reason=serializer.validated_data['reason'],
                user=request.user,
                post_to_gl=serializer.validated_data.get('post_to_gl', False)
            )
            return Response(StockMovementSerializer(movement).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'])
    def movements(self, request, pk=None):
        """Get stock movement history for an item."""
        item = self.get_object()
        movements = StockMovement.objects.filter(item=item).order_by('-created_at')
        serializer = StockMovementSerializer(movements, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser])
    def upload(self, request):
        """Bulk upload inventory items from Excel."""
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)

        if not file.name.endswith(('.xlsx', '.xls')):
            return Response({'error': 'File must be .xlsx or .xls'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            results = InventoryService.upload_from_excel(file, request.user)
            return Response(results, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def download_template(self, request):
        """Download Excel template for bulk upload."""
        try:
            buffer = InventoryService.generate_upload_template()
            response = HttpResponse(
                buffer.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = 'attachment; filename="inventory_upload_template.xlsx"'
            return response
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# =============================================================================
# GRN VIEWSET
# =============================================================================

class GRNViewSet(viewsets.ModelViewSet):
    queryset = GoodsReceivedNote.objects.select_related(
        'supplier', 'received_by', 'journal_entry'
    ).prefetch_related('lines').all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['supplier', 'status']
    search_fields = ['grn_number', 'supplier__name']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return GRNListSerializer
        return GRNDetailSerializer

    def create(self, request, *args, **kwargs):
        """Handle nested lines creation."""
        import json
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        if hasattr(data, 'getlist'):
            data = request.data.dict()
        if isinstance(data.get('lines'), str):
            data['lines'] = json.loads(data['lines'])

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save(created_by=request.user, received_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        """Confirm GRN — adds stock and creates movements."""
        grn = self.get_object()
        try:
            grn = InventoryService.confirm_grn(grn, request.user)
            return Response(GRNDetailSerializer(grn).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def post_to_gl(self, request, pk=None):
        """Post confirmed GRN to General Ledger."""
        grn = self.get_object()
        try:
            grn = InventoryService.post_grn_to_gl(grn, request.user)
            return Response(GRNDetailSerializer(grn).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


# =============================================================================
# SUPPLY ISSUE VIEWSET
# =============================================================================

class SupplyIssueViewSet(viewsets.ModelViewSet):
    queryset = SupplyIssue.objects.select_related(
        'approved_by', 'budget_line', 'journal_entry'
    ).prefetch_related('items').all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['department', 'status']
    search_fields = ['issue_number', 'department', 'requested_by']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return SupplyIssueListSerializer
        return SupplyIssueDetailSerializer

    def create(self, request, *args, **kwargs):
        """Handle nested items creation."""
        import json
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        if hasattr(data, 'getlist'):
            data = request.data.dict()
        if isinstance(data.get('items'), str):
            data['items'] = json.loads(data['items'])

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save(created_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a pending supply issue."""
        issue = self.get_object()
        try:
            issue = InventoryService.approve_issue(issue, request.user)
            return Response(SupplyIssueDetailSerializer(issue).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def issue(self, request, pk=None):
        """Process an approved issue — deducts stock."""
        issue_obj = self.get_object()
        post_to_gl = request.data.get('post_to_gl', False)
        try:
            issue_obj = InventoryService.process_issue(issue_obj, request.user, post_to_gl=post_to_gl)
            return Response(SupplyIssueDetailSerializer(issue_obj).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


# =============================================================================
# STOCK TAKE VIEWSET
# =============================================================================

class StockTakeViewSet(viewsets.ModelViewSet):
    queryset = StockTake.objects.select_related('conducted_by').prefetch_related('lines').all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status']
    search_fields = ['reference']
    ordering = ['-date']

    def get_serializer_class(self):
        if self.action == 'list':
            return StockTakeListSerializer
        return StockTakeDetailSerializer

    def create(self, request, *args, **kwargs):
        """Handle nested lines creation."""
        import json
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        if hasattr(data, 'getlist'):
            data = request.data.dict()
        if isinstance(data.get('lines'), str):
            data['lines'] = json.loads(data['lines'])

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save(conducted_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def reconcile(self, request, pk=None):
        """Reconcile stock take — applies variances."""
        stock_take = self.get_object()
        post_to_gl = request.data.get('post_to_gl', False)
        try:
            stock_take = InventoryService.reconcile_stock_take(
                stock_take, request.user, post_to_gl=post_to_gl
            )
            return Response(StockTakeDetailSerializer(stock_take).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
