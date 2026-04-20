from django.contrib import admin
from .models import GatewayConfig, PaymentTransaction, SMSLog, Invoice


@admin.register(GatewayConfig)
class GatewayConfigAdmin(admin.ModelAdmin):
    list_display = ('provider', 'label', 'environment', 'is_active', 'updated_at')
    list_filter = ('provider', 'environment', 'is_active')
    search_fields = ('label', 'shortcode', 'username')
    # Sensitive key fields — still visible to super-admins but not in list view
    fieldsets = (
        ('Identity', {'fields': ('provider', 'label', 'environment', 'is_active')}),
        ('Daraja (Safaricom M-Pesa)', {
            'classes': ('collapse',),
            'fields': (
                'consumer_key', 'consumer_secret', 'shortcode', 'passkey',
                'callback_url', 'b2c_initiator_name', 'b2c_initiator_password',
                'b2c_result_url', 'b2c_queue_timeout_url',
            ),
        }),
        ('Paystack', {
            'classes': ('collapse',),
            'fields': ('public_key', 'secret_key'),
        }),
        ('SMS Provider', {
            'classes': ('collapse',),
            'fields': (
                'api_key', 'api_secret', 'username', 'sender_id',
                'account_sid', 'auth_token', 'from_number',
            ),
        }),
    )


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ('reference', 'provider', 'phone', 'amount', 'currency', 'status', 'created_at')
    list_filter = ('provider', 'status', 'currency')
    search_fields = ('reference', 'external_reference', 'phone')
    readonly_fields = ('reference', 'created_at', 'updated_at', 'raw_request', 'raw_response')
    date_hierarchy = 'created_at'


@admin.register(SMSLog)
class SMSLogAdmin(admin.ModelAdmin):
    list_display = ('provider', 'recipient', 'status', 'message_id', 'cost', 'created_at')
    list_filter = ('provider', 'status')
    search_fields = ('recipient', 'message_id')
    readonly_fields = ('created_at',)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_code', 'user', 'amount', 'total', 'payment_complete')
    list_filter = ('payment_complete',)
    search_fields = ('invoice_code', 'user__email')
