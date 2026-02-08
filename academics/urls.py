from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ClassSessionViewSet, StudentSessionEnrollmentViewSet

router = DefaultRouter()
router.register(r'sessions', ClassSessionViewSet)
router.register(r'enrollments', StudentSessionEnrollmentViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
