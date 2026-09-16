"""concept_ledger — read or update the shared design-DNA ledger."""

import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from djangopress.core.build.ledger import Ledger, format_entries, parse_brief


class Command(BaseCommand):
    help = 'Read/append the cross-site design DNA ledger.'

    def add_arguments(self, parser):
        parser.add_argument('--read', action='store_true')
        parser.add_argument('--append', default='', help='brief-<k>.md to append')
        parser.add_argument('--mark-shipped', nargs=2, metavar=('SITE', 'KEY'))
        parser.add_argument('--site', default='')
        parser.add_argument('--key', default='')
        parser.add_argument('--vertical', default='')
        parser.add_argument('--shipped', action='store_true')
        parser.add_argument('--limit', type=int, default=12)

    def handle(self, *args, **opts):
        ledger = Ledger()
        if opts['read']:
            self.stdout.write(format_entries(ledger.read(vertical=opts['vertical'] or None, limit=opts['limit'])))
        elif opts['append']:
            if not (opts['site'] and opts['key'] and opts['vertical']):
                raise CommandError('--append needs --site, --key and --vertical')
            b = parse_brief(Path(opts['append']).read_text())
            ledger.append({'site': opts['site'], 'date': datetime.date.today().isoformat(), 'key': opts['key'],
                           'name': b['name'], 'vertical': opts['vertical'], 'register': b['register'],
                           'shipped': opts['shipped'], 'dna': b['dna']})
            self.stdout.write(f"appended {b['name']} ({opts['site']}/{opts['key']})")
        elif opts['mark_shipped']:
            ledger.mark_shipped(*opts['mark_shipped'])
            self.stdout.write('ok')
        else:
            raise CommandError('one of --read, --append, --mark-shipped')
