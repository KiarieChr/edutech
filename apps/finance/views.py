from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from .models import Account, AccountType, AccountSubType
from .serializers import AccountSerializer, AccountTypeOptionSerializer, AccountSubTypeOptionSerializer

class AccountViewSet(viewsets.ModelViewSet):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    pagination_class = None  # Always return all accounts (small dataset)
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['code', 'name', 'type', 'sub_type']
    ordering_fields = ['code', 'name', 'type']
    
    def get_permissions(self):
        """Allow read access without authentication, require auth for write operations"""
        if self.action in ['list', 'retrieve', 'types', 'sub_types', 'structure']:
            return [AllowAny()]
        return [IsAuthenticated()]
    
    @action(detail=False, methods=['get'])
    def types(self, request):
        """Return available Account Types"""
        data = [{'value': c[0], 'label': str(c[1])} for c in AccountType.choices]
        return Response(data)

    @action(detail=False, methods=['get'])
    def sub_types(self, request):
        """Return available Account Sub-Types"""
        data = [{'value': c[0], 'label': str(c[1])} for c in AccountSubType.choices]
        return Response(data) # Fixed typo here

    @action(detail=False, methods=['get'])
    def structure(self, request):
        """Return hierarchical structure of accounts"""
        # Optimized fetch for hierarchy could be done here.
        # For now, just a list is fine, frontend can build tree.
        serializer = self.get_serializer(self.queryset, many=True)
        return Response(serializer.data)

from .models import Tax, FinanceSettings, FiscalPeriod, Cashbook, PaymentMethod, SponsorType, Sponsorship
from .serializers import TaxSerializer, FinanceSettingsSerializer, FiscalPeriodSerializer, CashbookSerializer, PaymentMethodSerializer, SponsorTypeSerializer, SponsorshipSerializer

class TaxViewSet(viewsets.ModelViewSet):
    queryset = Tax.objects.all()
    serializer_class = TaxSerializer
    
    def get_permissions(self):
        """Allow read access without authentication"""
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAuthenticated()]

class FiscalPeriodViewSet(viewsets.ModelViewSet):
    queryset = FiscalPeriod.objects.all()
    serializer_class = FiscalPeriodSerializer

    def list(self, request, *args, **kwargs):
        # Auto-close expired periods before listing
        FiscalPeriod.auto_close_expired()
        return super().list(request, *args, **kwargs)

class CashbookViewSet(viewsets.ModelViewSet):
    queryset = Cashbook.objects.all()
    serializer_class = CashbookSerializer

    def perform_create(self, serializer):
        cashbook = serializer.save()
        
        # Handle Opening Balance
        if cashbook.opening_balance > 0 and not cashbook.is_opening_balance_posted:
            from journals.models import JournalEntry, JournalLine
            from datetime import date
            
            # 1. Find Equity Account (Retained Earnings or Opening Balance Equity)
            # Try finding an account with 'opening' or 'equity' in name, or create one?
            # For robustness, we check specifically for 'Retained Earnings' subtype or type Equity
            equity_acc = Account.objects.filter(sub_type='RETAINED_EARNINGS').first()
            if not equity_acc:
                equity_acc = Account.objects.filter(type='EQUITY').first()

            if equity_acc and cashbook.account:
                # 2. Create Journal using Service (safer)
                from journals.services import JournalService

                try:
                    today = cashbook.opening_balance_date or date.today()

                    journal_data = {
                        'date': today,
                        'reference': f"OPENBAL-{cashbook.id}",
                        'description': f"Opening Balance for {cashbook.name}",
                        'journal_type': 'GENERAL',
                        'status': 'DRAFT'
                    }

                    # Prepare lines
                    lines_data = [
                        {
                            'account': cashbook.account,  # Debit Asset
                            'debit': cashbook.opening_balance,
                            'credit': 0,
                            'description': "Opening Balance"
                        },
                        {
                            'account': equity_acc,  # Credit Equity
                            'debit': 0,
                            'credit': cashbook.opening_balance,
                            'description': "Opening Balance Offset"
                        }
                    ]

                    journal_data['lines'] = lines_data
                    entry = JournalService.create_journal_entry(
                        journal_data,
                        user=self.request.user if self.request.user.is_authenticated else None
                    )

                    # Explicitly post to ledger
                    JournalService.post_journal_entry(entry)

                    # Mark as posted
                    cashbook.is_opening_balance_posted = True
                    cashbook.save()

                except Exception as e:
                    print(f"Error posting opening balance: {e}")
                    # Log error but don't fail the cashbook creation


class PaymentMethodViewSet(viewsets.ModelViewSet):
    queryset = PaymentMethod.objects.all()
    serializer_class = PaymentMethodSerializer
    
    def get_permissions(self):
        """Allow read access without authentication"""
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAuthenticated()]
    
from .models import FinanceSettings
from .serializers import FinanceSettingsSerializer
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

class FinanceSettingsView(viewsets.ViewSet):
    """
    API endpoint that allows Finance Settings to be viewed or updated.
    GET  /api/finance/settings/ — authenticated users can read
    POST /api/finance/settings/ — admin-only update
    """
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        if self.action == 'list':
            return [IsAuthenticated()]
        return [IsAdminUser()]

    def list(self, request):
        # Always return the single instance
        settings = FinanceSettings.load()
        serializer = FinanceSettingsSerializer(settings)
        return Response(serializer.data)

    def create(self, request):
        # Update the single instance
        settings = FinanceSettings.load()
        serializer = FinanceSettingsSerializer(settings, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class SponsorTypeViewSet(viewsets.ModelViewSet):
    queryset = SponsorType.objects.all().select_related('clearing_account')
    serializer_class = SponsorTypeSerializer
    pagination_class = None
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAuthenticated()]

class SponsorshipViewSet(viewsets.ModelViewSet):
    queryset = Sponsorship.objects.all().select_related('sponsor_type', 'sponsor_type__clearing_account')
    serializer_class = SponsorshipSerializer
    pagination_class = None
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAuthenticated()]

   

