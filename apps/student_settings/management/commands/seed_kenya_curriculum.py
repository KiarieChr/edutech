"""
Seed the full Kenyan education curriculum structure.

Creates:
  - Curricula:  CBC (Competency-Based Curriculum), 8-4-4
  - Curriculum Levels (e.g. Lower Primary, Upper Primary, JSS, SSS)
  - Grade Structures (PP1 through Grade 12 / Form 1-4)
  - Learning Areas (CBC) + traditional subject groups
  - Subjects per curriculum level (in the timetable.Subject model)

Idempotent — safe to re-run; existing rows are skipped via get_or_create.
"""

from django.core.management.base import BaseCommand
from student_settings.models import (
    Curriculum,
    CurriculumLevel,
    LearningArea,
    GradeStructure,
)
from timetable.models import Subject


# ─── DATA ────────────────────────────────────────────────────────────────────

CURRICULA = [
    {
        'name': 'CBC',
        'code': 'CBC',
        'description': 'Competency-Based Curriculum (2-6-3-3-3) introduced by KICD in 2017.',
        'status': 'active',
    },
    {
        'name': '8-4-4',
        'code': '844',
        'description': 'Legacy 8-4-4 system (8 years primary, 4 years secondary, 4 years university).',
        'status': 'phased_out',
    },
]

# ── CBC Levels ──
CBC_LEVELS = [
    {'name': 'Pre-Primary', 'order': 1, 'min_years': 2, 'max_years': 2},
    {'name': 'Lower Primary', 'order': 2, 'min_years': 3, 'max_years': 3},
    {'name': 'Upper Primary', 'order': 3, 'min_years': 3, 'max_years': 3},
    {'name': 'Junior Secondary', 'order': 4, 'min_years': 3, 'max_years': 3},
    {'name': 'Senior Secondary', 'order': 5, 'min_years': 3, 'max_years': 3},
]

# ── 8-4-4 Levels ──
EIGHT_FOUR_FOUR_LEVELS = [
    {'name': 'Primary', 'order': 1, 'min_years': 8, 'max_years': 8},
    {'name': 'Secondary', 'order': 2, 'min_years': 4, 'max_years': 4},
]

# ── CBC Grades ──
CBC_GRADES = [
    # Pre-Primary
    {'level': 'Pre-Primary', 'name': 'PP1', 'code': 'PP1', 'order': 1, 'age': '4-5'},
    {'level': 'Pre-Primary', 'name': 'PP2', 'code': 'PP2', 'order': 2, 'age': '5-6'},
    # Lower Primary
    {'level': 'Lower Primary', 'name': 'Grade 1', 'code': 'G1', 'order': 3, 'age': '6-7'},
    {'level': 'Lower Primary', 'name': 'Grade 2', 'code': 'G2', 'order': 4, 'age': '7-8'},
    {'level': 'Lower Primary', 'name': 'Grade 3', 'code': 'G3', 'order': 5, 'age': '8-9'},
    # Upper Primary
    {'level': 'Upper Primary', 'name': 'Grade 4', 'code': 'G4', 'order': 6, 'age': '9-10'},
    {'level': 'Upper Primary', 'name': 'Grade 5', 'code': 'G5', 'order': 7, 'age': '10-11'},
    {'level': 'Upper Primary', 'name': 'Grade 6', 'code': 'G6', 'order': 8, 'age': '11-12'},
    # Junior Secondary
    {'level': 'Junior Secondary', 'name': 'Grade 7', 'code': 'G7', 'order': 9, 'age': '12-13'},
    {'level': 'Junior Secondary', 'name': 'Grade 8', 'code': 'G8', 'order': 10, 'age': '13-14'},
    {'level': 'Junior Secondary', 'name': 'Grade 9', 'code': 'G9', 'order': 11, 'age': '14-15'},
    # Senior Secondary
    {'level': 'Senior Secondary', 'name': 'Grade 10', 'code': 'G10', 'order': 12, 'age': '15-16'},
    {'level': 'Senior Secondary', 'name': 'Grade 11', 'code': 'G11', 'order': 13, 'age': '16-17'},
    {'level': 'Senior Secondary', 'name': 'Grade 12', 'code': 'G12', 'order': 14, 'age': '17-18'},
]

