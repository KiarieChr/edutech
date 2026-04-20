from rest_framework import viewsets, status, decorators
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Sum, Count, Q, F
from django.utils import timezone
from datetime import timedelta
from .models import FeeStructure, FeeItem, FeeInvoice
from .serializers import FeeStructureSerializer, FeeItemCreateSerializer, FeeItemSerializer, FeeInvoiceSerializer


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def fee_insights(request):
    """
    Smart Fee Insights API
    
    Returns comprehensive fee and billing insights:
    - Students invoiced vs not invoiced in current term
    - Students needing manual invoicing
    - Fee defaulters from previous term
    - Supplier invoices due
    - Payment trends
    """
    today = timezone.now().date()
    
    try:
        from student_settings.models import Term, AcademicYear
        from academics.models import StudentSessionEnrollment, ClassSession
        from accounts.models import Student
        
        # Get current term
        current_term = Term.objects.filter(is_current=True).select_related('academic_year').first()
        current_year = current_term.academic_year if current_term else AcademicYear.objects.filter(is_current=True).first()
        
        insights = {
            "current_term": current_term.name if current_term else "N/A",
            "current_year": current_year.name if current_year else "N/A",
            "generated_at": timezone.now().isoformat(),
        }
        
        # 1. INVOICING INSIGHTS
        # Get total active students in current term sessions
        current_sessions = ClassSession.objects.filter(
            academic_year=current_year,
            term=current_term
        ) if current_year and current_term else ClassSession.objects.none()
        
        enrolled_students = StudentSessionEnrollment.objects.filter(
            session__in=current_sessions,
            status='active'
        ).values_list('student_id', flat=True).distinct()
        
        total_enrolled = len(enrolled_students)
        
        # Students with invoices this term
        invoiced_students = FeeInvoice.objects.filter(
            term=current_term,
            academic_year=current_year
        ).exclude(status='VOID').values_list('student_id', flat=True).distinct() if current_term else []
        
        invoiced_count = len(set(invoiced_students))
        not_invoiced_count = total_enrolled - invoiced_count
        
        # Students needing manual invoicing (enrolled but missing from active sessions or special cases)
        # These are students who are enrolled but don't have a matching fee structure
        manual_invoicing_needed = []
        enrolled_set = set(enrolled_students)
        invoiced_set = set(invoiced_students)
        not_invoiced_ids = enrolled_set - invoiced_set
        
        # Get names of students not invoiced (limit to 10 for display)
        not_invoiced_students = Student.objects.filter(
            id__in=list(not_invoiced_ids)[:20]
        ).select_related('student').values(
            'id', 
            'admission_number',
            'student__first_name',
            'student__last_name'
        )
        
        insights["invoicing"] = {
            "total_enrolled": total_enrolled,
            "invoiced": invoiced_count,
            "not_invoiced": not_invoiced_count,
            "invoicing_rate": round((invoiced_count / total_enrolled * 100), 1) if total_enrolled > 0 else 0,
            "needs_manual_invoicing": list(not_invoiced_students),
            "needs_manual_count": len(not_invoiced_ids)
        }
        
        # 2. FEE DEFAULTERS from current and previous terms
        # Current term defaulters (balance > 0 and past due)
        current_defaulters = FeeInvoice.objects.filter(
            term=current_term,
            balance__gt=0,
            due_date__lt=today
        ).exclude(status='VOID').select_related(
            'student__student'
        ).values(
            'student_id',
            'student__admission_number',
            'student__student__first_name',
            'student__student__last_name',
            'balance',
            'total_amount',
            'due_date'
        ).order_by('-balance')[:15] if current_term else []
        
        # Previous term defaulters (carried over)
        prev_term = Term.objects.filter(
            academic_year=current_year,
            start_date__lt=current_term.start_date if current_term else today
        ).order_by('-start_date').first() if current_year else None
        
        previous_term_defaulters = FeeInvoice.objects.filter(
            term=prev_term,
            balance__gt=0
        ).exclude(status='VOID').select_related(
            'student__student'
        ).values(
            'student_id',
            'student__admission_number',
            'student__student__first_name',
            'student__student__last_name',
            'balance',
            'total_amount'
        ).order_by('-balance')[:15] if prev_term else []
        
        # Aggregate defaulter stats
        total_current_arrears = FeeInvoice.objects.filter(
            term=current_term,
            balance__gt=0,
            due_date__lt=today
        ).exclude(status='VOID').aggregate(
            total=Sum('balance'),
            count=Count('id')
        ) if current_term else {'total': 0, 'count': 0}
        
        total_previous_arrears = FeeInvoice.objects.filter(
            term=prev_term,
            balance__gt=0
        ).exclude(status='VOID').aggregate(
            total=Sum('balance'),
            count=Count('id')
        ) if prev_term else {'total': 0, 'count': 0}
        
        insights["defaulters"] = {
            "current_term": {
                "term_name": current_term.name if current_term else "N/A",
                "count": total_current_arrears['count'] or 0,
                "total_arrears": float(total_current_arrears['total'] or 0),
                "top_defaulters": list(current_defaulters)
            },
            "previous_term": {
                "term_name": prev_term.name if prev_term else "N/A",
                "count": total_previous_arrears['count'] or 0,
                "total_arrears": float(total_previous_arrears['total'] or 0),
                "top_defaulters": list(previous_term_defaulters)
            }
        }
        
        # 3. FEE COLLECTION SUMMARY
        current_term_collection = FeeInvoice.objects.filter(
            term=current_term
        ).exclude(status='VOID').aggregate(
            total_billed=Sum('total_amount'),
            total_paid=Sum('paid_amount'),
            total_balance=Sum('balance')
        ) if current_term else {'total_billed': 0, 'total_paid': 0, 'total_balance': 0}
        
        insights["collection"] = {
            "total_billed": float(current_term_collection['total_billed'] or 0),
            "total_collected": float(current_term_collection['total_paid'] or 0),
            "total_outstanding": float(current_term_collection['total_balance'] or 0),
            "collection_rate": round(
                (float(current_term_collection['total_paid'] or 0) / 
                 float(current_term_collection['total_billed'] or 1) * 100), 1
            ) if current_term_collection['total_billed'] else 0
        }
        
        # 4. SUPPLIER/PAYABLES INSIGHTS (if payables app exists)
        try:
            from payables.models import SupplierInvoice
            
            due_supplier_invoices = SupplierInvoice.objects.filter(
                status__in=['PENDING', 'PARTIALLY_PAID'],
                due_date__lte=today + timedelta(days=7)  # Due within 7 days
            ).aggregate(
                count=Count('id'),
                total_due=Sum('balance')
            )
            
            overdue_supplier_invoices = SupplierInvoice.objects.filter(
                status__in=['PENDING', 'PARTIALLY_PAID'],
                due_date__lt=today
            ).aggregate(
                count=Count('id'),
                total_overdue=Sum('balance')
            )
            
            insights["payables"] = {
                "due_within_7_days": {
                    "count": due_supplier_invoices['count'] or 0,
                    "total": float(due_supplier_invoices['total_due'] or 0)
                },
                "overdue": {
                    "count": overdue_supplier_invoices['count'] or 0,
                    "total": float(overdue_supplier_invoices['total_overdue'] or 0)
                }
            }
        except ImportError:
            insights["payables"] = {
                "due_within_7_days": {"count": 0, "total": 0},
                "overdue": {"count": 0, "total": 0}
            }
        
        # 5. ATTENDANCE INSIGHTS (if attendance tracking exists)
        try:
            from student_management.models.class_session import SessionAttendance
            
            # Today's attendance
            today_attendance = SessionAttendance.objects.filter(date=today).aggregate(
                total=Count('id'),
                present=Count('id', filter=Q(status='present')),
                absent=Count('id', filter=Q(status='absent')),
                late=Count('id', filter=Q(status='late'))
            )
            
            # This week's attendance
            week_start = today - timedelta(days=today.weekday())
            week_attendance = SessionAttendance.objects.filter(
                date__gte=week_start,
                date__lte=today
            ).aggregate(
                total=Count('id'),
                present=Count('id', filter=Q(status='present')),
                absent=Count('id', filter=Q(status='absent'))
            )
            
            insights["attendance"] = {
                "today": {
                    "total": today_attendance['total'] or 0,
                    "present": today_attendance['present'] or 0,
                    "absent": today_attendance['absent'] or 0,
                    "late": today_attendance['late'] or 0,
                    "rate": round((today_attendance['present'] or 0) / (today_attendance['total'] or 1) * 100, 1)
                },
                "this_week": {
                    "total": week_attendance['total'] or 0,
                    "present": week_attendance['present'] or 0,
                    "absent": week_attendance['absent'] or 0,
                    "rate": round((week_attendance['present'] or 0) / (week_attendance['total'] or 1) * 100, 1)
                }
            }
        except (ImportError, Exception):
            insights["attendance"] = {
                "today": {"total": 0, "present": 0, "absent": 0, "late": 0, "rate": 0},
                "this_week": {"total": 0, "present": 0, "absent": 0, "rate": 0}
            }
        
        # 6. QUICK ACTIONS / ALERTS
        alerts = []
        
        if not_invoiced_count > 0:
            alerts.append({
                "type": "warning",
                "title": "Students Not Invoiced",
                "message": f"{not_invoiced_count} students enrolled but not yet invoiced for {current_term.name if current_term else 'this term'}",
                "action": "Generate bulk invoices",
                "action_url": "/dashboard/fees/invoices"
            })
        
        if total_current_arrears['count'] and total_current_arrears['count'] > 0:
            alerts.append({
                "type": "danger",
                "title": "Fee Defaulters",
                "message": f"{total_current_arrears['count']} students with overdue fees totaling KES {total_current_arrears['total'] or 0:,.0f}",
                "action": "View defaulters",
                "action_url": "/dashboard/fees/arrears"
            })
        
        if insights.get("payables", {}).get("overdue", {}).get("count", 0) > 0:
            alerts.append({
                "type": "danger",
                "title": "Overdue Supplier Payments",
                "message": f"{insights['payables']['overdue']['count']} supplier invoices overdue",
                "action": "View payables",
                "action_url": "/dashboard/finance/payables"
            })
        
        insights["alerts"] = alerts
        
        return Response({
            "success": True,
            "data": insights
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({
            "success": False,
            "error": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class FeeStructureViewSet(viewsets.ModelViewSet):
    queryset = FeeStructure.objects.all()
    serializer_class = FeeStructureSerializer
    filterset_fields = ['academic_year', 'term', 'grade', 'curriculum', 'status']
    
    def get_queryset(self):
        qs = super().get_queryset()
        # Optional: Order by most recent
        return qs.order_by('-academic_year__start_date', '-term__start_date')

    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response({"detail": f"Server Error: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

    @decorators.action(detail=True, methods=['post'])
    def clone(self, request, pk=None):
        """
        Clones a source structure to one or more target grades/terms/years.
        
        RULE: Only ACTIVE fee structures can be cloned.
        
        Payload:
        {
            "target_grade_ids": [1, 2],  # List of Grade IDs
            "target_academic_year": 5,
            "target_term": 2,
            "target_curriculum": 1, # Optional
            "copy_items": true,
            "percentage_increase": 10.0  # Optional price increase
        }
        """
        source = self.get_object()
        
        # Validation: Only ACTIVE structures can be cloned
        if source.status != 'ACTIVE':
            return Response(
                {"detail": "Only ACTIVE fee structures can be cloned."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        target_grade_ids = request.data.get('target_grade_ids', [])
        year_id = request.data.get('target_academic_year')
        term_id = request.data.get('target_term')
        curr_id = request.data.get('target_curriculum') or source.curriculum_id
        
        if not target_grade_ids or not year_id or not term_id:
            return Response(
                {"detail": "Missing target parameters (target_grade_ids, target_academic_year, target_term)."},
                status=status.HTTP_400_BAD_REQUEST
            )

        created_count = 0
        errors = []

        for grade_id in target_grade_ids:
            try:
                # Check if exists, if so skip or error? Let's skip if exists to avoid crash
                if FeeStructure.objects.filter(
                    academic_year_id=year_id,
                    term_id=term_id,
                    grade_id=grade_id,
                    curriculum_id=curr_id
                ).exists():
                    errors.append(f"Structure for Grade ID {grade_id} already exists.")
                    continue

                new_structure = FeeStructure.objects.create(
                    academic_year_id=year_id,
                    term_id=term_id,
                    grade_id=grade_id,
                    curriculum_id=curr_id,
                    currency=source.currency,
                    status='DRAFT'
                )
                
                # Copy Items with optional percentage increase
                pc_increase = request.data.get('percentage_increase', 0)
                new_structure.clone_from(source, percentage_increase=pc_increase)
                created_count += 1
                
            except Exception as e:
                errors.append(f"Grade ID {grade_id}: {str(e)}")

        return Response({
            "detail": f"Cloned to {created_count} classes.",
            "errors": errors
        }, status=status.HTTP_201_CREATED if created_count > 0 else status.HTTP_400_BAD_REQUEST)

class FeeItemViewSet(viewsets.ModelViewSet):
    queryset = FeeItem.objects.all()
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return FeeItemCreateSerializer
        return FeeItemSerializer
    
    def destroy(self, request, *args, **kwargs):
        # Prevent deletion if structure is active?
        # For now, allow configuration editing always unless locked.
        return super().destroy(request, *args, **kwargs)

class FeeInvoiceViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Fee Invoices.
    """
    queryset = FeeInvoice.objects.all()
    serializer_class = FeeInvoiceSerializer
    filterset_fields = ['student', 'status', 'academic_year', 'term', 'class_session']

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.select_related(
            'student',
            'student__student',
            'academic_year',
            'term',
            'class_session',
            'class_session__grade'
        )
        return queryset.order_by('-date_issued', '-created_at')


class PaymentMethodViewSet(viewsets.ViewSet):
    """
    ViewSet for managing Payment Methods.
    """
    def list(self, request):
        from finance.models import PaymentMethod
        methods = PaymentMethod.objects.filter(is_active=True).values(
            'id', 'name', 'is_for_payment', 'is_for_receipt'
        )
        return Response(list(methods))

    def create(self, request):
        from finance.models import PaymentMethod
        name = request.data.get('name')
        if not name:
            return Response({'detail': 'Payment method name is required'}, status=status.HTTP_400_BAD_REQUEST)

        method = PaymentMethod.objects.create(name=name)
        return Response({'id': method.id, 'name': method.name}, status=status.HTTP_201_CREATED)


from .services import BillingService
from rest_framework.decorators import action
from django.core.exceptions import ValidationError


class BillingViewSet(viewsets.ViewSet):
    """
    ViewSet for Billing Operations (Context Fetching & Invoice Generation)
    
    Endpoints:
    - GET  /billing/context/?student_id=X      - Get billing context for student
    - GET  /billing/search-students/?query=X   - Search students
    - GET  /billing/invoices/                  - List invoices
    - POST /billing/invoices/                  - Create single invoice
    - POST /billing/bulk-invoice/              - Bulk generate invoices for session
    """
    
    @action(detail=False, methods=['get'])
    def context(self, request):
        student_id = request.query_params.get('student_id')
        if not student_id:
            return Response({"detail": "Student ID required"}, status=status.HTTP_400_BAD_REQUEST)
        
        from .template_billing_service import TemplateBillingService
        context = TemplateBillingService.get_student_context(student_id)
        if not context:
            return Response(
                {"detail": "No active enrollment found for this student."}, 
                status=status.HTTP_404_NOT_FOUND
            )
            
        return Response(context)

    @action(detail=False, methods=['get'], url_path='search-students')
    def search_students(self, request):
        query = request.query_params.get('query', '').strip()
        if not query:
            return Response([])

        from accounts.models import Student
        from student_settings.models import Enrollment
        from django.db.models import Q

        students = Student.objects.filter(
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(admission_number__icontains=query)
        )[:20]  # Limit results

        results = []
        for s in students:
            # Use Student model properties to get current grade
            # This automatically handles:
            # - Active enrollments (current class)
            # - Deleted grade filtering
            # - Fallback to intake for new students
            current_grade = s.current_grade
            current_enrollment = s.current_enrollment
            
            grade_id = current_grade.id if current_grade else None
            grade_name = current_grade.name if current_grade else None
            grade_curriculum = current_grade.curriculum_id if current_grade else None
            
            results.append({
                "id": s.id,
                "text": f"{s.student.get_full_name} ({s.admission_number})", 
                "name": s.student.get_full_name if s.student else "Unknown",
                "admission_number": s.admission_number,
                
                # Context for Reporting Back
                "current_grade_id": grade_id,
                "current_grade_name": grade_name,
                "current_curriculum": grade_curriculum,
                "current_stream_id": current_enrollment.stream.id if current_enrollment and current_enrollment.stream else None,
                "current_stream_name": current_enrollment.stream.name if current_enrollment and current_enrollment.stream else None,
            })
            
        return Response(results)

    @action(detail=False, methods=['get', 'post'])
    def invoices(self, request):
        if request.method == 'GET':
            # List Invoices
            queryset = FeeInvoice.objects.all().select_related('student__student', 'class_session', 'term', 'academic_year')
            
            # Filtering
            student_id = request.query_params.get('student_id')
            status_param = request.query_params.get('status')
            term = request.query_params.get('term')
            year = request.query_params.get('year')
            search = request.query_params.get('search')
            
            if student_id:
                queryset = queryset.filter(student_id=student_id)
            if status_param:
                queryset = queryset.filter(status__iexact=status_param)
            if term:
                queryset = queryset.filter(term__name__icontains=term)
            if year:
                queryset = queryset.filter(academic_year__name__icontains=year)
            if search:
                queryset = queryset.filter(
                    student__student__username__icontains=search
                ) | queryset.filter(
                     student__admission_number__icontains=search
                ) | queryset.filter(
                    invoice_number__icontains=search
                )
            
            # Order by most recent
            queryset = queryset.order_by('-date_issued', '-id')

            serializer = FeeInvoiceSerializer(queryset, many=True)
            return Response(serializer.data)

        # POST - Create Invoice (template-first, fallback to legacy)
        try:
            billing_source = request.data.get('billing_source')
            if billing_source == 'template' and request.data.get('template_id'):
                from .template_billing_service import TemplateBillingService
                # Map frontend 'items' to template's 'line_item_ids'
                invoice_data = dict(request.data)
                items = invoice_data.pop('items', [])
                if items:
                    invoice_data['line_item_ids'] = [
                        i['id'] for i in items if i.get('id') is not None
                    ]
                invoice = TemplateBillingService.generate_invoice(invoice_data, user=request.user)
            else:
                invoice = BillingService.generate_invoice(request.data, user=request.user)
            return Response({
                "id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "amount": invoice.total_amount,
                "status": invoice.status
            }, status=status.HTTP_201_CREATED)
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"Billing Error: {e}")
            import traceback
            traceback.print_exc()
            return Response({"detail": "Failed to generate invoice."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], url_path='bulk-invoice')
    def bulk_invoice(self, request):
        """
        Bulk generate invoices for all active students in a ClassSession.
        
        POST /billing/bulk-invoice/
        {
            "session_id": 1,
            "due_date": "2026-02-15",
            "remarks": "Term 1 Fees 2026"
        }
        
        Returns:
        {
            "success": ["INV-2026-T1-0001", "INV-2026-T1-0002"],
            "skipped": [
                {"student_id": 5, "student_name": "John Doe", "reason": "Invoice already exists"}
            ],
            "summary": {
                "total_processed": 50,
                "invoices_created": 48,
                "students_skipped": 2
            }
        }
        """
        try:
            from .template_billing_service import TemplateBillingService
            result = TemplateBillingService.bulk_generate_invoices(request.data, user=request.user)
            return Response(result, status=status.HTTP_201_CREATED)
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"Bulk Billing Error: {e}")
            import traceback
            traceback.print_exc()
            return Response(
                {"detail": "Failed to generate bulk invoices."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
