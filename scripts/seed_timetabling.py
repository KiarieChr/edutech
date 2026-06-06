import os
import sys
import django
from datetime import time

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from academics.models import ClassSession
from timetable.models import Subject, Room, TimePeriod, WorkAllocation
from student_settings.models import Curriculum, AcademicYear

User = get_user_model()

def run():
    print("Seeding timetabling data...")
    
    # 1. Get Existing Teachers
    teachers = list(User.objects.filter(is_lecturer=True)[:5])
    if len(teachers) < 5:
        print("Not enough teachers found!")
        return
    t_science, t_math, t_lang, t_hum, t_tech = teachers

    # 2. Rooms
    print("Creating rooms...")
    r_g9, _ = Room.objects.get_or_create(name="Grade 9 Room", defaults={"room_type": "classroom", "capacity": 40})
    r_g10, _ = Room.objects.get_or_create(name="Grade 10 Room", defaults={"room_type": "classroom", "capacity": 40})
    r_g11, _ = Room.objects.get_or_create(name="Grade 11 Room", defaults={"room_type": "classroom", "capacity": 40})
    r_lab, _ = Room.objects.get_or_create(name="Science Lab", defaults={"room_type": "lab", "capacity": 30})
    r_field, _ = Room.objects.get_or_create(name="Sports Field", defaults={"room_type": "field", "capacity": 100})
    
    # 3. Get Existing JS Subjects
    print("Fetching subjects...")
    # Math, English, Kiswahili, Integrated Science, Pre-Technical, Social Studies, RE, PE
    s_math = Subject.objects.filter(code="CBC-JS-MAT").first()
    s_eng = Subject.objects.filter(code="CBC-JS-ENG").first()
    s_ksw = Subject.objects.filter(code="CBC-JS-KSW").first()
    s_sci = Subject.objects.filter(code="CBC-JS-SCI").first()
    s_pts = Subject.objects.filter(code="CBC-JS-PTS").first()
    s_sst = Subject.objects.filter(code="CBC-JS-SS").first()
    s_re = Subject.objects.filter(code="CBC-JS-RE").first()
    s_pe = Subject.objects.filter(code="CBC-JS-PE").first()
    
    if not all([s_math, s_eng, s_ksw, s_sci, s_pts, s_sst, s_re, s_pe]):
        print("Some CBC Junior Secondary subjects are missing in the database.")
        return

    # 4. Time Periods
    print("Creating Time Periods...")
    year_2026 = AcademicYear.objects.filter(name__icontains="2026").first()
    if not year_2026:
        print("Academic Year 2026 not found!")
        return
        
    periods = [
        {"order": 1, "name": "Period 1", "short": "P1", "start": time(8, 0), "end": time(8, 40), "type": "lesson"},
        {"order": 2, "name": "Period 2", "short": "P2", "start": time(8, 40), "end": time(9, 20), "type": "lesson"},
        {"order": 3, "name": "Period 3", "short": "P3", "start": time(9, 20), "end": time(10, 0), "type": "lesson"},
        {"order": 4, "name": "Break", "short": "BRK", "start": time(10, 0), "end": time(10, 30), "type": "break"},
        {"order": 5, "name": "Period 4", "short": "P4", "start": time(10, 30), "end": time(11, 10), "type": "lesson"},
        {"order": 6, "name": "Period 5", "short": "P5", "start": time(11, 10), "end": time(11, 50), "type": "lesson"},
        {"order": 7, "name": "Period 6", "short": "P6", "start": time(11, 50), "end": time(12, 30), "type": "lesson"},
        {"order": 8, "name": "Lunch", "short": "LUN", "start": time(12, 30), "end": time(14, 0), "type": "lunch"},
        {"order": 9, "name": "Period 7", "short": "P7", "start": time(14, 0), "end": time(14, 40), "type": "lesson"},
        {"order": 10, "name": "Period 8", "short": "P8", "start": time(14, 40), "end": time(15, 20), "type": "lesson"},
    ]
    
    for pd in periods:
        TimePeriod.objects.get_or_create(
            academic_year=year_2026,
            order=pd["order"],
            defaults={
                "name": pd["name"],
                "short_name": pd["short"],
                "start_time": pd["start"],
                "end_time": pd["end"],
                "period_type": pd["type"],
                "is_schedulable": pd["type"] == "lesson"
            }
        )

    # 5. Work Allocations
    print("Creating Work Allocations...")
    # Grade 9 (ID 9), Grade 10 (ID 28), Grade 11 (ID 29)
    classes = ClassSession.objects.filter(id__in=[9, 28, 29])
    
    for c in classes:
        print(f"Allocating for {c.name}")
        WorkAllocation.objects.get_or_create(class_session=c, subject=s_math, teacher=t_math, defaults={"lessons_per_week": 5})
        WorkAllocation.objects.get_or_create(class_session=c, subject=s_eng, teacher=t_lang, defaults={"lessons_per_week": 5})
        WorkAllocation.objects.get_or_create(class_session=c, subject=s_ksw, teacher=t_lang, defaults={"lessons_per_week": 4})
        WorkAllocation.objects.get_or_create(class_session=c, subject=s_sci, teacher=t_science, defaults={"lessons_per_week": 5, "required_room_type": "lab"})
        WorkAllocation.objects.get_or_create(class_session=c, subject=s_pts, teacher=t_tech, defaults={"lessons_per_week": 4})
        WorkAllocation.objects.get_or_create(class_session=c, subject=s_sst, teacher=t_hum, defaults={"lessons_per_week": 4})
        WorkAllocation.objects.get_or_create(class_session=c, subject=s_re, teacher=t_hum, defaults={"lessons_per_week": 3})
        WorkAllocation.objects.get_or_create(class_session=c, subject=s_pe, teacher=t_tech, defaults={"lessons_per_week": 2, "required_room_type": "field"})

    print("Seeding completed successfully!")

if __name__ == '__main__':
    run()
