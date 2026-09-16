"""Tests for the design DNA ledger (Task 3)."""

import json
import os
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase

from djangopress.core.build.ledger import Ledger, format_entries, parse_brief

BRIEF = """CONCEPT NAME: Boarding Pass
REGISTER: distinctive
CREATIVE PREMISE: The restaurant as a departure gate; every section is a stamp on a ticket.
BRAND IDEA: The airport vocabulary of the menu.
DESIGN DNA:
- Movement: graphic-design-led
- Personality: playful, precise
- Layout grammar: ticket-stub modules on a 12-col grid
- Hero: full-bleed red field with a perforated ticket card
- Typography: Instrument Serif + DM Sans
- Color: cream ground, oxblood and plum accents
- Photography: documentary, warm
- Cropping: tight, tilted
- Graphic device: perforation line
- Section transitions: dashed tear lines
- Geometry: rounded stubs
- Density: medium
- Navigation: boarding-strip bar
- CTA: stamp button
- Motion: stamp-in on scroll
- Mobile behaviour: stubs stack
HERO DESCRIPTION: ...
"""


class ParseBriefTest(SimpleTestCase):

    def test_fields(self):
        b = parse_brief(BRIEF)
        self.assertEqual(b['name'], 'Boarding Pass')
        self.assertEqual(b['register'], 'distinctive')
        self.assertTrue(b['premise'].startswith('The restaurant'))
        self.assertEqual(b['dna']['graphic_device'], 'perforation line')
        self.assertEqual(b['dna']['mobile'], 'stubs stack')
        self.assertEqual(len(b['dna']), 16)


class LedgerTest(SimpleTestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / '.design-dna' / 'ledger.json'

    def tearDown(self):
        self.tmp.cleanup()

    def entry(self, site, key, vertical='restaurant', shipped=False, date='2026-09-16'):
        b = parse_brief(BRIEF)
        return {'site': site, 'date': date, 'key': key, 'name': b['name'], 'vertical': vertical,
                'register': b['register'], 'shipped': shipped, 'dna': b['dna']}

    def test_append_read_filter_and_order(self):
        led = Ledger(self.path)
        led.append(self.entry('a-site', 'a', date='2026-09-01'))
        led.append(self.entry('b-site', 'b', shipped=True, date='2026-09-02'))
        led.append(self.entry('c-site', 'c', vertical='legal', date='2026-09-03'))
        rows = led.read(vertical='restaurant')
        self.assertEqual([r['site'] for r in rows], ['b-site', 'a-site'])
        self.assertEqual(len(led.read()), 3)
        self.assertEqual(len(led.read(limit=1)), 1)

    def test_mark_shipped(self):
        led = Ledger(self.path)
        led.append(self.entry('a-site', 'a'))
        led.mark_shipped('a-site', 'a')
        self.assertTrue(led.read()[0]['shipped'])

    def test_format_entries(self):
        text = format_entries([self.entry('a-site', 'a')])
        self.assertIn('Boarding Pass', text)
        self.assertIn('Graphic device: perforation line', text)

    def test_command_roundtrip(self):
        brief = Path(self.tmp.name) / 'brief-b.md'
        brief.write_text(BRIEF)
        with patch.dict(os.environ, {'DJANGOPRESS_SITES_ROOT': self.tmp.name}):
            call_command('concept_ledger', '--append', str(brief), '--site', 'x', '--key', 'b', '--vertical', 'restaurant', '--shipped')
            out = StringIO()
            call_command('concept_ledger', '--read', '--vertical', 'restaurant', stdout=out)
        self.assertIn('Boarding Pass', out.getvalue())
        self.assertTrue(json.loads(self.path.read_text())[0]['shipped'])
