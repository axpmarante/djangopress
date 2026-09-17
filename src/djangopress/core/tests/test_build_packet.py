"""Tests for build_packet / build_prepare (Task 2)."""

import json
import tempfile
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from djangopress.core.build.briefing import parse_briefing
from djangopress.core.build.packet import build_packet, detect_vertical
from djangopress.core.models import Page, SiteImage, SiteSettings
from djangopress.core.tests.test_build_briefing import SAMPLE

AUDIT = """# CHECKin Faro — Site Audit

## Image Inventory

| Group | Count | Largest width | Source | Example URL |
|---|---|---|---|---|
| Dishes (pro, 2021) | 6 | 2048 (DSC-7371 2048×1365) | old site | https://example.com/dish.jpg |
| Exterior | 0 | — | — | — |
"""

MENU = {"pt": {"Entradas": [{"title": "Couvert", "desc": "", "price": "3.30", "photo": ""}]}}

# 1x1 PNG
PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
       b'\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82')


class DetectVerticalTest(TestCase):

    def test_restaurant_from_business_prose(self):
        self.assertEqual(detect_vertical(parse_briefing(SAMPLE)), 'restaurant')

    def test_default_is_services(self):
        b = parse_briefing(SAMPLE.replace('Cozinha de autor algarvia, à carta, para partilhar. Chef Leonel Pereira.', 'Consultoria.'))
        b.notes = {}
        self.assertEqual(detect_vertical(b), 'services')

    def test_notes_override(self):
        b = parse_briefing(SAMPLE)
        b.notes['vertical'] = 'legal'
        self.assertEqual(detect_vertical(b), 'legal')


class BuildPacketTest(TestCase):

    def test_shape(self):
        b = parse_briefing(SAMPLE)
        packet = build_packet(
            b, site_slug='checkin-faro',
            image_map={'dishes-1': {'url': 'https://s/dish.jpg', 'width': 2048, 'alt': 'Dishes'}},
            menus={'briefings/checkin-faro-menu.json': MENU},
        )
        self.assertEqual(packet['site']['lang_prefix'], '/pt')
        self.assertEqual(packet['site']['languages'], ['pt', 'en'])
        self.assertEqual(packet['business']['type'], 'restaurant')
        self.assertEqual(packet['business']['jsonld_type'], 'Restaurant')
        self.assertEqual(packet['facts']['phone'], '+351 289 000 000')
        req = packet['content']['home']['required']
        self.assertEqual(req[1]['href'], '/reservas/')
        menu_item = next(i for i in req if i['kind'] == 'Menu')
        self.assertEqual(menu_item['items'], [{'name': 'Couvert', 'price': '3.30', 'category': 'Entradas'}])
        self.assertEqual(packet['images']['map']['dishes-1']['width'], 2048)
        self.assertEqual(packet['design_constraints']['brand_colors'], ['#C51B17', '#40308A'])
        self.assertIn('editorial', packet['families'])

    def test_form_and_notes(self):
        b = parse_briefing(SAMPLE)
        packet = build_packet(b, site_slug='checkin-faro', image_map={}, menus={})
        self.assertEqual(packet['notes'], {'jsonld': 'Restaurant', 'cuisine': 'Algarvia', 'price range': '€€€'})
        self.assertEqual(packet['form'], {
            'slug': 'contact', 'action': '/forms/contact/submit/',
            'fields': ['name', 'email', 'message'], 'service_options': [],
        })

        sample_with_fields = SAMPLE.replace('price range: €€€', 'price range: €€€\nform fields: nome, telefone, email, mensagem')
        b2 = parse_briefing(sample_with_fields)
        packet2 = build_packet(b2, site_slug='checkin-faro', image_map={}, menus={})
        self.assertEqual(packet2['form']['fields'], ['nome', 'telefone', 'email', 'mensagem'])


class BuildPrepareCommandTest(TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'briefings').mkdir()
        (self.root / 'briefings' / 'checkin-faro.md').write_text(SAMPLE)
        (self.root / 'briefings' / 'checkin-faro-audit.md').write_text(AUDIT)
        (self.root / 'briefings' / 'checkin-faro-menu.json').write_text(json.dumps(MENU))
        Page.objects.all().delete()
        SiteImage.objects.all().delete()

    def tearDown(self):
        self.tmp.cleanup()

    def run_cmd(self, *extra):
        out = StringIO()
        storages = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
        with override_settings(MEDIA_ROOT=str(self.root / 'media'), STORAGES=storages), \
             patch('djangopress.core.build.packet.urlopen', return_value=BytesIO(PNG)), \
             patch('djangopress.core.management.commands.build_prepare.Path.cwd', return_value=self.root):
            call_command('build_prepare', str(self.root / 'briefings' / 'checkin-faro.md'), *extra, stdout=out)
        return json.loads(out.getvalue())

    def test_writes_settings_packet_privacy_and_images(self):
        summary = self.run_cmd()
        s = SiteSettings.load()
        self.assertEqual(s.default_language, 'pt')
        self.assertEqual([l['code'] for l in s.enabled_languages], ['pt', 'en'])
        self.assertEqual(s.site_name_i18n, {'pt': 'CHECKin Faro', 'en': 'CHECKin Faro'})
        self.assertEqual(s.contact_phone, '+351 289 000 000')
        self.assertEqual(s.instagram_url, 'https://instagram.com/checkinfaro')
        self.assertTrue(s.project_briefing.startswith('Cozinha de autor'))
        self.assertTrue(Page.objects.filter(slug_i18n__pt='politica-de-privacidade').exists())
        img = SiteImage.objects.get(key='dishes-pro-2021-1')
        self.assertTrue(img.image.name)
        packet = json.loads((self.root / 'docs' / 'build-packet.json').read_text())
        self.assertEqual(packet['images']['map']['dishes-pro-2021-1']['width'], 2048)
        self.assertEqual(summary['required_items'], 4)

    def test_open_questions_block(self):
        (self.root / 'briefings' / 'checkin-faro.md').write_text(
            SAMPLE.replace('## Business', '## Open Questions\n1. x?\n\n## Business'))
        with self.assertRaises(SystemExit):
            self.run_cmd()

    def test_no_download_skips_images(self):
        self.run_cmd('--no-download')
        self.assertFalse(SiteImage.objects.exists())
