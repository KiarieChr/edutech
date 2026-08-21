"""
accounts/authentication.py
Custom DRF authentication that validates against UserToken (one token per session)
while staying backward-compatible with the legacy DRF Token model during migration.
"""
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from django.utils import timezone


class UserTokenAuthentication(BaseAuthentication):
    """
    Authenticate against accounts.UserToken.
    Header format: Authorization: Token <40-char hex key>
    Falls back to DRF's built-in Token if no UserToken matches,
    so existing tokens continue to work during migration.
    """
    keyword = 'Token'

    def authenticate(self, request):
        auth = get_authorization_header(request).split()
        if not auth or auth[0].lower() != self.keyword.lower().encode():
            return None

        if len(auth) == 1:
            raise AuthenticationFailed('Invalid token header. No credentials provided.')
        if len(auth) > 2:
            raise AuthenticationFailed('Invalid token header. Token string should not contain spaces.')

        try:
            token_key = auth[1].decode()
        except UnicodeError:
            raise AuthenticationFailed('Invalid token header. Token string contains invalid characters.')

        return self._authenticate_credentials(request, token_key)

    def _authenticate_credentials(self, request, key):
        from .models import UserToken
        from django.utils import timezone
        from datetime import timedelta
        
        token = None
        is_legacy = False
        
        try:
            token = UserToken.objects.select_related('user').get(key=key)
        except UserToken.DoesNotExist:
            # Fall back to legacy DRF Token for backward compatibility
            try:
                from rest_framework.authtoken.models import Token as DRFToken
                drf_token = DRFToken.objects.select_related('user').get(key=key)
                if not drf_token.user.is_active:
                    raise AuthenticationFailed('User inactive or deleted.')
                
                # Auto-convert legacy DRFToken to UserToken so it tracks correctly
                token = UserToken.create_for_user(drf_token.user, request)
                token.key = drf_token.key # Keep the same key so client doesn't log out
                token.save()
                is_legacy = True
            except DRFToken.DoesNotExist:
                raise AuthenticationFailed('Invalid token.')

        if not token.user.is_active:
            raise AuthenticationFailed('User inactive or deleted.')

        # Enforce inactivity timeout
        now = timezone.now()
        timeout_minutes = getattr(token.user, 'session_timeout', 30)
        
        # If not legacy (legacy tokens just got created, so they pass), check timeout
        if not is_legacy:
            if now - token.last_used > timedelta(minutes=timeout_minutes):
                token.delete()
                raise AuthenticationFailed('Session expired due to inactivity.')

        # Update last_used timestamp (cheap non-blocking update)
        UserToken.objects.filter(pk=token.pk).update(last_used=now)

        return (token.user, token)

    def authenticate_header(self, request):
        return self.keyword
