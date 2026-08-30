from django.urls import path
from . import views

urlpatterns = [
    path("", views.PaymentGetwaysView.as_view(), name="payment_gateways"),
    path("paypal/", views.payment_paypal, name="paypal"),
    path("stripe/", views.payment_stripe, name="stripe"),
    path("coinbase/", views.payment_coinbase, name="coinbase"),
    path("paylike/", views.payment_paylike, name="paylike"),
    path("stripe-charge/", views.stripe_charge, name="stripe_charge"),
    path("gopay-charge/", views.gopay_charge, name="gopay_charge"),
    path("payment-succeed/", views.payment_succeed, name="payment-succeed"),
    path("complete/", views.paymentComplete, name="complete"),
    path("create-invoice/", views.create_invoice, name="create_invoice"),
    path("invoice-detail/<int:id>/", views.invoice_detail, name="invoice_detail"),

    # ── Gateway configuration (admin) ────────────────────────────────────────
    path("gateway-configs/", views.list_gateway_configs, name="list_gateway_configs"),
    path("gateway-configs/save/", views.save_gateway_config, name="save_gateway_config"),
    path("gateway-configs/<int:pk>/delete/", views.delete_gateway_config, name="delete_gateway_config"),

    # ── Daraja / M-Pesa ──────────────────────────────────────────────────────
    path("mpesa/stk-push/", views.daraja_stk_push, name="daraja_stk_push"),
    path("mpesa/stk-query/", views.daraja_stk_query, name="daraja_stk_query"),
    path("mpesa/callback/", views.daraja_callback, name="daraja_callback"),
    path("mpesa/register-urls/", views.daraja_register_urls, name="daraja_register_urls"),
    path("mpesa/c2b/validate/", views.daraja_c2b_validation, name="daraja_c2b_validation"),
    path("mpesa/c2b/confirm/", views.daraja_c2b_confirmation, name="daraja_c2b_confirmation"),

    # ── Paystack ─────────────────────────────────────────────────────────────
    path("paystack/initialize/", views.paystack_initialize, name="paystack_initialize"),
    path("paystack/verify/", views.paystack_verify, name="paystack_verify"),
    path("paystack/webhook/", views.paystack_webhook, name="paystack_webhook"),

    # ── SMS ──────────────────────────────────────────────────────────────────
    path("sms/send/", views.send_sms, name="send_sms"),
    path("sms/send-bulk/", views.send_sms_bulk, name="send_sms_bulk"),

    # ── Transactions ─────────────────────────────────────────────────────────
    path("transactions/", views.transaction_list, name="transaction_list"),
]
