from django.contrib import admin
from .models.parent import ParentGuardian
from .models.relationship import ParentStudentRelationship
from .models.preference import ParentCommunicationPreference

@admin.register(ParentGuardian)
class ParentGuardianAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'phone', 'whatsapp_number', 'status')
    search_fields = ('first_name', 'last_name', 'phone', 'email')
    list_filter = ('status', 'preferred_language')

@admin.register(ParentStudentRelationship)
class ParentStudentRelationshipAdmin(admin.ModelAdmin):
    list_display = ('parent', 'student', 'relationship_type', 'is_primary_contact')
    search_fields = ('parent__first_name', 'parent__last_name', 'student__student__first_name')
    list_filter = ('relationship_type', 'is_primary_contact', 'is_emergency_contact')

@admin.register(ParentCommunicationPreference)
class ParentCommunicationPreferenceAdmin(admin.ModelAdmin):
    list_display = ('parent', 'whatsapp_enabled', 'sms_enabled', 'email_enabled', 'preferred_channel')
    list_filter = ('preferred_channel', 'whatsapp_enabled', 'sms_enabled')

from .models.communication import Communication, Conversation, ConversationMessage
from .models.template import CommunicationTemplate

@admin.register(CommunicationTemplate)
class CommunicationTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'created_at')
    list_filter = ('category',)
    search_fields = ('name',)

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('parent', 'channel', 'status', 'assigned_staff', 'last_message_at')
    list_filter = ('channel', 'status')
    search_fields = ('parent__first_name', 'parent__last_name')

@admin.register(Communication)
class CommunicationAdmin(admin.ModelAdmin):
    list_display = ('recipient_parent', 'channel', 'category', 'status', 'direction', 'sent_at')
    list_filter = ('channel', 'category', 'status', 'direction')
    search_fields = ('recipient_parent__first_name', 'recipient_parent__last_name')

from .models.campaign import Campaign, CampaignRecipient

@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'channel', 'status', 'scheduled_at', 'total_recipients')
    list_filter = ('category', 'channel', 'status')
    search_fields = ('name',)

@admin.register(CampaignRecipient)
class CampaignRecipientAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'parent', 'target_phone', 'status', 'sent_at')
    list_filter = ('status',)
    search_fields = ('parent__first_name', 'parent__last_name', 'target_phone')
