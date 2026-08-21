from django.db import models
from django.conf import settings
from .template import CommunicationTemplate
from .parent import ParentGuardian

class Campaign(models.Model):
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=50, default='GENERAL')
    channel = models.CharField(max_length=20) # WHATSAPP, SMS
    
    # Audience filters stored as JSON
    audience_filters = models.JSONField(default=dict)
    
    template = models.ForeignKey(CommunicationTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    custom_message = models.TextField(blank=True, null=True)
    
    status = models.CharField(max_length=20, default='DRAFT') # DRAFT, PROCESSING, SCHEDULED, SENDING, COMPLETED, PAUSED, CANCELLED
    
    scheduled_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Analytics
    total_recipients = models.IntegerField(default=0)
    sent_count = models.IntegerField(default=0)
    delivered_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "crm_campaign"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

class CampaignRecipient(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='recipients')
    parent = models.ForeignKey(ParentGuardian, on_delete=models.CASCADE)
    
    # Denormalize target numbers at time of snapshot
    target_phone = models.CharField(max_length=60)
    
    # Snapshot of data for personalization (since parents can have multiple children)
    context_data = models.JSONField(default=dict)
    
    status = models.CharField(max_length=20, default='PENDING') # PENDING, SENT, FAILED
    provider_message_id = models.CharField(max_length=120, blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "crm_campaign_recipient"
        unique_together = ('campaign', 'parent')
