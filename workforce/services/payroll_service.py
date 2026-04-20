"""
Payroll Calculation Service
Handles the end-to-end payroll processing pipeline:
  1. Identify eligible employees
  2. Resolve basic salary from EmployeePayProfile
  3. Gather earnings: employee-level + group-level (PayrollAccount-aware)
  4. Gather deductions: employee-level + group-level (PayrollAccount-aware)
  5. Calculate pension contributions (NSSF + third-party schemes)
  6. Calculate statutory deductions (NSSF, SHIF, Housing Levy)
  7. Calculate PAYE with proper allowable deductions & reliefs
  8. Create PayrollCalculation + PayrollCalculationDetail records
  9. Create PensionContribution records
  10. Update PayrollPeriod totals
"""

from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone
from django.db import transaction
from django.db.models import Q, F

from workforce.core_models import Employee
from workforce.models import (
    PayrollPeriod,
    PayrollCalculation,
    PayrollCalculationDetail,
    PayrollAccount,
    EmployeePayProfile,
    EmployeeEarning,
    EmployeeDeduction,
    GroupEarning,
    GroupDeduction,
    PayrollConfiguration,
    TaxBand,
    TaxRelief,
    StatutoryRate,
    EarningType,
    DeductionType,
    PayrollAuditLog,
    EmployeePensionEnrollment,
    PensionContribution,
    GLAccountMapping,
)
from journals.services import JournalService
from journals.models import JournalEntry, LedgerEntry

ZERO = Decimal('0.00')
HUNDRED = Decimal('100')


def _round(value):
    """Round to 2 decimal places."""
    if value is None:
        return ZERO
    return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


