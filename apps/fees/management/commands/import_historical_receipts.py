"""
fees/management/commands/import_historical_receipts.py
======================================================
CLI Management Command to import historical & implementation receipts.

Usage examples:
  # 1. Generate a sample CSV template:
  python manage.py import_historical_receipts --generate-template sample_receipts.csv

  # 2. Run a pre-flight dry-run validation (no DB changes):
  python manage.py import_historical_receipts --file /path/to/receipts.csv --tenant school1 --dry-run

  # 3. Commit receipts to DB and post to General Ledger:
  python manage.py import_historical_receipts --file /path/to/receipts.csv --tenant school1

  # 4. Commit receipts without GL posting (student sub-ledger only):
  python manage.py import_historical_receipts --file /path/to/receipts.csv --tenant school1 --no-gl
"""

import os
import sys
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from fees.receipt_migration_engine import HistoricalReceiptMigrationEngine


class Command(BaseCommand):
    help = "Bulk import historical and implementation receipts from CSV or Excel file."

    def add_arguments(self, parser):
        parser.add_argument(
            '--file', '-f',
            type=str,
            help="Path to the Excel (.xlsx/.xls) or CSV (.csv) file to import."
        )
        parser.add_argument(
            '--tenant', '-t',
            type=str,
            default=None,
            help="Tenant schema name (e.g. 'school1'). If omitted, resolves from active tenants."
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Simulate the import and validation without making any database changes."
        )
        parser.add_argument(
            '--no-gl',
            action='store_true',
            help="Skip General Ledger double-entry journal postings (sub-ledger only)."
        )
        parser.add_argument(
            '--no-allocate',
            action='store_true',
            help="Do not auto-allocate to open invoices (leaves all receipts as prepayments)."
        )
        parser.add_argument(
            '--user',
            type=str,
            default=None,
            help="Username of user recording these receipts (defaults to first superuser)."
        )
        parser.add_argument(
            '--generate-template',
            type=str,
            help="Generate a blank template CSV file at the specified path and exit."
        )

    def handle(self, *args, **options):
        # 1. Handle template generation request
        template_path = options.get('generate_template')
        if template_path:
            csv_content = HistoricalReceiptMigrationEngine.generate_template_csv()
            try:
                with open(template_path, 'w', encoding='utf-8') as f:
                    f.write(csv_content)
                self.stdout.write(
                    self.style.SUCCESS(f"[OK] Sample receipt template successfully created at: {template_path}")
                )
                return
            except Exception as e:
                raise CommandError(f"Failed to write template to {template_path}: {e}")

        # 2. Validate file argument
        file_path = options.get('file')
        if not file_path:
            raise CommandError("Please specify a file to import using --file <path> or generate a template with --generate-template <path>.")

        if not os.path.exists(file_path):
            raise CommandError(f"File not found: {file_path}")

        # 3. Resolve Tenant Schema
        tenant_schema = options.get('tenant')
        try:
            from tenants.models import Client
            from django_tenants.utils import get_public_schema_name
            public_schema = get_public_schema_name()
            valid_tenants = list(Client.objects.exclude(schema_name=public_schema).values_list('schema_name', flat=True))

            if tenant_schema:
                if tenant_schema not in valid_tenants:
                    raise CommandError(
                        f"Tenant schema '{tenant_schema}' not found. Available tenant schemas: {', '.join(valid_tenants)}"
                    )
            else:
                if valid_tenants:
                    tenant_schema = valid_tenants[0]
                    self.stdout.write(
                        self.style.WARNING(f"No --tenant specified. Defaulting to first active tenant schema: '{tenant_schema}'")
                    )
        except CommandError:
            raise
        except Exception:
            pass

        # 4. Resolve User
        user = None
        User = get_user_model()
        user_name = options.get('user')
        if user_name:
            user = User.objects.filter(username=user_name).first()
            if not user:
                self.stdout.write(self.style.WARNING(f"User '{user_name}' not found. Falling back to system superuser."))

        if not user:
            user = User.objects.filter(is_superuser=True).first() or User.objects.first()

        dry_run = options.get('dry_run', False)
        post_to_gl = not options.get('no_gl', False)
        auto_allocate = not options.get('no_allocate', False)

        # 5. Display banner
        mode_str = "PRE-FLIGHT DRY-RUN (SIMULATION ONLY)" if dry_run else "LIVE MIGRATION (DATABASE COMMIT)"
        self.stdout.write("=" * 70)
        self.stdout.write(self.style.MIGRATE_HEADING(" Fahari Academia ERP - Historical Receipt Migration"))
        self.stdout.write("=" * 70)
        self.stdout.write(f" Mode:           {self.style.NOTICE(mode_str)}")
        self.stdout.write(f" File:           {file_path}")
        self.stdout.write(f" Tenant Schema:  {tenant_schema or 'public'}")
        self.stdout.write(f" Operator:       {user.username if user else 'System'}")
        self.stdout.write(f" Post to GL:     {'Yes (Cashbook & Trial Balance)' if post_to_gl else 'No (Sub-ledger only)'}")
        self.stdout.write(f" Auto-Allocate:  {'Yes (FIFO Invoice Clearance)' if auto_allocate else 'No (Prepayment only)'}")
        self.stdout.write("-" * 70)

        # 6. Initialize & Run Engine
        engine = HistoricalReceiptMigrationEngine(
            file_obj=file_path,
            tenant_schema=tenant_schema,
            user=user,
            dry_run=dry_run,
            post_to_gl=post_to_gl,
            auto_allocate=auto_allocate
        )

        results = engine.process()

        # 7. Print Results Summary
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.MIGRATE_HEADING(" Migration Summary Report"))
        self.stdout.write("=" * 70)

        total_rows = results.get('total_rows', 0)
        valid_rows = results.get('valid_rows_count', 0)
        error_rows = results.get('error_rows_count', 0)
        total_amount = Decimal(str(results.get('total_amount', 0)))
        
        if dry_run:
            allocated = Decimal(str(results.get('projected_allocated_amount', 0)))
            prepayments = Decimal(str(results.get('projected_prepayment_amount', 0)))
        else:
            allocated = Decimal(str(results.get('allocated_amount', 0)))
            prepayments = Decimal(str(results.get('prepayment_amount', 0)))

        self.stdout.write(f" Total Rows in File:      {total_rows}")
        self.stdout.write(self.style.SUCCESS(f" Valid Rows Processed:   {valid_rows}"))
        if error_rows > 0:
            self.stdout.write(self.style.ERROR(f" Error Rows (Failed):    {error_rows}"))
        else:
            self.stdout.write(f" Error Rows (Failed):    0")

        self.stdout.write("-" * 70)
        self.stdout.write(f" Total Money Value:       KES {total_amount:,.2f}")
        self.stdout.write(f" Cleared from Invoices:   KES {allocated:,.2f}")
        self.stdout.write(f" Carried as Prepayments:  KES {prepayments:,.2f}")

        if not dry_run:
            receipts_created = results.get('receipts_created_count', 0)
            journals_posted = results.get('journals_posted_count', 0)
            self.stdout.write("-" * 70)
            self.stdout.write(self.style.SUCCESS(f" Receipts Issued:        {receipts_created}"))
            self.stdout.write(self.style.SUCCESS(f" GL Journals Posted:     {journals_posted}"))

        # 8. Print Errors (if any)
        errors = results.get('errors', [])
        if errors:
            self.stdout.write("\n" + self.style.ERROR("! Validation and Processing Errors:"))
            for err in errors[:25]:  # Display first 25 errors
                self.stdout.write(self.style.ERROR(f"  * Row {err.get('row')}: {err.get('error')}"))
            if len(errors) > 25:
                self.stdout.write(self.style.WARNING(f"  ... and {len(errors) - 25} more errors."))

        self.stdout.write("=" * 70)
        if dry_run:
            if error_rows == 0:
                self.stdout.write(
                    self.style.SUCCESS("[OK] Pre-flight validation passed! Re-run without --dry-run to commit.")
                )
            else:
                self.stdout.write(
                    self.style.WARNING("[!] Please fix the errors listed above before executing the live migration.")
                )
        else:
            if error_rows == 0:
                self.stdout.write(
                    self.style.SUCCESS("[OK] Migration completed successfully! Financial statements and student ledgers are updated.")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"[!] Migration completed with {error_rows} errors. Valid rows ({valid_rows}) have been committed.")
                )

