from rest_framework import viewsets, status, decorators
from rest_framework.response import Response
from .models import FeeStructure, FeeItem, FeeInvoice
from .serializers import FeeStructureSerializer, FeeItemCreateSerializer, FeeItemSerializer, FeeInvoiceSerializer

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
        Payload:
        {
            "target_grade_ids": [1, 2],  # List of Grade IDs
            "target_academic_year": 5,
            "target_term": 2,
            "target_curriculum": 1, # Optional
            "copy_items": true
        }
        """
        source = self.get_object()
        
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
        methods = PaymentMethod.objects.filter(is_active=True).values('id', 'name', 'description')
        return Response(list(methods))

    def create(self, request):
        from finance.models import PaymentMethod
        name = request.data.get('name')
        description = request.data.get('description', '')
        if not name:
            return Response({'detail': 'Payment method name is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        method = PaymentMethod.objects.create(name=name, description=description)
        return Response({'id': method.id, 'name': method.name, 'description': method.description}, status=status.HTTP_201_CREATED)


from .services import BillingService
from rest_framework.decorators import action
from rest_framework.decorators import action
from django.core.exceptions import ValidationError

class BillingViewSet(viewsets.ViewSet):
    """
    ViewSet for Billing Operations (Context Fetching & Invoice Generation)
    """
    
    @action(detail=False, methods=['get'])
    def context(self, request):
        student_id = request.query_params.get('student_id')
        if not student_id:
            return Response({"detail": "Student ID required"}, status=status.HTTP_400_BAD_REQUEST)
        
        context = BillingService.get_student_context(student_id)
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

        # POST - Create Invoice
        try:
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
            return Response({"detail": "Failed to generate invoice."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
