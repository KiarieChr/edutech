from django.db import models
from django.conf import settings
from .parent import ParentGuardian
from student_management.models.profiles import Student
from .template import CommunicationTemplate

class Conversation(models.Model):
    parent = models.ForeignKey(ParentGuardian, on_delete=models.CASCADE, related_name='conversations')
    channel = models.CharField(max_length=20) # WHATSAPP, SMS, PORTAL
    assigned_staff = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, default='OPEN')
    last_message_at = models.DateTimeField(null=True, blank=True)
    last_inbound_at = models.DateTimeField(null=True, blank=True)
    last_outbound_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "crm_conversation"
        ordering = ["-last_message_at"]

    def __str__(self):
        return f"Conversation with {self.parent} via {self.channel}"

class ConversationMessage(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    direction = models.CharField(max_length=10) # INBOUND, OUTBOUND
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    body = models.TextField()
    provider_message_id = models.CharField(max_length=120, blank=True, null=True)
    status = models.CharField(max_length=20, default='SENT') # SENT, DELIVERED, READ, FAILED
    
    ai_generated = models.BooleanField(default=False)
    ai_confidence = models.FloatField(null=True, blank=True)
    
    sent_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "crm_conversation_message"
        ordering = ["sent_at"]

    def __str__(self):
        return f"{self.direction} at {self.sent_at}"

class Communication(models.Model):
    recipient_parent = models.ForeignKey(ParentGuardian, on_delete=models.CASCADE, related_name='communications')
    student = models.ForeignKey(Student, on_delete=models.SET_NULL, null=True, blank=True, related_name='crm_communications')
    category = models.CharField(max_length=50, default='GENERAL')
    channel = models.CharField(max_length=20) # WHATSAPP, SMS
    
    direction = models.CharField(max_length=10, default='OUTBOUND')
    message_body = models.TextField()
    template = models.ForeignKey(CommunicationTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    
    status = models.CharField(max_length=20, default='PENDING') # PENDING, QUEUED, SENT, DELIVERED, READ, FAILED
    provider = models.CharField(max_length=50, blank=True, null=True)
    provider_message_id = models.CharField(max_length=120, blank=True, null=True)
    conversation = models.ForeignKey(Conversation, on_delete=models.SET_NULL, null=True, blank=True, related_name='communications')
    
    scheduled_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "crm_communication"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.channel} to {self.recipient_parent} ({self.status})"
