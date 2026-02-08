"""
Management command to create journal entries for historical receipts.
This script processes all POSTED or ISSUED receipts that don't have journal entries yet.

Usage:
    python manage.py post_historical_receipts
    python manage.py post_historical_receipts --dry-run  # Preview without making changes
    python manage.py post_historical_receipts --receipt-id=123  # Process specific receipt
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.contrib.auth import get_user_model
from finance.models import Receipt
from journals.models import JournalEntry, JournalLine
from finance.receipt_journal_service import ReceiptJournalService

User = get_user_model()


class Command(BaseCommand):
    help = 'Create journal entries for historical receipts that were posted before automation'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without committing to database',
        )
        parser.add_argument(
            '--receipt-id',
            type=int,
            help='Process only a specific receipt by ID',
        )
        parser.add_argument(
            '--status',
            type=str,
            default='POSTED,ISSUED',
            help='Comma-separated list of receipt statuses to process (default: POSTED,ISSUED)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        receipt_id = options['receipt_id']
        statuses = options['status'].split(',')
        
        self.stdout.write(self.style.WARNING('=' * 70))
        self.stdout.write(self.style.WARNING('POST HISTORICAL RECEIPTS TO JOURNALS'))
        self.stdout.write(self.style.WARNING('=' * 70))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be saved\n'))
        
        # Build query for receipts
        query = Receipt.objects.filter(status__in=statuses)
        
        if receipt_id:
            query = query.filter(id=receipt_id)
            self.stdout.write(f'Processing specific receipt ID: {receipt_id}\n')
        
        # Find receipts without journal entries
        receipts_to_process = []
        for receipt in query.order_by('received_date', 'id'):
            # Check if receipt already has a journal entry
            has_journal = JournalEntry.objects.filter(
                reference__icontains=receipt.receipt_number
            ).exists()
            
            if not has_journal:
                receipts_to_process.append(receipt)
        
        total_receipts = len(receipts_to_process)
        
        if total_receipts == 0:
            self.stdout.write(self.style.SUCCESS('✓ No receipts found that need journal entries'))
            return
        
        self.stdout.write(f'Found {total_receipts} receipt(s) without journal entries\n')
        
        # Get system user for journal creation
        try:
            system_user = User.objects.filter(is_superuser=True).first()
            if not system_user:
                system_user = User.objects.first()
        except Exception:
            system_user = None
        
        # Process each receipt
        success_count = 0
        error_count = 0
        errors = []
        
        for idx, receipt in enumerate(receipts_to_process, 1):
            self.stdout.write(f'\n[{idx}/{total_receipts}] Processing Receipt: {receipt.receipt_number}')
            self.stdout.write(f'  Date: {receipt.received_date}')
            self.stdout.write(f'  Amount: KES {receipt.amount_received:,.2f}')
            self.stdout.write(f'  Type: {receipt.get_receipt_type_display()}')
            self.stdout.write(f'  Status: {receipt.status}')
            
            try:
                if not dry_run:
                    with transaction.atomic():
                        # Create journal entry
                        journal_entry = ReceiptJournalService.create_receipt_journal_entry(
                            receipt=receipt,
                            user=system_user
                        )
                        
                        self.stdout.write(self.style.SUCCESS(
                            f'  ✓ Created Journal Entry: {journal_entry.reference}'
                        ))
                        self.stdout.write(f'    - Journal ID: {journal_entry.id}')
                        self.stdout.write(f'    - Status: {journal_entry.status}')
                        self.stdout.write(f'    - Lines: {journal_entry.lines.count()}')
                        self.stdout.write(f'    - Ledger Entries: {journal_entry.ledger_entries.count()}')
                else:
                    self.stdout.write(self.style.WARNING('  ⊘ Skipped (dry-run mode)'))
                
                success_count += 1
                
            except Exception as e:
                error_count += 1
                error_msg = f'Receipt {receipt.receipt_number}: {str(e)}'
                errors.append(error_msg)
                self.stdout.write(self.style.ERROR(f'  ✗ Error: {str(e)}'))
        
        # Summary
        self.stdout.write('\n' + '=' * 70)
        self.stdout.write(self.style.WARNING('SUMMARY'))
        self.stdout.write('=' * 70)
        self.stdout.write(f'Total Receipts Processed: {total_receipts}')
        self.stdout.write(self.style.SUCCESS(f'Successful: {success_count}'))
        
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f'Errors: {error_count}'))
            self.stdout.write('\nError Details:')
            for error in errors:
                self.stdout.write(self.style.ERROR(f'  - {error}'))
        
        if dry_run:
            self.stdout.write('\n' + self.style.WARNING('DRY RUN COMPLETE - No changes were saved'))
        else:
            self.stdout.write('\n' + self.style.SUCCESS('✓ Migration Complete!'))
            
            # Verification
            self.stdout.write('\nVerification:')
            remaining = Receipt.objects.filter(status__in=statuses).exclude(
                receipt_number__in=JournalEntry.objects.values_list('reference', flat=True).distinct()
            ).count()
            
            if remaining > 0:
                self.stdout.write(self.style.WARNING(
                    f'  Note: {remaining} receipt(s) still without journal entries (may have errors)'
                ))
            else:
                self.stdout.write(self.style.SUCCESS('  ✓ All receipts now have journal entries!'))
