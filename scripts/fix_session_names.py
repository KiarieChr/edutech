import os
import django
import sys

# Add project root needed?
sys.path.append(os.getcwd())

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from academics.models import ClassSession

def fix_names():
    try:
        sessions = ClassSession.objects.all()
        print(f"Found {sessions.count()} sessions.", flush=True)
        
        updated = 0
        for session in sessions:
            old_name = session.name
            session.name = ""
            session.save()
            print(f"Updated: '{old_name}' -> '{session.name}'", flush=True)
            updated += 1
            
        print(f"Successfully updated {updated} session names.", flush=True)
    except Exception as e:
        print(f"Error: {e}", flush=True)

if __name__ == "__main__":
    fix_names()
