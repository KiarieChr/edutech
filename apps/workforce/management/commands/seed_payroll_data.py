"""
Management command to seed current Kenyan payroll statutory rates and sample pay grades.

Usage:
    python manage.py seed_payroll_data              # Seed everything
    python manage.py seed_payroll_data --paye        # PAYE tax bands + reliefs only
    python manage.py seed_payroll_data --statutory    # NSSF, SHIF, Housing Levy, NITA only
    python manage.py seed_payroll_data --grades       # Sample pay grades + steps only
    python manage.py seed_payroll_data --clear        # Clear existing data before seeding
"""

from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from workforce.models import (
    TaxBand,
    TaxRelief,
    StatutoryRate,
    JobGrade,
    PayGradeStep,
)


# ──────────────────────────────────────────────
# Kenya PAYE Tax Bands  (FY 2024/2025, current)
# ──────────────────────────────────────────────
TAX_BANDS = [
    {'lower': 0,       'upper': 24000,   'rate': 10,   'order': 1},
    {'lower': 24001,   'upper': 32333,   'rate': 25,   'order': 2},
    {'lower': 32334,   'upper': 500000,  'rate': 30,   'order': 3},
    {'lower': 500001,  'upper': 800000,  'rate': 32.5, 'order': 4},
    {'lower': 800001,  'upper': None,    'rate': 35,   'order': 5},
]

# ──────────────────────────────────────────────
# Tax Reliefs (Monthly)
# ──────────────────────────────────────────────
TAX_RELIEFS = [
    {
        'type': 'personal',
        'name': 'Personal Relief',
        'amount': 2400,
        'percentage': None,
        'max_amount': None,
    },
    {
        'type': 'insurance',
        'name': 'Insurance Relief',
        'amount': None,
        'percentage': 15,
        'max_amount': 5000,
    },
    {
        'type': 'housing',
        'name': 'Affordable Housing Relief',
        'amount': None,
        'percentage': 15,
        'max_amount': 9000,
    },
    {
        'type': 'pension',
        'name': 'Pension Relief',
        'amount': None,
        'percentage': 15,
        'max_amount': 20000,
    },
    {
        'type': 'disability',
        'name': 'Disability Exemption',
        'amount': 150000,
        'percentage': None,
        'max_amount': None,
    },
]

# ──────────────────────────────────────────────
# Statutory Rates (Current as of 2025)
# ──────────────────────────────────────────────
STATUTORY_RATES = [
    {
        'type': 'nssf_tier1',
        'name': 'NSSF Tier I',
        'employee_rate': Decimal('6.00'),
        'employer_rate': Decimal('6.00'),
        'fixed_amount': None,
        'lower_limit': Decimal('0'),
        'upper_limit': Decimal('7000'),
        'max_contribution': Decimal('420'),
    },
    {
        'type': 'nssf_tier2',
        'name': 'NSSF Tier II',
        'employee_rate': Decimal('6.00'),
        'employer_rate': Decimal('6.00'),
        'fixed_amount': None,
        'lower_limit': Decimal('7001'),
        'upper_limit': Decimal('36000'),
        'max_contribution': Decimal('1740'),
    },
    {
        'type': 'shif',
        'name': 'Social Health Insurance Fund (SHIF)',
        'employee_rate': Decimal('2.75'),
        'employer_rate': Decimal('0'),
        'fixed_amount': None,
        'lower_limit': None,
        'upper_limit': None,
        'max_contribution': None,
    },
    {
        'type': 'housing_levy',
        'name': 'Affordable Housing Levy',
        'employee_rate': Decimal('1.50'),
        'employer_rate': Decimal('1.50'),
        'fixed_amount': None,
        'lower_limit': None,
        'upper_limit': None,
        'max_contribution': None,
    },
    {
        'type': 'nita',
        'name': 'NITA Levy',
        'employee_rate': None,
        'employer_rate': None,
        'fixed_amount': Decimal('50'),
        'lower_limit': None,
        'upper_limit': None,
        'max_contribution': None,
    },
]

