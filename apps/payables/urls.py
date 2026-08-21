"""
Accounts Payable URL Configuration

Routes for:
- /suppliers/              - Supplier management
- /approval-thresholds/    - Approval threshold configuration
- /supplier-invoices/      - Supplier invoice management
- /payment-vouchers/       - Payment voucher management
- /imprest-retirements/    - Imprest retirement management
- /vendors/                - Legacy vendor endpoint
- /bills/                  - Legacy bill endpoint
"""

from rest_framework.routers import DefaultRouter
from .views import (
    VendorViewSet, BillViewSet,  # Legacy
    SupplierViewSet,
    ApprovalThresholdViewSet,
    SupplierInvoiceViewSet,
    PaymentVoucherViewSet,
    ImprestRetirementViewSet
)

router = DefaultRouter()

# New endpoints
router.register(r'suppliers', SupplierViewSet, basename='supplier')
router.register(r'approval-thresholds', ApprovalThresholdViewSet, basename='approval-threshold')
router.register(r'supplier-invoices', SupplierInvoiceViewSet, basename='supplier-invoice')
router.register(r'payment-vouchers', PaymentVoucherViewSet, basename='payment-voucher')
router.register(r'imprest-retirements', ImprestRetirementViewSet, basename='imprest-retirement')

# Legacy endpoints (kept for backward compatibility)
router.register(r'vendors', VendorViewSet, basename='vendor')
router.register(r'bills', BillViewSet, basename='bill')

urlpatterns = router.urls
