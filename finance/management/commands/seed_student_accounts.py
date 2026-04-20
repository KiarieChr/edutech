from django.core.management.base import BaseCommand
from finance.models import Account, AccountType, AccountSubType
from django.db import transaction


class Command(BaseCommand):
    help = 'Seeds student-related accounts (fee income vote heads, student receivables, prepayments)'

    def handle(self, *args, **options):
        self.stdout.write('Seeding student-related accounts...')

        # Student fee income accounts (sub-accounts under 4100 Tuition Fees)
        student_accounts = [
            # ── INCOME: Fee Vote Heads (4100 sub-accounts) ──
            {'code': '4101', 'name': 'Tuition Fee', 'type': AccountType.INCOME, 'sub_type': AccountSubType.SERVICE_INCOME, 'parent': '4100', 'is_student_related': True},
            {'code': '4102', 'name': 'Boarding Fee', 'type': AccountType.INCOME, 'sub_type': AccountSubType.SERVICE_INCOME, 'parent': '4100', 'is_student_related': True},
            {'code': '4103', 'name': 'Transport Fee', 'type': AccountType.INCOME, 'sub_type': AccountSubType.SERVICE_INCOME, 'parent': '4100', 'is_student_related': True},
            {'code': '4104', 'name': 'Activity Fee', 'type': AccountType.INCOME, 'sub_type': AccountSubType.SERVICE_INCOME, 'parent': '4100', 'is_student_related': True},
            {'code': '4105', 'name': 'Laboratory Fee', 'type': AccountType.INCOME, 'sub_type': AccountSubType.SERVICE_INCOME, 'parent': '4100', 'is_student_related': True},
            {'code': '4106', 'name': 'Library Fee', 'type': AccountType.INCOME, 'sub_type': AccountSubType.SERVICE_INCOME, 'parent': '4100', 'is_student_related': True},
            {'code': '4107', 'name': 'Computer Lab Fee', 'type': AccountType.INCOME, 'sub_type': AccountSubType.SERVICE_INCOME, 'parent': '4100', 'is_student_related': True},
            {'code': '4108', 'name': 'Examination Fee', 'type': AccountType.INCOME, 'sub_type': AccountSubType.SERVICE_INCOME, 'parent': '4100', 'is_student_related': True},
            {'code': '4109', 'name': 'Registration Fee', 'type': AccountType.INCOME, 'sub_type': AccountSubType.SERVICE_INCOME, 'parent': '4100', 'is_student_related': True},
            {'code': '4110', 'name': 'Admission Fee', 'type': AccountType.INCOME, 'sub_type': AccountSubType.SERVICE_INCOME, 'parent': '4100', 'is_student_related': True},
            {'code': '4111', 'name': 'Uniform Fee', 'type': AccountType.INCOME, 'sub_type': AccountSubType.SERVICE_INCOME, 'parent': '4100', 'is_student_related': True},
            {'code': '4112', 'name': 'Medical Fee', 'type': AccountType.INCOME, 'sub_type': AccountSubType.SERVICE_INCOME, 'parent': '4100', 'is_student_related': True},
            {'code': '4113', 'name': 'Sports Fee', 'type': AccountType.INCOME, 'sub_type': AccountSubType.SERVICE_INCOME, 'parent': '4100', 'is_student_related': True},
            {'code': '4114', 'name': 'Caution Money', 'type': AccountType.INCOME, 'sub_type': AccountSubType.SERVICE_INCOME, 'parent': '4100', 'is_student_related': True},
            {'code': '4115', 'name': 'Lunch / Meals Fee', 'type': AccountType.INCOME, 'sub_type': AccountSubType.SERVICE_INCOME, 'parent': '4100', 'is_student_related': True},
            {'code': '4116', 'name': 'Development Levy', 'type': AccountType.INCOME, 'sub_type': AccountSubType.SERVICE_INCOME, 'parent': '4100', 'is_student_related': True},
            {'code': '4117', 'name': 'Stationery Fee', 'type': AccountType.INCOME, 'sub_type': AccountSubType.SERVICE_INCOME, 'parent': '4100', 'is_student_related': True},
            {'code': '4118', 'name': 'Club & Societies Fee', 'type': AccountType.INCOME, 'sub_type': AccountSubType.SERVICE_INCOME, 'parent': '4100', 'is_student_related': True},
            {'code': '4119', 'name': 'Graduation Fee', 'type': AccountType.INCOME, 'sub_type': AccountSubType.SERVICE_INCOME, 'parent': '4100', 'is_student_related': True},
            {'code': '4120', 'name': 'Insurance Fee', 'type': AccountType.INCOME, 'sub_type': AccountSubType.SERVICE_INCOME, 'parent': '4100', 'is_student_related': True},

            # ── ASSET: Student Receivables (sub-account under 1300 Accounts Receivable) ──
            {'code': '1310', 'name': 'Student Fee Receivables', 'type': AccountType.ASSET, 'sub_type': AccountSubType.ACCOUNTS_RECEIVABLE, 'parent': '1300', 'is_student_related': True},
            {'code': '1320', 'name': 'Sundry Student Debtors', 'type': AccountType.ASSET, 'sub_type': AccountSubType.ACCOUNTS_RECEIVABLE, 'parent': '1300', 'is_student_related': True},

            # ── LIABILITY: Student Prepayments / Deposits (sub-accounts under 2300 Deferred Revenue) ──
            {'code': '2310', 'name': 'Student Prepaid Fees', 'type': AccountType.LIABILITY, 'sub_type': AccountSubType.DEFERRED_REVENUE, 'parent': '2300', 'is_student_related': True},
            {'code': '2320', 'name': 'Student Caution Deposits', 'type': AccountType.LIABILITY, 'sub_type': AccountSubType.REFUNDABLE_DEPOSIT, 'parent': '2300', 'is_student_related': True},
            {'code': '2330', 'name': 'Student Overpayments', 'type': AccountType.LIABILITY, 'sub_type': AccountSubType.DEFERRED_REVENUE, 'parent': '2300', 'is_student_related': True},
        ]

        # Also mark the parent account 4100 as student-related
        parent_accounts_to_mark = ['4100', '1300', '2300']

        with transaction.atomic():
            # Mark parent accounts as student-related
            for code in parent_accounts_to_mark:
                try:
                    acc = Account.objects.get(code=code)
                    if not acc.is_student_related:
                        acc.is_student_related = True
                        acc.save()
                        self.stdout.write(self.style.WARNING(f"Marked {code} - {acc.name} as student-related"))
                except Account.DoesNotExist:
                    self.stderr.write(self.style.ERROR(
                        f"Parent account {code} not found. Run 'seed_coa' first."
                    ))
                    return

            # Create student-related sub-accounts
            for acc_data in student_accounts:
                parent_code = acc_data.pop('parent')
                is_student_related = acc_data.pop('is_student_related')

                try:
                    parent = Account.objects.get(code=parent_code)
                except Account.DoesNotExist:
                    self.stderr.write(self.style.ERROR(
                        f"Parent {parent_code} not found for {acc_data['code']}. Run 'seed_coa' first."
                    ))
                    continue

                Account.objects.update_or_create(
                    code=acc_data['code'],
                    defaults={
                        'name': acc_data['name'],
                        'type': acc_data['type'],
                        'sub_type': acc_data['sub_type'],
                        'parent': parent,
                        'is_student_related': is_student_related,
                    }
                )
                self.stdout.write(self.style.SUCCESS(
                    f"  ✓ {acc_data['code']} - {acc_data['name']}"
                ))

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Successfully seeded {len(student_accounts)} student-related accounts'
        ))
        self.stdout.write(self.style.NOTICE(
            'These accounts are now available as fee vote heads in Fee Structures.'
        ))
