# ============================================================================
# URL Configuration (`recruitment/urls.py`)
# ============================================================================

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import *

router = DefaultRouter()
router.register(r'sources', RecruitmentSourceViewSet, basename='recruitment-source')
router.register(r'job-openings', JobOpeningViewSet, basename='job-opening')
router.register(r'applications', JobApplicationViewSet, basename='job-application')
router.register(r'interview-rounds', InterviewRoundViewSet, basename='interview-round')
router.register(r'interviews', InterviewScheduleViewSet, basename='interview-schedule')
router.register(r'interview-evaluations', InterviewEvaluationViewSet, basename='interview-evaluation')
router.register(r'assessment-tests', AssessmentTestViewSet, basename='assessment-test')
router.register(r'candidate-assessments', CandidateAssessmentViewSet, basename='candidate-assessment')
router.register(r'offer-letters', OfferLetterViewSet, basename='offer-letter')
router.register(r'background-checks', BackgroundCheckViewSet, basename='background-check')
router.register(r'reference-checks', ReferenceCheckViewSet, basename='reference-check')
router.register(r'compliance-checklists', ComplianceChecklistViewSet, basename='compliance-checklist')
router.register(r'selection-decisions', SelectionDecisionViewSet, basename='selection-decision')
router.register(r'onboarding-processes', OnboardingProcessViewSet, basename='onboarding-process')
router.register(r'probation-reviews', ProbationReviewViewSet, basename='probation-review')

urlpatterns = [
    path('', include(router.urls)),
    path('dashboard/', RecruitmentDashboardView.as_view(), name='recruitment-dashboard'),
    path('analytics/', RecruitmentAnalyticsView.as_view(), name='recruitment-analytics'),
    path('public/jobs/', PublicJobOpeningsView.as_view(), name='public-job-openings'),
    path('public/apply/', PublicJobApplicationView.as_view(), name='public-job-application'),
]