class PayrollCalculationService:
    """Process payroll for a given PayrollPeriod."""

    def __init__(self, period: PayrollPeriod, processed_by=None):
        self.period = period
        self.processed_by = processed_by
        self.config = PayrollConfiguration.get_active()
        self.tax_bands = list(TaxBand.get_current_bands())
        self.tax_reliefs = self._load_tax_reliefs()
        self.statutory_rates = self._load_statutory_rates()
        self.errors = []
        self.processed_count = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(self):
        """
        Main entry point. Returns dict with results.
        Wraps everything in an atomic transaction so partial failures
        don't leave orphan records.
        """
        employees = self._get_eligible_employees()

        if not employees.exists():
            return {
                'success': False,
                'message': 'No eligible employees found for this period.',
                'processed': 0,
                'errors': [],
            }

        with transaction.atomic():
            # Delete any previous calculations for this period (re-run)
            PayrollCalculationDetail.objects.filter(
                payroll_calculation__payroll_period=self.period
            ).delete()
            PayrollCalculation.objects.filter(
                payroll_period=self.period
            ).delete()
            # Also clear previous pension contributions for this period
            PensionContribution.objects.filter(
                payroll_period=self.period
            ).delete()

            # Delete existing payroll journals for this period (re-run)
            payroll_ref = f'PAYROLL-{self.period.period_name}'
            existing_journals = JournalEntry.objects.filter(reference=payroll_ref)
            if existing_journals.exists():
                # Delete LedgerEntry first (PROTECT constraint on journal_entry FK)
                LedgerEntry.objects.filter(journal_entry__in=existing_journals).delete()
                existing_journals.delete()  # Cascades to JournalLine

            for emp in employees:
                try:
                    self._process_employee(emp)
                    self.processed_count += 1
                except Exception as e:
                    self.errors.append(
                        f"{emp.employee_no} ({emp.first_name} {emp.last_name}): {str(e)}"
                    )

            # Aggregate totals onto the period
            self._update_period_totals()

            # Create and post payroll journal entry
            self._create_payroll_journals()

        return {
            'success': True,
            'message': f'Processed {self.processed_count} employees.',
            'processed': self.processed_count,
            'errors': self.errors,
        }

    # ------------------------------------------------------------------
    # Helpers – data loading
    # ------------------------------------------------------------------
    def _load_tax_reliefs(self):
        today = timezone.now().date()
        return {
            r.relief_type: r
            for r in TaxRelief.objects.filter(
                is_active=True,
                effective_date__lte=today,
            ).filter(
                Q(expiry_date__isnull=True) | Q(expiry_date__gte=today)
            )
        }

    def _load_statutory_rates(self):
        today = timezone.now().date()
        return {
            r.rate_type: r
            for r in StatutoryRate.objects.filter(
                is_active=True,
                is_enabled=True,
                effective_date__lte=today,
            ).filter(
                Q(expiry_date__isnull=True) | Q(expiry_date__gte=today)
            )
        }

    def _get_eligible_employees(self):
        """Active employees."""
        return Employee.objects.filter(
            employment_status__in=['active', 'probation'],
        ).select_related('department', 'job_grade')

    # ------------------------------------------------------------------
    # Per-employee processing
    # ------------------------------------------------------------------
    def _process_employee(self, emp: Employee):
        # 1. Get basic salary from active EmployeePayProfile
        pay_profile = (
            EmployeePayProfile.objects.filter(
                employee=emp,
                is_active=True,
                effective_from__lte=self.period.end_date,
            )
            .filter(
                Q(effective_to__isnull=True) | Q(effective_to__gte=self.period.start_date)
            )
            .order_by('-effective_from')
            .select_related('pay_profile')
            .first()
        )

        if not pay_profile:
            raise ValueError("No active pay profile found")

        basic_salary = _round(pay_profile.basic_salary)
        job_grade = emp.job_grade

        # 2. Gather earnings (employee-level + group-level)
        earnings = self._get_all_earnings(emp, job_grade, basic_salary)

        # 3. Build earning totals
        total_allowances = ZERO
        total_overtime = ZERO
        total_bonuses = ZERO

        for e in earnings:
            amount = e['amount']
            cat = e.get('category', 'allowance')
            if cat == 'overtime':
                total_overtime += amount
            elif cat == 'bonus':
                total_bonuses += amount
            else:
                total_allowances += amount

        total_earnings = total_allowances + total_overtime + total_bonuses
        gross_pay = basic_salary + total_earnings

        # 4. Calculate statutory deductions (NSSF, SHIF, Housing Levy)
        statutory = self._calculate_statutory(gross_pay, basic_salary)

        # 5. Calculate third-party pension contributions
        pension_result = self._calculate_pension(emp, basic_salary, gross_pay)

        # 6. Gather voluntary / loan deductions (employee-level + group-level)
        vol_deductions = self._get_all_deductions(emp, job_grade, gross_pay, basic_salary)
        total_voluntary = sum(d['amount'] for d in vol_deductions)
        total_loan = sum(
            d['amount'] for d in vol_deductions if d.get('category') == 'loan'
        )
        total_voluntary_only = total_voluntary - total_loan

        # 7. Calculate PAYE
        # Allowable deductions reduce taxable income before PAYE:
        # - NSSF employee contribution
        # - Tax-exempt pension contributions (employee portion)
        # - Any deduction where payroll_account.is_allowable_deduction = True
        allowable_before_tax = statutory.get('nssf_employee', ZERO)
        allowable_before_tax += pension_result['tax_exempt_employee']

        # Check voluntary deductions for is_allowable_deduction flag
        allowable_voluntary = ZERO
        for d in vol_deductions:
            pa = d.get('payroll_account')
            if pa and pa.is_allowable_deduction:
                allowable_voluntary += d['amount']
        allowable_before_tax += allowable_voluntary

        taxable_income = max(ZERO, gross_pay - allowable_before_tax)

        # PAYE with proper insurance relief from actual SHIF amount
        shif_amount = statutory.get('shif', ZERO)
        paye = self._calculate_paye(taxable_income, shif_amount)

        # 8. Total deductions
        total_statutory = statutory['total_employee'] + paye
        total_pension_employee = pension_result['total_employee']
        total_deductions = (
            total_statutory
            + total_pension_employee
            + total_voluntary
        )

        # 9. Net pay & employer cost
        net_pay = gross_pay - total_deductions
        employer_cost = (
            gross_pay
            + statutory.get('nssf_employer', ZERO)
            + statutory.get('housing_levy_employer', ZERO)
            + pension_result['total_employer']
        )

        # Combined pension (NSSF + third-party)
        pension_employee_total = statutory.get('nssf_employee', ZERO) + pension_result['total_employee']
        pension_employer_total = statutory.get('nssf_employer', ZERO) + pension_result['total_employer']

        # 10. Create PayrollCalculation
        calc = PayrollCalculation.objects.create(
            employee=emp,
            payroll_period=self.period,
            basic_salary=basic_salary,
            total_earnings=total_earnings,
            total_allowances=total_allowances,
            total_overtime=total_overtime,
            total_bonuses=total_bonuses,
            gross_pay=gross_pay,
            total_statutory_deductions=total_statutory,
            total_voluntary_deductions=_round(Decimal(str(total_voluntary_only))),
            total_loan_deductions=_round(Decimal(str(total_loan))),
            total_deductions=total_deductions,
            taxable_income=taxable_income,
            tax_amount=paye,
            pension_employee=pension_employee_total,
            pension_employer=pension_employer_total,
            net_pay=net_pay,
            employer_cost=employer_cost,
            payment_method='bank_transfer',
            payment_status='pending',
            calculated_by=self.processed_by,
        )

        # 11. Create detail line items
        self._create_earning_details(calc, basic_salary, earnings)
        self._create_statutory_details(calc, statutory, paye)
        self._create_pension_details(calc, pension_result)
        self._create_deduction_details(calc, vol_deductions)

        # 12. Create PensionContribution records
        self._create_pension_contributions(pension_result)

        # 13. Update loan balances
        self._update_loan_balances(vol_deductions)

        # 14. Audit log
        PayrollAuditLog.objects.create(
            payroll_period=self.period,
            employee=emp,
            action='calculated',
            new_values={
                'basic_salary': str(basic_salary),
                'gross_pay': str(gross_pay),
                'net_pay': str(net_pay),
                'total_deductions': str(total_deductions),
                'paye': str(paye),
                'pension_employee': str(pension_employee_total),
                'pension_employer': str(pension_employer_total),
            },
            performed_by=self.processed_by,
        )

    # ------------------------------------------------------------------
    # Earnings resolution (Phase 1)
    # ------------------------------------------------------------------
    def _get_all_earnings(self, emp, job_grade, basic_salary):
        """
        Merge employee-level + group-level earnings.
        Employee-level takes precedence: if an employee has a specific
        earning for a payroll_account, the group earning for the same
        account is skipped.
        Returns list of dicts with payroll_account-aware fields.
        """
        result = []
        seen_accounts = set()  # payroll_account IDs already covered

        # --- Employee-level earnings ---
        emp_earnings = EmployeeEarning.objects.filter(
            employee=emp,
            status__in=['approved', 'pending'],
        ).filter(
            Q(is_recurring=True, effective_from__lte=self.period.end_date)
            & (Q(effective_to__isnull=True) | Q(effective_to__gte=self.period.start_date))
            |
            Q(is_one_time=True, payroll_period=self.period)
        ).select_related('earning_type', 'payroll_account', 'payroll_account__employee_gl_account')

        for earning in emp_earnings:
            amount = self._resolve_earning_amount(earning, basic_salary)
            if amount <= ZERO:
                continue

            pa = earning.payroll_account
            et = earning.earning_type

            # Determine taxable/pensionable from PayrollAccount flags if available
            if pa:
                is_taxable = pa.used_for_paye
                is_pensionable = pa.used_for_pension
                category = pa.category
                description = pa.name
                gl_code = pa.employee_gl_account.code if pa.employee_gl_account else ''
                seen_accounts.add(pa.id)
            else:
                is_taxable = earning.is_taxable
                is_pensionable = earning.is_pensionable
                category = et.category if et else 'allowance'
                description = et.name if et else 'Earning'
                gl_code = et.gl_account_code if et else ''

            result.append({
                'description': description,
                'amount': amount,
                'category': category,
                'is_taxable': is_taxable,
                'is_pensionable': is_pensionable,
                'payroll_account': pa,
                'earning_type': et,
                'gl_account_code': gl_code,
            })

        # --- Group-level earnings (from job grade) ---
        if job_grade:
            group_earnings = GroupEarning.objects.filter(
                job_grade=job_grade,
                is_active=True,
                effective_from__lte=self.period.end_date,
            ).filter(
                Q(effective_to__isnull=True) | Q(effective_to__gte=self.period.start_date)
            ).select_related('payroll_account', 'payroll_account__employee_gl_account')

            for ge in group_earnings:
                if ge.payroll_account_id in seen_accounts:
                    continue  # Employee-level overrides group

                pa = ge.payroll_account
                amount = _round(ge.amount)
                if amount <= ZERO:
                    continue

                result.append({
                    'description': pa.name,
                    'amount': amount,
                    'category': pa.category,
                    'is_taxable': pa.used_for_paye,
                    'is_pensionable': pa.used_for_pension,
                    'payroll_account': pa,
                    'earning_type': None,
                    'gl_account_code': pa.employee_gl_account.code if pa.employee_gl_account else '',
                })

        return result

    def _resolve_earning_amount(self, earning, basic_salary):
        """Resolve earning amount based on calculation basis."""
        if earning.calculation_basis == 'fixed':
            return _round(earning.amount)
        elif earning.calculation_basis == 'hours' and earning.units and earning.rate:
            pa = earning.payroll_account
            et = earning.earning_type
            cat = (pa.category if pa else (et.category if et else ''))
            multiplier = self.config.overtime_multiplier if cat == 'overtime' else Decimal('1')
            return _round(earning.units * earning.rate * multiplier)
        elif earning.calculation_basis == 'rate' and earning.units and earning.rate:
            return _round(earning.units * earning.rate)
        elif earning.calculation_basis == 'percentage' and earning.rate:
            return _round(basic_salary * earning.rate / HUNDRED)
        return _round(earning.amount)

    # ------------------------------------------------------------------
    # Deductions resolution (Phase 1)
    # ------------------------------------------------------------------
    def _get_all_deductions(self, emp, job_grade, gross_pay, basic_salary):
        """
        Merge employee-level + group-level deductions.
        Employee-level takes precedence over group-level for the same
        payroll_account.
        """
        result = []
        seen_accounts = set()

        # --- Employee-level deductions ---
        emp_deductions = EmployeeDeduction.objects.filter(
            employee=emp,
            status__in=['approved', 'pending'],
        ).filter(
            Q(is_recurring=True, effective_from__lte=self.period.end_date)
            & (Q(effective_to__isnull=True) | Q(effective_to__gte=self.period.start_date))
            |
            Q(is_one_time=True, payroll_period=self.period)
        ).select_related('deduction_type', 'payroll_account', 'payroll_account__employee_gl_account')

        for ded in emp_deductions:
            amount = self._resolve_deduction_amount(ded, gross_pay, basic_salary)
            if amount <= ZERO:
                continue

            pa = ded.payroll_account
            dt = ded.deduction_type

            # For loans, don't deduct more than balance remaining
            category = (pa.category if pa else (dt.category if dt else 'voluntary'))
            if category == 'loan' and ded.balance_remaining is not None:
                if ded.balance_remaining <= ZERO:
                    continue
                amount = min(amount, _round(ded.balance_remaining))

            if pa:
                description = pa.name
                gl_code = pa.employee_gl_account.code if pa.employee_gl_account else ''
                seen_accounts.add(pa.id)
            else:
                description = dt.name if dt else 'Deduction'
                gl_code = dt.gl_account_code if dt else ''

            result.append({
                'description': description,
                'amount': _round(amount),
                'category': category,
                'payroll_account': pa,
                'deduction_type': dt,
                'gl_account_code': gl_code,
                'deduction_id': ded.pk,
                'is_loan': category == 'loan',
            })

        # --- Group-level deductions (from job grade) ---
        if job_grade:
            group_deductions = GroupDeduction.objects.filter(
                job_grade=job_grade,
                is_active=True,
                effective_from__lte=self.period.end_date,
            ).filter(
                Q(effective_to__isnull=True) | Q(effective_to__gte=self.period.start_date)
            ).select_related('payroll_account', 'payroll_account__employee_gl_account')

            for gd in group_deductions:
                if gd.payroll_account_id in seen_accounts:
                    continue  # Employee-level overrides group

                pa = gd.payroll_account
                amount = self._resolve_group_deduction_amount(gd, gross_pay, basic_salary)
                if amount <= ZERO:
                    continue

                result.append({
                    'description': pa.name,
                    'amount': _round(amount),
                    'category': pa.category,
                    'payroll_account': pa,
                    'deduction_type': None,
                    'gl_account_code': pa.employee_gl_account.code if pa.employee_gl_account else '',
                    'deduction_id': None,
                    'is_loan': False,
                })

        return result

    def _resolve_deduction_amount(self, ded, gross_pay, basic_salary):
        if ded.calculation_method == 'fixed':
            return _round(ded.amount)
        elif ded.calculation_method == 'percentage_of_gross' and ded.percentage:
            return _round(gross_pay * ded.percentage / HUNDRED)
        elif ded.calculation_method == 'percentage_of_basic' and ded.percentage:
            return _round(basic_salary * ded.percentage / HUNDRED)
        return _round(ded.amount)

    def _resolve_group_deduction_amount(self, gd, gross_pay, basic_salary):
        if gd.calculation_method == 'fixed':
            return _round(gd.amount)
        elif gd.calculation_method == 'percentage_of_gross' and gd.percentage:
            return _round(gross_pay * gd.percentage / HUNDRED)
        elif gd.calculation_method == 'percentage_of_basic' and gd.percentage:
            return _round(basic_salary * gd.percentage / HUNDRED)
        return _round(gd.amount)

    def _update_loan_balances(self, deductions):
        """Reduce balance_remaining for loan deductions."""
        for d in deductions:
            if d.get('is_loan') and d.get('deduction_id'):
                EmployeeDeduction.objects.filter(pk=d['deduction_id']).update(
                    balance_remaining=F('balance_remaining') - d['amount']
                )

    # ------------------------------------------------------------------
    # Pension calculation (Phase 2)
    # ------------------------------------------------------------------
    def _calculate_pension(self, emp, basic_salary, gross_pay):
        """
        Calculate third-party pension contributions from PensionScheme enrollments.
        Returns dict with per-scheme breakdown and totals.
        """
        result = {
            'schemes': [],          # Per-scheme details
            'total_employee': ZERO,
            'total_employer': ZERO,
            'tax_exempt_employee': ZERO,  # Portion that reduces taxable income
        }

        enrollments = EmployeePensionEnrollment.objects.filter(
            employee=emp,
            status='active',
            enrollment_date__lte=self.period.end_date,
        ).filter(
            Q(exit_date__isnull=True) | Q(exit_date__gte=self.period.start_date)
        ).select_related(
            'pension_scheme', 'pension_scheme__payroll_account',
            'pension_scheme__payroll_account__employee_gl_account',
            'pension_scheme__payroll_account__employer_gl_account',
        )

        for enrollment in enrollments:
            scheme = enrollment.pension_scheme

            if not scheme.is_active:
                continue

            # Check scheme effective dates
            if scheme.effective_from > self.period.end_date:
                continue
            if scheme.effective_to and scheme.effective_to < self.period.start_date:
                continue

            # Get effective rates via precedence: employee > grade > scheme
            ee_rate, er_rate = enrollment.get_effective_rates()

            # Determine base amount
            if scheme.calculation_basis == 'basic_salary':
                base = basic_salary
            elif scheme.calculation_basis == 'gross_pay':
                base = gross_pay
            elif scheme.calculation_basis == 'fixed_amount':
                # Fixed amount: use custom_amount from enrollment or 0
                base = ZERO
            else:
                base = basic_salary

            # Calculate contributions
            if scheme.calculation_basis == 'fixed_amount' and enrollment.custom_amount:
                ee_amount = _round(enrollment.custom_amount)
                er_amount = ZERO  # Fixed amounts are typically employee-only
            else:
                ee_amount = _round(base * ee_rate / HUNDRED)
                er_amount = _round(base * er_rate / HUNDRED)

            # Apply caps
            if scheme.max_employee_contribution:
                ee_amount = min(ee_amount, scheme.max_employee_contribution)
            if scheme.max_employer_contribution:
                er_amount = min(er_amount, scheme.max_employer_contribution)

            scheme_detail = {
                'enrollment': enrollment,
                'scheme': scheme,
                'base_amount': base,
                'employee_amount': ee_amount,
                'employer_amount': er_amount,
                'employee_rate': ee_rate,
                'employer_rate': er_rate,
                'is_tax_exempt': scheme.is_tax_exempt,
                'payroll_account': scheme.payroll_account,
            }

            result['schemes'].append(scheme_detail)
            result['total_employee'] += ee_amount
            result['total_employer'] += er_amount

            if scheme.is_tax_exempt:
                result['tax_exempt_employee'] += ee_amount

        return result

    def _create_pension_contributions(self, pension_result):
        """Create PensionContribution records for history tracking."""
        for s in pension_result['schemes']:
            PensionContribution.objects.create(
                enrollment=s['enrollment'],
                payroll_period=self.period,
                employee_amount=s['employee_amount'],
                employer_amount=s['employer_amount'],
                employee_rate_applied=s['employee_rate'],
                employer_rate_applied=s['employer_rate'],
                base_amount=s['base_amount'],
            )

    # ------------------------------------------------------------------
    # Statutory calculations – Kenya-specific (Phase 3)
    # ------------------------------------------------------------------
    def _calculate_statutory(self, gross_pay, basic_salary):
        """
        Calculate NSSF, SHIF, Housing Levy.
        Returns dict with individual amounts + totals.
        """
        result = {
            'nssf_employee': ZERO,
            'nssf_employer': ZERO,
            'shif': ZERO,
            'housing_levy_employee': ZERO,
            'housing_levy_employer': ZERO,
            'total_employee': ZERO,
            'total_employer': ZERO,
        }

        # --- NSSF (Tier I + Tier II) ---
        nssf_t1 = self.statutory_rates.get('nssf_tier1')
        nssf_t2 = self.statutory_rates.get('nssf_tier2')

        nssf_t1_employee = ZERO
        nssf_t1_employer = ZERO
        nssf_t2_employee = ZERO
        nssf_t2_employer = ZERO

        if nssf_t1:
            t1_upper = nssf_t1.upper_limit or gross_pay
            pensionable_t1 = min(gross_pay, t1_upper)
            if nssf_t1.employee_rate:
                nssf_t1_employee = _round(pensionable_t1 * nssf_t1.employee_rate / HUNDRED)
            elif nssf_t1.fixed_amount:
                nssf_t1_employee = _round(nssf_t1.fixed_amount)
            if nssf_t1.employer_rate:
                nssf_t1_employer = _round(pensionable_t1 * nssf_t1.employer_rate / HUNDRED)
            elif nssf_t1.fixed_amount:
                nssf_t1_employer = _round(nssf_t1.fixed_amount)
            # Cap tier 1 individually
            if nssf_t1.max_contribution:
                nssf_t1_employee = min(nssf_t1_employee, nssf_t1.max_contribution)
                nssf_t1_employer = min(nssf_t1_employer, nssf_t1.max_contribution)

        if nssf_t2:
            t1_upper = (nssf_t1.upper_limit if nssf_t1 and nssf_t1.upper_limit else ZERO)
            t2_upper = nssf_t2.upper_limit or gross_pay
            pensionable_t2 = max(ZERO, min(gross_pay, t2_upper) - t1_upper)
            if nssf_t2.employee_rate and pensionable_t2 > ZERO:
                nssf_t2_employee = _round(pensionable_t2 * nssf_t2.employee_rate / HUNDRED)
            if nssf_t2.employer_rate and pensionable_t2 > ZERO:
                nssf_t2_employer = _round(pensionable_t2 * nssf_t2.employer_rate / HUNDRED)
            # Cap tier 2 individually
            if nssf_t2.max_contribution:
                nssf_t2_employee = min(nssf_t2_employee, nssf_t2.max_contribution)
                nssf_t2_employer = min(nssf_t2_employer, nssf_t2.max_contribution)

        result['nssf_employee'] = nssf_t1_employee + nssf_t2_employee
        result['nssf_employer'] = nssf_t1_employer + nssf_t2_employer

        # --- SHIF (Social Health Insurance Fund, replaces NHIF) ---
        shif = self.statutory_rates.get('shif') or self.statutory_rates.get('nhif')
        if shif:
            if shif.employee_rate:
                shif_amount = _round(gross_pay * shif.employee_rate / HUNDRED)
                if shif.max_contribution:
                    shif_amount = min(shif_amount, shif.max_contribution)
                result['shif'] = shif_amount
            elif shif.fixed_amount:
                result['shif'] = _round(shif.fixed_amount)

        # --- Affordable Housing Levy ---
        housing = self.statutory_rates.get('housing_levy')
        if housing:
            if housing.employee_rate:
                result['housing_levy_employee'] = _round(
                    gross_pay * housing.employee_rate / HUNDRED
                )
            if housing.employer_rate:
                result['housing_levy_employer'] = _round(
                    gross_pay * housing.employer_rate / HUNDRED
                )

        # Employee totals (excludes PAYE — added later)
        result['total_employee'] = (
            result['nssf_employee']
            + result['shif']
            + result['housing_levy_employee']
        )
        result['total_employer'] = (
            result['nssf_employer']
            + result['housing_levy_employer']
        )

        return result

    # ------------------------------------------------------------------
    # PAYE – Kenya tax bands (Phase 3)
    # ------------------------------------------------------------------
    def _calculate_paye(self, taxable_income, shif_amount=ZERO):
        """
        Apply progressive tax bands to taxable income,
        then subtract reliefs:
        - Personal relief (fixed monthly amount)
        - Insurance relief (15% of SHIF contribution, capped)
        - Housing relief (if configured)
        - Pension relief (if configured)
        """
        if not self.tax_bands or taxable_income <= ZERO:
            return ZERO

        tax = ZERO
        remaining = taxable_income

        for band in self.tax_bands:
            if remaining <= ZERO:
                break

            lower = band.lower_limit
            upper = band.upper_limit if band.upper_limit else remaining + lower
            band_width = upper - lower
            taxable_in_band = min(remaining, band_width)
            tax += _round(taxable_in_band * band.rate / HUNDRED)
            remaining -= taxable_in_band

        # --- Personal relief ---
        personal = self.tax_reliefs.get('personal')
        if personal and personal.amount:
            tax = max(ZERO, tax - personal.amount)

        # --- Insurance relief: 15% of actual SHIF contribution, capped ---
        insurance = self.tax_reliefs.get('insurance')
        if insurance and shif_amount > ZERO:
            relief_pct = insurance.percentage or Decimal('15')
            insurance_relief = _round(shif_amount * relief_pct / HUNDRED)
            if insurance.max_amount:
                insurance_relief = min(insurance_relief, insurance.max_amount)
            tax = max(ZERO, tax - insurance_relief)

        # --- Affordable Housing relief (if configured) ---
        housing_relief = self.tax_reliefs.get('housing')
        if housing_relief and housing_relief.amount:
            tax = max(ZERO, tax - housing_relief.amount)

        # --- Pension relief (for voluntary pension, if configured) ---
        pension_relief = self.tax_reliefs.get('pension')
        if pension_relief and pension_relief.amount:
            tax = max(ZERO, tax - pension_relief.amount)

        return _round(max(ZERO, tax))

    # ------------------------------------------------------------------
    # Detail record creation (Phase 4 – GL via PayrollAccount)
    # ------------------------------------------------------------------
    def _create_earning_details(self, calc, basic_salary, earnings):
        """Create PayrollCalculationDetail for basic + each earning."""
        # Basic salary line
        basic_et = EarningType.objects.filter(category='basic').first()
        # Try to find a PayrollAccount for basic salary
        basic_pa = PayrollAccount.objects.filter(
            account_type='earning', category='basic', is_active=True
        ).first()

        PayrollCalculationDetail.objects.create(
            payroll_calculation=calc,
            item_type='earning',
            earning_type=basic_et,
            payroll_account=basic_pa,
            description='Basic Salary',
            amount=basic_salary,
            is_taxable=True,
            is_pensionable=True,
            gl_account_code=(
                basic_pa.employee_gl_account.code if basic_pa and basic_pa.employee_gl_account
                else (basic_et.gl_account_code if basic_et else 'SAL001')
            ),
        )

        for e in earnings:
            pa = e.get('payroll_account')
            result_gl = e.get('gl_account_code', '')
            if pa and pa.employee_gl_account:
                result_gl = pa.employee_gl_account.code

            PayrollCalculationDetail.objects.create(
                payroll_calculation=calc,
                item_type='earning',
                earning_type=e.get('earning_type'),
                payroll_account=pa,
                description=e['description'],
                amount=e['amount'],
                is_taxable=e.get('is_taxable', True),
                is_pensionable=e.get('is_pensionable', False),
                gl_account_code=result_gl,
            )

    def _create_statutory_details(self, calc, statutory, paye):
        """Create detail lines for statutory deductions + PAYE."""
        statutory_items = [
            ('NSSF Employee', statutory['nssf_employee'], 'nssf'),
            ('SHIF', statutory['shif'], 'shif'),
            ('Housing Levy', statutory['housing_levy_employee'], 'housing_levy'),
            ('PAYE', paye, 'paye'),
        ]
        for desc, amount, rate_type in statutory_items:
            if amount <= ZERO:
                continue

            # Resolve PayrollAccount:
            #  - For NSSF/SHIF/Housing Levy: via StatutoryRate FK
            #  - For PAYE: look up PayrollAccount directly (no StatutoryRate)
            if rate_type == 'paye':
                pa = PayrollAccount.objects.filter(
                    name='PAYE', account_type='deduction', is_active=True
                ).first()
            else:
                stat_rate = self.statutory_rates.get(
                    'nssf_tier1' if rate_type == 'nssf' else rate_type
                )
                pa = stat_rate.payroll_account if stat_rate else None

            dt = DeductionType.objects.filter(code__iexact=rate_type).first()

            gl_code = ''
            if pa and pa.employee_gl_account:
                gl_code = pa.employee_gl_account.code
            elif dt:
                gl_code = dt.gl_account_code

            PayrollCalculationDetail.objects.create(
                payroll_calculation=calc,
                item_type='deduction',
                deduction_type=dt,
                payroll_account=pa,
                description=desc,
                amount=amount,
                is_taxable=False,
                is_pensionable=False,
                gl_account_code=gl_code or rate_type.upper(),
            )

    def _create_pension_details(self, calc, pension_result):
        """Create detail lines for third-party pension deductions."""
        for s in pension_result['schemes']:
            scheme = s['scheme']
            pa = s.get('payroll_account')

            # Employee contribution line
            if s['employee_amount'] > ZERO:
                gl_code = ''
                if pa and pa.employee_gl_account:
                    gl_code = pa.employee_gl_account.code

                PayrollCalculationDetail.objects.create(
                    payroll_calculation=calc,
                    item_type='deduction',
                    payroll_account=pa,
                    description=f"Pension - {scheme.name} (Employee)",
                    amount=s['employee_amount'],
                    is_taxable=False,
                    is_pensionable=False,
                    gl_account_code=gl_code or scheme.code,
                )

    def _create_deduction_details(self, calc, deductions):
        """Create detail lines for voluntary / loan deductions."""
        for d in deductions:
            pa = d.get('payroll_account')
            gl_code = d.get('gl_account_code', '')
            if pa and pa.employee_gl_account:
                gl_code = pa.employee_gl_account.code

            PayrollCalculationDetail.objects.create(
                payroll_calculation=calc,
                item_type='deduction',
                deduction_type=d.get('deduction_type'),
                payroll_account=pa,
                description=d['description'],
                amount=d['amount'],
                is_taxable=False,
                is_pensionable=False,
                gl_account_code=gl_code,
            )

    # ------------------------------------------------------------------
    # Period totals
    # ------------------------------------------------------------------
    def _update_period_totals(self):
        """Aggregate all calculations and update the PayrollPeriod."""
        from django.db.models import Sum, Count

        agg = PayrollCalculation.objects.filter(
            payroll_period=self.period
        ).aggregate(
            total_gross=Sum('gross_pay'),
            total_ded=Sum('total_deductions'),
            total_net=Sum('net_pay'),
            emp_count=Count('id'),
        )

        self.period.total_gross_pay = agg['total_gross'] or ZERO
        self.period.total_deductions = agg['total_ded'] or ZERO
        self.period.total_net_pay = agg['total_net'] or ZERO
        self.period.employee_count = agg['emp_count'] or 0
        self.period.status = 'calculated'
        self.period.processing_completed_at = timezone.now()
        self.period.save()

    # ------------------------------------------------------------------
    # Payroll Journal Integration
    # ------------------------------------------------------------------
    def _create_payroll_journals(self):
        """
        Create a consolidated payroll journal entry for the period.

        Double-entry structure:
          Debit  – Salary / earning expense accounts
          Credit – Deduction liability accounts (PAYE, NSSF, SHIF, etc.)
          Credit – Net Pay Payable
          Debit  – Employer contribution expense accounts
          Credit – Employer contribution liability accounts
        """
        from finance.models import Account

        lines = []

        # --- 1. Earning lines (Debit expense accounts) ---
        earning_details = PayrollCalculationDetail.objects.filter(
            payroll_calculation__payroll_period=self.period,
            item_type='earning',
        ).select_related('payroll_account__employee_gl_account')

        earnings_by_account = {}
        for detail in earning_details:
            account = self._resolve_detail_gl_account(detail)
            if not account:
                continue
            key = account.id
            if key not in earnings_by_account:
                earnings_by_account[key] = {
                    'account': account,
                    'amount': ZERO,
                    'descriptions': set(),
                }
            earnings_by_account[key]['amount'] += detail.amount
            earnings_by_account[key]['descriptions'].add(detail.description)

        for data in earnings_by_account.values():
            if data['amount'] > ZERO:
                desc = ', '.join(sorted(data['descriptions']))
                lines.append({
                    'account': data['account'],
                    'debit': data['amount'],
                    'credit': ZERO,
                    'description': desc[:255],
                })

        # --- 2. Deduction lines (Credit liability accounts) ---
        deduction_details = PayrollCalculationDetail.objects.filter(
            payroll_calculation__payroll_period=self.period,
            item_type='deduction',
        ).select_related('payroll_account__employee_gl_account')

        deductions_by_account = {}
        for detail in deduction_details:
            account = self._resolve_detail_gl_account(detail)
            if not account:
                continue
            key = account.id
            if key not in deductions_by_account:
                deductions_by_account[key] = {
                    'account': account,
                    'amount': ZERO,
                    'descriptions': set(),
                }
            deductions_by_account[key]['amount'] += detail.amount
            deductions_by_account[key]['descriptions'].add(detail.description)

        for data in deductions_by_account.values():
            if data['amount'] > ZERO:
                desc = ', '.join(sorted(data['descriptions']))
                lines.append({
                    'account': data['account'],
                    'debit': ZERO,
                    'credit': data['amount'],
                    'description': desc[:255],
                })

        # --- 3. Net Pay line (Credit net pay liability) ---
        net_pay_total = self.period.total_net_pay or ZERO
        if net_pay_total > ZERO:
            net_pay_account = self._get_gl_mapping_account('net_pay_liability')
            if net_pay_account:
                lines.append({
                    'account': net_pay_account,
                    'debit': ZERO,
                    'credit': net_pay_total,
                    'description': 'Net Salary Payable',
                })

        # --- 4. Employer contribution lines ---
        self._add_employer_journal_lines(lines)

        if not lines:
            self.errors.append(
                'No GL accounts configured — payroll journal not created.'
            )
            return

        # Create and post the journal entry
        journal_data = {
            'date': self.period.payment_date or self.period.end_date,
            'description': f'Payroll - {self.period.period_name}',
            'journal_type': 'GENERAL',
            'reference': f'PAYROLL-{self.period.period_name}',
            'lines': lines,
        }

        entry = JournalService.create_journal_entry(
            journal_data, user=self.processed_by
        )

        try:
            JournalService.post_journal_entry(entry)
        except Exception as e:
            self.errors.append(
                f'Payroll journal created but could not be posted: {str(e)}'
            )

    def _resolve_detail_gl_account(self, detail):
        """Resolve a finance.Account from a PayrollCalculationDetail."""
        from finance.models import Account

        # Priority 1: PayrollAccount FK → employee_gl_account
        if detail.payroll_account and detail.payroll_account.employee_gl_account:
            return detail.payroll_account.employee_gl_account

        # Priority 2: gl_account_code string → Account lookup
        if detail.gl_account_code:
            try:
                return Account.objects.get(code=detail.gl_account_code)
            except Account.DoesNotExist:
                pass

        return None

    def _get_gl_mapping_account(self, mapping_type):
        """Get a finance.Account from GLAccountMapping by type."""
        from finance.models import Account

        try:
            mapping = GLAccountMapping.objects.get(
                mapping_type=mapping_type,
                is_active=True,
            )
            return Account.objects.get(code=mapping.gl_account_code)
        except (GLAccountMapping.DoesNotExist, Account.DoesNotExist):
            return None

    def _add_employer_journal_lines(self, lines):
        """
        Add employer contribution debit/credit lines.

        For each employer contribution:
          Debit  – employer_gl_account (expense)
          Credit – employee_gl_account (liability)
        """
        from django.db.models import Sum

        # Aggregate employer amounts from calculations
        agg = PayrollCalculation.objects.filter(
            payroll_period=self.period,
        ).aggregate(
            total_pension_employer=Sum('pension_employer'),
            total_employer_cost=Sum('employer_cost'),
            total_gross_pay=Sum('gross_pay'),
        )

        total_pension_employer = agg['total_pension_employer'] or ZERO
        total_employer_cost = agg['total_employer_cost'] or ZERO
        total_gross_pay = agg['total_gross_pay'] or ZERO

        # Housing levy employer = employer_cost - gross_pay - pension_employer
        total_housing_levy_employer = (
            total_employer_cost - total_gross_pay - total_pension_employer
        )

        # Third-party pension employer from PensionContribution records
        total_third_party_pension = (
            PensionContribution.objects.filter(
                payroll_period=self.period,
            ).aggregate(total=Sum('employer_amount'))['total']
            or ZERO
        )

        # NSSF employer = pension_employer_total - third_party_pension_employer
        total_nssf_employer = total_pension_employer - total_third_party_pension

        # --- NSSF Employer ---
        if total_nssf_employer > ZERO:
            nssf_rate = self.statutory_rates.get('nssf_tier1')
            pa = nssf_rate.payroll_account if nssf_rate else None
            if pa and pa.employer_gl_account and pa.employee_gl_account:
                lines.append({
                    'account': pa.employer_gl_account,
                    'debit': total_nssf_employer,
                    'credit': ZERO,
                    'description': 'NSSF Employer Contribution',
                })
                lines.append({
                    'account': pa.employee_gl_account,
                    'debit': ZERO,
                    'credit': total_nssf_employer,
                    'description': 'NSSF Employer Contribution Payable',
                })

        # --- Housing Levy Employer ---
        if total_housing_levy_employer > ZERO:
            housing_rate = self.statutory_rates.get('housing_levy')
            pa = housing_rate.payroll_account if housing_rate else None
            if pa and pa.employer_gl_account and pa.employee_gl_account:
                lines.append({
                    'account': pa.employer_gl_account,
                    'debit': total_housing_levy_employer,
                    'credit': ZERO,
                    'description': 'Housing Levy Employer Contribution',
                })
                lines.append({
                    'account': pa.employee_gl_account,
                    'debit': ZERO,
                    'credit': total_housing_levy_employer,
                    'description': 'Housing Levy Employer Contribution Payable',
                })

        # --- Third-Party Pension Employer ---
        if total_third_party_pension > ZERO:
            pension_contribs = PensionContribution.objects.filter(
                payroll_period=self.period,
                employer_amount__gt=ZERO,
            ).select_related(
                'enrollment__pension_scheme__payroll_account__employee_gl_account',
                'enrollment__pension_scheme__payroll_account__employer_gl_account',
            )

            pension_by_pa = {}
            for pc in pension_contribs:
                pa = getattr(
                    pc.enrollment.pension_scheme, 'payroll_account', None
                )
                if not pa:
                    continue
                key = pa.id
                if key not in pension_by_pa:
                    pension_by_pa[key] = {'pa': pa, 'amount': ZERO}
                pension_by_pa[key]['amount'] += pc.employer_amount

            for data in pension_by_pa.values():
                pa = data['pa']
                amount = data['amount']
                if (
                    amount > ZERO
                    and pa.employer_gl_account
                    and pa.employee_gl_account
                ):
                    lines.append({
                        'account': pa.employer_gl_account,
                        'debit': amount,
                        'credit': ZERO,
                        'description': f'Pension Employer - {pa.name}',
                    })
                    lines.append({
                        'account': pa.employee_gl_account,
                        'debit': ZERO,
                        'credit': amount,
                        'description': f'Pension Employer Payable - {pa.name}',
                    })
