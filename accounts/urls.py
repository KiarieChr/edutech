from django.urls import path, include
from django.contrib.auth import views as auth_views

from .views import (
    profile,
    profile_single,
    admin_panel,
    profile_update,
    change_password,
    LecturerFilterView,
    StudentListView,
    staff_add_view,
    edit_staff,
    delete_staff,
    student_add_view,
    edit_student,
    delete_student,
    edit_student_program,
    ParentAdd,
    validate_username,
    register,
    render_lecturer_pdf_list,  # new
    render_student_pdf_list,
    CustomLoginView, FirstTimeSetupView,users_dashboard,users_list_ajax, user_quick_actions_ajax
)

# from .forms import EmailValidationOnForgotPassword


urlpatterns = [
    path("", include("django.contrib.auth.urls")),
    path("admin_panel/", admin_panel, name="admin_panel"),
    path("profile/", profile, name="profile"),
    path("profile/<int:user_id>/detail/", profile_single, name="profile_single"),
    path("setting/", profile_update, name="edit_profile"),
    path("change_password/", change_password, name="change_password"),
    path("lecturers/", LecturerFilterView.as_view(), name="lecturer_list"),
    path("lecturer/add/", staff_add_view, name="add_lecturer"),
    path("staff/<int:pk>/edit/", edit_staff, name="staff_edit"),
    path("lecturers/<int:pk>/delete/", delete_staff, name="lecturer_delete"),
    path("students/", StudentListView.as_view(), name="student_list"),
    path("student/add/", student_add_view, name="add_student"),
    path("student/<int:pk>/edit/", edit_student, name="student_edit"),
    path("students/<int:pk>/delete/", delete_student, name="student_delete"),
    path(
        "edit_student_program/<int:pk>/",
        edit_student_program,
        name="student_program_edit",
    ),
    path("parents/add/", ParentAdd.as_view(), name="add_parent"),
    path("ajax/validate-username/", validate_username, name="validate_username"),
    path("register/", register, name="register"),
    # paths to pdf
    path(
        "create_lecturers_pdf_list/", render_lecturer_pdf_list, name="lecturer_list_pdf"
    ),  # new
    path(
        "create_students_pdf_list/", render_student_pdf_list, name="student_list_pdf"
    ), 
    path('auth/login/', CustomLoginView.as_view(), name='login'),

    # First-time login setup
    path('first-time-setup/', FirstTimeSetupView.as_view(), name='first_time_setup'),

    # Logout
    path('auth/logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),

    # Password reset
    path('auth/password-reset/', auth_views.PasswordResetView.as_view(), name='password_reset'),
    path('auth/password-reset/done/', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    path(
        'auth/password-reset-confirm/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(),
        name='password_reset_confirm'
    ),
    path(
        'auth/password-reset-complete/',
        auth_views.PasswordResetCompleteView.as_view(),
        name='password_reset_complete'
    ),
    path('users-dashboard/', users_dashboard, name='users_dashboard'),
    path('ajax/users-list/', users_list_ajax, name='users_list_ajax'),
    path('ajax/user/<int:user_id>/actions/', user_quick_actions_ajax, name='user_quick_actions'),
]
