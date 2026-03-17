# accounts/api_views.py
from rest_framework import status, viewsets, generics, permissions, filters
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.pagination import PageNumberPagination
from django.contrib.auth import update_session_auth_hash, login, authenticate, logout
from django.contrib.sessions.models import Session

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.core.paginator import Paginator
from django.db.models import Count, Q, F, When, Case, IntegerField, Sum
from django.db.models.functions import TruncMonth, TruncDay, TruncWeek
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from django.utils import timezone
import calendar
import logging

from .models import User, Student, Parent, Activity
from django.contrib.auth.models import Group, Permission
from .serializers import (
    UserSerializer, UserDetailSerializer, UserCreateSerializer,
    UserUpdateSerializer, LoginSerializer, EmailLoginSerializer,
    FirstTimeSetupSerializer, PasswordChangeSerializer,
    DashboardStatsSerializer, UserFilterSerializer,
    GroupSerializer, PermissionSerializer, UserSessionSerializer, ActivitySerializer,
    ForgotPasswordSerializer, VerifyOTPSerializer, ResetPasswordSerializer
)

import user_agents
import random
from datetime import timedelta
from core.utils import send_html_email
from .models import OTP


logger = logging.getLogger(__name__)

from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import JsonResponse

@ensure_csrf_cookie
def csrf(request):
    return JsonResponse({"detail": "CSRF set"})

class MeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    
class DebugDashboardView(APIView):
    """
    Simple debug view to verify authentication and return basic stats.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            "status": "success",
            "message": f"Authenticated as {request.user.username}",
            "user_id": request.user.id,
            "auth_method": request.auth.key if hasattr(request.auth, 'key') else "Session",
            "data": {
                "total_users": User.objects.count(),
                "active_users": User.objects.filter(is_active=True).count(),
                "your_role": "Admin" if request.user.is_superuser else "User"
            }
        })

class DashboardStatsAPIView(APIView):
    """
    API endpoint for users dashboard statistics.
    Returns comprehensive statistics for the admin dashboard.
    """
    
    # authentication_classes = [] # Removed to allow TokenAuthentication
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """
        Get dashboard statistics with optional date filters.
        """
        today = timezone.now().date()

        # 1. Stats Cards — real DB queries
        total_students_count = Student.objects.count()

        # Today's session attendance (graceful fallback if model unavailable)
        try:
            from student_management.models.class_session import SessionAttendance
            total_today = SessionAttendance.objects.filter(date=today).count()
            present_today = SessionAttendance.objects.filter(date=today, status='present').count()
            attendance_percent = round((present_today / total_today * 100), 1) if total_today > 0 else 0.0
        except Exception:
            attendance_percent = 0.0

        # Fee collection this month and defaulters (graceful fallback if model unavailable)
        try:
            from fees.models import FeeInvoice
            month_start = today.replace(day=1)
            paid_total = FeeInvoice.objects.filter(
                updated_at__date__gte=month_start
            ).aggregate(total=Sum('paid_amount'))['total'] or 0
            if paid_total >= 1_000_000:
                fee_collection = f"{paid_total / 1_000_000:.1f}M"
            elif paid_total >= 1_000:
                fee_collection = f"{paid_total / 1_000:.0f}K"
            else:
                fee_collection = str(paid_total)
            fee_defaulters = FeeInvoice.objects.filter(
                balance__gt=0
            ).values('student').distinct().count()
        except Exception:
            fee_collection = "0"
            fee_defaulters = 0

        stats = [
            {
                "title": 'Total Students',
                "count": f"{total_students_count:,}",
                "trend": 0,
                "trendLabel": 'enrolled students',
                "icon": 'users',
                "color": '#e3f2fd',
                "iconColor": '#2196f3'
            },
            {
                "title": "Today's Attendance",
                "count": f"{attendance_percent}%",
                "trend": 0,
                "trendLabel": 'present today',
                "icon": 'user-check',
                "color": '#e8f5e9',
                "iconColor": '#4caf50'
            },
            {
                "title": 'Fee Collection',
                "count": f"KES {fee_collection}",
                "trend": 0,
                "trendLabel": 'this month',
                "icon": 'credit-card',
                "color": '#fff3e0',
                "iconColor": '#ff9800'
            },
            {
                "title": 'Fee Defaulters',
                "count": str(fee_defaulters),
                "trend": 0,
                "trendLabel": 'outstanding balance',
                "icon": 'alert-triangle',
                "color": '#ffebee',
                "iconColor": '#f44336'
            },
        ]

        # 2. Charts Data
        # Weekly Attendance — real daily counts for Mon–Fri of current week
        week_start = today - timedelta(days=today.weekday())
        days_labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
        weekly_attendance = []
        for i, label in enumerate(days_labels):
            day_date = week_start + timedelta(days=i)
            try:
                from student_management.models.class_session import SessionAttendance
                present = SessionAttendance.objects.filter(date=day_date, status='present').count()
                absent = SessionAttendance.objects.filter(date=day_date, status='absent').count()
            except Exception:
                present = 0
                absent = 0
            weekly_attendance.append({"name": label, "present": present, "absent": absent})

        # Fee Collection Pie Chart — real totals for current term
        try:
            from fees.models import FeeInvoice
            from student_settings.models import Term
            
            # Get current term
            current_term = Term.objects.filter(is_current=True).select_related('academic_year').first()
            current_term_name = f"{current_term.name}, {current_term.academic_year.name}" if current_term else "Current Term"
            
            # Filter by current term if available
            if current_term:
                agg = FeeInvoice.objects.filter(term=current_term).aggregate(
                    collected=Sum('paid_amount'),
                    total_billed=Sum('total_amount'),
                )
            else:
                agg = FeeInvoice.objects.aggregate(
                    collected=Sum('paid_amount'),
                    total_billed=Sum('total_amount'),
                )
            total_billed = float(agg['total_billed'] or 0)
            fee_collected_val = float(agg['collected'] or 0)
            fee_pending_val = max(0.0, round(total_billed - fee_collected_val, 2))
            fee_overdue_val = 0.0  # requires due_date check; placeholder
        except Exception:
            fee_collected_val = 0.0
            fee_pending_val = 0.0
            fee_overdue_val = 0.0
            current_term_name = "Current Term"

        fee_collection_chart = [
            {"name": 'Collected', "value": fee_collected_val, "color": '#4caf50'},
            {"name": 'Pending', "value": fee_pending_val, "color": '#ff9800'},
            {"name": 'Overdue', "value": fee_overdue_val, "color": '#f44336'},
        ]
        
        # 3. Recent Activity (Mock)
        recent_activity = [
            { "id": 1, "title": 'New Student Enrolled', "desc": 'John Doe was enrolled in Class 9', "time": '5 minutes ago', "icon": 'user-plus', "color": '#e3f2fd' },
            { "id": 2, "title": 'Fee Payment Received', "desc": 'KES 45,000 received from...', "time": '15 minutes ago', "icon": 'credit-card', "color": '#fff3e0' },
            { "id": 3, "title": 'Report Cards Generated', "desc": 'Term 1 reports for Class 9', "time": '1 hour ago', "icon": 'file-text', "color": '#e8f5e9' },
            { "id": 4, "title": 'Staff Meeting Reminder', "desc": 'January payroll processed', "time": '2 hours ago', "icon": 'bell', "color": '#e3f2fd' },
        ]

        # 4. Upcoming Events (Mock)
        upcoming_events = [
            { "id": 1, "title": 'Mid-Term Examinations', "date": 'Feb 15, 2026', "time": '8:00 AM', "location": 'All Classrooms', "color": '#4caf50' },
            { "id": 2, "title": 'Parent-Teacher Meeting', "date": 'Feb 20, 2026', "time": '2:00 PM', "location": 'School Hall', "color": '#2196f3' },
            { "id": 3, "title": 'Sports Day', "date": 'Feb 28, 2026', "time": '9:00 AM', "location": 'Sports Ground', "color": '#009688' },
            { "id": 4, "title": 'Fee Payment Deadline', "date": 'Mar 5, 2026', "time": '5:00 PM', "location": 'Finance Office', "color": '#f44336' },
        ]

        # Prepare response data structure matching frontend expectations
        user_data = None
        if request.user and request.user.is_authenticated:
             user_data = UserSerializer(request.user).data
        else:
             # Basic dummy user data for non-authenticated view if needed
             user_data = {
                 'id': 0, 'username': 'Guest', 'email': '', 'first_name': 'Guest', 'last_name': 'User'
             }

        response_data = {
            "stats": stats,
            "isAuthenticated": request.user.is_authenticated if request.user else False,
            "user": user_data,
            "charts": {
                "weekly_attendance": weekly_attendance,
                "fee_collection": fee_collection_chart,
                "current_term": current_term_name
            },
            "recent_activity": recent_activity,
            "upcoming_events": upcoming_events
        }
        
        return Response({
            'success': True,
            'data': response_data,
            'message': _('Dashboard statistics retrieved successfully'),
        })
# Custom Pagination
class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'per_page'
    max_page_size = 100
    
    def get_paginated_response(self, data):
        return Response({
            'pagination': {
                'current_page': self.page.number,
                'total_pages': self.page.paginator.num_pages,
                'total_count': self.page.paginator.count,
                'has_previous': self.page.has_previous(),
                'has_next': self.page.has_next(),
                'per_page': self.page.paginator.per_page,
            },
            'results': data
        })

logger = logging.getLogger(__name__)


# Authentication APIs
class LoginAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = [] # Disable authentication to prevent "Invalid token" error if client sends stale token
    
    def post(self, request):
        # Accept both email_or_username format or email-only format      
        data = request.data.copy()

        
        if 'email' in data and 'password' in data:
            # Use email-specific serializer
            serializer = EmailLoginSerializer(data=data, context={'request': request})
        else:
            # Use generic identifier serializer
            serializer = LoginSerializer(data=data, context={'request': request})
        
        if serializer.is_valid():
            user = serializer.validated_data['user']
            
            # Check if first time login
            if user.is_first_login:
                # Store user_id in session for first-time setup
                request.session['first_time_user_id'] = user.id
                return Response({
                    'success': True,
                    'message': _("Welcome! Please complete your profile setup to continue."),
                    'requires_setup': True,
                    'user_id': user.id,
                    'user_email': user.email
                }, status=status.HTTP_200_OK)
            
            # Normal login for returning users
            login(request, user, backend='accounts.backends.EmailOrUsernameModelBackend')

            
            # Store session metadata for active sessions tracking
            request.session['user_agent'] = request.META.get('HTTP_USER_AGENT', '')
            request.session['ip_address'] = request.META.get('REMOTE_ADDR', '')
            request.session.save()
            
            # Log successful login activity
            Activity.log_activity(
                user=user,
                activity_type='login',
                request=request,
                description=f'User logged in',
                status='success'
            )

            
            token, created = Token.objects.get_or_create(user=user)
            
            return Response({
                'success': True,
                'message': _("Welcome back, {}!").format(user.get_full_name),
                'token': token.key,
                'user': UserSerializer(user).data,
                'requires_setup': False
            }, status=status.HTTP_200_OK)       
        
        # Log failed login attempt
        user_identifier = request.data.get('email') or request.data.get('username')
        try:
            user = User.objects.get(email__iexact=user_identifier) or User.objects.get(username__iexact=user_identifier)
            Activity.log_activity(
                user=user,
                activity_type='failed_login',
                request=request,
                description=f'Failed login attempt',
                status='failed'
            )
        except:
            pass  # User doesn't exist, don't log
        
        logger.error(f"Login validation errors: {serializer.errors}")
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

# Add this import if not already present
from django.contrib.auth.decorators import login_required

class FirstTimeSetupStatusAPIView(APIView):
    """Check if user needs first-time setup"""
    permission_classes = [AllowAny]
    authentication_classes = []
    
    def get(self, request):
        # Try to get user_id from session first
        user_id = request.session.get('first_time_user_id')
        
        # If not in session, try GET parameter
        if not user_id:
            user_id = request.GET.get('user_id')
        
        if not user_id:
            return Response({
                'success': False,
                'message': _('No setup session found'),
                'requires_setup': False
            })
        
        try:
            user = User.objects.get(pk=user_id)
            return Response({
                'success': True,
                'requires_setup': user.is_first_login,
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'username': user.username,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                }
            })
        except User.DoesNotExist:
            return Response({
                'success': False,
                'message': _('User not found'),
                'requires_setup': False
            })
class FirstTimeSetupAPIView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    
    def get_user_id(self, request):
        """Get user_id from various sources"""
        # Try session first
        user_id = request.session.get('first_time_user_id')
        
        # If not in session, try GET parameter
        if not user_id:
            user_id = request.GET.get('user_id')
            
        # If not in GET, try POST data (for POST requests)
        if not user_id and request.method == 'POST':
            user_id = request.data.get('user_id')
        
        return user_id
    
    def get(self, request):
        """Get current user info for setup form"""
        user_id = self.get_user_id(request)
        
        if not user_id:
            return Response({
                'success': False,
                'message': _("Invalid access. Please login first.")
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({
                'success': False,
                'message': _("User not found.")
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if user has already completed setup
        if not user.is_first_login:
            return Response({
                'success': False,
                'message': _("You have already completed the setup.")
            }, status=status.HTTP_400_BAD_REQUEST)
        
        return Response({
            'success': True,
            'requires_setup': True,
            'user': {
                'id': user.id,
                'current_email': user.email,
                'current_username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'phone': user.phone or '',
                'address': user.address or '',
                'gender': user.gender or '',
            }
        })
    
    def post(self, request):
        """Handle first-time setup submission"""
        user_id = self.get_user_id(request)
        
        if not user_id:
            return Response({
                'success': False,
                'message': _("Invalid access. Please login first.")
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({
                'success': False,
                'message': _("User not found.")
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if user has already completed setup
        if not user.is_first_login:
            return Response({
                'success': False,
                'message': _("You have already completed the setup.")
            }, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = FirstTimeSetupSerializer(
            data=request.data,
            context={'user': user}
        )
        
        if serializer.is_valid():
            # Update user data
            data = serializer.validated_data
            
            # Update email if provided and different
            if data.get('email') and data['email'] != user.email:
                user.email = data['email']
            
            # Update username if provided and different
            if data.get('username') and data['username'] != user.username:
                user.username = data['username']
            
            # Update other fields
            user.first_name = data.get('first_name', user.first_name)
            user.last_name = data.get('last_name', user.last_name)
            user.phone = data.get('phone', user.phone)
            user.address = data.get('address', user.address)
            user.gender = data.get('gender', user.gender)
            
            # Update password
            if data.get('password'):
                user.set_password(data['password'])
            
            user.is_first_login = False
            user.save()
            
            # Clear the session variable
            if 'first_time_user_id' in request.session:
                del request.session['first_time_user_id']
            
            # Log the user in
            login(request, user, backend='accounts.backends.EmailOrUsernameModelBackend')

            request.session.save()
            
            # Create token for API authentication
            token, created = Token.objects.get_or_create(user=user)
            
            return Response({
                'success': True,
                'message': _("Your profile has been set up successfully!"),
                'token': token.key,
                'user': UserSerializer(user).data,
                'requires_setup': False
            }, status=status.HTTP_200_OK)
        
        return Response({
            'success': False,
            'errors': serializer.errors,
            'message': _("Please correct the errors below.")
        }, status=status.HTTP_400_BAD_REQUEST)


class SetupCompleteAPIView(APIView):
    """Mark setup as complete and redirect to dashboard"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        user = request.user
        user.is_first_login = False
        user.save()
        
        return Response({
            'success': True,
            'message': _('Setup completed successfully'),
            'user': UserSerializer(user).data
        })

