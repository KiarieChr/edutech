"""
Management command: migrate_to_templates

Converts existing FeeStructure + FeeItem records into the new three-layer
VoteHead → FeeTemplate → TemplateLineItem architecture.

Groups structures that share the same fee items into a single template
covering multiple grades, dramatically reducing duplication.

Safe to re-run (idempotent via get_or_create).
"""
from collections import defaultdict
from django.core.management.base import BaseCommand
from django.db import transaction
from fees.models import (
    FeeStructure, FeeItem,
    VoteHead, GradeBand, FeeTemplate, TemplateLineItem,
)


class Command(BaseCommand):
    help = (
        'Migrate existing FeeStructures/FeeItems into VoteHead + FeeTemplate + '
        'TemplateLineItem. Groups duplicate structures into shared templates.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print migration plan without writing to the database.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        self.stdout.write(self.style.MIGRATE_HEADING(
            'Fee Template Migration' + (' (DRY RUN)' if dry_run else '')
        ))
        self.stdout.write('')

        structures = FeeStructure.objects.prefetch_related(
            'items__account'
        ).select_related(
            'academic_year', 'term', 'grade', 'curriculum'
        ).order_by('academic_year', 'term', 'grade')

        if not structures.exists():
            self.stdout.write(self.style.WARNING('No FeeStructures found. Nothing to migrate.'))
            return

        # ── STEP 1: Extract unique vote heads ──────────────────
        self.stdout.write(self.style.MIGRATE_HEADING('Step 1: Extract Vote Heads'))

        vote_head_map = {}  # name → VoteHead instance (or dict in dry-run)
        seen_names = set()

        for structure in structures:
            for item in structure.items.all():
                key = item.name.strip()
                if key in seen_names:
                    continue
                seen_names.add(key)

                code = self._generate_code(key)
                vh_data = {
                    'name': key,
                    'code': code,
                    'account': item.account,
                    'frequency': item.frequency,
                    'is_optional': item.is_optional,
                }

                if dry_run:
                    vote_head_map[key] = vh_data
                    self.stdout.write(f"  [DRY] VoteHead: {code} - {key} → {item.account}")
                else:
                    vh, created = VoteHead.objects.get_or_create(
                        name=key,
                        defaults={
                            'code': code,
                            'default_account': item.account,
                            'frequency': item.frequency,
                            'is_optional': item.is_optional,
                        }
                    )
                    vote_head_map[key] = vh
                    tag = 'CREATED' if created else 'EXISTS'
                    self.stdout.write(self.style.SUCCESS(
                        f"  [{tag}] {vh.code} - {vh.name}"
                    ))

        self.stdout.write(f'\n  Total vote heads: {len(vote_head_map)}')

        # ── STEP 2: Group structures into templates ────────────
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('Step 2: Group Structures → Templates'))

        # Group by (term, year, curriculum, fingerprint)
        # where fingerprint = sorted tuple of (item_name, amount)
        groups = defaultdict(list)

        for structure in structures:
            items = structure.items.all().order_by('name')
            fingerprint = tuple(
                (item.name.strip(), float(item.amount))
                for item in items
            )
            key = (
                structure.term_id,
                structure.academic_year_id,
                structure.curriculum_id,
                fingerprint,
            )
            groups[key].append(structure)

        self.stdout.write(f'  {structures.count()} structures → {len(groups)} unique templates')
        self.stdout.write(f'  Reduction: {structures.count() - len(groups)} duplicate structures eliminated')

        # ── STEP 3: Create templates and line items ────────────
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('Step 3: Create Fee Templates'))

        templates_created = 0
        line_items_created = 0

        if not dry_run:
            with transaction.atomic():
                templates_created, line_items_created = self._create_templates(
                    groups, vote_head_map
                )
        else:
            for key, group in groups.items():
                term_id, year_id, curr_id, fingerprint = key
                grade_names = [s.grade.name for s in group]
                representative = group[0]

                self.stdout.write(
                    f"  [DRY] Template: {representative.term} {representative.academic_year} "
                    f"→ Grades: {', '.join(grade_names)} "
                    f"({len(fingerprint)} items)"
                )
                templates_created += 1
                line_items_created += len(fingerprint)

        # ── SUMMARY ──────────────────────────────────────────
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('Migration Summary'))
        self.stdout.write(f'  Source FeeStructures:     {structures.count()}')
        self.stdout.write(f'  Vote Heads extracted:     {len(vote_head_map)}')
        self.stdout.write(f'  Templates created:        {templates_created}')
        self.stdout.write(f'  Line items created:       {line_items_created}')
        self.stdout.write(f'  Structures eliminated:    {structures.count() - templates_created}')

        if structures.count() > 0:
            pct = round((1 - templates_created / structures.count()) * 100, 1)
            self.stdout.write(f'  Reduction:                {pct}%')

        if dry_run:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                '  DRY RUN complete. No data written. '
                'Remove --dry-run to execute migration.'
            ))
        else:
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS(
                '  Migration complete. Legacy FeeStructures preserved for backward compatibility.'
            ))

    def _create_templates(self, groups, vote_head_map):
        templates_created = 0
        line_items_created = 0

        for key, group in groups.items():
            term_id, year_id, curr_id, fingerprint = key
            representative = group[0]
            grade_names = [s.grade.name for s in group]

            # Build template name
            if len(group) == 1:
                name = f"{representative.grade.name} Fees"
            else:
                name = f"{grade_names[0]}-{grade_names[-1]} Fees"

            template, t_created = FeeTemplate.objects.get_or_create(
                name=name,
                term_id=term_id,
                academic_year_id=year_id,
                defaults={
                    'curriculum_id': curr_id,
                    'status': representative.status,
                    'currency': representative.currency,
                }
            )

            if t_created:
                templates_created += 1

            # Assign grades
            grade_ids = [s.grade_id for s in group]
            template.grades.add(*grade_ids)

            # Create line items
            for item_name, item_amount in fingerprint:
                vh = vote_head_map.get(item_name.strip())
                if not vh:
                    continue

                # Find the original FeeItem for metadata
                original = representative.items.filter(name__iexact=item_name.strip()).first()

                _, li_created = TemplateLineItem.objects.get_or_create(
                    template=template,
                    vote_head=vh,
                    defaults={
                        'amount': item_amount,
                        'is_mandatory': not (original.is_optional if original else False),
                        'priority': original.priority if original else 0,
                    }
                )

                if li_created:
                    line_items_created += 1

            tag = 'CREATED' if t_created else 'EXISTS'
            self.stdout.write(self.style.SUCCESS(
                f"  [{tag}] {name} → {', '.join(grade_names)} "
                f"({len(fingerprint)} items, status={template.status})"
            ))

        return templates_created, line_items_created

    @staticmethod
    def _generate_code(name):
        """Generate a short unique code from a vote head name."""
        # Take first 3 consonants or uppercase letters
        words = name.upper().replace('-', ' ').replace('/', ' ').split()
        if len(words) == 1:
            code = words[0][:3]
        else:
            code = ''.join(w[0] for w in words[:4])

        # Ensure uniqueness
        base = code
        counter = 1
        while VoteHead.objects.filter(code=code).exists():
            code = f"{base}{counter}"
            counter += 1

        return code

