"""import_concept — one standalone concept document → DjangoPress rows (spec §7)."""

import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from djangopress.core.build.adapter import adapt
from djangopress.core.build.importer import cta_texts_from, import_as_page, import_result


def concept_key(path):
    m = re.search(r'concept-([a-z])\.html$', str(path))
    return m.group(1) if m else Path(path).stem


class Command(BaseCommand):
    help = 'Import a standalone concept HTML document as the site home page, header and footer.'

    def add_arguments(self, parser):
        parser.add_argument('file')
        parser.add_argument('--home', action='store_true')
        parser.add_argument('--as-page', default='', metavar='SLUG', help='import as an extra page with this slug (no header/footer/menu changes)')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--packet', default='docs/build-packet.json')
        parser.add_argument('--key', default='')

    def handle(self, *args, **opts):
        if opts['home'] and opts['as_page']:
            raise CommandError('--home and --as-page are mutually exclusive')
        path = Path(opts['file'])
        packet_path = Path(opts['packet'])
        if not packet_path.exists():
            raise CommandError(f'{packet_path} not found — run build_prepare first')
        packet = json.loads(packet_path.read_text())
        key = opts['key'] or concept_key(path)
        result = adapt(path.read_text(), lang=packet['site']['default_language'], languages=packet['site']['languages'],
                       image_map=packet['images']['map'], cta_texts=cta_texts_from(packet),
                       contact_phone=packet['facts'].get('phone', ''))
        report = result.as_report()
        report['key'] = key
        if result.ok and not opts['dry_run']:
            if opts['as_page']:
                saved = import_as_page(result, packet=packet, slug=opts['as_page'], change_summary=f"Import concept {key} as {opts['as_page']}")
            else:
                saved = import_result(result, packet=packet, set_home=opts['home'], change_summary=f'Import concept {key}')
            report.update(saved)
            out = path.parent / f'import-{key}.json'
            out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
            report['report'] = str(out)
        self.stdout.write(json.dumps(report, ensure_ascii=False))
        if not result.ok:
            raise SystemExit(1)
