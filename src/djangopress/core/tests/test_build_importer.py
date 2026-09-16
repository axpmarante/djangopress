"""Tests for JSON-LD, the importer and import_concept (Task 6)."""

import copy
import json
import tempfile
from io import StringIO
from pathlib import Path

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase

from djangopress.core.build.adapter import adapt
from djangopress.core.build.importer import cta_texts_from, import_as_page, import_result
from djangopress.core.build.jsonld import build_jsonld, geo_from_maps_url, parse_hours_line
from djangopress.core.models import GlobalSection, MenuItem, Page, SiteSettings

FIXTURES = Path(__file__).parent / 'fixtures'
MINIMAL = (FIXTURES / 'concept-minimal.html').read_text()

PACKET = {
    'site': {'slug': 'casa-teste', 'name': 'Casa Teste', 'default_language': 'pt', 'default_language_name': 'Português',
             'languages': ['pt', 'en'], 'lang_prefix': '/pt'},
    'business': {'type': 'restaurant', 'jsonld_type': 'Restaurant', 'specialization': 'x', 'positioning': 'Cozinha de autor algarvia.',
                 'prose': 'Cozinha de autor algarvia.', 'cuisine': 'Algarvia', 'price_range': '€€€'},
    'families': ['editorial'],
    'facts': {'phone': '+351 289 000 000', 'email': 'geral@casateste.pt', 'address': 'Rua do Castelo 1, Faro',
              'maps_url': 'https://www.google.com/maps/place/x/@37.0146,-7.935,17z', 'hours': ['Terça a Sábado: 19:00–23:00', 'Domingo e Segunda: encerrado'],
              'social': {'instagram': 'https://instagram.com/casateste'}},
    'pages': [{'name': 'Home', 'slug': 'home', 'description': ''}],
    'content': {'home': {'required': [
        {'id': 'home-1', 'kind': 'Message', 'text': 'Cozinha de autor algarvia', 'keywords': ['autor', 'algarvia']},
        {'id': 'home-2', 'kind': 'CTA', 'text': 'Reservar mesa', 'href': '/reservas/'},
        {'id': 'home-3', 'kind': 'Proof', 'text': 'Guia Michelin 2024'},
        {'id': 'home-4', 'kind': 'Menu', 'text': 'menu', 'items': [{'name': 'Couvert', 'price': '3.30', 'category': 'Entradas'}]},
    ], 'optional': []}},
    'images': {'strategy': 'reuse existing', 'map': {'dish-1': {'url': 'https://example.com/dish.jpg', 'width': 2048, 'alt': 'Prato'}}, 'constraints': {}},
    'design_constraints': {'brand_colors': [], 'logo': None, 'avoid': [], 'references': [], 'image_max_widths': {}},
    'header': '', 'footer': '',
}


