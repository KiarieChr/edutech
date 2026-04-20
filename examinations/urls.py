from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    GradingScaleViewSet, AssessmentTypeViewSet, ExaminationViewSet,
    TermResultViewSet, ReportCardTemplateViewSet
)

router = DefaultRouter()
router.register(r'grading-scales', GradingScaleViewSet, basename='grading-scale')
router.register(r'assessment-types', AssessmentTypeViewSet, basename='assessment-type')
router.register(r'examinations', ExaminationViewSet, basename='examination')
router.register(r'term-results', TermResultViewSet, basename='term-result')
router.register(r'report-templates', ReportCardTemplateViewSet, basename='report-template')

urlpatterns = [
    path('', include(router.urls)),
]
