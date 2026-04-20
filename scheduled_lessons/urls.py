from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import PlannedLessonViewSet

router = DefaultRouter()
router.register(r'planned-lessons', PlannedLessonViewSet, basename='planned-lesson')

urlpatterns = [
    path('', include(router.urls)),
]
