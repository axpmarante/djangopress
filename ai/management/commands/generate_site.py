"""
Management command for non-interactive full site generation from a briefing document.

Usage:
    python manage.py generate_site briefings/my-restaurant.md
    python manage.py generate_site briefings/my-restaurant.md --dry-run
    python manage.py generate_site briefings/my-restaurant.md --skip-images
    python manage.py generate_site briefings/my-restaurant.md --model gemini-pro --delay 3
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Generate a full site from a markdown briefing document'

    def add_arguments(self, parser):
        parser.add_argument(
            'briefing',
            help='Path to the markdown briefing file (e.g. briefings/my-site.md)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Parse briefing and show planned pages without generating anything',
        )
        parser.add_argument(
            '--skip-images',
            action='store_true',
            help='Skip image processing (faster, images can be done later via backoffice)',
        )
        parser.add_argument(
            '--skip-design-guide',
            action='store_true',
            help='Skip design guide generation after home page',
        )
        parser.add_argument(
            '--model',
            default='gemini-pro',
            help='LLM model to use for generation (default: gemini-pro)',
        )
        parser.add_argument(
            '--image-strategy',
            choices=['ai_generated', 'unsplash_preferred', 'mixed', 'skip'],
            default=None,
            help='Image handling strategy (default: from briefing or ai_generated)',
        )
        parser.add_argument(
            '--delay',
            type=int,
            default=2,
            help='Delay in seconds between LLM calls to avoid rate limits (default: 2)',
        )

    def handle(self, *args, **options):
        from ai.site_generator import SiteGenerator

        briefing_path = options['briefing']

        try:
            generator = SiteGenerator(
                briefing_path=briefing_path,
                stdout=self.stdout,
                dry_run=options['dry_run'],
                skip_images=options['skip_images'],
                skip_design_guide=options['skip_design_guide'],
                model=options['model'],
                image_strategy=options['image_strategy'],
                delay=options['delay'],
            )
        except FileNotFoundError as e:
            self.stderr.write(self.style.ERROR(str(e)))
            return

        try:
            result = generator.run()
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Generation failed: {e}'))
            raise

        if options['dry_run']:
            self.stdout.write(self.style.SUCCESS('\nDry run complete. No changes were made.'))
        elif result:
            errors = result.get('errors', [])
            if errors:
                self.stdout.write(self.style.WARNING(
                    f'\nGeneration completed with {len(errors)} error(s).'
                ))
            else:
                self.stdout.write(self.style.SUCCESS('\nSite generated successfully!'))
