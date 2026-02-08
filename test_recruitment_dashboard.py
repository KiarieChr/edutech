import os
import django
import sys
import json

# Setup Django environment
sys.path.append(r'd:\Tims Projects\edutech')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from rest_framework.test import APIRequestFactory
from recruitment.views import RecruitmentDashboardView
from django.contrib.auth import get_user_model

User = get_user_model()

def test_dashboard():
    factory = APIRequestFactory()
    request = factory.get('/api/recruitment/dashboard/')
    
    # Create a dummy user for authentication bypass (or mock it)
    # Since we are testing the view directly, we can manually attach a user
    try:
        user = User.objects.filter(is_superuser=True).first()
        if not user:
            print("No superuser found due to empty DB, creating one temporary might be needed or skipping auth check.")
            # We can mock the user
            class MockUser:
                is_authenticated = True
                is_staff = True
            user = MockUser()
    except Exception as e:
        print(f"Error getting user: {e}")
        return

    request.user = user
    
    view = RecruitmentDashboardView.as_view()
    response = view(request)
    
    print("Status Code:", response.status_code)
    print("Response Data:")
    print(json.dumps(response.data, indent=2, default=str))

if __name__ == '__main__':
    test_dashboard()
