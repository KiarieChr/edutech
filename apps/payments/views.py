import stripe
import uuid
import json

from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.response import Response
from rest_framework import status as http_status

from .models import GatewayConfig, PaymentTransaction, SMSLog
from .services import DarajaService, DarajaError, PaystackService, PaystackError, SMSService, SMSError


# ─── Gateway Config management ───────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAdminUser])
def list_gateway_configs(request):
    """List all gateway/SMS configurations (admin only)."""
    configs = GatewayConfig.objects.all().values(
        'id', 'provider', 'label', 'environment', 'is_active', 'created_at',
    )
    return Response(list(configs))


@api_view(['POST'])
@permission_classes([IsAdminUser])
def save_gateway_config(request):
    """Create or update a gateway configuration (admin only)."""
    data = request.data
    config_id = data.get('id')
    provider = data.get('provider', '')

    if config_id:
        try:
            cfg = GatewayConfig.objects.get(pk=config_id)
        except GatewayConfig.DoesNotExist:
            return Response({'error': 'Config not found'}, status=404)
    else:
        cfg = GatewayConfig(provider=provider)

    # Update all provided fields
    ALLOWED_FIELDS = [
        'provider', 'label', 'environment', 'is_active',
        'consumer_key', 'consumer_secret', 'shortcode', 'passkey',
        'callback_url', 'b2c_initiator_name', 'b2c_initiator_password',
        'b2c_result_url', 'b2c_queue_timeout_url',
        'public_key', 'secret_key',
        'api_key', 'api_secret', 'username', 'sender_id',
        'account_sid', 'auth_token', 'from_number',
    ]
    for field in ALLOWED_FIELDS:
        if field in data:
            setattr(cfg, field, data[field])

    cfg.save()
    return Response({'success': True, 'id': cfg.pk})


@api_view(['DELETE'])
@permission_classes([IsAdminUser])
def delete_gateway_config(request, pk):
    deleted, _ = GatewayConfig.objects.filter(pk=pk).delete()
    if deleted:
        return Response({'success': True})
    return Response({'error': 'Not found'}, status=404)


# ─── Daraja STK Push ─────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def daraja_stk_push(request):
    """
    Trigger an M-Pesa STK Push (prompt on customer phone).
    Body: { phone, amount, account_reference, description, fee_invoice_id? }
    """
    data = request.data
    required = ['phone', 'amount', 'account_reference']
    missing = [f for f in required if not data.get(f)]
    if missing:
        return Response({'error': f'Missing fields: {", ".join(missing)}'}, status=400)

    try:
        svc = DarajaService()
        result = svc.stk_push(
            phone=data['phone'],
            amount=int(data['amount']),
            account_reference=data['account_reference'],
            description=data.get('description', 'Fee payment'),
            fee_invoice_id=data.get('fee_invoice_id'),
            student_id=data.get('student_id'),
        )
        return Response(result)
    except DarajaError as exc:
        return Response({'error': str(exc)}, status=400)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def daraja_stk_query(request):
    """Query the status of an STK Push. Body: { checkout_request_id }"""
    checkout_id = request.data.get('checkout_request_id')
    if not checkout_id:
        return Response({'error': 'checkout_request_id required'}, status=400)
    try:
        svc = DarajaService()
        return Response(svc.stk_query(checkout_id))
    except DarajaError as exc:
        return Response({'error': str(exc)}, status=400)


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def daraja_callback(request):
    """
    Receives M-Pesa payment result from Safaricom.
    This URL must be publicly accessible (HTTPS) — register it in GatewayConfig.callback_url.
    """
    DarajaService.handle_stk_callback(request.data)
    return Response({'ResultCode': 0, 'ResultDesc': 'Accepted'})


@api_view(['POST'])
@permission_classes([IsAdminUser])
def daraja_register_urls(request):
    """Register C2B validation/confirmation URLs with Safaricom (admin only)."""
    data = request.data
    try:
        svc = DarajaService()
        result = svc.register_c2b_urls(
            validation_url=data.get('validation_url', ''),
            confirmation_url=data.get('confirmation_url', ''),
        )
        return Response(result)
    except DarajaError as exc:
        return Response({'error': str(exc)}, status=400)


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def daraja_c2b_validation(request):
    """
    Validation URL for M-Pesa C2B.
    Called by Safaricom before completing a payment to verify the account number.
    """
    result = DarajaService.handle_c2b_validation(request.data)
    return Response(result)


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def daraja_c2b_confirmation(request):
    """
    Confirmation URL for M-Pesa C2B.
    Called by Safaricom when payment is completed.
    """
    DarajaService.handle_c2b_confirmation(request.data)
    return Response({'ResultCode': 0, 'ResultDesc': 'Accepted'})


