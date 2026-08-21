from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
# pyrefly: ignore [missing-import]
from django_q.tasks import async_task
from django.db import connection

from django.utils import timezone
from .models.parent import ParentGuardian
from .models.campaign import Campaign
from .models.communication import Communication, Conversation, ConversationMessage
from .models.provider import ProviderConfig
from .serializers import ParentGuardianSerializer, CampaignSerializer, CommunicationSerializer, ConversationSerializer, ConversationMessageSerializer, ProviderConfigSerializer
from .providers.twilio_whatsapp import TwilioWhatsAppProvider
from .providers.africastalking_sms import AfricaTalkingSmsProvider

class ParentGuardianViewSet(viewsets.ModelViewSet):
    queryset = ParentGuardian.objects.filter(status='active').prefetch_related('students__student__student')
    serializer_class = ParentGuardianSerializer

class CampaignViewSet(viewsets.ModelViewSet):
    queryset = Campaign.objects.all()
    serializer_class = CampaignSerializer

    def create(self, request, *args, **kwargs):
        # We override create to immediately trigger the processing task
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Save the campaign
        campaign = serializer.save(status='PROCESSING')
        
        # Trigger the audience resolution and sending task via django-q
        schema_name = connection.schema_name
        async_task('crm.tasks.campaigns.process_campaign_audience', campaign.id, schema_name)
        
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

class CommunicationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Communication.objects.all()
    serializer_class = CommunicationSerializer

class ProviderConfigViewSet(viewsets.ModelViewSet):
    queryset = ProviderConfig.objects.all()
    serializer_class = ProviderConfigSerializer

class ConversationViewSet(viewsets.ModelViewSet):
    queryset = Conversation.objects.all().select_related('parent').prefetch_related('messages')
    serializer_class = ConversationSerializer
    
    @action(detail=True, methods=['post'])
    def reply(self, request, pk=None):
        conversation = self.get_object()
        body = request.data.get('message')
        if not body:
            return Response({"error": "Message is required"}, status=status.HTTP_400_BAD_REQUEST)
            
        provider = None
        if conversation.channel == 'WHATSAPP':
            provider = TwilioWhatsAppProvider()
            phone = conversation.parent.whatsapp_number
        elif conversation.channel == 'SMS':
            provider = AfricaTalkingSmsProvider()
            phone = conversation.parent.phone
            
        if not provider or not phone:
            return Response({"error": f"Cannot send via {conversation.channel}"}, status=status.HTTP_400_BAD_REQUEST)
            
        response = provider.send_message(phone, body)
        
        msg_status = 'SENT' if response.get('status') == 'sent' else 'FAILED'
        msg = ConversationMessage.objects.create(
            conversation=conversation,
            direction='OUTBOUND',
            sender=request.user,
            body=body,
            status=msg_status,
            provider_message_id=response.get('provider_message_id')
        )
        
        conversation.last_message_at = timezone.now()
        conversation.last_outbound_at = timezone.now()
        conversation.save()
        
        return Response(ConversationMessageSerializer(msg).data)
        
class ConversationMessageViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ConversationMessage.objects.all()
    serializer_class = ConversationMessageSerializer
    
    def get_queryset(self):
        qs = super().get_queryset()
        conversation_id = self.request.query_params.get('conversation_id')
        if conversation_id:
            qs = qs.filter(conversation_id=conversation_id)
        return qs