# ──────────────────────────────────────────────
# Sample Pay Grades (Kenyan education sector)
# ──────────────────────────────────────────────
PAY_GRADES = [
    # Support Staff
    {
        'code': 'A',  'name': 'Support Staff I',
        'category': 'non_teaching', 'level': 1,
        'min': 15000, 'max': 20000,
        'steps': [15000, 16000, 17000, 18000, 19000, 20000],
    },
    {
        'code': 'B',  'name': 'Support Staff II',
        'category': 'non_teaching', 'level': 2,
        'min': 20000, 'max': 28000,
        'steps': [20000, 21500, 23000, 24500, 26000, 28000],
    },
    # Administrative
    {
        'code': 'C',  'name': 'Administrative Assistant',
        'category': 'non_teaching', 'level': 3,
        'min': 25000, 'max': 35000,
        'steps': [25000, 27000, 29000, 31000, 33000, 35000],
    },
    {
        'code': 'D',  'name': 'Administrative Officer',
        'category': 'non_teaching', 'level': 4,
        'min': 35000, 'max': 50000,
        'steps': [35000, 38000, 41000, 44000, 47000, 50000],
    },
    # Teaching Staff
    {
        'code': 'T1', 'name': 'Teacher (P1 Certificate)',
        'category': 'teaching', 'level': 5,
        'min': 30000, 'max': 45000,
        'steps': [30000, 33000, 36000, 39000, 42000, 45000],
    },
    {
        'code': 'T2', 'name': 'Teacher (Diploma)',
        'category': 'teaching', 'level': 6,
        'min': 40000, 'max': 58000,
        'steps': [40000, 43500, 47000, 50500, 54000, 58000],
    },
    {
        'code': 'T3', 'name': 'Teacher (Graduate)',
        'category': 'teaching', 'level': 7,
        'min': 50000, 'max': 72000, 'degree': True,
        'steps': [50000, 54500, 59000, 63500, 68000, 72000],
    },
    {
        'code': 'T4', 'name': 'Senior Teacher',
        'category': 'teaching', 'level': 8,
        'min': 65000, 'max': 90000, 'degree': True,
        'steps': [65000, 70000, 75000, 80000, 85000, 90000],
    },
    # Management
    {
        'code': 'M1', 'name': 'Head of Department',
        'category': 'management', 'level': 9,
        'min': 80000, 'max': 110000, 'degree': True,
        'steps': [80000, 86000, 92000, 98000, 104000, 110000],
    },
    {
        'code': 'M2', 'name': 'Deputy Principal',
        'category': 'management', 'level': 10,
        'min': 100000, 'max': 140000, 'degree': True,
        'steps': [100000, 108000, 116000, 124000, 132000, 140000],
    },
    {
        'code': 'M3', 'name': 'Principal',
        'category': 'management', 'level': 11,
        'min': 130000, 'max': 180000, 'degree': True,
        'steps': [130000, 140000, 150000, 160000, 170000, 180000],
    },
    # Executive
    {
        'code': 'E1', 'name': 'Director',
        'category': 'executive', 'level': 12,
        'min': 180000, 'max': 280000, 'degree': True,
        'steps': [180000, 200000, 220000, 240000, 260000, 280000],
    },
    {
        'code': 'E2', 'name': 'Chief Executive',
        'category': 'executive', 'level': 13,
        'min': 250000, 'max': 400000, 'degree': True,
        'steps': [250000, 280000, 310000, 340000, 370000, 400000],
    },
]


