import json
import base64
import hashlib
import uuid
import threading
from datetime import timedelta
import concurrent.futures
import time

from django.utils import timezone
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.db import IntegrityError, connection, transaction
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

from django_tenants.test.cases import FastTenantTestCase, TenantTestCase
from tenants.models import Installation, Domain
from core.models import SyncOutbox, SyncTenantCursor

class PullTestMixin:
    def setup_crypto(self):
        self.private_key = ed25519.Ed25519PrivateKey.generate()
        self.public_key = self.private_key.public_key()
        self.public_key_pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')

    def create_installation(self, installation_id='INST-PULL'):
        return Installation.objects.create(
            installation_id=installation_id,
            tenant=self.tenant,
            name='Test Pull Installation',
            public_key=self.public_key_pem,
            is_active=True
        )

    def sign_request(self, method, path, timestamp_str, body_bytes, installation_id):
        body_hash = hashlib.sha256(body_bytes).hexdigest()
        canonical_string = f"{method}\n{path}\n{timestamp_str}\n{installation_id}\n{body_hash}"
        signature = self.private_key.sign(canonical_string.encode('utf-8'))
        return base64.b64encode(signature).decode('utf-8')

    def build_request(self, payload, timestamp=None, installation_id=None):
        if timestamp is None:
            timestamp = timezone.now().isoformat()
        if installation_id is None:
            installation_id = self.installation_id

        body_bytes = json.dumps(payload).encode('utf-8')
        signature = self.sign_request('POST', self.url, timestamp, body_bytes, installation_id)

        return {
            'data': payload,
            'format': 'json',
            'HTTP_X_INSTALLATION_ID': installation_id,
            'HTTP_X_TIMESTAMP': timestamp,
            'HTTP_X_SIGNATURE': signature
        }


class SyncPullAPITestCase(FastTenantTestCase, PullTestMixin):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = 'Test Pull Tenant'
        tenant.save()
        Domain.objects.create(domain='pulltest.com', tenant=tenant, is_primary=True)

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.setup_crypto()
        self.installation_id = 'INST-PULL'
        self.installation = self.create_installation(self.installation_id)
        self.url = reverse('sync-pull')

    def create_outbox_event(self, model='workforce.Employee', action='CREATE', source='CENTRAL'):
        with transaction.atomic():
            return SyncOutbox.objects.create(
                model_name=model,
                action=action,
                sync_id=str(uuid.uuid4()),
                payload={"data": "test"},
                source_installation_id=source
            )

    def test_valid_pull_empty(self):
        req = self.build_request({"cursor": 0, "limit": 10})
        response = self.client.post(self.url, **req)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(len(data['events']), 0)
        self.assertEqual(data['next_cursor'], 0)
        self.assertFalse(data['has_more'])

    def test_valid_pull_with_events(self):
        # Create events
        e1 = self.create_outbox_event()
        e2 = self.create_outbox_event()
        
        req = self.build_request({"cursor": 0, "limit": 10})
        response = self.client.post(self.url, **req)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['events']), 2)
        self.assertEqual(data['next_cursor'], e2.ordered_cursor)
        self.assertFalse(data['has_more'])

    def test_pagination_limit(self):
        for _ in range(5):
            self.create_outbox_event()
            
        req = self.build_request({"cursor": 0, "limit": 3})
        response = self.client.post(self.url, **req)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['events']), 3)
        self.assertTrue(data['has_more'])
        
        # Next page
        req2 = self.build_request({"cursor": data['next_cursor'], "limit": 3})
        response2 = self.client.post(self.url, **req2)
        data2 = response2.json()
        self.assertEqual(len(data2['events']), 2)
        self.assertFalse(data2['has_more'])

    def test_echo_exclusion(self):
        self.create_outbox_event(source='CENTRAL')
        self.create_outbox_event(source=self.installation_id) # Should be excluded
        self.create_outbox_event(source='OTHER-INST')
        
        req = self.build_request({"cursor": 0, "limit": 10})
        response = self.client.post(self.url, **req)
        data = response.json()
        self.assertEqual(len(data['events']), 2)
        sources = [e['source_installation_id'] for e in data['events']]
        self.assertNotIn(self.installation_id, sources)

    def test_invalid_cursor(self):
        req = self.build_request({"cursor": -1})
        response = self.client.post(self.url, **req)
        self.assertEqual(response.status_code, 400)


