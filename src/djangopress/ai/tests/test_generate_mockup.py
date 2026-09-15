"""Tests for the generate_mockup command — fake client, no network."""

import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase

from .test_openai_images import FakeClient, PNG_1PX, fake_response


class GenerateMockupTest(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.prompt = self.root / 'prompt.md'
        self.prompt.write_text('A desktop website hero section.')
        self.out = self.root / 'mockups' / '01-hero.png'
        self.costs = self.root / 'mockups' / 'costs.json'

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *args, client=None, **kw):
        out = StringIO()
        with patch('djangopress.ai.management.commands.generate_mockup.get_client', return_value=client or FakeClient()):
            call_command('generate_mockup', *args, '--costs-file', str(self.costs), stdout=out, **kw)
        return out.getvalue()

    def test_generates_and_records_cost(self):
        text = self._run('--prompt-file', str(self.prompt), '--out', str(self.out),
                         '--model', 'flare', '--size', '1280x3840', '--quality', 'medium')
        self.assertEqual(self.out.read_bytes(), PNG_1PX)
        data = json.loads(self.costs.read_text())
        self.assertEqual(len(data['records']), 1)
        rec = data['records'][0]
        self.assertEqual(rec['model'], 'gpt-image-2.5-flare')
        self.assertEqual(rec['size'], '1280x3840')
        self.assertEqual(rec['quality'], 'medium')
        self.assertEqual(rec['image_out'], 1760)
        self.assertAlmostEqual(data['total_usd'], rec['cost_usd'], places=8)
        self.assertIn('wrote', text)
        self.assertIn('$', text)

    def test_refs_use_edit_endpoint(self):
        ref = self.root / 'master.png'
        ref.write_bytes(PNG_1PX)
        client = FakeClient()
        self._run('--prompt-file', str(self.prompt), '--out', str(self.out),
                  '--size', '1920x1088', '--ref', str(ref), client=client)
        kind, kwargs = client.images.calls[0]
        self.assertEqual(kind, 'edit')
        self.assertNotIn('input_fidelity', kwargs)
        rec = json.loads(self.costs.read_text())['records'][0]
        self.assertEqual(rec['refs'], [str(ref)])

    def test_inline_prompt(self):
        client = FakeClient()
        self._run('--prompt', 'inline text', '--out', str(self.out), '--size', '1024x1024', client=client)
        self.assertEqual(client.images.calls[0][1]['prompt'], 'inline text')

    def test_dry_run_makes_no_call_and_writes_nothing(self):
        client = FakeClient()
        text = self._run('--prompt-file', str(self.prompt), '--out', str(self.out),
                         '--size', '1536x1024', '--dry-run', client=client)
        self.assertEqual(client.images.calls, [])
        self.assertFalse(self.out.exists())
        self.assertFalse(self.costs.exists())
        self.assertIn('gpt-image-2.5-sunburst', text)
        self.assertIn('1536x1024', text)

    def test_invalid_size_exits_before_calling(self):
        client = FakeClient()
        with self.assertRaises(SystemExit) as ctx:
            self._run('--prompt-file', str(self.prompt), '--out', str(self.out), '--size', '1920x1080', client=client)
        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(client.images.calls, [])

    def test_budget_refuses_when_total_would_exceed(self):
        # First call records ~$0.053 (97 text + 1760 out at published rates).
        self._run('--prompt-file', str(self.prompt), '--out', str(self.out), '--size', '1024x1024')
        second = self.root / 'mockups' / '02.png'
        client = FakeClient()
        with self.assertRaises(SystemExit):
            self._run('--prompt-file', str(self.prompt), '--out', str(second), '--size', '1024x1024',
                      '--budget', '0.06', client=client)
        self.assertEqual(client.images.calls, [])
        self.assertFalse(second.exists())

    def test_budget_allows_when_under(self):
        second = self.root / 'mockups' / '02.png'
        self._run('--prompt-file', str(self.prompt), '--out', str(second), '--size', '1024x1024', '--budget', '5')
        self.assertTrue(second.exists())

    def test_api_error_exits_1_with_message(self):
        APIStatusError = type('APIStatusError', (Exception,), {})
        err = APIStatusError('safety'); err.status_code = 400
        client = FakeClient(raises=[err])
        with self.assertRaises(SystemExit) as ctx:
            self._run('--prompt-file', str(self.prompt), '--out', str(self.out), '--size', '1024x1024', client=client)
        self.assertEqual(ctx.exception.code, 1)
        self.assertFalse(self.out.exists())

    def test_corrupt_costs_file_is_a_hard_error(self):
        self.costs.parent.mkdir(parents=True, exist_ok=True)
        self.costs.write_text('{not json')
        client = FakeClient()
        with self.assertRaises(SystemExit) as ctx:
            self._run('--prompt-file', str(self.prompt), '--out', str(self.out), '--size', '1024x1024', client=client)
        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(client.images.calls, [])
        self.assertEqual(self.costs.read_text(), '{not json')

    def test_costs_file_with_wrong_shape_is_a_hard_error(self):
        self.costs.parent.mkdir(parents=True, exist_ok=True)
        self.costs.write_text('[]')
        client = FakeClient()
        with self.assertRaises(SystemExit) as ctx:
            self._run('--prompt-file', str(self.prompt), '--out', str(self.out), '--size', '1024x1024', client=client)
        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(client.images.calls, [])
        self.assertEqual(self.costs.read_text(), '[]')

    def test_costs_written_atomically_leaves_no_tmp(self):
        self._run('--prompt-file', str(self.prompt), '--out', str(self.out), '--size', '1024x1024')
        self.assertTrue(self.costs.exists())
        self.assertFalse(self.costs.with_suffix('.json.tmp').exists())
