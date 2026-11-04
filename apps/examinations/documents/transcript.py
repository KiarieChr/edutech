"""
Official Academic Transcript Data Provider (Phase 3).
Extracts, validates, and renders formal institutional academic transcripts
from examinations and academics records using Document Design Studio and WeasyPrint.
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, Any, Optional
from django.core.exceptions import ValidationError
from django.utils.html import escape

from documents.models import DocumentTemplate
from documents.services.base_provider import BaseDocumentDataProvider
from examinations.models import TermResult, TermSubjectResult
from student_management.models import Student


class TranscriptDataProvider(BaseDocumentDataProvider):
    """
    Data provider for Official Student Academic Transcripts.
    Accepts either a TermResult record or a Student record (with term_result passed in context).
    """

    def __init__(self, entity: Any, context: Optional[Dict[str, Any]] = None):
        self.term_result: Optional[TermResult] = None
        self.student: Optional[Student] = None

        if isinstance(entity, TermResult):
            self.term_result = entity
            self.student = getattr(entity, "student", None)
        elif isinstance(entity, Student):
            self.student = entity
            # Resolve latest or context-specified term_result
            if context and "term_result_id" in context:
                self.term_result = TermResult.objects.filter(
                    pk=context["term_result_id"], student=entity
                ).first()
            if not self.term_result:
                self.term_result = (
                    TermResult.objects.filter(student=entity)
                    .select_related("class_session", "class_session__academic_year", "class_session__term")
                    .order_by("-created_at")
                    .first()
                )
        else:
            raise ValidationError(
                f"Unsupported entity type '{type(entity).__name__}'. "
                "TranscriptDataProvider requires a TermResult or Student instance."
            )

        super().__init__(entity, context=context)

    def get_document_type(self) -> str:
        return "academic_transcript"

    def get_document_title(self) -> str:
        return "OFFICIAL ACADEMIC TRANSCRIPT"

    def get_category(self) -> str:
        return DocumentTemplate.Category.TRANSCRIPT

    def validate(self) -> None:
        super().validate()
        if not self.student:
            raise ValidationError("A valid student record is required to generate a transcript.")
        if not self.term_result:
            raise ValidationError("No examination term result found for this student.")

    def get_context_data(self) -> Dict[str, Any]:
        """
        Builds normalized, sanitized context data from real examination records.
        """
        tr = self.term_result
        st = self.student
        user = getattr(st, "student", None)

        # Student Particulars
        first_name = getattr(user, "first_name", "") or ""
        last_name = getattr(user, "last_name", "") or ""
        full_name = getattr(user, "get_full_name", lambda: "")() or f"{first_name} {last_name}".strip() or "Student"
        adm_no = getattr(st, "admission_number", "") or "N/A"
        gender = getattr(user, "gender", "") or getattr(st, "gender", "") or ""
        gender_display = "Male" if gender.upper() == "M" else ("Female" if gender.upper() == "F" else gender)

        # Academic Session & Class info
        cs = getattr(tr, "class_session", None)
        class_name = getattr(cs, "name", "") or getattr(cs, "class_name", "") or "General"
        grade_obj = getattr(cs, "grade_structure", None) or getattr(st, "current_grade", None)
        grade_name = getattr(grade_obj, "name", "") or class_name
        curriculum_obj = getattr(grade_obj, "curriculum", None)
        curriculum_name = getattr(curriculum_obj, "name", "") or "National Curriculum"

        academic_year_obj = getattr(cs, "academic_year", None)
        academic_year_name = getattr(academic_year_obj, "name", "") or str(datetime.now().year)

        term_obj = getattr(cs, "term", None)
        term_name = getattr(term_obj, "name", "") or "Term 1"

        stream_obj = getattr(tr, "stream", None)
        stream_name = getattr(stream_obj, "name", "") or ""

        # Subject Results Table
        subject_results = []
        raw_subjects = tr.subject_results.select_related("subject").order_by("subject__name")
        for sr in raw_subjects:
            subj = sr.subject
            weighted_mark = float(sr.weighted_mark) if sr.weighted_mark is not None else 0.0
            points = float(sr.points) if sr.points is not None else 0.0
            subject_results.append({
                "code": getattr(subj, "code", ""),
                "name": getattr(subj, "name", "Subject"),
                "mark": f"{weighted_mark:.1f}",
                "grade": sr.grade or "-",
                "points": f"{points:.1f}",
                "grade_label": sr.grade_label or "",
                "rank": sr.subject_rank or "-",
                "total_in_subject": sr.total_in_subject or "-",
                "remark": sr.teacher_remark or "Good progress",
            })

        # Aggregated Scores
        total_marks = float(tr.total_marks or 0.0)
        avg_mark = float(tr.average_mark or 0.0)
        total_points = float(tr.total_points or 0.0)
        avg_points = float(tr.average_points or 0.0)

        current_year = datetime.now().year
        doc_ref = f"TRN/{current_year}/{adm_no.replace('/', '-')}"

        return {
            "document_ref": doc_ref,
            "transcript": {
                "student_name": full_name,
                "admission_number": adm_no,
                "gender": gender_display,
                "grade_name": grade_name,
                "class_name": class_name,
                "stream_name": stream_name,
                "curriculum_name": curriculum_name,
                "academic_year": academic_year_name,
                "term": term_name,
                "subjects_taken": tr.subjects_taken or len(subject_results),
                "total_marks": f"{total_marks:.1f}",
                "average_mark": f"{avg_mark:.1f}",
                "total_points": f"{total_points:.1f}",
                "average_points": f"{avg_points:.1f}",
                "overall_grade": tr.overall_grade or "-",
                "overall_grade_label": tr.overall_grade_label or "",
                "class_rank": tr.class_rank or "-",
                "total_in_class": tr.total_in_class or "-",
                "class_teacher_remark": tr.class_teacher_remark or "Consistent effort demonstrated across all learning areas.",
                "principal_remark": tr.principal_remark or "Satisfactory academic performance. Encouraged to maintain this standard.",
                "subjects": subject_results,
            }
        }

    def render_body_html(self, context: Dict[str, Any]) -> str:
        """
        Renders the academic transcript body HTML matching institutional document styling.
        """
        t = context.get("transcript", {})
        subjects = t.get("subjects", [])
        brand_primary = context.get("brand", {}).get("primary", "#17365D")
        brand_secondary = context.get("brand", {}).get("secondary", "#1F6B4F")
        brand_accent = context.get("brand", {}).get("accent", "#D4A72C")

        # Build Subject Rows
        subject_rows = []
        for s in subjects:
            subject_rows.append(f"""
            <tr>
                <td style="font-weight: 600; color: #1e293b;">{escape(s['code'])}</td>
                <td style="font-weight: 500;">{escape(s['name'])}</td>
                <td style="text-align: center; font-weight: 600;">{escape(s['mark'])}%</td>
                <td style="text-align: center; font-weight: 700; color: {brand_primary};">{escape(s['grade'])}</td>
                <td style="text-align: center;">{escape(s['points'])}</td>
                <td style="text-align: center;">{escape(str(s['rank']))} / {escape(str(s['total_in_subject']))}</td>
                <td style="font-size: 8pt; color: #475569;">{escape(s['remark'])}</td>
            </tr>
            """)

        rows_html = "".join(subject_rows) if subject_rows else """
            <tr><td colspan="7" style="text-align: center; color: #94a3b8; padding: 16px;">No recorded subject assessments for this term.</td></tr>
        """

        stream_disp = f" ({escape(t['stream_name'])})" if t.get('stream_name') else ""

        return f"""
        <div class="report-header">
            <h1 class="doc-title">{escape(self.get_document_title())}</h1>
            <p class="doc-meta">
                Academic Year: <strong>{escape(t.get('academic_year', ''))}</strong> | 
                Reporting Period: <strong>{escape(t.get('term', ''))}</strong> | 
                Ref: <strong>{escape(context.get('document_ref', ''))}</strong>
            </p>
        </div>

        <!-- Student Particulars Card -->
        <div class="info-card" style="margin-bottom: 16px; border-left: 3.5px solid {brand_primary};">
            <table class="grid-table" style="width: 100%; font-size: 8.5pt;">
                <tr>
                    <td style="width: 50%; vertical-align: top; padding-right: 12px;">
                        <div style="margin-bottom: 4px;"><strong>Student Name:</strong> {escape(t.get('student_name', ''))}</div>
                        <div style="margin-bottom: 4px;"><strong>Admission No:</strong> {escape(t.get('admission_number', ''))}</div>
                        <div><strong>Gender:</strong> {escape(t.get('gender', ''))}</div>
                    </td>
                    <td style="width: 50%; vertical-align: top; padding-left: 12px;">
                        <div style="margin-bottom: 4px;"><strong>Class / Level:</strong> {escape(t.get('grade_name', ''))}{stream_disp}</div>
                        <div style="margin-bottom: 4px;"><strong>Curriculum:</strong> {escape(t.get('curriculum_name', ''))}</div>
                        <div><strong>Subjects Taken:</strong> {escape(str(t.get('subjects_taken', '0')))}</div>
                    </td>
                </tr>
            </table>
        </div>

        <!-- Academic Performance Table -->
        <table class="data-table">
            <thead>
                <tr>
                    <th style="width: 12%;">Code</th>
                    <th style="width: 28%;">Learning Area / Subject</th>
                    <th style="width: 10%; text-align: center;">Mark</th>
                    <th style="width: 10%; text-align: center;">Grade</th>
                    <th style="width: 8%; text-align: center;">Points</th>
                    <th style="width: 12%; text-align: center;">Rank</th>
                    <th style="width: 20%;">Teacher Remarks</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>

        <!-- Summary & Aggregate Scores Card -->
        <div style="background-color: #f8fafc; border: 1px solid #cbd5e1; border-radius: 6px; padding: 12px 16px; margin-top: 14px; margin-bottom: 18px;">
            <table class="grid-table" style="width: 100%; font-size: 9pt;">
                <tr>
                    <td style="width: 25%; text-align: center; border-right: 1px solid #e2e8f0; padding: 4px 8px;">
                        <div style="font-size: 7.5pt; color: #64748b; text-transform: uppercase;">Total Marks</div>
                        <div style="font-size: 13pt; font-weight: 800; color: {brand_primary}; margin-top: 2px;">{escape(t.get('total_marks', '0'))}</div>
                    </td>
                    <td style="width: 25%; text-align: center; border-right: 1px solid #e2e8f0; padding: 4px 8px;">
                        <div style="font-size: 7.5pt; color: #64748b; text-transform: uppercase;">Average Mark</div>
                        <div style="font-size: 13pt; font-weight: 800; color: {brand_primary}; margin-top: 2px;">{escape(t.get('average_mark', '0'))}%</div>
                    </td>
                    <td style="width: 25%; text-align: center; border-right: 1px solid #e2e8f0; padding: 4px 8px;">
                        <div style="font-size: 7.5pt; color: #64748b; text-transform: uppercase;">Overall Grade</div>
                        <div style="font-size: 13pt; font-weight: 800; color: {brand_secondary}; margin-top: 2px;">{escape(t.get('overall_grade', '-'))}</div>
                    </td>
                    <td style="width: 25%; text-align: center; padding: 4px 8px;">
                        <div style="font-size: 7.5pt; color: #64748b; text-transform: uppercase;">Class Position</div>
                        <div style="font-size: 13pt; font-weight: 800; color: {brand_primary}; margin-top: 2px;">{escape(str(t.get('class_rank', '-')))} / {escape(str(t.get('total_in_class', '-')))}</div>
                    </td>
                </tr>
            </table>
        </div>

        <!-- Remarks and Authorizations -->
        <div style="margin-top: 16px; border: 1px solid #e2e8f0; border-radius: 6px; padding: 12px 14px; background: #ffffff;">
            <div style="margin-bottom: 10px;">
                <span style="font-size: 8pt; font-weight: 700; color: {brand_secondary}; text-transform: uppercase;">Class Teacher's Remark:</span>
                <p style="margin: 2px 0 0 0; font-size: 8.5pt; color: #334155; font-style: italic;">
                    "{escape(t.get('class_teacher_remark', ''))}"
                </p>
            </div>
            <div>
                <span style="font-size: 8pt; font-weight: 700; color: {brand_secondary}; text-transform: uppercase;">Principal's Endorsement:</span>
                <p style="margin: 2px 0 0 0; font-size: 8.5pt; color: #334155; font-style: italic;">
                    "{escape(t.get('principal_remark', ''))}"
                </p>
            </div>
        </div>

        <!-- Signatures and Stamp Section -->
        <div style="margin-top: 30px; page-break-inside: avoid;">
            <table class="grid-table" style="width: 100%; font-size: 8.5pt;">
                <tr>
                    <td style="width: 33%; vertical-align: bottom;">
                        <div style="border-bottom: 1px solid #94a3b8; width: 85%; height: 35px;"></div>
                        <div style="margin-top: 5px; font-weight: 700; color: #334155;">Class Teacher Signature</div>
                    </td>
                    <td style="width: 34%; text-align: center; vertical-align: bottom;">
                        <div style="border: 1px dashed {brand_accent}; width: 90px; height: 50px; margin: 0 auto; display: flex; align-items: center; justify-content: center; color: #94a3b8; font-size: 7.5pt; border-radius: 4px;">
                            OFFICIAL STAMP
                        </div>
                    </td>
                    <td style="width: 33%; text-align: right; vertical-align: bottom;">
                        <div style="border-bottom: 1px solid #94a3b8; width: 85%; margin-left: auto; height: 35px;"></div>
                        <div style="margin-top: 5px; font-weight: 700; color: #334155;">Principal / Head of School</div>
                    </td>
                </tr>
            </table>
        </div>
        """
