from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ClassSessionViewSet, StudentSessionEnrollmentViewSet
from student_settings.views import CurriculumLevelViewSet, TermViewSet, AcademicYearViewSet
from . import report_views

router = DefaultRouter()
router.register(r'sessions', ClassSessionViewSet)
router.register(r'enrollments', StudentSessionEnrollmentViewSet)
router.register(r'curriculum-levels', CurriculumLevelViewSet, basename='academic-curriculum-levels')
router.register(r'terms', TermViewSet, basename='academic-terms')
router.register(r'academic-years', AcademicYearViewSet, basename='academic-academic-years')

urlpatterns = [
    path('', include(router.urls)),
    # ── Student Management Reports ─────────────────────
    path('reports/overview/', report_views.report_overview, name='report-overview'),
    path('reports/student-list/', report_views.report_student_list, name='report-student-list'),
    path('reports/class-list/', report_views.report_class_list, name='report-class-list'),
    path('reports/fee-collections/', report_views.report_fee_collections, name='report-fee-collections'),
    path('reports/attendance/', report_views.report_attendance, name='report-attendance'),
    path('reports/class-statistics/', report_views.report_class_statistics, name='report-class-statistics'),
    path('reports/session-statistics/', report_views.report_session_statistics, name='report-session-statistics'),
    path('reports/applicant-statistics/', report_views.report_applicant_statistics, name='report-applicant-statistics'),
    path('reports/enrollment-statistics/', report_views.report_enrollment_statistics, name='report-enrollment-statistics'),
    path('reports/student-statement/', report_views.report_student_statement, name='report-student-statement'),
    path('reports/academic/', report_views.report_academic, name='report-academic'),
    path('reports/transfers/', report_views.report_transfers, name='report-transfers'),
    path('reports/demographics/', report_views.report_demographics, name='report-demographics'),
]