class JsonLdTest(TestCase):

    def test_hours_range(self):
        specs = parse_hours_line('Terça a Sábado: 19:00–23:00')
        self.assertEqual(specs[0]['dayOfWeek'], ['Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'])
        self.assertEqual((specs[0]['opens'], specs[0]['closes']), ('19:00', '23:00'))

    def test_hours_two_ranges_and_list(self):
        specs = parse_hours_line('Seg e Qua: 12h00-15h00, 19h00-23h00')
        self.assertEqual(len(specs), 2)
        self.assertEqual(specs[0]['dayOfWeek'], ['Monday', 'Wednesday'])
        self.assertEqual(specs[1]['opens'], '19:00')

    def test_closed_line_gives_nothing(self):
        self.assertEqual(parse_hours_line('Domingo e Segunda: encerrado'), [])

    def test_hours_dashed_range(self):
        specs = parse_hours_line('Ter–Sáb: 19:00–23:00')
        self.assertEqual(specs[0]['dayOfWeek'], ['Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'])
        self.assertEqual((specs[0]['opens'], specs[0]['closes']), ('19:00', '23:00'))
        specs2 = parse_hours_line('Seg-Sex 09:00–18:00')
        self.assertEqual(specs2[0]['dayOfWeek'], ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'])
        self.assertEqual((specs2[0]['opens'], specs2[0]['closes']), ('09:00', '18:00'))

    def test_unparseable_with_time_keeps_description(self):
        specs = parse_hours_line('Todos os dias exceto feriados: 10:00–18:00')
        self.assertEqual(specs[0]['opens'], '10:00')
        self.assertIn('description', specs[0])

    def test_geo(self):
        self.assertEqual(geo_from_maps_url('https://www.google.com/maps/place/x/@37.0146,-7.935,17z'), {'@type': 'GeoCoordinates', 'latitude': 37.0146, 'longitude': -7.935})
        self.assertEqual(geo_from_maps_url('https://maps.google.com/?q=37.01,-7.93')['latitude'], 37.01)
        self.assertIsNone(geo_from_maps_url('https://goo.gl/maps/abc'))

    def test_restaurant_block(self):
        d = build_jsonld(PACKET)
        self.assertEqual(d['@type'], 'Restaurant')
        self.assertEqual(d['servesCuisine'], 'Algarvia')
        self.assertEqual(d['priceRange'], '€€€')
        self.assertEqual(d['geo']['latitude'], 37.0146)
        self.assertEqual(d['image'], 'https://example.com/dish.jpg')
        self.assertEqual(d['sameAs'], ['https://instagram.com/casateste'])
        self.assertEqual(len(d['openingHoursSpecification']), 1)


class ImportResultTest(TestCase):
    """SiteSettings.load() caches across tests; clear the cache on both sides so
    neither a previous test nor this one leaks a stale homepage_id into the next
    (same reasoning as CheckSiteTestCase in test_check_site.py)."""

    def setUp(self):
        cache.clear()
        Page.objects.all().delete()
        MenuItem.objects.all().delete()
        GlobalSection.objects.all().delete()
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'Português'}, {'code': 'en', 'name': 'English'}]
        s.default_language = 'pt'
        s.gcs_folder = 'casa-teste'
        s.site_name_i18n = {'pt': 'Casa Teste', 'en': 'Casa Teste'}
        s.save()
        self.result = adapt(MINIMAL, lang='pt', languages=['pt', 'en'], image_map=PACKET['images']['map'],
                            cta_texts=cta_texts_from(PACKET), contact_phone='+351 289 000 000')

    def tearDown(self):
        cache.clear()

    def test_cta_texts(self):
        self.assertEqual(cta_texts_from(PACKET), ['Reservar mesa'])

    def test_import_creates_everything(self):
        out = import_result(self.result, packet=PACKET, set_home=True)
        home = Page.objects.get(slug_i18n__pt='home')
        self.assertEqual(out['page_id'], home.id)
        self.assertIn('data-section="hero"', home.html_content_i18n['pt'])
        self.assertEqual(home.meta_title_i18n['pt'], 'Casa Teste — Início')
        self.assertEqual(list(home.html_content_i18n.keys()), ['pt'])
        s = SiteSettings.load()
        self.assertEqual(s.homepage_id, home.id)
        self.assertIn('tailwind.config', s.custom_head_code)
        self.assertIn('application/ld+json', s.custom_head_code)
        self.assertEqual(s.heading_font, 'Lora')
        self.assertEqual(s.primary_color, '#c05b3e')
        self.assertEqual(s.container_width, '6xl')
        header = GlobalSection.objects.get(key='main-header')
        self.assertTrue(header.is_active)
        self.assertIn("{% url 'set_language' %}", header.html_template_i18n['pt'])
        self.assertEqual(GlobalSection.objects.get(key='main-footer').section_type, 'footer')
        self.assertEqual(MenuItem.objects.count(), 4)
        self.assertEqual(MenuItem.objects.order_by('sort_order').first().label_i18n, {'pt': 'Casa Teste'})

    def test_reimport_versions_and_does_not_duplicate(self):
        import_result(self.result, packet=PACKET)
        import_result(self.result, packet=PACKET, change_summary='again')
        self.assertEqual(Page.objects.filter(slug_i18n__pt='home').count(), 1)
        home = Page.objects.get(slug_i18n__pt='home')
        self.assertEqual(home.versions.count(), 1)
        self.assertEqual(GlobalSection.objects.get(key='main-header').versions.count(), 1)
        self.assertEqual(MenuItem.objects.count(), 4)

    def test_reimport_with_changed_content_versions_once(self):
        import_result(self.result, packet=PACKET)
        home = Page.objects.get(slug_i18n__pt='home')
        self.assertEqual(home.versions.count(), 1)
        changed_result = copy.copy(self.result)
        changed_result.meta_title = 'Nova Manchete'
        import_result(changed_result, packet=PACKET, change_summary='meta title update')
        home.refresh_from_db()
        self.assertEqual(home.versions.count(), 2)
        self.assertEqual(home.meta_title_i18n['pt'], 'Nova Manchete')

    def test_import_as_page_reimport_does_not_duplicate_versions(self):
        import_as_page(self.result, packet=PACKET, slug='homepage-v2')
        import_as_page(self.result, packet=PACKET, slug='homepage-v2')
        page = Page.objects.get(slug_i18n__pt='homepage-v2')
        self.assertEqual(page.versions.count(), 1)
        self.assertEqual(Page.objects.filter(slug_i18n__pt='homepage-v2').count(), 1)

    def test_import_as_page_is_scoped(self):
        import_result(self.result, packet=PACKET)
        header_before = GlobalSection.objects.get(key='main-header').html_template_i18n['pt']
        out = import_as_page(self.result, packet=PACKET, slug='homepage-v2')
        page = Page.objects.get(slug_i18n__pt='homepage-v2')
        self.assertEqual(out['page_id'], page.id)
        html = page.html_content_i18n['pt']
        self.assertTrue(html.startswith('<section'))
        self.assertIn('fonts.googleapis.com/css2?family=Lora', html)
        self.assertIn('tailwind.config', html)
        self.assertIn('body.bg-white', html)
        self.assertNotIn('{{', html)
        self.assertEqual(GlobalSection.objects.get(key='main-header').html_template_i18n['pt'], header_before)
        self.assertEqual(SiteSettings.load().homepage_id, Page.objects.get(slug_i18n__pt='home').id)
        self.assertEqual(MenuItem.objects.count(), 4)
        self.assertFalse(MenuItem.objects.filter(url__contains='homepage-v2').exists())

    def test_check_site_residue_is_images_only(self):
        import_result(self.result, packet=PACKET)
        out = StringIO()
        try:
            call_command('check_site', json=True, stdout=out)
        except SystemExit:
            pass
        failures = json.loads(out.getvalue())['failures']
        self.assertEqual({f['check'] for f in failures}, {'images'}, failures)


