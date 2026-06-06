from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    FacultyViewSet, DepartmentViewSet, ProgrammeViewSet, SpecializationViewSet,
    ProgrammeUnitViewSet, UnitOfferingViewSet,
    ProgrammeEnrollmentViewSet, UnitRegistrationViewSet
)

router = DefaultRouter()
router.register(r'faculties',    FacultyViewSet)
router.register(r'departments',  DepartmentViewSet)
router.register(r'programmes',   ProgrammeViewSet)
router.register(r'specializations', SpecializationViewSet)
router.register(r'units',        ProgrammeUnitViewSet)
router.register(r'offerings',    UnitOfferingViewSet)
router.register(r'enrollments',  ProgrammeEnrollmentViewSet)
router.register(r'unit-registrations', UnitRegistrationViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