class LogoutAPIView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        # Delete token if using token authentication
        try:
            request.user.auth_token.delete()
        except (AttributeError, Token.DoesNotExist):
            pass
        
        logout(request)
        return Response({
            'success': True,
            'message': _("Successfully logged out.")
        }, status=status.HTTP_200_OK)


# User Management APIs
class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('-date_joined')
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['email', 'username', 'first_name', 'last_name', 'phone']
    ordering_fields = ['date_joined', 'last_login', 'email', 'username']
    
    def get_permissions(self):
        """
        Allow different permissions based on the action
        """
        if self.action in ['list', 'retrieve']:
            # Allow any authenticated user to list/retrieve users
            permission_classes = [IsAuthenticated]
        elif self.action in ['create', 'update', 'partial_update', 'destroy']:
            # Only admins can create/update/delete users
            permission_classes = [IsAdminUser]
        else:
            # All other actions (profile, sessions, etc) require authentication
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        elif self.action in ['retrieve', 'update', 'partial_update']:
            return UserDetailSerializer
        return super().get_serializer_class()
    
    @action(detail=False, methods=['get'])
    def dashboard_stats(self, request):
        """Get dashboard statistics"""
        stats = {
            'total_users': User.objects.count(),
            'students': User.objects.filter(is_student=True).count(),
            'lecturers': User.objects.filter(is_lecturer=True).count(),
            'parents': User.objects.filter(is_parent=True).count(),
            'department_heads': User.objects.filter(is_dep_head=True).count(),
            'admins': User.objects.filter(is_superuser=True).count(),
            'active_users': User.objects.filter(is_active=True).count(),
            'inactive_users': User.objects.filter(is_active=False).count(),
            'first_login_pending': User.objects.filter(is_first_login=True).count(),
        }
        
        serializer = DashboardStatsSerializer(stats)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def filtered_list(self, request):
        """Get filtered users list"""
        filter_serializer = UserFilterSerializer(data=request.query_params)
        if not filter_serializer.is_valid():
            return Response({
                'success': False,
                'errors': filter_serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        data = filter_serializer.validated_data
        
        # Start with all users
        users = User.objects.all()
        
        # Apply search filter
        search = data.get('search', '')
        if search:
            users = users.filter(
                Q(username__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search) |
                Q(phone__icontains=search)
            )
        
        # Apply role filter
        role = data.get('role', '')
        if role == 'student':
            users = users.filter(is_student=True)
        elif role == 'lecturer':
            users = users.filter(is_lecturer=True)
        elif role == 'parent':
            users = users.filter(is_parent=True)
        elif role == 'dep_head':
            users = users.filter(is_dep_head=True)
        elif role == 'admin':
            users = users.filter(is_superuser=True)
        
        # Apply status filter
        status_filter = data.get('status', '')
        if status_filter == 'active':
            users = users.filter(is_active=True)
        elif status_filter == 'inactive':
            users = users.filter(is_active=False)
        
        # Apply first login filter
        first_login = data.get('first_login', '')
        if first_login == 'pending':
            users = users.filter(is_first_login=True)
        elif first_login == 'completed':
            users = users.filter(is_first_login=False)
        
        # Order by date joined (newest first)
        users = users.order_by('-date_joined')
        
        # Paginate
        page = data['page']
        per_page = data['per_page']
        paginator = Paginator(users, per_page)
        
        try:
            users_page = paginator.page(page)
        except:
            users_page = paginator.page(1)
        
        # Prepare response
        serializer = UserSerializer(users_page, many=True)
        
        return Response({
            'success': True,
            'users': serializer.data,
            'pagination': {
                'current_page': users_page.number,
                'total_pages': paginator.num_pages,
                'total_count': paginator.count,
                'has_previous': users_page.has_previous(),
                'has_next': users_page.has_next(),
                'per_page': per_page,
            },
            'filters': data
        })
    
    @action(detail=True, methods=['post'])
    def quick_actions(self, request, pk=None):
        """Quick actions for users"""
        user = self.get_object()
        action_type = request.data.get('action')
        
        if action_type == 'toggle_active':
            user.is_active = not user.is_active
            user.save()
            return Response({
                'success': True,
                'message': f'User {"activated" if user.is_active else "deactivated"} successfully',
                'is_active': user.is_active
            })
        
        elif action_type == 'reset_first_login':
            user.is_first_login = True
            user.save()
            return Response({
                'success': True,
                'message': 'User will be required to complete first-time setup on next login',
                'is_first_login': user.is_first_login
            })
        
        return Response({
            'success': False,
            'message': 'Invalid action'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def profile(self, request):
        """Get current user's profile"""
        serializer = UserDetailSerializer(request.user)
        return Response({
            'success': True,
            'profile': serializer.data
        })
    
    @action(detail=False, methods=['put', 'patch'])
    def update_profile(self, request):
        """Update current user's profile"""
        serializer = UserUpdateSerializer(
            request.user,
            data=request.data,
            partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response({
                'success': True,
                'message': _("Profile updated successfully."),
                'user': UserDetailSerializer(request.user).data
            })
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def change_password(self, request):
        """Change current user's password"""
        serializer = PasswordChangeSerializer(data=request.data)
        if serializer.is_valid():
            old_password = serializer.validated_data['old_password']
            new_password = serializer.validated_data['new_password']
            
            if not request.user.check_password(old_password):
                return Response({
                    'success': False,
                    'message': _("Old password is incorrect.")
                }, status=status.HTTP_400_BAD_REQUEST)
            
            request.user.set_password(new_password)
            request.user.save()
            
            # Update session auth hash to keep user logged in
            update_session_auth_hash(request, request.user)
            
            return Response({
                'success': True,
                'message': _("Password changed successfully.")
            })
        
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def sessions(self, request):
        """Get active sessions for the current user"""
        sessions = Session.objects.filter(expire_date__gt=timezone.now())
        user_sessions = []
        current_session_key = request.session.session_key

        for s in sessions:
            data = s.get_decoded()
            if data.get('_auth_user_id') == str(request.user.id):
                ua_string = data.get('user_agent', '')
                user_agent = user_agents.parse(ua_string) if ua_string else None
                
                session_info = {
                    'session_key': s.session_key,
                    'device': user_agent.device.family if user_agent else 'Unknown Device',
                    'browser': f"{user_agent.browser.family} {user_agent.browser.version_string}" if user_agent else 'Unknown Browser',
                    'os': f"{user_agent.os.family} {user_agent.os.version_string}" if user_agent else 'Unknown OS',
                    'ip': data.get('ip_address', 'Unknown'),
                    'expire_date': s.expire_date,
                    'current': s.session_key == current_session_key
                }
                user_sessions.append(session_info)

        serializer = UserSessionSerializer(user_sessions, many=True)
        return Response({
            'success': True,
            'sessions': serializer.data
        })

    @action(detail=False, methods=['post'])
    def terminate_session(self, request):
        """Terminate a specific session"""
        session_key = request.data.get('session_key')
        if not session_key:
            return Response({'success': False, 'message': 'Session key is required'}, status=400)
        
        try:
            session = Session.objects.get(session_key=session_key)
            data = session.get_decoded()
            if data.get('_auth_user_id') == str(request.user.id):
                session.delete()
                return Response({'success': True, 'message': 'Session terminated successfully'})
            else:
                return Response({'success': False, 'message': 'Unauthorized'}, status=403)
        except Session.DoesNotExist:
            return Response({'success': False, 'message': 'Session not found'}, status=404)

    @action(detail=False, methods=['post'])
    def upload_avatar(self, request):
        """Upload user avatar"""
        if 'avatar' not in request.FILES:
            return Response({
                'success': False, 
                'message': 'No avatar file provided'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user = request.user
        user.picture = request.FILES['avatar']
        user.save()
        
        # Log the activity
        from .models import Activity
        Activity.log_activity(
            user=user,
            activity_type='avatar_upload',
            request=request,
            description=f'Avatar uploaded: {request.FILES["avatar"].name}'
        )
        
        return Response({
            'success': True,
            'message': 'Avatar uploaded successfully',
            'picture_url': user.picture.url if user.picture else None
        })

    @action(detail=False, methods=['post'])
    def logout_all(self, request):
        """Terminate all active sessions for current user"""
        sessions = Session.objects.filter(expire_date__gt=timezone.now())
        count = 0
        
        for s in sessions:
            try:
                data = s.get_decoded()
                if data.get('_auth_user_id') == str(request.user.id):
                    s.delete()
                    count += 1
            except:
                pass
        
        # Log the activity
        from .models import Activity
        Activity.log_activity(
            user=request.user,
            activity_type='logout',
            request=request,
            description=f'Logged out from {count} sessions'
        )
        
        # Also flush current session
        request.session.flush()
        
        return Response({
            'success': True,
            'message': f'Successfully logged out from {count} sessions'
        })

    @action(detail=False, methods=['get'])
    def activities(self, request):
        """Get user activity log"""
        from .models import Activity
        from .serializers import ActivitySerializer
        
        # Get query parameters for filtering
        activity_type = request.query_params.get('type', None)
        limit = int(request.query_params.get('limit', 20))
        
        # Build queryset
        activities = Activity.objects.filter(user=request.user)
        
        if activity_type:
            activities = activities.filter(activity_type=activity_type)
        
        # Limit results
        activities = activities[:limit]
        
        serializer = ActivitySerializer(activities, many=True)
        return Response({
            'success': True,
            'activities': serializer.data,
            'count': len(serializer.data)
        })


class ForgotPasswordAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            user = User.objects.get(email__iexact=email)
            
            # Generate 6-digit OTP
            code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
            expires_at = timezone.now() + timedelta(minutes=10)
            
            # Save OTP
            OTP.objects.create(user=user, code=code, expires_at=expires_at)
            
            # Send Email
            context = {
                'user': user,
                'otp': code,
                'expires_in': 10
            }
            try:
                send_html_email(
                    subject="Password Reset OTP",
                    recipient_list=[email],
                    template="accounts/email/password_reset_otp.html",
                    context=context
                )
            except Exception as e:
                logger.error(f"Failed to send OTP email: {e}")
                return Response({'success': False, 'message': 'Failed to send OTP email.'}, status=500)
            
            return Response({'success': True, 'message': 'OTP sent to your email.'})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class VerifyOTPAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            code = serializer.validated_data['code']
            
            otp = OTP.objects.filter(
                user__email__iexact=email, 
                code=code, 
                is_used=False
            ).last()
            
            if otp and not otp.is_expired():
                return Response({'success': True, 'message': 'OTP verified.'})
            
            return Response({'success': False, 'message': 'Invalid or expired OTP.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ResetPasswordAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            code = serializer.validated_data['code']
            password = serializer.validated_data['password']
            
            otp = OTP.objects.filter(
                user__email__iexact=email, 
                code=code, 
                is_used=False
            ).last()
            
            if otp and not otp.is_expired():
                user = otp.user
                user.set_password(password)
                user.save()
                
                # Mark OTP as used
                otp.is_used = True
                otp.save()
                
                return Response({'success': True, 'message': 'Password reset successfully.'})
            
            return Response({'success': False, 'message': 'Invalid or expired OTP.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)




# Utility APIs
class ValidateEmailAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        email = request.GET.get('email', '').strip()
        if not email:
            return Response({
                'is_taken': False,
                'message': _("Email is required.")
            }, status=status.HTTP_400_BAD_REQUEST)
        
        is_taken = User.objects.filter(email__iexact=email).exists()
        return Response({
            'is_taken': is_taken,
            'message': _("Email already registered.") if is_taken else _("Email is available.")
        })


class ValidateUsernameAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        username = request.GET.get('username', '').strip()
        if not username:
            return Response({
                'is_taken': False,
                'message': _("Username is required.")
            }, status=status.HTTP_400_BAD_REQUEST)
        
        is_taken = User.objects.filter(username__iexact=username).exists()
        return Response({
            'is_taken': is_taken,
            'message': _("Username already taken.") if is_taken else _("Username is available.")
        })


# Registration API
class RegisterAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        # Use UserCreateSerializer for registration
        serializer = UserCreateSerializer(data=request.data)
        
        if serializer.is_valid():
            user = serializer.save()
            
            # You might want to log the user in automatically
            # login(request, user)
            
            return Response({
                'success': True,
                'message': _("Account created successfully. Please login to continue."),
                'user': UserSerializer(user).data
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


# Role (Group) Management
class RoleViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows Roles (Groups) to be viewed or edited.
    Only accessible by Admin Users.
    """
    queryset = Group.objects.all()
    serializer_class = GroupSerializer
    permission_classes = [IsAdminUser]
    
    def get_queryset(self):
        return Group.objects.annotate(user_count=Count('user')).order_by('name')

class PermissionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint that allows Permissions to be viewed.
    Only accessible by Admin Users.
    """
    queryset = Permission.objects.all().order_by('content_type__app_label', 'codename')
    serializer_class = PermissionSerializer
    permission_classes = [IsAdminUser]
    pagination_class = None  # Return all permissions at once for the matrix
