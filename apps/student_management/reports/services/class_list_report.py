"""
Official Class List Report Service
"""
from typing import Dict, Any, List
from datetime import date
from django.db.models import QuerySet, Count, Q
from student_settings.models import Enrollment
from student_management.reports.base import BaseStudentReport


class OfficialClassListReport(BaseStudentReport):
    report_id = "official-class-list"
    title = "Official Class List"
    description = "Official classroom and stream attendance and assessment roster."

    def get_base_queryset(self) -> QuerySet:
        qs = Enrollment.objects.filter(is_active=True, is_deleted=False).select_related(
            'student__student', 'student__campus',
            'grade', 'stream', 'term', 'academic_year', 'campus'
        )

        academic_year = self.filters.get("academic_year")
        term = self.filters.get("term")
        grade = self.filters.get("grade")
        stream = self.filters.get("stream")
        gender = self.filters.get("gender")
        stay_status = self.filters.get("stay_status")
        campus = self.filters.get("campus")
        search = self.filters.get("search")

        if academic_year:
            qs = qs.filter(academic_year_id=academic_year)
        if term:
            qs = qs.filter(term_id=term)
        if grade:
            qs = qs.filter(grade_id=grade)
        if stream:
            qs = qs.filter(stream_id=stream)
        if gender:
            qs = qs.filter(student__student__gender=gender)
        if stay_status:
            qs = qs.filter(stay_status=stay_status)
        if search:
            qs = qs.filter(
                Q(student__admission_number__icontains=search) |
                Q(student__student__first_name__icontains=search) |
                Q(student__student__last_name__icontains=search)
            )

        # Server-enforced campus access control
        from core.campus_filter import get_effective_campus_id_for_user
        effective_campus_id = get_effective_campus_id_for_user(self.user, self.filters)
        if effective_campus_id:
            qs = qs.filter(campus_id=effective_campus_id)

        return qs.order_by('grade__level_order', 'stream__name', 'student__student__first_name')

    def get_summary_metrics(self, queryset: QuerySet) -> Dict[str, Any]:
        """Compute full dataset aggregates in a single database aggregation."""
        aggs = queryset.aggregate(
            total=Count('id'),
            males=Count('id', filter=Q(student__student__gender='M')),
            females=Count('id', filter=Q(student__student__gender='F')),
            day_scholars=Count('id', filter=Q(stay_status='day_scholar')),
            boarders=Count('id', filter=Q(stay_status='boarder')),
        )
        return {
            "total_enrolled": aggs["total"],
            "male_count": aggs["males"],
            "female_count": aggs["females"],
            "day_scholars": aggs["day_scholars"],
            "boarders": aggs["boarders"],
        }

    def get_columns(self) -> List[Dict[str, str]]:
        return [
            {"key": "admission_number", "label": "Adm No.", "align": "left"},
            {"key": "student_name", "label": "Student Name", "align": "left"},
            {"key": "gender", "label": "Gender", "align": "center"},
            {"key": "grade", "label": "Grade/Class", "align": "left"},
            {"key": "stream", "label": "Stream", "align": "left"},
            {"key": "stay_status", "label": "Stay Status", "align": "left"},
            {"key": "enrollment_date", "label": "Enrolled On", "align": "center"},
            {"key": "emergency_contact", "label": "Emergency Phone", "align": "left"},
        ]

    def serialize_record(self, enr: Enrollment) -> Dict[str, Any]:
        student = enr.student
        user_obj = student.student
        full_name = f"{user_obj.first_name} {user_obj.last_name}".strip() or user_obj.username

        stay_status_display = enr.get_stay_status_display() if hasattr(enr, 'get_stay_status_display') else (enr.stay_status or "Day Scholar")

        return {
            "id": enr.id,
            "admission_number": student.admission_number or "—",
            "student_name": full_name,
            "gender": user_obj.gender or "—",
            "grade": enr.grade.name if enr.grade else "—",
            "stream": enr.stream.name if enr.stream else "—",
            "stay_status": stay_status_display,
            "enrollment_date": str(enr.enrollment_date) if enr.enrollment_date else "—",
            "emergency_contact": student.emergency_contact_phone or "—",
        }
