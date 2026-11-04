"""
Verification Script: HR & Payroll Milestone 1 - Backend Schema & Document Studio Integration
Verifies:
1. Models: Employee statutory & bank fields, EmployeeContract model creation and validation.
2. Document Studio Integration: DocumentTemplate.Category has PAYSLIP, EMPLOYMENT_CONTRACT, P9_FORM.
3. WeasyPrint Document Generation:
   - Payslip generation (PayslipDataProvider) -> PDF blob > 0 bytes
   - Contract generation (EmployeeContractDataProvider) -> PDF blob > 0 bytes
   - P9 Tax Deduction Card generation (P9FormDataProvider) -> PDF blob > 0 bytes
4. APIClient HTTP Tests:
   - GET /api/workforce/documents/payslip/{id}/ -> 200 OK & Content-Type: application/pdf
   - GET /api/workforce/documents/contract/{id}/ -> 200 OK & Content-Type: application/pdf
   - GET /api/workforce/documents/p9/{id}/?year=2026 -> 200 OK & Content-Type: application/pdf
5. Currency check: No hardcoded $ symbol in generated documents, uses tenant configured currency.
"""
import os
import sys
from decimal import Decimal
import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, 'apps'))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

import django
django.setup()

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from django_tenants.test.client import BaseTenantRequestFactory
from django_tenants.utils import schema_context

from tenants.models import Client
from documents.models import DocumentTemplate
from documents.services.document_generator import DocumentGeneratorService
from workforce.core_models import Employee, EmployeeContract
# pyrefly: ignore[missing-import]
from workforce.models import (
    Department, JobGrade, JobTitle, PayrollPeriod, PayrollCalculation,
    PayrollCalculationDetail, EarningType, DeductionType
)
from workforce.documents.payslip import PayslipDataProvider
from workforce.documents.contract import EmployeeContractDataProvider
from workforce.documents.p9_form import P9FormDataProvider

User = get_user_model()


class TenantAPIClient(BaseTenantRequestFactory, APIClient):
    def generic(self, *args, **kwargs):
        if "HTTP_HOST" not in kwargs:
            try:
                domain_obj = self.tenant.domains.filter(is_primary=True).first() or self.tenant.domains.first()
                kwargs["HTTP_HOST"] = domain_obj.domain if domain_obj else f"{self.tenant.schema_name}.localhost"
            except Exception:
                kwargs["HTTP_HOST"] = f"{self.tenant.schema_name}.localhost"
        request = super().generic(*args, **kwargs)
        request.tenant = self.tenant
        return request


