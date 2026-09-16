"""build_verify — screen concept files, or verify the live site (spec §8)."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from djangopress.core.build.verify import screen_file, verify_live


class Command(BaseCommand):
    help = 'Verify concept files (--files) or the imported site: check_site + probe + content contract.'

    def add_arguments(self, parser):
        parser.add_argument('--files', nargs='*', default=[])
        parser.add_argument('--widths', default='390,834,1440')
        parser.add_argument('--port', type=int, default=8000)
        parser.add_argument('--no-screenshot', action='store_true')
        parser.add_argument('--packet', default='docs/build-packet.json')

    def handle(self, *args, **opts):
        packet_path = Path(opts['packet'])
        if not packet_path.exists():
            raise CommandError(f'{packet_path} not found — run build_prepare first')
        packet = json.loads(packet_path.read_text())
        widths = tuple(int(w) for w in opts['widths'].split(','))
        if opts['files']:
            results = [screen_file(f, packet, widths=widths) for f in opts['files']]
            out = Path.cwd() / 'docs' / 'concepts' / 'screen.json'
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(results, ensure_ascii=False, indent=2))
            self.stdout.write(json.dumps(results, ensure_ascii=False))
            if not all(r['clean'] for r in results):
                raise SystemExit(1)
            if not all(r['probe_available'] for r in results):
                raise SystemExit(2)
            return
        result = verify_live(packet, port=opts['port'], screenshot=not opts['no_screenshot'], widths=widths)
        out = Path.cwd() / 'docs' / 'verify.json'
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        self.stdout.write(json.dumps(result, ensure_ascii=False))
        if not result['clean']:
            raise SystemExit(1)
        if not result['probe']['available']:
            raise SystemExit(2)
