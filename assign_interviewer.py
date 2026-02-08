import os
import django
import sys

# Setup Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from workforce.core_models import Employee
from recruitment.models import InterviewSchedule, JobApplication

User = get_user_model()

def assign_interviewer():
    # 1. Get the current user's employee profile
    try:
        user = User.objects.get(username='james') # Adjust if different
    except User.DoesNotExist:
        user = User.objects.filter(is_superuser=True).first()
    
    if not user or not hasattr(user, 'employee_profile'):
        print("Error: User or Employee profile not found. Run fix_employee_profile.py first.")
        return

    interviewer = user.employee_profile
    print(f"Interviewer: {interviewer}")

    # 2. Get the target interview (assuming Application ID 1 based on frontend)
    try:
        application = JobApplication.objects.get(id=1)
        # Get the latest scheduled or in-progress interview
        interview = InterviewSchedule.objects.filter(
            application=application
        ).exclude(status='cancelled').last()
        
        if not interview:
            print("No active interview found for Application #1")
            return

        print(f"Found Interview: {interview} (ID: {interview.id})")
        
        # 3. Assign the interviewer
        if not interview.interviewers.filter(id=interviewer.id).exists():
            print("Assigning interviewer to interview...")
            interview.interviewers.add(interviewer)
            interview.save()
            print("Success! You are now assigned to this interview.")
        else:
            print("You are already assigned to this interview.")

    except JobApplication.DoesNotExist:
        print("Application #1 not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    assign_interviewer()
