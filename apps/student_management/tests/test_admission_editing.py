from datetime import date
from django_tenants.test.cases import FastTenantTestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, force_authenticate

from student_management.models.admission import Admission
from student_management.models.profiles import Student, Parent
from student_management.models.application import Application
from student_settings.models import AcademicYear, Term, Curriculum, CurriculumLevel, GradeStructure, Stream, Enrollment, Intake
from student_management.viewsets.admission_viewset import AdmissionViewSet
from transport.models import Route, Stop, StudentAssignment

User = get_user_model()


class AdmissionDetailEditingTestCase(FastTenantTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.staff_user = User.objects.create_superuser(
            username='admin_editor',
            email='admin@editor.com',
            password='testpassword123'
        )

        # Academic settings
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
        self.intake = Intake.objects.create(
            academic_year=self.academic_year,
            name='January 2026 Intake',
            start_date=date(2026, 1, 5),
            created_by=self.staff_user,
            updated_by=self.staff_user
        )
        self.curriculum = Curriculum.objects.create(name='CBC', code='CBC')
        self.level = CurriculumLevel.objects.create(
            curriculum=self.curriculum,
            name='Primary',
            order=1
        )
        self.grade1 = GradeStructure.objects.create(
            curriculum=self.curriculum,
            curriculum_level=self.level,
            name='Grade 1',
            level_order=1
        )
        self.grade2 = GradeStructure.objects.create(
            curriculum=self.curriculum,
            curriculum_level=self.level,
            name='Grade 2',
            level_order=2
        )
        self.stream1 = Stream.objects.create(grade=self.grade1, name='North')
        self.stream2 = Stream.objects.create(grade=self.grade2, name='South')

        # Transport Route & Stop
        self.route = Route.objects.create(
            route_code='RT-101',
            route_name='Westlands Express',
            direction='two_way',
            status='active'
        )
        self.stop = Stop.objects.create(
            route=self.route,
            stop_name='Sarit Centre',
            stop_order=1
        )

        # Student User & Profile
        self.student_user = User.objects.create_user(
            username='student_101',
            first_name='John',
            last_name='Doe',
            gender='M',
            email='john@test.com'
        )
        self.student = Student.objects.create(
            student=self.student_user,
            admission_number='ADM/2026/101',
            admission_date=date(2026, 1, 10),
            date_of_birth=date(2018, 5, 12),
            blood_group='O+',
            nationality='Kenyan',
            status='active'
        )

        # Parent
        self.parent_user = User.objects.create_user(
            username='parent_101',
            first_name='David',
            last_name='Doe',
            is_parent=True
        )
        self.parent = Parent.objects.create(
            user=self.parent_user,
            student=self.student,
            first_name='David',
            last_name='Doe',
            phone='+254711223344',
            email='david@test.com',
            relation_ship='Father'
        )

        # Enrollment
        self.enrollment = Enrollment.objects.create(
            student=self.student,
            academic_year=self.academic_year,
            term=self.term,
            curriculum=self.curriculum,
            curriculum_level=self.level,
            grade=self.grade1,
            stream=self.stream1,
            stay_status='day_scholar',
            enrollment_date=date(2026, 1, 10),
            status='active',
            is_active=True,
            created_by=self.staff_user,
            updated_by=self.staff_user
        )

        # Application & Admission
        self.application = Application.objects.create(
            first_name='John',
            last_name='Doe',
            gender='M',
            date_of_birth=date(2018, 5, 12),
            guardian_name='David Doe',
            phone_number='+254711223344',
            intake=self.intake,
            applying_for_grade=self.grade1,
            applying_for_curriculum=self.curriculum,
            application_status='accepted'
        )
        self.admission = Admission.objects.create(
            application=self.application,
            student=self.student,
            admission_number='ADM/2026/101',
            admission_date=date(2026, 1, 10),
            created_by=self.staff_user,
            updated_by=self.staff_user
        )

    def test_retrieve_admission_contains_all_details(self):
        """Verify GET returns complete student identity, biodata, academic, parent, and transport fields."""
        view = AdmissionViewSet.as_view({'get': 'retrieve'})
        domain = self.tenant.domains.first().domain if self.tenant.domains.exists() else 'test.localhost'
        request = self.factory.get(f'/api/student-management/admissions/{self.admission.id}/', HTTP_HOST=domain)
        force_authenticate(request, user=self.staff_user)
        response = view(request, pk=self.admission.id)

        self.assertEqual(response.status_code, 200)
        data = response.data

        # Identity & Biodata
        self.assertEqual(data['first_name'], 'John')
        self.assertEqual(data['last_name'], 'Doe')
        self.assertEqual(data['gender'], 'M')
        self.assertEqual(data['blood_group'], 'O+')
        self.assertEqual(data['admission_number'], 'ADM/2026/101')

        # Parent
        self.assertEqual(data['guardian_first_name'], 'David')
        self.assertEqual(data['guardian_last_name'], 'Doe')
        self.assertEqual(data['guardian_phone'], '+254711223344')
        self.assertEqual(data['guardian_relationship'], 'Father')

        # Academic
        self.assertEqual(data['grade_id'], self.grade1.id)
        self.assertEqual(data['stream_id'], self.stream1.id)
        self.assertEqual(data['stay_status'], 'day_scholar')

        # Transport
        self.assertFalse(data['transport_enabled'])

    def test_update_admission_with_biodata_parents_academic_and_route(self):
        """Verify PATCH updates student biodata, parent info, academic enrollment, and transport assignment."""
        view = AdmissionViewSet.as_view({'patch': 'partial_update'})
        domain = self.tenant.domains.first().domain if self.tenant.domains.exists() else 'test.localhost'

        update_payload = {
            # Biodata
            'first_name': 'Jonathan',
            'last_name': 'Doe-Smith',
            'birth_certificate_number': 'BC-998877',
            'allergies': 'Peanuts, Penicillin',
            'medical_conditions': 'Asthma',
            'emergency_contact_name': 'Mary Doe',
            'emergency_contact_phone': '+254722998877',
            'emergency_contact_relationship': 'Aunt',
            'home_address': 'Kilimani, Ring Road Court 4',
            # Parent
            'guardian_first_name': 'David',
            'guardian_last_name': 'Doe-Smith',
            'guardian_phone': '+254700000001',
            'guardian_email': 'david.smith@test.com',
            # Academic
            'grade_id': self.grade2.id,
            'stream_id': self.stream2.id,
            'stay_status': 'boarder',
            # Transport
            'transport_enabled': True,
            'route_id': self.route.id,
            'stop_id': self.stop.id,
            'transport_type': 'two_way'
        }

        request = self.factory.patch(
            f'/api/student-management/admissions/{self.admission.id}/',
            data=update_payload,
            format='json',
            HTTP_HOST=domain
        )
        force_authenticate(request, user=self.staff_user)
        response = view(request, pk=self.admission.id)

        self.assertEqual(response.status_code, 200)

        # 1. Verify User & Student model updates
        self.student_user.refresh_from_db()
        self.assertEqual(self.student_user.first_name, 'Jonathan')
        self.assertEqual(self.student_user.last_name, 'Doe-Smith')

        self.student.refresh_from_db()
        self.assertEqual(self.student.birth_certificate_number, 'BC-998877')
        self.assertEqual(self.student.allergies, 'Peanuts, Penicillin')
        self.assertEqual(self.student.medical_conditions, 'Asthma')
        self.assertEqual(self.student.home_address, 'Kilimani, Ring Road Court 4')
        self.assertEqual(self.student.emergency_contact_name, 'Mary Doe')

        # 2. Verify Parent model updates
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.last_name, 'Doe-Smith')
        self.assertEqual(self.parent.phone, '+254700000001')
        self.assertEqual(self.parent.email, 'david.smith@test.com')

        # 3. Verify Enrollment updates
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.grade_id, self.grade2.id)
        self.assertEqual(self.enrollment.stream_id, self.stream2.id)
        self.assertEqual(self.enrollment.stay_status, 'boarder')

        # 4. Verify Transport assignment created
        assignment = StudentAssignment.objects.filter(student=self.student, is_active=True).first()
        self.assertIsNotNone(assignment)
        self.assertEqual(assignment.route_id, self.route.id)
        self.assertEqual(assignment.stop_id, self.stop.id)
        self.assertEqual(assignment.transport_type, 'two_way')
