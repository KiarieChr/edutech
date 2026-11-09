"""
fees/receipt_migration_engine.py
================================
Core Migration and Bulk Ingestion Engine for Historical & Implementation Receipts.

Supports:
- Excel (.xlsx) and CSV (.csv) parsing with robust header normalization.
- Dry-run pre-flight validation (simulates allocations without touching DB).
- Tenant schema isolation via django_tenants schema_context.
- FIFO automatic allocation against open student fee invoices.
- Automated creation of StudentPrepayment records for surplus balances.
- Automatic double-entry posting to the General Ledger (ReceiptJournalService)
  updating Cashbook, Trial Balance, and Balance Sheet.
- Detailed row-by-row error reporting with exportable error logs.
- Can be invoked from the interactive UI or CLI (manage.py).
"""

import io
import csv
import logging
from decimal import Decimal, InvalidOperation
from datetime import date, datetime
from typing import Dict, List, Any, Optional, Tuple

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


class HistoricalReceiptMigrationEngine:
    """
    Ingestion engine for bulk importing historical and implementation receipts.
    """

    HEADER_ALIASES = {
        'admission_number': [
            'admission_number', 'admission_no', 'adm_no', 'admno',
            'student_id', 'student_admission_number', 'reg_no', 'registration_number'
        ],
        'amount': [
            'amount', 'amount_received', 'paid_amount', 'receipt_amount', 'paid', 'total'
        ],
        'date': [
            'date', 'receipt_date', 'received_date', 'payment_date', 'trans_date', 'transaction_date'
        ],
        'payment_method': [
            'payment_method', 'method', 'mode_of_payment', 'channel', 'mode', 'payment_mode'
        ],
        'reference': [
            'reference', 'ref', 'transaction_code', 'mpesa_code', 'cheque_no',
            'check_number', 'slip_number', 'bank_ref', 'ref_no'
        ],
        'receipt_number': [
            'receipt_number', 'receipt_no', 'rct_no', 'receipt_id'
        ],
        'payer_name': [
            'payer_name', 'payer', 'paid_by', 'depositor', 'parent_name'
        ],
        'academic_year': [
            'academic_year', 'year', 'session_year'
        ],
        'term': [
            'term', 'term_name', 'semester'
        ],
        'fee_category': [
            'fee_category', 'category'
        ],
        'notes': [
            'notes', 'description', 'remarks', 'narration', 'memo'
        ]
    }

    def __init__(
        self,
        file_obj,
        tenant_schema: Optional[str] = None,
        user=None,
        dry_run: bool = True,
        post_to_gl: bool = True,
        auto_allocate: bool = True,
        default_academic_year_id: Optional[int] = None,
        default_term_id: Optional[int] = None,
        default_payment_method_id: Optional[int] = None,
    ):
        """
        Args:
            file_obj: File-like object (UploadedFile, BytesIO) or file path string.
            tenant_schema: PostgreSQL schema name if multi-tenant (e.g. 'school1').
            user: User executing migration (for audit trail).
            dry_run: If True, validates and previews allocations without committing.
            post_to_gl: If True, creates double-entry journal entries in General Ledger.
            auto_allocate: If True, allocates receipt amounts to open invoices FIFO.
            default_academic_year_id: Fallback academic year if omitted in file.
            default_term_id: Fallback term if omitted in file.
            default_payment_method_id: Fallback payment method if omitted in file.
        """
        self.file_obj = file_obj
        self.tenant_schema = tenant_schema
        self.user = user
        self.dry_run = dry_run
        self.post_to_gl = post_to_gl
        self.auto_allocate = auto_allocate
        self.default_academic_year_id = default_academic_year_id
        self.default_term_id = default_term_id
        self.default_payment_method_id = default_payment_method_id

        # Internal caches to prevent duplicate database queries
        self._student_cache: Dict[str, Any] = {}
        self._payment_method_cache: Dict[str, Any] = {}
        self._year_cache: Dict[str, Any] = {}
        self._term_cache: Dict[str, Any] = {}

    def process(self) -> Dict[str, Any]:
        """
        Executes the migration process (or dry-run simulation).
        Returns a comprehensive dictionary of stats, errors, and previews.
        """
        if self.tenant_schema:
            from django_tenants.utils import schema_context
            with schema_context(self.tenant_schema):
                return self._run_pipeline()
        return self._run_pipeline()

    def _run_pipeline(self) -> Dict[str, Any]:
        # 1. Parse rows from CSV or Excel
        raw_rows, parse_error = self._parse_file()
        if parse_error:
            return {
                'success': False,
                'dry_run': self.dry_run,
                'error': parse_error,
                'total_rows': 0,
                'valid_rows_count': 0,
                'error_rows_count': 0,
                'errors': [{'row': 0, 'error': parse_error}]
            }

        if not raw_rows:
            return {
                'success': False,
                'dry_run': self.dry_run,
                'error': 'Uploaded file is empty or contains no data rows.',
                'total_rows': 0,
                'valid_rows_count': 0,
                'error_rows_count': 0,
                'errors': [{'row': 0, 'error': 'File has no data rows'}]
            }

        # 2. Warm up caches
        self._warm_up_caches()

        # 3. Process rows
        if self.dry_run:
            # In dry-run mode, we do not commit to DB
            return self._execute_dry_run(raw_rows)
        else:
            # In commit mode, wrap everything in atomic transaction with savepoints
            return self._execute_commit(raw_rows)

    def _parse_file(self) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Parses CSV or Excel file into a normalized list of row dictionaries."""
        file_name = getattr(self.file_obj, 'name', '') or str(self.file_obj)
        content = self.file_obj

        # Handle file paths passed as strings
        if isinstance(content, str):
            try:
                content = open(content, 'rb')
            except Exception as e:
                return [], f"Failed to open file: {e}"

        # Rewind if possible
        if hasattr(content, 'seek'):
            content.seek(0)

        # 1. Check for Excel format
        if file_name.endswith('.xlsx') or file_name.endswith('.xls'):
            try:
                import openpyxl
                workbook = openpyxl.load_workbook(content, data_only=True)
                sheet = workbook.active
                rows_iter = sheet.iter_rows(values_only=True)
                
                try:
                    header_row = next(rows_iter)
                except StopIteration:
                    return [], "Excel file is completely empty."

                if not header_row:
                    return [], "Excel header row is empty."

                normalized_headers = self._normalize_headers(header_row)
                data_rows = []
                for row_idx, row_values in enumerate(rows_iter, start=2):
                    if not any(v is not None and str(v).strip() != '' for v in row_values):
                        continue  # Skip blank rows
                    row_dict = {}
                    for col_idx, val in enumerate(row_values):
                        if col_idx < len(normalized_headers):
                            header_name = normalized_headers[col_idx]
                            if header_name:
                                row_dict[header_name] = val
                    row_dict['_row_num'] = row_idx
                    data_rows.append(row_dict)

                return data_rows, None
            except Exception as exc:
                return [], f"Failed to parse Excel file: {exc}"

        # 2. CSV parsing fallback
        try:
            # Read bytes and try decoding with fallback encodings
            if hasattr(content, 'read'):
                raw_bytes = content.read()
            elif isinstance(content, bytes):
                raw_bytes = content
            elif isinstance(content, str):
                raw_bytes = content
            else:
                raw_bytes = bytes(content)

            if isinstance(raw_bytes, str):
                text_content = raw_bytes
            else:
                text_content = None
                for encoding in ['utf-8-sig', 'utf-8', 'windows-1252', 'latin-1']:
                    try:
                        text_content = raw_bytes.decode(encoding)
                        break
                    except UnicodeDecodeError:
                        continue

            if text_content is None:
                return [], "Unable to decode CSV file. Please ensure it is saved as UTF-8."

            reader = csv.reader(io.StringIO(text_content))
            try:
                header_row = next(reader)
            except StopIteration:
                return [], "CSV file is empty."

            normalized_headers = self._normalize_headers(header_row)
            data_rows = []
            for row_idx, row_values in enumerate(reader, start=2):
                if not any(v.strip() != '' for v in row_values):
                    continue
                row_dict = {}
                for col_idx, val in enumerate(row_values):
                    if col_idx < len(normalized_headers):
                        header_name = normalized_headers[col_idx]
                        if header_name:
                            row_dict[header_name] = val.strip()
                row_dict['_row_num'] = row_idx
                data_rows.append(row_dict)

            return data_rows, None
        except Exception as exc:
            return [], f"Failed to parse CSV file: {exc}"

    def _normalize_headers(self, raw_headers: List[Any]) -> List[Optional[str]]:
        """Maps arbitrary spreadsheet header strings to canonical field keys."""
        canonical_headers = []
        for raw in raw_headers:
            if raw is None:
                canonical_headers.append(None)
                continue
            clean_str = str(raw).strip().lower().replace(' ', '_').replace('-', '_').replace('.', '')
            matched_key = None
            for canonical, aliases in self.HEADER_ALIASES.items():
                if clean_str == canonical or clean_str in aliases:
                    matched_key = canonical
                    break
            canonical_headers.append(matched_key or clean_str)
        return canonical_headers

    def _warm_up_caches(self):
        """Loads payment methods, academic years, and terms into memory."""
        from finance.models import PaymentMethod
        from student_settings.models import AcademicYear, Term

        # Payment Methods
        for pm in PaymentMethod.objects.select_related('account').all():
            self._payment_method_cache[pm.name.strip().upper()] = pm
            if hasattr(pm, 'code') and pm.code:
                self._payment_method_cache[pm.code.strip().upper()] = pm

        # Academic Years
        for ay in AcademicYear.objects.all():
            self._year_cache[ay.name.strip().upper()] = ay
            self._year_cache[str(ay.id)] = ay

        # Terms
        for t in Term.objects.all():
            self._term_cache[t.name.strip().upper()] = t
            self._term_cache[str(t.id)] = t

    def _get_student(self, admission_no: str):
        """Fetches student by admission number with memory caching."""
        clean_adm = str(admission_no).strip().upper()
        if clean_adm in self._student_cache:
            return self._student_cache[clean_adm]

        from student_management.models import Student
        student = Student.objects.select_related('student', 'campus').filter(
            admission_number__iexact=clean_adm
        ).first()
        self._student_cache[clean_adm] = student
        return student

    def _resolve_payment_method(self, raw_value: Any):
        """Finds PaymentMethod by name, code, or ID, falling back to default."""
        from finance.models import PaymentMethod
        if not raw_value:
            if self.default_payment_method_id:
                return PaymentMethod.objects.filter(pk=self.default_payment_method_id).first()
            return PaymentMethod.objects.first()

        clean_val = str(raw_value).strip().upper()
        if clean_val in self._payment_method_cache:
            return self._payment_method_cache[clean_val]

        try:
            val_id = int(clean_val)
            pm = PaymentMethod.objects.filter(pk=val_id).first()
            if pm:
                self._payment_method_cache[clean_val] = pm
                return pm
        except ValueError:
            pass

        # Try case-insensitive substring or contains
        pm = PaymentMethod.objects.filter(name__icontains=clean_val).first()
        if pm:
            self._payment_method_cache[clean_val] = pm
            return pm

        if self.default_payment_method_id:
            return PaymentMethod.objects.filter(pk=self.default_payment_method_id).first()
        return PaymentMethod.objects.first()

    def _parse_date(self, val: Any) -> Optional[date]:
        """Robust date parser handling datetime objects and common string formats."""
        if isinstance(val, datetime):
            return val.date()
        if isinstance(val, date):
            return val
        if not val:
            return date.today()

        date_str = str(val).strip()
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y', '%Y/%m/%d', '%d.%m.%Y'):
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue

        try:
            from dateutil import parser
            return parser.parse(date_str).date()
        except Exception:
            return None

    def _validate_row(self, row: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Validates row data and resolves relations.
        Returns (clean_data, error_message).
        """
        row_num = row.get('_row_num', 0)
        adm_no = row.get('admission_number')

        if not adm_no:
            return None, f"Row {row_num}: Admission Number is required."

        student = self._get_student(str(adm_no))
        if not student:
            return None, f"Row {row_num}: Student with Admission Number '{adm_no}' not found in system."

        # Amount validation
        raw_amt = row.get('amount')
        if raw_amt is None or str(raw_amt).strip() == '':
            return None, f"Row {row_num}: Amount is missing."

        try:
            # Clean thousands separators (e.g. 25,000.00 -> 25000.00)
            clean_amt_str = str(raw_amt).replace(',', '').strip()
            amount = Decimal(clean_amt_str)
            if amount <= 0:
                return None, f"Row {row_num}: Amount must be greater than zero (found {raw_amt})."
        except (InvalidOperation, ValueError, TypeError):
            return None, f"Row {row_num}: Invalid amount format '{raw_amt}'."

        # Date validation
        receipt_date = self._parse_date(row.get('date'))
        if not receipt_date:
            return None, f"Row {row_num}: Invalid date format '{row.get('date')}'."

        # Payment method resolution
        raw_pm = row.get('payment_method')
        payment_method = self._resolve_payment_method(raw_pm)
        if not payment_method:
            return None, f"Row {row_num}: Payment method '{raw_pm}' not found and no default available."

        if self.post_to_gl and not getattr(payment_method, 'account_id', None):
            return None, (
                f"Row {row_num}: Payment method '{payment_method.name}' has no linked GL Account. "
                f"Please link a Cash/Bank account to this payment method under Finance Settings."
            )

        # Academic Year & Term (optional)
        academic_year = None
        raw_year = row.get('academic_year')
        if raw_year:
            academic_year = self._year_cache.get(str(raw_year).strip().upper())
        if not academic_year and self.default_academic_year_id:
            from student_settings.models import AcademicYear
            academic_year = AcademicYear.objects.filter(pk=self.default_academic_year_id).first()

        term = None
        raw_term = row.get('term')
        if raw_term:
            term = self._term_cache.get(str(raw_term).strip().upper())
        if not term and self.default_term_id:
            from student_settings.models import Term
            term = Term.objects.filter(pk=self.default_term_id).first()

        # Payer name fallback
        payer_name = row.get('payer_name')
        if not payer_name:
            if student.student:
                fn = getattr(student.student, 'get_full_name', '')
                payer_name = (fn() if callable(fn) else fn) or getattr(student.student, 'username', '')
            else:
                payer_name = f"Student {student.admission_number}"

        clean_data = {
            'row_num': row_num,
            'student': student,
            'amount': amount,
            'date': receipt_date,
            'payment_method': payment_method,
            'reference': str(row.get('reference') or '').strip(),
            'receipt_number': str(row.get('receipt_number') or '').strip(),
            'payer_name': str(payer_name).strip(),
            'academic_year': academic_year,
            'term': term,
            'fee_category': str(row.get('fee_category') or 'Tuition Fees').strip(),
            'notes': str(row.get('notes') or f"Historical import for {student.admission_number}").strip()
        }

        return clean_data, None

    def _execute_dry_run(self, raw_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Simulates the entire import without writing to the database.
        Tracks virtual invoice balances in memory to reflect sequential payments.
        """
        from fees.models import FeeInvoiceItem, FeeInvoice
        from finance.models import ReceiptAllocation

        valid_rows = []
        errors = []
        total_amount = Decimal('0.00')
        projected_allocated = Decimal('0.00')
        projected_prepayments = Decimal('0.00')

        # Virtual memory tracking of invoice item balances
        virtual_item_balances: Dict[int, Decimal] = {}

        for row in raw_rows:
            clean_data, error = self._validate_row(row)
            if error:
                errors.append({'row': row.get('_row_num', 0), 'error': error})
                continue

            student = clean_data['student']
            amount = clean_data['amount']
            total_amount += amount

            # Simulation of FIFO allocation
            row_allocated = Decimal('0.00')
            remaining_to_allocate = amount

            if self.auto_allocate:
                open_items = FeeInvoiceItem.objects.filter(
                    invoice__student=student,
                    invoice__status__in=['SENT', 'PARTIALLY_PAID', 'OVERDUE']
                ).exclude(
                    invoice__status='VOID'
                ).select_related('invoice').order_by('invoice__date_issued', 'id')

                for item in open_items:
                    if remaining_to_allocate <= 0:
                        break

                    # Get current virtual balance
                    if item.id not in virtual_item_balances:
                        allocated_db = ReceiptAllocation.objects.filter(
                            invoice_item=item
                        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
                        virtual_item_balances[item.id] = max(Decimal('0.00'), item.amount - allocated_db)

                    curr_balance = virtual_item_balances[item.id]
                    if curr_balance > 0:
                        alloc = min(remaining_to_allocate, curr_balance)
                        row_allocated += alloc
                        virtual_item_balances[item.id] -= alloc
                        remaining_to_allocate -= alloc

            row_prepayment = amount - row_allocated
            projected_allocated += row_allocated
            projected_prepayments += row_prepayment

            if student.student:
                fn = getattr(student.student, 'get_full_name', '')
                student_display_name = (fn() if callable(fn) else fn) or getattr(student.student, 'username', '')
            else:
                student_display_name = student.admission_number

            valid_rows.append({
                'row': clean_data['row_num'],
                'admission_number': student.admission_number,
                'student_name': student_display_name,
                'date': clean_data['date'].strftime('%Y-%m-%d'),
                'amount': float(amount),
                'allocated_amount': float(row_allocated),
                'prepayment_amount': float(row_prepayment),
                'payment_method': clean_data['payment_method'].name,
                'reference': clean_data['reference']
            })

        return {
            'success': len(errors) == 0,
            'dry_run': True,
            'total_rows': len(raw_rows),
            'valid_rows_count': len(valid_rows),
            'error_rows_count': len(errors),
            'total_amount': float(total_amount),
            'projected_allocated_amount': float(projected_allocated),
            'projected_prepayment_amount': float(projected_prepayments),
            'errors': errors,
            'sample_valid_rows': valid_rows[:50]  # First 50 rows for modal preview
        }

    def _execute_commit(self, raw_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Commits valid receipts to database with sub-ledger allocations and GL journal entries.
        """
        from finance.models import Receipt, ReceiptAllocation, StudentPrepayment
        from fees.models import FeeInvoiceItem
        from finance.receipt_journal_service import ReceiptJournalService

        valid_count = 0
        errors = []
        created_receipts = []
        journals_posted_count = 0
        total_amount = Decimal('0.00')
        total_allocated = Decimal('0.00')
        total_prepayments = Decimal('0.00')

        for row in raw_rows:
            clean_data, error = self._validate_row(row)
            if error:
                errors.append({'row': row.get('_row_num', 0), 'error': error})
                continue

            sid = transaction.savepoint()
            try:
                student = clean_data['student']
                amount = clean_data['amount']
                receipt_date = clean_data['date']

                # Create Receipt instance
                receipt = Receipt(
                    received_date=receipt_date,
                    receipt_type='STUDENT_FEE',
                    payer_name=clean_data['payer_name'],
                    student=student,
                    amount_received=amount,
                    payment_method=clean_data['payment_method'],
                    reference=clean_data['reference'],
                    received_by=self.user if self.user and self.user.is_authenticated else None,
                    status='POSTED',
                    is_posted=True,
                    posted_at=timezone.now(),
                    fee_category=clean_data['fee_category'],
                    academic_year=clean_data['academic_year'],
                    term=clean_data['term'],
                    notes=clean_data['notes']
                )

                if clean_data['receipt_number']:
                    receipt.receipt_number = clean_data['receipt_number']

                receipt.save()

                # FIFO Invoice Allocation
                row_allocated = Decimal('0.00')
                remaining_to_allocate = amount

                if self.auto_allocate:
                    open_items = FeeInvoiceItem.objects.filter(
                        invoice__student=student,
                        invoice__status__in=['SENT', 'PARTIALLY_PAID', 'OVERDUE']
                    ).exclude(
                        invoice__status='VOID'
                    ).select_related('invoice').order_by('invoice__date_issued', 'id')

                    for item in open_items:
                        if remaining_to_allocate <= 0:
                            break

                        allocated_so_far = ReceiptAllocation.objects.filter(
                            invoice_item=item
                        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
                        item_balance = item.amount - allocated_so_far

                        if item_balance > 0:
                            alloc_amount = min(remaining_to_allocate, item_balance)

                            ReceiptAllocation.objects.create(
                                receipt=receipt,
                                invoice=item.invoice,
                                invoice_item=item,
                                amount=alloc_amount
                            )

                            inv = item.invoice
                            inv.paid_amount += alloc_amount
                            inv.balance = inv.total_amount - inv.paid_amount
                            if inv.balance <= 0:
                                inv.status = 'PAID'
                            elif inv.paid_amount > 0:
                                inv.status = 'PARTIALLY_PAID'
                            inv.save(update_fields=['paid_amount', 'balance', 'status', 'updated_at'])

                            row_allocated += alloc_amount
                            remaining_to_allocate -= alloc_amount

                receipt.amount_allocated = row_allocated

                # Surplus handling -> StudentPrepayment
                if amount > row_allocated:
                    surplus = amount - row_allocated
                    StudentPrepayment.objects.create(
                        student=student,
                        receipt=receipt,
                        amount=surplus,
                        balance=surplus
                    )
                    total_prepayments += surplus

                receipt.save(update_fields=['amount_allocated'])
                total_allocated += row_allocated
                total_amount += amount

                # GL Journal Entry Posting
                if self.post_to_gl:
                    try:
                        ReceiptJournalService.create_receipt_journal_entry(
                            receipt=receipt,
                            user=self.user
                        )
                        journals_posted_count += 1
                    except Exception as gl_exc:
                        logger.warning(
                            f"Warning: GL posting for receipt {receipt.receipt_number} failed: {gl_exc}"
                        )

                transaction.savepoint_commit(sid)
                valid_count += 1
                created_receipts.append(receipt.receipt_number)

            except Exception as exc:
                transaction.savepoint_rollback(sid)
                errors.append({
                    'row': row.get('_row_num', 0),
                    'error': f"Database error on row {row.get('_row_num', 0)}: {exc}"
                })

        return {
            'success': len(errors) == 0,
            'dry_run': False,
            'total_rows': len(raw_rows),
            'valid_rows_count': valid_count,
            'error_rows_count': len(errors),
            'total_amount': float(total_amount),
            'allocated_amount': float(total_allocated),
            'prepayment_amount': float(total_prepayments),
            'receipts_created_count': len(created_receipts),
            'journals_posted_count': journals_posted_count,
            'sample_receipt_numbers': created_receipts[:10],
            'errors': errors
        }

    @classmethod
    def generate_template_csv(cls) -> str:
        """
        Generates standard CSV template content for historical receipt migration.
        """
        output = io.StringIO()
        writer = csv.writer(output)
        headers = [
            'admission_number',
            'date',
            'amount',
            'payment_method',
            'reference',
            'receipt_number',
            'payer_name',
            'academic_year',
            'term',
            'fee_category',
            'notes'
        ]
        writer.writerow(headers)
        # Sample illustrative rows
        writer.writerow([
            'ADM-2024-001', '2024-02-15', '25000', 'Bank Transfer', 'EQ-98721',
            'RCT-2024-0001', 'Grace Kamau', '2024', 'Term 1', 'Tuition Fees', 'Opening implementation fee balance'
        ])
        writer.writerow([
            'ADM-2024-002', '2024-03-10', '18000', 'M-Pesa', 'QWE892182',
            '', 'James Mwangi', '2024', 'Term 1', 'Tuition Fees', 'Term 1 clearance payment'
        ])
        return output.getvalue()

