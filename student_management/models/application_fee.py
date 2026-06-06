from django.db import models
from django.conf import settings
from student_settings.models import BaseModel


class ApplicationFeePayment(BaseModel):
    """
    Tracks payment of the application/registration fee.
    Created automatically when an Application is submitted and
    AdmissionWorkflowConfig.require_application_fee=True.
    """

    STATUS_CHOICES = [
        ('pending', 'Pending Payment'),
        ('paid', 'Paid'),
        ('waived', 'Waived'),
        ('refunded', 'Refunded'),
    ]

    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('mpesa', 'M-Pesa'),
        ('bank_transfer', 'Bank Transfer'),
        ('cheque', 'Cheque'),
        ('card', 'Card'),
        ('other', 'Other'),
    ]

    # ── Core Link ───────────────────────────────────────────────────────────────
    application = models.OneToOneField(
        'student_management.Application',
        on_delete=models.CASCADE,
        related_name='fee_payment',
        help_text='The application this fee is associated with'
    )

    # ── Fee Details ─────────────────────────────────────────────────────────────
    amount = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text='Amount charged (copied from AdmissionWorkflowConfig at creation time)'
    )
    currency = models.CharField(max_length=10, default='KES')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # ── Payment Info ────────────────────────────────────────────────────────────
    payment_method = models.CharField(
        max_length=20, choices=PAYMENT_METHOD_CHOICES,
        null=True, blank=True
    )
    payment_date = models.DateField(null=True, blank=True)
    payment_reference = models.CharField(
        max_length=100, blank=True, null=True,
        help_text='M-Pesa code, bank slip number, cheque number, etc.'
    )
    receipt_number = models.CharField(
        max_length=100, blank=True, null=True,
        help_text='Internal receipt number issued by the school'
    )

    # ── Waiver ──────────────────────────────────────────────────────────────────
    waiver_reason = models.TextField(
        blank=True, null=True,
        help_text='Required if status=waived — explain why the fee was waived'
    )

    # ── Staff ───────────────────────────────────────────────────────────────────
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='fee_payments_recorded',
        help_text='Staff member who recorded this payment'
    )

    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'application_fee_payments'
        ordering = ['-created_at']
        verbose_name = 'Application Fee Payment'

    def __str__(self):
        return (
            f"Fee for {self.application} — "
            f"{self.currency} {self.amount} [{self.get_status_display()}]"
        )

    @property
    def is_cleared(self):
        """True when payment can no longer block progression."""
        return self.status in ('paid', 'waived')