class SyncPullConcurrencyTestCase(TenantTestCase, PullTestMixin):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = 'Test Concurrency Tenant'
        tenant.save()
        Domain.objects.create(domain='concur.com', tenant=tenant, is_primary=True)

    def setUp(self):
        super().setUp()
        self.setup_crypto()
        self.installation_id = 'INST-CONCUR'
        self.installation = self.create_installation(self.installation_id)
        
    def test_concurrent_allocation_and_rollback(self):
        # We need two threads to allocate cursors to prove serialization
        # Thread A starts, allocates cursor, sleeps, then rolls back.
        # Thread B tries to allocate cursor while A is sleeping. It should block.
        # Once A rolls back, B should get the same cursor A had allocated.
        
        ready_event = threading.Event()
        proceed_event = threading.Event()
        
        def tx_a():
            with connection.cursor() as cursor:
                cursor.execute(f"SET search_path TO {self.tenant.schema_name}")
            try:
                with transaction.atomic():
                    # Allocate cursor
                    SyncTenantCursor.allocate_cursor()
                    ready_event.set()
                    # Wait for B to attempt allocation
                    proceed_event.wait()
                    # Rollback intentionally
                    raise ValueError("Intentional rollback")
            except ValueError:
                pass

        def tx_b():
            with connection.cursor() as cursor:
                cursor.execute(f"SET search_path TO {self.tenant.schema_name}")
            ready_event.wait()
            # B attempts allocation. If A locked it correctly, B will block here.
            # We signal A to proceed so B can eventually unblock.
            proceed_event.set()
            
            with transaction.atomic():
                c = SyncTenantCursor.allocate_cursor()
                # Create the event
                SyncOutbox.objects.create(
                    ordered_cursor=c,
                    model_name="test",
                    action="CREATE",
                    sync_id=str(uuid.uuid4()),
                    source_installation_id="B"
                )
                return c

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_a = executor.submit(tx_a)
            future_b = executor.submit(tx_b)
            future_a.result()
            b_cursor = future_b.result()
            
        # Since A rolled back, B should get cursor = 1
        self.assertEqual(b_cursor, 1)

    def test_concurrent_allocation_commit_ordering(self):
        # Transaction A allocates cursor, sleeps, then commits.
        # Transaction B allocates cursor (will block until A commits), then commits.
        # We ensure no gaps and B waits for A.
        ready_event = threading.Event()
        proceed_event = threading.Event()
        
        def tx_a():
            with connection.cursor() as cursor:
                cursor.execute(f"SET search_path TO {self.tenant.schema_name}")
            with transaction.atomic():
                c = SyncTenantCursor.allocate_cursor()
                SyncOutbox.objects.create(
                    ordered_cursor=c,
                    model_name="test",
                    action="CREATE",
                    sync_id=str(uuid.uuid4()),
                    source_installation_id="A"
                )
                ready_event.set()
                proceed_event.wait()
            return c

        def tx_b():
            with connection.cursor() as cursor:
                cursor.execute(f"SET search_path TO {self.tenant.schema_name}")
            ready_event.wait()
            # Trigger A to finish
            proceed_event.set()
            with transaction.atomic():
                c = SyncTenantCursor.allocate_cursor()
                SyncOutbox.objects.create(
                    ordered_cursor=c,
                    model_name="test",
                    action="CREATE",
                    sync_id=str(uuid.uuid4()),
                    source_installation_id="B"
                )
            return c

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_a = executor.submit(tx_a)
            future_b = executor.submit(tx_b)
            a_cursor = future_a.result()
            b_cursor = future_b.result()
            
        self.assertEqual(a_cursor, 1)
        self.assertEqual(b_cursor, 2)
