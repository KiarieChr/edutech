import json
import hashlib
import dateutil.parser
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from cryptography.exceptions import InvalidSignature
import base64
from tenants.models import Installation

class Ed25519SyncAuthentication(BaseAuthentication):
    def authenticate(self, request):
        installation_id = request.META.get('HTTP_X_INSTALLATION_ID')
        timestamp_str = request.META.get('HTTP_X_TIMESTAMP')
        signature_b64 = request.META.get('HTTP_X_SIGNATURE')

        if not installation_id:
            raise AuthenticationFailed({"code": "MISSING_INSTALLATION_ID", "message": "Missing X-Installation-ID header"})
        if not timestamp_str:
            raise AuthenticationFailed({"code": "MISSING_TIMESTAMP", "message": "Missing X-Timestamp header"})
        if not signature_b64:
            raise AuthenticationFailed({"code": "MISSING_SIGNATURE", "message": "Missing X-Signature header"})

        try:
            timestamp = dateutil.parser.isoparse(timestamp_str)
        except ValueError:
            raise AuthenticationFailed({"code": "INVALID_TIMESTAMP", "message": "Invalid timestamp format"})

        if abs((timezone.now() - timestamp).total_seconds()) > 300:
            raise AuthenticationFailed({"code": "REQUEST_EXPIRED", "message": "Request timestamp outside tolerance window"})

        try:
            installation = Installation.objects.get(installation_id=installation_id)
        except Installation.DoesNotExist:
            raise AuthenticationFailed({"code": "UNKNOWN_INSTALLATION", "message": "Installation not found"})

        if not installation.is_active:
            raise AuthenticationFailed({"code": "INSTALLATION_INACTIVE", "message": "Installation is not active"})

        try:
            from cryptography.hazmat.primitives import serialization
            public_key = serialization.load_pem_public_key(installation.public_key.encode('utf-8'))
        except Exception:
            raise AuthenticationFailed({"code": "INVALID_PUBLIC_KEY", "message": "Stored public key is invalid"})

        try:
            body_bytes = request.body
            body_hash = hashlib.sha256(body_bytes).hexdigest()
            
            canonical_string = f"{request.method}\n{request.path}\n{timestamp_str}\n{installation_id}\n{body_hash}"
            
            signature = base64.b64decode(signature_b64)
            public_key.verify(signature, canonical_string.encode('utf-8'))
        except InvalidSignature:
            raise AuthenticationFailed({"code": "SIGNATURE_VERIFICATION_FAILED", "message": "Invalid signature"})
        except Exception as e:
            raise AuthenticationFailed({"code": "SIGNATURE_ERROR", "message": "Error verifying signature"})

        installation.last_seen_at = timezone.now()
        installation.save(update_fields=['last_seen_at'])

        class DummyUser:
            is_authenticated = True
            tenant = installation.tenant
            installation = installation

        return (DummyUser(), None)
