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
    TransportStopViewSet,
    RouteStopViewSet,
    TransportRouteViewSet,
    TransportScheduleViewSet,
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

# Transport Routing
router.register(r'transport-stops', TransportStopViewSet, basename='fleet-transport-stop')
router.register(r'route-stops', RouteStopViewSet, basename='fleet-route-stop')
router.register(r'transport-routes', TransportRouteViewSet, basename='fleet-transport-route')
router.register(r'transport-schedules', TransportScheduleViewSet, basename='fleet-transport-schedule')

urlpatterns = [
    path('', include(router.urls)),
]
