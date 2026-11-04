"""
Student & Guardian Contact Directory Report Service
"""
from typing import Dict, Any, List
from django.db.models import QuerySet, Count, Q
from student_management.models import Student
from student_management.reports.base import BaseStudentReport


class ContactDirectoryReport(BaseStudentReport):
    report_id = "contact-directory"
    title = "Student & Guardian Contact Directory"
    description = "Official administrative and emergency contact directory for guardians and students."

    def get_base_queryset(self) -> QuerySet:
        qs = Student.objects.select_related(
            'student', 'campus', 'intake'
        ).prefetch_related(
            'enrollments__grade',
            'enrollments__stream',
            'parents'
        )

        academic_year = self.filters.get("academic_year")
        grade = self.filters.get("grade")
        stream = self.filters.get("stream")
        status = self.filters.get("status")
        campus = self.filters.get("campus")
        search = self.filters.get("search")

        if academic_year:
            qs = qs.filter(enrollments__academic_year_id=academic_year)
        if grade:
            qs = qs.filter(enrollments__grade_id=grade)
        if stream:
            qs = qs.filter(enrollments__stream_id=stream)
        if status:
            qs = qs.filter(status=status)
        if search:
            qs = qs.filter(
                Q(admission_number__icontains=search) |
                Q(student__first_name__icontains=search) |
                Q(student__last_name__icontains=search) |
                Q(parents__first_name__icontains=search) |
                Q(parents__last_name__icontains=search) |
                Q(parents__phone__icontains=search)
            )

        # Server-enforced campus access control
        from core.campus_filter import get_effective_campus_id_for_user
        effective_campus_id = get_effective_campus_id_for_user(self.user, self.filters)
        if effective_campus_id:
            qs = qs.filter(campus_id=effective_campus_id)

        return qs.distinct().order_by('admission_number')

    def get_summary_metrics(self, queryset: QuerySet) -> Dict[str, Any]:
        total = queryset.count()
        with_guardians = queryset.filter(parents__isnull=False).distinct().count()
        with_emergency = queryset.filter(emergency_contact_phone__isnull=False).exclude(emergency_contact_phone='').count()
        return {
            "total_students": total,
            "registered_guardians": with_guardians,
            "with_emergency_phone": with_emergency,
        }

    def get_columns(self) -> List[Dict[str, str]]:
        return [
            {"key": "admission_number", "label": "Adm No.", "align": "left"},
            {"key": "student_name", "label": "Student Name", "align": "left"},
            {"key": "current_placement", "label": "Class / Stream", "align": "left"},
            {"key": "guardian_name", "label": "Primary Guardian", "align": "left"},
            {"key": "relation", "label": "Relationship", "align": "center"},
            {"key": "guardian_phone", "label": "Guardian Phone", "align": "left"},
            {"key": "guardian_email", "label": "Guardian Email", "align": "left"},
            {"key": "emergency_contact", "label": "Emergency Contact", "align": "left"},
            {"key": "emergency_phone", "label": "Emergency Phone", "align": "left"},
        ]

    def serialize_record(self, student: Student) -> Dict[str, Any]:
        user_obj = student.student
        full_name = f"{user_obj.first_name} {user_obj.last_name}".strip() or user_obj.username

        # Current active enrollment
        active_enr = None
        for enr in student.enrollments.all():
            if enr.is_active and not enr.is_deleted:
                active_enr = enr
                break

        if active_enr and active_enr.grade:
            placement = active_enr.grade.name
            if active_enr.stream:
                placement += f" - {active_enr.stream.name}"
        else:
            placement = "—"

        parents = list(student.parents.all())
        primary_parent = parents[0] if parents else None

        guardian_name = f"{primary_parent.first_name} {primary_parent.last_name}".strip() if primary_parent else "—"
        relation = primary_parent.relation_ship if primary_parent and primary_parent.relation_ship else "—"
        guardian_phone = primary_parent.phone if primary_parent and primary_parent.phone else "—"
        guardian_email = primary_parent.email if primary_parent and primary_parent.email else "—"

        return {
            "id": student.id,
            "admission_number": student.admission_number or "—",
            "student_name": full_name,
            "current_placement": placement,
            "guardian_name": guardian_name,
            "relation": relation,
            "guardian_phone": guardian_phone,
            "guardian_email": guardian_email,
            "emergency_contact": student.emergency_contact_name or "—",
            "emergency_phone": student.emergency_contact_phone or "—",
        }
