# accounts/backends.py
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

UserModel = get_user_model()

class EmailOrUsernameModelBackend(ModelBackend):
    """
    Authenticate using either email or username.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        
        # Check if it's an email format
        if '@' in username:
            # Try email lookup first
            try:
                user = UserModel.objects.get(email__iexact=username)
            except UserModel.DoesNotExist:
                # Fall back to username
                try:
                    user = UserModel.objects.get(username__iexact=username)
                except UserModel.DoesNotExist:
                    UserModel().set_password(password)  # Timing attack protection
                    return None
            except UserModel.MultipleObjectsReturned:
                user = UserModel.objects.filter(email__iexact=username).first()
        else:
            # Try username lookup
            try:
                user = UserModel.objects.get(username__iexact=username)
            except UserModel.DoesNotExist:
                UserModel().set_password(password)  # Timing attack protection
                return None
        
        # Check password
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
    
    def get_user(self, user_id):
        try:
            user = UserModel.objects.get(pk=user_id)
        except UserModel.DoesNotExist:
            return None
        return user if self.user_can_authenticate(user) else None