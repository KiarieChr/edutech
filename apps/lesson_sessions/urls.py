from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import (
    LessonSessionViewSet, TeacherSubstitutionViewSet,
    CurriculumCoverageViewSet, TeacherWorkloadView,
)

router = DefaultRouter()
router.register(r'sessions',         LessonSessionViewSet,       basename='lesson-session')
router.register(r'substitutions',    TeacherSubstitutionViewSet, basename='substitution')
router.register(r'curriculum-coverage', CurriculumCoverageViewSet, basename='curriculum-coverage')

urlpatterns = [
    path('', include(router.urls)),
    path('teacher-workload/', TeacherWorkloadView.as_view(), name='teacher-workload'),
]
