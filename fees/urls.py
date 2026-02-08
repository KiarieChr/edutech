from django.urls import path, include
from rest_framework.routers import DefaultRouter
from fees.views import FeeStructureViewSet, FeeItemViewSet, FeeInvoiceViewSet, PaymentMethodViewSet, BillingViewSet
from .arrears_views import ArrearsViewSet
from .receipt_views import ReceiptViewSet

router = DefaultRouter()
router.register(r'fee-structures', FeeStructureViewSet, basename='fee-structure')
router.register(r'fee-items', FeeItemViewSet, basename='fee-item')
router.register(r'invoices', FeeInvoiceViewSet, basename='invoice')
router.register(r'payment-methods', PaymentMethodViewSet, basename='payment-method')
router.register(r'billing', BillingViewSet, basename='billing')
router.register(r'arrears', ArrearsViewSet, basename='arrears')
router.register(r'receipts', ReceiptViewSet, basename='receipts')

urlpatterns = [
    path('', include(router.urls)),
]
