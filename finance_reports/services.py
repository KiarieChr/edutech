from django.db.models import Sum, Q, Value, DecimalField
from django.db.models.functions import Coalesce
from finance.models import Account, AccountType
from journals.models import LedgerEntry

class ReportService:
    @staticmethod
    def get_trial_balance(start_date=None, end_date=None):
        """
        Returns a list of accounts with their total debit, credit and net balance.
        Querying LedgerEntry.
        """
        filters = Q()
        if start_date:
            filters &= Q(date__gte=start_date)
        if end_date:
            filters &= Q(date__lte=end_date)
            
        accounts = Account.objects.filter(is_active=True).order_by('code')
        report_data = []
        
        total_dr_sum = 0
        total_cr_sum = 0
        
        for account in accounts:
            entries = LedgerEntry.objects.filter(filters, account=account)
            agg = entries.aggregate(
                sum_debit=Coalesce(Sum('debit'), Value(0, output_field=DecimalField())),
                sum_credit=Coalesce(Sum('credit'), Value(0, output_field=DecimalField()))
            )
            
            debit = agg['sum_debit']
            credit = agg['sum_credit']
            
            if debit == 0 and credit == 0:
                continue
                
            net = debit - credit
            
            report_data.append({
                'account_id': account.id,
                'code': account.code,
                'name': account.name,
                'type': account.type,
                'debit': debit,
                'credit': credit,
                'net_balance': net
            })
            
            total_dr_sum += debit
            total_cr_sum += credit
            
        return {
            'lines': report_data,
            'total_debit': total_dr_sum,
            'total_credit': total_cr_sum,
            'balanced': total_dr_sum == total_cr_sum
        }

    @staticmethod
    def get_balance_sheet(as_of_date):
        """
        Assets = Liabilities + Equity
        Returns detailed breakdown of accounts.
        """
        filters = Q()
        if as_of_date:
            filters &= Q(date__lte=as_of_date)
            
        # 1. Calculate Net Income (Revenue - Expense) for Retained Earnings
        ie_entries = LedgerEntry.objects.filter(
            filters, 
            Q(account__type__in=[AccountType.INCOME, AccountType.EXPENSE])
        )
        ie_agg = ie_entries.aggregate(
            sum_debit=Coalesce(Sum('debit'), Value(0, output_field=DecimalField())),
            sum_credit=Coalesce(Sum('credit'), Value(0, output_field=DecimalField()))
        )
        net_income = ie_agg['sum_credit'] - ie_agg['sum_debit']
        
        # 2. Helper to get accounts with balances for a set of types
        def get_category_details(valid_types, natural_debit=True):
            # Fetch all accounts of these types
            accounts = Account.objects.filter(type__in=valid_types).order_by('code')
            details = []
            total = 0
            
            for acc in accounts:
                # Aggregate ledger entries for this account
                # Optimization: Could do one big query with grouping, but loop is safer for logic first
                entries = LedgerEntry.objects.filter(filters, account=acc)
                agg = entries.aggregate(
                    dr=Coalesce(Sum('debit'), Value(0, output_field=DecimalField())),
                    cr=Coalesce(Sum('credit'), Value(0, output_field=DecimalField()))
                )
                
                if natural_debit:
                    bal = agg['dr'] - agg['cr']
                else:
                    bal = agg['cr'] - agg['dr']
                
                if bal != 0:
                    details.append({
                        'code': acc.code,
                        'name': acc.name,
                        'sub_type': acc.sub_type,
                        'balance': bal
                    })
                    total += bal
            
            return details, total

        # Assets (Natural Debit)
        asset_lines, total_assets = get_category_details([AccountType.ASSET], natural_debit=True)
        
        # Liabilities (Natural Credit)
        liab_lines, total_liabilities = get_category_details([AccountType.LIABILITY], natural_debit=False)
        
        # Equity (Natural Credit)
        equity_lines, total_equity = get_category_details([AccountType.EQUITY], natural_debit=False)
        
        # Add Net Income to Equity section
        # We append a pseudo-account for Net Income (Retained Earnings for current period)
        if net_income != 0:
            equity_lines.append({
                'code': 'RE-CURR', # Pseudo code
                'name': 'Net Income (Current Period)',
                'sub_type': 'RETAINED_EARNINGS',
                'balance': net_income
            })
            total_equity += net_income
        
        return {
            'assets': {
                'lines': asset_lines,
                'total': total_assets
            },
            'liabilities': {
                'lines': liab_lines,
                'total': total_liabilities
            },
            'equity': {
                'lines': equity_lines,
                'total': total_equity
            },
            'summary': {
                'total_assets': total_assets,
                'total_liabilities_equity': total_liabilities + total_equity,
                'check_diff': total_assets - (total_liabilities + total_equity)
            }
        }

    @staticmethod
    def get_income_statement(start_date, end_date):
        """
        Revenue - Expenses
        Returns detailed breakdown.
        """
        filters = Q(date__gte=start_date, date__lte=end_date)
        
        def get_category_details(acc_type, natural_credit=True):
            accounts = Account.objects.filter(type=acc_type).order_by('code')
            details = []
            total = 0
            
            for acc in accounts:
                entries = LedgerEntry.objects.filter(filters, account=acc)
                agg = entries.aggregate(
                    dr=Coalesce(Sum('debit'), Value(0, output_field=DecimalField())),
                    cr=Coalesce(Sum('credit'), Value(0, output_field=DecimalField()))
                )
                
                if natural_credit:
                    bal = agg['cr'] - agg['dr']
                else:
                    bal = agg['dr'] - agg['cr']
                
                if bal != 0:
                    details.append({
                        'code': acc.code,
                        'name': acc.name,
                        'sub_type': acc.sub_type,
                        'balance': bal
                    })
                    total += bal
                    
            return details, total

        # Income (Natural Credit)
        revenue_lines, total_revenue = get_category_details(AccountType.INCOME, natural_credit=True)
        
        # Expenses (Natural Debit)
        expense_lines, total_expenses = get_category_details(AccountType.EXPENSE, natural_credit=False)
        
        return {
            'revenue': {
                'lines': revenue_lines,
                'total': total_revenue
            },
            'expenses': {
                'lines': expense_lines,
                'total': total_expenses
            },
            'summary': {
                'total_revenue': total_revenue,
                'total_expenses': total_expenses,
                'net_income': total_revenue - total_expenses
            }
        }

    @staticmethod
    def get_cash_flow_statement(start_date, end_date):
        """
        Indirect Method Cash Flow Statement
        """
        filters = Q(date__gte=start_date, date__lte=end_date)
        
        # 1. Operating Activities
        # Start with Net Income
        income_stmt = ReportService.get_income_statement(start_date, end_date)
        net_income = income_stmt['summary']['net_income']
        
        # Adjustments for Non-Cash items (Depreciation usually, but we might not have it strictly separated yet)
        # For now, we assume simple cash basis or accrual where we adjust for working capital changes.
        
        def get_net_change(acc_types, sub_type=None):
            q = Q(account__type__in=acc_types)
            if sub_type:
                q &= Q(account__sub_type=sub_type)
            
            entries = LedgerEntry.objects.filter(filters, q)
            agg = entries.aggregate(
                sum_debit=Coalesce(Sum('debit'), Value(0, output_field=DecimalField())),
                sum_credit=Coalesce(Sum('credit'), Value(0, output_field=DecimalField()))
            )
            # For Assets: Credit (Decrease) is Cash In (Positive), Debit (Increase) is Cash Out (Negative)
            # For Liab/Equity: Credit (Increase) is Cash In (Positive), Debit (Decrease) is Cash Out (Negative)
            
            is_asset = AccountType.ASSET in acc_types
            
            if is_asset:
                return agg['sum_credit'] - agg['sum_debit']
            else:
                return agg['sum_credit'] - agg['sum_debit']

        # Working Capital Changes (Short Term Assets & Liabs)
        # AR (Asset): Decrease is +Cash
        change_ar = get_net_change([AccountType.ASSET], 'RECEIVABLE')
        # Inventory (Asset): Decrease is +Cash
        change_inventory = get_net_change([AccountType.ASSET], 'INVENTORY') 
        # AP (Liability): Increase is +Cash
        change_ap = get_net_change([AccountType.LIABILITY], 'PAYABLE')
        
        net_cash_operating = net_income + change_ar + change_inventory + change_ap
        
        # 2. Investing Activities (Long term assets)
        # Fixed Assets: Purchase (Dr) is -Cash, Sale (Cr) is +Cash
        net_cash_investing = get_net_change([AccountType.ASSET], 'FIXED_ASSET')
        
        # 3. Financing Activities (Long term liabs & Equity)
        # Loans (Liab): Borrow (Cr) is +Cash, Repay (Dr) is -Cash
        # Equity: Capital Inj (Cr) is +Cash, Drawings (Dr) is -Cash
        change_loans = get_net_change([AccountType.LIABILITY], 'LONG_TERM')
        change_equity = get_net_change([AccountType.EQUITY]) 
        # Note: Equity change here includes Retained Earnings (Net Income), which we already counted.
        # So strictly we should exclude Net Income from Equity change if it filters into RE account.
        # However, usually manual Equity entries (Capital/Drawings) are separate from P&L close.
        # We will assume direct Equity postings here.
        
        net_cash_financing = change_loans + change_equity
        
        net_change_cash = net_cash_operating + net_cash_investing + net_cash_financing
        
        # Opening Cash Balance
        # Get balance of all CASH/BANK accounts just before start_date
        cash_accounts_filter = Q(account__sub_type__in=['CASH', 'BANK'])
        opening_entries = LedgerEntry.objects.filter(date__lt=start_date).filter(cash_accounts_filter)
        opening_agg = opening_entries.aggregate(
            dr=Coalesce(Sum('debit'), Value(0, output_field=DecimalField())),
            cr=Coalesce(Sum('credit'), Value(0, output_field=DecimalField()))
        )
        opening_cash = opening_agg['dr'] - opening_agg['cr']
        
        closing_cash = opening_cash + net_change_cash
        
        return {
            'operating_activities': {
                'net_income': net_income,
                'adjustments': {
                    'accounts_receivable': change_ar,
                    'inventory': change_inventory,
                    'accounts_payable': change_ap,
                },
                'net_cash': net_cash_operating
            },
            'investing_activities': {
                'fixed_assets': net_cash_investing,
                'net_cash': net_cash_investing
            },
            'financing_activities': {
                'loans': change_loans,
                'equity': change_equity,
                'net_cash': net_cash_financing
            },
            'summary': {
                'net_change': net_change_cash,
                'opening_balance': opening_cash,
                'closing_balance': closing_cash
            }
        }

    @staticmethod
    def _get_account_balances(filters, account_q, natural_debit=True):
        """
        Helper to get detailed balances for a queryset of accounts.
        """
        accounts = Account.objects.filter(account_q).order_by('code')
        details = []
        total = 0
        
        for acc in accounts:
            entries = LedgerEntry.objects.filter(filters, account=acc)
            agg = entries.aggregate(
                dr=Coalesce(Sum('debit'), Value(0, output_field=DecimalField())),
                cr=Coalesce(Sum('credit'), Value(0, output_field=DecimalField()))
            )
            
            if natural_debit:
                bal = agg['dr'] - agg['cr']
            else:
                bal = agg['cr'] - agg['dr']
            
            if bal != 0:
                details.append({
                    'code': acc.code,
                    'name': acc.name,
                    'sub_type': acc.sub_type,
                    'balance': bal
                })
                total += bal
                
        return details, total

    @staticmethod
    def get_financial_notes(start_date, end_date):
        """
        Generates Notes to Financial Statements.
        Groups accounts by sub-types and provides details.
        """
        filters = Q(date__gte=start_date, date__lte=end_date)
        
        notes = []
        note_counter = 1

        def add_note(title, q_filter, natural_debit=True):
            nonlocal note_counter
            details, total = ReportService._get_account_balances(filters, q_filter, natural_debit)
            if details:
                notes.append({
                    'number': note_counter,
                    'title': title,
                    'accounts': details,
                    'total': total
                })
                note_counter += 1

        # Note 1: Cash and Cash Equivalents
        add_note("Cash and Cash Equivalents", Q(type=AccountType.ASSET, sub_type__in=['CASH', 'BANK']))

        # Note 2: Receivables
        add_note("Accounts Receivable", Q(type=AccountType.ASSET, sub_type='RECEIVABLE'))

        # Note 3: Payables
        add_note("Accounts Payable", Q(type=AccountType.LIABILITY, sub_type='PAYABLE'), natural_debit=False)

        # Note 4: Property, Plant and Equipment
        add_note("Property, Plant and Equipment", Q(type=AccountType.ASSET, sub_type='FIXED_ASSET'))
        
        # Note 5: Revenue
        add_note("Revenue", Q(type=AccountType.INCOME), natural_debit=False)

        # Note 6: Operating Expenses
        add_note("Operating Expenses", Q(type=AccountType.EXPENSE))

        return {
            'period': f"{start_date} to {end_date}",
            'notes': notes
        }

    @staticmethod
    def get_general_ledger(account_id, start_date=None, end_date=None):
        """
        Get detailed transactions for a specific account.
        """
        filters = Q(account_id=account_id)
        if start_date:
            filters &= Q(date__gte=start_date)
        if end_date:
            filters &= Q(date__lte=end_date)
            
        entries = LedgerEntry.objects.filter(filters).select_related('journal_entry').order_by('date', 'created_at')
        
        # Calculate opening balance
        opening_balance = 0
        if start_date:
            op_filters = Q(account_id=account_id, date__lt=start_date)
            op_agg = LedgerEntry.objects.filter(op_filters).aggregate(
                dr=Coalesce(Sum('debit'), Value(0, output_field=DecimalField())),
                cr=Coalesce(Sum('credit'), Value(0, output_field=DecimalField()))
            )
            # Determine natural balance based on account type?
            # Or just return net Dr-Cr.
            # Standard GL usually shows running balance.
            # Asset/Exp: Dr is +, Cr is -
            # Liab/Eq/Inc: Cr is +, Dr is -
            
            account = Account.objects.get(id=account_id)
            is_debit_natural = account.type in [AccountType.ASSET, AccountType.EXPENSE]
            
            if is_debit_natural:
                opening_balance = op_agg['dr'] - op_agg['cr']
            else:
                opening_balance = op_agg['cr'] - op_agg['dr']
        else:
            # Need account to know natural type
            try:
                account = Account.objects.get(id=account_id)
            except Account.DoesNotExist:
                return []
            is_debit_natural = account.type in [AccountType.ASSET, AccountType.EXPENSE]

        results = []
        running_balance = opening_balance
        
        for entry in entries:
            # Calculate running balance
            if is_debit_natural:
                change = entry.debit - entry.credit
            else:
                change = entry.credit - entry.debit
                
            running_balance += change
            
            results.append({
                'id': entry.id,
                'date': entry.date,
                'journal_no': f"JE-{entry.journal_entry.id}" if entry.journal_entry else '-',
                'description': entry.journal_entry.description if entry.journal_entry else '-',
                'reference': entry.journal_entry.reference if entry.journal_entry else '-',
                'debit': entry.debit,
                'credit': entry.credit,
                'balance': running_balance
            })
            
        return {
            'account_code': account.code,
            'account_name': account.name,
            'opening_balance': opening_balance,
            'lines': results,
            'closing_balance': running_balance
        }
