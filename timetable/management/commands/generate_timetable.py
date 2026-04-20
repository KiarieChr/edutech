"""
generate_timetable.py — Management command for semi-automatic timetable generation.

This command provides a CLI interface to the SchedulingService for:
1. Generating timetables for specific classes
2. Bulk generation for all classes
3. Filling gaps in existing timetables
4. Preview mode (suggestions only)

Usage:
------
    # Generate for a specific class (semi-auto mode)
    python manage.py generate_timetable --class-id=5
    
    # Generate for all classes
    python manage.py generate_timetable --all
    
    # Preview only (don't create slots)
    python manage.py generate_timetable --class-id=5 --preview
    
    # Fill gaps in existing timetable
    python manage.py generate_timetable --class-id=5 --fill-gaps
    
    # With preferences
    python manage.py generate_timetable --class-id=5 --prefer-afternoon --no-spread
"""
import sys
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = 'Generate timetables using the semi-automatic scheduling algorithm'

    def add_arguments(self, parser):
        # Target selection
        target_group = parser.add_mutually_exclusive_group(required=True)
        target_group.add_argument(
            '--class-id',
            type=int,
            help='ID of the class session to generate timetable for'
        )
        target_group.add_argument(
            '--all',
            action='store_true',
            help='Generate timetables for all active classes'
        )

        # Mode options
        parser.add_argument(
            '--preview',
            action='store_true',
            help='Preview mode: show suggestions without creating slots'
        )
        parser.add_argument(
            '--fill-gaps',
            action='store_true',
            help='Only fill unscheduled allocations, preserve existing slots'
        )

        # Preferences
        parser.add_argument(
            '--prefer-afternoon',
            action='store_true',
            help='Prefer afternoon slots (default: morning)'
        )
        parser.add_argument(
            '--no-spread',
            action='store_true',
            help='Disable subject spreading (allow multiple same-subject per day)'
        )
        parser.add_argument(
            '--max-same-subject',
            type=int,
            default=1,
            help='Maximum same subject lessons per day (default: 1)'
        )

        # Output options
        parser.add_argument(
            '--verbose', '-v',
            action='store_true',
            help='Show detailed output'
        )

    def handle(self, *args, **options):
        from timetable.services.scheduling_service import (
            SchedulingService, SchedulingMode, SchedulingPreferences
        )
        from academics.models import ClassSession

        # Determine mode
        if options['preview']:
            mode = SchedulingMode.SUGGESTIONS_ONLY
        elif options['fill_gaps']:
            mode = SchedulingMode.BATCH_FILL
        else:
            mode = SchedulingMode.SEMI_AUTO

        # Build preferences
        preferences = SchedulingPreferences(
            prefer_morning=not options['prefer_afternoon'],
            spread_subjects=not options['no_spread'],
            max_same_subject_per_day=options['max_same_subject'],
        )

        # Get classes to process
        if options['all']:
            classes = ClassSession.objects.filter(is_active=True)
            self.stdout.write(f"Processing {classes.count()} active classes...")
        else:
            try:
                classes = [ClassSession.objects.get(pk=options['class_id'])]
            except ClassSession.DoesNotExist:
                raise CommandError(f"Class session with ID {options['class_id']} not found")

        service = SchedulingService()
        total_placed = 0
        total_needed = 0
        failed_classes = []

        for class_session in classes:
            self.stdout.write(f"\n{'='*60}")
            self.stdout.write(f"Processing: {class_session.name}")
            self.stdout.write('='*60)

            try:
                result = service.generate_timetable(
                    class_session=class_session,
                    mode=mode,
                    preferences=preferences,
                )

                total_placed += result.placed_count
                total_needed += result.total_allocations

                # Display results
                if result.success:
                    self.stdout.write(self.style.SUCCESS(
                        f"  SUCCESS: {result.placed_count}/{result.total_allocations} "
                        f"slots placed ({result.to_dict()['placement_percentage']:.1f}%)"
                    ))
                else:
                    self.stdout.write(self.style.WARNING(
                        f"  PARTIAL: {result.placed_count}/{result.total_allocations} "
                        f"slots placed ({result.to_dict()['placement_percentage']:.1f}%)"
                    ))

                # Show created slots
                if result.created_slots and options['verbose']:
                    self.stdout.write(f"  Created slot IDs: {result.created_slots}")

                # Show unplaced allocations
                if result.unplaced:
                    self.stdout.write(self.style.WARNING("  Unplaced allocations:"))
                    for unplaced in result.unplaced:
                        self.stdout.write(
                            f"    - {unplaced['subject']} ({unplaced['teacher']}): "
                            f"{unplaced['remaining']} lessons needed - {unplaced['reason']}"
                        )

                # Show warnings
                if result.warnings and options['verbose']:
                    for warning in result.warnings:
                        self.stdout.write(self.style.WARNING(f"  Warning: {warning}"))

                # Timing
                if options['verbose']:
                    self.stdout.write(f"  Time: {result.execution_time_ms:.2f}ms")

            except Exception as e:
                failed_classes.append((class_session.name, str(e)))
                self.stdout.write(self.style.ERROR(f"  FAILED: {str(e)}"))

        # Summary
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write("SUMMARY")
        self.stdout.write('='*60)

        if total_needed > 0:
            percentage = total_placed / total_needed * 100
            self.stdout.write(f"Total: {total_placed}/{total_needed} slots ({percentage:.1f}%)")

        if failed_classes:
            self.stdout.write(self.style.ERROR(f"Failed classes: {len(failed_classes)}"))
            for name, error in failed_classes:
                self.stdout.write(f"  - {name}: {error}")

        if total_placed == total_needed:
            self.stdout.write(self.style.SUCCESS("All allocations scheduled successfully!"))
        elif total_placed > 0:
            self.stdout.write(self.style.WARNING(
                "Some allocations need manual scheduling. "
                "Use the admin interface to complete them."
            ))
        else:
            self.stdout.write(self.style.ERROR(
                "No slots were created. Check work allocations and constraints."
            ))
