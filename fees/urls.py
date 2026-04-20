from django.urls import path, include
from rest_framework.routers import DefaultRouter
from fees.views import FeeStructureViewSet, FeeItemViewSet, FeeInvoiceViewSet, PaymentMethodViewSet, BillingViewSet, fee_insights
from .arrears_views import ArrearsViewSet
from .receipt_views import ReceiptViewSet
from .template_views import (
    VoteHeadViewSet, GradeBandViewSet, FeeTemplateViewSet,
    TemplateLineItemViewSet, StudentFeeProfileViewSet,
    fee_rollover,
)

router = DefaultRouter()
router.register(r'fee-structures', FeeStructureViewSet, basename='fee-structure')
router.register(r'fee-items', FeeItemViewSet, basename='fee-item')
router.register(r'invoices', FeeInvoiceViewSet, basename='invoice')
router.register(r'payment-methods', PaymentMethodViewSet, basename='payment-method')
router.register(r'billing', BillingViewSet, basename='billing')
router.register(r'arrears', ArrearsViewSet, basename='arrears')
router.register(r'receipts', ReceiptViewSet, basename='receipts')

# Template architecture endpoints
router.register(r'vote-heads', VoteHeadViewSet, basename='vote-head')
router.register(r'grade-bands', GradeBandViewSet, basename='grade-band')
router.register(r'fee-templates', FeeTemplateViewSet, basename='fee-template')
router.register(r'template-line-items', TemplateLineItemViewSet, basename='template-line-item')
router.register(r'student-fee-profiles', StudentFeeProfileViewSet, basename='student-fee-profile')

urlpatterns = [
    path('', include(router.urls)),
    path('insights/', fee_insights, name='fee-insights'),
    path('rollover/', fee_rollover, name='fee-rollover'),
]
