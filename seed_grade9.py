import random

from django.contrib.auth import get_user_model
from student_settings.models import GradeStructure
from academics.models import ClassSession, StudentSessionEnrollment
from timetable.models import Subject
from examinations.models import Examination, AssessmentType, StudentMark
from django.utils import timezone

User = get_user_model()

def seed_grade9_marks():
    print("Starting Grade 9 marks seeding...")
    
    # 1. Find Grade 9
    grade = GradeStructure.objects.filter(name__icontains='9').first()
    if not grade:
        print("Could not find a Grade with '9' in the name.")
        return

    print(f"Found Grade: {grade.name}")

    # 2. Find active class session for Grade 9
    session = ClassSession.objects.filter(grade=grade, status__in=['active', 'scheduled']).first()
    if not session:
        print(f"No active class session found for {grade.name}.")
        # Let's see if there is ANY session
        session = ClassSession.objects.filter(grade=grade).last()
        if not session:
            print("No class session found at all. Cannot proceed.")
            return
        else:
            print(f"Using session '{session.name}' even though it has status '{session.status}'")
            
    print(f"Using Session: {session.name}")

    # 3. Get enrolled active students
    enrollments = StudentSessionEnrollment.objects.filter(session=session, status='active')
    if not enrollments.exists():
        print("No active enrolled students found in this session.")
        return
        
    print(f"Found {enrollments.count()} active students.")
    
    # 4. Get Existing Exams for this session
    exams = Examination.objects.filter(class_session=session)
    if not exams.exists():
        print("No exams scheduled for this class session yet. Please schedule an exam first.")
        return
        
    print(f"Found {exams.count()} scheduled exams for this session. Seeding marks...")
    
    # Get a user for 'entered_by'
    user = User.objects.filter(is_superuser=True).first() or User.objects.first()

    marks_created = 0
    exams_completed = 0
    
    # 6. Seed Marks for existing exams
    for exam in exams:
        # Mark the exam as completed
        if exam.status != 'completed':
            exam.status = 'completed'
            exam.save()
            exams_completed += 1
            
        # Add marks for all active enrolled students
        for enrollment in enrollments:
            raw_mark = random.randint(35, 98) # Random mark between 35 and 98
            mark, mark_created = StudentMark.objects.update_or_create(
                examination=exam,
                student=enrollment.student,
                defaults={
                    'raw_mark': raw_mark,
                    'is_absent': False,
                    'entered_by': user
                }
            )
            if mark_created:
                marks_created += 1
                
    print(f"Success! Marked {exams_completed} exams as completed and entered {marks_created} student marks.")
    print("You can now compute term results in the dashboard.")

def run_for_all_tenants():
    from tenants.models import Client
    from django_tenants.utils import schema_context
    
    tenants = Client.objects.exclude(schema_name='public')
    if not tenants.exists():
        print("No tenants found!")
        return
        
    for tenant in tenants:
        print(f"\n--- Seeding for Tenant: {tenant.schema_name} ---")
        with schema_context(tenant.schema_name):
            seed_grade9_marks()

if __name__ == '__main__':
    run_for_all_tenants()
