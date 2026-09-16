"""Tests for the probe and build_verify (Task 8)."""

import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from djangopress.core.build.adapter import adapt
from djangopress.core.build.importer import cta_texts_from, import_result
from djangopress.core.build.probe import run_probe
from djangopress.core.build.verify import BLOCKING_KINDS, is_residue, screen_file, verify_live
from djangopress.core.models import Page, SiteSettings
from djangopress.core.tests.test_build_importer import MINIMAL, PACKET

BROKEN = """<!DOCTYPE html><html><head><style>body{margin:0}</style></head><body>
<header><a href="#" style="color:#fff">Home</a></header>
<main>
<section data-section="hero" id="hero" style="height:600px;background:#fff"><h1>Hi</h1><div style="width:2000px;height:10px"></div></section>
<section data-section="empty" id="empty"></section>
<section data-section="text" id="text" style="height:300px"><p>Body</p></section>
<section data-section="reveal" id="reveal" style="height:300px"><p style="opacity:0">Hidden until scroll</p></section>
</main>
<footer style="height:200px">footer</footer>
<div style="position:fixed;bottom:0;left:0;right:0;height:80px;background:#000"></div>
</body></html>"""


def playwright_available():
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


class ProbeTest(TestCase):

    def setUp(self):
        if not playwright_available():
            self.skipTest('playwright not installed')

    def test_detects_known_defects(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'broken.html'
            f.write_text(BROKEN)
            try:
                out = run_probe(f.as_uri(), widths=(390,), cta_texts=['Reservar'])
            except Exception as exc:  # chromium missing
                self.skipTest(f'chromium unavailable: {exc}')
        kinds = {d['kind'] for d in out['defects']}
        self.assertTrue(out['available'])
        self.assertIn('overflow', kinds)
        self.assertIn('empty-section', kinds)
        self.assertIn('covered-footer', kinds)
        self.assertIn('cta-below-fold', kinds)
        self.assertIn('header-contrast', kinds)
        self.assertIn('hidden-content', kinds)
        self.assertEqual(next(d for d in out['defects'] if d['kind'] == 'hidden-content')['section'], 'reveal')
        self.assertEqual(next(d for d in out['defects'] if d['kind'] == 'overflow')['section'], 'hero')

    def test_clean_page_and_screenshot(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'ok.html'
            f.write_text(MINIMAL)
            shot = Path(d) / 'home-390.png'
            try:
                out = run_probe(f.as_uri(), widths=(390,), screenshot_path=shot)
            except Exception as exc:
                self.skipTest(f'chromium unavailable: {exc}')
            self.assertTrue(shot.exists())
        blocking = [x for x in out['defects'] if x['kind'] in BLOCKING_KINDS]
        self.assertEqual(blocking, [])


class ResidueTest(TestCase):

    def test_residue(self):
        self.assertTrue(is_residue({'check': 'images', 'message': 'page 1 [pt]: unresolved placeholder https://placehold.co/x'}))
        self.assertTrue(is_residue({'check': 'images', 'message': 'page 1 [pt]: leftover data-image-* attribute on x'}))
        self.assertFalse(is_residue({'check': 'images', 'message': 'page 1 [pt]: <img> without alt (x)'}))
        self.assertFalse(is_residue({'check': 'links', 'message': 'x'}))


FAKE_PROBE_OK = lambda url, **kw: {'available': True, 'defects': []}  # noqa: E731
FAKE_PROBE_BAD = lambda url, **kw: {'available': True, 'defects': [{'kind': 'overflow', 'section': 'menu', 'detail': 'x', 'width': 390}]}  # noqa: E731
FAKE_PROBE_NONE = lambda url, **kw: {'available': False, 'defects': []}  # noqa: E731


class ScreenFileTest(TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = Path(self.tmp.name) / 'concept-b.html'
        self.f.write_text(MINIMAL)

    def tearDown(self):
        self.tmp.cleanup()

    def test_clean(self):
        r = screen_file(self.f, PACKET, probe=FAKE_PROBE_OK)
        self.assertEqual(r['key'], 'b')
        self.assertEqual(r['hard_errors'], [])
        self.assertEqual(r['content_missing'], [])
        self.assertTrue(r['clean'])

    def test_blocking_defect(self):
        r = screen_file(self.f, PACKET, probe=FAKE_PROBE_BAD)
        self.assertFalse(r['clean'])

    def test_truncated_is_hard_error(self):
        self.f.write_text(MINIMAL[: MINIMAL.index('<footer')])
        r = screen_file(self.f, PACKET, probe=FAKE_PROBE_OK)
        self.assertTrue(r['hard_errors'])
        self.assertFalse(r['clean'])

    def test_content_missing_blocks(self):
        self.f.write_text(MINIMAL.replace('Guia Michelin 2024', 'x'))
        r = screen_file(self.f, PACKET, probe=FAKE_PROBE_OK)
        self.assertEqual([m['id'] for m in r['content_missing']], ['home-3'])
        self.assertFalse(r['clean'])


class VerifyLiveTest(TestCase):

    def setUp(self):
        Page.objects.all().delete()
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'Português'}, {'code': 'en', 'name': 'English'}]
        s.default_language = 'pt'
        s.gcs_folder = 'casa-teste'
        s.site_name_i18n = {'pt': 'Casa Teste', 'en': 'Casa Teste'}
        s.save()
        result = adapt(MINIMAL, lang='pt', languages=['pt', 'en'], image_map=PACKET['images']['map'],
                       cta_texts=cta_texts_from(PACKET), contact_phone='+351 289 000 000')
        import_result(result, packet=PACKET)

    def test_verify_live_clean_with_residue(self):
        with patch('djangopress.core.build.verify.ensure_server', return_value=None):
            r = verify_live(PACKET, port=8999, probe=FAKE_PROBE_OK, screenshot=False)
        self.assertEqual(r['check_site'], [])
        self.assertGreater(r['residue'], 0)
        self.assertEqual(r['content_missing'], [])
        self.assertTrue(r['clean'])

    def test_probe_unavailable_reported(self):
        with patch('djangopress.core.build.verify.ensure_server', return_value=None):
            r = verify_live(PACKET, port=8999, probe=FAKE_PROBE_NONE, screenshot=False)
        self.assertFalse(r['probe']['available'])
        self.assertTrue(r['clean'])


class BuildVerifyCommandTest(TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'docs' / 'concepts').mkdir(parents=True)
        (self.root / 'docs' / 'build-packet.json').write_text(json.dumps(PACKET))
        (self.root / 'docs' / 'concepts' / 'concept-a.html').write_text(MINIMAL)
        (self.root / 'docs' / 'concepts' / 'concept-b.html').write_text(MINIMAL[: MINIMAL.index('<footer')])

    def tearDown(self):
        self.tmp.cleanup()

    def test_files_mode_writes_screen_json_and_exits_1(self):
        out = StringIO()
        with patch('djangopress.core.build.verify.run_probe', FAKE_PROBE_OK), \
             patch('djangopress.core.management.commands.build_verify.Path.cwd', return_value=self.root):
            with self.assertRaises(SystemExit) as cm:
                call_command('build_verify', '--files', str(self.root / 'docs/concepts/concept-a.html'),
                             str(self.root / 'docs/concepts/concept-b.html'),
                             '--packet', str(self.root / 'docs/build-packet.json'), stdout=out)
        self.assertEqual(cm.exception.code, 1)
        screen = json.loads((self.root / 'docs' / 'concepts' / 'screen.json').read_text())
        self.assertEqual([(s['key'], s['clean']) for s in screen], [('a', True), ('b', False)])
