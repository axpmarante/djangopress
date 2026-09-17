"""Tests for prompt filling and build_prompt (Task 10)."""

import copy
import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from djangopress.core.build.prompts import fill_builder, fill_director, registers_for, upsert_concept_index
from djangopress.core.tests.test_build_importer import PACKET
from djangopress.core.tests.test_build_ledger import BRIEF


class RegistersTest(SimpleTestCase):

    def test_registers_conventional_default(self):
        regs = registers_for(3)
        self.assertEqual([l for l, _ in regs], ['A', 'B', 'C'])
        self.assertTrue(regs[0][1].startswith('conventional, template-grade'))
        self.assertIn('one distinctive idea', regs[1][1])
        self.assertIn('different axis', regs[2][1])
        six = [r for _, r in registers_for(6)]
        self.assertEqual(six[:3], [r for _, r in regs])
        self.assertEqual(six[3:], ['canonical, dark variation', 'canonical, type-led variation', 'one bolder take, still usable'])

    def test_registers_bold_unchanged(self):
        self.assertEqual(registers_for(3, 'bold'),
                         [('A', 'commercially safe'), ('B', 'distinctive contemporary'), ('C', 'strongly creative')])
        self.assertEqual([r for _, r in registers_for(6, 'bold')],
                         ['commercially safe', 'distinctive contemporary', 'distinctive contemporary',
                          'strongly creative', 'strongly creative', 'experimental'])


class FillTest(SimpleTestCase):

    def test_director(self):
        text = fill_director(PACKET, 'PREVIOUS DNA HERE', 3)
        self.assertIn('hospitality, restaurants and premium consumer brands', text)
        self.assertIn('Generate: 3 concepts', text)
        self.assertIn('A conventional, template-grade', text)
        self.assertIn('PREVIOUS DNA HERE', text)
        self.assertIn('editorial', text)
        self.assertIn('Cozinha de autor algarvia.', text)
        self.assertNotIn('+351 289 000 000', text)   # the director never sees facts
        self.assertIn('roam freely', text)
        self.assertNotIn('[[', text)

    def test_director_conventional_default(self):
        text = fill_director(PACKET, 'PREVIOUS DNA HERE', 3)
        self.assertIn('CANONICAL STRUCTURE (required', text)
        self.assertIn('reservation', text)
        self.assertIn('ALLOWED in this mode', text)
        self.assertIn('conventional, template-grade', text)
        self.assertIn('The bar is taste, not novelty', text)
        self.assertIn('at least 5 of', text)
        self.assertNotIn('at least 7 of the 16', text)
        self.assertNotIn('floating glass card over hero', text)
        self.assertNotIn('strongly creative', text)
        self.assertNotIn('[[', text)

    def test_director_bold(self):
        packet = copy.deepcopy(PACKET)
        packet['design_constraints']['mode'] = 'bold'
        text = fill_director(packet, 'PREVIOUS DNA HERE', 3)
        self.assertIn('CANONICAL STRUCTURE (for reference', text)
        self.assertIn('floating glass card over hero', text)
        self.assertIn('strongly creative', text)
        self.assertIn('at least 7 of the 16', text)
        self.assertIn('different high-level creative studio', text)
        self.assertNotIn('ALLOWED in this mode', text)
        self.assertNotIn('[[', text)

    def test_director_references(self):
        packet = copy.deepcopy(PACKET)
        packet['design_constraints']['references'] = ['https://example.com/a']
        text = fill_director(packet, '', 3)
        self.assertIn('References chosen by the operator (structure and register to adapt, never copy): https://example.com/a', text)

    def test_director_with_direction(self):
        packet = copy.deepcopy(PACKET)
        packet['design_constraints']['direction'] = 'Sólido e de confiança, claro'
        text = fill_director(packet, 'PREVIOUS DNA HERE', 3)
        self.assertIn('Sólido e de confiança, claro', text)
        self.assertNotIn('[[', text)

    def test_builder(self):
        text = fill_builder(PACKET, BRIEF, 'docs/concepts/concept-b.html')
        self.assertIn('docs/concepts/concept-b.html', text)
        self.assertIn('Boarding Pass', text)
        self.assertIn('REQUIRED', text)
        self.assertIn('Reservar mesa → /reservas/', text)
        self.assertIn('Couvert — 3.30', text)
        self.assertIn('https://example.com/dish.jpg', text)
        self.assertIn('+351 289 000 000', text)
        self.assertIn('Português', text)
        self.assertIn('ONLY to these pages: none — use anchors only', text)
        self.assertIn('/forms/contact/submit/', text)
        self.assertIn('name, email, message', text)
        self.assertIn('name="website_url"', text)
        self.assertNotIn('[[', text)

    def test_builder_conventional_avoid_block(self):
        text = fill_builder(PACKET, BRIEF, 'docs/concepts/concept-b.html')
        self.assertIn('ALLOWED in this mode', text)
        self.assertIn("Also avoid the three items under this concept's own AVOID.", text)
        self.assertNotIn('floating glass card over hero', text)
        self.assertNotIn('[[', text)

    def test_builder_bold_avoid_block(self):
        packet = copy.deepcopy(PACKET)
        packet['design_constraints']['mode'] = 'bold'
        text = fill_builder(packet, BRIEF, 'docs/concepts/concept-b.html')
        self.assertIn('floating glass card over hero', text)
        self.assertIn("Also avoid the three items under this concept's own AVOID.", text)
        self.assertNotIn('ALLOWED in this mode', text)
        self.assertNotIn('[[', text)

    def test_builder_lists_pages(self):
        packet = copy.deepcopy(PACKET)
        packet['pages'] = [{'slug': 'home'}, {'slug': 'contactos'}, {'slug': 'reservas'}]
        text = fill_builder(packet, BRIEF, 'docs/concepts/concept-b.html')
        self.assertIn('ONLY to these pages: /contactos/, /reservas/', text)
        self.assertNotIn('[[', text)


