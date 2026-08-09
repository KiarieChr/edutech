import os
import re

directory = r"d:\projects\edutech"

def process_file(filepath):
    if not filepath.endswith('.py'):
        return
    if "migrations" in filepath:
        return  # Skip migrations to avoid messing up history

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Pattern 1: from student_management.models import Student, Parent etc
    # We'll just replace 'accounts.models' with 'student_management.models' for the specific classes
    # Actually it's easier to find lines like 'from accounts.models import ...' and replace specific tokens.
    
    new_content = content.replace("from student_management.models import Student", "from student_management.models import Student")
    new_content = new_content.replace("from student_management.models import Parent", "from student_management.models import Parent")
    new_content = new_content.replace("from student_management.models import DepartmentHead", "from student_management.models import DepartmentHead")
    new_content = new_content.replace("from accounts.models import User
from student_management.models import Student", "from accounts.models import User\nfrom student_management.models import Student")
    new_content = new_content.replace("from student_management.models import Student, Parent", "from student_management.models import Student, Parent")
    new_content = new_content.replace("from accounts.models import User
from student_management.models import Student, Parent", "from accounts.models import User\nfrom student_management.models import Student, Parent")
    new_content = new_content.replace("from student_management.models import Parent, Student, User", "from accounts.models import User\nfrom student_management.models import Student, Parent")
    new_content = new_content.replace("from accounts.models import User
from student_management.models import DepartmentHead", "from accounts.models import User\nfrom student_management.models import DepartmentHead")
    new_content = new_content.replace("from accounts.models import User
from student_management.models import Student, Parent, DepartmentHead, LEVEL, RELATION_SHIP", "from accounts.models import User\nfrom student_management.models import Student, Parent, DepartmentHead, LEVEL, RELATION_SHIP")
    
    # Foreign keys
    new_content = new_content.replace("'student_management.Student'", "'student_management.Student'")
    new_content = new_content.replace('"student_management.Student"', '"student_management.Student"')
    new_content = new_content.replace("'student_management.Parent'", "'student_management.Parent'")
    new_content = new_content.replace('"student_management.Parent"', '"student_management.Parent"')
    new_content = new_content.replace("'student_management.DepartmentHead'", "'student_management.DepartmentHead'")
    new_content = new_content.replace('"student_management.DepartmentHead"', '"student_management.DepartmentHead"')

    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated {filepath}")

for root, _, files in os.walk(directory):
    if "venv" in root or ".git" in root:
        continue
    for file in files:
        process_file(os.path.join(root, file))
