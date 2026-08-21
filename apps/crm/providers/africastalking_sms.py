# pyrefly: ignore [missing-import]
import africastalking
from django.conf import settings
from .base import CommunicationProvider

class AfricaTalkingSmsProvider(CommunicationProvider):
    def __init__(self):
        from crm.models.provider import ProviderConfig
        
        config = ProviderConfig.objects.filter(provider_type='africastalking', is_active=True).first()
        
        self.username = config.account_id if config else getattr(settings, 'AT_USERNAME', 'sandbox')
        self.api_key = config.api_key if config else getattr(settings, 'AT_API_KEY', '')
        self.sender_id = config.sender_id if config else getattr(settings, 'AT_SENDER_ID', '')
        
        if config:
            self.use_mock = config.use_mock
        else:
            self.use_mock = getattr(settings, 'CRM_USE_MOCK_PROVIDERS', False)
        
        if self.username and self.api_key:
            africastalking.initialize(self.username, self.api_key)
            self.sms = africastalking.SMS
        else:
            self.sms = None

    def send_message(self, recipient_phone, message, **kwargs):
        if self.use_mock:
            print(f"[MOCK AFRICA'S TALKING] Sending SMS to {recipient_phone}: {message}")
            return {
                "status": "sent",
                "provider_message_id": f"mock_at_sms_{recipient_phone}_{hash(message)}"
            }

        if not self.sms:
            return {"status": "failed", "error": "Africa's Talking not configured"}
            
        try:
            response = self.sms.send(message, [recipient_phone], self.sender_id)
            
            recipients = response.get('SMSMessageData', {}).get('Recipients', [])
            if recipients and recipients[0].get('status') == 'Success':
                return {
                    "status": "sent",
                    "provider_message_id": recipients[0].get('messageId')
                }
            else:
                error = recipients[0].get('status') if recipients else "Unknown error"
                return {"status": "failed", "error": error}
        except Exception as e:
            return {"status": "failed", "error": str(e)}
