"""Tests for core.services.global_sections — GlobalSectionService."""

from django.test import TestCase
from core.models import GlobalSection, SiteSettings
from core.services.global_sections import GlobalSectionService


class GlobalSectionServiceGetTest(TestCase):

    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.section = GlobalSection.objects.create(
            key='main-header',
            name='Main Header',
            section_type='header',
            html_template_i18n={
                'pt': '<header><nav>Menu PT</nav></header>',
                'en': '<header><nav>Menu EN</nav></header>',
            },
            is_active=True,
        )

    def test_get_existing(self):
        result = GlobalSectionService.get('main-header')
        self.assertTrue(result['success'])
        self.assertEqual(result['section'].id, self.section.id)
        self.assertEqual(result['section'].key, 'main-header')

    def test_get_not_found(self):
        result = GlobalSectionService.get('nonexistent')
        self.assertFalse(result['success'])
        self.assertIn('not found', result['error'])


class GlobalSectionServiceGetHtmlTest(TestCase):

    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.section = GlobalSection.objects.create(
            key='main-footer',
            name='Main Footer',
            section_type='footer',
            html_template_i18n={
                'pt': '<footer><p>Rodape PT</p></footer>',
                'en': '<footer><p>Footer EN</p></footer>',
            },
            is_active=True,
        )

    def test_get_html_default_lang(self):
        result = GlobalSectionService.get_html('main-footer')
        self.assertTrue(result['success'])
        self.assertEqual(result['language'], 'pt')
        self.assertIn('Rodape PT', result['html'])

    def test_get_html_specific_lang(self):
        result = GlobalSectionService.get_html('main-footer', lang='en')
        self.assertTrue(result['success'])
        self.assertEqual(result['language'], 'en')
        self.assertIn('Footer EN', result['html'])

    def test_get_html_fallback_to_first_available(self):
        """When requested language is missing, fall back to first available."""
        result = GlobalSectionService.get_html('main-footer', lang='fr')
        self.assertTrue(result['success'])
        # Falls back to first available language (pt)
        self.assertIn('Rodape PT', result['html'])

    def test_get_html_not_found(self):
        result = GlobalSectionService.get_html('nonexistent')
        self.assertFalse(result['success'])
        self.assertIn('not found', result['error'])

    def test_get_html_empty_i18n(self):
        """Section with empty html_template_i18n returns empty string."""
        GlobalSection.objects.create(
            key='empty-section',
            name='Empty',
            section_type='custom',
            html_template_i18n={},
            is_active=True,
        )
        result = GlobalSectionService.get_html('empty-section')
        self.assertTrue(result['success'])
        self.assertEqual(result['html'], '')


class GlobalSectionServiceListTest(TestCase):

    def setUp(self):
        GlobalSection.objects.all().delete()
        self.header = GlobalSection.objects.create(
            key='main-header', name='Main Header', section_type='header',
            html_template_i18n={'pt': '<header>H</header>'},
            is_active=True, order=0,
        )
        self.footer = GlobalSection.objects.create(
            key='main-footer', name='Main Footer', section_type='footer',
            html_template_i18n={'pt': '<footer>F</footer>'},
            is_active=True, order=1,
        )
        self.inactive = GlobalSection.objects.create(
            key='old-banner', name='Old Banner', section_type='announcement',
            html_template_i18n={'pt': '<div>Banner</div>'},
            is_active=False, order=2,
        )

    def test_list_all(self):
        result = GlobalSectionService.list()
        self.assertTrue(result['success'])
        self.assertEqual(len(result['sections']), 3)

    def test_list_active_only(self):
        result = GlobalSectionService.list(active_only=True)
        self.assertTrue(result['success'])
        self.assertEqual(len(result['sections']), 2)

    def test_list_by_type(self):
        result = GlobalSectionService.list(section_type='header')
        self.assertTrue(result['success'])
        self.assertEqual(len(result['sections']), 1)
        self.assertEqual(result['sections'][0].key, 'main-header')

    def test_list_ordered(self):
        result = GlobalSectionService.list()
        keys = [s.key for s in result['sections']]
        self.assertEqual(keys, ['main-header', 'main-footer', 'old-banner'])


class GlobalSectionServiceUpdateHtmlTest(TestCase):

    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.section = GlobalSection.objects.create(
            key='main-header',
            name='Main Header',
            section_type='header',
            html_template_i18n={
                'pt': '<header>Old PT</header>',
                'en': '<header>Old EN</header>',
            },
            is_active=True,
        )

    def test_update_html_single_lang(self):
        result = GlobalSectionService.update_html(
            'main-header', '<header>New PT</header>', lang='pt',
        )
        self.assertTrue(result['success'])
        self.section.refresh_from_db()
        self.assertIn('New PT', self.section.html_template_i18n['pt'])
        # English unchanged
        self.assertIn('Old EN', self.section.html_template_i18n['en'])

    def test_update_html_default_lang(self):
        result = GlobalSectionService.update_html(
            'main-header', '<header>Default update</header>',
        )
        self.assertTrue(result['success'])
        self.section.refresh_from_db()
        self.assertIn('Default update', self.section.html_template_i18n['pt'])

    def test_update_html_not_found(self):
        result = GlobalSectionService.update_html(
            'nonexistent', '<header>X</header>',
        )
        self.assertFalse(result['success'])
        self.assertIn('not found', result['error'])
