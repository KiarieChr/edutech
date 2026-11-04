from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import BudgetViewSet, BudgetLineViewSet

from finance.budget_views import BudgetDashboardView
from finance.budget_planning_views import (
    BudgetPlanningView,
    BudgetPlanningSaveView,
    BudgetPlanningSubmitView,
    BudgetPlanningExportView,
    BudgetPlanningImportView,
)
from finance.budget_income_views import (
    IncomeProjectionView,
    IncomeProjectionAdjustmentSaveView,
)

router = DefaultRouter()
router.register(r'budgets', BudgetViewSet)
router.register(r'budget-lines', BudgetLineViewSet)

urlpatterns = [
    path('dashboard/', BudgetDashboardView.as_view(), name='budgets-dashboard'),
    path('planning/', BudgetPlanningView.as_view(), name='budgets-planning'),
    path('planning/save/', BudgetPlanningSaveView.as_view(), name='budgets-planning-save'),
    path('planning/<int:pk>/submit/', BudgetPlanningSubmitView.as_view(), name='budgets-planning-submit-pk'),
    path('planning/submit/', BudgetPlanningSubmitView.as_view(), name='budgets-planning-submit'),
    path('planning/export/', BudgetPlanningExportView.as_view(), name='budgets-planning-export'),
    path('planning/import/', BudgetPlanningImportView.as_view(), name='budgets-planning-import'),
    path('income-projection/', IncomeProjectionView.as_view(), name='budgets-income-projection'),
    path('income-projection/adjust/', IncomeProjectionAdjustmentSaveView.as_view(), name='budgets-income-projection-adjust'),
    path('', include(router.urls)),
]
