from rest_framework import serializers
from .models import AnthropicAPIKey, IntelligenceChatSession, IntelligenceChatMessage

class AnthropicAPIKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = AnthropicAPIKey
        fields = ['id', 'name', 'api_key', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
        
    def to_representation(self, instance):
        return super().to_representation(instance)

class IntelligenceChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = IntelligenceChatMessage
        fields = ['id', 'role', 'content', 'created_at']

class IntelligenceChatSessionSerializer(serializers.ModelSerializer):
    messages = IntelligenceChatMessageSerializer(many=True, read_only=True)
    
    class Meta:
        model = IntelligenceChatSession
        fields = ['id', 'title', 'created_at', 'updated_at', 'messages']