# ── 8-4-4 Grades ──
EIGHT_FOUR_FOUR_GRADES = [
    {'level': 'Primary', 'name': 'Class 1', 'code': 'C1', 'order': 1, 'age': '6-7'},
    {'level': 'Primary', 'name': 'Class 2', 'code': 'C2', 'order': 2, 'age': '7-8'},
    {'level': 'Primary', 'name': 'Class 3', 'code': 'C3', 'order': 3, 'age': '8-9'},
    {'level': 'Primary', 'name': 'Class 4', 'code': 'C4', 'order': 4, 'age': '9-10'},
    {'level': 'Primary', 'name': 'Class 5', 'code': 'C5', 'order': 5, 'age': '10-11'},
    {'level': 'Primary', 'name': 'Class 6', 'code': 'C6', 'order': 6, 'age': '11-12'},
    {'level': 'Primary', 'name': 'Class 7', 'code': 'C7', 'order': 7, 'age': '12-13'},
    {'level': 'Primary', 'name': 'Class 8', 'code': 'C8', 'order': 8, 'age': '13-14'},
    {'level': 'Secondary', 'name': 'Form 1', 'code': 'F1', 'order': 9, 'age': '14-15'},
    {'level': 'Secondary', 'name': 'Form 2', 'code': 'F2', 'order': 10, 'age': '15-16'},
    {'level': 'Secondary', 'name': 'Form 3', 'code': 'F3', 'order': 11, 'age': '16-17'},
    {'level': 'Secondary', 'name': 'Form 4', 'code': 'F4', 'order': 12, 'age': '17-18'},
]

# ── Learning Areas ──
LEARNING_AREAS = [
    {'name': 'Literacy & Indigenous Languages', 'code': 'LIT', 'category': 'languages', 'color': '#ef4444', 'order': 1},
    {'name': 'English Language', 'code': 'ENG', 'category': 'languages', 'color': '#f97316', 'order': 2},
    {'name': 'Kiswahili Language', 'code': 'KSW', 'category': 'languages', 'color': '#f59e0b', 'order': 3},
    {'name': 'Mathematics', 'code': 'MAT', 'category': 'sciences', 'color': '#3b82f6', 'order': 4},
    {'name': 'Integrated Science', 'code': 'SCI', 'category': 'sciences', 'color': '#10b981', 'order': 5},
    {'name': 'Social Studies', 'code': 'SS', 'category': 'humanities', 'color': '#8b5cf6', 'order': 6},
    {'name': 'Religious Education', 'code': 'RE', 'category': 'humanities', 'color': '#6366f1', 'order': 7},
    {'name': 'Creative Arts & Sports', 'code': 'CAS', 'category': 'arts', 'color': '#ec4899', 'order': 8},
    {'name': 'Health Education', 'code': 'HE', 'category': 'pe', 'color': '#14b8a6', 'order': 9},
    {'name': 'Agriculture & Nutrition', 'code': 'AGR', 'category': 'sciences', 'color': '#22c55e', 'order': 10},
    {'name': 'Physical Education & Sport', 'code': 'PE', 'category': 'pe', 'color': '#06b6d4', 'order': 11},
    {'name': 'Home Science', 'code': 'HS', 'category': 'technical', 'color': '#a855f7', 'order': 12},
    {'name': 'Pre-Technical Studies', 'code': 'PTS', 'category': 'technical', 'color': '#64748b', 'order': 13},
    {'name': 'Business Studies', 'code': 'BIZ', 'category': 'humanities', 'color': '#0ea5e9', 'order': 14},
    {'name': 'Life Skills', 'code': 'LS', 'category': 'other', 'color': '#84cc16', 'order': 15},
    {'name': 'Foreign Languages', 'code': 'FL', 'category': 'languages', 'color': '#d946ef', 'order': 16},
    {'name': 'Computer Science', 'code': 'CS', 'category': 'technical', 'color': '#475569', 'order': 17},

    # 8-4-4 specific
    {'name': 'Physics', 'code': 'PHY', 'category': 'sciences', 'color': '#2563eb', 'order': 18},
    {'name': 'Chemistry', 'code': 'CHE', 'category': 'sciences', 'color': '#059669', 'order': 19},
    {'name': 'Biology', 'code': 'BIO', 'category': 'sciences', 'color': '#16a34a', 'order': 20},
    {'name': 'History & Government', 'code': 'HIS', 'category': 'humanities', 'color': '#7c3aed', 'order': 21},
    {'name': 'Geography', 'code': 'GEO', 'category': 'humanities', 'color': '#0d9488', 'order': 22},
]

