from django.db.models.signals import post_save
from django.dispatch import receiver
from student_management.models.class_session import StudentPlacement
from finance.models import FinanceSettings
from .services import BillingService
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=StudentPlacement)
def trigger_auto_billing(sender, instance, created, **kwargs):
    """
    Triggers auto-billing when a student reports (ClassSession created/updated with status='active' and type='reporting').
    
    DISABLED FOR NOW: Strict "Configuration Only" requirement.
    Future: This will be re-enabled or moved to a dedicated Billing Module.
    """
    pass
    # if instance.session_type == 'reporting' and instance.session_status == 'active':
    #     # Check settings
    #     try:
    #         settings = FinanceSettings.load()
    #         if settings.auto_billing_enabled:
    #             BillingService.generate_invoice_for_student(instance.student, instance)
    #     except Exception as e:
    #         logger.error(f"Error in auto-billing for {instance}: {e}")
