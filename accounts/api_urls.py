# accounts/api_urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import (
    UserViewSet,
    LoginAPIView, FirstTimeSetupAPIView, LogoutAPIView,
    ValidateUsernameAPIView, RegisterAPIView,DashboardStatsAPIView
)

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
#router.register(r'students', StudentViewSet, basename='student')
#router.register(r'parents', ParentViewSet, basename='parent')

urlpatterns = [
    # Authentication
    path('auth/login/', LoginAPIView.as_view(), name='api_login'),
    path('auth/first-time-setup/', FirstTimeSetupAPIView.as_view(), name='api_first_time_setup'),
    path('auth/logout/', LogoutAPIView.as_view(), name='api_logout'),
    path('auth/register/', RegisterAPIView.as_view(), name='api_register'),
    path('dashboard/stats/', DashboardStatsAPIView.as_view(), name='api_dashboard_stats'),
    
    # Profile
   # path('profile/', ProfileAPIView.as_view(), name='api_profile'),
    #path('profile/<int:user_id>/', ProfileAPIView.as_view(), name='api_profile_single'),
    
    # Utility
    path('validate-username/', ValidateUsernameAPIView.as_view(), name='api_validate_username'),
    
    # Include router URLs
    path('', include(router.urls)),
]