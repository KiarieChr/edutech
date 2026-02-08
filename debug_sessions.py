import os
import django
import sys

# Setup Django environment
sys.path.append(r'd:\Tims Projects\edutech')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from student_settings.models import Intake, AcademicYear, Term, GradeStructure

def diagnose_intake_progression(intake_id=None):
    if intake_id:
        intakes = Intake.objects.filter(id=intake_id)
    else:
        intakes = Intake.objects.all()


    with open('debug_log.txt', 'w', encoding='utf-8') as f:
        f.write(f"Checking {intakes.count()} intakes...\n")

        for intake in intakes:
            f.write(f"\n--- Intake: {intake.name} (ID: {intake.id}) ---\n")
            if not intake.entry_grade:
                f.write("ERROR: No entry_grade set.\n")
                continue
            
            start_year = intake.academic_year
            start_grade = intake.entry_grade
            curriculum = start_grade.curriculum
            
            f.write(f"Start Year: {start_year}, Start Grade: {start_grade}, Curriculum: {curriculum}\n")
            
            # Years
            years = AcademicYear.objects.filter(
                start_date__gte=start_year.start_date,
                is_deleted=False
            ).order_by('start_date')
            f.write(f"Found {years.count()} future/current years.\n")
            
            # Grades
            grades = GradeStructure.objects.filter(
                curriculum=curriculum,
                level_order__gte=start_grade.level_order,
                is_active=True,
                is_deleted=False
            ).order_by('level_order')
            f.write(f"Found {grades.count()} future/current grades.\n")
            
            progression_map = list(zip(years, grades))
            f.write(f"Progression Map Size: {len(progression_map)}\n")
            
            if len(grades) > len(years):
                f.write(f"ERROR: Inconsistency! Need {len(grades) - len(years)} more years.\n")
                
            for year, grade in progression_map:
                terms = Term.objects.filter(academic_year=year, is_deleted=False)
                f.write(f"  Year {year} -> Grade {grade}: Found {terms.count()} terms.\n")
                if not terms.exists():
                    f.write(f"  ERROR: No terms for year {year}!\n")

diagnose_intake_progression()
