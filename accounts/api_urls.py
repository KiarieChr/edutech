# accounts/api_urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import (
    UserViewSet,
    LoginAPIView, FirstTimeSetupAPIView, LogoutAPIView,
    ValidateUsernameAPIView, RegisterAPIView, DashboardStatsAPIView,
    DebugDashboardView, csrf, MeAPIView,FirstTimeSetupStatusAPIView, SetupCompleteAPIView,
    RoleViewSet, PermissionViewSet,
    ForgotPasswordAPIView, VerifyOTPAPIView, ResetPasswordAPIView
)


router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'roles', RoleViewSet, basename='role')
router.register(r'permissions', PermissionViewSet, basename='permission')
#router.register(r'students', StudentViewSet, basename='student')
#router.register(r'parents', ParentViewSet, basename='parent')

urlpatterns = [
    # Authentication
    path('auth/login/', LoginAPIView.as_view(), name='api_login'),
    path('auth/first-time-setup/', FirstTimeSetupAPIView.as_view(), name='api_first_time_setup'),
    path('auth/first-time-setup/status/', FirstTimeSetupStatusAPIView.as_view(), name='api_setup_status'),
    path('auth/setup-complete/', SetupCompleteAPIView.as_view(), name='api_setup_complete'),
    path('auth/logout/', LogoutAPIView.as_view(), name='api_logout'),
    path('auth/register/', RegisterAPIView.as_view(), name='api_register'),
    path('csrf/', csrf, name='api_csrf'),
    path('dashboard/stats/', DashboardStatsAPIView.as_view(), name='api_dashboard_stats'),
    path('dashboard/debug/', DebugDashboardView.as_view(), name='api_dashboard_debug'),
    path('auth/me/', MeAPIView.as_view(), name='api_me'),
    
    # Password Reset
    path('auth/forgot-password/', ForgotPasswordAPIView.as_view(), name='api_forgot_password'),
    path('auth/verify-otp/', VerifyOTPAPIView.as_view(), name='api_verify_otp'),
    path('auth/reset-password/', ResetPasswordAPIView.as_view(), name='api_reset_password'),

    # Profile
   # path('profile/', ProfileAPIView.as_view(), name='api_profile'),
    #path('profile/<int:user_id>/', ProfileAPIView.as_view(), name='api_profile_single'),
    
    # Utility
    path('validate-username/', ValidateUsernameAPIView.as_view(), name='api_validate_username'),
    
    # Include router URLs
    path('', include(router.urls)),
]