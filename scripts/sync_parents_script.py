from django.db import connection, transaction
from tenants.models import Client
from student_management.models.profiles import Parent as StudentParent
from crm.models.parent import ParentGuardian
from crm.models.relationship import ParentStudentRelationship

tenants = Client.objects.exclude(schema_name='public')
for tenant in tenants:
    connection.set_schema(tenant.schema_name)
    print(f'Syncing parents for tenant: {tenant.name}')
    with transaction.atomic():
        parents = StudentParent.objects.all()
        count_created = 0
        count_updated = 0
        for sp in parents:
            phone = sp.phone
            if not phone:
                continue
            phone = phone.strip()
            if not phone.startswith('+'):
                phone = '+' + phone
                
            crm_parent, created = ParentGuardian.objects.get_or_create(
                phone=phone,
                defaults={
                    'user': sp.user,
                    'first_name': sp.first_name,
                    'last_name': sp.last_name,
                    'email': sp.email,
                    'whatsapp_number': phone,
                }
            )
            if created:
                count_created += 1
            else:
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
                    
            if sp.student:
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
                    defaults={'relationship_type': relation_type}
                )
        print(f'Successfully synced {count_created} new parents, updated {count_updated} for {tenant.name}')
