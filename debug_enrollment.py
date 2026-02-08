import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from academics.models import StudentSessionEnrollment
from accounts.models import Student

sid = 3
print(f"--- Debugging Student ID: {sid} ---")
try:
    s = Student.objects.get(id=sid)
    # Corrected attribute access: s.student refers to User, which has first_name
    print(f"Student Found: {s.student.username} (Adm: {s.admission_number})")
except Student.DoesNotExist:
    print("Student ID 3 NOT FOUND in database.")

enrollments = StudentSessionEnrollment.objects.filter(student_id=sid)
print(f"Total Enrollments: {enrollments.count()}")

if enrollments.count() == 0:
    print(">> NO ENROLLMENTS FOUND. This explains the 404.")
    print(">> Action: Go to Admissions/Enrollment modules and enroll this student.")
else:
    for e in enrollments:
        print(f" - ID: {e.id}")
        print(f"   Session: {e.session.name if e.session else 'None'}")
        print(f"   Is Active: {e.is_active} (Must be True for billing)")
        print(f"   Status: {e.status}")
