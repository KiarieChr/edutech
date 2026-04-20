from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AcademicYearViewSet, TermViewSet, CurriculumViewSet,
    GradeStructureViewSet, StreamViewSet, AdmissionConfigViewSet,
    StudentStatusViewSet, PromotionRuleViewSet, DemographicConfigViewSet,
    SchoolCalendarViewSet, EnrollmentViewSet, IntakeViewSet,
    CurriculumLevelViewSet, LearningAreaViewSet
)

router = DefaultRouter()
router.register(r'academic-years', AcademicYearViewSet)
router.register(r'intakes', IntakeViewSet)
router.register(r'terms', TermViewSet)
router.register(r'curricula', CurriculumViewSet)
router.register(r'curriculum-levels', CurriculumLevelViewSet)
router.register(r'learning-areas', LearningAreaViewSet)
router.register(r'classes', GradeStructureViewSet)
router.register(r'streams', StreamViewSet)
router.register(r'admission-config', AdmissionConfigViewSet)
router.register(r'student-statuses', StudentStatusViewSet)
router.register(r'promotion-rules', PromotionRuleViewSet)
router.register(r'demographic-config', DemographicConfigViewSet)
router.register(r'calendar', SchoolCalendarViewSet)
router.register(r'enrollments', EnrollmentViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