def run_milestone1_verification():
    print("=" * 80)
    print("FAHARI ACADEMIA - HR & PAYROLL MILESTONE 1 VERIFICATION")
    print("Backend Schema & Document Studio Integration")
    print("=" * 80)

    passed_tests = 0
    total_tests = 0

    def assert_true(condition, test_name, extra=""):
        nonlocal passed_tests, total_tests
        total_tests += 1
        if condition:
            passed_tests += 1
            print(f"  [PASS] {test_name} {extra}")
        else:
            print(f"  [FAIL] {test_name} {extra}")

    # 1. Verify Enum Categories in DocumentTemplate
    print("\n--- 1. Document Studio Template Categories ---")
    categories = [choice[0] for choice in DocumentTemplate.Category.choices]
    assert_true("payslip" in categories, "Category 'PAYSLIP' exists in DocumentTemplate.Category")
    assert_true("employment_contract" in categories, "Category 'EMPLOYMENT_CONTRACT' exists in DocumentTemplate.Category")
    assert_true("p9_form" in categories, "Category 'P9_FORM' exists in DocumentTemplate.Category")

    # 2. Multi-Tenant Context Setup
    tenant = Client.objects.filter(schema_name='demo_school').first() or Client.objects.exclude(schema_name='public').first()
    if not tenant:
        print("ERROR: No valid tenant found in database.")
        sys.exit(1)

    print(f"\nActive Tenant: {tenant.name} ({tenant.schema_name})")

    with schema_context(tenant.schema_name):
        client = TenantAPIClient(tenant)

        # Admin user for API authentication
        admin_user, _ = User.objects.get_or_create(
            username="hr_director_test",
            defaults={"email": "hr@fahari.ac.ke", "is_staff": True, "is_superuser": True}
        )
        client.force_authenticate(user=admin_user)

        # Ensure Department & JobTitle
        dept, _ = Department.objects.get_or_create(
            name="Academic Sciences",
            defaults={"code": "SCI-01"}
        )
        job_title, _ = JobTitle.objects.get_or_create(
            title="Senior Lecturer in Physics",
            defaults={"department": dept}
        )

        # --- 2. Model Test: Employee with Statutory & Bank Details ---
        print("\n--- 2. Employee Statutory & Bank Details Schema ---")
        emp_no = "EMP-TEST-2026-M1"
        emp, created = Employee.objects.update_or_create(
            employee_no=emp_no,
            defaults={
                "first_name": "Dr. Caroline",
                "last_name": "Mwangi",
                "gender": Employee.Gender.FEMALE,
                "date_of_birth": datetime.date(1985, 4, 12),
                "national_id": "ID-29384756",
                "personal_email": "caroline.mwangi@example.com",
                "official_email": "c.mwangi@fahari.ac.ke",
                "phone_primary": "+254712345678",
                "employee_category": Employee.EmployeeCategory.TEACHING,
                "payroll_type": Employee.PayrollType.MONTHLY,
                "employment_status": Employee.EmploymentStatus.ACTIVE,
                "hire_date": datetime.date(2022, 1, 10),
                "department": dept,
                # New Statutory & Bank Details
                "kra_pin": "A001234567Z",
                "nssf_number": "NSSF-98765432",
                "nhif_number": "SHIF-12345678",
                "bank_name": "Kenya Commercial Bank",
                "bank_branch": "Kilimani Branch",
                "bank_account_name": "Caroline Mwangi",
                "bank_account_number": "1122334455",
            }
        )

        assert_true(emp.kra_pin == "A001234567Z", "Employee kra_pin field saved correctly")
        assert_true(emp.nssf_number == "NSSF-98765432", "Employee nssf_number field saved correctly")
        assert_true(emp.nhif_number == "SHIF-12345678", "Employee nhif_number field saved correctly")
        assert_true(emp.bank_name == "Kenya Commercial Bank", "Employee bank_name field saved correctly")
        assert_true(emp.bank_account_number == "1122334455", "Employee bank_account_number saved correctly")

        # --- 3. Model Test: EmployeeContract Creation ---
        print("\n--- 3. EmployeeContract Model Creation ---")
        contract, _ = EmployeeContract.objects.update_or_create(
            employee=emp,
            contract_type=EmployeeContract.ContractType.PERMANENT,
            defaults={
                "start_date": datetime.date(2026, 1, 1),
                "end_date": None, # permanent
                "gross_salary": Decimal("185000.00"),
                "status": EmployeeContract.Status.ACTIVE,
            }
        )

        assert_true(contract.id is not None, "EmployeeContract record created successfully", f"(ID: {contract.id})")
        assert_true(contract.gross_salary == Decimal("185000.00"), "EmployeeContract gross_salary matches Decimal(185000.00)")
        assert_true(contract.contract_type == "permanent", "EmployeeContract type is permanent")
        assert_true(contract.status == "active", "EmployeeContract status is active")

        # --- 4. Payroll Calculation Setup ---
        print("\n--- 4. Payroll Calculation Setup ---")
        period, _ = PayrollPeriod.objects.get_or_create(
            period_name="January 2026",
            defaults={
                "period_type": PayrollPeriod.PeriodType.MONTHLY,
                "start_date": datetime.date(2026, 1, 1),
                "end_date": datetime.date(2026, 1, 31),
                "payment_date": datetime.date(2026, 1, 30),
                "status": PayrollPeriod.Status.CALCULATED,
            }
        )

        calc, _ = PayrollCalculation.objects.update_or_create(
            employee=emp,
            payroll_period=period,
            defaults={
                "basic_salary": Decimal("150000.00"),
                "total_earnings": Decimal("185000.00"),
                "total_allowances": Decimal("35000.00"),
                "gross_pay": Decimal("185000.00"),
                "taxable_income": Decimal("182840.00"),
                "tax_amount": Decimal("38200.00"),
                "pension_employee": Decimal("2160.00"),
                "pension_employer": Decimal("2160.00"),
                "total_statutory_deductions": Decimal("46360.00"),
                "total_deductions": Decimal("46360.00"),
                "net_pay": Decimal("138640.00"),
                "employer_cost": Decimal("187160.00"),
                "payment_method": PayrollCalculation.PaymentMethod.BANK_TRANSFER,
                "bank_account_number": emp.bank_account_number,
                "payment_status": PayrollCalculation.PaymentStatus.PAID,
            }
        )

        # Clear old details and create fresh line items
        calc.details.all().delete()
        PayrollCalculationDetail.objects.create(
            payroll_calculation=calc,
            item_type="earning",
            description="Basic Salary",
            amount=Decimal("150000.00"),
            is_taxable=True,
            gl_account_code="6001"
        )
        PayrollCalculationDetail.objects.create(
            payroll_calculation=calc,
            item_type="earning",
            description="House Allowance",
            amount=Decimal("35000.00"),
            is_taxable=True,
            gl_account_code="6002"
        )
        PayrollCalculationDetail.objects.create(
            payroll_calculation=calc,
            item_type="deduction",
            description="N.S.S.F. (Tier I & II)",
            amount=Decimal("2160.00"),
            gl_account_code="2001"
        )
        PayrollCalculationDetail.objects.create(
            payroll_calculation=calc,
            item_type="deduction",
            description="S.H.I.F. (Social Health)",
            amount=Decimal("5000.00"),
            gl_account_code="2002"
        )
        PayrollCalculationDetail.objects.create(
            payroll_calculation=calc,
            item_type="deduction",
            description="P.A.Y.E. (Income Tax)",
            amount=Decimal("38200.00"),
            gl_account_code="2003"
        )
        PayrollCalculationDetail.objects.create(
            payroll_calculation=calc,
            item_type="deduction",
            description="Affordable Housing Levy",
            amount=Decimal("2775.00"),
            gl_account_code="2004"
        )

        assert_true(calc.details.count() == 6, "PayrollCalculationDetail lines populated (6 items)")

        # --- 5. WeasyPrint Direct Rendering Engine Tests ---
        print("\n--- 5. WeasyPrint Document Generator Tests ---")
        output_dir = os.path.join(BASE_DIR, "test_output")
        os.makedirs(output_dir, exist_ok=True)

        # A. Payslip Provider
        payslip_provider = PayslipDataProvider(calc)
        payslip_pdf = DocumentGeneratorService.generate_pdf(payslip_provider)
        payslip_path = os.path.join(output_dir, "test_payslip.pdf")
        with open(payslip_path, "wb") as f:
            f.write(payslip_pdf)
        
        assert_true(len(payslip_pdf) > 1000, "Payslip PDF generated via WeasyPrint", f"({len(payslip_pdf):,} bytes -> {payslip_path})")
        assert_true(payslip_pdf.startswith(b"%PDF"), "Payslip binary is a valid PDF")

        # B. Contract Provider
        contract_provider = EmployeeContractDataProvider(contract)
        contract_pdf = DocumentGeneratorService.generate_pdf(contract_provider)
        contract_path = os.path.join(output_dir, "test_contract.pdf")
        with open(contract_path, "wb") as f:
            f.write(contract_pdf)

        assert_true(len(contract_pdf) > 1000, "Employment Contract PDF generated via WeasyPrint", f"({len(contract_pdf):,} bytes -> {contract_path})")
        assert_true(contract_pdf.startswith(b"%PDF"), "Contract binary is a valid PDF")

        # C. P9 Form Provider
        p9_provider = P9FormDataProvider(emp, context={"year": 2026})
        p9_pdf = DocumentGeneratorService.generate_pdf(p9_provider)
        p9_path = os.path.join(output_dir, "test_p9_form.pdf")
        with open(p9_path, "wb") as f:
            f.write(p9_pdf)

        assert_true(len(p9_pdf) > 1000, "KRA P9 Form PDF generated via WeasyPrint", f"({len(p9_pdf):,} bytes -> {p9_path})")
        assert_true(p9_pdf.startswith(b"%PDF"), "P9 binary is a valid PDF")

        # --- 6. DRF APIClient HTTP Endpoint Tests ---
        print("\n--- 6. DRF APIClient HTTP Endpoint Verification ---")

        # A. GET /api/workforce/documents/payslip/{calculation_id}/
        url_payslip = f"/api/workforce/documents/payslip/{calc.id}/"
        res_payslip = client.get(url_payslip)
        assert_true(
            res_payslip.status_code == 200,
            f"GET {url_payslip} returned 200 OK",
            f"(Status: {res_payslip.status_code})"
        )
        assert_true(
            res_payslip.get('Content-Type') == 'application/pdf',
            "GET payslip Content-Type is 'application/pdf'",
            f"({res_payslip.get('Content-Type')})"
        )
        assert_true(
            len(res_payslip.content) > 1000,
            "GET payslip body returns genuine binary PDF blob",
            f"({len(res_payslip.content):,} bytes)"
        )

        # B. GET /api/workforce/documents/contract/{contract_id}/
        url_contract = f"/api/workforce/documents/contract/{contract.id}/"
        res_contract = client.get(url_contract)
        assert_true(
            res_contract.status_code == 200,
            f"GET {url_contract} returned 200 OK",
            f"(Status: {res_contract.status_code})"
        )
        assert_true(
            res_contract.get('Content-Type') == 'application/pdf',
            "GET contract Content-Type is 'application/pdf'",
            f"({res_contract.get('Content-Type')})"
        )
        assert_true(
            len(res_contract.content) > 1000,
            "GET contract body returns genuine binary PDF blob",
            f"({len(res_contract.content):,} bytes)"
        )

        # C. GET /api/workforce/documents/p9/{employee_id}/?year=2026
        url_p9 = f"/api/workforce/documents/p9/{emp.id}/?year=2026"
        res_p9 = client.get(url_p9)
        assert_true(
            res_p9.status_code == 200,
            f"GET {url_p9} returned 200 OK",
            f"(Status: {res_p9.status_code})"
        )
        assert_true(
            res_p9.get('Content-Type') == 'application/pdf',
            "GET P9 Form Content-Type is 'application/pdf'",
            f"({res_p9.get('Content-Type')})"
        )
        assert_true(
            len(res_p9.content) > 1000,
            "GET P9 Form body returns genuine binary PDF blob",
            f"({len(res_p9.content):,} bytes)"
        )

        # --- 7. Currency Check ---
        print("\n--- 7. Currency Formatting Check ---")
        payslip_html = payslip_provider.render_body_html(payslip_provider.get_context_data())
        assert_true("KES" in payslip_html, "Payslip HTML contains tenant currency 'KES'")
        assert_true("$" not in payslip_html, "Payslip HTML contains no hardcoded '$' symbols")

        contract_html = contract_provider.render_body_html(contract_provider.get_context_data())
        assert_true("KES" in contract_html, "Contract HTML contains tenant currency 'KES'")
        assert_true("$" not in contract_html, "Contract HTML contains no hardcoded '$' symbols")

    print("\n" + "=" * 80)
    print(f"VERIFICATION SUMMARY: {passed_tests}/{total_tests} TESTS PASSED")
    print("=" * 80)

    if passed_tests == total_tests:
        print("\nALL MILESTONE 1 CHECKS COMPLETED SUCCESSFULLY!")
        return True
    else:
        print("\nSOME CHECKS FAILED.")
        return False


if __name__ == "__main__":
    success = run_milestone1_verification()
    sys.exit(0 if success else 1)
