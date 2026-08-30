import logging
from .services import BillingAutomationService

logger = logging.getLogger(__name__)

def run_monthly_billing_task(schema_name):
    """
    Django-Q task to generate monthly billing for a tenant.
    Usually scheduled to run on the 1st of every month.
    """
    try:
        from django.db import connection
        connection.set_schema(schema_name)
    except Exception:
        pass
        
    try:
        invoice = BillingAutomationService.run_monthly_billing()
        if invoice:
            logger.info(f"Successfully generated billing invoice {invoice.invoice_number} for {schema_name}")
        else:
            logger.info(f"No billing required or already generated for {schema_name}")
    except Exception as e:
        logger.error(f"Failed to generate billing for {schema_name}: {str(e)}")
