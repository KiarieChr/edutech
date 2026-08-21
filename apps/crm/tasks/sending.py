import logging
from django.db import transaction
from ..models.campaign import Campaign, CampaignRecipient
from ..models.communication import Communication
from ..providers.twilio_whatsapp import TwilioWhatsAppProvider
from ..providers.africastalking_sms import AfricaTalkingSmsProvider

logger = logging.getLogger(__name__)

def dispatch_campaign_messages(campaign_id, schema_name):
    try:
        from django.db import connection
        connection.set_schema(schema_name)
    except Exception:
        pass
        
    try:
        campaign = Campaign.objects.get(id=campaign_id)
        if campaign.status != 'SCHEDULED':
            return
            
        campaign.status = 'SENDING'
        campaign.save()
        
        provider = None
        if campaign.channel == 'WHATSAPP':
            provider = TwilioWhatsAppProvider()
        elif campaign.channel == 'SMS':
            provider = AfricaTalkingSmsProvider()
            
        if not provider:
            logger.error(f"No provider found for channel {campaign.channel}")
            return
            
        recipients = campaign.recipients.filter(status='PENDING')
        
        sent_count = campaign.sent_count
        failed_count = campaign.failed_count
        
        for recipient in recipients:
            body = campaign.template.body if campaign.template else campaign.custom_message
            if not body:
                body = ""
                
            body = body.replace('{{first_name}}', recipient.context_data.get('first_name', 'Parent'))
            body = body.replace('{{students_names}}', recipient.context_data.get('students_names', 'your child'))
            
            response = provider.send_message(recipient.target_phone, body)
            
            comm = Communication.objects.create(
                recipient_parent=recipient.parent,
                category=campaign.category,
                channel=campaign.channel,
                direction='OUTBOUND',
                message_body=body,
                template=campaign.template,
                status=response.get('status', 'FAILED').upper(),
                provider=campaign.channel,
                provider_message_id=response.get('provider_message_id', '')
            )
            
            if response.get('status') == 'sent':
                recipient.status = 'SENT'
                recipient.provider_message_id = response.get('provider_message_id')
                sent_count += 1
            else:
                recipient.status = 'FAILED'
                recipient.error_message = response.get('error', 'Unknown Error')
                failed_count += 1
                
            recipient.save()
            
        campaign.sent_count = sent_count
        campaign.failed_count = failed_count
        campaign.status = 'COMPLETED'
        campaign.save()
        
    except Exception as e:
        logger.error(f"Failed to dispatch campaign {campaign_id}: {str(e)}")
