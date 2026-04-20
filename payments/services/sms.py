"""
payments/services/sms.py
=========================
SMS integration — supports Africa's Talking, Twilio, and Infobip.

All credentials are loaded from GatewayConfig (database).
The SMSService auto-selects the active provider, or you can pass one explicitly.

Usage
-----
    from payments.services.sms import SMSService

    sms = SMSService()                   # picks the active provider
    sms.send('+254712345678', 'Hello!')

    # Or send to multiple recipients
    sms.send_bulk(['+254712345678', '+254798765432'], 'Fee reminder …')

    # Templated helpers
    sms.send_payment_received(phone, student_name, amount, invoice_no)
    sms.send_fee_reminder(phone, student_name, balance, due_date)
"""

import logging

from payments.models import GatewayConfig, SMSLog

logger = logging.getLogger(__name__)


class SMSError(Exception):
    pass


# ── Base ──────────────────────────────────────────────────────────────────────

class _BaseSMS:
    provider_key: str = ''

    def __init__(self, config: GatewayConfig):
        self.cfg = config

    def send(self, recipient: str, message: str) -> SMSLog:
        raise NotImplementedError

    def send_bulk(self, recipients: list, message: str) -> list:
        return [self.send(r, message) for r in recipients]

    def _log(self, recipient, message, status='queued', message_id='', cost='', failure_reason='') -> SMSLog:
        return SMSLog.objects.create(
            provider=self.provider_key,
            recipient=recipient,
            message=message,
            status=status,
            message_id=message_id,
            cost=cost,
            failure_reason=failure_reason,
        )


# ── Africa's Talking ─────────────────────────────────────────────────────────

class AfricasTalkingSMS(_BaseSMS):
    """
    Requires `africastalking` pip package:
        pip install africastalking
    """
    provider_key = 'africastalking'

    def send(self, recipient: str, message: str) -> SMSLog:
        log = self._log(recipient, message)
        try:
            import africastalking  # type: ignore
            africastalking.initialize(
                username=self.cfg.username,
                api_key=self.cfg.api_key,
            )
            sms_service = africastalking.SMS
            response = sms_service.send(
                message=message,
                recipients=[recipient],
                sender_id=self.cfg.sender_id or None,
            )
            # Parse first recipient result
            result = response.get('SMSMessageData', {}).get('Recipients', [{}])[0]
            status_code = result.get('statusCode', 0)
            if status_code == 101:
                log.status = 'sent'
                log.message_id = result.get('messageId', '')
                log.cost = str(result.get('cost', ''))
            else:
                log.status = 'failed'
                log.failure_reason = result.get('status', str(response))
            log.save()
        except Exception as exc:
            log.status = 'failed'
            log.failure_reason = str(exc)
            log.save()
            logger.exception('Africa\'s Talking SMS failed to %s', recipient)
        return log


# ── Twilio ────────────────────────────────────────────────────────────────────

class TwilioSMS(_BaseSMS):
    """
    Requires `twilio` pip package:
        pip install twilio
    """
    provider_key = 'twilio'

    def send(self, recipient: str, message: str) -> SMSLog:
        log = self._log(recipient, message)
        try:
            from twilio.rest import Client  # type: ignore
            client = Client(self.cfg.account_sid, self.cfg.auth_token)
            msg = client.messages.create(
                body=message,
                from_=self.cfg.from_number,
                to=recipient,
            )
            log.status = 'sent'
            log.message_id = msg.sid
            log.save()
        except Exception as exc:
            log.status = 'failed'
            log.failure_reason = str(exc)
            log.save()
            logger.exception('Twilio SMS failed to %s', recipient)
        return log


# ── Infobip ───────────────────────────────────────────────────────────────────

