from django.urls import path
from . import views

app_name = 'portal'

urlpatterns = [
    # ── Student endpoints ─────────────────────────────────
    path('me/', views.my_profile, name='my-profile'),
    path('dashboard/', views.student_dashboard_stats, name='student-dashboard'),
    path('fees/', views.my_fees, name='my-fees'),
    path('payments/', views.my_payments, name='my-payments'),
    path('results/', views.my_results, name='my-results'),
    path('exam-results/', views.my_exam_results, name='my-exam-results'),
    path('timetable/', views.my_timetable, name='my-timetable'),
    path('attendance/', views.my_attendance, name='my-attendance'),
    path('announcements/', views.announcements, name='announcements'),

    # ── Student assignment endpoints ─────────────────────
    path('assignments/', views.my_assignments_portal, name='my-assignments'),
    path('assignments/<int:assignment_id>/submit/', views.submit_assignment_portal, name='submit-assignment'),

    # ── Student statement endpoint ───────────────────────
    path('statement/', views.my_statement, name='my-statement'),

    # ── Parent endpoints ──────────────────────────────────
    path('parent/me/', views.parent_profile, name='parent-profile'),
    path('parent/dashboard/', views.parent_dashboard_stats, name='parent-dashboard'),
    path('parent/children/', views.parent_children, name='parent-children'),
    path('parent/child/<int:student_id>/fees/', views.parent_child_fees, name='parent-child-fees'),
    path('parent/child/<int:student_id>/results/', views.parent_child_results, name='parent-child-results'),
    path('parent/child/<int:student_id>/attendance/', views.parent_child_attendance, name='parent-child-attendance'),
    path('parent/child/<int:student_id>/assignments/', views.parent_child_assignments_portal, name='parent-child-assignments'),
    path('parent/child/<int:student_id>/statement/', views.parent_child_statement, name='parent-child-statement'),
]
