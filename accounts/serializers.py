# accounts/serializers.py
from rest_framework import serializers
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from .models import User, Student, Parent

User = get_user_model()


class DashboardSummarySerializer(serializers.Serializer):
    total_users = serializers.IntegerField()
    active_users = serializers.IntegerField()
    inactive_users = serializers.IntegerField()
    users_active_recently = serializers.IntegerField()
    users_never_logged_in = serializers.IntegerField()
    monthly_growth_rate = serializers.FloatField()


class RoleDistributionSerializer(serializers.Serializer):
    students = serializers.IntegerField()
    lecturers = serializers.IntegerField()
    parents = serializers.IntegerField()
    department_heads = serializers.IntegerField()
    admins = serializers.IntegerField()
    first_login_pending = serializers.IntegerField()
    first_login_completed = serializers.IntegerField()


class GenderDistributionSerializer(serializers.Serializer):
    M = serializers.IntegerField()
    F = serializers.IntegerField()
    unknown = serializers.IntegerField()


class StatusBreakdownSerializer(serializers.Serializer):
    active = serializers.IntegerField()
    inactive = serializers.IntegerField()
    verified = serializers.IntegerField()
    pending_setup = serializers.IntegerField()


class MonthlyTrendSerializer(serializers.Serializer):
    month = serializers.CharField()
    count = serializers.IntegerField()
    date = serializers.CharField()


class DailyTrendSerializer(serializers.Serializer):
    day = serializers.CharField()
    date = serializers.CharField()
    count = serializers.IntegerField()


class RegistrationTrendsSerializer(serializers.Serializer):
    monthly = MonthlyTrendSerializer(many=True)
    daily = DailyTrendSerializer(many=True)
    current_month = serializers.IntegerField()
    previous_month = serializers.IntegerField()


class RecentUserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField(allow_null=True)
    first_name = serializers.CharField(allow_null=True)
    last_name = serializers.CharField(allow_null=True)
    date_joined = serializers.DateTimeField()
    last_login = serializers.DateTimeField(allow_null=True)
    is_active = serializers.BooleanField()


class RecentActivitySerializer(serializers.Serializer):
    recent_users = RecentUserSerializer(many=True)
    period = serializers.CharField()
    start_date = serializers.CharField(allow_null=True)
    end_date = serializers.CharField(allow_null=True)


class StudentLevelSerializer(serializers.Serializer):
    level = serializers.IntegerField()
    count = serializers.IntegerField()


class StudentStatisticsSerializer(serializers.Serializer):
    levels = StudentLevelSerializer(many=True, required=False)
    with_parents = serializers.IntegerField(required=False)
    without_parents = serializers.IntegerField(required=False)


class TimestampsSerializer(serializers.Serializer):
    generated_at = serializers.DateTimeField()
    period_applied = serializers.CharField()


class DashboardResponseSerializer(serializers.Serializer):
    summary = DashboardSummarySerializer()
    role_distribution = RoleDistributionSerializer()
    gender_distribution = GenderDistributionSerializer()
    status_breakdown = StatusBreakdownSerializer()
    registration_trends = RegistrationTrendsSerializer()
    recent_activity = RecentActivitySerializer()
    student_statistics = StudentStatisticsSerializer(required=False)
    lecturer_statistics = serializers.DictField(required=False)
    timestamps = TimestampsSerializer()

class LoginSerializer(serializers.Serializer):
    # Accept either email_or_username or separate email/username fields
    email_or_username = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)
    username = serializers.CharField(required=False)
    password = serializers.CharField(style={'input_type': 'password'})
    
    def validate(self, data):
        identifier = data.get('email_or_username')
        email = data.get('email')
        username = data.get('username')
        password = data.get('password')
        
        # Determine the identifier to use
        if not identifier:
            identifier = email or username
        
        if not identifier:
            raise serializers.ValidationError(_("Must include email, username, or email/username."))
        
        if not password:
            raise serializers.ValidationError(_("Password is required."))
        
        # Authenticate user
        user = authenticate(
            request=self.context.get('request'),
            username=identifier,
            password=password
        )
        
        if user:
            if not user.is_active:
                raise serializers.ValidationError(_("User account is disabled."))
            data['user'] = user
        else:
            raise serializers.ValidationError(_("Unable to log in with provided credentials."))
        
        return data
        


class EmailLoginSerializer(serializers.Serializer):
    """Alternative serializer that specifically asks for email"""
    email = serializers.EmailField()
    password = serializers.CharField(style={'input_type': 'password'})
    
    def validate(self, data):
        email = data.get('email')
        password = data.get('password')
        
        if not email:
            raise serializers.ValidationError(_("Email is required."))
        
        if not password:
            raise serializers.ValidationError(_("Password is required."))
        
        # Authenticate using email
        user = authenticate(
            request=self.context.get('request'),
            username=email,  # Our backend handles email as username
            password=password
        )
        
        if user:
            if not user.is_active:
                raise serializers.ValidationError(_("User account is disabled."))
            data['user'] = user
        else:
            raise serializers.ValidationError(_("Unable to log in with provided credentials."))
        
        return data


class FirstTimeSetupSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    username = serializers.CharField(required=False)
    password = serializers.CharField(style={'input_type': 'password'}, required=True)
    confirm_password = serializers.CharField(style={'input_type': 'password'}, required=True)
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)
    phone = serializers.CharField(required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)
    gender = serializers.ChoiceField(choices=[('M', 'Male'), ('F', 'Female')], required=False)
    
    def validate(self, data):
        user = self.context.get('user')
        
        # Password validation
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError({
                'confirm_password': _("Passwords do not match.")
            })
        
        try:
            validate_password(data['password'])
        except ValidationError as e:
            raise serializers.ValidationError({'password': list(e.messages)})
        
        # Email validation
        email = data['email']
        if User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
            raise serializers.ValidationError({
                'email': _("This email is already registered.")
            })
        
        # Username validation (if provided)
        username = data.get('username')
        if username and User.objects.filter(username__iexact=username).exclude(pk=user.pk).exists():
            raise serializers.ValidationError({
                'username': _("This username is already taken.")
            })
        
        return data


# ====================
# User Serializers
# ====================

class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    picture_url = serializers.CharField(source='get_picture', read_only=True)
    profile_url = serializers.CharField(source='get_absolute_url', read_only=True)
    role = serializers.CharField(source='get_user_role', read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name', 'full_name',
            'is_student', 'is_lecturer', 'is_parent', 'is_dep_head', 'is_superuser',
            'is_active', 'gender', 'phone', 'address', 'picture', 'picture_url',
            'is_first_login', 'date_joined', 'last_login', 'profile_url', 'role'
        ]
        read_only_fields = ['date_joined', 'last_login', 'is_superuser']


class UserDetailSerializer(UserSerializer):
    statistics = serializers.SerializerMethodField(read_only=True)
    
    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ['statistics']
    
    def get_statistics(self, obj):
        # Add any statistics you want to include
        return {}


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    confirm_password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    
    class Meta:
        model = User
        fields = [
            'email', 'username', 'first_name', 'last_name', 'password',
            'confirm_password', 'is_student', 'is_lecturer', 'is_parent',
            'gender', 'phone', 'address'
        ]
        extra_kwargs = {
            'email': {'required': True},
            'username': {'required': False},
        }
    
    def validate(self, data):
        # Check if passwords match
        if data['password'] != data.pop('confirm_password'):
            raise serializers.ValidationError({
                'confirm_password': _("Passwords do not match.")
            })
        
        # Validate password strength
        try:
            validate_password(data['password'])
        except ValidationError as e:
            raise serializers.ValidationError({'password': list(e.messages)})
        
        # Check if email already exists
        if User.objects.filter(email__iexact=data['email']).exists():
            raise serializers.ValidationError({
                'email': _("A user with this email already exists.")
            })
        
        # Check username if provided
        username = data.get('username')
        if username and User.objects.filter(username__iexact=username).exists():
            raise serializers.ValidationError({
                'username': _("This username is already taken.")
            })
        
        return data
    
    def create(self, validated_data):
        # Determine user type
        is_student = validated_data.get('is_student', False)
        is_lecturer = validated_data.get('is_lecturer', False)
        is_parent = validated_data.get('is_parent', False)
        
        # Create user
        user = User.objects.create_user(
            email=validated_data['email'],
            username=validated_data.get('username'),
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            password=validated_data['password'],
            is_student=is_student,
            is_lecturer=is_lecturer,
            is_parent=is_parent,
            gender=validated_data.get('gender'),
            phone=validated_data.get('phone'),
            address=validated_data.get('address'),
            is_first_login=True
        )
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=False)
    
    class Meta:
        model = User
        fields = [
            'email', 'username', 'first_name', 'last_name',
            'gender', 'phone', 'address', 'picture', 'is_active'
        ]
        extra_kwargs = {
            'email': {'required': False},
            'username': {'required': False},
        }
    
    def validate_email(self, value):
        user = self.instance
        if value and User.objects.filter(email__iexact=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError(_("This email is already registered."))
        return value
    
    def validate_username(self, value):
        user = self.instance
        if value and User.objects.filter(username__iexact=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError(_("This username is already taken."))
        return value


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(style={'input_type': 'password'})
    new_password = serializers.CharField(style={'input_type': 'password'})
    confirm_new_password = serializers.CharField(style={'input_type': 'password'})
    
    def validate(self, data):
        if data['new_password'] != data['confirm_new_password']:
            raise serializers.ValidationError({
                'confirm_new_password': _("New passwords do not match.")
            })
        
        try:
            validate_password(data['new_password'])
        except ValidationError as e:
            raise serializers.ValidationError({'new_password': list(e.messages)})
        
        return data


# ====================
# Other Serializers
# ====================

# Add your Student, Parent, and other serializers here...
# (Keep your existing serializers for these models)

class DashboardStatsSerializer(serializers.Serializer):
    total_users = serializers.IntegerField()
    students = serializers.IntegerField()
    lecturers = serializers.IntegerField()
    parents = serializers.IntegerField()
    department_heads = serializers.IntegerField()
    admins = serializers.IntegerField()
    active_users = serializers.IntegerField()
    inactive_users = serializers.IntegerField()
    first_login_pending = serializers.IntegerField()


class UserFilterSerializer(serializers.Serializer):
    search = serializers.CharField(required=False)
    role = serializers.CharField(required=False)
    status = serializers.CharField(required=False)
    first_login = serializers.CharField(required=False)
    page = serializers.IntegerField(default=1, min_value=1)
    per_page = serializers.IntegerField(default=10, min_value=1, max_value=100)