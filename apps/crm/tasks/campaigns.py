import logging
# pyrefly: ignore [missing-import]
from django_q.tasks import async_task
from django.db import transaction
from django.db.models import Prefetch

from ..models.campaign import Campaign, CampaignRecipient
from ..models.parent import ParentGuardian
from ..models.relationship import ParentStudentRelationship

logger = logging.getLogger(__name__)

def process_campaign_audience(campaign_id, schema_name):
    # Set the tenant schema context if django-tenants is active
    try:
        from django.db import connection
        connection.set_schema(schema_name)
    except Exception:
        pass
        
    try:
        campaign = Campaign.objects.get(id=campaign_id)
        if campaign.status != 'PROCESSING':
            return
            
        # Audience Resolution:
        relationships = ParentStudentRelationship.objects.select_related('parent', 'student').filter(
            parent__status='active'
        )
        
        # Avoid duplicating parents
        parent_contexts = {}
        for rel in relationships:
            parent = rel.parent
            if parent.id not in parent_contexts:
                phone = parent.whatsapp_number if campaign.channel == 'WHATSAPP' else parent.phone
                if not phone:
                    continue # Skip if missing phone
                
                parent_contexts[parent.id] = {
                    'parent_obj': parent,
                    'phone': phone,
                    'students': []
                }
            
            parent_contexts[parent.id]['students'].append(f"{rel.student.student.first_name} {rel.student.student.last_name}")

        recipients_to_create = []
        for pid, data in parent_contexts.items():
            context_data = {
                'first_name': data['parent_obj'].first_name,
                'last_name': data['parent_obj'].last_name,
                'students_names': ", ".join(data['students'])
            }
            
            recipients_to_create.append(
                CampaignRecipient(
                    campaign=campaign,
                    parent=data['parent_obj'],
                    target_phone=data['phone'],
                    context_data=context_data,
                    status='PENDING'
                )
            )
            
        with transaction.atomic():
            CampaignRecipient.objects.bulk_create(recipients_to_create)
            campaign.total_recipients = len(recipients_to_create)
            campaign.status = 'SCHEDULED'
            campaign.save()
            
        # Trigger sending
        async_task('crm.tasks.sending.dispatch_campaign_messages', campaign.id, schema_name)
        
    except Exception as e:
        logger.error(f"Failed to process campaign {campaign_id}: {str(e)}")
