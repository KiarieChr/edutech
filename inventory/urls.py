from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    CategoryViewSet,
    InventoryItemViewSet,
    GRNViewSet,
    SupplyIssueViewSet,
    StockTakeViewSet
)

router = DefaultRouter()
router.register(r'categories', CategoryViewSet)
router.register(r'items', InventoryItemViewSet)
router.register(r'grns', GRNViewSet)
router.register(r'issues', SupplyIssueViewSet)
router.register(r'stock-takes', StockTakeViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
