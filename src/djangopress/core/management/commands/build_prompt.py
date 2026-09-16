"""build_prompt — write the filled director or builder prompt to docs/concepts/prompts/."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from djangopress.core.build.ledger import Ledger, format_entries
from djangopress.core.build.prompts import fill_builder, fill_director, upsert_concept_index


class Command(BaseCommand):
    help = 'Fill a prompt template: build_prompt director [--concepts N] | build_prompt builder <k>'

    def add_arguments(self, parser):
        parser.add_argument('kind', choices=['director', 'builder'])
        parser.add_argument('key', nargs='?', default='')
        parser.add_argument('--concepts', type=int, default=3)
        parser.add_argument('--packet', default='docs/build-packet.json')

    def handle(self, *args, **opts):
        root = Path.cwd()
        packet = json.loads(Path(opts['packet']).read_text())
        prompts = root / 'docs' / 'concepts' / 'prompts'
        prompts.mkdir(parents=True, exist_ok=True)
        if opts['kind'] == 'director':
            n = opts['concepts']
            if not 1 <= n <= 6:
                raise CommandError('--concepts must be between 1 and 6')
            ledger = format_entries(Ledger().read(vertical=packet['business']['type']))
            out = prompts / 'director.md'
            out.write_text(fill_director(packet, ledger, n))
            self.stdout.write(json.dumps({'prompt': str(out), 'concepts': n}))
            return
        key = opts['key']
        if not key:
            raise CommandError('builder needs a concept key')
        brief = root / 'docs' / 'concepts' / f'brief-{key}.md'
        if not brief.exists():
            raise CommandError(f'{brief} not found — write the director output there first')
        output = f'docs/concepts/concept-{key}.html'
        out = prompts / f'builder-{key}.md'
        out.write_text(fill_builder(packet, brief.read_text(), output))
        entry = upsert_concept_index(root / 'docs' / 'concepts' / 'concepts.json', key, brief.read_text())
        self.stdout.write(json.dumps({'prompt': str(out), 'output': output, 'concept': entry}, ensure_ascii=False))
