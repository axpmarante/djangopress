"""Tests for the check_site management command."""

import json
from io import StringIO

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from djangopress.core.models import GlobalSection, MenuItem, Page, SiteSettings


VALID_HOME_HTML = """
<section data-section="hero" id="hero">
  <h1>Bem-vindo</h1>
  <a href="#contact">Contactos</a>
  <a href="/pt/sobre/">Sobre</a>
  <img src="/media/site_images/hero.jpg" alt="Sala">
</section>
<section data-section="contact" id="contact">
  <p>Ligue-nos</p>
</section>
"""

VALID_JSONLD = (
    '<script type="application/ld+json">'
    '{"@context": "https://schema.org", "@type": "LocalBusiness", '
    '"name": "Casa", "telephone": "+351 289 000 000", "address": "Rua Um, Faro"}'
    '</script>'
)


def make_valid_site():
    """Build the smallest site that passes every check. Returns the home page."""
    Page.objects.all().delete()
    MenuItem.objects.all().delete()
    s = SiteSettings.load()
    s.enabled_languages = [{'code': 'pt', 'name': 'Português'}]
    s.default_language = 'pt'
    s.gcs_folder = 'test-site'
    s.site_name_i18n = {'pt': 'Casa de Teste'}
    s.primary_color = '#c05b3e'
    s.secondary_color = '#3e6b73'
    s.background_color = '#f5f0e8'
    s.text_color = '#2b2520'
    s.custom_head_code = VALID_JSONLD
    home = Page.objects.create(
        title_i18n={'pt': 'Início'},
        slug_i18n={'pt': 'home'},
        html_content_i18n={'pt': VALID_HOME_HTML},
        meta_title_i18n={'pt': 'Casa de Teste'},
        meta_description_i18n={'pt': 'Descrição'},
        is_active=True,
        sort_order=0,
    )
    s.homepage = home
    s.save()
    for key, name, section_type in (
        ('main-header', 'Main Header', 'header'),
        ('main-footer', 'Main Footer', 'footer'),
    ):
        gs, _ = GlobalSection.objects.get_or_create(
            key=key, defaults={'name': name, 'section_type': section_type},
        )
        gs.html_template_i18n = {'pt': '<header><nav>x</nav></header>'}
        gs.is_active = True
        gs.save()
    MenuItem.objects.create(label_i18n={'pt': 'Início'}, page=home, is_active=True)
    return home


def run_checks(only=None):
    from djangopress.core.management.commands.check_site import SiteChecker
    return SiteChecker(only=only).run()


def check_names(failures):
    return sorted({f['check'] for f in failures})


class CheckSiteTestCase(TestCase):
    """SiteSettings.load() caches across tests; clear the cache on both sides
    so neither a previous test nor this one leaks a stale homepage_id into
    the next."""

    def setUp(self):
        cache.clear()
        super().setUp()

    def tearDown(self):
        cache.clear()
        super().tearDown()


class ValidSiteTest(CheckSiteTestCase):
    def test_valid_site_has_no_failures(self):
        make_valid_site()
        self.assertEqual(run_checks(), [])


class SettingsCheckTest(CheckSiteTestCase):
    def setUp(self):
        self.home = make_valid_site()

    def test_missing_homepage(self):
        s = SiteSettings.load()
        s.homepage = None
        s.save()
        self.assertIn('settings', check_names(run_checks(only=['settings'])))

    def test_template_default_colors(self):
        s = SiteSettings.load()
        s.primary_color = '#1E3A8A'
        s.secondary_color = '#64748B'
        s.background_color = '#FFFFFF'
        s.text_color = '#1F2937'
        s.save()
        failures = run_checks(only=['settings'])
        self.assertTrue(any('template default' in f['message'] for f in failures))

    def test_default_site_name(self):
        s = SiteSettings.load()
        s.site_name_i18n = {'pt': 'DjangoPress'}
        s.save()
        self.assertIn('settings', check_names(run_checks(only=['settings'])))


