from django.core.management.base import BaseCommand
from projects.models import Project, parse_xlsform


class Command(BaseCommand):
    help = 'Re-parse XLSForm schemas for all projects (or a specific one) to pick up new schema fields like "relevant".'

    def add_arguments(self, parser):
        parser.add_argument(
            '--project-id',
            type=int,
            default=None,
            help='Only re-parse the schema for this project ID. Omit to process all projects.',
        )

    def handle(self, *args, **options):
        qs = Project.objects.all()
        if options['project_id']:
            qs = qs.filter(pk=options['project_id'])

        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.WARNING('No matching projects found.'))
            return

        self.stdout.write(f'Re-parsing schemas for {total} project(s)...')
        ok = 0
        skip = 0
        err = 0

        for project in qs:
            if not project.xlsform:
                self.stdout.write(self.style.WARNING(
                    f'  [{project.pk}] {project.name} — skipped (no XLSForm uploaded)'
                ))
                skip += 1
                continue

            try:
                parsed = parse_xlsform(project.xlsform.path)
                if 'error' in parsed:
                    self.stdout.write(self.style.ERROR(
                        f'  [{project.pk}] {project.name} — parse error: {parsed["error"]}'
                    ))
                    err += 1
                    continue

                Project.objects.filter(pk=project.pk).update(schema_json=parsed)

                field_count = len(parsed.get('fields', []))
                relevant_count = sum(1 for f in parsed.get('fields', []) if f.get('relevant'))
                self.stdout.write(self.style.SUCCESS(
                    f'  [{project.pk}] {project.name} — OK '
                    f'({field_count} fields, {relevant_count} with skip logic)'
                ))
                ok += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f'  [{project.pk}] {project.name} — error: {e}'
                ))
                err += 1

        self.stdout.write(f'\nDone. {ok} updated, {skip} skipped, {err} errors.')
