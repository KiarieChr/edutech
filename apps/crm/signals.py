from django.db.models.signals import post_save
from django.dispatch import receiver
from student_management.models.profiles import Parent as StudentParent
from crm.models.parent import ParentGuardian
from crm.models.relationship import ParentStudentRelationship
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=StudentParent)
def sync_parent_to_crm(sender, instance, created, **kwargs):
    """
    When a Parent is created or updated in student_management,
    sync it to the CRM ParentGuardian.
    """
    phone = instance.phone
    if not phone:
        return
        
    phone = phone.strip()
    if not phone.startswith('+'):
        phone = '+' + phone
        
    crm_parent, crm_created = ParentGuardian.objects.get_or_create(
        phone=phone,
        defaults={
            'user': instance.user,
            'first_name': instance.first_name,
            'last_name': instance.last_name,
            'email': instance.email,
            'whatsapp_number': phone,
        }
    )
    
    if not crm_created:
        crm_parent.first_name = instance.first_name
        crm_parent.last_name = instance.last_name
        crm_parent.email = instance.email
        if instance.user and not crm_parent.user:
            crm_parent.user = instance.user
        crm_parent.save()
        
    if instance.student:
        relation_type = 'guardian'
        if instance.relation_ship:
            r = instance.relation_ship.lower()
            if 'mother' in r:
                relation_type = 'mother'
            elif 'father' in r:
                relation_type = 'father'
                
        ParentStudentRelationship.objects.get_or_create(
            parent=crm_parent,
            student=instance.student,
            defaults={
                'relationship_type': relation_type
            }
        )