class PageHtmlCheckTest(CheckSiteTestCase):
    def setUp(self):
        self.home = make_valid_site()

    def _set_html(self, html):
        self.home.html_content_i18n = {'pt': html}
        self.home.save()

    def test_empty_html(self):
        self._set_html('')
        self.assertIn('page-html', check_names(run_checks()))

    def test_forbidden_tag(self):
        self._set_html('<section data-section="hero" id="hero"><nav>x</nav></section>')
        self.assertIn('forbidden-tag', check_names(run_checks()))

    def test_section_without_data_section(self):
        self._set_html('<section id="hero"><p>x</p></section>')
        self.assertIn('sections', check_names(run_checks()))

    def test_section_id_mismatch(self):
        self._set_html('<section data-section="hero" id="top"><p>x</p></section>')
        self.assertIn('sections', check_names(run_checks()))

    def test_duplicate_section(self):
        self._set_html(
            '<section data-section="hero" id="hero"><p>x</p></section>'
            '<section data-section="hero" id="hero"><p>y</p></section>'
        )
        self.assertIn('sections', check_names(run_checks()))

    def test_placeholder_image(self):
        self._set_html(
            '<section data-section="hero" id="hero">'
            '<img src="https://placehold.co/600x400" alt="x"></section>'
        )
        self.assertIn('images', check_names(run_checks()))

    def test_image_without_alt(self):
        self._set_html(
            '<section data-section="hero" id="hero"><img src="/media/a.jpg"></section>'
        )
        self.assertIn('images', check_names(run_checks()))

    def test_aria_hidden_image_with_alt(self):
        self._set_html(
            '<section data-section="hero" id="hero">'
            '<img src="/media/a.jpg" alt="dup" aria-hidden="true"></section>'
        )
        self.assertIn('images', check_names(run_checks()))

    def test_dangling_anchor(self):
        self._set_html(
            '<section data-section="hero" id="hero"><a href="#nowhere">x</a></section>'
        )
        self.assertIn('anchors', check_names(run_checks()))

    def test_inactive_page_is_skipped(self):
        Page.objects.create(
            title_i18n={'pt': 'Rascunho'}, slug_i18n={'pt': 'rascunho'},
            html_content_i18n={'pt': '<nav>bad</nav>'}, is_active=False,
        )
        self.assertNotIn('forbidden-tag', check_names(run_checks()))


class SeoShapeCheckTest(CheckSiteTestCase):
    def setUp(self):
        self.home = make_valid_site()

    def test_non_object_jsonld_reports_seo_failure(self):
        s = SiteSettings.load()
        s.custom_head_code = '<script type="application/ld+json">"hello"</script>'
        s.save()
        failures = run_checks(only=['seo'])
        self.assertTrue(any('expected an object or a list' in f['message'] for f in failures))

    def test_graph_single_object_is_checked(self):
        s = SiteSettings.load()
        s.custom_head_code = '<script type="application/ld+json">{"@context": "https://schema.org", "@graph": {"@type": "Restaurant", "name": "X"}}</script>'
        s.save()
        self.assertEqual(check_names(run_checks(only=['seo'])), ['seo'])


class LinksCheckTest(CheckSiteTestCase):
    def setUp(self):
        self.home = make_valid_site()

    def _set_html(self, html):
        self.home.html_content_i18n = {'pt': html}
        self.home.save()

    def test_unprefixed_internal_link_fails(self):
        self._set_html('<section data-section="hero" id="hero"><a href="/reservas/">x</a></section>')
        failures = run_checks(only=['links'])
        self.assertEqual(check_names(failures), ['links'])
        self.assertIn('/reservas/', failures[0]['message'])

    def test_prefixed_link_passes(self):
        self._set_html('<section data-section="hero" id="hero"><a href="/pt/reservas/">x</a><a href="/pt/#hero">y</a></section>')
        self.assertEqual(run_checks(only=['links']), [])

    def test_media_static_and_external_links_pass(self):
        self._set_html(
            '<section data-section="hero" id="hero">'
            '<a href="/media/menu.pdf">m</a><a href="/static/x.css">s</a>'
            '<a href="https://example.com/">e</a><a href="/">root</a></section>'
        )
        self.assertEqual(run_checks(only=['links']), [])

    def test_message_names_the_page_language(self):
        self.home.html_content_i18n = {
            'pt': VALID_HOME_HTML,
            'en': VALID_HOME_HTML.replace('/pt/sobre/', '/about/'),
        }
        self.home.save()
        failures = run_checks(only=['links'])
        self.assertEqual(len(failures), 1)
        self.assertIn('expected /en/', failures[0]['message'])

    def test_non_i18n_paths_pass(self):
        self._set_html(
            '<section data-section="hero" id="hero">'
            '<a href="/forms/x/">f</a><a href="/sitemap.xml">s</a>'
            '<a href="/robots.txt">r</a><a href="/django-admin/">a</a>'
            '</section>'
        )
        failures = run_checks(only=['links'])
        self.assertEqual(check_names(failures), [])


class HomeCheckTest(CheckSiteTestCase):
    def setUp(self):
        self.home = make_valid_site()

    def test_home_slug_must_be_home_in_every_language(self):
        self.home.slug_i18n = {'pt': 'home', 'en': 'inicio'}
        self.home.save()
        failures = run_checks(only=['home'])
        self.assertEqual(check_names(failures), ['home'])
        self.assertIn("'inicio'", failures[0]['message'])

    def test_homepage_fk_must_point_at_home(self):
        other = Page.objects.create(
            title_i18n={'pt': 'Outra'}, slug_i18n={'pt': 'outra'},
            html_content_i18n={'pt': VALID_HOME_HTML},
            meta_title_i18n={'pt': 'x'}, meta_description_i18n={'pt': 'y'}, is_active=True,
        )
        s = SiteSettings.load()
        s.homepage = other
        s.save()
        self.assertIn('home', check_names(run_checks(only=['home'])))

    def test_no_home_page(self):
        self.home.slug_i18n = {'pt': 'inicio'}
        self.home.save()
        self.assertIn('home', check_names(run_checks(only=['home'])))


