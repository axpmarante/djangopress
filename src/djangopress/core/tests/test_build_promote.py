"""Tests for promote_concept (Task 9)."""

import json
import os
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from djangopress.core.models import Page, SiteSettings
from djangopress.core.tests.test_build_importer import MINIMAL, PACKET

INDEX = [
    {'key': 'a', 'name': 'Safe', 'register': 'safe', 'premise': '', 'file': 'concept-a.html', 'status': 'rejected'},
    {'key': 'b', 'name': 'Distinct', 'register': 'distinctive', 'premise': '', 'file': 'concept-b.html', 'status': 'shipped'},
    {'key': 'c', 'name': 'Wild', 'register': 'creative', 'premise': '', 'file': 'concept-c.html', 'status': 'rejected'},
]


class PromoteConceptTest(TestCase):

    def setUp(self):
        Page.objects.all().delete()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'docs' / 'concepts').mkdir(parents=True)
        (self.root / 'docs' / 'build-packet.json').write_text(json.dumps(PACKET))
        (self.root / 'docs' / 'concepts' / 'concepts.json').write_text(json.dumps(INDEX))
        (self.root / 'docs' / 'concepts' / 'concept-c.html').write_text(MINIMAL)
        (self.root / '.design-dna').mkdir()
        (self.root / '.design-dna' / 'ledger.json').write_text(json.dumps([
            {'site': 'casa-teste', 'date': '2026-09-16', 'key': 'b', 'name': 'Distinct', 'vertical': 'restaurant', 'register': 'distinctive', 'shipped': True, 'dna': {}},
            {'site': 'casa-teste', 'date': '2026-09-16', 'key': 'c', 'name': 'Wild', 'vertical': 'restaurant', 'register': 'creative', 'shipped': False, 'dna': {}},
        ]))
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'Português'}, {'code': 'en', 'name': 'English'}]
        s.default_language = 'pt'
        s.save()

    def tearDown(self):
        self.tmp.cleanup()

    def run_cmd(self, *args):
        out = StringIO()
        with patch('djangopress.core.management.commands.promote_concept.Path.cwd', return_value=self.root), \
             patch.dict(os.environ, {'DJANGOPRESS_SITES_ROOT': self.tmp.name}), \
             patch('djangopress.core.management.commands.promote_concept.subprocess.run') as run:
            run.return_value.returncode = 0
            call_command('promote_concept', *args, '--packet', str(self.root / 'docs' / 'build-packet.json'), stdout=out)
        return json.loads(out.getvalue()), run

    def test_promote_swaps_status_and_ledger(self):
        rep, run = self.run_cmd('c')
        self.assertTrue(rep['ok'])
        self.assertTrue(Page.objects.filter(slug_i18n__pt='home').exists())
        index = {e['key']: e['status'] for e in json.loads((self.root / 'docs' / 'concepts' / 'concepts.json').read_text())}
        self.assertEqual(index, {'a': 'rejected', 'b': 'rejected', 'c': 'shipped'})
        ledger = {e['key']: e['shipped'] for e in json.loads((self.root / '.design-dna' / 'ledger.json').read_text())}
        self.assertEqual(ledger, {'b': False, 'c': True})
        run.assert_not_called()

    def test_publish_runs_sync_and_redeploy(self):
        rep, run = self.run_cmd('c', '--publish')
        cmds = [c.args[0] for c in run.call_args_list]
        self.assertEqual(cmds[0], ['railway', 'status'])
        self.assertIn('railway redeploy -y', cmds[1])
        self.assertTrue(rep['published'])
