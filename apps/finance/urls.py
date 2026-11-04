from .views import AccountViewSet, TaxViewSet, FinanceSettingsView, FiscalPeriodViewSet, CashbookViewSet, PaymentMethodViewSet, SponsorTypeViewSet, SponsorshipViewSet, AdmissionFeeTemplateViewSet, AdmissionFeeItemViewSet
from rest_framework.routers import DefaultRouter
from django.urls import path, include

from .budget_views import BudgetDashboardView
from .budget_planning_views import (
    BudgetPlanningView,
    BudgetPlanningSaveView,
    BudgetPlanningSubmitView,
    BudgetPlanningExportView,
    BudgetPlanningImportView,
)
from .budget_income_views import (
    IncomeProjectionView,
    IncomeProjectionAdjustmentSaveView,
)
from .budget_adjustment_views import (
    BudgetAdjustmentPreviewView,
    BudgetAdjustmentApplyView,
    BudgetAdjustmentHistoryView,
)
from .budget_approval_views import (
    BudgetPlanningApproveView,
    BudgetPlanningRejectView,
    BudgetAdjustmentApproveView,
    BudgetAdjustmentRejectView,
    PendingApprovalsListView,
)
from .budget_report_views import (
    BudgetVsActualReportExportView,
    AdjustmentHistoryReportExportView,
    BudgetReportsMetadataView,
)

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
    # Dashboard & Planning Formulation
    path('budgeting/dashboard/', BudgetDashboardView.as_view(), name='finance-budgeting-dashboard'),
    path('budgeting/planning/', BudgetPlanningView.as_view(), name='finance-budgeting-planning'),
    path('budgeting/planning/save/', BudgetPlanningSaveView.as_view(), name='finance-budgeting-planning-save'),
    path('budgeting/planning/<int:pk>/submit/', BudgetPlanningSubmitView.as_view(), name='finance-budgeting-planning-submit-pk'),
    path('budgeting/planning/submit/', BudgetPlanningSubmitView.as_view(), name='finance-budgeting-planning-submit'),
    path('budgeting/planning/<int:pk>/approve/', BudgetPlanningApproveView.as_view(), name='finance-budgeting-planning-approve-pk'),
    path('budgeting/planning/approve/', BudgetPlanningApproveView.as_view(), name='finance-budgeting-planning-approve'),
    path('budgeting/planning/<int:pk>/reject/', BudgetPlanningRejectView.as_view(), name='finance-budgeting-planning-reject-pk'),
    path('budgeting/planning/reject/', BudgetPlanningRejectView.as_view(), name='finance-budgeting-planning-reject'),
    path('budgeting/planning/export/', BudgetPlanningExportView.as_view(), name='finance-budgeting-planning-export'),
    path('budgeting/planning/import/', BudgetPlanningImportView.as_view(), name='finance-budgeting-planning-import'),

    # Income Projections
    path('budgeting/income-projection/', IncomeProjectionView.as_view(), name='finance-budgeting-income-projection'),
    path('budgeting/income-projection/adjust/', IncomeProjectionAdjustmentSaveView.as_view(), name='finance-budgeting-income-projection-adjust'),

    # Automatic Adjustments
    path('budgeting/adjustments/preview/', BudgetAdjustmentPreviewView.as_view(), name='finance-budgeting-adjustments-preview'),
    path('budgeting/adjustments/apply/', BudgetAdjustmentApplyView.as_view(), name='finance-budgeting-adjustments-apply'),
    path('budgeting/adjustments/history/', BudgetAdjustmentHistoryView.as_view(), name='finance-budgeting-adjustments-history'),
    path('budgeting/adjustments/<int:pk>/approve/', BudgetAdjustmentApproveView.as_view(), name='finance-budgeting-adjustments-approve-pk'),
    path('budgeting/adjustments/approve/', BudgetAdjustmentApproveView.as_view(), name='finance-budgeting-adjustments-approve'),
    path('budgeting/adjustments/<int:pk>/reject/', BudgetAdjustmentRejectView.as_view(), name='finance-budgeting-adjustments-reject-pk'),
    path('budgeting/adjustments/reject/', BudgetAdjustmentRejectView.as_view(), name='finance-budgeting-adjustments-reject'),

    # Approvals Queue
    path('budgeting/approvals/pending/', PendingApprovalsListView.as_view(), name='finance-budgeting-approvals-pending'),

    # Reports & Exports (PDF / Excel)
    path('budgeting/reports/budget-vs-actual/', BudgetVsActualReportExportView.as_view(), name='finance-budgeting-reports-budget-vs-actual'),
    path('budgeting/reports/adjustments/', AdjustmentHistoryReportExportView.as_view(), name='finance-budgeting-reports-adjustments'),
    path('budgeting/reports/metadata/', BudgetReportsMetadataView.as_view(), name='finance-budgeting-reports-metadata'),

    path('', include(router.urls)),
]
