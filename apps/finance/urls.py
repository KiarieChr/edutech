from .views import AccountViewSet, TaxViewSet, FinanceSettingsView, FiscalPeriodViewSet, CashbookViewSet, PaymentMethodViewSet, SponsorTypeViewSet, SponsorshipViewSet
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

urlpatterns = [
    path('', include(router.urls)),
]
