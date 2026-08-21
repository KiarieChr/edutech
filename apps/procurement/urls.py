from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'requisitions', views.PurchaseRequisitionViewSet)
router.register(r'rfqs', views.RFQViewSet)
router.register(r'quotations', views.SupplierQuotationViewSet)
router.register(r'purchase-orders', views.PurchaseOrderViewSet)
router.register(r'contracts', views.SupplierContractViewSet)

urlpatterns = [
    path('', include(router.urls)),

    # Nested: requisition lines
    path('requisitions/<int:requisition_pk>/lines/',
         views.RequisitionLineViewSet.as_view({'get': 'list', 'post': 'create'}),
         name='requisition-lines'),
    path('requisitions/<int:requisition_pk>/lines/<int:pk>/',
         views.RequisitionLineViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}),
         name='requisition-line-detail'),

    # Nested: PO lines
    path('purchase-orders/<int:po_pk>/lines/',
         views.PurchaseOrderLineViewSet.as_view({'get': 'list', 'post': 'create'}),
         name='po-lines'),
    path('purchase-orders/<int:po_pk>/lines/<int:pk>/',
         views.PurchaseOrderLineViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}),
         name='po-line-detail'),

    # Nested: contract milestones
    path('contracts/<int:contract_pk>/milestones/',
         views.ContractMilestoneViewSet.as_view({'get': 'list', 'post': 'create'}),
         name='contract-milestones'),
    path('contracts/<int:contract_pk>/milestones/<int:pk>/',
         views.ContractMilestoneViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}),
         name='contract-milestone-detail'),
    path('contracts/<int:contract_pk>/milestones/<int:pk>/complete/',
         views.ContractMilestoneViewSet.as_view({'post': 'complete'}),
         name='contract-milestone-complete'),

    # Public quotation links (no auth)
    path('quote/<uuid:token>/',
         views.public_rfq_detail, name='public-rfq-detail'),
    path('quote/<uuid:token>/submit/',
         views.public_quotation_submit, name='public-quotation-submit'),
]
