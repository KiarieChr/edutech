from datetime import date, time
from django.contrib.auth import get_user_model
from django_tenants.test.cases import FastTenantTestCase
from rest_framework.test import APIClient

from student_settings.models import AcademicYear, Term, Curriculum, CurriculumLevel, GradeStructure
from academics.models import ClassSession
from timetable.models import Room, Subject, TimePeriod, WorkAllocation, TimetableSlot
from timetable.services.scheduling_service import SchedulingService, SchedulingMode, SchedulingPreferences
from timetable.services.conflict_engine import ConflictEngine, ConflictType

User = get_user_model()


class RoomAssignmentAndSchedulingTests(FastTenantTestCase):
    """
    Automated Test Suite for Milestone 2:
    - Room-to-Grade Assignment Rules (dedicated, preferred, shared)
    - Scheduling Engine room selection logic
    - ConflictEngine validation for room assignment rules
    """

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = "Timetable Test Tenant"
        tenant.save()

    @classmethod
    def setup_domain(cls, domain):
        domain.is_primary = True

    def setUp(self):
        super().setUp()
        self.teacher = User.objects.create_user(
            username='teacher_john',
            email='john@school.ac.ke',
            password='testpassword123',
            first_name='John',
            last_name='Mwangi'
        )

        # Academic infrastructure
        self.academic_year = AcademicYear.objects.create(
            name='2026',
            start_date=date(2026, 1, 5),
            end_date=date(2026, 11, 27),
            is_current=True
        )
        self.term = Term.objects.create(
            academic_year=self.academic_year,
            name='Term 1 2026',
            start_date=date(2026, 1, 5),
            end_date=date(2026, 4, 3),
            order=1
        )
        self.curriculum = Curriculum.objects.create(name='CBC', code='CBC')
        self.level = CurriculumLevel.objects.create(
            curriculum=self.curriculum,
            name='Junior Secondary',
            order=1
        )
        self.grade7 = GradeStructure.objects.create(
            curriculum=self.curriculum,
            curriculum_level=self.level,
            name='Grade 7',
            level_order=7
        )
        self.grade8 = GradeStructure.objects.create(
            curriculum=self.curriculum,
            curriculum_level=self.level,
            name='Grade 8',
            level_order=8
        )

        self.class_session_g7 = ClassSession.objects.create(
            name='Grade 7 East - Term 1 2026',
            grade=self.grade7,
            term=self.term,
            academic_year=self.academic_year,
            curriculum=self.curriculum,
            curriculum_level=self.level,
            status='active'
        )
        self.class_session_g8 = ClassSession.objects.create(
            name='Grade 8 West - Term 1 2026',
            grade=self.grade8,
            term=self.term,
            academic_year=self.academic_year,
            curriculum=self.curriculum,
            curriculum_level=self.level,
            status='active'
        )

        # Schedulable period: Period 1 (08:00 - 08:45)
        self.period1 = TimePeriod.objects.create(
            name='Period 1',
            order=1,
            start_time=time(8, 0),
            end_time=time(8, 45),
            is_schedulable=True,
            is_active=True,
            applies_to_days='0,1,2,3,4,5'
        )

        # Subjects
        self.science_subject = Subject.objects.create(
            name='Integrated Science',
            code='SC-7',
            curriculum=self.curriculum,
            curriculum_level=self.level,
            weekly_lessons=1
        )
        self.math_subject = Subject.objects.create(
            name='Mathematics',
            code='MATH-7',
            curriculum=self.curriculum,
            curriculum_level=self.level,
            weekly_lessons=1
        )

        self.scheduling_service = SchedulingService()
        self.conflict_engine = ConflictEngine()

    def test_dedicated_room_never_assigned_to_unassigned_grade(self):
        """
        Prove: A 'dedicated' room is NEVER assigned to an unassigned grade.
        Grade 8 dedicated science lab must strictly exclude Grade 7.
        """
        # Create a dedicated lab for Grade 8 only
        dedicated_lab = Room.objects.create(
            name='Grade 8 Advanced Science Lab',
            room_type='lab',
            capacity=40,
            assignment_mode='dedicated',
            is_active=True,
            is_active_for_scheduling=True,
        )
        dedicated_lab.assigned_grades.add(self.grade8)

        # Grade 7 allocation requires a lab
        alloc = WorkAllocation.objects.create(
            teacher=self.teacher,
            subject=self.science_subject,
            class_session=self.class_session_g7,
            lessons_per_week=1,
            required_room_type='lab',
            priority=1,
            is_active=True,
        )

        # Attempt to select room for Grade 7
        room, error_reason = self.scheduling_service._select_room(
            subject=self.science_subject,
            class_session=self.class_session_g7,
            day_of_week=0,
            start_time=time(8, 0),
            end_time=time(8, 45),
            preferences=SchedulingPreferences(),
            allocation=alloc,
        )

        self.assertIsNone(room, "Dedicated room must NOT be assigned to an unassigned grade")
        self.assertIn("No available Laboratory permitted for Grade 7", error_reason)

        # Run full auto-scheduler for Grade 7
        result = self.scheduling_service.generate_timetable(
            class_session=self.class_session_g7,
            mode=SchedulingMode.SEMI_AUTO,
        )

        # Must report unplaced with clear reason
        self.assertEqual(result.placed_count, 0)
        self.assertEqual(len(result.unplaced), 1)
        self.assertIn("permitted for Grade 7", result.unplaced[0]['reason'])

        # ConflictEngine must also reject manual placement of Grade 7 into this room
        conflict_result = self.conflict_engine.check_slot_creation(
            class_session=self.class_session_g7,
            subject=self.science_subject,
            teacher=self.teacher,
            day_of_week=0,
            start_time=time(8, 0),
            end_time=time(8, 45),
            room=dedicated_lab,
        )
        self.assertFalse(conflict_result.is_valid)
        self.assertTrue(any("dedicated" in c.message for c in conflict_result.conflicts))

    def test_preferred_room_chosen_over_generic_room_when_both_available(self):
        """
        Prove: A 'preferred' room is chosen over a generic shared room when both are available.
        """
        # Shared room
        shared_room = Room.objects.create(
            name='General Classroom A',
            room_type='classroom',
            capacity=40,
            assignment_mode='shared',
            is_active=True,
            is_active_for_scheduling=True,
        )

        # Preferred room for Grade 7
        preferred_room = Room.objects.create(
            name='Junior Secondary Block Room 101',
            room_type='classroom',
            capacity=40,
            assignment_mode='preferred',
            is_active=True,
            is_active_for_scheduling=True,
        )
        preferred_room.assigned_grades.add(self.grade7)

        alloc = WorkAllocation.objects.create(
            teacher=self.teacher,
            subject=self.math_subject,
            class_session=self.class_session_g7,
            lessons_per_week=1,
            required_room_type='classroom',
            priority=1,
            is_active=True,
        )

        # Select room for Grade 7: preferred room should be chosen
        selected_room, err = self.scheduling_service._select_room(
            subject=self.math_subject,
            class_session=self.class_session_g7,
            day_of_week=0,
            start_time=time(8, 0),
            end_time=time(8, 45),
            preferences=SchedulingPreferences(),
            allocation=alloc,
        )

        self.assertIsNotNone(selected_room)
        self.assertEqual(selected_room.id, preferred_room.id, "Preferred room must take precedence over shared room")

    def test_dedicated_room_assigned_to_assigned_grade(self):
        """
        Prove: A dedicated room IS successfully assigned to a grade that is in assigned_grades.
        """
        lab = Room.objects.create(
            name='Grade 7 Dedicated Lab',
            room_type='lab',
            capacity=40,
            assignment_mode='dedicated',
            is_active=True,
            is_active_for_scheduling=True,
        )
        lab.assigned_grades.add(self.grade7)

        alloc = WorkAllocation.objects.create(
            teacher=self.teacher,
            subject=self.science_subject,
            class_session=self.class_session_g7,
            lessons_per_week=1,
            required_room_type='lab',
            priority=1,
            is_active=True,
        )

        result = self.scheduling_service.generate_timetable(
            class_session=self.class_session_g7,
            mode=SchedulingMode.SEMI_AUTO,
        )

        self.assertEqual(result.placed_count, 1)
        slot = TimetableSlot.objects.get(pk=result.created_slots[0])
        self.assertEqual(slot.room, lab)

    def test_inactive_for_scheduling_room_excluded(self):
        """
        Prove: A room with is_active_for_scheduling=False is never scheduled.
        """
        inactive_room = Room.objects.create(
            name='Renovating Lab',
            room_type='lab',
            capacity=40,
            assignment_mode='shared',
            is_active=True,
            is_active_for_scheduling=False,  # Under maintenance
        )

        alloc = WorkAllocation.objects.create(
            teacher=self.teacher,
            subject=self.science_subject,
            class_session=self.class_session_g7,
            lessons_per_week=1,
            required_room_type='lab',
            priority=1,
            is_active=True,
        )

        room, err = self.scheduling_service._select_room(
            subject=self.science_subject,
            class_session=self.class_session_g7,
            day_of_week=0,
            start_time=time(8, 0),
            end_time=time(8, 45),
            preferences=SchedulingPreferences(),
            allocation=alloc,
        )
        self.assertIsNone(room)
        self.assertIn("permitted for Grade 7", err)
