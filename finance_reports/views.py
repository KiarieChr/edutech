from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Sum, Q
from decimal import Decimal
from .services import ReportService

class ReportViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

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
