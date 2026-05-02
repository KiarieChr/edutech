from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .viewsets import (
    DriverProfileViewSet,
    FuelLogViewSet,
    MaintenanceRecordViewSet,
    TripLogViewSet,
    VehicleAssignmentViewSet,
    VehicleDocumentViewSet,
    VehicleExpenseViewSet,
    VehicleViewSet,
)

router = DefaultRouter()
router.register(r'vehicles', VehicleViewSet, basename='fleet-vehicle')
router.register(r'drivers', DriverProfileViewSet, basename='fleet-driver')
router.register(r'assignments', VehicleAssignmentViewSet, basename='fleet-assignment')
router.register(r'trips', TripLogViewSet, basename='fleet-trip')
router.register(r'fuel-logs', FuelLogViewSet, basename='fleet-fuel-log')
router.register(r'maintenance-records', MaintenanceRecordViewSet, basename='fleet-maintenance-record')
router.register(r'expenses', VehicleExpenseViewSet, basename='fleet-expense')
router.register(r'documents', VehicleDocumentViewSet, basename='fleet-document')

urlpatterns = [
    path('', include(router.urls)),
]
