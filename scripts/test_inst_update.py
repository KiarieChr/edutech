import django, os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
django.setup()

from core.api_views import InstitutionProfileSerializer
from core.models import InstitutionProfile

inst = InstitutionProfile.get_instance()
print(f'Current type: {inst.institution_type}')

# Test new choices
for t in ['lower_primary', 'upper_primary', 'primary', 'secondary', 'mixed']:
    s = InstitutionProfileSerializer(inst, data={'institution_type': t}, partial=True)
    valid = s.is_valid()
    print(f'  {t}: valid={valid} {s.errors if not valid else ""}')

# Test what frontend might be sending
print('\nTest empty optional fields:')
s = InstitutionProfileSerializer(inst, data={'website': '', 'portal_url': '', 'email': ''}, partial=True)
print(f'  valid={s.is_valid()} {s.errors if not s.is_valid() else ""}')

# Test full payload similar to what frontend sends
print('\nTest full PATCH with logo:')
s = InstitutionProfileSerializer(inst, data={'name': 'Test School', 'institution_type': 'lower_primary'}, partial=True)
print(f'  valid={s.is_valid()} {s.errors if not s.is_valid() else ""}')
