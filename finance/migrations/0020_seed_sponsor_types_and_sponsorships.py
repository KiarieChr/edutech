from django.db import migrations

def seed_sponsorship_data(apps, schema_editor):
    Account = apps.get_model('finance', 'Account')
    SponsorType = apps.get_model('finance', 'SponsorType')
    Sponsorship = apps.get_model('finance', 'Sponsorship')

    # Ensure parent account 2300 exists
    try:
        parent_account = Account.objects.get(code='2300')
    except Account.DoesNotExist:
        # If it doesn't exist, we find any liability or let it be None
        parent_account = Account.objects.filter(type='LIABILITY', parent=None).first()

    # Define GL accounts to create
    clearing_accounts_data = [
        {
            'code': '2341',
            'name': 'Government Scholarships Clearing',
            'type': 'LIABILITY',
            'sub_type': 'DEFERRED_REVENUE',
            'parent': parent_account,
            'is_student_related': True
        },
        {
            'code': '2342',
            'name': 'NGO Scholarships Clearing',
            'type': 'LIABILITY',
            'sub_type': 'DEFERRED_REVENUE',
            'parent': parent_account,
            'is_student_related': True
        },
        {
            'code': '2343',
            'name': 'CDF Bursaries Clearing',
            'type': 'LIABILITY',
            'sub_type': 'DEFERRED_REVENUE',
            'parent': parent_account,
            'is_student_related': True
        },
        {
            'code': '2344',
            'name': 'County Bursaries Clearing',
            'type': 'LIABILITY',
            'sub_type': 'DEFERRED_REVENUE',
            'parent': parent_account,
            'is_student_related': True
        }
    ]

    accounts_map = {}
    for acc_data in clearing_accounts_data:
        account, created = Account.objects.get_or_create(
            code=acc_data['code'],
            defaults={
                'name': acc_data['name'],
                'type': acc_data['type'],
                'sub_type': acc_data['sub_type'],
                'parent': acc_data['parent'],
                'is_student_related': acc_data['is_student_related']
            }
        )
        accounts_map[acc_data['code']] = account

    # Define Sponsor Types to create
    sponsor_types_data = [
        {
            'name': 'Government Scholarships',
            'clearing_account_code': '2341',
            'description': 'Scholarships funded by government bodies or agencies.'
        },
        {
            'name': 'NGO Scholarships',
            'clearing_account_code': '2342',
            'description': 'Scholarships offered by Non-Governmental Organizations and Foundations.'
        },
        {
            'name': 'CDF Bursaries',
            'clearing_account_code': '2343',
            'description': 'Bursaries funded from the Constituency Development Fund.'
        },
        {
            'name': 'County Bursaries',
            'clearing_account_code': '2344',
            'description': 'Bursary programs managed by County Governments.'
        }
    ]

    sponsor_types_map = {}
    for st_data in sponsor_types_data:
        clearing_acc = accounts_map.get(st_data['clearing_account_code'])
        st_obj, created = SponsorType.objects.get_or_create(
            name=st_data['name'],
            defaults={
                'clearing_account': clearing_acc,
                'description': st_data['description']
            }
        )
        sponsor_types_map[st_data['name']] = st_obj

    # Define default Sponsorship programs
    sponsorships_data = [
        {
            'name': 'Equity Group Foundation Wings to Fly',
            'sponsor_type_name': 'NGO Scholarships',
            'code': 'WTF-EQ',
            'description': 'Wings to Fly secondary school scholarship program by Equity Group Foundation.'
        },
        {
            'name': 'Elimu Scholarship Program',
            'sponsor_type_name': 'NGO Scholarships',
            'code': 'ELIMU-NGO',
            'description': 'Elimu Scholarship Program for needy children.'
        },
        {
            'name': 'CDF Kabete Constituency',
            'sponsor_type_name': 'CDF Bursaries',
            'code': 'CDF-KBT',
            'description': 'Bursary funding from Kabete Constituency Development Fund.'
        },
        {
            'name': 'County Government Bursary Fund',
            'sponsor_type_name': 'County Bursaries',
            'code': 'COUNTY-BUR',
            'description': 'General county-level educational bursary allocation.'
        },
        {
            'name': 'Higher Education Loans Board (HELB) Scholarship',
            'sponsor_type_name': 'Government Scholarships',
            'code': 'HELB-SCH',
            'description': 'HELB government sponsorship program.'
        }
    ]

    for s_data in sponsorships_data:
        st_obj = sponsor_types_map.get(s_data['sponsor_type_name'])
        if st_obj:
            Sponsorship.objects.get_or_create(
                name=s_data['name'],
                defaults={
                    'sponsor_type': st_obj,
                    'code': s_data['code'],
                    'address': s_data['description']
                }
            )

def reverse_sponsorship_data(apps, schema_editor):
    Sponsorship = apps.get_model('finance', 'Sponsorship')
    SponsorType = apps.get_model('finance', 'SponsorType')
    Account = apps.get_model('finance', 'Account')

    Sponsorship.objects.all().delete()
    SponsorType.objects.all().delete()
    Account.objects.filter(code__in=['2341', '2342', '2343', '2344']).delete()

class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0019_sponsorship_receipt_parent_receipt_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_sponsorship_data, reverse_sponsorship_data),
    ]
