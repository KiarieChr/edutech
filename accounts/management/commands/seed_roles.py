"""
Seed default user roles (Django Groups) with appropriate permissions.

Usage:
    python manage.py seed_roles

Roles created:
    - Teacher           (academics, results, attendance, lesson management)
    - Lecturer          (same as Teacher — alias for tertiary context)
    - Parent            (read-only: student info, fees, results)
    - Finance Manager   (finance, fees, payments, invoicing, budgets, journals, payables)
    - Bursar            (fees, payments, receipts)
    - HR Manager        (workforce, recruitment)
    - Registrar         (student_management, student_settings, accounts)
    - Department Head   (academics + teacher + department management)
    - Librarian         (read-only across most modules)
    - ICT Admin         (core system, auth, accounts, sessions)
    - Procurement Officer (procurement-related — falls under finance for now)
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType


# ── Role → permission mapping ────────────────────────────────────
# Keys: role name
# Values: dict with:
#   'modules'  — list of app_labels to include ALL permissions from
#   'extras'   — list of (app_label, codename) for cherry-picked permissions
#   'exclude'  — list of codenames to exclude
ROLE_DEFINITIONS = {
    'Teacher': {
        'modules': ['academics', 'result', 'lesson_sessions', 'scheduled_lessons', 'quiz', 'course'],
        'extras': [
            ('student_settings', 'view_enrollment'),
            ('accounts', 'view_student'),
            ('student_management', 'view_application'),
            ('timetable', 'view_timetableslot'),
            ('timetable', 'view_timetableversion'),
            ('timetable', 'view_subject'),
            ('timetable', 'view_room'),
            ('timetable', 'view_timeperiod'),
        ],
        'exclude': [],
    },
    'Lecturer': {
        # Same as Teacher — used in tertiary/university context
        'modules': ['academics', 'result', 'lesson_sessions', 'scheduled_lessons', 'quiz', 'course'],
        'extras': [
            ('student_settings', 'view_enrollment'),
            ('accounts', 'view_student'),
            ('student_management', 'view_application'),
            ('timetable', 'view_timetableslot'),
            ('timetable', 'view_timetableversion'),
            ('timetable', 'view_subject'),
            ('timetable', 'view_room'),
            ('timetable', 'view_timeperiod'),
        ],
        'exclude': [],
    },
    'Parent': {
        'modules': [],
        'extras': [
            ('accounts', 'view_student'),
            ('accounts', 'view_parent'),
            ('result', 'view_result'),
            ('fees', 'view_feestructure'),
            ('fees', 'view_feeitem'),
            ('fees', 'view_feetemplate'),
            ('fees', 'view_votehead'),
            ('payments', 'view_invoice'),
            ('invoicing', 'view_invoice'),
            ('student_settings', 'view_enrollment'),
        ],
        'exclude': [],
    },
    'Finance Manager': {
        'modules': ['finance', 'fees', 'payments', 'invoicing', 'budgets', 'journals', 'payables'],
        'extras': [
            ('accounts', 'view_student'),
            ('student_settings', 'view_enrollment'),
            ('workforce', 'view_employee'),
        ],
        'exclude': [],
    },
    'Bursar': {
        'modules': ['fees', 'payments', 'invoicing'],
        'extras': [
            ('accounts', 'view_student'),
            ('student_settings', 'view_enrollment'),
            ('finance', 'view_account'),
            ('finance', 'view_fiscalperiod'),
            ('finance', 'view_receipt'),
            ('finance', 'view_receiptallocation'),
            ('finance', 'view_paymentmethod'),
        ],
        'exclude': [],
    },
    'HR Manager': {
        'modules': ['workforce', 'recruitment'],
        'extras': [
            ('accounts', 'view_user'),
            ('accounts', 'change_user'),
        ],
        'exclude': [],
    },
    'Registrar': {
        'modules': ['student_management', 'student_settings'],
        'extras': [
            ('accounts', 'view_student'),
            ('accounts', 'add_student'),
            ('accounts', 'change_student'),
            ('accounts', 'view_user'),
            ('accounts', 'add_user'),
            ('accounts', 'change_user'),
            ('academics', 'view_classsession'),
            ('academics', 'view_studentsessionenrollment'),
        ],
        'exclude': [],
    },
    'Department Head': {
        'modules': ['academics', 'result', 'lesson_sessions', 'scheduled_lessons', 'quiz', 'course'],
        'extras': [
            ('student_settings', 'view_enrollment'),
            ('accounts', 'view_student'),
            ('student_management', 'view_application'),
            ('workforce', 'view_employee'),
            ('workforce', 'view_department'),
            ('workforce', 'change_department'),
            ('timetable', 'view_timetableslot'),
            ('timetable', 'view_timetableversion'),
            ('timetable', 'change_timetableslot'),
            ('timetable', 'change_timetableversion'),
        ],
        'exclude': [],
    },
    'Librarian': {
        'modules': [],
        'extras': [
            ('accounts', 'view_student'),
            ('accounts', 'view_user'),
            ('student_settings', 'view_enrollment'),
            ('academics', 'view_classsession'),
            ('academics', 'view_studentsessionenrollment'),
            ('course', 'view_course'),
        ],
        'exclude': [],
    },
    'ICT Admin': {
        'modules': ['core', 'auth', 'accounts', 'sessions', 'authtoken', 'contenttypes'],
        'extras': [],
        'exclude': [],
    },
    'Procurement Officer': {
        'modules': ['budgets'],
        'extras': [
            ('finance', 'view_account'),
            ('finance', 'view_fiscalperiod'),
            ('payables', 'view_bill'),
            ('payables', 'add_bill'),
            ('payables', 'change_bill'),
            ('payables', 'view_supplier'),
            ('payables', 'view_vendor'),
            ('invoicing', 'view_invoice'),
        ],
        'exclude': [],
    },
}


class Command(BaseCommand):
    help = 'Seed default user roles with appropriate permissions.'

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0

        # Cache content types for lookup
        ct_map = {}
        for ct in ContentType.objects.all():
            ct_map[ct.app_label] = ct_map.get(ct.app_label, [])
            ct_map[ct.app_label].append(ct.id)

        for role_name, definition in ROLE_DEFINITIONS.items():
            group, created = Group.objects.get_or_create(name=role_name)

            # Collect permissions
            perm_ids = set()

            # 1. All permissions from listed modules
            for app_label in definition.get('modules', []):
                ct_ids = ct_map.get(app_label, [])
                if ct_ids:
                    module_perms = Permission.objects.filter(
                        content_type_id__in=ct_ids
                    ).values_list('id', flat=True)
                    perm_ids.update(module_perms)

            # 2. Cherry-picked extras
            for app_label, codename in definition.get('extras', []):
                try:
                    perm = Permission.objects.get(
                        content_type__app_label=app_label,
                        codename=codename,
                    )
                    perm_ids.add(perm.id)
                except Permission.DoesNotExist:
                    self.stdout.write(self.style.WARNING(
                        f'  ⚠ Permission not found: {app_label}.{codename}'
                    ))

            # 3. Exclude
            for codename in definition.get('exclude', []):
                try:
                    perm = Permission.objects.get(codename=codename)
                    perm_ids.discard(perm.id)
                except Permission.DoesNotExist:
                    pass

            # Assign
            group.permissions.set(perm_ids)

            status_label = 'CREATED' if created else 'UPDATED'
            icon = '✅' if created else '🔄'
            if created:
                created_count += 1
            else:
                updated_count += 1

            self.stdout.write(
                f'  {icon} {status_label}: {role_name} — {len(perm_ids)} permissions'
            )

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Done! {created_count} created, {updated_count} updated. '
            f'Total: {len(ROLE_DEFINITIONS)} roles.'
        ))
