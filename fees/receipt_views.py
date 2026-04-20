# fees/receipt_views.py
"""
ViewSet for Receipt Book Dashboard
Provides endpoints for receipt management and statistics.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Sum, Count, Q
from django.db.models.functions import Coalesce
from django.utils import timezone
from decimal import Decimal, InvalidOperation as DecimalException
from datetime import date, timedelta

from finance.models import Receipt, PaymentMethod, StudentPrepayment
from accounts.models import Student
from fees.models import FeeInvoice


class ReceiptViewSet(viewsets.ViewSet):
    """
    ViewSet for managing receipts in the Receipt Book Dashboard.
    
    Endpoints:
    - GET /receipts/ - List receipts with filters
    - POST /receipts/ - Create new receipt
    - GET /receipts/{id}/ - Get single receipt details
    - POST /receipts/{id}/post/ - Post a draft receipt
    - POST /receipts/{id}/reverse/ - Reverse a receipt
    - POST /receipts/{id}/print/ - Track print count
    - GET /receipts/summary/ - Dashboard statistics
    """
    
    def _apply_filters(self, queryset, request):
        """Apply common filters to receipt queryset"""
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        receipt_type = request.query_params.get('receipt_type')
        payment_method = request.query_params.get('payment_method')
        receipt_status = request.query_params.get('status')
        search = request.query_params.get('search', '').strip()
        
        # Date range filter
        if date_from:
            queryset = queryset.filter(received_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(received_date__lte=date_to)
        
        # Receipt type filter
        if receipt_type and receipt_type != 'All':
            queryset = queryset.filter(receipt_type=receipt_type)
        
        # Payment method filter
        if payment_method and payment_method != 'All':
            queryset = queryset.filter(payment_method__name__icontains=payment_method)
        
        # Status filter  
        if receipt_status and receipt_status != 'All':
            queryset = queryset.filter(status=receipt_status)
        
        # Search filter (receipt number, payer name, student name, reference)
        if search:
            queryset = queryset.filter(
                Q(receipt_number__icontains=search) |
                Q(payer_name__icontains=search) |
                Q(reference__icontains=search) |
                Q(student__student__first_name__icontains=search) |
                Q(student__student__last_name__icontains=search) |
                Q(student__admission_number__icontains=search)
            )
        
        return queryset
    
    def list(self, request):
        """
        Get list of receipts with filters and pagination.
        
        Query Params:
        - date_from: Filter receipts from this date
        - date_to: Filter receipts to this date
        - receipt_type: Filter by type (STUDENT_FEE, STUDENT_NON_FEE, SPONSOR, GENERAL)
        - payment_method: Filter by payment method name
        - status: Filter by status (DRAFT, ISSUED, PRINTED, REVERSED)
        - search: Search by receipt number, payer name, reference, student
        - page: Page number (default: 1)
        - page_size: Items per page (default: 20)
        """
        
        # Get all receipts
        receipts = Receipt.objects.select_related(
            'student',
            'student__student',
            'payment_method',
            'received_by',
            'term',
            'academic_year',
            'income_account'
        ).order_by('-received_date', '-receipt_number')
        
        # Apply filters
        receipts = self._apply_filters(receipts, request)
        
        # Simple pagination
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))
        
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        
        paginated_receipts = list(receipts[start_idx:end_idx])
        
        # Batch-compute student balances for balance summary on receipts
        student_ids = set(r.student_id for r in paginated_receipts if r.student_id)
        inv_bal_map = {}
        prep_map = {}
        if student_ids:
            for row in FeeInvoice.objects.filter(
                student_id__in=student_ids,
            ).exclude(status='VOID').values('student_id').annotate(
                total=Sum('balance'),
            ):
                inv_bal_map[row['student_id']] = float(row['total'] or 0)
            for row in StudentPrepayment.objects.filter(
                student_id__in=student_ids, is_fully_used=False,
            ).values('student_id').annotate(
                total=Sum('balance'),
            ):
                prep_map[row['student_id']] = float(row['total'] or 0)
        
        # Format response data
        results = []
        for receipt in paginated_receipts:
            data = {
                'id': receipt.id,
                'receipt_number': receipt.receipt_number,
                'date': receipt.received_date.strftime('%Y-%m-%d'),
                'receipt_type': receipt.get_receipt_type_display(),
                'payer_name': receipt.payer_name,
                'amount': float(receipt.amount_received),
                'payment_method': receipt.payment_method.name if receipt.payment_method else 'Unknown',
                'reference': receipt.reference,
                'issued_by': receipt.received_by.get_full_name if receipt.received_by else 'Unknown',
                'status': receipt.get_status_display(),
                'print_count': receipt.print_count,
                'notes': receipt.notes,
                'created_at': receipt.created_at.isoformat() if receipt.created_at else None,
                'reversal_reason': receipt.reversal_reason,
            }
            
            # Add student info for student receipts
            if receipt.student:
                data['student_id'] = receipt.student.id
                data['student_name'] = receipt.student.student.get_full_name if receipt.student.student else 'Unknown'
                data['admission_no'] = receipt.student.admission_number
                # Balance summary for receipt printing
                inv_bal = inv_bal_map.get(receipt.student_id, 0)
                prep_credit = prep_map.get(receipt.student_id, 0)
                current_balance = inv_bal - prep_credit
                data['balance_info'] = {
                    'previous_balance': round(current_balance + float(receipt.amount_received), 2),
                    'this_payment': float(receipt.amount_received),
                    'current_balance': round(current_balance, 2),
                }
            
            # Add type-specific fields
            if receipt.receipt_type == 'STUDENT_FEE':
                data['fee_category'] = receipt.fee_category
                data['term'] = receipt.term.name if receipt.term else None
                data['year'] = receipt.academic_year.name if receipt.academic_year else None
            elif receipt.receipt_type == 'STUDENT_NON_FEE':
                data['non_fee_category'] = receipt.non_fee_category
                data['description'] = receipt.description
            elif receipt.receipt_type == 'SPONSOR':
                data['sponsorship_type'] = receipt.sponsorship_type
                data['allocation_rule'] = receipt.allocation_rule
            elif receipt.receipt_type == 'GENERAL':
                data['income_account'] = receipt.income_account.name if receipt.income_account else None
                data['description'] = receipt.description
            
            results.append(data)
        
        return Response({
            'count': receipts.count(),
            'next': None,  # TODO: Implement proper pagination URLs
            'previous': None,
            'results': results
        })

    def create(self, request):
        """
        Create a new receipt.
        Payload depends on receipt_type.
        """
        try:
            data = request.data
            print("\n--- INCOMING RECEIPT PAYLOAD ---")
            print(data)
            print("--------------------------------\n")
            # Frontend service sends snake_case keys (receipt_type, etc.)
            receipt_type = data.get('receipt_type') or data.get('receiptType')
            
            # 1. Basic Validation
            if not receipt_type:
                return Response({'error': 'Receipt Type is required'}, status=status.HTTP_400_BAD_REQUEST)
                
            amount_val = data.get('amount_received') or data.get('amount') or 0
            try:
                amount = Decimal(str(amount_val))
            except (DecimalException, ValueError, TypeError):
                 return Response({'error': f'Invalid amount format: {amount_val}'}, status=status.HTTP_400_BAD_REQUEST)

            if amount <= 0:
                 return Response({'error': 'Amount must be greater than 0'}, status=status.HTTP_400_BAD_REQUEST)
                 
            # 2. Get Related Objects
            try:
                # Support both ID (payment_method_id) and Name (paymentMethod)
                pm_id = data.get('payment_method_id') or data.get('paymentMethodId')
                pm_name = data.get('paymentMethod') or data.get('payment_method')
                
                if pm_id:
                     payment_method = PaymentMethod.objects.get(pk=pm_id)
                elif pm_name:
                     payment_method = PaymentMethod.objects.get(name__iexact=pm_name)
                else: 
                     return Response({'error': 'Payment Method is required'}, status=status.HTTP_400_BAD_REQUEST)

            except (PaymentMethod.DoesNotExist, ValueError, TypeError):
                 return Response({'error': 'Invalid Payment Method'}, status=status.HTTP_400_BAD_REQUEST)
            
            student = None
            student_id = data.get('student_id') or data.get('studentId')
            if student_id:
                try:
                    student = Student.objects.get(pk=student_id)
                except Student.DoesNotExist:
                    return Response({'error': f'Student with ID {student_id} not found'}, status=status.HTTP_400_BAD_REQUEST)
            elif receipt_type == 'STUDENT_FEE':
                 return Response({'error': 'Student is required for Student Fee receipts'}, status=status.HTTP_400_BAD_REQUEST)
                
            # 3. Create Receipt
            # Generate Number (Mock-like for now or use utility)
            last_receipt = Receipt.objects.order_by('-id').first()
            last_num = int(last_receipt.receipt_number.split('-')[-1]) if last_receipt else 0
            new_num = f"RCT-2026-{str(last_num + 1).zfill(4)}"
            
            receipt = Receipt(
                receipt_number=new_num,
                received_date=data.get('received_date') or data.get('date', date.today()),
                receipt_type=receipt_type,
                payer_name=data.get('payer_name') or data.get('payerName'),
                student=student,
                amount_received=amount,
                payment_method=payment_method,
                reference=data.get('reference', ''),
                received_by=request.user if request.user.is_authenticated else None, # fallback?
                status='DRAFT', # Always create as Draft first
                notes=data.get('notes', 'No notes provided')
            )
            
            # Type specific fields
            if receipt_type == 'STUDENT_FEE':
                receipt.fee_category = data.get('fee_category') or data.get('feeCategory')
                # Term/Year handling - Frontend sends names or IDs. Service sends ID? 
                # Service: term_id, academic_year_id.
                
                term_id = data.get('term_id') or data.get('termId')
                year_id = data.get('academic_year_id') or data.get('academicYearId')

                if year_id:
                     from student_settings.models import AcademicYear
                     try:
                        receipt.academic_year = AcademicYear.objects.get(pk=year_id)
                     except AcademicYear.DoesNotExist:
                        pass
                
                if term_id:
                    from student_settings.models import Term
                    try:
                        receipt.term = Term.objects.get(pk=term_id)
                    except Term.DoesNotExist:
                        pass

            elif receipt_type == 'STUDENT_NON_FEE':
                receipt.non_fee_category = data.get('non_fee_category') or data.get('nonFeeCategory')
                receipt.description = data.get('description')
                
            elif receipt_type == 'SPONSOR':
                receipt.sponsorship_type = data.get('sponsorship_type') or data.get('sponsorshipType')
                receipt.allocation_rule = data.get('allocation_rule') or data.get('allocationRule')
            
            elif receipt_type == 'GENERAL':
                 receipt.description = data.get('description')
                 inc_id = data.get('income_account_id') or data.get('incomeAccountId')
                 if inc_id:
                     try:
                         receipt.income_account = Account.objects.get(pk=inc_id)
                     except Account.DoesNotExist:
                         pass

            # Save
            receipt.save()

            # 4. Handle Allocations
            allocations_data = data.get('allocations', [])
            if allocations_data and receipt_type == 'STUDENT_FEE' and student:
                from fees.models import FeeInvoiceItem
                from finance.models import ReceiptAllocation, StudentPrepayment
                
                total_allocated = Decimal(0)
                
                for alloc in allocations_data:
                    # Frontend parses breakdown: { feeCategoryId, amount, termId, academicYearId }
                    # We need to find the specific FeeInvoiceItem
                    try:
                        cat_id = alloc.get('feeCategoryId') or alloc.get('fee_category_id') # This is likely FeeItem ID or Name?
                        # Frontend sends FeeItem ID usually.
                        
                        alloc_amount = Decimal(str(alloc.get('amount', 0)))
                        if alloc_amount <= 0: continue
                        
                        # Find Invoice Item
                        # We filter by student and fee_item_id. 
                        # Ideally also by Term/Year if provided to differentiate past arrears
                        t_id = alloc.get('termId') or alloc.get('term_id')
                        y_id = alloc.get('academicYearId') or alloc.get('academic_year_id')
                        
                        query = FeeInvoiceItem.objects.filter(
                            invoice__student=student,
                            fee_item_id=cat_id,
                            invoice__status__in=['SENT', 'PARTIALLY_PAID', 'OVERDUE'] # Only open invoices? Or all?
                        )
                        
                        if t_id:
                            query = query.filter(invoice__term_id=t_id)
                        if y_id:
                            query = query.filter(invoice__academic_year_id=y_id)
                            
                        # Get the first match (FIFO usually)
                        offset_item = query.first()
                        
                        if offset_item:
                            # Create Allocation
                            ReceiptAllocation.objects.create(
                                receipt=receipt,
                                invoice=offset_item.invoice,
                                invoice_item=offset_item,
                                amount=alloc_amount
                            )
                            total_allocated += alloc_amount
                            
                            # Update Invoice Item / Invoice Balance? 
                            # Usually managed by signals or separate service update. 
                            # For now, let's assume ReceiptAllocation creation is the record.
                            # But we should update Invoice.paid_amount
                            inv = offset_item.invoice
                            inv.paid_amount += alloc_amount
                            inv.save() # This triggers status update in save()
                            
                    except Exception as e:
                        print(f"Error allocating item: {e}")
                        continue

                # Update Receipt Allocated Amount
                receipt.amount_allocated = total_allocated
                
                # Check for Prepayment (Overpayment)
                if amount > total_allocated:
                    surplus = amount - total_allocated
                    # Create Prepayment record
                    if surplus > 0:
                        StudentPrepayment.objects.create(
                           student=student,
                           receipt=receipt,
                           amount=surplus,
                           balance=surplus # Set initial balance
                        )
                
                receipt.save()
            
            # Check if receipt should be posted immediately
            requested_status = data.get('status', 'DRAFT')
            should_post = requested_status in ['POSTED', 'ISSUED']
            
            # If posting immediately, create journal entry
            if should_post:
                from finance.receipt_journal_service import ReceiptJournalService
                from django.utils import timezone
                
                try:
                    receipt.status = 'POSTED'
                    receipt.is_posted = True
                    receipt.posted_at = timezone.now()
                    receipt.save()
                    
                    # Create journal entry
                    journal_entry = ReceiptJournalService.create_receipt_journal_entry(
                        receipt=receipt,
                        user=request.user
                    )
                    
                    journal_info = {
                        'journal_entry_id': journal_entry.id,
                        'journal_reference': journal_entry.reference
                    }
                except Exception as e:
                    # Log but don't fail the receipt creation
                    print(f"Warning: Failed to create journal entry: {e}")
                    journal_info = {'journal_error': str(e)}
            else:
                journal_info = {}
            
            # Return created data (simplified)
            return Response({
                'id': receipt.id,
                'receipt_number': receipt.receipt_number,
                'status': receipt.status,
                'message': 'Receipt created successfully',
                **journal_info
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def post(self, request, pk=None):
        """
        Post a draft receipt to make it official and create journal entry.
        """
        from finance.receipt_journal_service import ReceiptJournalService
        from django.utils import timezone
        
        try:
            receipt = Receipt.objects.select_related(
                'payment_method',
                'student',
                'student__student',
                'income_account'
            ).prefetch_related(
                'allocations__invoice_item__fee_item__account',
                'prepayment_records'
            ).get(pk=pk)
        except Receipt.DoesNotExist:
            return Response({'detail': 'Receipt not found.'}, status=status.HTTP_404_NOT_FOUND)
            
        if receipt.status != 'DRAFT':
            return Response({'detail': f'Receipt is already {receipt.status}'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Update receipt status
            receipt.status = 'POSTED'
            receipt.is_posted = True
            receipt.posted_at = timezone.now()
            receipt.save()
            
            # Create journal entry
            journal_entry = ReceiptJournalService.create_receipt_journal_entry(
                receipt=receipt,
                user=request.user
            )
            
            # Serialize and return
            data = {
                'id': receipt.id,
                'receipt_number': receipt.receipt_number,
                'status': receipt.status,
                'journal_entry_id': journal_entry.id,
                'journal_reference': journal_entry.reference,
                'message': 'Receipt posted successfully and journal entry created'
            }
            return Response(data)
            
        except Exception as e:
            # Rollback will happen automatically due to transaction handling
            return Response({
                'detail': 'Failed to post receipt',
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


    @action(detail=True, methods=['post'])
    def reverse(self, request, pk=None):
        """Reverse a receipt"""
        try:
            receipt = Receipt.objects.get(pk=pk)
        except Receipt.DoesNotExist:
             return Response({'detail': 'Receipt not found.'}, status=status.HTTP_404_NOT_FOUND)

        if receipt.status == 'REVERSED':
            return Response({'detail': 'Receipt is already reversed.'}, status=status.HTTP_400_BAD_REQUEST)
            
        reason = request.data.get('reason', 'Reversed by user command')
        receipt.status = 'REVERSED'
        receipt.reversal_reason = reason
        receipt.save()
        
        # Logic to reverse accounting entries/allocations could go here
        
        return Response({'status': 'REVERSED', 'message': 'Receipt reversed'})

    @action(detail=True, methods=['post'])
    def print(self, request, pk=None):
        """
        Track print count and update receipt status.
        - If receipt is DRAFT or POSTED, mark as ISSUED on first print
        - Increment print_count for all prints
        """
        try:
            receipt = Receipt.objects.get(pk=pk)
            
            # If not yet issued, mark as ISSUED
            if receipt.status in ['DRAFT', 'POSTED']:
                receipt.status = 'ISSUED'
            
            # Increment print count
            receipt.print_count += 1
            receipt.save()
            
            return Response({
                'print_count': receipt.print_count,
                'status': receipt.status,
                'message': f'Receipt {"issued and " if receipt.print_count == 1 else ""}printed successfully'
            })
        except Receipt.DoesNotExist:
            return Response({'detail': 'Receipt not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Get receipt summary statistics for dashboard.
        
        Returns:
        {
            "total_receipts_today": int,
            "total_receipts_term": int,
            "total_amount_today": float,
            "total_amount_term": float,
            "student_fee_receipts": {"count": int, "amount": float},
            "non_fee_receipts": {"count": int, "amount": float},
            "sponsor_receipts": {"count": int, "amount": float},
            "general_receipts": {"count": int, "amount": float},
            "payment_method_breakdown": {...},
            "last_receipt_number": str,
            "next_receipt_number": str
        }
        """
        
        today = date.today()
        
        # Get receipts for today (not reversed)
        today_receipts = Receipt.objects.filter(
            received_date=today
        ).exclude(status='REVERSED')
        
        # Get receipts for current term (simplified - get this month's receipts)
        month_start = today.replace(day=1)
        term_receipts = Receipt.objects.filter(
            received_date__gte=month_start
        ).exclude(status='REVERSED')
        
        # Calculate totals
        today_stats = today_receipts.aggregate(
            count=Count('id'),
            total=Coalesce(Sum('amount_received'), Decimal('0.00'))
        )
        
        term_stats = term_receipts.aggregate(
            count=Count('id'),
            total=Coalesce(Sum('amount_received'), Decimal('0.00'))
        )
        
        # Breakdown by receipt type
        type_breakdown = {}
        for receipt_type, display_name in Receipt.RECEIPT_TYPES:
            stats = term_receipts.filter(receipt_type=receipt_type).aggregate(
                count=Count('id'),
                amount=Coalesce(Sum('amount_received'), Decimal('0.00'))
            )
            type_breakdown[receipt_type] = {
                'count': stats['count'],
                'amount': float(stats['amount'])
            }
        
        # Payment method breakdown
        payment_breakdown = {}
        for pm in PaymentMethod.objects.all():
            stats = term_receipts.filter(payment_method=pm).aggregate(
                count=Count('id'),
                amount=Coalesce(Sum('amount_received'), Decimal('0.00'))
            )
            if stats['count'] > 0:
                payment_breakdown[pm.name.lower()] = {
                    'count': stats['count'],
                    'amount': float(stats['amount']),
                    'percentage': round((float(stats['amount']) / float(term_stats['total']) * 100), 1) if float(term_stats['total']) > 0 else 0
                }
        
        # Get last receipt number
        last_receipt = Receipt.objects.order_by('-created_at').first()
        last_receipt_number = last_receipt.receipt_number if last_receipt else 'RCT-2026-0000'
        
        # TODO: Generate next receipt number properly
        next_receipt_number = 'RCT-2026-' + str(int(last_receipt_number.split('-')[-1]) + 1).zfill(4) if last_receipt else 'RCT-2026-0001'
        
        return Response({
            'total_receipts_today': today_stats['count'],
            'total_receipts_term': term_stats['count'],
            'total_amount_today': float(today_stats['total']),
            'total_amount_term': float(term_stats['total']),
            'student_fee_receipts': type_breakdown.get('STUDENT_FEE', {'count': 0, 'amount': 0}),
            'non_fee_receipts': type_breakdown.get('STUDENT_NON_FEE', {'count': 0, 'amount': 0}),
            'sponsor_receipts': type_breakdown.get('SPONSOR', {'count': 0, 'amount': 0}),
            'general_receipts': type_breakdown.get('GENERAL', {'count': 0, 'amount': 0}),
            'payment_method_breakdown': payment_breakdown,
            'last_receipt_number': last_receipt_number,
            'next_receipt_number': next_receipt_number,
            'active_receipt_book': 'Receipt Book 2026 - Current',
            'today_trend': '+0%',  # TODO: Calculate actual trend
            'term_trend': '+0%'
        })
