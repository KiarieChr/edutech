import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from journals.models import JournalEntry
from journals.serializers import JournalEntrySerializer
from rest_framework.renderers import JSONRenderer

try:
    journals = JournalEntry.objects.all()
    print(f"Found {journals.count()} journals.")
    
    serializer = JournalEntrySerializer(journals, many=True)
    # Force evaluation
    data = serializer.data
    # print(json.dumps(data, indent=2, default=str)) # Be careful with large output
    print("Serialization successful.")
    
    if len(data) > 0:
        print("First entry sample:")
        print(data[0])
    
except Exception as e:
    print("Error during serialization:")
    print(e)
    import traceback
    traceback.print_exc()
