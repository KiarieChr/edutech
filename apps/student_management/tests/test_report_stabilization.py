from datetime import date
from django_tenants.test.cases import FastTenantTestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, force_authenticate

from student_management.viewsets.reports_viewset import StudentReportsViewSet
from student_management.models import Student
from student_settings.models import AcademicYear, Term, Curriculum, CurriculumLevel, GradeStructure, Stream, Enrollment
from academics.report_views import report_transfers, report_demographics

User = get_user_model()

class ReportStabilizationTestCase(FastTenantTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_superuser(
            username='admin_test',
            email='admin@test.com',
            password='testpassword123'
        )

        # Create basic curriculum and calendar data
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
            name='Grade 1',
            level_order=1
        )
        self.stream = Stream.objects.create(
            grade=self.grade,
            name='North'
        )

        # Create students
        self.student_users = []
        self.students = []
        for i in range(3):
            u = User.objects.create_user(
                username=f'student_{i}',
                first_name=f'First{i}',
                last_name=f'Last{i}',
                gender='M' if i % 2 == 0 else 'F'
            )
            s = Student.objects.create(
                student=u,
                admission_number=f'ADM/2026/00{i}',
                date_of_birth=date(2018, 5, 10 + i),
                admission_date=date(2026, 1, 6),
                status='active'
            )
            self.student_users.append(u)
            self.students.append(s)

            # Create Enrollment
            Enrollment.objects.create(
                student=s,
                academic_year=self.academic_year,
                term=self.term,
                curriculum=self.curriculum,
                curriculum_level=self.level,
                grade=self.grade,
                stream=self.stream,
                enrollment_date=date(2026, 1, 6),
                status=Enrollment.EnrollmentStatus.ACTIVE,
                is_active=True
            )

    def test_nominal_roll_optimization_and_age_calculation(self):
        """Verify nominal_roll executes with select_related optimization and computes age."""
        view = StudentReportsViewSet.as_view({'get': 'nominal_roll'})
        request = self.factory.get('/api/student-management/reports/nominal_roll/')
        force_authenticate(request, user=self.user)

        with self.assertNumQueries(1):  # 1 single query thanks to select_related('student__student', ...)
            response = view(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 3)

        # Check first student data
        first_row = response.data[0]
        self.assertEqual(first_row['admission_number'], 'ADM/2026/000')
        self.assertEqual(first_row['full_name'], 'First0 Last0')
        self.assertIsNotNone(first_row['age'])
        self.assertGreater(first_row['age'], 0)

    def test_academics_report_transfers_no_field_error(self):
        """Verify report_transfers executes without FieldError ('updated_at')."""
        request = self.factory.get('/api/academics/reports/transfers/')
        force_authenticate(request, user=self.user)
        response = report_transfers(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn('stats', response.data)
        self.assertIn('table', response.data)

    def test_academics_report_demographics_no_field_error(self):
        """Verify report_demographics executes without FieldError ('student__date_of_birth')."""
        request = self.factory.get('/api/academics/reports/demographics/')
        force_authenticate(request, user=self.user)
        response = report_demographics(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn('ageDistribution', response.data)
        self.assertIn('genderSummary', response.data)

    def test_overview_stats_endpoint(self):
        """Verify overview_stats returns calculated aggregated statistics with fast ORM queries."""
        view = StudentReportsViewSet.as_view({'get': 'overview_stats'})
        request = self.factory.get('/api/student-management/reports/overview-stats/')
        force_authenticate(request, user=self.user)

        response = view(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total_students'], 3)
        self.assertEqual(response.data['active_students'], 3)
        self.assertIn('gender_breakdown', response.data)
        self.assertEqual(response.data['gender_breakdown']['male'], 2)
        self.assertEqual(response.data['gender_breakdown']['female'], 1)
        self.assertEqual(response.data['new_admissions'], 3)
        self.assertIn('class_distribution', response.data)
        self.assertGreaterEqual(len(response.data['class_distribution']), 1)
        self.assertEqual(response.data['class_distribution'][0]['class_name'], 'Grade 1')
        self.assertEqual(response.data['class_distribution'][0]['count'], 3)
        self.assertEqual(response.data['transfers_exits'], 0)