class ImportConceptCommandTest(TestCase):

    def setUp(self):
        cache.clear()
        Page.objects.all().delete()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'docs' / 'concepts').mkdir(parents=True)
        (self.root / 'docs' / 'build-packet.json').write_text(json.dumps(PACKET))
        (self.root / 'docs' / 'concepts' / 'concept-b.html').write_text(MINIMAL)
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'Português'}, {'code': 'en', 'name': 'English'}]
        s.default_language = 'pt'
        s.save()

    def tearDown(self):
        cache.clear()
        self.tmp.cleanup()

    def run_cmd(self, *args):
        out = StringIO()
        call_command('import_concept', str(self.root / 'docs' / 'concepts' / 'concept-b.html'),
                     '--packet', str(self.root / 'docs' / 'build-packet.json'), *args, stdout=out)
        return json.loads(out.getvalue())

    def test_dry_run_writes_nothing(self):
        rep = self.run_cmd('--dry-run')
        self.assertTrue(rep['ok'])
        self.assertEqual(rep['sections'], ['hero', 'menu', 'contact'])
        self.assertFalse(Page.objects.filter(slug_i18n__pt='home').exists())

    def test_import_and_report_file(self):
        rep = self.run_cmd('--home')
        self.assertTrue(rep['ok'])
        self.assertTrue(Page.objects.filter(slug_i18n__pt='home').exists())
        self.assertTrue((self.root / 'docs' / 'concepts' / 'import-b.json').exists())

    def test_as_page_command(self):
        rep = self.run_cmd('--as-page', 'homepage-v3')
        self.assertTrue(rep['ok'])
        self.assertTrue(Page.objects.filter(slug_i18n__pt='homepage-v3').exists())
        self.assertFalse(Page.objects.filter(slug_i18n__pt='home').exists())

    def test_truncated_exits_1(self):
        (self.root / 'docs' / 'concepts' / 'concept-b.html').write_text(MINIMAL[: MINIMAL.index('<footer')])
        with self.assertRaises(SystemExit):
            self.run_cmd('--home')
        self.assertFalse(Page.objects.filter(slug_i18n__pt='home').exists())

    def test_home_import_marks_index(self):
        concepts_json = self.root / 'docs' / 'concepts' / 'concepts.json'
        concepts_json.write_text(json.dumps([
            {'key': 'a', 'status': 'pending'},
            {'key': 'b', 'status': 'pending'},
            {'key': 'c', 'status': 'pending'},
        ]))
        self.run_cmd('--home')
        index = json.loads(concepts_json.read_text())
        statuses = {e['key']: e['status'] for e in index}
        self.assertEqual(statuses, {'a': 'pending', 'b': 'shipped', 'c': 'pending'})
