from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import datetime, timedelta
from .models import JournalEntry
from .serializers import JournalEntrySerializer
from .services import JournalService


class JournalEntryPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


class JournalEntryViewSet(viewsets.ModelViewSet):
    queryset = JournalEntry.objects.all()
    serializer_class = JournalEntrySerializer
    pagination_class = JournalEntryPagination
    filterset_fields = ['date', 'journal_type', 'status']
    search_fields = ['description', 'reference']
    ordering = ['-date', '-created_at']
    
    def get_queryset(self):
        """
        Optionally filter by date range.
        Query params: start_date, end_date
        """
        queryset = super().get_queryset()
        
        # Date range filtering
        start_date = self.request.query_params.get('start_date', None)
        end_date = self.request.query_params.get('end_date', None)
        
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)
        
        # Default to current month if no dates specified
        if not start_date and not end_date:
            today = timezone.now().date()
            first_day = today.replace(day=1)
            queryset = queryset.filter(date__gte=first_day)
        
        return queryset

    def perform_create(self, serializer):
        # We can use the serializer's save which calls create(), 
        # but we also need to attach the user.
        serializer.save(created_by=self.request.user if self.request.user.is_authenticated else None)

    @action(detail=True, methods=['post'])
    def post(self, request, pk=None):
        """
        Custom action to POST a journal entry (finalize it).
        """
        entry = self.get_object()
        try:
            JournalService.post_journal_entry(entry)
            serializer = self.get_serializer(entry)
            return Response(serializer.data)
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
