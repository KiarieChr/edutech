"""
Fix payroll GL account setup:
1. Create missing GL accounts
2. Fix PayrollAccount GL assignments  
3. Create new PayrollAccounts for SHIF, Housing Levy, PAYE
4. Link StatutoryRates to PayrollAccounts
5. Create GLAccountMappings
"""
import os, sys, django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from finance.models import Account
from workforce.models import PayrollAccount, StatutoryRate, GLAccountMapping

# ── Step 1: Create missing GL accounts ──────────────────────────────
print("=== Step 1: Creating missing GL accounts ===")

liability_parent = Account.objects.filter(code='2000').first()
expense_parent = Account.objects.filter(code='6100').first()

accounts_to_create = [
    ('2606', 'SHIF Liability', 'LIABILITY', 'CURRENT_LIABILITY', liability_parent),
    ('2607', 'Housing Levy Liability', 'LIABILITY', 'CURRENT_LIABILITY', liability_parent),
    ('6102', 'House Allowance Expense', 'EXPENSE', 'OPERATING', expense_parent),
    ('6103', 'Commute Allowance Expense', 'EXPENSE', 'OPERATING', expense_parent),
    ('6104', 'NSSF Employer Expense', 'EXPENSE', 'OPERATING', expense_parent),
    ('6105', 'Housing Levy Employer Expense', 'EXPENSE', 'OPERATING', expense_parent),
]

for code, name, acct_type, sub_type, parent in accounts_to_create:
    obj, created = Account.objects.get_or_create(
        code=code,
        defaults={
            'name': name,
            'type': acct_type,
            'sub_type': sub_type,
            'parent': parent,
            'is_active': True,
            'available_in_payroll': True,
        }
    )
    status = 'Created' if created else 'Exists'
    print(f"  {status}: {code} - {name}")


# ── Step 2: Fix existing PayrollAccount GL assignments ──────────────
print("\n=== Step 2: Fixing PayrollAccount GL assignments ===")

# House Allowance earning should debit expense 6102, not liability 2602
ha_pa = PayrollAccount.objects.filter(name='HOUSE ALLOWANCE', account_type='earning').first()
if ha_pa:
    ha_expense = Account.objects.get(code='6102')
    ha_liability = Account.objects.get(code='2602')
    ha_pa.employee_gl_account = ha_expense  # Expense for debit (earning = expense)
    ha_pa.employer_gl_account = None
    ha_pa.save()
    print(f"  Fixed HOUSE ALLOWANCE: ee_gl=6102 (expense)")

# Commute Allowance earning should debit expense 6103
ca_pa = PayrollAccount.objects.filter(name='COMMUTE ALLOWANCE', account_type='earning').first()
if ca_pa:
    ca_expense = Account.objects.get(code='6103')
    ca_pa.employee_gl_account = ca_expense
    ca_pa.employer_gl_account = None
    ca_pa.save()
    print(f"  Fixed COMMUTE ALLOWANCE: ee_gl=6103 (expense)")

# Basic Salary is already correct: ee_gl=6101 (expense)
bs_pa = PayrollAccount.objects.filter(name='BASIC SALARY', account_type='earning').first()
if bs_pa:
    print(f"  Basic Salary OK: ee_gl={bs_pa.employee_gl_account.code if bs_pa.employee_gl_account else 'None'}")

# NSSF deduction: ee_gl should be liability 2605, er_gl should be expense 6104
nssf_pa = PayrollAccount.objects.filter(name='NSSF', account_type='deduction').first()
if nssf_pa:
    nssf_liability = Account.objects.get(code='2605')
    nssf_expense = Account.objects.get(code='6104')
    nssf_pa.employee_gl_account = nssf_liability  # Liability for credit (employee deduction)
    nssf_pa.employer_gl_account = nssf_expense     # Expense for debit (employer contribution)
    nssf_pa.save()
    print(f"  Fixed NSSF: ee_gl=2605 (liability), er_gl=6104 (expense)")

# PAYE deduction: ee_gl should be liability 2604
paye_pa = PayrollAccount.objects.filter(name='PAYE', account_type='deduction').first()
if paye_pa:
    paye_liability = Account.objects.get(code='2604')
    paye_pa.employee_gl_account = paye_liability
    paye_pa.save()
    print(f"  Fixed PAYE: ee_gl=2604 (liability)")


# ── Step 3: Create missing PayrollAccounts ──────────────────────────
print("\n=== Step 3: Creating missing PayrollAccounts ===")

shif_liability = Account.objects.get(code='2606')
housing_liability = Account.objects.get(code='2607')
housing_expense = Account.objects.get(code='6105')

# SHIF PayrollAccount
shif_pa, created = PayrollAccount.objects.get_or_create(
    code='SHIF',
    defaults={
        'name': 'SHIF',
        'account_type': 'deduction',
        'category': 'statutory',
        'employee_gl_account': shif_liability,
        'is_active': True,
        'used_for_paye': False,
        'used_for_pension': False,
        'is_allowable_deduction': False,
    }
)
if not created:
    shif_pa.employee_gl_account = shif_liability
    shif_pa.save()
