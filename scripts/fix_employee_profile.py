import os
import django
import sys
from datetime import date

# Setup Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from workforce.core_models import Employee

User = get_user_model()

def create_employee_profile():
    # Find the user 'james' or the first superuser
    try:
        user = User.objects.get(username='james')
    except User.DoesNotExist:
        print("User 'james' not found. searching for superuser...")
        user = User.objects.filter(is_superuser=True).first()
    
    if not user:
        print("No suitable user found to link employee profile.")
        return

    print(f"Checking profile for user: {user.username} ({user.email})")

    # Check if profile exists
    if hasattr(user, 'employee_profile') and user.employee_profile:
        print(f"User already has employee profile: {user.employee_profile}")
        return

    # Create dummy employee
    print("Creating new Employee profile...")
    
    try:
        employee = Employee.objects.create(
            employee_no=f"EMP-{user.id:04d}",
            first_name=user.first_name or "James",
            last_name=user.last_name or "Admin",
            date_of_birth=date(1990, 1, 1),
            gender='male',
            national_id=f"ID-{user.id:05d}",
            personal_email=user.email or "james@example.com",
            official_email=user.email or "james@example.com",
            phone_primary="0700000000",
            employee_category='teaching',
            payroll_type='monthly',
            hire_date=date(2023, 1, 1),
            user=user
        )
        print(f"Successfully created Employee: {employee}")
        print("You can now retry the interview evaluation submission.")
        
    except Exception as e:
        print(f"Failed to create employee: {e}")

if __name__ == "__main__":
    create_employee_profile()
