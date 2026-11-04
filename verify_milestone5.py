"""
Milestone 5 Verification Script: Approvals, Reporting & Audit Trail.
Tests all Milestone 5 capabilities via DRF APIClient and Django ORM:
1. Budget Planning Approval & Rejection (transitions, line locking, audit log)
2. Budget Adjustment Approval & Rejection (permission enforcement, factor locking, audit log)
3. Audit Trail Logging (append-only, capturing user, action, timestamp, states)
4. Reporting Engine Exports:
   - Budget vs. Actual Statement (WeasyPrint PDF & openpyxl Excel)
   - Adjustment History Audit Report (WeasyPrint PDF & openpyxl Excel)
   - Reporting Metadata Telemetry
5. Pending Approvals Queue API
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
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from rest_framework.test import APIClient
from django_tenants.test.client import BaseTenantRequestFactory
from django_tenants.utils import schema_context

from tenants.models import Client, Domain
from budgets.models import (
    Budget,
    BudgetLine,
    BudgetStatus,
    BudgetAdjustmentStatus,
    BudgetAdjustmentHistory,
    BudgetAuditAction,
    BudgetAuditLog,
)
from finance.models import Account, AccountType, AccountSubType

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


def run_milestone5_verification():
    print("=" * 80)
    print("FAHARI ACADEMIA - MILESTONE 5 VERIFICATION: APPROVALS, REPORTING & AUDIT TRAIL")
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

    tenant = Client.objects.filter(schema_name='demo_school').first() or Client.objects.exclude(schema_name='public').first()
    if not tenant:
        print("ERROR: No valid tenant found in database.")
        sys.exit(1)

    print(f"Active Tenant: {tenant.name} ({tenant.schema_name})")

    with schema_context(tenant.schema_name):
        client = TenantAPIClient(tenant)

        # 0. FIXTURES SETUP
        admin_user, _ = User.objects.get_or_create(
            username="m5_cfo_admin",
            defaults={"email": "cfo@fahari.ac.ke", "is_staff": True, "is_superuser": True}
        )

        officer_user, _ = User.objects.get_or_create(
            username="m5_finance_officer",
            defaults={"email": "officer@fahari.ac.ke", "is_staff": False, "is_superuser": False}
        )

        # Accounts
        acc_teaching, _ = Account.objects.get_or_create(
            code="5001-M5",
            defaults={
                "name": "Teaching Materials",
                "type": AccountType.EXPENSE,
                "sub_type": AccountSubType.TEACHING_EXPENSES
            }
        )
        acc_utilities, _ = Account.objects.get_or_create(
            code="5002-M5",
            defaults={
                "name": "Utilities & Power",
                "type": AccountType.EXPENSE,
                "sub_type": AccountSubType.UTILITIES
            }
        )

        test_year = 2026

        # Clean existing test budgets for isolation
        Budget.objects.filter(name__startswith="M5 Test Budget").delete()

        # ─────────────────────────────────────────────────────────────────────
        # 1. BUDGET PLANNING APPROVAL WORKFLOW
        # ─────────────────────────────────────────────────────────────────────
        print("\n--- 1. BUDGET PLANNING APPROVAL & REJECTION WORKFLOW ---")

        # 1.1 Create Budget in PENDING_APPROVAL status
        budget_approval = Budget.objects.create(
            name="M5 Test Budget Approval 2026",
            fiscal_year=test_year,
            start_date=datetime.date(test_year, 1, 1),
            end_date=datetime.date(test_year, 12, 31),
            status=BudgetStatus.PENDING_APPROVAL,
            description="Formulated draft submitted for board sign-off."
        )
        line1 = BudgetLine.objects.create(
            budget=budget_approval,
            account=acc_teaching,
            amount=Decimal("450000.00"),
            original_budget=Decimal("0.00"),
            controlled_budget=Decimal("0.00"),
            category_rule="flexible"
        )
        line2 = BudgetLine.objects.create(
            budget=budget_approval,
            account=acc_utilities,
            amount=Decimal("250000.00"),
            original_budget=Decimal("0.00"),
            controlled_budget=Decimal("0.00"),
            category_rule="fixed"
        )

        # Test Pending Approvals List API
        client.force_authenticate(user=admin_user)
        resp_pending = client.get(f"/api/finance/budgeting/approvals/pending/?fiscal_year={test_year}")
        assert_true(resp_pending.status_code == 200, "GET /api/finance/budgeting/approvals/pending/ returns 200 OK")
        data_p = resp_pending.json()
        pending_ids = [b['id'] for b in data_p.get('pending_budgets', [])]
        assert_true(budget_approval.id in pending_ids, "Pending approvals queue lists the submitted budget")

        # 1.2 Approve Budget via POST /api/finance/budgeting/planning/{id}/approve/
        resp_approve = client.post(
            f"/api/finance/budgeting/planning/{budget_approval.id}/approve/",
            {"notes": "Ratified by Board of Management."}
        )
        assert_true(resp_approve.status_code == 200, f"POST /api/finance/budgeting/planning/{budget_approval.id}/approve/ returns 200 OK")
        
        # Verify budget status transition
        budget_approval.refresh_from_db()
        assert_true(budget_approval.status == BudgetStatus.APPROVED, "Budget status transitioned from 'pending_approval' to 'approved'")

        # Verify BudgetLine proposed_budget locked into original_budget & controlled_budget
        line1.refresh_from_db()
        line2.refresh_from_db()
        assert_true(line1.original_budget == Decimal("450000.00") and line1.controlled_budget == Decimal("450000.00"),
                    "BudgetLine 1 proposed_budget locked into original_budget and controlled_budget")
        assert_true(line2.original_budget == Decimal("250000.00") and line2.controlled_budget == Decimal("250000.00"),
                    "BudgetLine 2 proposed_budget locked into original_budget and controlled_budget")

        # Verify Audit Log entry was created
        audit_entry = BudgetAuditLog.objects.filter(
            budget=budget_approval,
            action=BudgetAuditAction.APPROVED
        ).first()
        assert_true(audit_entry is not None, "BudgetAuditLog entry recorded for budget approval")
        if audit_entry:
            assert_true(audit_entry.previous_state == BudgetStatus.PENDING_APPROVAL and audit_entry.new_state == BudgetStatus.APPROVED,
                        "BudgetAuditLog correctly tracks previous_state and new_state")
            assert_true(audit_entry.user == admin_user, "BudgetAuditLog correctly tracks approving user")

        # 1.3 Test Budget Planning Rejection
        budget_reject = Budget.objects.create(
            name="M5 Test Budget Reject 2026",
            fiscal_year=test_year,
            start_date=datetime.date(test_year, 1, 1),
            end_date=datetime.date(test_year, 12, 31),
            status=BudgetStatus.PENDING_APPROVAL,
            description="Budget with unrealistic projections."
        )
        resp_reject = client.post(
            f"/api/finance/budgeting/planning/{budget_reject.id}/reject/",
            {"reason": "Exceeds anticipated fee collection by 35%."}
        )
        assert_true(resp_reject.status_code == 200, f"POST /api/finance/budgeting/planning/{budget_reject.id}/reject/ returns 200 OK")
        budget_reject.refresh_from_db()
        assert_true(budget_reject.status == BudgetStatus.REJECTED, "Budget status transitioned to 'rejected'")
        reject_audit = BudgetAuditLog.objects.filter(budget=budget_reject, action=BudgetAuditAction.REJECTED).first()
        assert_true(reject_audit is not None and "Exceeds" in reject_audit.details.get('rejection_reason', ''),
                    "BudgetAuditLog records rejection reason notes")

        # ─────────────────────────────────────────────────────────────────────
        # 2. BUDGET ADJUSTMENT APPROVAL WORKFLOW & PERMISSIONS
        # ─────────────────────────────────────────────────────────────────────
        print("\n--- 2. BUDGET ADJUSTMENT APPROVAL WORKFLOW & PERMISSIONS ---")

        # Setup Budget with Austerity reduction
        budget_adj = Budget.objects.create(
            name="M5 Test Budget Austerity 2026",
            fiscal_year=test_year,
            start_date=datetime.date(test_year, 1, 1),
            end_date=datetime.date(test_year, 12, 31),
            status=BudgetStatus.APPROVED,
            adjustment_status=BudgetAdjustmentStatus.PENDING_REVIEW,
            adjustment_factor=Decimal("0.8500")
        )
        line_adj = BudgetLine.objects.create(
            budget=budget_adj,
            account=acc_teaching,
            amount=Decimal("100000.00"),
            original_budget=Decimal("100000.00"),
            controlled_budget=Decimal("85000.00"),
            category_rule="flexible"
        )
        adj_history = BudgetAdjustmentHistory.objects.create(
            budget=budget_adj,
            previous_factor=Decimal("1.0000"),
            new_factor=Decimal("0.8500"),
            projected_income=Decimal("1000000.00"),
            actual_income=Decimal("850000.00"),
            total_reduction=Decimal("15000.00"),
            trigger_reason="Term 1 collection shortfall of 15%."
        )

        # 2.1 Permission Enforcement: Officer without permission gets 403 Forbidden
        client.force_authenticate(user=officer_user)
        resp_unauth = client.post(f"/api/finance/budgeting/adjustments/{adj_history.id}/approve/", {"notes": "Unauthorized attempt"})
        assert_true(resp_unauth.status_code == 403, "Non-authorized user receives 403 Forbidden on adjustment approval")

        # 2.2 Grant specific permission or use executive CFO
        client.force_authenticate(user=admin_user)
        resp_adj_app = client.post(
            f"/api/finance/budgeting/adjustments/{adj_history.id}/approve/",
            {"notes": "Ratified by Board Finance Committee."}
        )
        assert_true(resp_adj_app.status_code == 200, f"POST /api/finance/budgeting/adjustments/{adj_history.id}/approve/ returns 200 OK")
        
        budget_adj.refresh_from_db()
        adj_history.refresh_from_db()
        assert_true(budget_adj.adjustment_status == BudgetAdjustmentStatus.REDUCED,
                    "Budget adjustment_status transitioned to 'reduced'")
        assert_true(adj_history.approved_by == admin_user,
                    "BudgetAdjustmentHistory records approving executive user")

        adj_audit = BudgetAuditLog.objects.filter(budget=budget_adj, action=BudgetAuditAction.ADJUSTED).first()
        assert_true(adj_audit is not None, "BudgetAuditLog recorded for adjustment approval")
        if adj_audit:
            assert_true(adj_audit.details.get('factor') == 0.85, "BudgetAuditLog records adjustment multiplier factor")

        # 2.3 Test Adjustment Rejection / Baseline Restoration
        budget_adj_rev = Budget.objects.create(
            name="M5 Test Budget Revert 2026",
            fiscal_year=test_year,
            start_date=datetime.date(test_year, 1, 1),
            end_date=datetime.date(test_year, 12, 31),
            status=BudgetStatus.APPROVED,
            adjustment_status=BudgetAdjustmentStatus.PENDING_REVIEW,
            adjustment_factor=Decimal("0.8000")
        )
        line_rev = BudgetLine.objects.create(
            budget=budget_adj_rev,
            account=acc_teaching,
            amount=Decimal("100000.00"),
            original_budget=Decimal("100000.00"),
            controlled_budget=Decimal("80000.00"),
            category_rule="flexible"
        )
        resp_adj_rej = client.post(
            f"/api/finance/budgeting/adjustments/{budget_adj_rev.id}/reject/",
            {"reason": "Bridge loan secured; austerity reduction rescinded."}
        )
        assert_true(resp_adj_rej.status_code == 200, "POST /api/finance/budgeting/adjustments/{id}/reject/ returns 200 OK")
        budget_adj_rev.refresh_from_db()
        line_rev.refresh_from_db()
        assert_true(budget_adj_rev.adjustment_factor == Decimal("1.0000"), "Adjustment factor restored to 1.0000 baseline")
        assert_true(budget_adj_rev.adjustment_status == BudgetAdjustmentStatus.NORMAL, "Adjustment status restored to 'normal'")
        assert_true(line_rev.controlled_budget == Decimal("100000.00"), "BudgetLine controlled_budget restored to 100% baseline")

        # ─────────────────────────────────────────────────────────────────────
        # 3. REPORTING ENGINE EXPORTS: PDF & EXCEL
        # ─────────────────────────────────────────────────────────────────────
        print("\n--- 3. REPORTING & EXPORT ENGINE (WEASYPRINT PDF & OPENPYXL EXCEL) ---")

        # 3.1 Budget vs. Actual Report - PDF (WeasyPrint)
        resp_bva_pdf = client.get(f"/api/finance/budgeting/reports/budget-vs-actual/?year={test_year}&format=pdf")
        print(f"DEBUG resp_bva_pdf: status={resp_bva_pdf.status_code}, content={resp_bva_pdf.content[:150]}")
        assert_true(resp_bva_pdf.status_code == 200, "GET /reports/budget-vs-actual/?format=pdf returns 200 OK")
        assert_true("application/pdf" in resp_bva_pdf['Content-Type'], "PDF export has Content-Type 'application/pdf'")
        assert_true(resp_bva_pdf.content.startswith(b'%PDF-'), "PDF export content contains valid %PDF- binary header")
        assert_true(len(resp_bva_pdf.content) > 1000, f"Generated PDF has substantial payload ({len(resp_bva_pdf.content)} bytes)")

        # 3.2 Budget vs. Actual Report - Excel (openpyxl)
        resp_bva_xlsx = client.get(f"/api/finance/budgeting/reports/budget-vs-actual/?year={test_year}&format=xlsx")
        assert_true(resp_bva_xlsx.status_code == 200, "GET /reports/budget-vs-actual/?format=xlsx returns 200 OK")
        assert_true("spreadsheetml.sheet" in resp_bva_xlsx['Content-Type'], "Excel export has openxml spreadsheet Content-Type")
        assert_true(resp_bva_xlsx.content.startswith(b'PK\x03\x04'), "Excel export content has valid XLSX PK zip header")
        assert_true(len(resp_bva_xlsx.content) > 1000, f"Generated XLSX has substantial payload ({len(resp_bva_xlsx.content)} bytes)")

        # 3.3 Adjustment History Report - PDF
        resp_adj_pdf = client.get(f"/api/finance/budgeting/reports/adjustments/?year={test_year}&format=pdf")
        assert_true(resp_adj_pdf.status_code == 200, "GET /reports/adjustments/?format=pdf returns 200 OK")
        assert_true(resp_adj_pdf.content.startswith(b'%PDF-'), "Adjustment History PDF has valid %PDF- binary header")

        # 3.4 Adjustment History Report - Excel
        resp_adj_xlsx = client.get(f"/api/finance/budgeting/reports/adjustments/?year={test_year}&format=xlsx")
        assert_true(resp_adj_xlsx.status_code == 200, "GET /reports/adjustments/?format=xlsx returns 200 OK")
        assert_true(resp_adj_xlsx.content.startswith(b'PK\x03\x04'), "Adjustment History XLSX has valid PK zip header")

        # 3.5 Reports Metadata API
        resp_meta = client.get(f"/api/finance/budgeting/reports/metadata/?year={test_year}")
        assert_true(resp_meta.status_code == 200, "GET /reports/metadata/ returns 200 OK")
        meta_json = resp_meta.json()
        assert_true("budget_vs_actual" in meta_json and "adjustments" in meta_json, "Reports metadata provides cards telemetry")

        # Clean up test records
        Budget.objects.filter(name__startswith="M5 Test Budget").delete()

    print("\n" + "=" * 80)
    print(f"VERIFICATION COMPLETE: {passed_tests} / {total_tests} Tests Passed")
    print("=" * 80)
    if passed_tests == total_tests:
        print(">>> ALL MILESTONE 5 BACKEND CAPABILITIES VERIFIED SUCCESSFULLY <<<")
        return 0
    else:
        print(">>> SOME TESTS FAILED <<<")
        return 1


if __name__ == "__main__":
    exit_code = run_milestone5_verification()
    sys.exit(exit_code)
