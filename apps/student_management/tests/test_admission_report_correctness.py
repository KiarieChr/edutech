import datetime
from django_tenants.test.cases import FastTenantTestCase
from django.contrib.auth import get_user_model
from student_management.models import Admission, Application, Student, Parent
from student_settings.models import AcademicYear, GradeStructure, Intake, Curriculum
from student_management.reports.services.admissions_register_report import AdmissionsRegisterReport

User = get_user_model()


class AdmissionReportCorrectnessTestCase(FastTenantTestCase):
    def setUp(self):
        super().setUp()
        self.staff_user = User.objects.create_user(
            username='admin_report_tester',
            password='Password123!',
            is_staff=True,
            is_superuser=True
        )

        self.curriculum = Curriculum.objects.create(name='CBC System', code='CBC-REP')
        self.academic_year = AcademicYear.objects.create(
            name='2026 Academic Year',
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 12, 31),
            is_current=True,
            created_by=self.staff_user,
            updated_by=self.staff_user
        )
        self.grade = GradeStructure.objects.create(
            name='Grade 5',
            curriculum=self.curriculum,
            level_order=5
        )
        self.intake = Intake.objects.create(
            name='Term 1 2026 Intake',
            academic_year=self.academic_year,
            start_date=datetime.date(2026, 1, 1),
            created_by=self.staff_user,
            updated_by=self.staff_user
        )

    def test_search_with_guardian_does_not_duplicate_rows(self):
        """Assert that a student with multiple matching parents returns exactly 1 row (no SQL multiplication)."""
        student_user = User.objects.create_user(
            username='duptest_student',
            first_name='Amina',
            last_name='Kariuki',
            gender='F'
        )
        student = Student.objects.create(
            student=student_user,
            admission_number='REP-DUP-001',
            status='active'
        )
        app = Application.objects.create(
            first_name='Amina',
            last_name='Kariuki',
            applying_for_grade=self.grade,
            applying_for_curriculum=self.curriculum,
            intake=self.intake,
            created_by=self.staff_user,
            updated_by=self.staff_user
        )
        adm = Admission.objects.create(
            application=app,
            student=student,
            admission_number='REP-DUP-001',
            admission_date=datetime.date(2026, 2, 10),
            created_by=self.staff_user,
            updated_by=self.staff_user
        )

        # Create TWO parents who BOTH have phone numbers or names matching "Waweru"
        father_user = User.objects.create_user(username='father_waweru', first_name='Peter', last_name='Waweru')
        Parent.objects.create(
            user=father_user,
            student=student,
            first_name='Peter',
            last_name='Waweru',
            phone='+254711999888',
            relation_ship='Father'
        )

        mother_user = User.objects.create_user(username='mother_waweru', first_name='Grace', last_name='Waweru')
        Parent.objects.create(
            user=mother_user,
            student=student,
            first_name='Grace',
            last_name='Waweru',
            phone='+254711999889',
            relation_ship='Mother'
        )

        # Run report query with search="Waweru"
        report = AdmissionsRegisterReport(self.staff_user, {'search': 'Waweru'})
        qs = report.get_base_queryset()

        # The count MUST be exactly 1, not 2
        self.assertEqual(qs.count(), 1)
        preview = report.get_preview_data(page=1, page_size=10)
        self.assertEqual(len(preview['results']), 1)
        self.assertEqual(preview['results'][0]['admission_number'], 'REP-DUP-001')

    def test_pagination_stable_after_distinct_ordering(self):
        """Assert that walking pages 1..N with distinct ordering never skips or duplicates rows."""
        created_admissions = []
        for i in range(12):
            s_user = User.objects.create_user(
                username=f'pagestudent_{i}',
                first_name=f'Student_{i:02d}',
                last_name='Wambui',
                gender='M' if i % 2 == 0 else 'F'
            )
            s = Student.objects.create(
                student=s_user,
                admission_number=f'REP-PAGE-{i:03d}',
                status='active'
            )
            ap = Application.objects.create(
                first_name=f'Student_{i:02d}',
                last_name='Wambui',
                applying_for_grade=self.grade,
                applying_for_curriculum=self.curriculum,
                intake=self.intake,
                created_by=self.staff_user,
                updated_by=self.staff_user
            )
            a = Admission.objects.create(
                application=ap,
                student=s,
                admission_number=f'REP-PAGE-{i:03d}',
                admission_date=datetime.date(2026, 3, 1),
                created_by=self.staff_user,
                updated_by=self.staff_user
            )
            created_admissions.append(a.id)

            # Add parent with searchable keyword
            p_user = User.objects.create_user(username=f'page_parent_{i}', last_name='Wambui')
            Parent.objects.create(
                user=p_user,
                student=s,
                first_name='Guardian',
                last_name='Wambui',
                phone=f'+254700000{i:03d}'
            )

        report = AdmissionsRegisterReport(self.staff_user, {'search': 'Wambui'})
        
        # Walk 3 pages of size 4
        seen_ids = []
        for page_num in [1, 2, 3]:
            page_data = report.get_preview_data(page=page_num, page_size=4)
            for row in page_data['results']:
                seen_ids.append(row['id'])

        # Total seen should be 12, each strictly unique
        self.assertEqual(len(seen_ids), 12)
        self.assertEqual(len(set(seen_ids)), 12)

    def test_single_query_summary_metrics(self):
        """Assert summary metrics return exact male, female, total, and transfer aggregates."""
        report = AdmissionsRegisterReport(self.staff_user, {})
        qs = report.get_base_queryset()
        metrics = report.get_summary_metrics(qs)
        self.assertIn('total_admitted', metrics)
        self.assertIn('male_count', metrics)
        self.assertIn('female_count', metrics)
        self.assertIn('transfers_in', metrics)
        self.assertEqual(metrics['total_admitted'], metrics['male_count'] + metrics['female_count'])
