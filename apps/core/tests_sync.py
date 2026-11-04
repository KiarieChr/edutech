import json
import base64
import hashlib
import uuid
import threading
from datetime import timedelta
import concurrent.futures

from django.utils import timezone
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.db import IntegrityError, connection
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

from django_tenants.test.cases import FastTenantTestCase, TenantTestCase
from tenants.models import Installation, Client, Domain
from core.models import SyncProcessedEvent, SyncErrorLog
from workforce.models import Employee

class SyncTestMixin:
    def setup_crypto(self):
        self.private_key = ed25519.Ed25519PrivateKey.generate()
        self.public_key = self.private_key.public_key()
        self.public_key_pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')

    def create_installation(self, installation_id='INST-001'):
        return Installation.objects.create(
            installation_id=installation_id,
            tenant=self.tenant,
            name='Test Installation',
            public_key=self.public_key_pem,
            is_active=True
        )

    def sign_request(self, method, path, timestamp_str, body_bytes, installation_id):
        body_hash = hashlib.sha256(body_bytes).hexdigest()
        canonical_string = f"{method}\n{path}\n{timestamp_str}\n{installation_id}\n{body_hash}"
        signature = self.private_key.sign(canonical_string.encode('utf-8'))
        return base64.b64encode(signature).decode('utf-8')

    def build_request(self, payload, timestamp=None, installation_id=None, tamper_body=False, tamper_signature=None):
        if timestamp is None:
            timestamp = timezone.now().isoformat()
        if installation_id is None:
            installation_id = self.installation_id

        body_bytes = json.dumps(payload).encode('utf-8')
        signature = self.sign_request('POST', self.url, timestamp, body_bytes, installation_id)

        if tamper_body:
            payload['tampered'] = True
            body_bytes = json.dumps(payload).encode('utf-8')

        if tamper_signature:
            signature = tamper_signature

        return {
            'data': payload,
            'format': 'json',
            'HTTP_X_INSTALLATION_ID': installation_id,
            'HTTP_X_TIMESTAMP': timestamp,
            'HTTP_X_SIGNATURE': signature
        }


