import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import RequestFactory
from django.contrib.auth import get_user_model
from workforce.viewsets import EmployeeViewSet, AttendanceRecordViewSet
from rest_framework.test import APIRequestFactory, force_authenticate

User = get_user_model()
factory = APIRequestFactory()

# Get a user without an employee profile (if possible, or just create one)
user, created = User.objects.get_or_create(username='test_fallback_user', email='test@example.com')

print(f"Testing with user: {user.username}")

# 1. Test my_comprehensive_summary
view = EmployeeViewSet.as_view({'get': 'my_comprehensive_summary'})
request = factory.get('/workforce/api/employees/my_comprehensive_summary/')
force_authenticate(request, user=user)
response = view(request)

print(f"my_comprehensive_summary status: {response.status_code}")
print(f"my_comprehensive_summary data: {response.data}")

# 2. Test my_clock_policy (should fallback to general_policy)
view = AttendanceRecordViewSet.as_view({'get': 'my_clock_policy'})
request = factory.get('/workforce/api/attendance/my_clock_policy/')
force_authenticate(request, user=user)
response = view(request)

print(f"my_clock_policy status: {response.status_code}")
print(f"my_clock_policy data: {response.data}")

# 3. Test general_policy directly
view = AttendanceRecordViewSet.as_view({'get': 'general_policy'})
request = factory.get('/workforce/api/attendance/general_policy/')
force_authenticate(request, user=user)
response = view(request)

print(f"general_policy status: {response.status_code}")
print(f"general_policy data: {response.data}")

if response.status_code == 200:
    print("Verification successful!")
else:
    print("Verification failed!")
