#!/usr/bin/env python
"""
Test script to verify all API endpoints are properly implemented and accessible
"""
import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ackkirinyaga.settings')

# For edutech project
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ackkirinyaga.settings')

django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

User = get_user_model()

def test_endpoints():
    """Test all API endpoints"""
    print("=" * 80)
    print("Testing API Endpoints")
    print("=" * 80)
    
    client = APIClient()
    
    # Create a test user
    print("\n1. Creating test user...")
    test_user, created = User.objects.get_or_create(
        username='testuser',
        defaults={
            'email': 'testuser@example.com',
            'first_name': 'Test',
            'last_name': 'User',
            'is_active': True
        }
    )
    test_user.set_password('testpass123')
    test_user.save()
    
    # Get or create token
    token, _ = Token.objects.get_or_create(user=test_user)
    client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    print(f"✓ Test user created: {test_user.username}")
    print(f"✓ Token: {token.key}")
    
    # Dictionary to track endpoint results
    endpoints = {}
    
    # Test 1: Profile endpoint
    print("\n2. Testing GET /api/users/profile/")
    response = client.get('/api/users/profile/')
    endpoints['GET /api/users/profile/'] = {
        'status': response.status_code,
        'success': response.status_code in [200, 201]
    }
    print(f"   Status: {response.status_code} - {'✓' if response.status_code in [200, 201] else '✗'}")
    
    # Test 2: Update profile endpoint
    print("\n3. Testing PUT /api/users/update_profile/")
    data = {'first_name': 'UpdatedTest'}
    response = client.put('/api/users/update_profile/', data, format='json')
    endpoints['PUT /api/users/update_profile/'] = {
        'status': response.status_code,
        'success': response.status_code in [200, 201]
    }
    print(f"   Status: {response.status_code} - {'✓' if response.status_code in [200, 201] else '✗'}")
    
    # Test 3: Sessions endpoint
    print("\n4. Testing GET /api/users/sessions/")
    response = client.get('/api/users/sessions/')
    endpoints['GET /api/users/sessions/'] = {
        'status': response.status_code,
        'success': response.status_code in [200, 201]
    }
    print(f"   Status: {response.status_code} - {'✓' if response.status_code in [200, 201] else '✗'}")
    
    # Test 4: Activities endpoint
    print("\n5. Testing GET /api/users/activities/")
    response = client.get('/api/users/activities/')
    endpoints['GET /api/users/activities/'] = {
        'status': response.status_code,
        'success': response.status_code in [200, 201]
    }
    print(f"   Status: {response.status_code} - {'✓' if response.status_code in [200, 201] else '✗'}")
    
    # Test 5: Users list endpoint
    print("\n6. Testing GET /api/users/")
    response = client.get('/api/users/')
    endpoints['GET /api/users/'] = {
        'status': response.status_code,
        'success': response.status_code in [200, 201]
    }
    print(f"   Status: {response.status_code} - {'✓' if response.status_code in [200, 201] else '✗'}")
    if response.status_code in [200, 201]:
        print(f"   Response data keys: {response.data.keys() if hasattr(response, 'data') else 'N/A'}")
    
    # Test 6: Change password endpoint
    print("\n7. Testing POST /api/users/change_password/")
    data = {
        'old_password': 'testpass123',
        'new_password': 'newpass123',
        'confirm_new_password': 'newpass123'
    }
    response = client.post('/api/users/change_password/', data, format='json')
    endpoints['POST /api/users/change_password/'] = {
        'status': response.status_code,
        'success': response.status_code in [200, 201]
    }
    print(f"   Status: {response.status_code} - {'✓' if response.status_code in [200, 201] else '✗'}")
    
    # Reset password for next tests
    test_user.set_password('testpass123')
    test_user.save()
    
    # Test 7: Logout all endpoint
    print("\n8. Testing POST /api/users/logout_all/")
    response = client.post('/api/users/logout_all/')
    endpoints['POST /api/users/logout_all/'] = {
        'status': response.status_code,
        'success': response.status_code in [200, 201]
    }
    print(f"   Status: {response.status_code} - {'✓' if response.status_code in [200, 201] else '✗'}")
    
    # Re-authenticate after logout_all
    client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    
    # Test 8: Users list (admin endpoint)
    print("\n9. Testing GET /api/users/ (list all)")
    response = client.get('/api/users/')
    endpoints['GET /api/users/ (list)'] = {
        'status': response.status_code,
        'success': response.status_code in [200, 201]
    }
    print(f"   Status: {response.status_code} - {'✓' if response.status_code in [200, 201] else '✗'}")
    
    # Print summary
    print("\n" + "=" * 80)
    print("ENDPOINT TEST SUMMARY")
    print("=" * 80)
    
    passed = sum(1 for e in endpoints.values() if e['success'])
    total = len(endpoints)
    
    for endpoint, result in endpoints.items():
        status_symbol = '✓' if result['success'] else '✗'
        print(f"{status_symbol} {endpoint:45} - Status: {result['status']}")
    
    print("=" * 80)
    print(f"Total: {passed}/{total} endpoints working")
    print("=" * 80)
    
    return passed == total

if __name__ == '__main__':
    success = test_endpoints()
    exit(0 if success else 1)
