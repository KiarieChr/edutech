import os
import django
import sys

# Setup Django environment
sys.path.append(r'd:\Tims Projects\edutech')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from academics.models import ClassSession
from student_settings.models import Intake

def check_sessions():

    with open('session_log.txt', 'w', encoding='utf-8') as f:
        count = ClassSession.objects.count()
        f.write(f"Total ClassSessions: {count}\n")
        
        sessions = ClassSession.objects.all().order_by('-created_at')[:20]
        for s in sessions:
            f.write(f"ID: {s.id}, Name: {s.name}, AY: {s.academic_year_id} ({s.academic_year}), Term: {s.term}, Grade: {s.grade}\n")

        f.write("\n--- Intakes ---\n")
        intakes = Intake.objects.all()
        for i in intakes:
            f.write(f"Intake: {i.name} (ID: {i.id}), AY: {i.academic_year_id}\n")

if __name__ == "__main__":
    check_sessions()
