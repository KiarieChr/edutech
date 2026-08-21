import django, os, json
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
django.setup()

from django.test import RequestFactory
from django.contrib.auth import get_user_model
from student_settings.views import GradeStructureViewSet, CurriculumLevelViewSet

User = get_user_model()
user = User.objects.first()

factory = RequestFactory()

# Test classes
request = factory.get('/api/settings/classes/')
request.user = user
response = GradeStructureViewSet.as_view({'get': 'list'})(request)
response.render()
data = json.loads(response.content)
items = data if isinstance(data, list) else data.get('results', [])
print(f'CLASSES: {len(items)} grades')
for g in items:
    curr = g.get('curriculum_name', g.get('curriculum', '?'))
    print(f'  {curr} | {g.get("name", "?")}')

print()

# Test curriculum levels
request2 = factory.get('/api/settings/curriculum-levels/')
request2.user = user
response2 = CurriculumLevelViewSet.as_view({'get': 'list'})(request2)
response2.render()
data2 = json.loads(response2.content)
items2 = data2 if isinstance(data2, list) else data2.get('results', [])
print(f'CURRICULUM LEVELS: {len(items2)} levels')
for l in items2:
    curr = l.get('curriculum_name', l.get('curriculum', '?'))
    print(f'  {curr} | {l.get("name", "?")}')