class InfobipSMS(_BaseSMS):
    """
    Uses Infobip REST API directly (no extra package needed).
    Expects cfg.api_key = '<your-infobip-api-key>'
    and cfg.sender_id = '<your-sender-id>'
    Base URL is read from cfg.username (store your Infobip base URL there, e.g.
    'xyz123.api.infobip.com').
    """
    provider_key = 'infobip'

    def send(self, recipient: str, message: str) -> SMSLog:
        import requests as _req
        log = self._log(recipient, message)
        try:
            base_url = f'https://{self.cfg.username}' if self.cfg.username else 'https://api.infobip.com'
            resp = _req.post(
                f'{base_url}/sms/2/text/advanced',
                headers={
                    'Authorization': f'App {self.cfg.api_key}',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                },
                json={
                    'messages': [{
                        'from': self.cfg.sender_id or 'INFO',
                        'destinations': [{'to': recipient}],
                        'text': message,
                    }]
                },
                timeout=30,
            )
            data = resp.json()
            result = data.get('messages', [{}])[0]
            status = result.get('status', {}).get('groupName', 'UNKNOWN')
            if status == 'PENDING':
                log.status = 'sent'
                log.message_id = result.get('messageId', '')
            else:
                log.status = 'failed'
                log.failure_reason = str(data)
            log.save()
        except Exception as exc:
            log.status = 'failed'
            log.failure_reason = str(exc)
            log.save()
            logger.exception('Infobip SMS failed to %s', recipient)
        return log


# ── Facade ────────────────────────────────────────────────────────────────────

_PROVIDER_MAP = {
    'africastalking': AfricasTalkingSMS,
    'twilio': TwilioSMS,
    'infobip': InfobipSMS,
}


class SMSService:
    """
    Auto-selects the active SMS provider from GatewayConfig.
    Expose a unified interface so calling code never needs to know which
    provider is in use.
    """

    def __init__(self, provider_key: str = None):
        if provider_key:
            try:
                config = GatewayConfig.get_active(provider_key)
            except GatewayConfig.DoesNotExist:
                raise SMSError(f'No active config for SMS provider "{provider_key}".')
        else:
            # Pick first active SMS provider
            config = (
                GatewayConfig.objects
                .filter(provider__in=list(_PROVIDER_MAP), is_active=True)
                .first()
            )
            if not config:
                raise SMSError(
                    'No active SMS provider configured. '
                    'Add one in Admin → Payments → Gateway Configs.'
                )
        cls = _PROVIDER_MAP.get(config.provider)
        if cls is None:
            raise SMSError(f'Unknown SMS provider "{config.provider}".')
        self._backend: _BaseSMS = cls(config)

    # ── Core ──────────────────────────────────────────────────────────────────

    def send(self, recipient: str, message: str) -> SMSLog:
        return self._backend.send(recipient, message)

    def send_bulk(self, recipients: list, message: str) -> list:
        return self._backend.send_bulk(recipients, message)

    # ── Templated messages ────────────────────────────────────────────────────

    def send_payment_received(
        self,
        phone: str,
        student_name: str,
        amount: float,
        invoice_no: str,
        school_name: str = 'School',
    ) -> SMSLog:
        message = (
            f'Dear Parent/Guardian, payment of KES {amount:,.2f} for '
            f'{student_name} (Ref: {invoice_no}) has been received. '
            f'Thank you. - {school_name}'
        )
        return self.send(phone, message)

    def send_fee_reminder(
        self,
        phone: str,
        student_name: str,
        balance: float,
        due_date: str,
        school_name: str = 'School',
    ) -> SMSLog:
        message = (
            f'Dear Parent/Guardian, {student_name} has an outstanding fee '
            f'balance of KES {balance:,.2f} due by {due_date}. '
            f'Please settle to avoid inconvenience. - {school_name}'
        )
        return self.send(phone, message)

    def send_admission_notification(
        self,
        phone: str,
        student_name: str,
        grade: str,
        school_name: str = 'School',
    ) -> SMSLog:
        message = (
            f'Congratulations! {student_name} has been admitted to {grade} at '
            f'{school_name}. Please visit the school office to complete enrolment.'
        )
        return self.send(phone, message)

    def send_result_notification(
        self,
        phone: str,
        student_name: str,
        term: str,
        school_name: str = 'School',
    ) -> SMSLog:
        message = (
            f'Dear Parent/Guardian, {student_name}\'s {term} results are now '
            f'available on the parent portal. Log in to view them. - {school_name}'
        )
        return self.send(phone, message)