class IndexTest(SimpleTestCase):

    def test_upsert(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'concepts.json'
            upsert_concept_index(p, 'b', BRIEF)
            upsert_concept_index(p, 'b', BRIEF)
            upsert_concept_index(p, 'a', BRIEF.replace('Boarding Pass', 'Quiet Room'))
            rows = json.loads(p.read_text())
        self.assertEqual([(r['key'], r['name'], r['status']) for r in rows], [('a', 'Quiet Room', 'pending'), ('b', 'Boarding Pass', 'pending')])
        self.assertEqual(rows[1]['file'], 'concept-b.html')


class CommandTest(TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'docs' / 'concepts').mkdir(parents=True)
        (self.root / 'docs' / 'build-packet.json').write_text(json.dumps(PACKET))
        (self.root / 'docs' / 'concepts' / 'brief-b.md').write_text(BRIEF)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cmd(self, *args):
        out = StringIO()
        with patch('djangopress.core.management.commands.build_prompt.Path.cwd', return_value=self.root), \
             patch('djangopress.core.management.commands.build_prompt.Ledger') as L:
            L.return_value.read.return_value = []
            call_command('build_prompt', *args, '--packet', str(self.root / 'docs' / 'build-packet.json'), stdout=out)
        return json.loads(out.getvalue())

    def test_director_written(self):
        rep = self.run_cmd('director', '--concepts', '3')
        p = self.root / 'docs' / 'concepts' / 'prompts' / 'director.md'
        self.assertEqual(rep['prompt'], str(p))
        self.assertIn('none yet', p.read_text())

    def test_builder_written_and_indexed(self):
        rep = self.run_cmd('builder', 'b')
        p = self.root / 'docs' / 'concepts' / 'prompts' / 'builder-b.md'
        self.assertEqual(rep['prompt'], str(p))
        self.assertEqual(rep['output'], 'docs/concepts/concept-b.html')
        self.assertIn('Boarding Pass', p.read_text())
        self.assertIn(str(self.root / 'docs' / 'concepts' / 'concept-b.html'), p.read_text())
        rows = json.loads((self.root / 'docs' / 'concepts' / 'concepts.json').read_text())
        self.assertEqual(rows[0]['key'], 'b')
