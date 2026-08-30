import datetime
from decimal import Decimal
from django.utils import timezone
from django.db import transaction

from core.models import SystemSubscription, SMSPricingBand, BillingCycle
from payments.models import SMSLog
from intelligence.models import IntelligenceUsage
from payables.models import Supplier, SupplierInvoice, SupplierInvoiceLine
from finance.models import Account

class BillingAutomationService:
    SUPPLIER_NAME = "Royal Software Solutions (R.S.S Limited)"
    
    @classmethod
    def run_monthly_billing(cls, target_date=None):
        """
        Runs the billing process for the previous month.
        target_date defaults to today. It will bill for (target_date - 1 month).
        """
        if not target_date:
            target_date = timezone.now().date()
            
        # Determine the billing month (first day of previous month)
        first_day_of_current = target_date.replace(day=1)
        last_day_of_prev = first_day_of_current - datetime.timedelta(days=1)
        billing_month = last_day_of_prev.replace(day=1)
        
        # Check if already billed
        cycle, created = BillingCycle.objects.get_or_create(month=billing_month)
        if cycle.invoice_generated:
            return cycle.invoice
            
        with transaction.atomic():
            invoice = cls._generate_invoice(billing_month)
            if invoice:
                cycle.invoice_generated = True
                cycle.generated_at = timezone.now()
                cycle.invoice = invoice
                cycle.save()
            return invoice

    @classmethod
    def _generate_invoice(cls, billing_month):
        # 1. Get or Create Supplier
        supplier, _ = Supplier.objects.get_or_create(
            name=cls.SUPPLIER_NAME,
            defaults={'payment_terms': 'NET_30'}
        )
        
        # 2. Get Subscription
        subscription = SystemSubscription.get_instance()
        
        # Determine expense account
        expense_account = Account.objects.filter(
            type='EXPENSE', 
            name__icontains='Software'
        ).first()
        
        if not expense_account:
            expense_account = Account.objects.filter(type='EXPENSE').first()
            
        if not expense_account:
            # Cannot proceed without an expense account
            return None

        # 3. Calculate Components
        base_fee = subscription.monthly_fee
        
        # Count SMS sent in that month
        next_month = (billing_month.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
        sms_count = SMSLog.objects.filter(
            created_at__gte=billing_month,
            created_at__lt=next_month,
            status__in=['sent', 'delivered']
        ).count()
        
        sms_cost = Decimal('0.00')
        if sms_count > 0:
            band = SMSPricingBand.objects.filter(max_sms__gte=sms_count).order_by('max_sms').first()
            if band:
                sms_cost = band.fixed_price
            else:
                highest_band = SMSPricingBand.objects.order_by('-max_sms').first()
                if highest_band:
                    sms_cost = highest_band.fixed_price
                else:
                    sms_cost = Decimal('1.00') * sms_count
        
        # AI Usage
        ai_usage = IntelligenceUsage.objects.filter(
            month__year=billing_month.year,
            month__month=billing_month.month
        ).first()
        
        ai_cost = Decimal('0.00')
        if ai_usage:
            raw_ai_cost = ai_usage.cost_approx
            markup = raw_ai_cost * (subscription.ai_markup_percentage / Decimal('100.0'))
            ai_cost = raw_ai_cost + markup

        if base_fee == 0 and sms_cost == 0 and ai_cost == 0:
            return None

        # 4. Create Invoice
        # Generate a unique invoice number
        invoice_number = f"SYS-{billing_month.strftime('%Y%m')}"
        
        # If invoice number already exists, maybe append a timestamp
        if SupplierInvoice.objects.filter(supplier=supplier, invoice_number=invoice_number).exists():
            invoice_number = f"{invoice_number}-{timezone.now().strftime('%H%M%S')}"
        
        invoice = SupplierInvoice.objects.create(
            supplier=supplier,
            source='MANUAL',
            invoice_number=invoice_number,
            invoice_date=timezone.now().date(),
            due_date=timezone.now().date() + datetime.timedelta(days=30),
            status='DRAFT',
            notes=f"System Usage Billing for {billing_month.strftime('%B %Y')}"
        )
        
        # Add Lines
        if base_fee > 0:
            SupplierInvoiceLine.objects.create(
                invoice=invoice,
                description=f"Base Package: {subscription.package_name}",
                quantity=1,
                unit_price=base_fee,
                gl_account=expense_account,
                vat_rate=Decimal('16.00')
            )
            
        if sms_cost > 0:
            SupplierInvoiceLine.objects.create(
                invoice=invoice,
                description=f"SMS Usage ({sms_count} messages)",
                quantity=1,
                unit_price=sms_cost,
                gl_account=expense_account,
                vat_rate=Decimal('16.00')
            )
            
        if ai_cost > 0:
            SupplierInvoiceLine.objects.create(
                invoice=invoice,
                description=f"AI Intelligence Usage",
                quantity=1,
                unit_price=ai_cost,
                gl_account=expense_account,
                vat_rate=Decimal('16.00')
            )
            
        invoice.update_totals()
        return invoice
