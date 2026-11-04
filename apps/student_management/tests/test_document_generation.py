from datetime import date
from io import BytesIO
from django_tenants.test.cases import FastTenantTestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, force_authenticate

from student_management.viewsets.reports_viewset import StudentReportsViewSet
from student_management.models import Student, Parent
from student_settings.models import AcademicYear, Term, Curriculum, CurriculumLevel, GradeStructure, Stream, Enrollment

import openpyxl
from docx import Document

User = get_user_model()

class DocumentGenerationTestCase(FastTenantTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_superuser(
            username='admin_reports',
            email='admin@reports.com',
            password='password123'
        )

        # Academic structure
        self.academic_year = AcademicYear.objects.create(
            name='2026',
            start_date=date(2026, 1, 5),
            end_date=date(2026, 11, 27),
            is_current=True
        )
        self.term = Term.objects.create(
            academic_year=self.academic_year,
            name='Term 1',
            start_date=date(2026, 1, 5),
            end_date=date(2026, 4, 3),
            order=1
        )
        self.curriculum = Curriculum.objects.create(name='CBC', code='CBC')
        self.level = CurriculumLevel.objects.create(
            curriculum=self.curriculum,
            name='Primary',
            order=1
        )
        self.grade = GradeStructure.objects.create(
            curriculum=self.curriculum,
            curriculum_level=self.level,
            name='Grade 4',
            level_order=4
        )
        self.stream = Stream.objects.create(
            grade=self.grade,
            name='Blue'
        )

        # Create test students and parents
        for i in range(5):
            u = User.objects.create_user(
                username=f'std_{i}',
                first_name=f'Student{i}',
                last_name='Kamau',
                gender='M' if i % 2 == 0 else 'F'
            )
            s = Student.objects.create(
                student=u,
                admission_number=f'ADM/2026/0{i}',
                birth_certificate_number=f'BC-2026-{i}',
                date_of_birth=date(2016, 3, 10 + i),
                admission_date=date(2026, 1, 6),
                status='active',
                emergency_contact_phone='+254700000000'
            )

            parent_u = User.objects.create_user(username=f'parent_{i}')
            Parent.objects.create(
                user=parent_u,
                student=s,
                first_name='Parent',
                last_name='Kamau',
                phone='+254711111111',
                relation_ship='Father'
            )

            Enrollment.objects.create(
                student=s,
                academic_year=self.academic_year,
                term=self.term,
                curriculum=self.curriculum,
                curriculum_level=self.level,
                grade=self.grade,
                stream=self.stream,
                enrollment_date=date(2026, 1, 6),
                stay_status='day_scholar' if i < 3 else 'boarder',
                status=Enrollment.EnrollmentStatus.ACTIVE,
                is_active=True,
                created_by=self.user,
                updated_by=self.user
            )

    def test_master_register_preview_and_summaries(self):
        """Verify Master Register preview returns paginated records and full-set summaries."""
        view = StudentReportsViewSet.as_view({'get': 'master_register_preview'})
        domain = self.tenant.domains.first().domain if self.tenant.domains.exists() else 'test.localhost'
        request = self.factory.get('/api/student-management/reports/master_register_preview/?grade=' + str(self.grade.id), HTTP_HOST=domain)
        force_authenticate(request, user=self.user)
        response = view(request)

        self.assertEqual(response.status_code, 200)
        data = response.data
        self.assertEqual(data['pagination']['count'], 5)
        self.assertEqual(len(data['results']), 5)
        self.assertEqual(data['summaries']['total_students'], 5)
        self.assertEqual(data['summaries']['male_count'], 3)
        self.assertEqual(data['summaries']['female_count'], 2)

    def test_class_list_preview_and_summaries(self):
        """Verify Official Class List preview returns correct roster and summaries."""
        view = StudentReportsViewSet.as_view({'get': 'class_list_preview'})
        domain = self.tenant.domains.first().domain if self.tenant.domains.exists() else 'test.localhost'
        request = self.factory.get(f'/api/student-management/reports/class_list_preview/?academic_year={self.academic_year.id}&grade={self.grade.id}', HTTP_HOST=domain)
        force_authenticate(request, user=self.user)
        response = view(request)

        self.assertEqual(response.status_code, 200)
        data = response.data
        self.assertEqual(data['pagination']['count'], 5)
        self.assertEqual(data['summaries']['total_enrolled'], 5)
        self.assertEqual(data['summaries']['day_scholars'], 3)
        self.assertEqual(data['summaries']['boarders'], 2)

    def test_pdf_export_structure(self):
        """Verify PDF export returns valid binary starting with %PDF-."""
        view = StudentReportsViewSet.as_view({'get': 'master_register_export'})
        domain = self.tenant.domains.first().domain if self.tenant.domains.exists() else 'test.localhost'
        request = self.factory.get('/api/student-management/reports/master_register_export/?format=pdf', HTTP_HOST=domain)
        force_authenticate(request, user=self.user)
        response = view(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        content = response.content
        self.assertTrue(content.startswith(b'%PDF-'))
        self.assertGreater(len(content), 1000)

    def test_excel_export_structure(self):
        """Verify Excel export returns valid loadable .xlsx with correct typed cells."""
        view = StudentReportsViewSet.as_view({'get': 'master_register_export'})
        domain = self.tenant.domains.first().domain if self.tenant.domains.exists() else 'test.localhost'
        request = self.factory.get('/api/student-management/reports/master_register_export/?format=excel', HTTP_HOST=domain)
        force_authenticate(request, user=self.user)
        response = view(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn('spreadsheetml.sheet', response['Content-Type'])

        wb = openpyxl.load_workbook(BytesIO(response.content))
        self.assertIn('Student Master Register', wb.sheetnames[0])
        ws = wb.active
        # Header is row 7, data starts row 8
        self.assertEqual(ws.cell(row=7, column=1).value, 'Adm No.')
        self.assertEqual(ws.cell(row=8, column=1).value, 'ADM/2026/00')

    def test_word_export_structure(self):
        """Verify Word export returns valid loadable .docx package."""
        view = StudentReportsViewSet.as_view({'get': 'class_list_export'})
        domain = self.tenant.domains.first().domain if self.tenant.domains.exists() else 'test.localhost'
        request = self.factory.get('/api/student-management/reports/class_list_export/?format=word', HTTP_HOST=domain)
        force_authenticate(request, user=self.user)
        response = view(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn('wordprocessingml.document', response['Content-Type'])

        doc = Document(BytesIO(response.content))
        self.assertGreater(len(doc.paragraphs), 1)
        self.assertIn('Official Class List', doc.paragraphs[1].text)
        self.assertEqual(len(doc.tables), 1)
        # Table has 1 header row + 5 student rows = 6 rows
        self.assertEqual(len(doc.tables[0].rows), 6)
