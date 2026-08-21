from django.db import models
from .parent import ParentGuardian

class ParentCommunicationPreference(models.Model):
    parent = models.OneToOneField(ParentGuardian, on_delete=models.CASCADE, related_name='communication_preferences')
    
    sms_enabled = models.BooleanField(default=True)
    whatsapp_enabled = models.BooleanField(default=True)
    email_enabled = models.BooleanField(default=True)
    portal_notifications_enabled = models.BooleanField(default=True)
    
    preferred_channel = models.CharField(max_length=20, default='whatsapp')
    
    marketing_enabled = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "crm_parent_communication_preference"
