"""Tests for the check_site management command."""

import json

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


class ValidSiteTest(TestCase):
    def test_valid_site_has_no_failures(self):
        make_valid_site()
        self.assertEqual(run_checks(), [])


class SettingsCheckTest(TestCase):
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


class PageHtmlCheckTest(TestCase):
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


class SeoShapeCheckTest(TestCase):
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
