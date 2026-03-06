"""
push_data management command — push local database content to a remote DjangoPress site.

Usage:
    python manage.py push_data https://my-site.railway.app
    python manage.py push_data https://my-site.railway.app --dry-run
"""

import json
import sys
import urllib.request
import urllib.error

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from io import StringIO


# Models to sync — order matters for foreign key dependencies.
# This list is imported by pull_data and data_sync_export.
DUMP_MODELS = [
    'djangopress.core.SiteSettings',
    'djangopress.core.DynamicForm',
    'djangopress.core.FormSubmission',
    'djangopress.core.SiteImage',
    'djangopress.core.Page',
    'djangopress.core.GlobalSection',
    'djangopress.core.MenuItem',
    # PageVersion handled separately (filtered to last 3 per page)
]

# DB table names in truncation order (children before parents).
SYNC_TABLES_ORDERED = [
    'core_pageversion',
    'core_menuitem',
    'core_globalsection',
    'core_page',
    'core_siteimage',
    'core_formsubmission',
    'core_dynamicform',
    'core_sitesettings',
]

MAX_VERSIONS_PER_PAGE = 3


def build_fixture():
    """Serialize DUMP_MODELS + filtered PageVersions to a JSON string."""
    from djangopress.core.models import Page, PageVersion

    # Dump main models
    buf = StringIO()
    call_command('dumpdata', *DUMP_MODELS, format='json', indent=None, stdout=buf)
    fixture = json.loads(buf.getvalue())

    # Add last N PageVersions per page, with created_by nullified
    for page in Page.objects.all():
        versions = (
            PageVersion.objects
            .filter(page=page)
            .order_by('-created_at')[:MAX_VERSIONS_PER_PAGE]
        )
        for v in versions:
            buf2 = StringIO()
            call_command(
                'dumpdata', 'djangopress.core.PageVersion',
                pks=str(v.pk), format='json', indent=None, stdout=buf2,
            )
            entries = json.loads(buf2.getvalue())
            for entry in entries:
                entry['fields']['created_by'] = None
            fixture.extend(entries)

    return fixture


def fixture_summary(fixture):
    """Return a dict of model_label → count."""
    counts = {}
    for obj in fixture:
        model = obj['model']
        counts[model] = counts.get(model, 0) + 1
    return counts


class Command(BaseCommand):
    help = 'Push local database content to a remote DjangoPress site.'

    def add_arguments(self, parser):
        parser.add_argument('url', help='Remote site URL (e.g. https://my-site.railway.app)')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be sent without pushing')

    def handle(self, *args, **options):
        url = options['url'].rstrip('/')
        dry_run = options['dry_run']

        sync_secret = getattr(settings, 'SYNC_SECRET', None) or settings.__dict__.get('SYNC_SECRET')
        # Try env directly
        if not sync_secret:
            import os
            sync_secret = os.environ.get('SYNC_SECRET', '')

        if not sync_secret:
            raise CommandError(
                'SYNC_SECRET is not set.\n'
                'Add SYNC_SECRET=<random-token> to your .env file.\n'
                'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
            )

        self.stdout.write('Building fixture from local database...')
        fixture = build_fixture()
        payload = json.dumps(fixture)
        size_mb = len(payload.encode()) / (1024 * 1024)

        counts = fixture_summary(fixture)
        total = sum(counts.values())

        self.stdout.write('\nFixture summary:')
        for model in sorted(counts):
            self.stdout.write(f'  {model}: {counts[model]}')
        self.stdout.write(f'  Total: {total} objects, {size_mb:.1f} MB')

        if dry_run:
            self.stdout.write(self.style.SUCCESS('\nDry run complete. No data sent.'))
            return

        # Confirm
        self.stdout.write(f'\nThis will REPLACE content on {url}')
        answer = input('Type "yes" to proceed: ')
        if answer.strip().lower() != 'yes':
            self.stdout.write('Aborted.')
            return

        endpoint = f'{url}/backoffice/api/data-sync/'
        self.stdout.write(f'\nPushing {total} objects to {endpoint}...')

        req = urllib.request.Request(
            endpoint,
            data=payload.encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {sync_secret}',
            },
            method='POST',
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode())
                if body.get('success'):
                    self.stdout.write(self.style.SUCCESS(
                        f'Done! {body.get("loaded", total)} objects pushed to {url}.'
                    ))
                else:
                    raise CommandError(f'Server error: {body.get("error", "unknown")}')
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            try:
                msg = json.loads(body).get('error', body)
            except json.JSONDecodeError:
                msg = body
            if e.code == 404:
                raise CommandError(
                    f'Export endpoint not found (404). Deploy first with: railway up -d'
                )
            raise CommandError(f'HTTP {e.code}: {msg}')
        except urllib.error.URLError as e:
            raise CommandError(f'Connection failed: {e.reason}')
