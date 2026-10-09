from .views import AccountViewSet, TaxViewSet, FinanceSettingsView, FiscalPeriodViewSet, CashbookViewSet, PaymentMethodViewSet, SponsorTypeViewSet, SponsorshipViewSet, AdmissionFeeTemplateViewSet, AdmissionFeeItemViewSet
from rest_framework.routers import DefaultRouter
from django.urls import path, include

router = DefaultRouter()
router.register(r'accounts', AccountViewSet)
router.register(r'taxes', TaxViewSet)
router.register(r'fiscal-periods', FiscalPeriodViewSet)
router.register(r'cashbooks', CashbookViewSet)
router.register(r'payment-methods', PaymentMethodViewSet)
router.register(r'settings', FinanceSettingsView, basename='finance-settings')
router.register(r'sponsor-types', SponsorTypeViewSet, basename='sponsor-types')
router.register(r'sponsorships', SponsorshipViewSet, basename='sponsorships')
router.register(r'admission-fee-templates', AdmissionFeeTemplateViewSet, basename='admission-fee-templates')
router.register(r'admission-fee-items', AdmissionFeeItemViewSet, basename='admission-fee-items')

urlpatterns = [
    path('', include(router.urls)),
]
