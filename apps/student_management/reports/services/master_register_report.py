"""
Student Master Register Report Service
"""
from typing import Dict, Any, List
from datetime import date
from django.db.models import QuerySet, Count, Q
from student_management.models import Student
from student_management.reports.base import BaseStudentReport


class StudentMasterRegisterReport(BaseStudentReport):
    report_id = "student-master-register"
    title = "Student Master Register"
    description = "Official comprehensive school register of all enrolled and past students."

    def get_base_queryset(self) -> QuerySet:
        qs = Student.objects.select_related(
            'student', 'campus', 'intake'
        ).prefetch_related(
            'enrollments__grade',
            'enrollments__stream',
            'enrollments__academic_year',
            'enrollments__term',
            'parents'
        )

        # Filters
        academic_year = self.filters.get("academic_year")
        grade = self.filters.get("grade")
        stream = self.filters.get("stream")
        gender = self.filters.get("gender")
        status = self.filters.get("status")
        campus = self.filters.get("campus")
        search = self.filters.get("search")

        if academic_year:
            qs = qs.filter(enrollments__academic_year_id=academic_year)
        if grade:
            qs = qs.filter(enrollments__grade_id=grade)
        if stream:
            qs = qs.filter(enrollments__stream_id=stream)
        if gender:
            qs = qs.filter(student__gender=gender)
        if status:
            qs = qs.filter(status=status)
        if search:
            qs = qs.filter(
                Q(admission_number__icontains=search) |
                Q(student__first_name__icontains=search) |
                Q(student__last_name__icontains=search)
            )

        # Server-enforced campus access control
        from core.campus_filter import get_effective_campus_id_for_user
        effective_campus_id = get_effective_campus_id_for_user(self.user, self.filters)
        if effective_campus_id:
            qs = qs.filter(campus_id=effective_campus_id)

        return qs.distinct().order_by('admission_number')

    def get_summary_metrics(self, queryset: QuerySet) -> Dict[str, Any]:
        """Compute full dataset aggregates in a single database aggregation."""
        aggs = queryset.aggregate(
            total=Count('id'),
            males=Count('id', filter=Q(student__gender='M')),
            females=Count('id', filter=Q(student__gender='F')),
            active_count=Count('id', filter=Q(status='active')),
        )
        return {
            "total_students": aggs["total"],
            "male_count": aggs["males"],
            "female_count": aggs["females"],
            "active_students": aggs["active_count"],
        }

    def get_columns(self) -> List[Dict[str, str]]:
        return [
            {"key": "admission_number", "label": "Adm No.", "align": "left"},
            {"key": "full_name", "label": "Student Name", "align": "left"},
            {"key": "gender", "label": "Gender", "align": "center"},
            {"key": "age", "label": "Age", "align": "center"},
            {"key": "birth_certificate_number", "label": "Birth Cert No.", "align": "left"},
            {"key": "current_grade", "label": "Class/Grade", "align": "left"},
            {"key": "current_stream", "label": "Stream", "align": "left"},
            {"key": "guardian_name", "label": "Primary Guardian", "align": "left"},
            {"key": "guardian_phone", "label": "Guardian Phone", "align": "left"},
            {"key": "status", "label": "Status", "align": "center"},
        ]

    def serialize_record(self, student: Student) -> Dict[str, Any]:
        user_obj = student.student
        today = date.today()
        age = None
        if student.date_of_birth:
            dob = student.date_of_birth
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

        # Current enrollment
        active_enr = None
        for enr in student.enrollments.all():
            if enr.is_active and not enr.is_deleted:
                active_enr = enr
                break

        grade_name = active_enr.grade.name if active_enr and active_enr.grade else "—"
        stream_name = active_enr.stream.name if active_enr and active_enr.stream else "—"

        # Guardian info
        parents = list(student.parents.all())
        guardian_name = f"{parents[0].first_name} {parents[0].last_name}".strip() if parents else "—"
        guardian_phone = parents[0].phone if parents and parents[0].phone else "—"

        full_name = f"{user_obj.first_name} {user_obj.last_name}".strip() or user_obj.username

        return {
            "id": student.id,
            "admission_number": student.admission_number or "—",
            "full_name": full_name,
            "gender": user_obj.gender or "—",
            "age": age if age is not None else "—",
            "birth_certificate_number": student.birth_certificate_number or "—",
            "current_grade": grade_name,
            "current_stream": stream_name,
            "guardian_name": guardian_name,
            "guardian_phone": guardian_phone,
            "status": student.get_status_display() if hasattr(student, 'get_status_display') else student.status.title(),
        }