# ── CBC Subjects per Level ──
CBC_SUBJECTS = {
    'Pre-Primary': [
        # Activity areas
        {'name': 'Language Activities', 'code': 'CBC-PP-LA', 'area': 'Literacy & Indigenous Languages', 'type': 'compulsory', 'lessons': 5},
        {'name': 'Mathematical Activities', 'code': 'CBC-PP-MA', 'area': 'Mathematics', 'type': 'compulsory', 'lessons': 5},
        {'name': 'Environmental Activities', 'code': 'CBC-PP-EA', 'area': 'Integrated Science', 'type': 'compulsory', 'lessons': 5},
        {'name': 'Psychomotor & Creative Activities', 'code': 'CBC-PP-PCA', 'area': 'Creative Arts & Sports', 'type': 'compulsory', 'lessons': 5},
        {'name': 'Religious Education Activities', 'code': 'CBC-PP-RE', 'area': 'Religious Education', 'type': 'compulsory', 'lessons': 3},
    ],
    'Lower Primary': [
        {'name': 'Literacy', 'code': 'CBC-LP-LIT', 'area': 'Literacy & Indigenous Languages', 'type': 'compulsory', 'lessons': 5},
        {'name': 'English', 'code': 'CBC-LP-ENG', 'area': 'English Language', 'type': 'compulsory', 'lessons': 5},
        {'name': 'Kiswahili / KSL', 'code': 'CBC-LP-KSW', 'area': 'Kiswahili Language', 'type': 'compulsory', 'lessons': 5},
        {'name': 'Mathematics', 'code': 'CBC-LP-MAT', 'area': 'Mathematics', 'type': 'compulsory', 'lessons': 5},
        {'name': 'Environmental Activities', 'code': 'CBC-LP-ENV', 'area': 'Integrated Science', 'type': 'compulsory', 'lessons': 4},
        {'name': 'Hygiene & Nutrition', 'code': 'CBC-LP-HN', 'area': 'Health Education', 'type': 'compulsory', 'lessons': 3},
        {'name': 'Religious Education', 'code': 'CBC-LP-RE', 'area': 'Religious Education', 'type': 'compulsory', 'lessons': 3},
        {'name': 'Movement & Creative Activities', 'code': 'CBC-LP-MCA', 'area': 'Creative Arts & Sports', 'type': 'compulsory', 'lessons': 5},
    ],
    'Upper Primary': [
        {'name': 'English', 'code': 'CBC-UP-ENG', 'area': 'English Language', 'type': 'compulsory', 'lessons': 5},
        {'name': 'Kiswahili / KSL', 'code': 'CBC-UP-KSW', 'area': 'Kiswahili Language', 'type': 'compulsory', 'lessons': 5},
        {'name': 'Home Science', 'code': 'CBC-UP-HS', 'area': 'Home Science', 'type': 'compulsory', 'lessons': 3},
        {'name': 'Agriculture', 'code': 'CBC-UP-AGR', 'area': 'Agriculture & Nutrition', 'type': 'compulsory', 'lessons': 3},
        {'name': 'Science & Technology', 'code': 'CBC-UP-ST', 'area': 'Integrated Science', 'type': 'compulsory', 'lessons': 4},
        {'name': 'Mathematics', 'code': 'CBC-UP-MAT', 'area': 'Mathematics', 'type': 'compulsory', 'lessons': 5},
        {'name': 'Religious Education', 'code': 'CBC-UP-RE', 'area': 'Religious Education', 'type': 'compulsory', 'lessons': 3},
        {'name': 'Social Studies', 'code': 'CBC-UP-SS', 'area': 'Social Studies', 'type': 'compulsory', 'lessons': 3},
        {'name': 'Creative Arts', 'code': 'CBC-UP-CA', 'area': 'Creative Arts & Sports', 'type': 'compulsory', 'lessons': 4},
        {'name': 'Physical & Health Education', 'code': 'CBC-UP-PHE', 'area': 'Physical Education & Sport', 'type': 'compulsory', 'lessons': 3},
    ],
    'Junior Secondary': [
        {'name': 'English', 'code': 'CBC-JS-ENG', 'area': 'English Language', 'type': 'compulsory', 'lessons': 5},
        {'name': 'Kiswahili / KSL', 'code': 'CBC-JS-KSW', 'area': 'Kiswahili Language', 'type': 'compulsory', 'lessons': 5},
        {'name': 'Mathematics', 'code': 'CBC-JS-MAT', 'area': 'Mathematics', 'type': 'compulsory', 'lessons': 5},
        {'name': 'Integrated Science', 'code': 'CBC-JS-SCI', 'area': 'Integrated Science', 'type': 'compulsory', 'lessons': 5},
        {'name': 'Health Education', 'code': 'CBC-JS-HE', 'area': 'Health Education', 'type': 'compulsory', 'lessons': 2},
        {'name': 'Pre-Technical Studies', 'code': 'CBC-JS-PTS', 'area': 'Pre-Technical Studies', 'type': 'compulsory', 'lessons': 3},
        {'name': 'Social Studies', 'code': 'CBC-JS-SS', 'area': 'Social Studies', 'type': 'compulsory', 'lessons': 4},
        {'name': 'Religious Education', 'code': 'CBC-JS-RE', 'area': 'Religious Education', 'type': 'compulsory', 'lessons': 3},
        {'name': 'Business Studies', 'code': 'CBC-JS-BIZ', 'area': 'Business Studies', 'type': 'compulsory', 'lessons': 3},
        {'name': 'Agriculture', 'code': 'CBC-JS-AGR', 'area': 'Agriculture & Nutrition', 'type': 'compulsory', 'lessons': 3},
        {'name': 'Life Skills', 'code': 'CBC-JS-LS', 'area': 'Life Skills', 'type': 'compulsory', 'lessons': 1},
        {'name': 'Physical Education & Sport', 'code': 'CBC-JS-PE', 'area': 'Physical Education & Sport', 'type': 'compulsory', 'lessons': 2},
        {'name': 'Foreign Language', 'code': 'CBC-JS-FL', 'area': 'Foreign Languages', 'type': 'optional', 'lessons': 3},
        {'name': 'Computer Science', 'code': 'CBC-JS-CS', 'area': 'Computer Science', 'type': 'optional', 'lessons': 3},
        {'name': 'Visual Arts', 'code': 'CBC-JS-VA', 'area': 'Creative Arts & Sports', 'type': 'optional', 'lessons': 3},
        {'name': 'Performing Arts', 'code': 'CBC-JS-PA', 'area': 'Creative Arts & Sports', 'type': 'optional', 'lessons': 3},
        {'name': 'Home Science', 'code': 'CBC-JS-HS', 'area': 'Home Science', 'type': 'optional', 'lessons': 3},
    ],
    'Senior Secondary': [
        # Core / compulsory
        {'name': 'English', 'code': 'CBC-SS-ENG', 'area': 'English Language', 'type': 'compulsory', 'lessons': 5},
        {'name': 'Kiswahili / KSL', 'code': 'CBC-SS-KSW', 'area': 'Kiswahili Language', 'type': 'compulsory', 'lessons': 5},
        {'name': 'Mathematics', 'code': 'CBC-SS-MAT', 'area': 'Mathematics', 'type': 'compulsory', 'lessons': 5},
        # Elective / pathway subjects
        {'name': 'Biology', 'code': 'CBC-SS-BIO', 'area': 'Integrated Science', 'type': 'elective', 'lessons': 4},
        {'name': 'Physics', 'code': 'CBC-SS-PHY', 'area': 'Integrated Science', 'type': 'elective', 'lessons': 4},
        {'name': 'Chemistry', 'code': 'CBC-SS-CHE', 'area': 'Integrated Science', 'type': 'elective', 'lessons': 4},
        {'name': 'History', 'code': 'CBC-SS-HIS', 'area': 'Social Studies', 'type': 'elective', 'lessons': 4},
        {'name': 'Geography', 'code': 'CBC-SS-GEO', 'area': 'Social Studies', 'type': 'elective', 'lessons': 4},
        {'name': 'Business Studies', 'code': 'CBC-SS-BIZ', 'area': 'Business Studies', 'type': 'elective', 'lessons': 4},
        {'name': 'Computer Science', 'code': 'CBC-SS-CS', 'area': 'Computer Science', 'type': 'elective', 'lessons': 4},
        {'name': 'Agriculture', 'code': 'CBC-SS-AGR', 'area': 'Agriculture & Nutrition', 'type': 'elective', 'lessons': 4},
        {'name': 'Home Science', 'code': 'CBC-SS-HS', 'area': 'Home Science', 'type': 'elective', 'lessons': 4},
        {'name': 'Visual Arts', 'code': 'CBC-SS-VA', 'area': 'Creative Arts & Sports', 'type': 'elective', 'lessons': 4},
        {'name': 'Foreign Language', 'code': 'CBC-SS-FL', 'area': 'Foreign Languages', 'type': 'elective', 'lessons': 4},
        {'name': 'Religious Education', 'code': 'CBC-SS-RE', 'area': 'Religious Education', 'type': 'elective', 'lessons': 3},
    ],
}

