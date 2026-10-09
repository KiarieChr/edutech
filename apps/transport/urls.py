from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    RouteViewSet,
    StopViewSet,
    FeeStructureViewSet,
    StudentAssignmentViewSet,
    FeeChargeViewSet
)

router = DefaultRouter()
router.register(r'routes', RouteViewSet, basename='route')
router.register(r'stops', StopViewSet, basename='stop')
router.register(r'fee-structures', FeeStructureViewSet, basename='fee-structure')
router.register(r'assignments', StudentAssignmentViewSet, basename='assignment')
router.register(r'charges', FeeChargeViewSet, basename='charge')

urlpatterns = [
    path('', include(router.urls)),
]
