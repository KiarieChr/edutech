# accounts/api_views.py
from rest_framework import status, viewsets, generics, permissions, filters
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.pagination import PageNumberPagination
from django.contrib.auth import update_session_auth_hash, login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.core.paginator import Paginator
from django.db.models import Count, Q, F, When, Case, IntegerField
from django.db.models.functions import TruncMonth, TruncDay, TruncWeek
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from django.utils import timezone
import calendar
import logging

from .models import User, Student, Parent
from .serializers import (
    UserSerializer, UserDetailSerializer, UserCreateSerializer,
    UserUpdateSerializer, LoginSerializer, EmailLoginSerializer,
    FirstTimeSetupSerializer, PasswordChangeSerializer,
    DashboardStatsSerializer, UserFilterSerializer,DashboardStatsSerializer
)

logger = logging.getLogger(__name__)



class DashboardStatsAPIView(APIView):
    """
    API endpoint for users dashboard statistics.
    Returns comprehensive statistics for the admin dashboard.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def get(self, request):
        """
        Get dashboard statistics with optional date filters.
        
        Query Parameters:
        - period: 'today', 'week', 'month', 'year', 'all' (default: 'all')
        - start_date: Custom start date (YYYY-MM-DD)
        - end_date: Custom end date (YYYY-MM-DD)
        """
        # Get query parameters
        period = request.query_params.get('period', 'all')
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        
        # Initialize date filters
        date_filter = Q()
        
        # Apply period filter
        now = timezone.now()
        if period == 'today':
            date_filter = Q(date_joined__date=now.date())
        elif period == 'week':
            week_start = now - timedelta(days=now.weekday())
            date_filter = Q(date_joined__date__gte=week_start.date())
        elif period == 'month':
            date_filter = Q(date_joined__year=now.year, date_joined__month=now.month)
        elif period == 'year':
            date_filter = Q(date_joined__year=now.year)
        elif period == 'custom' and start_date_str and end_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                date_filter = Q(date_joined__date__gte=start_date, date_joined__date__lte=end_date)
            except ValueError:
                pass
        
        # 1. User Statistics
        total_users = User.objects.filter(date_filter).count()
        active_users = User.objects.filter(date_filter, is_active=True).count()
        inactive_users = User.objects.filter(date_filter, is_active=False).count()
        
        # User roles statistics
        students = User.objects.filter(date_filter, is_student=True).count()
        lecturers = User.objects.filter(date_filter, is_lecturer=True).count()
        parents = User.objects.filter(date_filter, is_parent=True).count()
        department_heads = User.objects.filter(date_filter, is_dep_head=True).count()
        admins = User.objects.filter(date_filter, is_superuser=True).count()
        
        # First login status
        first_login_pending = User.objects.filter(date_filter, is_first_login=True).count()
        first_login_completed = User.objects.filter(date_filter, is_first_login=False).count()
        
        # 2. Registration Trends
        # Last 12 months registration trend
        twelve_months_ago = now - relativedelta(months=11)
        monthly_registrations = User.objects.filter(
            date_joined__gte=twelve_months_ago
        ).annotate(
            month=TruncMonth('date_joined')
        ).values('month').annotate(
            count=Count('id')
        ).order_by('month')
        
        # Format monthly data
        monthly_data = []
        for i in range(12):
            month_date = (now - relativedelta(months=i)).replace(day=1)
            month_str = month_date.strftime('%b %Y')
            
            # Find count for this month
            count = 0
            for item in monthly_registrations:
                if item['month'].replace(day=1) == month_date.replace(day=1):
                    count = item['count']
                    break
            
            monthly_data.append({
                'month': month_str,
                'count': count,
                'date': month_date.strftime('%Y-%m')
            })
        
        monthly_data.reverse()  # Show oldest to newest
        
        # Last 7 days registration trend
        week_ago = now - timedelta(days=6)
        daily_registrations = User.objects.filter(
            date_joined__date__gte=week_ago.date()
        ).annotate(
            day=TruncDay('date_joined')
        ).values('day').annotate(
            count=Count('id')
        ).order_by('day')
        
        # Format daily data
        daily_data = []
        for i in range(7):
            day_date = (now - timedelta(days=i)).date()
            day_str = day_date.strftime('%a')
            
            # Find count for this day
            count = 0
            for item in daily_registrations:
                if item['day'].date() == day_date:
                    count = item['count']
                    break
            
            daily_data.append({
                'day': day_str,
                'date': day_date.strftime('%Y-%m-%d'),
                'count': count
            })
        
        daily_data.reverse()  # Show oldest to newest
        
        # 3. User Activity
        # Users with recent login (last 7 days)
        recent_login_threshold = now - timedelta(days=7)
        active_recently = User.objects.filter(
            last_login__gte=recent_login_threshold
        ).count()
        
        # Users never logged in
        never_logged_in = User.objects.filter(last_login__isnull=True).count()
        
        # 4. Gender Statistics
        gender_stats = User.objects.filter(date_filter).values('gender').annotate(
            count=Count('id')
        ).order_by('gender')
        
        gender_data = {
            'M': 0,
            'F': 0,
            'unknown': 0
        }
        
        for stat in gender_stats:
            if stat['gender'] == 'M':
                gender_data['M'] = stat['count']
            elif stat['gender'] == 'F':
                gender_data['F'] = stat['count']
        
        gender_data['unknown'] = total_users - (gender_data['M'] + gender_data['F'])
        
        # 5. Top performing metrics
        # Most active users (by login count - if you track this)
        # For now, we'll use recent login as proxy
        
        # 6. User growth rate
        # Current month vs previous month
        current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        prev_month_start = (current_month_start - relativedelta(months=1))
        prev_month_end = current_month_start - timedelta(seconds=1)
        
        current_month_users = User.objects.filter(
            date_joined__gte=current_month_start
        ).count()
        
        prev_month_users = User.objects.filter(
            date_joined__gte=prev_month_start,
            date_joined__lt=current_month_start
        ).count()
        
        # Calculate growth rate
        if prev_month_users > 0:
            growth_rate = ((current_month_users - prev_month_users) / prev_month_users) * 100
        else:
            growth_rate = 100 if current_month_users > 0 else 0
        
        # 7. User status breakdown
        status_breakdown = {
            'active': User.objects.filter(is_active=True).count(),
            'inactive': User.objects.filter(is_active=False).count(),
            'verified': User.objects.filter(is_active=True, is_first_login=False).count(),
            'pending_setup': first_login_pending,
        }
        
        # 8. Recent users (last 5)
        recent_users = User.objects.order_by('-date_joined')[:5].values(
            'id', 'username', 'email', 'first_name', 'last_name',
            'date_joined', 'last_login', 'is_active'
        )
        
        # 9. Student specific statistics (if needed)
        student_stats = {}
        if students > 0:
            # Get student levels distribution
            student_levels = Student.objects.filter(
                student__date_joined__filter=date_filter if date_filter else Q()
            ).values('level').annotate(
                count=Count('id')
            ).order_by('level')
            
            student_stats['levels'] = list(student_levels)
            
            # Students with parent accounts
            students_with_parents = Student.objects.filter(
                parent__isnull=False
            ).count()
            student_stats['with_parents'] = students_with_parents
            student_stats['without_parents'] = students - students_with_parents
        
        # 10. Lecturer specific statistics (if needed)
        lecturer_stats = {}
        if lecturers > 0:
            # You could add department distribution here
            pass
        
        # Prepare response data
        response_data = {
            'summary': {
                'total_users': total_users,
                'active_users': active_users,
                'inactive_users': inactive_users,
                'users_active_recently': active_recently,
                'users_never_logged_in': never_logged_in,
                'monthly_growth_rate': round(growth_rate, 2),
            },
            
            'role_distribution': {
                'students': students,
                'lecturers': lecturers,
                'parents': parents,
                'department_heads': department_heads,
                'admins': admins,
                'first_login_pending': first_login_pending,
                'first_login_completed': first_login_completed,
            },
            
            'gender_distribution': gender_data,
            
            'status_breakdown': status_breakdown,
            
            'registration_trends': {
                'monthly': monthly_data,
                'daily': daily_data,
                'current_month': current_month_users,
                'previous_month': prev_month_users,
            },
            
            'recent_activity': {
                'recent_users': list(recent_users),
                'period': period,
                'start_date': start_date_str,
                'end_date': end_date_str,
            },
            
            'student_statistics': student_stats,
            'lecturer_statistics': lecturer_stats,
            
            'timestamps': {
                'generated_at': now.isoformat(),
                'period_applied': period,
            }
        }
        
        return Response({
            'success': True,
            'data': response_data,
            'message': _('Dashboard statistics retrieved successfully')
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
    
    def post(self, request):
        # Accept both email_or_username format or email-only format

        logger.info(f"Login request data: {request.data}")
        logger.info(f"Login request content type: {request.content_type}")
        logger.info(f"Login request headers: {dict(request.headers)}")
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
            login(request, user)
            
            # Get or create token for API authentication
            token, created = Token.objects.get_or_create(user=user)
            
            return Response({
                'success': True,
                'message': _("Welcome back, {}!").format(user.get_full_name),
                'token': token.key,
                'user': UserSerializer(user).data,
                'requires_setup': False
            }, status=status.HTTP_200_OK)       
        
        logger.error(f"Login validation errors: {serializer.errors}")
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class FirstTimeSetupAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    
    def dispatch(self, request, *args, **kwargs):
        # Get user_id from session
        user_id = request.session.get('first_time_user_id')
        
        if not user_id:
            return Response({
                'success': False,
                'message': _("Invalid access. Please login first.")
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get user object
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
        
        # Store user in instance for later use
        self.current_user = user
        
        return super().dispatch(request, *args, **kwargs)
    
    def get(self, request):
        """Get current user info for setup form"""
        return Response({
            'success': True,
            'user': {
                'id': self.current_user.id,
                'current_email': self.current_user.email,
                'current_username': self.current_user.username,
                'first_name': self.current_user.first_name,
                'last_name': self.current_user.last_name,
            }
        })
    
    def post(self, request):
        serializer = FirstTimeSetupSerializer(
            data=request.data,
            context={'user': self.current_user}
        )
        
        if serializer.is_valid():
            # Update user data
            data = serializer.validated_data
            
            # Update email if provided
            if data.get('email'):
                self.current_user.email = data['email']
            
            # Update username if provided
            if data.get('username'):
                self.current_user.username = data['username']
            
            # Update other fields
            self.current_user.first_name = data.get('first_name', self.current_user.first_name)
            self.current_user.last_name = data.get('last_name', self.current_user.last_name)
            self.current_user.phone = data.get('phone', self.current_user.phone)
            self.current_user.address = data.get('address', self.current_user.address)
            self.current_user.gender = data.get('gender', self.current_user.gender)
            
            # Update password
            self.current_user.set_password(data['password'])
            self.current_user.is_first_login = False
            
            self.current_user.save()
            
            # Clear the session variable
            if 'first_time_user_id' in request.session:
                del request.session['first_time_user_id']
            
            # Log the user in
            login(request, self.current_user)
            
            # Create token for API authentication
            token, created = Token.objects.get_or_create(user=self.current_user)
            
            return Response({
                'success': True,
                'message': _("Your profile has been set up successfully!"),
                'token': token.key,
                'user': UserSerializer(self.current_user).data
            }, status=status.HTTP_200_OK)
        
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


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
    permission_classes = [IsAdminUser]
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['email', 'username', 'first_name', 'last_name', 'phone']
    ordering_fields = ['date_joined', 'last_login', 'email', 'username']
    
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