# ── 8-4-4 Subjects per Level ──
EIGHT_FOUR_FOUR_SUBJECTS = {
    'Primary': [
        {'name': 'English', 'code': '844-P-ENG', 'area': 'English Language', 'type': 'compulsory', 'lessons': 7},
        {'name': 'Kiswahili', 'code': '844-P-KSW', 'area': 'Kiswahili Language', 'type': 'compulsory', 'lessons': 5},
        {'name': 'Mathematics', 'code': '844-P-MAT', 'area': 'Mathematics', 'type': 'compulsory', 'lessons': 7},
        {'name': 'Science', 'code': '844-P-SCI', 'area': 'Integrated Science', 'type': 'compulsory', 'lessons': 5},
        {'name': 'Social Studies', 'code': '844-P-SS', 'area': 'Social Studies', 'type': 'compulsory', 'lessons': 4},
        {'name': 'Religious Education', 'code': '844-P-RE', 'area': 'Religious Education', 'type': 'compulsory', 'lessons': 3},
        {'name': 'Creative Arts', 'code': '844-P-CA', 'area': 'Creative Arts & Sports', 'type': 'compulsory', 'lessons': 3},
        {'name': 'Physical Education', 'code': '844-P-PE', 'area': 'Physical Education & Sport', 'type': 'compulsory', 'lessons': 2},
        {'name': 'Home Science', 'code': '844-P-HS', 'area': 'Home Science', 'type': 'compulsory', 'lessons': 2},
    ],
    'Secondary': [
        # Compulsory
        {'name': 'English', 'code': '844-S-ENG', 'area': 'English Language', 'type': 'compulsory', 'lessons': 6},
        {'name': 'Kiswahili', 'code': '844-S-KSW', 'area': 'Kiswahili Language', 'type': 'compulsory', 'lessons': 5},
        {'name': 'Mathematics', 'code': '844-S-MAT', 'area': 'Mathematics', 'type': 'compulsory', 'lessons': 6},
        # Sciences
        {'name': 'Physics', 'code': '844-S-PHY', 'area': 'Physics', 'type': 'compulsory', 'lessons': 4},
        {'name': 'Chemistry', 'code': '844-S-CHE', 'area': 'Chemistry', 'type': 'compulsory', 'lessons': 4},
        {'name': 'Biology', 'code': '844-S-BIO', 'area': 'Biology', 'type': 'compulsory', 'lessons': 4},
        # Humanities
        {'name': 'History & Government', 'code': '844-S-HIS', 'area': 'History & Government', 'type': 'elective', 'lessons': 4},
        {'name': 'Geography', 'code': '844-S-GEO', 'area': 'Geography', 'type': 'elective', 'lessons': 4},
        {'name': 'Religious Education', 'code': '844-S-RE', 'area': 'Religious Education', 'type': 'elective', 'lessons': 3},
        # Technical / applied
        {'name': 'Business Studies', 'code': '844-S-BIZ', 'area': 'Business Studies', 'type': 'elective', 'lessons': 4},
        {'name': 'Agriculture', 'code': '844-S-AGR', 'area': 'Agriculture & Nutrition', 'type': 'elective', 'lessons': 3},
        {'name': 'Computer Studies', 'code': '844-S-CS', 'area': 'Computer Science', 'type': 'elective', 'lessons': 3},
        {'name': 'Home Science', 'code': '844-S-HS', 'area': 'Home Science', 'type': 'elective', 'lessons': 3},
        {'name': 'French', 'code': '844-S-FRE', 'area': 'Foreign Languages', 'type': 'elective', 'lessons': 3},
    ],
}


