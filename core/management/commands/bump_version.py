"""
bump_version management command — bump the DjangoPress semantic version.

Usage:
    python manage.py bump_version patch   # 1.0.0 → 1.0.1
    python manage.py bump_version minor   # 1.0.1 → 1.1.0
    python manage.py bump_version major   # 1.1.0 → 2.0.0
    python manage.py bump_version         # shows current version
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


VERSION_FILE = Path(__file__).resolve().parents[3] / 'VERSION'


def get_version():
    """Read current version from VERSION file."""
    return VERSION_FILE.read_text().strip()


def set_version(version):
    """Write version to VERSION file."""
    VERSION_FILE.write_text(f'{version}\n')


class Command(BaseCommand):
    help = 'Bump the DjangoPress semantic version (major.minor.patch).'

    def add_arguments(self, parser):
        parser.add_argument(
            'part',
            nargs='?',
            choices=['major', 'minor', 'patch'],
            help='Which part to bump (major, minor, or patch). Omit to show current version.',
        )

    def handle(self, *args, **options):
        current = get_version()
        part = options['part']

        if not part:
            self.stdout.write(f'DjangoPress v{current}')
            return

        try:
            major, minor, patch = (int(x) for x in current.split('.'))
        except ValueError:
            raise CommandError(f'Invalid version in VERSION file: {current}')

        if part == 'major':
            major += 1
            minor = 0
            patch = 0
        elif part == 'minor':
            minor += 1
            patch = 0
        elif part == 'patch':
            patch += 1

        new_version = f'{major}.{minor}.{patch}'
        set_version(new_version)
        self.stdout.write(self.style.SUCCESS(f'v{current} → v{new_version}'))