class Command(BaseCommand):
    help = 'Seed Kenyan payroll statutory rates (PAYE, NSSF, SHIF, Housing Levy) and sample pay grades'

    def add_arguments(self, parser):
        parser.add_argument('--paye', action='store_true', help='Seed PAYE tax bands and reliefs only')
        parser.add_argument('--statutory', action='store_true', help='Seed NSSF, SHIF, Housing Levy, NITA only')
        parser.add_argument('--grades', action='store_true', help='Seed sample pay grades only')
        parser.add_argument('--clear', action='store_true', help='Clear existing data before seeding')

    @transaction.atomic
    def handle(self, *args, **options):
        seed_all = not (options['paye'] or options['statutory'] or options['grades'])
        today = date.today()

        if options['paye'] or seed_all:
            self._seed_paye(today, options['clear'])

        if options['statutory'] or seed_all:
            self._seed_statutory(today, options['clear'])

        if options['grades'] or seed_all:
            self._seed_grades(options['clear'])

        self.stdout.write(self.style.SUCCESS('\nDone! All selected data seeded successfully.'))

    # ── PAYE ──────────────────────────────────

    def _seed_paye(self, today, clear):
        self.stdout.write(self.style.MIGRATE_HEADING('\n── PAYE Tax Bands ──'))

        if clear:
            deleted, _ = TaxBand.objects.all().delete()
            self.stdout.write(f'  Cleared {deleted} existing tax bands')

        for band in TAX_BANDS:
            obj, created = TaxBand.objects.update_or_create(
                lower_limit=band['lower'],
                effective_date=today,
                defaults={
                    'upper_limit': band['upper'],
                    'rate': band['rate'],
                    'sort_order': band['order'],
                    'is_active': True,
                },
            )
            status = 'Created' if created else 'Updated'
            upper = f"KES {band['upper']:,.0f}" if band['upper'] else '∞'
            self.stdout.write(
                f"  {status}: KES {band['lower']:>10,.0f} – {upper:>12}  →  {band['rate']}%"
            )

        self.stdout.write(self.style.MIGRATE_HEADING('\n── Tax Reliefs ──'))

        if clear:
            deleted, _ = TaxRelief.objects.all().delete()
            self.stdout.write(f'  Cleared {deleted} existing reliefs')

        for relief in TAX_RELIEFS:
            obj, created = TaxRelief.objects.update_or_create(
                relief_type=relief['type'],
                defaults={
                    'name': relief['name'],
                    'amount': relief['amount'],
                    'percentage': relief['percentage'],
                    'max_amount': relief['max_amount'],
                    'effective_date': today,
                    'is_active': True,
                },
            )
            status = 'Created' if created else 'Updated'
            if relief['amount']:
                detail = f"KES {relief['amount']:,.0f}/month"
            else:
                detail = f"{relief['percentage']}%"
                if relief['max_amount']:
                    detail += f" (max KES {relief['max_amount']:,.0f})"
            self.stdout.write(f"  {status}: {relief['name']:30s}  →  {detail}")

    # ── Statutory Rates ───────────────────────

    def _seed_statutory(self, today, clear):
        self.stdout.write(self.style.MIGRATE_HEADING('\n── Statutory Rates ──'))

        if clear:
            deleted, _ = StatutoryRate.objects.all().delete()
            self.stdout.write(f'  Cleared {deleted} existing statutory rates')

        for rate in STATUTORY_RATES:
            obj, created = StatutoryRate.objects.update_or_create(
                rate_type=rate['type'],
                effective_date=today,
                defaults={
                    'name': rate['name'],
                    'employee_rate': rate['employee_rate'],
                    'employer_rate': rate['employer_rate'],
                    'fixed_amount': rate['fixed_amount'],
                    'lower_limit': rate['lower_limit'],
                    'upper_limit': rate['upper_limit'],
                    'max_contribution': rate['max_contribution'],
                    'is_active': True,
                    'is_enabled': True,
                },
            )
            status = 'Created' if created else 'Updated'

            if rate['fixed_amount']:
                detail = f"Fixed KES {rate['fixed_amount']:,.0f}/employee (employer)"
            else:
                parts = []
                if rate['employee_rate']:
                    parts.append(f"EE {rate['employee_rate']}%")
                if rate['employer_rate'] and rate['employer_rate'] > 0:
                    parts.append(f"ER {rate['employer_rate']}%")
                detail = ' + '.join(parts)
                if rate['max_contribution']:
                    detail += f" (max KES {rate['max_contribution']:,.0f})"
                if rate['upper_limit']:
                    detail += f" on KES {rate['lower_limit']:,.0f}–{rate['upper_limit']:,.0f}"

            self.stdout.write(f"  {status}: {rate['name']:35s}  →  {detail}")

    # ── Pay Grades ────────────────────────────

    def _seed_grades(self, clear):
        self.stdout.write(self.style.MIGRATE_HEADING('\n── Pay Grades & Steps ──'))

        if clear:
            deleted_steps, _ = PayGradeStep.objects.all().delete()
            deleted_grades, _ = JobGrade.objects.all().delete()
            self.stdout.write(f'  Cleared {deleted_grades} grades and {deleted_steps} steps')

        for g in PAY_GRADES:
            grade, created = JobGrade.objects.update_or_create(
                code=g['code'],
                defaults={
                    'name': g['name'],
                    'category': g['category'],
                    'grade_level': g['level'],
                    'min_salary': g['min'],
                    'max_salary': g['max'],
                    'currency': 'KES',
                    'requires_degree': g.get('degree', False),
                    'is_active': True,
                },
            )

            grade_status = 'Created' if created else 'Updated'

            # Seed steps
            step_count = 0
            for i, amount in enumerate(g['steps'], start=1):
                _, step_created = PayGradeStep.objects.update_or_create(
                    job_grade=grade,
                    step_number=i,
                    defaults={'amount': amount, 'is_active': True},
                )
                if step_created:
                    step_count += 1

            self.stdout.write(
                f"  {grade_status}: {g['code']:4s} {g['name']:30s}  "
                f"KES {g['min']:>9,.0f} – {g['max']:>9,.0f}  "
                f"({len(g['steps'])} steps, {step_count} new)"
            )