# ─── Paystack ────────────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def paystack_initialize(request):
    """
    Start a Paystack payment (card / mobile_money / bank etc.).
    Body: { email, amount, phone?, channel?, callback_url?, fee_invoice_id? }
    Returns authorization_url to redirect the payer to.
    """
    data = request.data
    if not data.get('email') or not data.get('amount'):
        return Response({'error': 'email and amount are required'}, status=400)
    try:
        svc = PaystackService()
        result = svc.initialize(
            email=data['email'],
            amount_kes=float(data['amount']),
            phone=data.get('phone', ''),
            channel=data.get('channel', 'mobile_money'),
            callback_url=data.get('callback_url', ''),
            fee_invoice_id=data.get('fee_invoice_id'),
            student_id=data.get('student_id'),
            metadata=data.get('metadata'),
        )
        return Response(result)
    except PaystackError as exc:
        return Response({'error': str(exc)}, status=400)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def paystack_verify(request):
    """Verify a Paystack transaction. Query param: ?reference=<ref>"""
    ref = request.query_params.get('reference')
    if not ref:
        return Response({'error': 'reference required'}, status=400)
    try:
        svc = PaystackService()
        return Response(svc.verify(ref))
    except PaystackError as exc:
        return Response({'error': str(exc)}, status=400)


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def paystack_webhook(request):
    """Receives Paystack webhook events. Must be registered in your Paystack dashboard."""
    sig = request.headers.get('X-Paystack-Signature', '')
    try:
        svc = PaystackService()
        svc.handle_webhook(request.data, sig)
    except PaystackError:
        pass  # misconfigured — still return 200 so Paystack stops retrying
    return Response(status=200)


# ─── SMS ─────────────────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdminUser])
def send_sms(request):
    """
    Send a one-off SMS (admin only).
    Body: { recipient, message, provider? }
    """
    data = request.data
    recipient = data.get('recipient')
    message = data.get('message')
    if not recipient or not message:
        return Response({'error': 'recipient and message are required'}, status=400)
    try:
        svc = SMSService(provider_key=data.get('provider'))
        log = svc.send(recipient, message)
        return Response({'success': log.status == 'sent', 'log_id': log.pk, 'status': log.status})
    except SMSError as exc:
        return Response({'error': str(exc)}, status=400)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def send_sms_bulk(request):
    """
    Send the same message to multiple recipients.
    Body: { recipients: [...], message, provider? }
    """
    data = request.data
    recipients = data.get('recipients', [])
    message = data.get('message', '')
    if not recipients or not message:
        return Response({'error': 'recipients and message are required'}, status=400)
    try:
        svc = SMSService(provider_key=data.get('provider'))
        logs = svc.send_bulk(recipients, message)
        return Response({
            'sent': sum(1 for l in logs if l.status == 'sent'),
            'failed': sum(1 for l in logs if l.status == 'failed'),
            'total': len(logs),
        })
    except SMSError as exc:
        return Response({'error': str(exc)}, status=400)


# ─── Transaction history ─────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def transaction_list(request):
    """List payment transactions with optional filters."""
    qs = PaymentTransaction.objects.all()
    provider = request.query_params.get('provider')
    status_filter = request.query_params.get('status')
    student_id = request.query_params.get('student_id')
    if provider:
        qs = qs.filter(provider=provider)
    if status_filter:
        qs = qs.filter(status=status_filter)
    if student_id:
        qs = qs.filter(student_id=student_id)

    data = list(qs.values(
        'id', 'provider', 'reference', 'external_reference',
        'phone', 'amount', 'currency', 'status', 'description',
        'fee_invoice_id', 'student_id', 'failure_reason', 'created_at',
    ).order_by('-created_at')[:200])
    return Response({'results': data, 'count': len(data)})


from django.http import JsonResponse
from django.conf import settings
from django.shortcuts import redirect
from django.views.generic.base import TemplateView

from django.http import JsonResponse

import gopay
from gopay.enums import Recurrence, PaymentInstrument, BankSwiftCode, Currency, Language
from .models import Invoice


def payment_paypal(request):
    return render(request, "payments/paypal.html", context={})


def payment_stripe(request):
    return render(request, "payments/stripe.html", context={})


def payment_coinbase(request):
    return render(request, "payments/coinbase.html", context={})


def payment_paylike(request):
    return render(request, "payments/paylike.html", context={})


def payment_succeed(request):
    return render(request, "payments/payment_succeed.html", context={})


