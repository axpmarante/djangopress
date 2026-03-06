"""
pull_data management command — pull remote database content to local.

Usage:
    python manage.py pull_data https://my-site.railway.app
    python manage.py pull_data https://my-site.railway.app --dry-run
"""

import json
import os
import urllib.request
import urllib.error

from django.core.management.base import BaseCommand, CommandError
from django.core.cache import cache
from django.db import connection
from django.core.serializers import deserialize

from core.management.commands.push_data import SYNC_TABLES_ORDERED


class Command(BaseCommand):
    help = 'Pull remote database content to the local DjangoPress database.'

    def add_arguments(self, parser):
        parser.add_argument('url', help='Remote site URL (e.g. https://my-site.railway.app)')
        parser.add_argument('--dry-run', action='store_true', help='Fetch and show summary without loading')

    def handle(self, *args, **options):
        url = options['url'].rstrip('/')
        dry_run = options['dry_run']

        sync_secret = os.environ.get('SYNC_SECRET', '')
        if not sync_secret:
            raise CommandError(
                'SYNC_SECRET is not set.\n'
                'Add SYNC_SECRET=<random-token> to your .env file.\n'
                'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
            )

        endpoint = f'{url}/backoffice/api/data-sync-export/'
        self.stdout.write(f'Fetching data from {endpoint}...')

        req = urllib.request.Request(
            endpoint,
            headers={'Authorization': f'Bearer {sync_secret}'},
            method='GET',
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read().decode()
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            try:
                msg = json.loads(body).get('error', body)
            except (json.JSONDecodeError, ValueError):
                msg = body
            if e.code == 404:
                raise CommandError(
                    'Export endpoint not found (404). Deploy the latest code first: railway up -d'
                )
            raise CommandError(f'HTTP {e.code}: {msg}')
        except urllib.error.URLError as e:
            raise CommandError(f'Connection failed: {e.reason}')

        try:
            fixture = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            raise CommandError('Invalid response from server (not valid JSON)')

        if not isinstance(fixture, list):
            # Server might have returned an error object
            if isinstance(fixture, dict) and 'error' in fixture:
                raise CommandError(f'Server error: {fixture["error"]}')
            raise CommandError('Invalid response from server (expected JSON array)')

        # Summary
        counts = {}
        for obj in fixture:
            model = obj.get('model', 'unknown')
            counts[model] = counts.get(model, 0) + 1
        total = sum(counts.values())
        size_mb = len(raw.encode()) / (1024 * 1024)

        self.stdout.write('\nFixture summary:')
        for model in sorted(counts):
            self.stdout.write(f'  {model}: {counts[model]}')
        self.stdout.write(f'  Total: {total} objects, {size_mb:.1f} MB')

        if total == 0:
            self.stdout.write(self.style.WARNING('\nWarning: remote returned 0 objects.'))

        if dry_run:
            self.stdout.write(self.style.SUCCESS('\nDry run complete. No local data changed.'))
            return

        # Confirm
        self.stdout.write(f'\nThis will REPLACE local content with data from {url}')
        answer = input('Type "yes" to proceed: ')
        if answer.strip().lower() != 'yes':
            self.stdout.write('Aborted.')
            return

        self.stdout.write(f'\nLoading {total} objects into local database...')

        # Truncate local sync tables
        is_sqlite = connection.vendor == 'sqlite'
        with connection.cursor() as cursor:
            if is_sqlite:
                cursor.execute('PRAGMA foreign_keys = OFF')
            try:
                for table in SYNC_TABLES_ORDERED:
                    cursor.execute(f'DELETE FROM "{table}"')
            finally:
                if is_sqlite:
                    cursor.execute('PRAGMA foreign_keys = ON')

        # Reset PostgreSQL sequences if applicable
        if connection.vendor == 'postgresql':
            with connection.cursor() as cursor:
                for table in SYNC_TABLES_ORDERED:
                    cursor.execute(
                        f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), 1, false)"
                    )

        # Deserialize and save
        json_str = json.dumps(fixture)
        objects = list(deserialize('json', json_str))
        count = 0
        for obj in objects:
            obj.save()
            count += 1

        cache.clear()
        self.stdout.write(self.style.SUCCESS(f'Done! {count} objects loaded locally.'))
