from django.db import connection
from django.db.models import Prefetch
from student_management.models import Student
from examinations.models import TermResult, TermSubjectResult
from .models import IntelligenceAuditLog, IntelligenceUsage
import datetime

class FahariIntelligenceService:
    @staticmethod
    def log_audit(user, data_scope, document_type, status='APPROVED'):
        IntelligenceAuditLog.objects.create(
            user=user,
            data_scope_queried=data_scope,
            document_type_generated=document_type,
            approval_status=status
        )

    @staticmethod
    def get_student_academic_context(student_id, term, academic_year, class_id):
        """
        Retrieves anonymised academic data for a student.
        Ensures strict separation of data (Tenant schema aware).
        """
        # Strict validation that we are inside a tenant schema (not public)
        if connection.schema_name == 'public':
            raise ValueError("Intelligence queries cannot be executed in the public schema.")

        # Query data safely using Django ORM which respects the current schema_context
        try:
            student = Student.objects.get(id=student_id)
            
            # Find the TermResult based on term/academic_year mapping to class_session
            # Or get the latest one if mapping is complex for this phase
            term_perf = TermResult.objects.filter(
                student=student
            ).order_by('-id').first()
            
            if not term_perf:
                raise ValueError("No academic records found for this student.")

            subject_perfs = TermSubjectResult.objects.filter(
                term_result=term_perf
            ).select_related('subject')
            
            # Anonymisation Layer: 
            # - Remove last name
            # - Remove national IDs or sensitive PII
            # - Use internal DB ID (or hash) instead of actual admission number
            
            subject_data = []
            for sp in subject_perfs:
                subject_data.append({
                    "subject": sp.subject.name,
                    "marks": float(sp.weighted_mark),
                    "max": 100.0, # Assuming standard out of 100
                    "grade": sp.grade
                })
            
            # Sort to find best/worst
            sorted_subjects = sorted(subject_data, key=lambda x: x["marks"], reverse=True)
            top_2 = [s["subject"] for s in sorted_subjects[:2]]
            bottom_2 = [s["subject"] for s in sorted_subjects[-2:]] if len(sorted_subjects) >= 2 else []

            context = {
                "first_name": student.first_name,
                "class_name": getattr(student.current_class, 'name', 'Unknown Class'),
                "curriculum": getattr(student.current_class, 'curriculum_type', 'CBC'),
                "position": getattr(term_perf, 'class_rank', 'N/A'),
                "total_students": getattr(term_perf, 'total_in_class', 'N/A'),
                "attendance_percentage": 'N/A', # Attendance from separate module if needed
                "conduct_notes": getattr(term_perf, 'class_teacher_remark', 'None'),
                "subject_performance": subject_data,
                "top_subjects": top_2,
                "bottom_subjects": bottom_2
            }
            return context

        except Exception as e:
            raise ValueError(f"Failed to retrieve data: {str(e)}")

    @staticmethod
    def build_narrative_prompts(context, tone="formal"):
        curriculum = context.get('curriculum', 'CBC')
        
        system_prompt = (
            f"You are an experienced school educator writing professional report card narratives "
            f"for an East African school. Write in a {tone} tone appropriate for {curriculum} curriculum. "
            f"Be specific, encouraging, and constructive. Reference actual subject performance. "
            f"Never fabricate information not provided. Keep narratives between 80-120 words."
        )

        perf_lines = "\n".join([f"{s['subject']}: {s['marks']}/{s['max']} ({s['grade']})" for s in context['subject_performance']])

        user_prompt = (
            f"Write a report card narrative for a student with the following academic profile this term:\n\n"
            f"Class: {context['class_name']} | Position: {context['position']} of {context['total_students']}\n"
            f"Curriculum: {curriculum}\n"
            f"Attendance: {context['attendance_percentage']}%\n\n"
            f"Subject Performance:\n{perf_lines}\n\n"
            f"Strongest subjects: {', '.join(context['top_subjects'])}\n"
            f"Subjects needing improvement: {', '.join(context['bottom_subjects'])}\n"
            f"Conduct notes: {context['conduct_notes']}\n\n"
            f"Generate a professional, specific, and encouraging report card narrative for {context['first_name']}."
        )

        return system_prompt, user_prompt

    @staticmethod
    def get_institutional_context(tenant_schema: str):
        """
        Fetches high-level aggregated data for the Conversational AI to answer general queries.
        """
        try:
            total_students = Student.objects.count()

            # Dynamically fetch classes breakdown
            try:
                from student_settings.models import Enrollment
                from django.db.models import Count
                
                enrollment_counts = Enrollment.objects.filter(
                    is_active=True, 
                    is_deleted=False
                ).values('grade__name').annotate(count=Count('id'))
                
                if enrollment_counts:
                    classes_breakdown = ", ".join([f"{e['grade__name'] or 'Unassigned'} ({e['count']})" for e in enrollment_counts])
                else:
                    classes_breakdown = "No students currently enrolled in classes."
            except Exception:
                classes_breakdown = "Data unavailable"

            # Dynamically fetch active term
            try:
                from student_settings.models import Term
                active_term_obj = Term.objects.filter(is_current=True).first()
                active_term = f"{active_term_obj.name} ({active_term_obj.academic_year.name})" if active_term_obj else "No active term set"
            except Exception:
                active_term = "Data unavailable"

            context = {
                "tenant": tenant_schema,
                "total_students": total_students,
                "active_term": active_term,
                "total_fee_arrears": "Data unavailable",
                "attendance_average": "Data unavailable",
                "classes_breakdown": classes_breakdown
            }
            return context
        except Exception:
            return {"tenant": tenant_schema, "error": "Could not fetch data"}

    @staticmethod
    def build_chat_system_prompt(context):
        system_prompt = (
            f"You are Fahari AI, the intelligence assistant for a school. "
            f"You have access to the following live institutional data: {context}. "
            f"Answer the user's questions accurately based ONLY on this context. "
            f"If they ask for specific PII or deep details not in the context, inform them you only have access to high-level aggregates for security reasons."
        )
        return system_prompt
