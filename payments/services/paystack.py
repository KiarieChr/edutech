"""
payments/services/paystack.py
==============================
Paystack payment gateway — supports M-Pesa (mobile money) as a channel in Kenya.

Credentials are loaded from GatewayConfig (database) — never from settings/env.

Supported flows
---------------
* Initialize a transaction  (card, mobile_money, ussd, bank_transfer …)
* Verify a transaction      (used in webhook + redirect callback)
* List banks / mobile-money providers
* Refund

Paystack M-Pesa notes
---------------------
* channel = 'mobile_money', provider = 'mpesa', bank_code = 'MPESA'
* Phone must be in 07XXXXXXXX or 254XXXXXXXXX format.
* Paystack collects the money, reconciles with Safaricom, settles to you.
* Webhooks carry a `charge.success` event — wire it to `handle_webhook()`.

Usage
-----
    from payments.services.paystack import PaystackService

    svc = PaystackService()
    result = svc.initialize(
        email='guardian@school.ke',
        amount_kes=1500,
        reference='INV-2026-001',
        phone='0712345678',
        channel='mobile_money',
        fee_invoice_id=42,
    )
    # redirect user to result['data']['authorization_url']
"""

import hashlib
import hmac
import logging
import uuid

import requests

from payments.models import GatewayConfig, PaymentTransaction

logger = logging.getLogger(__name__)


class PaystackError(Exception):
    pass


class PaystackService:
    BASE_URL = 'https://api.paystack.co'

    def __init__(self, config: GatewayConfig = None):
        if config is None:
            try:
                config = GatewayConfig.get_active('paystack')
            except GatewayConfig.DoesNotExist:
                raise PaystackError(
                    'No active Paystack configuration found. '
                    'Please add one in Admin → Payments → Gateway Configs.'
                )
        self.cfg = config

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _headers(self) -> dict:
        return {
            'Authorization': f'Bearer {self.cfg.secret_key}',
            'Content-Type': 'application/json',
        }

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        phone = phone.strip().replace('+', '').replace(' ', '')
        if phone.startswith('07') or phone.startswith('01'):
            phone = '254' + phone[1:]
        return phone

    # ── Initialize ────────────────────────────────────────────────────────────

    def initialize(
        self,
        email: str,
        amount_kes: float,
        reference: str = None,
        phone: str = '',
        channel: str = 'mobile_money',   # or 'card', 'bank', 'ussd', 'bank_transfer'
        callback_url: str = '',
        fee_invoice_id: int = None,
        student_id: int = None,
        metadata: dict = None,
    ) -> dict:
        """
        Create a Paystack transaction.
        Returns {'success': bool, 'authorization_url': str, 'transaction_id': int}
        """
        if reference is None:
            reference = f'PS-{uuid.uuid4().hex[:14].upper()}'

        amount_kobo = int(amount_kes * 100)  # Paystack expects amount in kobo (or cents)

        payload = {
            'email': email,
            'amount': amount_kobo,
            'currency': 'KES',
            'reference': reference,
            'channels': [channel],
            'metadata': metadata or {},
        }
        if phone:
            payload['mobile_money'] = {
                'phone': self._normalize_phone(phone),
                'provider': 'mpesa',
            }
        if callback_url:
            payload['callback_url'] = callback_url

        txn = PaymentTransaction.objects.create(
            provider='paystack',
            reference=reference,
            phone=phone,
            amount=amount_kes,
            description=f'Paystack {channel} payment',
            fee_invoice_id=fee_invoice_id,
            student_id=student_id,
            raw_request=payload,
        )

        try:
            resp = requests.post(
                f'{self.BASE_URL}/transaction/initialize',
                json=payload,
                headers=self._headers(),
                timeout=30,
            )
            data = resp.json()
            txn.raw_response = data

            if data.get('status'):
                txn.external_reference = data['data'].get('reference', reference)
                txn.status = 'processing'
            else:
                txn.status = 'failed'
                txn.failure_reason = data.get('message', 'Unknown error')
            txn.save()

            return {
                'success': data.get('status', False),
                'authorization_url': data.get('data', {}).get('authorization_url', ''),
                'access_code': data.get('data', {}).get('access_code', ''),
                'reference': reference,
                'transaction_id': txn.id,
                'message': data.get('message', ''),
            }
        except Exception as exc:
            txn.status = 'failed'
            txn.failure_reason = str(exc)
            txn.save()
            logger.exception('Paystack initialize failed')
            raise PaystackError(str(exc)) from exc

    # ── Verify ────────────────────────────────────────────────────────────────

    def verify(self, reference: str) -> dict:
        """
        Verify a transaction by reference.
        Updates the local PaymentTransaction row.
        """
        resp = requests.get(
            f'{self.BASE_URL}/transaction/verify/{reference}',
            headers=self._headers(),
            timeout=30,
        )
        data = resp.json()
        txn = PaymentTransaction.objects.filter(
            reference=reference, provider='paystack',
        ).first()

        if txn:
            status_map = {
                'success': 'success',
                'failed': 'failed',
                'abandoned': 'cancelled',
                'reversed': 'reversed',
            }
            raw_status = data.get('data', {}).get('status', '')
            txn.status = status_map.get(raw_status, txn.status)
            txn.raw_response = {**txn.raw_response, 'verify': data}
            txn.save()

            if txn.status == 'success' and txn.fee_invoice_id:
                from payments.services.daraja import _apply_payment_to_invoice
                _apply_payment_to_invoice(txn)

        return data

    # ── Webhook handler ───────────────────────────────────────────────────────

    def handle_webhook(self, payload: dict, signature: str) -> bool:
        """
        Verify and process a Paystack webhook.

        Call from your webhook view:
            svc.handle_webhook(request.data, request.headers.get('X-Paystack-Signature'))

        Returns True if processed successfully.
        """
        # Verify HMAC-SHA512 signature
        expected = hmac.new(
            self.cfg.secret_key.encode(),
            msg=str(payload).encode(),
            digestmod=hashlib.sha512,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature or ''):
            logger.warning('Paystack webhook signature mismatch')
            return False

        event = payload.get('event')
        if event == 'charge.success':
            ref = payload.get('data', {}).get('reference', '')
            self.verify(ref)

        return True

    # ── Refund ────────────────────────────────────────────────────────────────

    def refund(self, transaction_reference: str, amount_kes: float = None) -> dict:
        """Full or partial refund. Omit amount for full refund."""
        payload = {'transaction': transaction_reference}
        if amount_kes is not None:
            payload['amount'] = int(amount_kes * 100)
        resp = requests.post(
            f'{self.BASE_URL}/refund',
            json=payload,
            headers=self._headers(),
            timeout=30,
        )
        return resp.json()

    # ── List mobile money providers ───────────────────────────────────────────

    def list_mobile_providers(self, country: str = 'KE') -> list:
        resp = requests.get(
            f'{self.BASE_URL}/bank?currency=KES&country={country}&type=mobile_money',
            headers=self._headers(),
            timeout=30,
        )
        return resp.json().get('data', [])