class Command(BaseCommand):
    help = 'Seed Kenyan curriculum: CBC & 8-4-4 with levels, grades, learning areas, and subjects.'

    def handle(self, *args, **options):
        self._seed_learning_areas()
        cbc = self._seed_curriculum(CURRICULA[0], CBC_LEVELS, CBC_GRADES, CBC_SUBJECTS)
        e44 = self._seed_curriculum(CURRICULA[1], EIGHT_FOUR_FOUR_LEVELS, EIGHT_FOUR_FOUR_GRADES, EIGHT_FOUR_FOUR_SUBJECTS)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('✔ Kenyan curriculum seeded successfully.'))

    # ── helpers ──

    def _seed_learning_areas(self):
        self.stdout.write('\n── Learning Areas ──')
        for la in LEARNING_AREAS:
            obj, created = LearningArea.objects.get_or_create(
                name=la['name'],
                defaults={
                    'code': la['code'],
                    'category': la['category'],
                    'color_hex': la['color'],
                    'order': la['order'],
                    'is_active': True,
                },
            )
            tag = '+' if created else '='
            self.stdout.write(f'  {tag} {obj.name}')

    def _seed_curriculum(self, cur_data, levels_data, grades_data, subjects_data):
        self.stdout.write(f'\n── Curriculum: {cur_data["name"]} ──')

        curriculum, created = Curriculum.objects.get_or_create(
            code=cur_data['code'],
            defaults={
                'name': cur_data['name'],
                'description': cur_data['description'],
                'status': cur_data['status'],
                'is_active': True,
            },
        )
        self.stdout.write(f'  {"+" if created else "="} Curriculum {curriculum.name}')

        # Levels
        level_map = {}
        for lv in levels_data:
            obj, created = CurriculumLevel.objects.get_or_create(
                curriculum=curriculum,
                name=lv['name'],
                defaults={
                    'order': lv['order'],
                    'min_years': lv.get('min_years'),
                    'max_years': lv.get('max_years'),
                },
            )
            level_map[lv['name']] = obj
            self.stdout.write(f'    {"+" if created else "="} Level: {obj.name}')

        # Grades
        for gr in grades_data:
            level_obj = level_map.get(gr['level'])
            obj, created = GradeStructure.objects.get_or_create(
                curriculum=curriculum,
                code=gr['code'],
                defaults={
                    'curriculum_level': level_obj,
                    'name': gr['name'],
                    'level_order': gr['order'],
                    'age_range': gr.get('age'),
                    'is_active': True,
                },
            )
            self.stdout.write(f'      {"+" if created else "="} Grade: {obj.name}')

        # Subjects
        area_cache = {la.name: la for la in LearningArea.objects.all()}
        for level_name, subs in subjects_data.items():
            level_obj = level_map.get(level_name)
            for sub in subs:
                area_obj = area_cache.get(sub['area'])
                obj, created = Subject.objects.get_or_create(
                    code=sub['code'],
                    defaults={
                        'name': sub['name'],
                        'curriculum': curriculum,
                        'curriculum_level': level_obj,
                        'learning_area': area_obj,
                        'subject_type': sub['type'],
                        'weekly_lessons': sub['lessons'],
                        'is_active': True,
                    },
                )
                self.stdout.write(f'        {"+" if created else "="} Subject: {obj.name} ({sub["code"]})')

        return curriculum
