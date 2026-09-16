"""
audit_repeat_groups — Phase 0 measurement for the editor's "Add another" verb.

For every active page (default language unless --lang), lists the sibling
groups the repeat-group heuristic finds per section, with size and
ambiguity flags. Read-only.

Usage:
    python manage.py audit_repeat_groups           # markdown table
    python manage.py audit_repeat_groups --json
    python manage.py audit_repeat_groups --lang en
"""
import json

from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand

from djangopress.core.models import Page, SiteSettings
from djangopress.editor_v2.structure import find_repeat_groups


class Command(BaseCommand):
    help = 'Report repeat groups found by the editor heuristic, per page and section.'

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true', dest='as_json')
        parser.add_argument('--lang', default=None)

    def handle(self, *args, **options):
        settings = SiteSettings.load()
        lang = options['lang'] or settings.get_default_language()
        report = {'language': lang, 'pages': []}

        for page in Page.objects.filter(is_active=True).order_by('sort_order', 'id'):
            html = (page.html_content_i18n or {}).get(lang) or ''
            soup = BeautifulSoup(html, 'html.parser')
            page_entry = {'slug': (page.slug_i18n or {}).get(lang, str(page.id)), 'sections': []}
            for section in soup.find_all('section', attrs={'data-section': True}):
                groups = find_repeat_groups(section)
                page_entry['sections'].append({
                    'name': section.get('data-section'),
                    'groups': [{
                        'signature': g['signature'],
                        'size': g['size'],
                        'nested': g['nested'],
                        'ambiguous': g['ambiguous'],
                        'container_path': g['container_path'],
                    } for g in groups],
                })
            report['pages'].append(page_entry)

        if options['as_json']:
            self.stdout.write(json.dumps(report, indent=2, ensure_ascii=False))
            return

        self.stdout.write(f'# Repeat groups ({lang})\n')
        self.stdout.write('| page | section | signature | size | nested | ambiguous |')
        self.stdout.write('|---|---|---|---|---|---|')
        for p in report['pages']:
            for s in p['sections']:
                if not s['groups']:
                    self.stdout.write(f"| {p['slug']} | {s['name']} | (none) | | | |")
                for g in s['groups']:
                    self.stdout.write(
                        f"| {p['slug']} | {s['name']} | {g['signature']} | {g['size']} | "
                        f"{'yes' if g['nested'] else ''} | {g['ambiguous']} |"
                    )