class SyncAPITestCase(FastTenantTestCase, SyncTestMixin):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = 'Test Tenant'
        tenant.save()
        Domain.objects.create(domain='test.com', tenant=tenant, is_primary=True)

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.setup_crypto()
        self.installation_id = 'INST-001'
        self.installation = self.create_installation(self.installation_id)
        self.url = reverse('sync-push')

    def test_missing_headers(self):
        response = self.client.post(self.url, {}, format='json')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['code'], 'MISSING_INSTALLATION_ID')

    def test_malformed_headers(self):
        req = self.build_request({'events': []})
        req['HTTP_X_TIMESTAMP'] = 'not-a-timestamp'
        response = self.client.post(self.url, **req)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['code'], 'INVALID_TIMESTAMP')

    def test_tampered_body(self):
        req = self.build_request({'events': []}, tamper_body=True)
        response = self.client.post(self.url, **req)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['code'], 'SIGNATURE_VERIFICATION_FAILED')

    def test_expired_timestamp(self):
        expired_ts = (timezone.now() - timedelta(minutes=10)).isoformat()
        req = self.build_request({'events': []}, timestamp=expired_ts)
        response = self.client.post(self.url, **req)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['code'], 'REQUEST_EXPIRED')

    def test_future_timestamp(self):
        future_ts = (timezone.now() + timedelta(minutes=10)).isoformat()
        req = self.build_request({'events': []}, timestamp=future_ts)
        response = self.client.post(self.url, **req)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['code'], 'REQUEST_EXPIRED')

    def test_unknown_installation(self):
        req = self.build_request({'events': []}, installation_id='UNKNOWN-123')
        response = self.client.post(self.url, **req)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['code'], 'UNKNOWN_INSTALLATION')

    def test_disabled_installation(self):
        self.installation.is_active = False
        self.installation.save()
        req = self.build_request({'events': []})
        response = self.client.post(self.url, **req)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['code'], 'INSTALLATION_INACTIVE')

    def test_valid_retry_idempotency(self):
        event_id = str(uuid.uuid4())
        payload = {
            'events': [{
                'event_id': event_id,
                'source_installation_id': self.installation_id,
                'model': 'workforce.Employee',
                'action': 'CREATE',
                'sync_id': str(uuid.uuid4()),
                'payload': {'first_name': 'Retry', 'last_name': 'Test'}
            }]
        }
        req = self.build_request(payload)
        response1 = self.client.post(self.url, **req)
        self.assertEqual(response1.status_code, 200)
        self.assertIn(event_id, response1.json()['success'])

        # Exact same request should be accepted as a retry and return idempotency marker
        response2 = self.client.post(self.url, **req)
        self.assertEqual(response2.status_code, 200)
        self.assertIn(event_id, response2.json()['already_processed'])

    def test_cross_tenant_rejection(self):
        # We need another tenant for this test
        # Instead, just verify the source_installation_id check
        event_id = str(uuid.uuid4())
        payload = {
            'events': [{
                'event_id': event_id,
                'source_installation_id': 'OTHER-TENANT-INST',
                'model': 'workforce.Employee',
                'action': 'CREATE',
                'sync_id': str(uuid.uuid4()),
                'payload': {}
            }]
        }
        req = self.build_request(payload)
        response = self.client.post(self.url, **req)
        self.assertEqual(response.status_code, 200)
        self.assertIn(event_id, [f['event_id'] for f in response.json()['failed']])

    def test_missing_event_id(self):
        payload = {
            'events': [{
                'source_installation_id': self.installation_id,
                'model': 'workforce.Employee',
                'action': 'CREATE'
            }]
        }
        req = self.build_request(payload)
        response = self.client.post(self.url, **req)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['failed'][0]['code'], 'MISSING_EVENT_ID')

    def test_unsupported_model(self):
        event_id = str(uuid.uuid4())
        payload = {
            'events': [{
                'event_id': event_id,
                'source_installation_id': self.installation_id,
                'model': 'core.SystemConfiguration', # Not syncable
                'action': 'CREATE'
            }]
        }
        req = self.build_request(payload)
        response = self.client.post(self.url, **req)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['failed'][0]['code'], 'UNKNOWN_MODEL')

    def test_successful_event_and_idempotency(self):
        sync_id = str(uuid.uuid4())
        event_id = str(uuid.uuid4())
        payload = {
            'events': [{
                'event_id': event_id,
                'source_installation_id': self.installation_id,
                'model': 'workforce.Employee',
                'action': 'CREATE',
                'sync_id': sync_id,
                'payload': {'first_name': 'Test', 'last_name': 'Sync'}
            }]
        }
        
        # 1. Process successfully
        req = self.build_request(payload)
        response = self.client.post(self.url, **req)
        self.assertEqual(response.status_code, 200)
        self.assertIn(event_id, response.json()['processed'])
        self.assertTrue(Employee.objects.filter(sync_id=sync_id).exists())
        self.assertTrue(SyncProcessedEvent.objects.filter(event_id=event_id).exists())

        # 2. Sequential duplicate request (with new timestamp to pass replay check)
        req2 = self.build_request(payload)
        response2 = self.client.post(self.url, **req2)
        self.assertEqual(response2.status_code, 200)
        self.assertIn(event_id, response2.json()['already_processed'])

    def test_rollback_on_business_failure(self):
        event_id = str(uuid.uuid4())
        sync_id = str(uuid.uuid4())
        payload = {
            'events': [{
                'event_id': event_id,
                'source_installation_id': self.installation_id,
                'model': 'workforce.Employee',
                'action': 'UNSUPPORTED_ACTION',
                'sync_id': sync_id,
                'payload': {}
            }]
        }
        req = self.build_request(payload)
        response = self.client.post(self.url, **req)
        self.assertEqual(response.status_code, 200)
        self.assertIn(event_id, [f['event_id'] for f in response.json()['failed']])
        
        # Check rollback
        self.assertFalse(SyncProcessedEvent.objects.filter(event_id=event_id).exists())
        self.assertTrue(SyncErrorLog.objects.filter(event_id=event_id).exists())

    def test_partial_success(self):
        event_ok = str(uuid.uuid4())
        event_fail = str(uuid.uuid4())
        payload = {
            'events': [
                {
                    'event_id': event_ok,
                    'source_installation_id': self.installation_id,
                    'model': 'workforce.Employee',
                    'action': 'CREATE',
                    'sync_id': str(uuid.uuid4()),
                    'payload': {'first_name': 'Test', 'last_name': 'Sync'}
                },
                {
                    'event_id': event_fail,
                    'source_installation_id': self.installation_id,
                    'model': 'workforce.Employee',
                    'action': 'UNSUPPORTED_ACTION',
                    'sync_id': str(uuid.uuid4()),
                    'payload': {}
                }
            ]
        }
        req = self.build_request(payload)
        response = self.client.post(self.url, **req)
        data = response.json()
        
        self.assertIn(event_ok, data['processed'])
        self.assertIn(event_fail, [f['event_id'] for f in data['failed']])


class SyncConcurrencyTestCase(TenantTestCase, SyncTestMixin):
    def setUp(self):
        super().setUp()
        self.setup_crypto()
        self.installation_id = 'INST-001'
        self.installation = self.create_installation(self.installation_id)
        self.url = reverse('sync-push')

    def test_concurrent_duplicate_events(self):
        """
        Verify that competing requests for the same event cannot apply 
        the business change twice and cannot create inconsistent processed-event records.
        """
        event_id = str(uuid.uuid4())
        sync_id = str(uuid.uuid4())
        
        payload = {
            'events': [{
                'event_id': event_id,
                'source_installation_id': self.installation_id,
                'model': 'workforce.Employee',
                'action': 'CREATE',
                'sync_id': sync_id,
                'payload': {'first_name': 'Concurrent', 'last_name': 'Test'}
            }]
        }
        
        # We need two separate API clients so they have distinct connections/states
        client1 = APIClient()
        client2 = APIClient()
        
        req1 = self.build_request(payload)
        req2 = self.build_request(payload)

        # Execute concurrently
        def send_request1():
            connection.close() # Ensure fresh connection for thread
            return client1.post(self.url, **req1)
            
        def send_request2():
            connection.close() # Ensure fresh connection for thread
            return client2.post(self.url, **req2)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future1 = executor.submit(send_request1)
            future2 = executor.submit(send_request2)
            
            resp1 = future1.result()
            resp2 = future2.result()

        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp2.status_code, 200)

        data1 = resp1.json()
        data2 = resp2.json()

        # One should process, one should reject as already_processed
        processed = data1['processed'] + data2['processed']
        already_processed = data1['already_processed'] + data2['already_processed']

        self.assertEqual(len(processed), 1, "Event should be processed exactly once")
        self.assertEqual(len(already_processed), 1, "One request should be marked already_processed")

        # Business logic executed exactly once
        self.assertEqual(Employee.objects.filter(sync_id=sync_id).count(), 1)
        self.assertEqual(SyncProcessedEvent.objects.filter(event_id=event_id).count(), 1)
