from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from tenants.models import Installation, Client, Domain
from django.utils import timezone
from datetime import timedelta
import uuid
import json
import base64
import hashlib
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

class SyncAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        
        # We need a tenant
        self.tenant = Client.objects.create(schema_name='test_tenant', name='Test Tenant', auto_create_schema=False)
        self.domain = Domain.objects.create(domain='test.com', tenant=self.tenant, is_primary=True)
        
        # Generate Ed25519 key pair
        self.private_key = ed25519.Ed25519PrivateKey.generate()
        self.public_key = self.private_key.public_key()
        self.public_key_pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')
        
        # Create installation
        self.installation_id = 'INST-001'
        self.installation = Installation.objects.create(
            installation_id=self.installation_id,
            tenant=self.tenant,
            name='Test Installation',
            public_key=self.public_key_pem,
            is_active=True
        )
        
        self.url = reverse('sync-push')

    def sign_request(self, method, path, timestamp_str, body_bytes):
        body_hash = hashlib.sha256(body_bytes).hexdigest()
        canonical_string = f"{method}\n{path}\n{timestamp_str}\n{self.installation_id}\n{body_hash}"
        signature = self.private_key.sign(canonical_string.encode('utf-8'))
        return base64.b64encode(signature).decode('utf-8')

    def test_missing_headers(self):
        response = self.client.post(self.url, {}, format='json')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['code'], 'MISSING_INSTALLATION_ID')

    def test_valid_request(self):
        payload = {"events": []}
        body_bytes = json.dumps(payload).encode('utf-8')
        timestamp_str = timezone.now().isoformat()
        
        signature = self.sign_request('POST', self.url, timestamp_str, body_bytes)
        
        response = self.client.post(
            self.url,
            data=payload,
            format='json',
            HTTP_X_INSTALLATION_ID=self.installation_id,
            HTTP_X_TIMESTAMP=timestamp_str,
            HTTP_X_SIGNATURE=signature
        )
        
        self.assertEqual(response.status_code, 200)

    def test_tampered_body(self):
        payload = {"events": []}
        body_bytes = json.dumps(payload).encode('utf-8')
        timestamp_str = timezone.now().isoformat()
        
        signature = self.sign_request('POST', self.url, timestamp_str, body_bytes)
        
        # Tamper payload
        payload = {"events": [{"tampered": True}]}
        
        response = self.client.post(
            self.url,
            data=payload,
            format='json',
            HTTP_X_INSTALLATION_ID=self.installation_id,
            HTTP_X_TIMESTAMP=timestamp_str,
            HTTP_X_SIGNATURE=signature
        )
        
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['code'], 'SIGNATURE_VERIFICATION_FAILED')
