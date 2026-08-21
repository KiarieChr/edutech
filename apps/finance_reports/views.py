from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.utils import timezone
from django.db.models import Sum, Q
from decimal import Decimal
from .services import ReportService

class ReportViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        """Allow read-only access to report endpoints"""
        if self.action in ['trial_balance', 'overview', 'balance_sheet', 'income_statement']:
            return [AllowAny()]
        return [IsAuthenticated()]

    @action(detail=False, methods=['get'])
    def overview(self, request):
        """
        Get financial overview statistics including:
        - Current fiscal year/period
        - Income, expenses, surplus
        - Collection rate
        - Outstanding fees
        """
        from finance.models import FiscalPeriod, Account
        from journals.models import LedgerEntry
        from fees.models import FeeInvoice
        from finance.models import Receipt
        
        # Get current fiscal period
        today = timezone.now().date()
        current_period = FiscalPeriod.objects.filter(
            start_date__lte=today,
            end_date__gte=today,
            is_closed=False
        ).first()
        
        fiscal_year = current_period.name if current_period else "N/A"
        start_date = current_period.start_date if current_period else today.replace(month=1, day=1)
        end_date = today
        
        # Get income accounts balance (Revenue)
        income_accounts = Account.objects.filter(type='INCOME')
        total_income = Decimal('0.00')
        for acc in income_accounts:
            ledgers = LedgerEntry.objects.filter(
                account=acc,
                date__gte=start_date,
                date__lte=end_date
            )
            # Income increases with credit
            total_income += sum(l.credit - l.debit for l in ledgers)
        
        # Get expense accounts balance
        expense_accounts = Account.objects.filter(type='EXPENSE')
        total_expenses = Decimal('0.00')
        for acc in expense_accounts:
            ledgers = LedgerEntry.objects.filter(
                account=acc,
                date__gte=start_date,
                date__lte=end_date
            )
            # Expenses increase with debit
            total_expenses += sum(l.debit - l.credit for l in ledgers)
        
        net_surplus = total_income - total_expenses
        
        # Get cash/bank balance
        cash_bank_accounts = Account.objects.filter(Q(sub_type='BANK') | Q(sub_type='CASH'))
        cash_bank_balance = Decimal('0.00')
        for acc in cash_bank_accounts:
            last_ledger = LedgerEntry.objects.filter(account=acc).order_by('-date', '-created_at').first()
            if last_ledger:
                cash_bank_balance += last_ledger.balance_after
        
        # Get outstanding fees (invoiced but not paid)
        total_invoiced = FeeInvoice.objects.filter(
            date_issued__gte=start_date,
            date_issued__lte=end_date
        ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
        
        total_paid = Receipt.objects.filter(
            received_date__gte=start_date,
            received_date__lte=end_date,
            status__in=['POSTED', 'ISSUED']
        ).aggregate(total=Sum('amount_received'))['total'] or Decimal('0.00')
        
        outstanding_fees = total_invoiced - total_paid
        
        # Calculate collection rate
        collection_rate = 0
        if total_invoiced > 0:
            collection_rate = round((total_paid / total_invoiced) * 100, 1)
        
        return Response({
            'fiscalYear': fiscal_year,
            'currentTerm': current_period.name if current_period else "N/A",
            'totalIncome': float(total_income),
            'totalExpenses': float(total_expenses),
            'netSurplus': float(net_surplus),
            'cashBankBalance': float(cash_bank_balance),
            'outstandingFees': float(outstanding_fees),
            'collectionRate': collection_rate,
            'periodStart': start_date.isoformat(),
            'periodEnd': end_date.isoformat()
        })

    @action(detail=False, methods=['get'])
    def trial_balance(self, request):
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        data = ReportService.get_trial_balance(start_date, end_date)
        return Response(data)

    @action(detail=False, methods=['get'])
    def balance_sheet(self, request):
        as_of_date = request.query_params.get('date') # Mandatory? default today
        if not as_of_date:
            from django.utils import timezone
            as_of_date = timezone.now().date()
            
        data = ReportService.get_balance_sheet(as_of_date)
        return Response(data)

    @action(detail=False, methods=['get'])
    def income_statement(self, request):
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        if not start_date or not end_date:
            return Response({'error': 'start_date and end_date are required'}, status=status.HTTP_400_BAD_REQUEST)
            
        data = ReportService.get_income_statement(start_date, end_date)
        return Response(data)

    @action(detail=False, methods=['get'], url_path='cash-flow-statement')
    def cash_flow_statement(self, request):
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        if not start_date or not end_date:
            return Response({'error': 'start_date and end_date are required'}, status=status.HTTP_400_BAD_REQUEST)
            
        data = ReportService.get_cash_flow_statement(start_date, end_date)
        return Response(data)

    @action(detail=False, methods=['get'], url_path='financial-notes')
    def financial_notes(self, request):
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        if not start_date or not end_date:
            return Response({'error': 'start_date and end_date are required'}, status=status.HTTP_400_BAD_REQUEST)
            
        data = ReportService.get_financial_notes(start_date, end_date)
        return Response(data)

    @action(detail=False, methods=['get'], url_path='cash-flow')
    def cash_flow(self, request):
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if not start_date or not end_date:
            from django.utils import timezone
            end_date = timezone.now().date()
            start_date = end_date.replace(day=1) # Default to current month

        data = ReportService.get_cash_flow_statement(start_date, end_date)
        return Response(data)

    @action(detail=False, methods=['get'], url_path='general-ledger')
    def general_ledger(self, request):
        account_id = request.query_params.get('account_id')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        if not account_id:
            return Response({'error': 'account_id is required'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            data = ReportService.get_general_ledger(account_id, start_date, end_date)
            return Response(data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    # -------------------------------------------------------------------------
    # FEE COLLECTION REPORTS
    # -------------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='fee-collections')
    def fee_collections(self, request):
        """
        Fee collections summary with filters: academic_year, term, class_session, group_by (class|term|month|payment_method).
        Returns invoiced vs collected breakdown.
        """
        from fees.models import FeeInvoice
        from finance.models import Receipt
        from django.db.models import Count

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        academic_year_id = request.query_params.get('academic_year')
        term_id = request.query_params.get('term')
        session_id = request.query_params.get('session')
        group_by = request.query_params.get('group_by', 'term')

        inv_filters = Q()
        rec_filters = Q(receipt_type='STUDENT_FEE', status__in=['ISSUED', 'PRINTED'])
        if start_date:
            inv_filters &= Q(date_issued__gte=start_date)
            rec_filters &= Q(received_date__gte=start_date)
        if end_date:
            inv_filters &= Q(date_issued__lte=end_date)
            rec_filters &= Q(received_date__lte=end_date)
        if academic_year_id:
            inv_filters &= Q(academic_year_id=academic_year_id)
        if term_id:
            inv_filters &= Q(term_id=term_id)
        if session_id:
            inv_filters &= Q(class_session_id=session_id)

        invoices = FeeInvoice.objects.filter(inv_filters).exclude(status='VOID')
        receipts = Receipt.objects.filter(rec_filters)

        total_invoiced = invoices.aggregate(t=Sum('total_amount'))['t'] or Decimal('0.00')
        total_collected = receipts.aggregate(t=Sum('amount_received'))['t'] or Decimal('0.00')
        total_balance = total_invoiced - total_collected
        collection_rate = round(float(total_collected) / float(total_invoiced) * 100, 1) if total_invoiced > 0 else 0

        # Grouping
        rows = []
        if group_by == 'class':
            qs = invoices.values(
                'class_session_id', 'class_session__name'
            ).annotate(
                invoiced=Sum('total_amount'),
                paid=Sum('paid_amount'),
                count=Count('id')
            ).order_by('-invoiced')
            for r in qs:
                balance = (r['invoiced'] or 0) - (r['paid'] or 0)
                rate = round(float(r['paid'] or 0) / float(r['invoiced']) * 100, 1) if r['invoiced'] else 0
                rows.append({'label': r['class_session__name'] or 'Unknown', 'invoiced': float(r['invoiced'] or 0), 'collected': float(r['paid'] or 0), 'balance': float(balance), 'rate': rate, 'count': r['count']})
        elif group_by == 'month':
            from django.db.models.functions import TruncMonth
            qs = invoices.annotate(month=TruncMonth('date_issued')).values('month').annotate(
                invoiced=Sum('total_amount'), paid=Sum('paid_amount'), count=Count('id')
            ).order_by('month')
            for r in qs:
                balance = (r['invoiced'] or 0) - (r['paid'] or 0)
                rate = round(float(r['paid'] or 0) / float(r['invoiced']) * 100, 1) if r['invoiced'] else 0
                rows.append({'label': r['month'].strftime('%b %Y') if r['month'] else '', 'invoiced': float(r['invoiced'] or 0), 'collected': float(r['paid'] or 0), 'balance': float(balance), 'rate': rate, 'count': r['count']})
        elif group_by == 'payment_method':
            qs = receipts.values('payment_method__name').annotate(collected=Sum('amount_received'), count=Count('id')).order_by('-collected')
            for r in qs:
                rows.append({'label': r['payment_method__name'] or 'Unknown', 'collected': float(r['collected'] or 0), 'invoiced': 0, 'balance': 0, 'rate': 0, 'count': r['count']})
        else:  # term (default)
            qs = invoices.values('term__name', 'academic_year__name').annotate(
                invoiced=Sum('total_amount'), paid=Sum('paid_amount'), count=Count('id')
            ).order_by('academic_year__name', 'term__name')
            for r in qs:
                balance = (r['invoiced'] or 0) - (r['paid'] or 0)
                rate = round(float(r['paid'] or 0) / float(r['invoiced']) * 100, 1) if r['invoiced'] else 0
                label = f"{r['academic_year__name']} — {r['term__name']}" if r['academic_year__name'] else r['term__name'] or 'Unknown'
                rows.append({'label': label, 'invoiced': float(r['invoiced'] or 0), 'collected': float(r['paid'] or 0), 'balance': float(balance), 'rate': rate, 'count': r['count']})

        return Response({
            'summary': {
                'total_invoiced': float(total_invoiced),
                'total_collected': float(total_collected),
                'total_balance': float(total_balance),
                'collection_rate': collection_rate,
                'invoice_count': invoices.count(),
                'receipt_count': receipts.count(),
            },
            'rows': rows,
            'group_by': group_by,
        })

    @action(detail=False, methods=['get'], url_path='arrears')
    def arrears(self, request):
        """
        Outstanding/arrears report — students with unpaid balances.
        Filters: academic_year, term, session, min_balance, status.
        Supports pagination.
        """
        from fees.models import FeeInvoice
        from django.db.models import F

        academic_year_id = request.query_params.get('academic_year')
        term_id = request.query_params.get('term')
        session_id = request.query_params.get('session')
        min_bal_param = request.query_params.get('min_balance')
        min_balance = Decimal(min_bal_param) if min_bal_param else Decimal('0.01')
        search = request.query_params.get('search', '')
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 50))
        sort_by = request.query_params.get('sort_by', '-balance')  # -balance, name, admission_number

        filters = Q(balance__gte=min_balance) & ~Q(status='VOID')
        if academic_year_id:
            filters &= Q(academic_year_id=academic_year_id)
        if term_id:
            filters &= Q(term_id=term_id)
        if session_id:
            filters &= Q(class_session_id=session_id)
        if search:
            filters &= (
                Q(student__student__first_name__icontains=search) |
                Q(student__student__last_name__icontains=search) |
                Q(student__admission_number__icontains=search)
            )

        qs = FeeInvoice.objects.filter(filters).select_related(
            'student__student', 'class_session', 'term', 'academic_year'
        ).order_by(sort_by if sort_by in ['balance', '-balance', 'student__admission_number'] else '-balance')

        total_count = qs.count()
        total_balance = qs.aggregate(t=Sum('balance'))['t'] or Decimal('0.00')
        total_invoiced = qs.aggregate(t=Sum('total_amount'))['t'] or Decimal('0.00')

        # Bucket by aging
        from django.utils import timezone as tz
        today = tz.now().date()

        start = (page - 1) * page_size
        end = start + page_size
        page_qs = qs[start:end]

        rows = []
        for inv in page_qs:
            days_overdue = (today - inv.date_issued).days if inv.date_issued else 0
            if days_overdue <= 30:
                bucket = '0-30 days'
            elif days_overdue <= 60:
                bucket = '31-60 days'
            elif days_overdue <= 90:
                bucket = '61-90 days'
            else:
                bucket = '90+ days'

            rows.append({
                'student_id': inv.student_id,
                'admission_number': inv.student.admission_number if inv.student else '',
                'student_name': inv.student.student.get_full_name if (inv.student and hasattr(inv.student, 'student') and inv.student.student) else '',
                'class_session': inv.class_session.name if inv.class_session else '',
                'term': inv.term.name if inv.term else '',
                'academic_year': inv.academic_year.name if inv.academic_year else '',
                'invoice_number': inv.invoice_number,
                'date_issued': inv.date_issued.isoformat() if inv.date_issued else None,
                'due_date': inv.due_date.isoformat() if inv.due_date else None,
                'total_amount': float(inv.total_amount),
                'paid_amount': float(inv.paid_amount),
                'balance': float(inv.balance),
                'status': inv.status,
                'days_overdue': days_overdue,
                'bucket': bucket,
            })

        # Aging summary
        aging = {'0-30 days': 0, '31-60 days': 0, '61-90 days': 0, '90+ days': 0}
        for inv in qs:
            days = (today - inv.date_issued).days if inv.date_issued else 0
            if days <= 30:
                aging['0-30 days'] += float(inv.balance)
            elif days <= 60:
                aging['31-60 days'] += float(inv.balance)
            elif days <= 90:
                aging['61-90 days'] += float(inv.balance)
            else:
                aging['90+ days'] += float(inv.balance)

        return Response({
            'summary': {
                'total_count': total_count,
                'total_balance': float(total_balance),
                'total_invoiced': float(total_invoiced),
                'aging': [{'bucket': k, 'amount': v} for k, v in aging.items()],
            },
            'results': rows,
            'count': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': max(1, (total_count + page_size - 1) // page_size),
        })

    @action(detail=False, methods=['get'], url_path='payment-summary')
    def payment_summary(self, request):
        """
        Daily/weekly/monthly/yearly payment summary. 
        group_by: day|week|month|year
        """
        from finance.models import Receipt
        from django.db.models.functions import TruncDay, TruncWeek, TruncMonth, TruncYear

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        group_by = request.query_params.get('group_by', 'month')
        payment_method_id = request.query_params.get('payment_method')

        filters = Q(status__in=['ISSUED', 'PRINTED'])
        if start_date:
            filters &= Q(received_date__gte=start_date)
        if end_date:
            filters &= Q(received_date__lte=end_date)
        if payment_method_id:
            filters &= Q(payment_method_id=payment_method_id)

        trunc_map = {'day': TruncDay, 'week': TruncWeek, 'month': TruncMonth, 'year': TruncYear}
        TruncFn = trunc_map.get(group_by, TruncMonth)

        from django.db.models import Count
        qs = Receipt.objects.filter(filters).annotate(period=TruncFn('received_date')).values(
            'period', 'receipt_type', 'payment_method__name'
        ).annotate(
            total=Sum('amount_received'),
            count=Count('id')
        ).order_by('period')

        # Also get totals by payment method
        by_method = Receipt.objects.filter(filters).values('payment_method__name').annotate(
            total=Sum('amount_received'), count=Count('id')
        ).order_by('-total')

        # Build period-level aggregation
        period_map = {}
        for r in qs:
            key = r['period'].isoformat() if r['period'] else 'Unknown'
            if key not in period_map:
                period_map[key] = {'period': key, 'total': 0, 'count': 0, 'by_type': {}}
            period_map[key]['total'] += float(r['total'] or 0)
            period_map[key]['count'] += r['count']
            rtype = r['receipt_type'] or 'OTHER'
            period_map[key]['by_type'][rtype] = period_map[key]['by_type'].get(rtype, 0) + float(r['total'] or 0)

        receipts_all = Receipt.objects.filter(filters)
        grand_total = receipts_all.aggregate(t=Sum('amount_received'))['t'] or Decimal('0.00')
        grand_count = receipts_all.count()

        return Response({
            'summary': {
                'grand_total': float(grand_total),
                'grand_count': grand_count,
                'by_method': [{'method': r['payment_method__name'] or 'Unknown', 'total': float(r['total'] or 0), 'count': r['count']} for r in by_method],
            },
            'rows': sorted(period_map.values(), key=lambda x: x['period']),
            'group_by': group_by,
        })

    @action(detail=False, methods=['get'], url_path='expense-analysis')
    def expense_analysis(self, request):
        """
        Expense analysis by account, department, period.
        Draws from LedgerEntry on EXPENSE type accounts.
        """
        from finance.models import Account
        from journals.models import LedgerEntry
        from django.db.models.functions import TruncMonth
        from django.db.models import Count

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        group_by = request.query_params.get('group_by', 'account')

        filters = Q(account__type='EXPENSE')
        if start_date:
            filters &= Q(date__gte=start_date)
        if end_date:
            filters &= Q(date__lte=end_date)

        entries = LedgerEntry.objects.filter(filters)
        grand_total = entries.aggregate(
            t=Sum('debit') - Sum('credit')
        )

        # by account
        by_account = entries.values(
            'account__id', 'account__name', 'account__sub_type'
        ).annotate(
            amount=Sum('debit') - Sum('credit'),
            count=Count('id')
        ).order_by('-amount')

        # monthly trend
        monthly = entries.annotate(month=TruncMonth('date')).values('month').annotate(
            amount=Sum('debit') - Sum('credit')
        ).order_by('month')

        rows = []
        for r in by_account:
            rows.append({
                'account_id': r['account__id'],
                'account_name': r['account__name'],
                'sub_type': r['account__sub_type'],
                'amount': float(r['amount'] or 0),
                'count': r['count'],
            })

        trend = []
        for r in monthly:
            trend.append({
                'month': r['month'].strftime('%Y-%m') if r['month'] else '',
                'amount': float(r['amount'] or 0),
            })

        total_expenses = sum(r['amount'] for r in rows if r['amount'] > 0)

        return Response({
            'summary': {
                'total_expenses': total_expenses,
                'account_count': len(rows),
            },
            'by_account': rows,
            'monthly_trend': trend,
        })

    @action(detail=False, methods=['get'], url_path='supplier-balances')
    def supplier_balances(self, request):
        """
        Supplier outstanding balances — unpaid/partially paid supplier invoices.
        """
        from payables.models import SupplierInvoice, Supplier
        from django.db.models import Count

        supplier_id = request.query_params.get('supplier')
        status_filter = request.query_params.get('status', 'unpaid')  # unpaid|all
        search = request.query_params.get('search', '')

        filters = Q()
        if status_filter == 'unpaid':
            filters &= Q(status__in=['APPROVED', 'PARTIALLY_PAID', 'OVERDUE', 'PENDING'])
        if supplier_id:
            filters &= Q(supplier_id=supplier_id)
        if search:
            filters &= Q(supplier__name__icontains=search)

        invoices = SupplierInvoice.objects.filter(filters).select_related('supplier').order_by('supplier__name', '-invoice_date')

        # Group by supplier
        supplier_map = {}
        for inv in invoices:
            sid = inv.supplier_id
            if sid not in supplier_map:
                supplier_map[sid] = {
                    'supplier_id': sid,
                    'supplier_name': inv.supplier.name if inv.supplier else 'Unknown',
                    'supplier_code': inv.supplier.code if inv.supplier else '',
                    'total_invoiced': 0,
                    'total_paid': 0,
                    'balance': 0,
                    'invoice_count': 0,
                    'invoices': []
                }
            total = float(getattr(inv, 'total_amount', 0) or 0)
            paid = float(getattr(inv, 'amount_paid', 0) or 0)
            balance = total - paid
            supplier_map[sid]['total_invoiced'] += total
            supplier_map[sid]['total_paid'] += paid
            supplier_map[sid]['balance'] += balance
            supplier_map[sid]['invoice_count'] += 1
            supplier_map[sid]['invoices'].append({
                'invoice_id': inv.id,
                'invoice_number': getattr(inv, 'invoice_number', str(inv.id)),
                'invoice_date': inv.invoice_date.isoformat() if hasattr(inv, 'invoice_date') and inv.invoice_date else None,
                'due_date': inv.due_date.isoformat() if hasattr(inv, 'due_date') and inv.due_date else None,
                'total_amount': total,
                'amount_paid': paid,
                'balance': balance,
                'status': inv.status,
            })

        rows = sorted(supplier_map.values(), key=lambda x: -x['balance'])
        grand_balance = sum(r['balance'] for r in rows)

        return Response({
            'summary': {'grand_balance': grand_balance, 'supplier_count': len(rows)},
            'rows': rows,
        })

    @action(detail=False, methods=['get'], url_path='customer-balances')
    def customer_balances(self, request):
        """
        Other (non-student) customer balances from the invoicing module.
        """
        try:
            from invoicing.models import Invoice, Customer
        except ImportError:
            return Response({'summary': {}, 'rows': []})

        search = request.query_params.get('search', '')
        status_filter = request.query_params.get('status', 'unpaid')

        filters = Q()
        if status_filter == 'unpaid':
            filters &= ~Q(status__in=['PAID', 'VOID', 'CANCELLED'])
        if search:
            filters &= Q(customer__name__icontains=search)

        try:
            invoices = Invoice.objects.filter(filters).select_related('customer').order_by('customer__name')
        except Exception:
            return Response({'summary': {}, 'rows': []})

        cust_map = {}
        for inv in invoices:
            cid = getattr(inv, 'customer_id', None)
            if cid not in cust_map:
                cust_map[cid] = {
                    'customer_id': cid,
                    'customer_name': inv.customer.name if inv.customer else 'Unknown',
                    'total_invoiced': 0, 'total_paid': 0, 'balance': 0, 'invoice_count': 0
                }
            total = float(getattr(inv, 'total_amount', 0) or 0)
            paid = float(getattr(inv, 'amount_paid', 0) or 0)
            cust_map[cid]['total_invoiced'] += total
            cust_map[cid]['total_paid'] += paid
            cust_map[cid]['balance'] += (total - paid)
            cust_map[cid]['invoice_count'] += 1

        rows = sorted(cust_map.values(), key=lambda x: -x['balance'])
        return Response({
            'summary': {'grand_balance': sum(r['balance'] for r in rows), 'customer_count': len(rows)},
            'rows': rows,
        })

    @action(detail=False, methods=['get'], url_path='top-defaulters')
    def top_defaulters(self, request):
        """
        Top N students with highest outstanding fee balances.
        """
        from fees.models import FeeInvoice
        from django.db.models import F

        n = int(request.query_params.get('limit', 20))
        academic_year_id = request.query_params.get('academic_year')
        term_id = request.query_params.get('term')

        filters = Q(balance__gt=0) & ~Q(status='VOID')
        if academic_year_id:
            filters &= Q(academic_year_id=academic_year_id)
        if term_id:
            filters &= Q(term_id=term_id)

        from django.db.models import Sum as DSum
        qs = FeeInvoice.objects.filter(filters).values(
            'student_id',
            'student__student__first_name',
            'student__student__last_name',
            'student__admission_number',
        ).annotate(
            total_invoiced=DSum('total_amount'),
            total_paid=DSum('paid_amount'),
            total_balance=DSum('balance'),
        ).order_by('-total_balance')[:n]

        rows = []
        for r in qs:
            first = r['student__student__first_name'] or ''
            last = r['student__student__last_name'] or ''
            
            # Get latest class session for the student
            latest_invoice = FeeInvoice.objects.filter(student_id=r['student_id']).select_related('class_session').order_by('-date_issued').first()
            class_session_name = latest_invoice.class_session.name if latest_invoice and latest_invoice.class_session else ''
            
            rows.append({
                'student_id': r['student_id'],
                'student_name': f"{first} {last}".strip(),
                'admission_number': r['student__admission_number'] or '',
                'class_session': class_session_name,
                'total_invoiced': float(r['total_invoiced'] or 0),
                'total_paid': float(r['total_paid'] or 0),
                'total_balance': float(r['total_balance'] or 0),
            })

        return Response({'rows': rows, 'count': len(rows)})
