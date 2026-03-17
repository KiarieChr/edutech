"""
timetable_report.py — Management command for timetable analytics reports.

Generates various reports on timetable status, coverage, and workloads.

Usage:
------
    # Dashboard summary
    python manage.py timetable_report --dashboard
    
    # Teacher workloads
    python manage.py timetable_report --workloads
    
    # Class coverage
    python manage.py timetable_report --coverage
    
    # Room utilization
    python manage.py timetable_report --rooms
    
    # Conflict audit
    python manage.py timetable_report --conflicts
    
    # All reports
    python manage.py timetable_report --all
    
    # Export to JSON
    python manage.py timetable_report --all --json > report.json
"""
import json
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Generate timetable analytics reports'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dashboard',
            action='store_true',
            help='Show dashboard summary'
        )
        parser.add_argument(
            '--workloads',
            action='store_true',
            help='Show teacher workload report'
        )
        parser.add_argument(
            '--coverage',
            action='store_true',
            help='Show class coverage report'
        )
        parser.add_argument(
            '--rooms',
            action='store_true',
            help='Show room utilization report'
        )
        parser.add_argument(
            '--conflicts',
            action='store_true',
            help='Show conflict audit report'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Generate all reports'
        )
        parser.add_argument(
            '--json',
            action='store_true',
            help='Output in JSON format'
        )

    def handle(self, *args, **options):
        from timetable.services.analytics import TimetableAnalytics

        analytics = TimetableAnalytics()
        reports = {}

        if options['all'] or options['dashboard']:
            reports['dashboard'] = analytics.get_dashboard_summary()

        if options['all'] or options['workloads']:
            reports['workloads'] = analytics.get_teacher_workloads()

        if options['all'] or options['coverage']:
            reports['coverage'] = analytics.get_all_classes_coverage()

        if options['all'] or options['rooms']:
            reports['rooms'] = analytics.get_room_utilization()

        if options['all'] or options['conflicts']:
            reports['conflicts'] = analytics.get_conflict_summary()

        if not any([options['dashboard'], options['workloads'], options['coverage'],
                    options['rooms'], options['conflicts'], options['all']]):
            self.stdout.write(self.style.WARNING(
                "No report type specified. Use --help for options."
            ))
            return

        if options['json']:
            self.stdout.write(json.dumps(reports, indent=2, default=str))
        else:
            self._print_reports(reports)

    def _print_reports(self, reports):
        if 'dashboard' in reports:
            self._print_dashboard(reports['dashboard'])

        if 'workloads' in reports:
            self._print_workloads(reports['workloads'])

        if 'coverage' in reports:
            self._print_coverage(reports['coverage'])

        if 'rooms' in reports:
            self._print_rooms(reports['rooms'])

        if 'conflicts' in reports:
            self._print_conflicts(reports['conflicts'])

    def _print_dashboard(self, data):
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.HTTP_INFO("DASHBOARD SUMMARY"))
        self.stdout.write("=" * 60)

        overview = data.get('overview', {})
        self.stdout.write(f"Total Scheduled Slots: {overview.get('total_scheduled_slots', 0)}")
        self.stdout.write(f"Active Classes: {overview.get('active_classes', 0)}")
        self.stdout.write(f"Active Rooms: {overview.get('active_rooms', 0)}")
        self.stdout.write(f"Active Teachers: {overview.get('active_teachers', 0)}")

        alloc = data.get('allocations', {})
        self.stdout.write(f"\nAllocations: {alloc.get('complete', 0)}/{alloc.get('total', 0)} complete")
        self.stdout.write(f"Completion Rate: {alloc.get('completion_rate', 0):.1f}%")

        health = data.get('system_health', {})
        if health.get('status') == 'clean':
            self.stdout.write(self.style.SUCCESS("\nSystem Health: CLEAN (no conflicts)"))
        else:
            self.stdout.write(self.style.ERROR(
                f"\nSystem Health: {health.get('conflicts', 0)} conflicts detected!"
            ))

    def _print_workloads(self, data):
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.HTTP_INFO("TEACHER WORKLOADS"))
        self.stdout.write("=" * 60)

        self.stdout.write(f"Total Teachers: {data.get('total_teachers', 0)}")
        self.stdout.write(f"Average Weekly Lessons: {data.get('average_weekly_lessons', 0)}")
        self.stdout.write(f"Range: {data.get('min_weekly_lessons', 0)} - {data.get('max_weekly_lessons', 0)}")

        self.stdout.write("\nTop 10 by Workload:")
        for i, teacher in enumerate(data.get('teachers', [])[:10], 1):
            level = teacher.get('workload_level', 'unknown')
            style = self.style.SUCCESS if level == 'normal' else (
                self.style.WARNING if level == 'heavy' else (
                    self.style.ERROR if level == 'overloaded' else self.style.HTTP_NOT_MODIFIED
                )
            )
            self.stdout.write(style(
                f"  {i}. {teacher['name']}: {teacher['total_lessons']} lessons "
                f"({teacher['unique_classes']} classes, {teacher['unique_subjects']} subjects) "
                f"- {level}"
            ))

    def _print_coverage(self, data):
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.HTTP_INFO("CLASS COVERAGE"))
        self.stdout.write("=" * 60)

        self.stdout.write(f"Fully Scheduled: {data.get('fully_scheduled', 0)}")
        self.stdout.write(f"Partially Scheduled: {data.get('partially_scheduled', 0)}")
        self.stdout.write(f"Not Scheduled: {data.get('not_scheduled', 0)}")

        # Show classes needing attention (below 100%)
        self.stdout.write("\nClasses Needing Attention:")
        for cls in data.get('classes', []):
            if cls['coverage_percentage'] < 100:
                style = self.style.WARNING if cls['coverage_percentage'] > 50 else self.style.ERROR
                self.stdout.write(style(
                    f"  {cls['class_name']}: {cls['coverage_percentage']:.1f}% "
                    f"({cls['complete']}/{cls['total']} subjects)"
                ))

    def _print_rooms(self, data):
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.HTTP_INFO("ROOM UTILIZATION"))
        self.stdout.write("=" * 60)

        self.stdout.write(f"Total Rooms: {data.get('total_rooms', 0)}")
        self.stdout.write(f"Average Utilization: {data.get('average_utilization', 0):.1f}%")
        self.stdout.write(f"Underutilized (<30%): {data.get('underutilized', 0)}")
        self.stdout.write(f"Optimal (30-80%): {data.get('optimal', 0)}")
        self.stdout.write(f"High Usage (>80%): {data.get('overutilized', 0)}")

        self.stdout.write("\nRoom Details:")
        for room in data.get('rooms', []):
            level = room.get('utilization_level', 'unknown')
            style = self.style.SUCCESS if level == 'optimal' else (
                self.style.WARNING if level in ['high', 'low'] else self.style.HTTP_NOT_MODIFIED
            )
            self.stdout.write(style(
                f"  {room['name']}: {room['utilization_percentage']:.1f}% "
                f"({room['scheduled_slots']}/{room['available_slots']} slots)"
            ))

    def _print_conflicts(self, data):
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.HTTP_INFO("CONFLICT AUDIT"))
        self.stdout.write("=" * 60)

        total = data.get('total_conflicts', 0)
        if total == 0:
            self.stdout.write(self.style.SUCCESS("No conflicts detected. System is clean."))
        else:
            self.stdout.write(self.style.ERROR(f"TOTAL CONFLICTS: {total}"))
            self.stdout.write(f"  Teacher Double-Bookings: {data.get('teacher_conflicts', 0)}")
            self.stdout.write(f"  Room Double-Bookings: {data.get('room_conflicts', 0)}")
            self.stdout.write(f"  Class Double-Bookings: {data.get('class_conflicts', 0)}")

            self.stdout.write("\nConflict Details:")
            for conflict in data.get('conflicts', []):
                self.stdout.write(self.style.ERROR(
                    f"  {conflict['type']}: {conflict['day']} {conflict['time']} "
                    f"({conflict['count']} entries)"
                ))
