"""promote_concept — make another already-built concept the live home page, optionally publish (spec §9, §10)."""

import json
import subprocess
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from djangopress.core.build.adapter import adapt
from djangopress.core.build.importer import cta_texts_from, import_result
from djangopress.core.build.ledger import Ledger

PUBLISH_CMD = 'bash scripts/sync-to-prod.sh && railway redeploy -y'


class Command(BaseCommand):
    help = 'Import docs/concepts/concept-<k>.html as the home page and mark it shipped.'

    def add_arguments(self, parser):
        parser.add_argument('key')
        parser.add_argument('--publish', action='store_true')
        parser.add_argument('--packet', default='docs/build-packet.json')

    def handle(self, *args, **opts):
        root = Path.cwd()
        key = opts['key']
        packet = json.loads(Path(opts['packet']).read_text())
        concepts_dir = root / 'docs' / 'concepts'
        path = concepts_dir / f'concept-{key}.html'
        if not path.exists():
            raise CommandError(f'{path} not found')
        result = adapt(path.read_text(), lang=packet['site']['default_language'], languages=packet['site']['languages'],
                       image_map=packet['images']['map'], cta_texts=cta_texts_from(packet),
                       contact_phone=packet['facts'].get('phone', ''))
        report = result.as_report()
        report['key'] = key
        if not result.ok:
            self.stdout.write(json.dumps(report, ensure_ascii=False))
            raise SystemExit(1)
        report.update(import_result(result, packet=packet, set_home=True, change_summary=f'Promote concept {key}'))

        index_path = concepts_dir / 'concepts.json'
        if index_path.exists():
            index = json.loads(index_path.read_text())
            for entry in index:
                if entry['key'] == key:
                    entry['status'] = 'shipped'
                elif entry.get('status') == 'shipped':
                    entry['status'] = 'rejected'
            index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2))
        Ledger().mark_shipped(packet['site']['slug'], key)

        report['published'] = False
        if opts['publish']:
            if subprocess.run(['railway', 'status'], capture_output=True).returncode == 0:
                subprocess.run(PUBLISH_CMD, shell=True, check=True)
                report['published'] = True
            else:
                report['publish_hint'] = 'site is not linked to Railway — run /deploy-site-railway first'
        self.stdout.write(json.dumps(report, ensure_ascii=False))
