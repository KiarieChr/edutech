from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .webhooks import twilio_webhook, africastalking_webhook, simulate_inbound
from .views import ParentGuardianViewSet, CampaignViewSet, CommunicationViewSet, ConversationViewSet, ConversationMessageViewSet, ProviderConfigViewSet

app_name = 'crm'

router = DefaultRouter()
router.register(r'parents', ParentGuardianViewSet, basename='parent')
router.register(r'campaigns', CampaignViewSet, basename='campaign')
router.register(r'communications', CommunicationViewSet, basename='communication')
router.register(r'conversations', ConversationViewSet, basename='conversation')
router.register(r'messages', ConversationMessageViewSet, basename='message')
router.register(r'provider-configs', ProviderConfigViewSet, basename='provider-config')

urlpatterns = [
    path('webhooks/twilio/', twilio_webhook, name='twilio-webhook'),
    path('webhooks/africastalking/', africastalking_webhook, name='at-webhook'),
    path('webhooks/simulate/', simulate_inbound, name='simulate-inbound'),
    path('', include(router.urls)),
]
