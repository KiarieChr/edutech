from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import BudgetViewSet, BudgetLineViewSet

router = DefaultRouter()
router.register(r'budgets', BudgetViewSet)
router.register(r'budget-lines', BudgetLineViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
