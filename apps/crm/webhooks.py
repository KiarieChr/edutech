import logging
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from .models.parent import ParentGuardian
from .models.communication import Conversation, ConversationMessage

logger = logging.getLogger(__name__)

def process_inbound_message(phone_number, body, channel, provider_message_id):
    # Try to find the parent by phone or whatsapp_number
    parent = ParentGuardian.objects.filter(phone=phone_number).first()
    if not parent:
        parent = ParentGuardian.objects.filter(whatsapp_number=phone_number).first()
        
    if not parent:
        logger.warning(f"Inbound message from unknown number {phone_number}")
        return False
        
    # Get or create conversation
    conversation, created = Conversation.objects.get_or_create(
        parent=parent,
        channel=channel,
        defaults={'status': 'OPEN'}
    )
    
    # Update conversation status if it was closed
    if conversation.status == 'CLOSED':
        conversation.status = 'OPEN'
        
    conversation.last_message_at = timezone.now()
    conversation.last_inbound_at = timezone.now()
    conversation.save()
    
    # Create message
    ConversationMessage.objects.create(
        conversation=conversation,
        direction='INBOUND',
        body=body,
        status='DELIVERED',
        provider_message_id=provider_message_id
    )
    
    return True


@api_view(['POST'])
@permission_classes([AllowAny])
def twilio_webhook(request):
    """Webhook receiver for Twilio WhatsApp"""
    # Twilio sends form data
    from_number = request.data.get('From', '')
    body = request.data.get('Body', '')
    message_sid = request.data.get('MessageSid', '')
    
    # Format: whatsapp:+254...
    if from_number.startswith('whatsapp:'):
        from_number = from_number.replace('whatsapp:', '')
        
    if from_number and body:
        process_inbound_message(from_number, body, 'WHATSAPP', message_sid)
        
    # Twilio expects empty TwiML response
    return Response("<Response></Response>", content_type="text/xml", status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
def africastalking_webhook(request):
    """Webhook receiver for Africa's Talking SMS"""
    from_number = request.data.get('from', '')
    body = request.data.get('text', '')
    message_id = request.data.get('id', '')
    
    if from_number and body:
        process_inbound_message(from_number, body, 'SMS', message_id)
        
    return Response({"status": "success"}, status=status.HTTP_200_OK)


@api_view(['POST'])
# We can leave this open for the frontend dummy tester
@permission_classes([AllowAny])
def simulate_inbound(request):
    """Dummy endpoint to simulate an inbound message from frontend"""
    phone_number = request.data.get('phone')
    body = request.data.get('message')
    channel = request.data.get('channel', 'WHATSAPP')
    
    if not phone_number or not body:
        return Response({"error": "phone and message required"}, status=status.HTTP_400_BAD_REQUEST)
        
    success = process_inbound_message(phone_number, body, channel, f"sim_{timezone.now().timestamp()}")
    
    if success:
        return Response({"status": "simulated"})
    else:
        return Response({"error": "Parent not found"}, status=status.HTTP_404_NOT_FOUND)
