"""
Official Student Admission Letter Data Provider.
Extracts, validates, and renders formal admission letters from Student Management records
using the Document Design Studio and WeasyPrint rendering pipeline.
"""
import os
import base64
from datetime import datetime, date
from typing import Dict, Any, Optional
from django.core.exceptions import ValidationError
from django.utils.html import escape

from core.models import InstitutionProfile
from documents.models import DocumentTemplate
from documents.services.base_provider import BaseDocumentDataProvider
from student_management.models import Admission, Student


def file_to_data_uri(field_file) -> Optional[str]:
    """Safely converts an ImageField file to a base64 Data URI."""
    if not field_file:
        return None
    try:
        if hasattr(field_file, "path") and os.path.exists(field_file.path):
            with open(field_file.path, "rb") as f:
                data = base64.b64encode(f.read()).decode("utf-8")
                ext = os.path.splitext(field_file.path)[1].lower().replace(".", "")
                mime = "png" if ext == "png" else "jpeg"
                return f"data:image/{mime};base64,{data}"
    except Exception:
        pass
    return None


class AdmissionLetterDataProvider(BaseDocumentDataProvider):
    """
    Data provider for Official Student Admission Letters.
    Accepts either an Admission record or a Student record with an associated admission.
    """

    def __init__(self, entity: Any, context: Optional[Dict[str, Any]] = None):
        self.admission: Optional[Admission] = None
        self.student: Optional[Student] = None

        if isinstance(entity, Admission):
            self.admission = entity
            self.student = getattr(entity, "student", None)
        elif isinstance(entity, Student):
            self.student = entity
            self.admission = getattr(entity, "admission_record", None)
        else:
            raise ValidationError(
                f"Unsupported entity type '{type(entity).__name__}'. "
                "AdmissionLetterDataProvider requires an Admission or Student instance."
            )

        super().__init__(entity, context=context)

    def get_document_type(self) -> str:
        return "admission_letter"

    def get_document_title(self) -> str:
        return "OFFICIAL LETTER OF ADMISSION"

    def get_category(self) -> str:
        return DocumentTemplate.Category.LETTER

    def validate(self) -> None:
        super().validate()
        if not self.admission and not self.student:
            raise ValidationError("An admission or student record is required.")

        adm_no = (
            getattr(self.admission, "admission_number", None)
            or getattr(self.student, "admission_number", None)
        )
        if not adm_no:
            raise ValidationError(
                "Cannot generate admission letter: The student does not have an allocated admission number."
            )

    def get_context_data(self) -> Dict[str, Any]:
        """
        Builds a comprehensive dictionary of student, admission, and guardian particulars.
        """
        app = getattr(self.admission, "application", None) if self.admission else None
        student_obj = self.student
        user_obj = getattr(student_obj, "student", None) if student_obj else None

        # Resolve Student Name
        if app and app.first_name:
            first_name = app.first_name
            middle_name = app.middle_name or ""
            last_name = app.last_name
            full_name = f"{first_name} {middle_name} {last_name}".replace("  ", " ").strip()
        elif user_obj:
            first_name = user_obj.first_name
            last_name = user_obj.last_name
            full_name = user_obj.get_full_name() or f"{first_name} {last_name}".strip()
        else:
            first_name = "Applicant"
            last_name = ""
            full_name = "Admitted Student"

        # Admission Number & Reference
        adm_no = (
            getattr(self.admission, "admission_number", "")
            or getattr(student_obj, "admission_number", "")
            or "PENDING"
        )
        current_year = datetime.now().year
        doc_ref = f"ADM/{current_year}/{adm_no}"

        # Admission & Reporting Dates
        raw_adm_date = getattr(self.admission, "admission_date", None) or getattr(student_obj, "admission_date", None) or date.today()
        if isinstance(raw_adm_date, (datetime, date)):
            formatted_adm_date = raw_adm_date.strftime("%d %B %Y")
        else:
            formatted_adm_date = str(raw_adm_date)

        # Academic Particulars
        grade_name = ""
        curriculum_name = ""
        campus_name = ""
        intake_name = ""

        if app:
            grade_name = getattr(app.applying_for_grade, "name", "")
            curriculum_name = getattr(app.applying_for_curriculum, "name", "")
            campus_name = getattr(app.campus, "name", "")
            intake_name = getattr(app.intake, "name", "")
            reporting_date = getattr(app.intake, "start_date", None)
        else:
            reporting_date = None

        if not grade_name and student_obj and student_obj.current_grade:
            grade_name = getattr(student_obj.current_grade, "name", "")
        if not grade_name:
            grade_name = "Form 1 / Grade 7"

        if not campus_name and student_obj and student_obj.campus:
            campus_name = getattr(student_obj.campus, "name", "")
        if not campus_name and self.admission and self.admission.campus:
            campus_name = getattr(self.admission.campus, "name", "")
        if not campus_name:
            campus_name = "Main Campus"

        if not intake_name and student_obj and student_obj.intake:
            intake_name = getattr(student_obj.intake, "name", "")
        if not intake_name:
            intake_name = f"Academic Year {current_year} Intake"

        formatted_reporting_date = (
            reporting_date.strftime("%d %B %Y")
            if isinstance(reporting_date, (datetime, date))
            else f"First Term, {current_year}"
        )

        # Guardian Particulars
        guardian_name = getattr(app, "guardian_name", "") or ""
        guardian_phone = getattr(app, "phone_number", "") or ""
        guardian_email = getattr(app, "email", "") or ""
        guardian_address = getattr(app, "guardian_address", "") or getattr(app, "home_address", "") or ""
        guardian_relation = getattr(app, "guardian_relationship", "Parent/Guardian") or "Parent/Guardian"

        if not guardian_name and student_obj:
            parent = student_obj.parents.first()
            if parent:
                guardian_name = f"{parent.first_name} {parent.last_name}".strip()
                guardian_phone = parent.phone or ""
                guardian_email = parent.email or ""
                guardian_relation = parent.relation_ship or "Parent/Guardian"

        if not guardian_name:
            guardian_name = "Parent / Legal Guardian"

        # Institutional Signatory Particulars
        inst_profile = InstitutionProfile.get_instance()
        principal_name = inst_profile.principal_name or "Dr. Arthur Kimani"
        principal_title = inst_profile.principal_title or "CHIEF PRINCIPAL"
        signature_uri = file_to_data_uri(inst_profile.signature_image)
        stamp_uri = file_to_data_uri(inst_profile.stamp_image)

        return {
            "document_ref": doc_ref,
            "document_date": datetime.now().strftime("%d %B %Y"),
            "student": {
                "full_name": full_name,
                "first_name": first_name,
                "last_name": last_name,
                "admission_number": adm_no,
                "gender": getattr(app, "gender", "") or (getattr(user_obj, "gender", "") if user_obj else ""),
                "dob": getattr(app, "date_of_birth", None) or getattr(student_obj, "date_of_birth", None),
                "nationality": getattr(app, "nationality", "") or getattr(student_obj, "nationality", "Kenyan") or "Kenyan",
            },
            "admission": {
                "admission_number": adm_no,
                "admission_date": formatted_adm_date,
                "reporting_date": formatted_reporting_date,
                "campus": campus_name,
                "grade": grade_name,
                "curriculum": curriculum_name or "CBC / 8-4-4 Standard",
                "intake": intake_name,
            },
            "guardian": {
                "name": guardian_name,
                "relationship": guardian_relation.capitalize(),
                "phone": guardian_phone,
                "email": guardian_email,
                "address": guardian_address or "P.O. Box — Private Bag",
            },
            "signatory": {
                "name": principal_name,
                "title": principal_title,
                "signature_uri": signature_uri,
                "stamp_uri": stamp_uri,
            },
        }

    def render_body_html(self, context: Dict[str, Any]) -> str:
        """
        Renders a formal institutional admission letter body.
        Follows print-layout typography standards with clear hierarchy.
        """
        student = context.get("student", {})
        admission = context.get("admission", {})
        guardian = context.get("guardian", {})
        signatory = context.get("signatory", {})
        brand = context.get("brand", {})
        inst = context.get("institution", {})

        primary_color = brand.get("primary", "#17365D")
        secondary_color = brand.get("secondary", "#1F6B4F")
        accent_color = brand.get("accent", "#D4A72C")
        school_name = inst.get("name", "The Institution")

        signature_html = ""
        if signatory.get("signature_uri"):
            signature_html = f'<img src="{signatory["signature_uri"]}" style="max-height: 48px; max-width: 140px; display: block; margin-bottom: 4px;" alt="Signature" />'
        else:
            signature_html = '<div style="height: 38px;"></div>'

        stamp_html = ""
        if signatory.get("stamp_uri"):
            stamp_html = f"""
            <div style="position: absolute; right: 40px; bottom: 0px; opacity: 0.85; pointer-events: none;">
                <img src="{signatory['stamp_uri']}" style="width: 95px; height: 95px; object-fit: contain;" alt="Official Stamp" />
            </div>
            """

        return f"""
        <article class="admission-letter-content" style="font-size: 9.5pt; line-height: 1.55; color: #1e293b; position: relative;">
            
            <!-- Reference & Date Line -->
            <table class="grid-table" style="width: 100%; border-collapse: collapse; margin-bottom: 12px; font-size: 8.5pt;">
                <tr>
                    <td style="text-align: left; vertical-align: top; width: 60%; color: #475569;">
                        <strong>Ref:</strong> <span style="font-family: monospace; font-weight: bold; color: {primary_color};">{escape(context.get('document_ref', 'ADM/2026'))}</span>
                    </td>
                    <td style="text-align: right; vertical-align: top; width: 40%; color: #475569;">
                        <strong>Date:</strong> {escape(context.get('document_date', ''))}
                    </td>
                </tr>
            </table>

            <!-- Addressee Block -->
            <div style="margin-bottom: 14px; font-size: 9pt; line-height: 1.45; color: #334155;">
                <div style="font-weight: bold; color: #0f172a;">To the Parent / Legal Guardian of:</div>
                <div style="font-weight: 800; font-size: 10pt; color: {primary_color};">{escape(student.get('full_name', ''))}</div>
                <div>{escape(guardian.get('name', ''))} ({escape(guardian.get('relationship', 'Parent'))})</div>
                <div>{escape(guardian.get('address', ''))}</div>
                <div>Tel: {escape(guardian.get('phone', ''))} | Email: {escape(guardian.get('email', ''))}</div>
            </div>

            <!-- Salutation & Formal Subject Line -->
            <div style="margin-bottom: 10px;">
                <p style="margin: 0 0 8px 0;">Dear Sir/Madam,</p>
                <div style="background-color: #f1f5f9; border-left: 3.5px solid {primary_color}; padding: 7px 12px; border-radius: 0 4px 4px 0;">
                    <span style="font-size: 10pt; font-weight: 800; text-transform: uppercase; letter-spacing: 0.3px; color: {primary_color};">
                        RE: OFFICIAL OFFER OF ADMISSION TO {escape(admission.get('grade', ''))} — {escape(student.get('full_name', ''))}
                    </span>
                </div>
            </div>

            <!-- Congratulatory Opening -->
            <p style="margin-top: 10px; margin-bottom: 10px; text-align: justify;">
                On behalf of the Board of Management, faculty, and administration of <strong>{escape(school_name)}</strong>, 
                I have the pleasure to convey to you that <strong>{escape(student.get('full_name', ''))}</strong> has been officially 
                admitted to our institution under <strong>Admission Number {escape(admission.get('admission_number', ''))}</strong>.
            </p>

            <!-- Admission Particulars Summary Card -->
            <div style="border: 1px solid #e2e8f0; border-radius: 6px; overflow: hidden; margin: 12px 0 14px 0;">
                <div style="background-color: {primary_color}; color: #ffffff; padding: 5px 10px; font-size: 8.5pt; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px;">
                    Particulars of Official Admission
                </div>
                <table style="width: 100%; border-collapse: collapse; font-size: 8.5pt;">
                    <tbody>
                        <tr style="border-bottom: 1px solid #f1f5f9;">
                            <td style="padding: 5px 10px; width: 25%; font-weight: 600; color: #64748b; background-color: #f8fafc;">Full Student Name</td>
                            <td style="padding: 5px 10px; width: 25%; font-weight: bold; color: #0f172a;">{escape(student.get('full_name', ''))}</td>
                            <td style="padding: 5px 10px; width: 25%; font-weight: 600; color: #64748b; background-color: #f8fafc;">Admission Number</td>
                            <td style="padding: 5px 10px; width: 25%; font-weight: bold; font-family: monospace; color: {primary_color};">{escape(admission.get('admission_number', ''))}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #f1f5f9;">
                            <td style="padding: 5px 10px; font-weight: 600; color: #64748b; background-color: #f8fafc;">Admitted Grade/Class</td>
                            <td style="padding: 5px 10px; font-weight: bold; color: #0f172a;">{escape(admission.get('grade', ''))}</td>
                            <td style="padding: 5px 10px; font-weight: 600; color: #64748b; background-color: #f8fafc;">Curriculum / Pathway</td>
                            <td style="padding: 5px 10px; color: #0f172a;">{escape(admission.get('curriculum', 'Standard'))}</td>
                        </tr>
                        <tr>
                            <td style="padding: 5px 10px; font-weight: 600; color: #64748b; background-color: #f8fafc;">Campus Allocated</td>
                            <td style="padding: 5px 10px; color: #0f172a;">{escape(admission.get('campus', 'Main Campus'))}</td>
                            <td style="padding: 5px 10px; font-weight: 600; color: #64748b; background-color: #f8fafc;">Expected Reporting Date</td>
                            <td style="padding: 5px 10px; font-weight: bold; color: {secondary_color};">{escape(admission.get('reporting_date', 'First Day of Term'))}</td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <!-- Reporting Instructions & Document Requirements -->
            <div style="margin-bottom: 12px;">
                <p style="margin: 0 0 6px 0; font-weight: bold; color: {primary_color};">Mandatory Documentation Required on Reporting Day:</p>
                <ol style="margin: 0; padding-left: 20px; font-size: 8.5pt; color: #334155; line-height: 1.5;">
                    <li>Original Birth Certificate along with two certified photocopies.</li>
                    <li>Official Leaving Certificate and original Report Form from the previous school (where applicable).</li>
                    <li>Two (2) recent colored passport-size photographs of the student with name written on the reverse.</li>
                    <li>Duly completed and signed Student Medical Examination Form and immunization records.</li>
                    <li>Official bank deposit slip or M-Pesa confirmation receipt for term fee payment as per the attached fee schedule.</li>
                </ol>
            </div>

            <p style="margin: 8px 0 16px 0; text-align: justify; font-size: 9pt;">
                Please note that this offer of admission is valid subject to full compliance with the institution's code of conduct 
                and timely fulfillment of the registration requirements. We congratulate {escape(student.get('first_name', 'the student'))} 
                and welcome your family to our vibrant academic community.
            </p>

            <!-- Formal Sign-Off & Seal Block -->
            <div style="position: relative; margin-top: 14px; page-break-inside: avoid;">
                <table class="grid-table" style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="width: 65%; vertical-align: bottom;">
                            <div style="font-size: 9pt; color: #334155; margin-bottom: 4px;">Yours sincerely,</div>
                            {signature_html}
                            <div style="font-weight: 800; font-size: 9.5pt; color: {primary_color}; text-transform: uppercase;">
                                {escape(signatory.get('name', 'The Principal'))}
                            </div>
                            <div style="font-size: 8pt; font-weight: bold; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px;">
                                {escape(signatory.get('title', 'CHIEF PRINCIPAL'))}
                            </div>
                            <div style="font-size: 7.5pt; color: #94a3b8; margin-top: 1px;">
                                {escape(school_name)}
                            </div>
                        </td>
                        <td style="width: 35%; text-align: right; vertical-align: bottom; position: relative;">
                            {stamp_html}
                        </td>
                    </tr>
                </table>
            </div>

            <!-- Tear-off Acceptance Slip -->
            <div style="margin-top: 24px; border-top: 1.5px dashed #cbd5e1; padding-top: 10px; font-size: 8pt; color: #475569; page-break-inside: avoid;">
                <div style="text-align: center; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px; color: {primary_color}; margin-bottom: 6px;">
                    Parent / Guardian Acceptance Slip (To be surrendered upon admission)
                </div>
                <p style="margin: 0 0 6px 0; line-height: 1.4;">
                    I, ____________________________________________________, parent/guardian of <strong>{escape(student.get('full_name', ''))}</strong> 
                    (Adm No: <strong>{escape(admission.get('admission_number', ''))}</strong>), accept the offer of admission to 
                    <strong>{escape(school_name)}</strong> and agree to abide by all institutional rules and financial regulations.
                </p>
                <table style="width: 100%; margin-top: 8px;">
                    <tr>
                        <td style="width: 50%;">Parent/Guardian Signature: _______________________</td>
                        <td style="width: 50%; text-align: right;">Date: ________________________</td>
                    </tr>
                </table>
            </div>

        </article>
        """
