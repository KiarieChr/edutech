# pyrefly: ignore [missing-import]
from twilio.rest import Client
from django.conf import settings
from .base import CommunicationProvider

class TwilioWhatsAppProvider(CommunicationProvider):
    def __init__(self):
        from crm.models.provider import ProviderConfig
        
        config = ProviderConfig.objects.filter(provider_type='twilio', is_active=True).first()
        
        self.account_sid = config.account_id if config else getattr(settings, 'TWILIO_ACCOUNT_SID', '')
        self.auth_token = config.api_key if config else getattr(settings, 'TWILIO_AUTH_TOKEN', '')
        self.sender = config.sender_id if config else getattr(settings, 'TWILIO_WHATSAPP_SENDER', '')
        
        # Use database use_mock if config exists, else fallback to settings
        if config:
            self.use_mock = config.use_mock
        else:
            self.use_mock = getattr(settings, 'CRM_USE_MOCK_PROVIDERS', False)
            
        self.client = Client(self.account_sid, self.auth_token) if self.account_sid else None

    def send_message(self, recipient_phone, message, **kwargs):
        if self.use_mock:
            print(f"[MOCK TWILIO] Sending WhatsApp to {recipient_phone}: {message}")
            return {
                "status": "sent",
                "provider_message_id": f"mock_tw_wa_{recipient_phone}_{hash(message)}"
            }

        if not self.client:
            return {"status": "failed", "error": "Twilio not configured"}
            
        try:
            # Twilio WhatsApp numbers must be prefixed with 'whatsapp:'
            to_number = f"whatsapp:{recipient_phone}"
            from_number = f"whatsapp:{self.sender}"
            
            message_obj = self.client.messages.create(
                body=message,
                from_=from_number,
                to=to_number,
                **kwargs
            )
            return {
                "status": "sent",
                "provider_message_id": message_obj.sid,
            }
        except Exception as e:
            return {"status": "failed", "error": str(e)}
