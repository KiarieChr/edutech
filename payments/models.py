from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class Invoice(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    total = models.FloatField(null=True, blank=True)
    amount = models.FloatField(null=True, blank=True)
    payment_complete = models.BooleanField(default=False)
    invoice_code = models.CharField(max_length=200, blank=True, null=True)


# ─── Integration credential storage ──────────────────────────────────────────

class GatewayConfig(models.Model):
    """
    Stores third-party API credentials in the database so they can be managed
    through the admin UI or a settings page — never hard-coded or in .env.

    Each provider has exactly ONE active config row (enforced by the unique
    (provider, is_active=True) convention + save() override below).
    """

    PROVIDER_CHOICES = [
        # Payment gateways
        ('daraja', 'Safaricom Daraja (M-Pesa)'),
        ('paystack', 'Paystack'),
        # SMS providers
        ('africastalking', "Africa's Talking SMS"),
        ('twilio', 'Twilio SMS'),
        ('infobip', 'Infobip SMS'),
    ]

    ENVIRONMENT_CHOICES = [
        ('sandbox', 'Sandbox / Test'),
        ('production', 'Production / Live'),
    ]

    provider = models.CharField(max_length=40, choices=PROVIDER_CHOICES)
    label = models.CharField(
        max_length=80, blank=True,
        help_text='Friendly name, e.g. "School M-Pesa till"',
    )
    environment = models.CharField(
        max_length=20, choices=ENVIRONMENT_CHOICES, default='sandbox',
    )
    is_active = models.BooleanField(default=False)

    # ── Daraja fields ─────────────────────────────────────────────────────────
    consumer_key = models.CharField(max_length=200, blank=True)
    consumer_secret = models.CharField(max_length=200, blank=True)
    shortcode = models.CharField(
        max_length=20, blank=True,
        help_text='Business shortcode (paybill or till number)',
    )
    passkey = models.CharField(
        max_length=400, blank=True,
        help_text='Lipa-Na-M-Pesa online passkey',
    )
    callback_url = models.URLField(
        blank=True,
        help_text='Public HTTPS URL Safaricom will POST payment results to',
    )
    b2c_initiator_name = models.CharField(max_length=100, blank=True)
    b2c_initiator_password = models.CharField(max_length=200, blank=True)
    b2c_result_url = models.URLField(blank=True)
    b2c_queue_timeout_url = models.URLField(blank=True)

    # ── Paystack fields ───────────────────────────────────────────────────────
    public_key = models.CharField(max_length=200, blank=True)
    secret_key = models.CharField(max_length=200, blank=True)

    # ── SMS provider fields ───────────────────────────────────────────────────
    api_key = models.CharField(max_length=300, blank=True)
    api_secret = models.CharField(max_length=300, blank=True)    # Africa's Talking / Infobip
    username = models.CharField(max_length=100, blank=True)      # Africa's Talking username
    sender_id = models.CharField(
        max_length=20, blank=True,
        help_text='Alphanumeric sender ID shown on recipient\'s phone',
    )
    account_sid = models.CharField(max_length=100, blank=True)   # Twilio
    auth_token = models.CharField(max_length=200, blank=True)    # Twilio
    from_number = models.CharField(max_length=20, blank=True)    # Twilio

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Gateway Config'
        verbose_name_plural = 'Gateway Configs'
        ordering = ['provider']

    def __str__(self):
        env = '🟢' if self.environment == 'production' else '🟡'
        return f"{env} {self.get_provider_display()} — {self.label or self.environment}"

    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def get_active(cls, provider: str) -> 'GatewayConfig':
        """
        Fetch the single active config for a provider.
        Raises GatewayConfig.DoesNotExist if not configured.
        """
        return cls.objects.get(provider=provider, is_active=True)


# ─── Payment transaction log ─────────────────────────────────────────────────

class PaymentTransaction(models.Model):
    """
    Immutable log of every payment attempt, regardless of provider.
    Links to fees.FeeInvoice when available.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('reversed', 'Reversed'),
    ]
    PROVIDER_CHOICES = GatewayConfig.PROVIDER_CHOICES

    provider = models.CharField(max_length=40, choices=PROVIDER_CHOICES)
    reference = models.CharField(max_length=100, unique=True, db_index=True)
    external_reference = models.CharField(
        max_length=100, blank=True,
        help_text='Provider transaction ID, e.g. Safaricom CheckoutRequestID',
    )
    phone = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=5, default='KES')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    description = models.CharField(max_length=255, blank=True)
    fee_invoice = models.ForeignKey(
        'fees.FeeInvoice', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='payment_transactions',
    )
    student = models.ForeignKey(
        'accounts.Student', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='payment_transactions',
    )
    raw_request = models.JSONField(default=dict, blank=True)
    raw_response = models.JSONField(default=dict, blank=True)
    failure_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.provider} | {self.reference} | {self.status}"


# ─── SMS log ─────────────────────────────────────────────────────────────────

class SMSLog(models.Model):
    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
    ]

    provider = models.CharField(max_length=40)
    recipient = models.CharField(max_length=20)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    message_id = models.CharField(max_length=100, blank=True)
    cost = models.CharField(max_length=20, blank=True)
    failure_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.provider} → {self.recipient} [{self.status}]"

