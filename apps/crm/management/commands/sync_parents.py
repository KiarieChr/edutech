from django.core.management.base import BaseCommand
from django.db import connection, transaction
from tenants.models import Client
from student_management.models.profiles import Parent as StudentParent, Student
from crm.models.parent import ParentGuardian
from crm.models.relationship import ParentStudentRelationship
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Synchronizes existing student_management Parents into the CRM ParentGuardian model'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Starting sync_parents...'))
        tenants = Client.objects.exclude(schema_name='public')
        self.stdout.write(self.style.NOTICE(f'Found {tenants.count()} tenants'))
        
        for tenant in tenants:
            connection.set_schema(tenant.schema_name)
            self.stdout.write(self.style.NOTICE(f'Syncing parents for tenant: {tenant.name}'))
            
            with transaction.atomic():
                parents = StudentParent.objects.all()
                count_created = 0
                count_updated = 0
                
                for sp in parents:
                    # Phone normalization
                    phone = sp.phone
                    if not phone:
                        continue
                        
                    # Clean phone number (strip whitespace, ensure +)
                    phone = phone.strip()
                    if not phone.startswith('+'):
                        phone = '+' + phone
                        
                    # Get or Create CRM Parent
                    crm_parent, created = ParentGuardian.objects.get_or_create(
                        phone=phone,
                        defaults={
                            'user': sp.user,
                            'first_name': sp.first_name,
                            'last_name': sp.last_name,
                            'email': sp.email,
                            'whatsapp_number': phone, # Assuming same for now
                        }
                    )
                    
                    if created:
                        count_created += 1
                    else:
                        # Update missing fields if needed
                        updated = False
                        if not crm_parent.whatsapp_number:
                            crm_parent.whatsapp_number = phone
                            updated = True
                        if not crm_parent.user and sp.user:
                            crm_parent.user = sp.user
                            updated = True
                        if updated:
                            crm_parent.save()
                            count_updated += 1
                            
                    # Link to Student
                    if sp.student:
                        # We need the relationship mapping
                        # Default to Mother/Father based on relation_ship
                        relation_type = 'guardian'
                        if sp.relation_ship:
                            r = sp.relation_ship.lower()
                            if 'mother' in r:
                                relation_type = 'mother'
                            elif 'father' in r:
                                relation_type = 'father'
                                
                        ParentStudentRelationship.objects.get_or_create(
                            parent=crm_parent,
                            student=sp.student,
                            defaults={
                                'relationship_type': relation_type,
                                'is_primary': True
                            }
                        )
                        
            self.stdout.write(self.style.SUCCESS(f'Successfully synced {count_created} new parents, updated {count_updated} for {tenant.name}'))