class MetaCheckTest(CheckSiteTestCase):
    def test_missing_meta_description(self):
        home = make_valid_site()
        home.meta_description_i18n = {}
        home.save()
        self.assertEqual(check_names(run_checks(only=['meta'])), ['meta'])


class DomParityCheckTest(CheckSiteTestCase):
    def setUp(self):
        self.home = make_valid_site()

    def test_identical_structure_passes(self):
        en = VALID_HOME_HTML.replace('Bem-vindo', 'Welcome').replace('/pt/sobre/', '/en/about/')
        self.home.html_content_i18n = {'pt': VALID_HOME_HTML, 'en': en}
        self.home.save()
        self.assertEqual(run_checks(only=['dom-parity']), [])

    def test_extra_element_fails(self):
        en = VALID_HOME_HTML.replace('<p>Ligue-nos</p>', '<p>Call us</p><p>extra</p>')
        self.home.html_content_i18n = {'pt': VALID_HOME_HTML, 'en': en}
        self.home.save()
        failures = run_checks(only=['dom-parity'])
        self.assertEqual(check_names(failures), ['dom-parity'])
        self.assertIn('elements', failures[0]['message'])

    def test_changed_class_fails(self):
        en = VALID_HOME_HTML.replace('<h1>', '<h1 class="text-xl">')
        self.home.html_content_i18n = {'pt': VALID_HOME_HTML, 'en': en}
        self.home.save()
        self.assertEqual(check_names(run_checks(only=['dom-parity'])), ['dom-parity'])


class GlobalSectionCheckTest(CheckSiteTestCase):
    def test_inactive_footer_fails(self):
        make_valid_site()
        gs = GlobalSection.objects.get(key='main-footer')
        gs.is_active = False
        gs.save()
        failures = run_checks(only=['global-section'])
        self.assertEqual(check_names(failures), ['global-section'])
        self.assertIn('main-footer', failures[0]['message'])


class MenuCheckTest(CheckSiteTestCase):
    def test_no_menu_items_fails(self):
        make_valid_site()
        MenuItem.objects.all().delete()
        self.assertEqual(check_names(run_checks(only=['menu'])), ['menu'])

    def test_item_linking_inactive_page_fails(self):
        home = make_valid_site()
        home.is_active = False
        home.save()
        failures = run_checks(only=['menu'])
        self.assertEqual(check_names(failures), ['menu'])


class SeoCheckTest(CheckSiteTestCase):
    def setUp(self):
        make_valid_site()

    def _set_head(self, code):
        s = SiteSettings.load()
        s.custom_head_code = code
        s.save()

    def test_missing_jsonld_fails(self):
        self._set_head('')
        self.assertEqual(check_names(run_checks(only=['seo'])), ['seo'])

    def test_unparseable_jsonld_fails(self):
        self._set_head('<script type="application/ld+json">{not json</script>')
        failures = run_checks(only=['seo'])
        self.assertIn('does not parse', failures[0]['message'])

    def test_restaurant_missing_required_keys(self):
        self._set_head('<script type="application/ld+json">{"@type": "Restaurant", "name": "X"}</script>')
        failures = run_checks(only=['seo'])
        missing = {f['message'].split("'")[1] for f in failures}
        self.assertEqual(missing, {'telephone', 'address', 'geo', 'openingHoursSpecification', 'servesCuisine', 'priceRange'})

    def test_unknown_type_only_needs_to_parse(self):
        self._set_head('<script type="application/ld+json">{"@type": "WebSite", "name": "X"}</script>')
        self.assertEqual(run_checks(only=['seo']), [])


class CommandInterfaceTest(CheckSiteTestCase):
    def test_json_output_ok(self):
        make_valid_site()
        out = StringIO()
        call_command('check_site', '--json', stdout=out)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload, {'ok': True, 'failures': []})

    def test_failure_exits_1_with_named_lines(self):
        make_valid_site()
        MenuItem.objects.all().delete()
        out = StringIO()
        with self.assertRaises(SystemExit) as ctx:
            call_command('check_site', stdout=out)
        self.assertEqual(ctx.exception.code, 1)
        text = out.getvalue()
        self.assertIn('FAIL — 1 problem(s):', text)
        self.assertIn('[menu] no active MenuItems', text)

    def test_only_restricts_checks(self):
        make_valid_site()
        MenuItem.objects.all().delete()
        out = StringIO()
        call_command('check_site', '--only', 'settings,seo', '--json', stdout=out)
        self.assertTrue(json.loads(out.getvalue())['ok'])

    def test_unknown_check_name(self):
        make_valid_site()
        with self.assertRaises(CommandError):
            call_command('check_site', '--only', 'nope')
