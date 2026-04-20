"""
Views for the three-layer fee template architecture:
  VoteHead, GradeBand, FeeTemplate (+ TemplateLineItem), StudentFeeProfile
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.core.exceptions import ValidationError
from django.db.models import Q

from .models import VoteHead, GradeBand, FeeTemplate, TemplateLineItem, StudentFeeProfile
from .serializers import (
    VoteHeadSerializer,
    GradeBandSerializer,
    FeeTemplateSerializer, FeeTemplateWriteSerializer,
    TemplateLineItemSerializer, TemplateLineItemWriteSerializer,
    StudentFeeProfileSerializer,
)
from .template_billing_service import TemplateBillingService


# ── VoteHead ──────────────────────────────────────────────

class VoteHeadViewSet(viewsets.ModelViewSet):
    queryset = VoteHead.objects.select_related('default_account').all()
    serializer_class = VoteHeadSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    filterset_fields = ['is_active', 'is_optional', 'frequency']
    search_fields = ['name', 'code']

    @action(detail=False, methods=['post'])
    def auto_create_from_accounts(self, request):
        """
        Auto-create VoteHeads from student-related income/liability accounts
        that don't already have a VoteHead.
        POST /api/fees/vote-heads/auto_create_from_accounts/
        """
        from finance.models import Account
        existing_account_ids = set(
            VoteHead.objects.values_list('default_account_id', flat=True)
        )
        accounts = Account.objects.filter(
            is_student_related=True,
            type__in=['INCOME', 'LIABILITY']
        ).exclude(id__in=existing_account_ids)

        created = []
        for acc in accounts:
            code = acc.code[:20] if acc.code else acc.name[:3].upper()
            # Ensure unique code
            base_code = code
            counter = 1
            while VoteHead.objects.filter(code=code).exists():
                code = f"{base_code}{counter}"
                counter += 1
            vh = VoteHead.objects.create(
                name=acc.name,
                code=code,
                default_account=acc,
                frequency='RECURRING',
                is_optional=False,
                is_active=True,
            )
            created.append({'id': vh.id, 'name': vh.name, 'code': vh.code})

        return Response({
            'created_count': len(created),
            'created': created,
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


# ── GradeBand ─────────────────────────────────────────────

class GradeBandViewSet(viewsets.ModelViewSet):
    queryset = GradeBand.objects.prefetch_related('grades').all()
    serializer_class = GradeBandSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    filterset_fields = ['is_active']
    search_fields = ['name']


# ── FeeTemplate ───────────────────────────────────────────

class FeeTemplateViewSet(viewsets.ModelViewSet):
    queryset = FeeTemplate.objects.select_related(
        'grade_band', 'term', 'academic_year', 'curriculum', 'parent_template'
    ).prefetch_related(
        'line_items__vote_head',
        'line_items__override_account',
        'line_items__vote_head__default_account',
        'grades',
    ).all()
    permission_classes = [IsAuthenticated]
    filterset_fields = ['status', 'term', 'academic_year', 'curriculum', 'grade_band']
    search_fields = ['name']

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return FeeTemplateWriteSerializer
        return FeeTemplateSerializer

    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    # ── clone ─────────────────────────────────────────────
    @action(detail=True, methods=['post'])
    def clone(self, request, pk=None):
        """
        Clone a single template to a new term/year.

        POST /api/fees/fee-templates/{id}/clone/
        {
            "target_term": 5,
            "target_year": 3,
            "percentage_increase": 10.0
        }
        """
        source = self.get_object()
        from student_settings.models import Term, AcademicYear

        target_term_id = request.data.get('target_term')
        target_year_id = request.data.get('target_year')
        pct = request.data.get('percentage_increase', 0)

        if not target_term_id or not target_year_id:
            return Response(
                {'detail': 'target_term and target_year are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            target_term = Term.objects.get(pk=target_term_id)
            target_year = AcademicYear.objects.get(pk=target_year_id)
        except (Term.DoesNotExist, AcademicYear.DoesNotExist):
            return Response(
                {'detail': 'Invalid term or academic year ID.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Duplicate check
        if FeeTemplate.objects.filter(
            name=source.name,
            term=target_term,
            academic_year=target_year,
        ).exists():
            return Response(
                {'detail': f"Template '{source.name}' already exists for {target_term} {target_year}."},
                status=status.HTTP_409_CONFLICT,
            )

        new = source.clone_to(target_year, target_term, percentage_increase=pct)
        return Response(
            FeeTemplateSerializer(new).data,
            status=status.HTTP_201_CREATED,
        )

    # ── bulk_clone (year rollover) ────────────────────────
    @action(detail=False, methods=['post'], url_path='bulk-clone')
    def bulk_clone(self, request):
        """
        Clone ALL active templates from source term/year to target.

        POST /api/fees/fee-templates/bulk-clone/
        {
            "source_term": 2,
            "source_year": 1,
            "target_term": 5,
            "target_year": 3,
            "percentage_increase": 5.0
        }
        """
        from student_settings.models import Term, AcademicYear

        src_term_id = request.data.get('source_term')
        src_year_id = request.data.get('source_year')
        tgt_term_id = request.data.get('target_term')
        tgt_year_id = request.data.get('target_year')
        pct = request.data.get('percentage_increase', 0)

        if not all([src_term_id, src_year_id, tgt_term_id, tgt_year_id]):
            return Response(
                {'detail': 'source_term, source_year, target_term, target_year are all required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            tgt_term = Term.objects.get(pk=tgt_term_id)
            tgt_year = AcademicYear.objects.get(pk=tgt_year_id)
        except (Term.DoesNotExist, AcademicYear.DoesNotExist):
            return Response(
                {'detail': 'Invalid target term or year.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sources = FeeTemplate.objects.filter(
            term_id=src_term_id,
            academic_year_id=src_year_id,
            status='ACTIVE',
        ).prefetch_related('line_items', 'grades')

        created = []
        skipped = []

        for src in sources:
            if FeeTemplate.objects.filter(
                name=src.name, term=tgt_term, academic_year=tgt_year,
            ).exists():
                skipped.append({'name': src.name, 'reason': 'Already exists'})
                continue

            new = src.clone_to(tgt_year, tgt_term, percentage_increase=pct)
            created.append({'id': new.id, 'name': new.name})

        return Response({
            'created_count': len(created),
            'skipped_count': len(skipped),
            'created': created,
            'skipped': skipped,
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    # ── activate ──────────────────────────────────────────
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """
        Activate a DRAFT template (runs validation checks).
        """
        template = self.get_object()
        if template.status == 'ACTIVE':
            return Response({'detail': 'Already active.'})

        template.status = 'ACTIVE'
        try:
            template.clean()
            template.save()
        except ValidationError as e:
            template.status = 'DRAFT'
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(FeeTemplateSerializer(template).data)

    # ── deactivate ────────────────────────────────────────
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        template = self.get_object()
        template.status = 'INACTIVE'
        template.save(update_fields=['status', 'updated_at'])
        return Response(FeeTemplateSerializer(template).data)

    # ── apply to structures ───────────────────────────────
    @action(detail=True, methods=['post'], url_path='apply-to-structures')
    def apply_to_structures(self, request, pk=None):
        """
        Create/update legacy FeeStructure + FeeItem records from this template.

        POST /api/fees/fee-templates/{id}/apply-to-structures/
        {
            "grade_ids": [1, 2, 3],
            "academic_year": 1,
            "term": 2,
            "overwrite_existing": false
        }
        """
        from student_settings.models import GradeStructure, Term, AcademicYear
        from .models import FeeStructure, FeeItem

        template = self.get_object()
        grade_ids = request.data.get('grade_ids', [])
        year_id = request.data.get('academic_year')
        term_id = request.data.get('term')
        overwrite = request.data.get('overwrite_existing', False)

        if not grade_ids or not year_id or not term_id:
            return Response(
                {'detail': 'grade_ids, academic_year, and term are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            year = AcademicYear.objects.get(pk=year_id)
            term = Term.objects.get(pk=term_id)
        except (AcademicYear.DoesNotExist, Term.DoesNotExist):
            return Response(
                {'detail': 'Invalid academic_year or term.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        grades = GradeStructure.objects.filter(id__in=grade_ids)
        if not grades.exists():
            return Response(
                {'detail': 'No valid grades found.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        line_items = template.line_items.select_related(
            'vote_head', 'vote_head__default_account', 'override_account'
        ).all()

        created = []
        updated = []
        skipped = []

        for grade in grades:
            existing = FeeStructure.objects.filter(
                grade=grade, term=term, academic_year=year,
                curriculum=template.curriculum,
            ).first()

            if existing and not overwrite:
                skipped.append({'grade': grade.name, 'reason': 'Already exists'})
                continue

            if existing and overwrite:
                existing.items.all().delete()
                structure = existing
                structure.currency = template.currency
                structure.status = template.status
                structure.save(update_fields=['currency', 'status', 'updated_at'])
                label = updated
            else:
                structure = FeeStructure.objects.create(
                    grade=grade,
                    term=term,
                    academic_year=year,
                    curriculum=template.curriculum,
                    currency=template.currency,
                    status=template.status,
                )
                label = created

            for li in line_items:
                FeeItem.objects.create(
                    structure=structure,
                    name=li.vote_head.name,
                    amount=li.amount,
                    is_optional=not li.is_mandatory,
                    frequency=li.vote_head.frequency,
                    priority=li.priority,
                    account=li.override_account or li.vote_head.default_account,
                )

            label.append({'grade': grade.name, 'structure_id': structure.id})

        return Response({
            'created_count': len(created),
            'updated_count': len(updated),
            'skipped_count': len(skipped),
            'created': created,
            'updated': updated,
            'skipped': skipped,
        }, status=status.HTTP_201_CREATED if created or updated else status.HTTP_200_OK)

    # ── readiness check ───────────────────────────────────
    @action(detail=False, methods=['get'], url_path='readiness-check')
    def readiness_check(self, request):
        """
        GET /api/fees/fee-templates/readiness-check/?term=2&year=1
        """
        term_id = request.query_params.get('term')
        year_id = request.query_params.get('year')
        if not term_id or not year_id:
            return Response(
                {'detail': 'term and year query params required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        report = TemplateBillingService.readiness_check(term_id, year_id)
        return Response(report)


# ── TemplateLineItem ──────────────────────────────────────

class TemplateLineItemViewSet(viewsets.ModelViewSet):
    queryset = TemplateLineItem.objects.select_related(
        'vote_head', 'override_account', 'vote_head__default_account', 'template'
    ).all()
    permission_classes = [IsAuthenticated]
    filterset_fields = ['template', 'vote_head', 'is_mandatory']

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return TemplateLineItemWriteSerializer
        return TemplateLineItemSerializer


# ── StudentFeeProfile ────────────────────────────────────

class StudentFeeProfileViewSet(viewsets.ModelViewSet):
    queryset = StudentFeeProfile.objects.prefetch_related('custom_items').all()
    serializer_class = StudentFeeProfileSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['is_boarder', 'uses_transport']
    search_fields = ['student__student__first_name', 'student__student__last_name', 'student__admission_number']

    def get_queryset(self):
        qs = super().get_queryset()
        student_id = self.request.query_params.get('student_id')
        if student_id:
            qs = qs.filter(student_id=student_id)
        return qs


# ── Rollover ──────────────────────────────────────────────

from rest_framework.decorators import api_view, permission_classes as perm_dec


@api_view(['POST'])
@perm_dec([IsAuthenticated])
def fee_rollover(request):
    """
    POST /api/fees/rollover/
    {
        "from_year": 1,
        "to_year": 3,
        "percentage_increase": 5.0,
        "dry_run": true
    }
    """
    from_year = request.data.get('from_year')
    to_year = request.data.get('to_year')
    pct = request.data.get('percentage_increase', 0)
    dry_run = request.data.get('dry_run', False)

    if not from_year or not to_year:
        return Response(
            {'detail': 'from_year and to_year are required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        report = TemplateBillingService.rollover(from_year, to_year, pct, dry_run=dry_run)
        return Response(report)
    except ValidationError as e:
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
