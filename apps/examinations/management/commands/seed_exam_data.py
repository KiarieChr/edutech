from django.core.management.base import BaseCommand
from examinations.models import GradingScale, GradingLevel, AssessmentType
from student_settings.models import Curriculum, CurriculumLevel


class Command(BaseCommand):
    help = 'Seed grading scales and assessment types for all curricula'

    def handle(self, *args, **options):
        self._seed_grading_scales()
        self._seed_assessment_types()
        self.stdout.write(self.style.SUCCESS('Seeding complete.'))

    def _seed_grading_scales(self):
        # --- CBC Rubric Grading ---
        cbc = Curriculum.objects.filter(code='CBC').first()
        if not cbc:
            self.stdout.write(self.style.WARNING('CBC curriculum not found, skipping CBC grading'))
        else:
            scale, created = GradingScale.objects.get_or_create(
                code='CBC-RUBRIC',
                defaults={
                    'name': 'CBC Rubric Scale',
                    'curriculum': cbc,
                    'scale_type': 'rubric',
                    'max_mark': 100,
                    'pass_mark': 41, # Usually ME2 is passing
                    'description': 'Competency-Based Curriculum rubric grading (EE, ME, AE, BE - 8 Levels)',
                }
            )
            
            # Always update levels to ensure we have the latest 8-level rubric
            GradingLevel.objects.filter(scale=scale).delete()
            
            levels = [
                ('EE1', 'Exceeding Expectations 1', 90, 100, 8, 1, '#15803d'),
                ('EE2', 'Exceeding Expectations 2', 75, 89, 7, 2, '#22c55e'),
                ('ME1', 'Meeting Expectations 1', 58, 74, 6, 3, '#1d4ed8'),
                ('ME2', 'Meeting Expectations 2', 41, 57, 5, 4, '#3b82f6'),
                ('AE1', 'Approaching Expectations 1', 31, 40, 4, 5, '#ea580c'),
                ('AE2', 'Approaching Expectations 2', 21, 30, 3, 6, '#f59e0b'),
                ('BE1', 'Below Expectations 1', 11, 20, 2, 7, '#b91c1c'),
                ('BE2', 'Below Expectations 2', 0, 10, 1, 8, '#ef4444'),
            ]
            for grade, label, min_m, max_m, pts, order, color in levels:
                GradingLevel.objects.create(
                    scale=scale, grade=grade, label=label,
                    min_mark=min_m, max_mark=max_m, points=pts,
                    order=order, color_hex=color,
                )
            
            if created:
                self.stdout.write(f'  Created CBC Rubric scale with {len(levels)} levels')
            else:
                self.stdout.write(f'  Updated CBC Rubric scale with {len(levels)} levels')

        # --- 8-4-4 Points Grading ---
        k844 = Curriculum.objects.filter(code='844').first()
        if not k844:
            self.stdout.write(self.style.WARNING('8-4-4 curriculum not found, skipping'))
        else:
            scale, created = GradingScale.objects.get_or_create(
                code='844-POINTS',
                defaults={
                    'name': '8-4-4 Points Scale',
                    'curriculum': k844,
                    'scale_type': 'points',
                    'max_mark': 100,
                    'pass_mark': 30,
                    'description': 'Kenya 8-4-4 system grading (A to E with 12 point scale)',
                }
            )
            if created:
                levels = [
                    ('A',  'Excellent',       80, 100, 12, 1,  '#15803d'),
                    ('A-', 'Very Good',        75, 79,  11, 2,  '#22c55e'),
                    ('B+', 'Good',             70, 74,  10, 3,  '#4ade80'),
                    ('B',  'Fairly Good',      65, 69,   9, 4,  '#3b82f6'),
                    ('B-', 'Above Average',    60, 64,   8, 5,  '#60a5fa'),
                    ('C+', 'Average',          55, 59,   7, 6,  '#93c5fd'),
                    ('C',  'Below Average',    50, 54,   6, 7,  '#f59e0b'),
                    ('C-', 'Fair',             45, 49,   5, 8,  '#fbbf24'),
                    ('D+', 'Below Fair',       40, 44,   4, 9,  '#f97316'),
                    ('D',  'Weak',             35, 39,   3, 10, '#fb923c'),
                    ('D-', 'Very Weak',        30, 34,   2, 11, '#ef4444'),
                    ('E',  'Fail',              0, 29,   1, 12, '#dc2626'),
                ]
                for grade, label, min_m, max_m, pts, order, color in levels:
                    GradingLevel.objects.create(
                        scale=scale, grade=grade, label=label,
                        min_mark=min_m, max_mark=max_m, points=pts,
                        order=order, color_hex=color,
                    )
                self.stdout.write(f'  Created 8-4-4 Points scale with {len(levels)} levels')
            else:
                self.stdout.write('  8-4-4 Points scale already exists')

        # --- K-CBC (same as CBC rubric but separate scale) ---
        kcbc = Curriculum.objects.filter(code='K-CBC').first()
        if kcbc:
            scale, created = GradingScale.objects.get_or_create(
                code='KCBC-RUBRIC',
                defaults={
                    'name': 'K-CBC Rubric Scale',
                    'curriculum': kcbc,
                    'scale_type': 'rubric',
                    'max_mark': 100,
                    'pass_mark': 41,
                    'description': 'Kenya CBC rubric grading (8 Levels)',
                }
            )
            
            GradingLevel.objects.filter(scale=scale).delete()
            
            levels = [
                ('EE1', 'Exceeding Expectations 1', 90, 100, 8, 1, '#15803d'),
                ('EE2', 'Exceeding Expectations 2', 75, 89, 7, 2, '#22c55e'),
                ('ME1', 'Meeting Expectations 1', 58, 74, 6, 3, '#1d4ed8'),
                ('ME2', 'Meeting Expectations 2', 41, 57, 5, 4, '#3b82f6'),
                ('AE1', 'Approaching Expectations 1', 31, 40, 4, 5, '#ea580c'),
                ('AE2', 'Approaching Expectations 2', 21, 30, 3, 6, '#f59e0b'),
                ('BE1', 'Below Expectations 1', 11, 20, 2, 7, '#b91c1c'),
                ('BE2', 'Below Expectations 2', 0, 10, 1, 8, '#ef4444'),
            ]
            for grade, label, min_m, max_m, pts, order, color in levels:
                GradingLevel.objects.create(
                    scale=scale, grade=grade, label=label,
                    min_mark=min_m, max_mark=max_m, points=pts,
                    order=order, color_hex=color,
                )
            
            if created:
                self.stdout.write(f'  Created K-CBC Rubric scale with {len(levels)} levels')
            else:
                self.stdout.write(f'  Updated K-CBC Rubric scale with {len(levels)} levels')

    def _seed_assessment_types(self):
        # --- CBC Assessment Types ---
        cbc = Curriculum.objects.filter(code='CBC').first()
        if cbc:
            types = [
                ('Opener', 'OPENER', 'formative', 10, 100, 1),
                ('Mid-Term', 'MID-TERM', 'formative', 20, 100, 2),
                ('End-Term', 'END-TERM', 'summative', 50, 100, 3),
                ('Project', 'PROJECT', 'formative', 20, 100, 4),
            ]
            for name, code, cat, weight, max_m, order in types:
                _, created = AssessmentType.objects.get_or_create(
                    curriculum=cbc, code=code,
                    defaults={
                        'name': name, 'category': cat,
                        'weight': weight, 'max_mark': max_m, 'order': order,
                    }
                )
                if created:
                    self.stdout.write(f'  Created CBC assessment: {name}')

        # --- K-CBC (same pattern) ---
        kcbc = Curriculum.objects.filter(code='K-CBC').first()
        if kcbc:
            types = [
                ('Opener', 'OPENER', 'formative', 10, 100, 1),
                ('Mid-Term', 'MID-TERM', 'formative', 20, 100, 2),
                ('End-Term', 'END-TERM', 'summative', 50, 100, 3),
                ('Project', 'PROJECT', 'formative', 20, 100, 4),
            ]
            for name, code, cat, weight, max_m, order in types:
                _, created = AssessmentType.objects.get_or_create(
                    curriculum=kcbc, code=code,
                    defaults={
                        'name': name, 'category': cat,
                        'weight': weight, 'max_mark': max_m, 'order': order,
                    }
                )
                if created:
                    self.stdout.write(f'  Created K-CBC assessment: {name}')

        # --- 8-4-4 Assessment Types ---
        k844 = Curriculum.objects.filter(code='844').first()
        if k844:
            types = [
                ('CAT 1', 'CAT1', 'formative', 10, 100, 1),
                ('CAT 2', 'CAT2', 'formative', 10, 100, 2),
                ('Mid-Term', 'MID-TERM', 'formative', 20, 100, 3),
                ('End-Term', 'END-TERM', 'summative', 60, 100, 4),
            ]
            for name, code, cat, weight, max_m, order in types:
                _, created = AssessmentType.objects.get_or_create(
                    curriculum=k844, code=code,
                    defaults={
                        'name': name, 'category': cat,
                        'weight': weight, 'max_mark': max_m, 'order': order,
                    }
                )
                if created:
                    self.stdout.write(f'  Created 8-4-4 assessment: {name}')
