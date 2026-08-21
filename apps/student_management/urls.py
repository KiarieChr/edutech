from django.urls import path, include
from rest_framework.routers import DefaultRouter
from student_management.viewsets.import_viewset import StudentImportViewSet
from student_management.viewsets import ApplicationViewSet, AdmissionViewSet, EnquiryViewSet, StudentReportsViewSet

router = DefaultRouter()
router.register(r'applications', ApplicationViewSet)
router.register(r'admissions', AdmissionViewSet)
router.register(r'enquiries', EnquiryViewSet)
router.register(r'import', StudentImportViewSet, basename='student-import')
router.register(r'reports', StudentReportsViewSet, basename='student-reports')

urlpatterns = [
    path('', include(router.urls)),
]
