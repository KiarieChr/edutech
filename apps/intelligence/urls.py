from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import report_card_narrative, ask_intelligence, AnthropicAPIKeyViewSet, IntelligenceChatSessionViewSet

router = DefaultRouter()
router.register(r'anthropic-keys', AnthropicAPIKeyViewSet, basename='anthropic-keys')
router.register(r'chat-sessions', IntelligenceChatSessionViewSet, basename='chat-sessions')

urlpatterns = [
    path('report-card-narrative/', report_card_narrative, name='report_card_narrative'),
    path('ask/', ask_intelligence, name='ask_intelligence'),
]

urlpatterns += router.urls
