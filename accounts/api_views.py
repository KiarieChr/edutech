# accounts/api_views.py
from rest_framework import status, viewsets, generics, permissions, filters
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.authtoken.models import Token
from .authentication import UserTokenAuthentication
from .models import UserToken
from rest_framework.pagination import PageNumberPagination
from django.contrib.auth import update_session_auth_hash, login, authenticate, logout
from django.contrib.sessions.models import Session

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Q, F, When, Case, IntegerField, Sum
from django.db.models.functions import TruncMonth, TruncDay, TruncWeek
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from django.utils import timezone
import calendar
import logging

from .models import User, Activity
from student_management.models import Student, Parent
from django.contrib.auth.models import Group, Permission
from .serializers import (
    StudentSerializer,
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
    API endpoint for admin dashboard statistics.
    All data is fetched from the database — nothing is mocked.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = timezone.now().date()
        now = timezone.now()

        # ── helpers ──────────────────────────────────────────────
        def _fmt(val):
            """Human‑readable currency shorthand."""
            if val is None:
                return "0"
            val = float(val)
            if val >= 1_000_000:
                return f"{val / 1_000_000:.1f}M"
            if val >= 1_000:
                return f"{val / 1_000:.0f}K"
            return f"{val:,.0f}"

        ACTIVITY_ICON_MAP = {
            'login': 'user-check', 'logout': 'user-check',
            'profile_update': 'users', 'avatar_upload': 'users',
            'password_change': 'bell', 'permission_change': 'bell',
            'failed_login': 'alert-triangle', 'account_locked': 'alert-triangle',
            'account_unlocked': 'check', 'email_verification': 'check',
            'session_terminate': 'clock',
        }
        ACTIVITY_COLOR_MAP = {
            'login': '#e3f2fd', 'logout': '#e3f2fd',
            'profile_update': '#e8f5e9', 'avatar_upload': '#e8f5e9',
            'password_change': '#fff3e0', 'permission_change': '#fff3e0',
            'failed_login': '#ffebee', 'account_locked': '#ffebee',
            'account_unlocked': '#e8f5e9', 'email_verification': '#e8f5e9',
            'session_terminate': '#f3e5f5',
        }
        EVENT_COLORS = ['#4caf50', '#2196f3', '#009688', '#f44336', '#ff9800', '#9c27b0']

        # ── 1. stat cards ────────────────────────────────────────
        total_students = Student.objects.count()
        active_students = Student.objects.filter(status='active').count()

        # Attendance
        try:
            from student_management.models.class_session import SessionAttendance
            att_today = SessionAttendance.objects.filter(date=today).count()
            att_present = SessionAttendance.objects.filter(date=today, status='present').count()
            attendance_pct = round(att_present / att_today * 100, 1) if att_today else 0.0
        except Exception:
            attendance_pct = 0.0

        # Fees
        try:
            from fees.models import FeeInvoice
            month_start = today.replace(day=1)
            paid_this_month = FeeInvoice.objects.filter(
                updated_at__date__gte=month_start
            ).aggregate(t=Sum('paid_amount'))['t'] or 0
            fee_defaulters = FeeInvoice.objects.filter(
                balance__gt=0
            ).values('student').distinct().count()
        except Exception:
            paid_this_month = 0
            fee_defaulters = 0

        # Staff
        try:
            from workforce.core_models import Employee
            total_staff = Employee.objects.count()
            active_staff = Employee.objects.filter(employment_status='active').count()
        except Exception:
            total_staff = 0
            active_staff = 0

        # Departments
        try:
            from workforce.models import Department
            dept_count = Department.objects.count()
        except Exception:
            dept_count = 0

        # New students this month
        month_start_dt = today.replace(day=1)
        new_students_month = Student.objects.filter(
            admission_date__gte=month_start_dt
        ).count()

        stats = [
            {"title": "Total Students", "count": f"{total_students:,}", "trend": 0,
             "trendLabel": "enrolled students", "icon": "users",
             "color": "#e3f2fd", "iconColor": "#2196f3"},
            {"title": "Today's Attendance", "count": f"{attendance_pct}%", "trend": 0,
             "trendLabel": "present today", "icon": "user-check",
             "color": "#e8f5e9", "iconColor": "#4caf50"},
            {"title": "Fee Collection", "count": f"KES {_fmt(paid_this_month)}", "trend": 0,
             "trendLabel": "this month", "icon": "credit-card",
             "color": "#fff3e0", "iconColor": "#ff9800"},
            {"title": "Fee Defaulters", "count": str(fee_defaulters), "trend": 0,
             "trendLabel": "outstanding balance", "icon": "alert-triangle",
             "color": "#ffebee", "iconColor": "#f44336"},
            # ── secondary stats ──
            {"title": "Active Students", "count": f"{active_students:,}", "trend": 0,
             "trendLabel": "currently active", "icon": "users",
             "color": "#e0f2f1", "iconColor": "#009688"},
            {"title": "New This Month", "count": str(new_students_month), "trend": 0,
             "trendLabel": "admissions", "icon": "user-plus",
             "color": "#e8eaf6", "iconColor": "#3f51b5"},
            {"title": "Total Staff", "count": str(total_staff), "trend": 0,
             "trendLabel": f"{active_staff} active", "icon": "users",
             "color": "#fce4ec", "iconColor": "#e91e63"},
            {"title": "Departments", "count": str(dept_count), "trend": 0,
             "trendLabel": "organisational units", "icon": "book",
             "color": "#f3e5f5", "iconColor": "#9c27b0"},
        ]

        # ── 2. charts ───────────────────────────────────────────
        # Weekly attendance
        week_start = today - timedelta(days=today.weekday())
        weekly_attendance = []
        for i, label in enumerate(['Mon', 'Tue', 'Wed', 'Thu', 'Fri']):
            day_date = week_start + timedelta(days=i)
            try:
                from student_management.models.class_session import SessionAttendance
                present = SessionAttendance.objects.filter(date=day_date, status='present').count()
                absent = SessionAttendance.objects.filter(date=day_date, status='absent').count()
            except Exception:
                present, absent = 0, 0
            weekly_attendance.append({"name": label, "present": present, "absent": absent})

        # Fee collection pie (current term)
        current_term_name = "Current Term"
        fee_collected_val = fee_pending_val = fee_overdue_val = 0.0
        try:
            from fees.models import FeeInvoice
            from student_settings.models import Term
            current_term = Term.objects.filter(is_current=True).select_related('academic_year').first()
            if current_term:
                current_term_name = f"{current_term.name}, {current_term.academic_year.name}"
                inv_qs = FeeInvoice.objects.filter(term=current_term)
            else:
                inv_qs = FeeInvoice.objects.all()
            agg = inv_qs.aggregate(collected=Sum('paid_amount'), billed=Sum('total_amount'))
            billed = float(agg['billed'] or 0)
            fee_collected_val = float(agg['collected'] or 0)
            fee_pending_val = max(0.0, round(billed - fee_collected_val, 2))
            # Overdue = balance on invoices past due date
            fee_overdue_val = float(
                inv_qs.filter(due_date__lt=today, balance__gt=0)
                .aggregate(t=Sum('balance'))['t'] or 0
            )
        except Exception:
            pass

        fee_collection_chart = [
            {"name": "Collected", "value": fee_collected_val, "color": "#4caf50"},
            {"name": "Pending", "value": fee_pending_val, "color": "#ff9800"},
            {"name": "Overdue", "value": fee_overdue_val, "color": "#f44336"},
        ]

        # Performance chart — average marks per subject (latest published exams)
        performance_data = []
        try:
            from examinations.models import TermSubjectResult
            from django.db.models import Avg
            subj_avgs = (
                TermSubjectResult.objects
                .filter(term_result__is_published=True)
                .values('subject__name')
                .annotate(avg_mark=Avg('weighted_mark'))
                .order_by('-avg_mark')[:10]
            )
            for row in subj_avgs:
                performance_data.append({
                    "subject": row['subject__name'],
                    "score": round(float(row['avg_mark'] or 0), 1),
                    "average": round(float(row['avg_mark'] or 0), 1),
                    "max": 100,
                })
        except Exception:
            pass

        # Enrollment chart — monthly new students for the last 6 months
        enrollment_data = []
        try:
            six_months_ago = today - timedelta(days=180)
            monthly = (
                Student.objects
                .filter(admission_date__gte=six_months_ago)
                .annotate(month=TruncMonth('admission_date'))
                .values('month')
                .annotate(count=Count('id'))
                .order_by('month')
            )
            # Build a complete 6‑month series
            for offset in range(6):
                m = (today.replace(day=1) - relativedelta(months=5 - offset))
                label = m.strftime('%b')
                actual = 0
                for row in monthly:
                    if row['month'] and row['month'].month == m.month and row['month'].year == m.year:
                        actual = row['count']
                        break
                enrollment_data.append({
                    "month": label,
                    "enrollments": actual,
                    "target": 0,
                })
        except Exception:
            pass

        # ── 3. recent activity (from DB) ─────────────────────────
        recent_activity = []
        try:
            activities = Activity.objects.select_related('user').order_by('-timestamp')[:8]
            for act in activities:
                delta = now - act.timestamp
                if delta.days > 0:
                    time_ago = f"{delta.days} day{'s' if delta.days > 1 else ''} ago"
                elif delta.seconds >= 3600:
                    hrs = delta.seconds // 3600
                    time_ago = f"{hrs} hour{'s' if hrs > 1 else ''} ago"
                elif delta.seconds >= 60:
                    mins = delta.seconds // 60
                    time_ago = f"{mins} minute{'s' if mins > 1 else ''} ago"
                else:
                    time_ago = "just now"
                user_name = act.user.get_full_name() or act.user.username if act.user else "System"
                recent_activity.append({
                    "id": act.id,
                    "title": act.get_activity_type_display() if hasattr(act, 'get_activity_type_display') else act.activity_type.replace('_', ' ').title(),
                    "desc": act.description or f"{user_name} — {act.activity_type}",
                    "time": time_ago,
                    "icon": ACTIVITY_ICON_MAP.get(act.activity_type, 'bell'),
                    "color": ACTIVITY_COLOR_MAP.get(act.activity_type, '#e3f2fd'),
                })
        except Exception:
            pass

        # ── 4. upcoming events (from DB) ─────────────────────────
        upcoming_events = []
        try:
            from core.models import NewsAndEvents
            events_qs = (
                NewsAndEvents.objects
                .filter(posted_as='Event')
                .order_by('-updated_date')[:6]
            )
            for idx, evt in enumerate(events_qs):
                dt = evt.updated_date or evt.upload_time
                upcoming_events.append({
                    "id": evt.id,
                    "title": evt.title,
                    "date": dt.strftime('%b %d, %Y') if dt else '',
                    "time": dt.strftime('%I:%M %p') if dt else '',
                    "location": '',
                    "color": EVENT_COLORS[idx % len(EVENT_COLORS)],
                })
        except Exception:
            pass

        # ── 5. resource usage (real counts) ──────────────────────
        active_users = User.objects.filter(is_active=True).count()
        total_users = User.objects.count()
        resource_usage = {
            "storage": {"used": 0, "total": 0, "unit": "GB"},
            "bandwidth": {"used": 0, "total": 0, "unit": "GB"},
            "activeUsers": {"count": active_users, "total": total_users},
            "serverLoad": {"percentage": 0},
        }

        # ── response ────────────────────────────────────────────
        user_data = UserSerializer(request.user).data if request.user.is_authenticated else {
            'id': 0, 'username': 'Guest', 'email': '', 'first_name': 'Guest', 'last_name': 'User'
        }

        return Response({
            'success': True,
            'data': {
                "stats": stats,
                "isAuthenticated": request.user.is_authenticated,
                "user": user_data,
                "charts": {
                    "weekly_attendance": weekly_attendance,
                    "fee_collection": fee_collection_chart,
                    "current_term": current_term_name,
                    "performance": performance_data,
                    "enrollment": enrollment_data,
                },
                "recent_activity": recent_activity,
                "upcoming_events": upcoming_events,
                "resource_usage": resource_usage,
            },
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
                user_token = UserToken.create_for_user(user, request)
                return Response({
                    'success': True,
                    'message': _("Welcome! Please complete your profile setup to continue."),
                    'requires_setup': True,
                    'token': user_token.key,
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

            
            user_token = UserToken.create_for_user(user, request)
            
            return Response({
                'success': True,
                'message': _("Welcome back, {}!").format(user.get_full_name),
                'token': user_token.key,
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
    
    @staticmethod
    def generate_default_email(user):
        """Generate a unique default email from the user's name/username."""
        import re
        base = user.username or ''
        if user.first_name:
            base = user.first_name.lower()
            if user.last_name:
                base = f"{base}.{user.last_name.lower()}"
        # Sanitize: keep only alphanumeric, dots, hyphens
        base = re.sub(r'[^a-z0-9.\-]', '', base) or f"user{user.pk}"
        candidate = f"{base}@fahari.academy"
        # Ensure uniqueness
        counter = 1
        while User.objects.filter(email__iexact=candidate).exclude(pk=user.pk).exists():
            candidate = f"{base}{counter}@fahari.academy"
            counter += 1
        return candidate
    
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
        
        # Check if current email conflicts with another user
        current_email = user.email or ''
        email_conflict = False
        suggested_email = current_email
        if current_email and User.objects.filter(email__iexact=current_email).exclude(pk=user.pk).exists():
            email_conflict = True
            suggested_email = self.generate_default_email(user)
        elif not current_email:
            suggested_email = self.generate_default_email(user)
        
        return Response({
            'success': True,
            'requires_setup': True,
            'email_conflict': email_conflict,
            'user': {
                'id': user.id,
                'current_email': suggested_email,
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
            
            # Update email - auto-generate if blank/missing
            email = (data.get('email') or '').strip()
            if email and email != user.email:
                user.email = email
            elif not email:
                user.email = self.generate_default_email(user)
            
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
            user_token = UserToken.create_for_user(user, request)
            
            return Response({
                'success': True,
                'message': _("Your profile has been set up successfully!"),
                'token': user_token.key,
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
        # Revoke the current UserToken (per-session token)
        auth = request.auth
        if isinstance(auth, UserToken):
            auth.delete()
        else:
            # Fallback: delete legacy DRF token if present
            try:
                request.user.auth_token.delete()
            except (AttributeError, Token.DoesNotExist):
                pass
        
        logout(request)
        Activity.log_activity(
            user=request.user,
            activity_type='logout',
            request=request,
            description='User logged out',
        )
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

    def get_queryset(self):
        qs = super().get_queryset()
        
        # Status filtering
        status_param = self.request.query_params.get('status')
        is_active = self.request.query_params.get('is_active')
        
        if status_param:
            if status_param.lower() == 'active':
                qs = qs.filter(is_active=True)
            elif status_param.lower() == 'inactive':
                qs = qs.filter(is_active=False)
        elif is_active is not None:
            qs = qs.filter(is_active=is_active.lower() in ('true', '1'))
            
        # Role filtering
        role = self.request.query_params.get('role')
        if role and role.lower() != 'all':
            role_l = role.lower()
            if role_l == 'student':
                qs = qs.filter(is_student=True)
            elif role_l == 'lecturer' or role_l == 'teacher':
                qs = qs.filter(is_lecturer=True)
            elif role_l == 'parent':
                qs = qs.filter(is_parent=True)
            elif role_l == 'admin':
                qs = qs.filter(is_superuser=True)
            else:
                # Try filtering by Group name
                qs = qs.filter(groups__name__icontains=role)
                
        # First login filtering
        is_first_login = self.request.query_params.get('is_first_login')
        if is_first_login is not None:
            qs = qs.filter(is_first_login=is_first_login.lower() in ('true', '1'))
            
        return qs.distinct()
    
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
        """Get active sessions for the current user (one UserToken per login)."""
        from django.utils import timezone
        from datetime import timedelta
        
        current_token_id = request.auth.id if isinstance(request.auth, UserToken) else None
        client_ip = Activity.get_client_ip(request)

        # Prune sessions older than 4 hours automatically
        four_hours_ago = timezone.now() - timedelta(hours=4)
        UserToken.objects.filter(user=request.user, last_used__lt=four_hours_ago).exclude(id=current_token_id).delete()

        tokens = UserToken.objects.filter(user=request.user)
        user_sessions = [
            {
                'id': t.id,
                'session_key': str(t.id),  # kept for frontend compat
                'device': t.device or 'Unknown Device',
                'browser': t.browser or 'Unknown Browser',
                'os': t.os or 'Unknown OS',
                'ip': t.ip_address or 'Unknown',
                'created_at': t.created_at,
                'last_used': t.last_used,
                'expire_date': t.last_used,  # alias for legacy serializer field
                'current': t.id == current_token_id,
                'label': t.label,
                'is_same_network': bool(client_ip and t.ip_address == client_ip),
            }
            for t in tokens
        ]

        return Response({
            'success': True,
            'sessions': user_sessions,
        })

    @action(detail=False, methods=['post'])
    def terminate_session(self, request):
        """Terminate a specific UserToken session."""
        token_id = request.data.get('token_id') or request.data.get('session_key')
        if not token_id:
            return Response({'success': False, 'message': 'token_id is required'}, status=400)
        
        deleted, _ = UserToken.objects.filter(id=token_id, user=request.user).delete()
        if deleted:
            Activity.log_activity(
                user=request.user,
                activity_type='session_terminate',
                request=request,
                description=f'Session {token_id} terminated',
            )
            return Response({'success': True, 'message': 'Session terminated successfully'})
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
        """Terminate ALL UserToken sessions for the current user."""
        current_token_id = request.auth.id if isinstance(request.auth, UserToken) else None
        qs = UserToken.objects.filter(user=request.user)
        count = qs.count()
        qs.delete()
        
        Activity.log_activity(
            user=request.user,
            activity_type='logout',
            request=request,
            description=f'Logged out from all {count} sessions',
        )
        
        logout(request)
        
        return Response({
            'success': True,
            'message': f'Successfully logged out from {count} sessions',
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

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def assign_roles(self, request, pk=None):
        """Assign roles (groups) to a user. Expects { group_ids: [1, 2, 3] }"""
        user = self.get_object()
        group_ids = request.data.get('group_ids', [])
        groups = Group.objects.filter(id__in=group_ids)
        user.groups.set(groups)
        return Response({
            'success': True,
            'message': f'Roles updated for {user.get_full_name or user.username}',
            'groups': GroupSerializer(user.groups.all(), many=True).data
        })

    @action(detail=True, methods=['get', 'post'], permission_classes=[IsAdminUser])
    def user_permissions(self, request, pk=None):
        """GET: list all permissions for user. POST: assign direct permissions. { permission_ids: [...] }"""
        user = self.get_object()
        if request.method == 'GET':
            all_perms = user.get_all_permissions()
            group_perms = user.get_group_permissions()
            direct_perms = PermissionSerializer(user.user_permissions.all(), many=True).data
            return Response({
                'all_permissions': sorted(list(all_perms)),
                'group_permissions': sorted(list(group_perms)),
                'direct_permissions': direct_perms,
            })
        else:
            perm_ids = request.data.get('permission_ids', [])
            perms = Permission.objects.filter(id__in=perm_ids)
            user.user_permissions.set(perms)
            return Response({
                'success': True,
                'message': f'Permissions updated for {user.get_full_name or user.username}',
                'direct_permissions': PermissionSerializer(user.user_permissions.all(), many=True).data
            })

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def link_employee(self, request, pk=None):
        """Link an existing HR Employee profile to this user"""
        user = self.get_object()
        employee_id = request.data.get('employee_id')
        
        if not employee_id:
            return Response({'success': False, 'message': 'employee_id is required'}, status=400)
            
        try:
            from workforce.core_models import Employee
            employee = Employee.objects.get(id=employee_id)
            if employee.user and employee.user.id != user.id:
                return Response({'success': False, 'message': 'This employee is already linked to another user'}, status=400)
                
            # If user is already linked to another employee, unlink it first
            Employee.objects.filter(user=user).update(user=None)
            
            employee.user = user
            employee.save(update_fields=['user'])
            
            return Response({
                'success': True, 
                'message': f'Successfully linked {employee.get_full_name()} to {user.username}'
            })
        except Exception as e:
            return Response({'success': False, 'message': 'Employee not found or linking failed'}, status=404)


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


class CheckGuardianEmailAPIView(APIView):
    """Check if a guardian/parent account already exists for the given email."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        email = request.GET.get('email', '').strip()
        if not email:
            return Response({
                'exists': False,
                'message': 'Email is required.'
            }, status=status.HTTP_400_BAD_REQUEST)

        from student_management.models import Parent
        parent = Parent.objects.select_related('user', 'student').filter(
            user__email__iexact=email, user__is_parent=True
        ).first()

        if parent:
            return Response({
                'exists': True,
                'parent_user_id': parent.user.id,
                'parent_name': f"{parent.first_name} {parent.last_name}".strip(),
                'parent_email': parent.user.email,
                'parent_phone': parent.phone or '',
                'linked_students': list(
                    Parent.objects.filter(user=parent.user)
                    .values_list('student__admission_number', flat=True)
                ),
                'message': 'A parent account with this email already exists.'
            })

        return Response({
            'exists': False,
            'message': 'No existing parent account found for this email.'
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

    @action(detail=True, methods=['get'])
    def members(self, request, pk=None):
        """Get all users in this role"""
        role = self.get_object()
        users = role.user_set.all().order_by('first_name', 'last_name')
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def add_members(self, request, pk=None):
        """Add users to a role. Expects { user_ids: [1, 2, 3] }"""
        role = self.get_object()
        user_ids = request.data.get('user_ids', [])
        users = User.objects.filter(id__in=user_ids)
        role.user_set.add(*users)
        return Response({
            'success': True,
            'message': f'{users.count()} user(s) added to {role.name}'
        })

    @action(detail=True, methods=['post'])
    def remove_members(self, request, pk=None):
        """Remove users from a role. Expects { user_ids: [1, 2, 3] }"""
        role = self.get_object()
        user_ids = request.data.get('user_ids', [])
        users = User.objects.filter(id__in=user_ids)
        role.user_set.remove(*users)
        return Response({
            'success': True,
            'message': f'{users.count()} user(s) removed from {role.name}'
        })

class PermissionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint that allows Permissions to be viewed.
    Only accessible by Admin Users.
    """
    queryset = Permission.objects.all().order_by('content_type__app_label', 'codename')
    serializer_class = PermissionSerializer
    permission_classes = [IsAdminUser]
    pagination_class = None  # Return all permissions at once for the matrix

class StudentViewSet(viewsets.ModelViewSet):
    queryset = Student.objects.all().select_related('student', 'intake', 'campus').order_by('-student__date_joined')
    serializer_class = StudentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['student__first_name', 'student__last_name', 'student__email', 'admission_number']
    ordering_fields = ['student__date_joined', 'student__first_name', 'admission_number']
