from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import (
    SubjectViewSet, RoomViewSet, TimetableSlotViewSet,
    TimetableExceptionViewSet, CurriculumUnitViewSet,
    # New enhanced timetabling viewsets
    TimePeriodViewSet, WorkAllocationViewSet, TeacherAvailabilityViewSet,
    TimetableLockViewSet, TimetableVersionViewSet,
    # API views
    ConflictCheckView, SchedulingView, AnalyticsView,
    ClassTimetableView, TeacherTimetableView, RoomTimetableView,
    GenerateForTermView, MonthlyTimetableView,
)

router = DefaultRouter()
router.register(r'subjects',    SubjectViewSet,           basename='subject')
router.register(r'rooms',       RoomViewSet,              basename='room')
router.register(r'slots',       TimetableSlotViewSet,     basename='timetable-slot')
router.register(r'exceptions',  TimetableExceptionViewSet, basename='timetable-exception')
router.register(r'curriculum-units', CurriculumUnitViewSet, basename='curriculum-unit')

# New enhanced timetabling endpoints
router.register(r'periods',      TimePeriodViewSet,        basename='time-period')
router.register(r'allocations',  WorkAllocationViewSet,    basename='work-allocation')
router.register(r'availability', TeacherAvailabilityViewSet, basename='teacher-availability')
router.register(r'locks',        TimetableLockViewSet,     basename='timetable-lock')
router.register(r'versions',     TimetableVersionViewSet,  basename='timetable-version')

urlpatterns = [
    path('', include(router.urls)),
    
    # Conflict checking and scheduling
    path('check-conflict/', ConflictCheckView.as_view(), name='check-conflict'),
    path('generate/', SchedulingView.as_view(), name='generate-timetable'),
    
    # Analytics endpoints
    path('analytics/<str:report_type>/', AnalyticsView.as_view(), name='analytics'),
    path('analytics/<str:report_type>/<int:entity_id>/', AnalyticsView.as_view(), name='analytics-detail'),
    
    # Full timetable views
    path('class/<int:class_id>/full/', ClassTimetableView.as_view(), name='class-timetable'),
    path('teacher/<int:teacher_id>/full/', TeacherTimetableView.as_view(), name='teacher-timetable'),
    path('room/<int:room_id>/full/', RoomTimetableView.as_view(), name='room-timetable'),
    
    # Batch scheduling & Calendar views
    path('generate-for-term/', GenerateForTermView.as_view(), name='generate-for-term'),
    path('monthly-view/', MonthlyTimetableView.as_view(), name='monthly-view'),
]