class PaymentGetwaysView(TemplateView):
    template_name = "payments/payment_gateways.html"

    def get_context_data(self, **kwargs):
        context = super(PaymentGetwaysView, self).get_context_data(**kwargs)
        context["key"] = settings.STRIPE_PUBLISHABLE_KEY
        context["amount"] = 500
        context["description"] = "Stripe Payment"
        context["invoice_session"] = self.request.session["invoice_session"]
        print(context["invoice_session"])
        return context


def stripe_charge(request):
    stripe.api_key = settings.STRIPE_SECRET_KEY

    if request.method == "POST":
        charge = stripe.Charge.create(
            amount=500,
            currency="eur",
            description="A Django charge",
            source=request.POST["stripeToken"],
        )
        invoice_code = request.session["invoice_session"]
        invoice = Invoice.objects.get(invoice_code=invoice_code)
        invoice.payment_complete = True
        invoice.save()
        return redirect("completed")
        # return JsonResponse({"invoice_code": invoice.invoice_code}, status=201)
        # return render(request, 'payments/charge.html')


def gopay_charge(request):
    if request.method == "POST":
        user = request.user

        payments = gopay.payments(
            {
                "goid": "[PAYMENT_ID]",
                "clientId": "[GOPAY_CLIENT_ID]",
                "clientSecret": "[GOPAY_CLIENT_SECRET]",
                "isProductionMode": False,
                "scope": gopay.TokenScope.ALL,
                "language": gopay.Language.ENGLISH,
                "timeout": 30,
            }
        )

        # recurrent payment must have field ''
        recurrentPayment = {
            "recurrence": {
                "recurrence_cycle": Recurrence.DAILY,
                "recurrence_period": "7",
                "recurrence_date_to": "2015-12-31",
            }
        }

        # pre-authorized payment must have field 'preauthorization'
        preauthorizedPayment = {"preauthorization": True}

        response = payments.create_payment(
            {
                "payer": {
                    "default_payment_instrument": PaymentInstrument.BANK_ACCOUNT,
                    "allowed_payment_instruments": [PaymentInstrument.BANK_ACCOUNT],
                    "default_swift": BankSwiftCode.FIO_BANKA,
                    "allowed_swifts": [BankSwiftCode.FIO_BANKA, BankSwiftCode.MBANK],
                    "contact": {
                        "first_name": user.first_name,
                        "last_name": user.last_name,
                        "email": user.email,
                        "phone_number": user.phone,
                        "city": "example city",
                        "street": "Plana 67",
                        "postal_code": "373 01",
                        "country_code": "CZE",
                    },
                },
                "amount": 150,
                "currency": Currency.CZECH_CROWNS,
                "order_number": "001",
                "order_description": "pojisteni01",
                "items": [
                    {"name": "item01", "amount": 50},
                    {"name": "item02", "amount": 100},
                ],
                "additional_params": [{"name": "invoicenumber", "value": "2015001003"}],
                "callback": {
                    "return_url": "http://www.your-url.tld/return",
                    "notification_url": "http://www.your-url.tld/notify",
                },
                "lang": Language.CZECH,  # if lang is not specified, then default lang is used
            }
        )

        if response.has_succeed():
            print("\nPayment Succeed\n")
            print("hooray, API returned " + str(response))
        else:
            print("\nPayment Fail\n")
            print(
                "oops, API returned " + str(response.status_code) + ": " + str(response)
            )
        return JsonResponse({"message": str(response)})

    return JsonResponse({"message": "GET requested"})


def paymentComplete(request):
    print(request.is_ajax())
    if request.is_ajax() or request.method == "POST":
        invoice_id = request.session["invoice_session"]
        invoice = Invoice.objects.get(id=invoice_id)
        invoice.payment_complete = True
        invoice.save()
        # return redirect('invoice', invoice.invoice_code)
    body = json.loads(request.body)
    print("BODY:", body)
    return JsonResponse("Payment completed!", safe=False)


def create_invoice(request):
    print(request.is_ajax())
    if request.method == "POST":
        invoice = Invoice.objects.create(
            user=request.user,
            amount=request.POST.get("amount"),
            total=26,
            invoice_code=str(uuid.uuid4()),
        )
        request.session["invoice_session"] = invoice.invoice_code
        return redirect("payment_gateways")
    # if request.is_ajax():
    #     invoice = Invoice.objects.create(
    #         user = request.user,
    #         amount = 15,
    #         total=26,
    #     )
    #     return JsonResponse({'invoice': invoice}, status=201) # created

    return render(
        request,
        "invoices.html",
        context={"invoices": Invoice.objects.filter(user=request.user)},
    )


def invoice_detail(request, slug):
    return render(
        request,
        "invoice_detail.html",
        context={"invoice": Invoice.objects.get(invoice_code=slug)},
    )
