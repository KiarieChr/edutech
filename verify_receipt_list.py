
import os
import django

# Setup Django before imports
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'edutech.settings')
try:
    django.setup()
except Exception:
    pass

from rest_framework.test import APIRequestFactory
from fees.receipt_views import ReceiptViewSet
from django.contrib.auth import get_user_model

def verify_list():
    print("--- Verifying Receipt List Fix ---")
    
    factory = APIRequestFactory()
    request = factory.get('/api/fees/receipts/')
    
    # Mock user
    User = get_user_model()
    request.user = User.objects.filter(is_superuser=True).first()
    
    view = ReceiptViewSet.as_view({'get': 'list'})
    
    try:
        response = view(request)
        print(f"Response Status: {response.status_code}")
        if response.status_code == 200:
            print("SUCCESS: Receipt list fetched successfully!")
            # Print a few fields to confirm
            if response.data.get('results'):
                first = response.data['results'][0]
                print(f"Sample Receipt: {first.get('receipt_number')} issued by {first.get('issued_by')}")
        else:
            print(f"FAIL: Status {response.status_code}")
            print(f"Data: {response.data}")
            
    except Exception as e:
        print(f"EXCEPTION: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_list()
