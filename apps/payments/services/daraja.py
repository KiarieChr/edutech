"""
payments/services/daraja.py
===========================
Safaricom Daraja API — M-Pesa integration.

Credentials are loaded exclusively from GatewayConfig (database),
never from settings.py or environment variables.

Supported APIs
--------------
* STK Push (Lipa Na M-Pesa Online / C2B)
* STK Push Query
* C2B Register URLs
* B2C (business pay-out)

Usage
-----
    from payments.services.daraja import DarajaService

    svc = DarajaService()           # loads active config automatically
    result = svc.stk_push(
        phone='254712345678',
        amount=500,
        account_reference='INV-2026-001',
        description='Fee payment',
    )
"""

import base64
import logging
from datetime import datetime

import requests
from django.utils import timezone

from payments.models import GatewayConfig, PaymentTransaction

logger = logging.getLogger(__name__)


class DarajaError(Exception):
    pass


class DarajaService:
    # ── Daraja base URLs ──────────────────────────────────────────────────────
    SANDBOX_BASE = 'https://sandbox.safaricom.co.ke'
    PRODUCTION_BASE = 'https://api.safaricom.co.ke'

    # ── Endpoints (relative) ─────────────────────────────────────────────────
    TOKEN_URL = '/oauth/v1/generate?grant_type=client_credentials'
    STK_PUSH_URL = '/mpesa/stkpush/v1/processrequest'
    STK_QUERY_URL = '/mpesa/stkpushquery/v1/query'
    C2B_REGISTER_URL = '/mpesa/c2b/v1/registerurl'
    B2C_URL = '/mpesa/b2c/v1/paymentrequest'

    def __init__(self, config: GatewayConfig = None):
        if config is None:
            try:
                config = GatewayConfig.get_active('daraja')
            except GatewayConfig.DoesNotExist:
                raise DarajaError(
                    'No active Daraja configuration found. '
                    'Please add one in Admin → Payments → Gateway Configs.'
                )
        self.cfg = config
        self.base_url = (
            self.PRODUCTION_BASE
            if config.environment == 'production'
            else self.SANDBOX_BASE
        )

    # ── Token management ─────────────────────────────────────────────────────

    def _get_access_token(self) -> str:
        credentials = base64.b64encode(
            f'{self.cfg.consumer_key}:{self.cfg.consumer_secret}'.encode()
        ).decode()
        resp = requests.get(
            self.base_url + self.TOKEN_URL,
            headers={'Authorization': f'Basic {credentials}'},
            timeout=30,
        )
        resp.raise_for_status()
        token = resp.json().get('access_token')
        if not token:
            raise DarajaError(f'Failed to obtain Daraja access token: {resp.text}')
        return token

    def _headers(self) -> dict:
        return {
            'Authorization': f'Bearer {self._get_access_token()}',
            'Content-Type': 'application/json',
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _timestamp(self) -> str:
        return datetime.now().strftime('%Y%m%d%H%M%S')

    def _password(self, timestamp: str) -> str:
        raw = f'{self.cfg.shortcode}{self.cfg.passkey}{timestamp}'
        return base64.b64encode(raw.encode()).decode()

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """Ensure phone is in 2547XXXXXXXX format."""
        phone = phone.strip().replace('+', '').replace(' ', '')
        if phone.startswith('07') or phone.startswith('01'):
            phone = '254' + phone[1:]
        return phone

    # ── STK Push (C2B prompt on customer's phone) ─────────────────────────────

    def stk_push(
        self,
        phone: str,
        amount: int,
        account_reference: str,
        description: str,
        fee_invoice_id: int = None,
        student_id: int = None,
    ) -> dict:
        """
        Initiate an STK Push (Lipa Na M-Pesa Online).

        Returns the raw Safaricom response dict.
        A `PaymentTransaction` row is created immediately with status='pending'.
        """
        phone = self._normalize_phone(phone)
        timestamp = self._timestamp()
        payload = {
            'BusinessShortCode': self.cfg.shortcode,
            'Password': self._password(timestamp),
            'Timestamp': timestamp,
            'TransactionType': 'CustomerPayBillOnline',
            'Amount': int(amount),
            'PartyA': phone,
            'PartyB': self.cfg.shortcode,
            'PhoneNumber': phone,
            'CallBackURL': self.cfg.callback_url,
            'AccountReference': account_reference[:12],
            'TransactionDesc': description[:13],
        }

        # Create pending transaction record
        import uuid
        ref = f'DARAJA-{uuid.uuid4().hex[:12].upper()}'
        txn = PaymentTransaction.objects.create(
            provider='daraja',
            reference=ref,
            phone=phone,
            amount=amount,
            description=description,
            fee_invoice_id=fee_invoice_id,
            student_id=student_id,
            raw_request=payload,
        )

        try:
            resp = requests.post(
                self.base_url + self.STK_PUSH_URL,
                json=payload,
                headers=self._headers(),
                timeout=30,
            )
            data = resp.json()
            txn.raw_response = data
            txn.external_reference = data.get('CheckoutRequestID', '')
            txn.status = 'processing' if data.get('ResponseCode') == '0' else 'failed'
            if data.get('ResponseCode') != '0':
                txn.failure_reason = data.get('ResponseDescription', '')
            txn.save()
            return {'success': data.get('ResponseCode') == '0', 'data': data, 'transaction_id': txn.id}
        except Exception as exc:
            txn.status = 'failed'
            txn.failure_reason = str(exc)
            txn.save()
            logger.exception('STK Push failed')
            raise DarajaError(str(exc)) from exc

    # ── STK Query ────────────────────────────────────────────────────────────

    def stk_query(self, checkout_request_id: str) -> dict:
        """Query the status of an STK Push request."""
        timestamp = self._timestamp()
        payload = {
            'BusinessShortCode': self.cfg.shortcode,
            'Password': self._password(timestamp),
            'Timestamp': timestamp,
            'CheckoutRequestID': checkout_request_id,
        }
        resp = requests.post(
            self.base_url + self.STK_QUERY_URL,
            json=payload,
            headers=self._headers(),
            timeout=30,
        )
        return resp.json()

    # ── Callback handler ─────────────────────────────────────────────────────

    @staticmethod
    def handle_stk_callback(payload: dict) -> 'PaymentTransaction | None':
        """
        Process the callback POST that Safaricom sends to `callback_url`.
        Updates the matching PaymentTransaction row.

        Call this from your callback view after deserialising the JSON body.
        """
        try:
            body = payload.get('Body', {}).get('stkCallback', {})
            checkout_id = body.get('CheckoutRequestID', '')
            result_code = str(body.get('ResultCode', ''))
            result_desc = body.get('ResultDesc', '')

            txn = PaymentTransaction.objects.filter(
                external_reference=checkout_id, provider='daraja',
            ).first()

            if not txn:
                logger.warning('Daraja callback: no transaction for %s', checkout_id)
                return None

            if result_code == '0':
                # Parse metadata items
                items = (
                    body.get('CallbackMetadata', {}).get('Item', [])
                )
                meta = {i['Name']: i.get('Value') for i in items}
                txn.status = 'success'
                txn.external_reference = meta.get('MpesaReceiptNumber', checkout_id)
            else:
                txn.status = 'failed'
                txn.failure_reason = result_desc

            txn.raw_response = {**txn.raw_response, 'callback': payload}
            txn.save()

            # If payment succeeded, update the linked FeeInvoice
            if txn.status == 'success' and txn.fee_invoice_id:
                _apply_payment_to_invoice(txn)

            return txn
        except Exception:
            logger.exception('Error processing Daraja STK callback')
            return None

    # ── C2B URL Registration & Handlers ──────────────────────────────────────

    def register_c2b_urls(self, validation_url: str, confirmation_url: str) -> dict:
        """Register C2B validation/confirmation URLs with Safaricom."""
        payload = {
            'ShortCode': self.cfg.shortcode,
            'ResponseType': 'Completed',
            'ConfirmationURL': confirmation_url,
            'ValidationURL': validation_url,
        }
        resp = requests.post(
            self.base_url + self.C2B_REGISTER_URL,
            json=payload,
            headers=self._headers(),
            timeout=30,
        )
        return resp.json()

    @staticmethod
    def handle_c2b_validation(payload: dict) -> dict:
        """
        Validate if the provided BillRefNumber (Account Number) is a valid
        Student admission number.
        Returns accepted/rejected JSON to Safaricom.
        """
        from student_management.models import Student
        bill_ref = payload.get('BillRefNumber', '').strip()

        if Student.objects.filter(admission_number=bill_ref).exists():
            return {'ResultCode': 0, 'ResultDesc': 'Accepted'}
        
        return {'ResultCode': 1, 'ResultDesc': 'Invalid Admission Number'}

    @staticmethod
    def handle_c2b_confirmation(payload: dict):
        """
        Record the payment and generate a finance.models.Receipt.
        """
        from student_management.models import Student
        from finance.models import Receipt, PaymentMethod
        from finance.receipt_journal_service import ReceiptJournalService
        from payments.services.sms import SMSService
        import uuid
        from django.contrib.auth import get_user_model
        from decimal import Decimal
        
        bill_ref = payload.get('BillRefNumber', '').strip()
        trans_amount = Decimal(str(payload.get('TransAmount', 0)))
        trans_id = payload.get('TransID', '')
        msisdn = str(payload.get('MSISDN', ''))
        first_name = payload.get('FirstName', '')
        last_name = payload.get('LastName', '')
        trans_time = payload.get('TransTime', '') # YYYYMMDDHHMMSS
        
        try:
            date_received = datetime.strptime(trans_time, '%Y%m%d%H%M%S').date()
        except ValueError:
            date_received = timezone.now().date()

        student = Student.objects.filter(admission_number=bill_ref).first()
        if not student:
            logger.error('Daraja C2B Confirmation: Student not found for %s', bill_ref)
            return

        # 1. Log Payment Transaction
        txn = PaymentTransaction.objects.create(
            provider='daraja',
            reference=f'C2B-{trans_id}',
            external_reference=trans_id,
            phone=msisdn,
            amount=trans_amount,
            status='success',
            description=f'M-Pesa C2B Payment by {first_name} {last_name}',
            student=student,
            raw_response=payload,
        )
        
        # 2. Generate Receipt
        try:
            payment_method = PaymentMethod.objects.filter(name__icontains='M-Pesa').first()
            if not payment_method:
                payment_method = PaymentMethod.objects.first()
                
            admin_user = get_user_model().objects.filter(is_superuser=True).first()
            
            receipt = Receipt.objects.create(
                receipt_number=f"RCT-{uuid.uuid4().hex[:8].upper()}",
                receipt_type='STUDENT_FEE',
                payer_name=f"{first_name} {last_name}",
                student=student,
                payment_method=payment_method,
                amount_received=trans_amount,
                received_date=date_received,
                received_by=admin_user,
                reference=trans_id,
                status='ISSUED',
                is_posted=False 
            )
            
            # Allocation logic
            from fees.models import FeeInvoice
            invoices = FeeInvoice.objects.filter(student=student, balance__gt=0).order_by('date_issued')
            
            total_allocated = Decimal('0.00')
            for inv in invoices:
                if total_allocated >= trans_amount:
                    break
                remaining_payment = trans_amount - total_allocated
                allocate = min(remaining_payment, inv.balance)
                
                inv.paid_amount += allocate
                inv.update_payment_status()
                total_allocated += allocate
                
            receipt.amount_allocated = total_allocated
            receipt.is_posted = True
            receipt.posted_at = timezone.now()
            receipt.save()
            
            # Create journal entry
            ReceiptJournalService.create_receipt_journal_entry(receipt, user=admin_user)
            
            # 3. Send SMS
            try:
                sms = SMSService()
                # Safely get student name
                student_name = student.student.get_full_name() if hasattr(student.student, 'get_full_name') else 'the student'
                msg = f"Dear {first_name}, we have received your payment of KES {trans_amount} for {student_name} (Adm: {bill_ref}). Receipt No: {receipt.receipt_number}."
                sms.send(msisdn, msg)
                
                # Send to parents if communications active
                for parent in student.parents.all():
                    if parent.phone and parent.phone != msisdn:
                        sms.send(parent.phone, msg)
            except Exception as e:
                logger.error('Failed to send SMS: %s', str(e))
                
        except Exception as exc:
            logger.exception('Daraja C2B Confirmation processing failed')
            txn.failure_reason = str(exc)
            txn.save()

    # ── B2C (Disbursement) ───────────────────────────────────────────────────

    def b2c_payment(
        self,
        phone: str,
        amount: int,
        occasion: str = '',
        remarks: str = 'Payment',
        command_id: str = 'BusinessPayment',
    ) -> dict:
        """
        Send money FROM the business TO a customer (refunds, bursaries, etc.).
        command_id choices: BusinessPayment | SalaryPayment | PromotionPayment
        """
        phone = self._normalize_phone(phone)
        payload = {
            'InitiatorName': self.cfg.b2c_initiator_name,
            'SecurityCredential': self.cfg.b2c_initiator_password,
            'CommandID': command_id,
            'Amount': int(amount),
            'PartyA': self.cfg.shortcode,
            'PartyB': phone,
            'Remarks': remarks[:100],
            'QueueTimeOutURL': self.cfg.b2c_queue_timeout_url,
            'ResultURL': self.cfg.b2c_result_url,
            'Occasion': occasion[:100],
        }
        resp = requests.post(
            self.base_url + self.B2C_URL,
            json=payload,
            headers=self._headers(),
            timeout=30,
        )
        return resp.json()


# ── Shared helper ─────────────────────────────────────────────────────────────

def _apply_payment_to_invoice(txn: PaymentTransaction):
    """
    Update fees.FeeInvoice paid_amount / balance / status after a confirmed payment.
    """
    try:
        invoice = txn.fee_invoice
        invoice.paid_amount = min(
            invoice.total_amount,
            invoice.paid_amount + txn.amount,
        )
        invoice.balance = max(0, invoice.total_amount - invoice.paid_amount)
        if invoice.balance == 0:
            invoice.status = 'PAID'
        else:
            invoice.status = 'PARTIALLY_PAID'
        invoice.save(update_fields=['paid_amount', 'balance', 'status'])
    except Exception:
        logger.exception('Failed to apply payment to invoice %s', txn.fee_invoice_id)