status = 'Created' if created else 'Updated'
print(f"  {status}: SHIF PayrollAccount (ee_gl=2606)")

# Housing Levy PayrollAccount
housing_pa, created = PayrollAccount.objects.get_or_create(
    code='HOUSING_LEVY',
    defaults={
        'name': 'HOUSING LEVY',
        'account_type': 'deduction',
        'category': 'statutory',
        'employee_gl_account': housing_liability,
        'employer_gl_account': housing_expense,
        'has_employer_contribution': True,
        'is_active': True,
        'used_for_paye': False,
        'used_for_pension': False,
        'is_allowable_deduction': False,
    }
)
if not created:
    housing_pa.employee_gl_account = housing_liability
    housing_pa.employer_gl_account = housing_expense
    housing_pa.save()
status = 'Created' if created else 'Updated'
print(f"  {status}: HOUSING LEVY PayrollAccount (ee_gl=2607, er_gl=6105)")


# ── Step 4: Link StatutoryRates to PayrollAccounts ──────────────────
print("\n=== Step 4: Linking StatutoryRates to PayrollAccounts ===")

# Get/refresh PayrollAccount references
nssf_pa = PayrollAccount.objects.filter(name='NSSF', account_type='deduction').first()
paye_pa = PayrollAccount.objects.filter(name='PAYE', account_type='deduction').first()
shif_pa = PayrollAccount.objects.filter(code='SHIF', account_type='deduction').first()
housing_pa = PayrollAccount.objects.filter(code='HOUSING_LEVY', account_type='deduction').first()

# NSSF Tier 1 and Tier 2
nssf_rates = StatutoryRate.objects.filter(rate_type__startswith='nssf')
for rate in nssf_rates:
    rate.payroll_account = nssf_pa
    rate.save()
    print(f"  Linked {rate.rate_type} -> NSSF PayrollAccount")

# SHIF
shif_rates = StatutoryRate.objects.filter(rate_type='shif')
for rate in shif_rates:
    rate.payroll_account = shif_pa
    rate.save()
    print(f"  Linked {rate.rate_type} -> SHIF PayrollAccount")

# Housing Levy
housing_rates = StatutoryRate.objects.filter(rate_type='housing_levy')
for rate in housing_rates:
    rate.payroll_account = housing_pa
    rate.save()
    print(f"  Linked {rate.rate_type} -> HOUSING LEVY PayrollAccount")

# PAYE: Check if there's a DeductionType with code 'paye'
from workforce.models import DeductionType
paye_dt, _ = DeductionType.objects.get_or_create(
    code='paye',
    defaults={
        'name': 'PAYE',
        'category': 'statutory',
        'is_mandatory': True,
        'gl_account_code': '2604',
        'is_active': True,
    }
)
print(f"  PAYE DeductionType: {paye_dt.code}")


# ── Step 5: Create GLAccountMappings ────────────────────────────────
print("\n=== Step 5: Creating GLAccountMappings ===")

mappings = [
    ('net_pay_liability', '2601', 'Netpay Liability'),
    ('salary_expense', '6101', 'Salaries and Wages'),
    ('paye_liability', '2604', 'PAYE Liability'),
    ('nssf_liability', '2605', 'NSSF Liability'),
    ('nhif_liability', '2606', 'SHIF Liability'),
    ('housing_levy', '2607', 'Housing Levy Liability'),
]

for mapping_type, code, name in mappings:
    obj, created = GLAccountMapping.objects.get_or_create(
        mapping_type=mapping_type,
        defaults={
            'gl_account_code': code,
            'gl_account_name': name,
            'is_active': True,
        }
    )
    status = 'Created' if created else 'Exists'
    print(f"  {status}: {mapping_type} -> {code} ({name})")


# ── Step 6: Enable available_in_payroll on new accounts ─────────────
print("\n=== Step 6: Ensuring payroll flag on all accounts ===")
codes = ['2601', '2602', '2603', '2604', '2605', '2606', '2607', '6101', '6102', '6103', '6104', '6105']
updated = Account.objects.filter(code__in=codes, available_in_payroll=False).update(available_in_payroll=True)
print(f"  Updated {updated} accounts to available_in_payroll=True")


# ── Final summary ──────────────────────────────────────────────────
print("\n=== Summary ===")
print("PayrollAccounts:")
for pa in PayrollAccount.objects.filter(is_active=True).select_related('employee_gl_account', 'employer_gl_account'):
    ee = pa.employee_gl_account
    er = pa.employer_gl_account
    print(f"  {pa.name} [{pa.account_type}/{pa.category}] | ee_gl={ee.code if ee else '-'} | er_gl={er.code if er else '-'}")

print("\nStatutoryRate linkages:")
for r in StatutoryRate.objects.filter(is_active=True).select_related('payroll_account'):
    pa = r.payroll_account
    print(f"  {r.rate_type}: PA={pa.name if pa else 'NONE'}")

print("\nGLAccountMappings:")
for m in GLAccountMapping.objects.filter(is_active=True):
    print(f"  {m.mapping_type}: {m.gl_account_code} ({m.gl_account_name})")
