from django.core.management.base import BaseCommand
from finance.models import Account, AccountType, AccountSubType
from django.db import transaction

class Command(BaseCommand):
    help = 'Seeds the default Chart of Accounts based on the specification'

    def handle(self, *args, **options):
        self.stdout.write('Seeding Chart of Accounts...')
        
        # Define the structure based on the prompt
        # ID-Range Type SubType
        # 1000–1999 → Assets
        # 2000–2999 → Liabilities
        # 3000–3999 → Equity
        # 4000–4999 → Income
        # 6000–6999 → Expenses (Skipping 5000 for CoS as per prompt optional/not listed explicitly in required subtypes)
        
        accounts_structure = [
            # ASSETS (1000-1999)
            {'code': '1000', 'name': 'Assets', 'type': AccountType.ASSET, 'sub_type': AccountSubType.CASH, 'parent': None}, # Root
            
            # Cash & Bank
            {'code': '1100', 'name': 'Cash on Hand', 'type': AccountType.ASSET, 'sub_type': AccountSubType.CASH, 'parent': '1000'},
            {'code': '1200', 'name': 'Bank Accounts', 'type': AccountType.ASSET, 'sub_type': AccountSubType.BANK, 'parent': '1000'},
            
            # Receivables
            {'code': '1300', 'name': 'Accounts Receivable', 'type': AccountType.ASSET, 'sub_type': AccountSubType.ACCOUNTS_RECEIVABLE, 'parent': '1000'},
            {'code': '1400', 'name': 'Prepayments', 'type': AccountType.ASSET, 'sub_type': AccountSubType.PREPAYMENTS, 'parent': '1000'},
            
            # Inventory
            {'code': '1500', 'name': 'Inventory', 'type': AccountType.ASSET, 'sub_type': AccountSubType.INVENTORY, 'parent': '1000'},
            
            # Fixed Assets
            {'code': '1600', 'name': 'Furniture & Equipment', 'type': AccountType.ASSET, 'sub_type': AccountSubType.FIXED_ASSET, 'parent': '1000'},
            {'code': '1700', 'name': 'Accumulated Depreciation', 'type': AccountType.ASSET, 'sub_type': AccountSubType.ACCUMULATED_DEPRECIATION, 'parent': '1000'},

            # LIABILITIES (2000–2999)
            {'code': '2000', 'name': 'Liabilities', 'type': AccountType.LIABILITY, 'sub_type': AccountSubType.ACCOUNTS_PAYABLE, 'parent': None},
            
            {'code': '2100', 'name': 'Accounts Payable', 'type': AccountType.LIABILITY, 'sub_type': AccountSubType.ACCOUNTS_PAYABLE, 'parent': '2000'},
            {'code': '2200', 'name': 'Accrued Expenses', 'type': AccountType.LIABILITY, 'sub_type': AccountSubType.ACCRUED_EXPENSES, 'parent': '2000'},
            {'code': '2300', 'name': 'Deferred Revenue', 'type': AccountType.LIABILITY, 'sub_type': AccountSubType.DEFERRED_REVENUE, 'parent': '2000'},
            {'code': '2400', 'name': 'Tax Payable', 'type': AccountType.LIABILITY, 'sub_type': AccountSubType.TAX_PAYABLE, 'parent': '2000'},
            {'code': '2500', 'name': 'Long Term Loans', 'type': AccountType.LIABILITY, 'sub_type': AccountSubType.LONG_TERM_LIABILITY, 'parent': '2000'},

            # EQUITY (3000–3999)
            {'code': '3000', 'name': 'Equity', 'type': AccountType.EQUITY, 'sub_type': AccountSubType.CAPITAL, 'parent': None},
            
            {'code': '3100', 'name': 'Share Capital', 'type': AccountType.EQUITY, 'sub_type': AccountSubType.CAPITAL, 'parent': '3000'},
            {'code': '3200', 'name': 'Retained Earnings', 'type': AccountType.EQUITY, 'sub_type': AccountSubType.RETAINED_EARNINGS, 'parent': '3000'},
            {'code': '3300', 'name': 'Current Year Surplus', 'type': AccountType.EQUITY, 'sub_type': AccountSubType.CURRENT_YEAR_SURPLUS, 'parent': '3000'},

            # INCOME (4000-4999)
            {'code': '4000', 'name': 'Income', 'type': AccountType.INCOME, 'sub_type': AccountSubType.SERVICE_INCOME, 'parent': None},
            
            {'code': '4100', 'name': 'Tuition Fees', 'type': AccountType.INCOME, 'sub_type': AccountSubType.SERVICE_INCOME, 'parent': '4000'},
            {'code': '4200', 'name': 'Service Revenue', 'type': AccountType.INCOME, 'sub_type': AccountSubType.SERVICE_INCOME, 'parent': '4000'},
            {'code': '4300', 'name': 'Grants & Donations', 'type': AccountType.INCOME, 'sub_type': AccountSubType.GRANTS_DONATIONS, 'parent': '4000'},
            {'code': '4900', 'name': 'Other Income', 'type': AccountType.INCOME, 'sub_type': AccountSubType.OTHER_INCOME, 'parent': '4000'},

            # EXPENSES (6000-6999)
            {'code': '6000', 'name': 'Expenses', 'type': AccountType.EXPENSE, 'sub_type': AccountSubType.ADMIN_EXPENSES, 'parent': None},
            
            {'code': '6100', 'name': 'Salaries & Wages', 'type': AccountType.EXPENSE, 'sub_type': AccountSubType.SALARIES_WAGES, 'parent': '6000'},
            {'code': '6200', 'name': 'Utilities', 'type': AccountType.EXPENSE, 'sub_type': AccountSubType.UTILITIES, 'parent': '6000'},
            {'code': '6300', 'name': 'Teaching Supplies', 'type': AccountType.EXPENSE, 'sub_type': AccountSubType.TEACHING_EXPENSES, 'parent': '6000'},
            {'code': '6400', 'name': 'Administrative Expenses', 'type': AccountType.EXPENSE, 'sub_type': AccountSubType.ADMIN_EXPENSES, 'parent': '6000'},
            {'code': '6500', 'name': 'Repairs & Maintenance', 'type': AccountType.EXPENSE, 'sub_type': AccountSubType.MAINTENANCE, 'parent': '6000'},
            {'code': '6600', 'name': 'Depreciation Expense', 'type': AccountType.EXPENSE, 'sub_type': AccountSubType.DEPRECIATION, 'parent': '6000'},
        ]

        with transaction.atomic():
            for acc_data in accounts_structure:
                parent_code = acc_data.pop('parent')
                parent = None
                if parent_code:
                    try:
                        parent = Account.objects.get(code=parent_code)
                    except Account.DoesNotExist:
                        self.stderr.write(self.style.ERROR(f"Parent {parent_code} not found for {acc_data['code']}"))
                        continue
                
                Account.objects.update_or_create(
                    code=acc_data['code'],
                    defaults={
                        'name': acc_data['name'],
                        'type': acc_data['type'],
                        'sub_type': acc_data['sub_type'],
                        'parent': parent
                    }
                )
                self.stdout.write(self.style.SUCCESS(f"Processed account {acc_data['code']} - {acc_data['name']}"))
        
        self.stdout.write(self.style.SUCCESS('Successfully seeded Chart of Accounts'))
