from rest_framework import serializers
from .models.parent import ParentGuardian
from .models.campaign import Campaign
from .models.communication import Communication, Conversation, ConversationMessage

from .models.provider import ProviderConfig

class ProviderConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderConfig
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']

class ConversationMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversationMessage
        fields = '__all__'

class ConversationSerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source='parent.first_name', read_only=True)
    parent_full_name = serializers.SerializerMethodField()
    phone = serializers.CharField(source='parent.phone', read_only=True)
    whatsapp_number = serializers.CharField(source='parent.whatsapp_number', read_only=True)
    recent_message = serializers.SerializerMethodField()
    
    class Meta:
        model = Conversation
        fields = '__all__'
        
    def get_parent_full_name(self, obj):
        return f"{obj.parent.first_name} {obj.parent.last_name}"
        
    def get_recent_message(self, obj):
        msg = obj.messages.order_by('-sent_at').first()
        return msg.body if msg else "No messages yet"

class ParentGuardianSerializer(serializers.ModelSerializer):
    students = serializers.SerializerMethodField()

    class Meta:
        model = ParentGuardian
        fields = ['id', 'first_name', 'last_name', 'phone', 'whatsapp_number', 'email', 'status', 'students']
        
    def get_students(self, obj):
        return [
            f"{rel.student.student.first_name} {rel.student.student.last_name}"
            for rel in obj.students.all()
        ]

class CampaignSerializer(serializers.ModelSerializer):
    class Meta:
        model = Campaign
        fields = '__all__'
        read_only_fields = ['total_recipients', 'sent_count', 'delivered_count', 'failed_count', 'status', 'created_at']

class CommunicationSerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source='recipient_parent.first_name', read_only=True)
    
    class Meta:
        model = Communication
        fields = '__all__'
