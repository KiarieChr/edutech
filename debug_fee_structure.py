import os
import django
import sys

# Setup Django Environment
sys.path.append('d:\\Tims Projects\\edutech')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from student_settings.models import Enrollment, Term, AcademicYear, GradeStructure, Curriculum
from fees.models import FeeStructure

def debug_billing_lookup():
    with open("debug_results.log", "w", encoding="utf-8") as f:
        f.write("--- Debugging Fee Structure Lookup ---\n")
        
        # 1. Get an Active Enrollment (Sample)
        # We'll look for one in 2026
        enrollment = Enrollment.objects.filter(is_active=True).order_by('-id').first()
        
        if not enrollment:
            f.write("No active enrollments found!\n")
            return

        f.write(f"Checking for Student: {enrollment.student}\n")
        f.write(f"Enrollment ID: {enrollment.id}\n")
        
        grade = enrollment.grade
        term = enrollment.term
        year = enrollment.academic_year
        curriculum = enrollment.curriculum
        
        f.write(f"\nContext:\n")
        f.write(f"  Year: {year} (ID: {year.id})\n")
        f.write(f"  Term: {term} (ID: {term.id})\n")
        f.write(f"  Grade: {grade} (ID: {grade.id})\n")
        f.write(f"  Curriculum: {curriculum} (ID: {curriculum.id if curriculum else 'None'})\n")

        # 2. Query Fee Structures strictly
        structures = FeeStructure.objects.filter(
            academic_year=year,
            term=term,
            grade=grade
        )
        
        f.write(f"\nFound {structures.count()} Fee Structures matching Year+Term+Grade:\n")
        for fs in structures:
            f.write(f"  ID: {fs.id}\n")
            f.write(f"  Name: {fs}\n")
            f.write(f"  Status: {fs.status} (Expected: 'ACTIVE')\n")
            f.write(f"  Curriculum: {fs.curriculum} (ID: {fs.curriculum.id if fs.curriculum else 'None'})\n")
            
            # Check strict match logic from services.py
            match = False
            if fs.status == 'ACTIVE':
                 if not fs.curriculum:
                     match = True # Default fallback
                 elif fs.curriculum == curriculum:
                     match = True # Exact match
            
            f.write(f"  Matches Current Logic? {match}\n")

        # 3. Check for broader matches (Maybe status is wrong?)
        if structures.count() == 0:
            f.write("\nChecking broader matches (ignoring grade)...\n")
            broad = FeeStructure.objects.filter(academic_year=year, term=term)
            for fs in broad:
                f.write(f"  [Grade Mismatch?] ID: {fs.id} - Grade: {fs.grade} ({fs.grade.id})\n")

if __name__ == "__main__":
    debug_billing_lookup()
