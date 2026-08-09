#!/usr/bin/env python
"""
Script to populate Intake model from existing AcademicYear data.
Run this after migrating to the new Intake model.

Usage:
    python populate_intakes.py
"""

import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'edutech.settings')
django.setup()

from student_settings.models import AcademicYear, Intake
from django.db import transaction


def populate_intakes():
    """Create Intake records from existing AcademicYear records"""
    
    print("=" * 60)
    print("Populating Intakes from Academic Years")
    print("=" * 60)
    
    academic_years = AcademicYear.objects.filter(is_deleted=False).order_by('start_date')
    
    if not academic_years.exists():
        print("\n⚠️  No academic years found. Please create academic years first.")
        return
    
    print(f"\nFound {academic_years.count()} academic year(s)")
    print("-" * 60)
    
    created_count = 0
    skipped_count = 0
    
    with transaction.atomic():
        for year in academic_years:
            # Generate intake name and code
            intake_name = f"{year.name} Intake"
            intake_code = f"INT{year.name.replace('/', '').replace('-', '')}"
            
            # Check if intake already exists
            existing = Intake.objects.filter(
                academic_year=year
            ).first()
            
            if existing:
                print(f"⏭️  Skipped: {intake_name} (already exists)")
                skipped_count += 1
                continue
            
            # Create intake
            intake = Intake.objects.create(
                academic_year=year,
                name=intake_name,
                code=intake_code,
                start_date=year.start_date,
                description=f"Intake for academic year {year.name}",
                is_active=year.is_current,
                created_by=year.created_by,
                updated_by=year.updated_by
            )
            
            print(f"✅ Created: {intake.name} ({intake.code})")
            created_count += 1
    
    print("-" * 60)
    print(f"\n📊 Summary:")
    print(f"   Created: {created_count}")
    print(f"   Skipped: {skipped_count}")
    print(f"   Total:   {created_count + skipped_count}")
    
    if created_count > 0:
        print(f"\n✅ Successfully created {created_count} intake(s)!")
    
    print("\n" + "=" * 60)


def migrate_student_intakes():
    """
    Optional: Migrate students from intake_year to intake.
    This is only needed if you have existing students with intake_year set.
    """
    from student_management.models import Student
    
    print("\n" + "=" * 60)
    print("Migrating Student Intake Assignments")
    print("=" * 60)
    
    # Note: This assumes students might have been manually assigned to academic years
    # In the new model, they should be assigned to Intake objects
    
    students_without_intake = Student.objects.filter(intake__isnull=True)
    
    if not students_without_intake.exists():
        print("\n✅ All students already have intake assignments!")
        return
    
    print(f"\nFound {students_without_intake.count()} student(s) without intake")
    print("Note: You may need to manually assign these students to intakes.")
    print("=" * 60)


if __name__ == '__main__':
    try:
        populate_intakes()
        migrate_student_intakes()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
