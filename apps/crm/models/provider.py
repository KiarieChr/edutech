from django.db import models

class ProviderConfig(models.Model):
    PROVIDER_CHOICES = (
        ('twilio', 'Twilio (WhatsApp/SMS)'),
        ('africastalking', "Africa's Talking (SMS)"),
    )
    
    provider_type = models.CharField(max_length=50, choices=PROVIDER_CHOICES, unique=True)
    account_id = models.CharField(max_length=255, blank=True, null=True, help_text="Twilio Account SID or AT Username")
    api_key = models.CharField(max_length=255, blank=True, null=True, help_text="Twilio Auth Token or AT API Key")
    sender_id = models.CharField(max_length=100, blank=True, null=True, help_text="Twilio Phone Number or AT Sender ID")
    is_active = models.BooleanField(default=True, help_text="Enable or disable this provider")
    use_mock = models.BooleanField(default=False, help_text="Use mock sending for testing/development without using credits")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "crm_provider_config"
        verbose_name = "Provider Configuration"
        verbose_name_plural = "Provider Configurations"

    def __str__(self):
        return f"{self.get_provider_type_display()} Config"
