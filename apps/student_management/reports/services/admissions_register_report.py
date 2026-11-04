"""
Admissions Register Report Service
"""
from typing import Dict, Any, List
from django.db.models import QuerySet, Count, Q, Exists, OuterRef
from student_management.models import Admission, Parent
from student_settings.models import AcademicYear
from student_management.reports.base import BaseStudentReport


class AdmissionsRegisterReport(BaseStudentReport):
    report_id = "admissions-register"
    title = "Official Admissions Register"
    description = "Official statutory admissions register documenting newly admitted students within a period."

    def get_base_queryset(self) -> QuerySet:
        qs = Admission.objects.select_related(
            'student__student', 'student__intake', 'student__campus',
            'application__applying_for_grade', 'application__applying_for_curriculum',
            'campus', 'admitted_by'
        ).prefetch_related(
            'student__parents'
        )

        date_from = self.filters.get("date_from")
        date_to = self.filters.get("date_to")
        academic_year = self.filters.get("academic_year")
        grade = self.filters.get("grade")
        stream = self.filters.get("stream")
        gender = self.filters.get("gender")
        entry_type = self.filters.get("entry_type")
        status = self.filters.get("status")
        campus = self.filters.get("campus")
        search = self.filters.get("search")

        # 1. Date Range
        if date_from:
            qs = qs.filter(admission_date__gte=date_from)
        if date_to:
            qs = qs.filter(admission_date__lte=date_to)

        # 2. Academic Year: Filter admissions that occurred within the academic year calendar bounds
        if academic_year:
            try:
                ay = AcademicYear.objects.filter(id=academic_year).first()
                if ay and ay.start_date and ay.end_date:
                    qs = qs.filter(admission_date__gte=ay.start_date, admission_date__lte=ay.end_date)
            except Exception:
                pass

        # 3. Entry Grade at Admission
        if grade:
            qs = qs.filter(application__applying_for_grade_id=grade)

        # 4. Current Class Stream (active, non-deleted enrollment)
        if stream:
            qs = qs.filter(
                student__enrollments__stream_id=stream,
                student__enrollments__is_active=True,
                student__enrollments__is_deleted=False
            )

        # 5. Gender
        if gender:
            qs = qs.filter(student__student__gender=gender)

        # 6. Admission Category (New Admission vs Transfer In)
        if entry_type:
            entry_type_lower = entry_type.lower()
            if 'transfer' in entry_type_lower:
                qs = qs.filter(
                    Q(application__is_transfer=True) |
                    (Q(student__previous_school_name__isnull=False) & ~Q(student__previous_school_name=''))
                )
            elif 'new' in entry_type_lower:
                qs = qs.filter(
                    Q(application__is_transfer=False) &
                    (Q(student__previous_school_name__isnull=True) | Q(student__previous_school_name=''))
                )

        # 7. Student Status
        if status:
            qs = qs.filter(student__status=status)

        # 8. Guardian & Student Search using Exists() subquery to avoid reverse FK row duplication
        if search:
            search = search.strip()
            parent_match_subquery = Parent.objects.filter(
                student_id=OuterRef('student_id')
            ).filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(phone__icontains=search) |
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(user__phone__icontains=search)
            )

            qs = qs.filter(
                Q(admission_number__icontains=search) |
                Q(student__student__first_name__icontains=search) |
                Q(student__student__last_name__icontains=search) |
                Q(student__previous_school_name__icontains=search) |
                Exists(parent_match_subquery)
            )

        # 9. Server-enforced campus access control
        from core.campus_filter import get_effective_campus_id_for_user
        effective_campus_id = get_effective_campus_id_for_user(self.user, self.filters)
        if effective_campus_id:
            qs = qs.filter(campus_id=effective_campus_id)

        # Strictly deterministic ordering for stable pagination (no row jumping across pages)
        return qs.order_by('-admission_date', '-id')

    def get_summary_metrics(self, queryset: QuerySet) -> Dict[str, Any]:
        """Compute full dataset aggregates in a single database round-trip (O(1) SQL execution)."""
        metrics = queryset.aggregate(
            total_admitted=Count('id'),
            male_count=Count('id', filter=Q(student__student__gender='M')),
            female_count=Count('id', filter=Q(student__student__gender='F')),
            transfers_in=Count(
                'id',
                filter=Q(application__is_transfer=True) | (
                    Q(student__previous_school_name__isnull=False) & ~Q(student__previous_school_name='')
                )
            )
        )

        return {
            "total_admitted": metrics['total_admitted'] or 0,
            "male_count": metrics['male_count'] or 0,
            "female_count": metrics['female_count'] or 0,
            "transfers_in": metrics['transfers_in'] or 0,
        }

    def get_columns(self) -> List[Dict[str, str]]:
        return [
            {"key": "admission_number", "label": "Adm No.", "align": "left"},
            {"key": "admission_date", "label": "Admission Date", "align": "center"},
            {"key": "student_name", "label": "Student Name", "align": "left"},
            {"key": "gender", "label": "Gender", "align": "center"},
            {"key": "entry_grade", "label": "Entry Grade", "align": "left"},
            {"key": "birth_certificate", "label": "Birth Cert No.", "align": "left"},
            {"key": "previous_school", "label": "Previous School", "align": "left"},
            {"key": "guardian_phone", "label": "Guardian Contact", "align": "left"},
            {"key": "admitted_by", "label": "Processed By", "align": "left"},
        ]

    def serialize_record(self, adm: Admission) -> Dict[str, Any]:
        student = adm.student
        user_obj = student.student
        full_name = f"{user_obj.first_name} {user_obj.last_name}".strip() or user_obj.username

        entry_grade = "—"
        if hasattr(adm, 'application') and adm.application and adm.application.applying_for_grade:
            entry_grade = adm.application.applying_for_grade.name

        parents = list(student.parents.all())
        guardian_phone = parents[0].phone if parents and parents[0].phone else "—"

        processed_by = adm.admitted_by.get_full_name if adm.admitted_by else "—"

        return {
            "id": adm.id,
            "admission_number": adm.admission_number,
            "admission_date": str(adm.admission_date) if adm.admission_date else "—",
            "student_name": full_name,
            "gender": user_obj.gender or "—",
            "entry_grade": entry_grade,
            "birth_certificate": student.birth_certificate_number or "—",
            "previous_school": student.previous_school_name or "—",
            "guardian_phone": guardian_phone,
            "admitted_by": processed_by,
        }
