from django.db import models
from django.conf import settings

class IntelligenceAuditLog(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    data_scope_queried = models.CharField(max_length=255)
    document_type_generated = models.CharField(max_length=100)
    approval_status = models.CharField(max_length=50, default='PENDING', choices=[
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('DISCARDED', 'Discarded')
    ])

    class Meta:
        db_table = 'intelligence_audit_log'
        ordering = ['-timestamp']

class IntelligenceUsage(models.Model):
    month = models.DateField()
    documents_generated = models.IntegerField(default=0)
    tokens_approx = models.IntegerField(default=0)
    cost_approx = models.DecimalField(max_digits=10, decimal_places=4, default=0.0)

    class Meta:
        db_table = 'intelligence_usage'
        unique_together = ('month',)
        ordering = ['-month']

class AnthropicAPIKey(models.Model):
    name = models.CharField(max_length=255, help_text="A name to identify this key, e.g. 'Production Key'")
    api_key = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'anthropic_api_key'
        verbose_name = 'Anthropic API Key'
        verbose_name_plural = 'Anthropic API Keys'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {'Active' if self.is_active else 'Inactive'}"

class IntelligenceChatSession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_chat_sessions')
    title = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'intelligence_chat_session'
        ordering = ['-updated_at']

    def __str__(self):
        return self.title or f"Chat Session {self.id}"

class IntelligenceChatMessage(models.Model):
    session = models.ForeignKey(IntelligenceChatSession, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=50, choices=[('user', 'User'), ('assistant', 'Assistant')])
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'intelligence_chat_message'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.role} at {self.created_at}"
