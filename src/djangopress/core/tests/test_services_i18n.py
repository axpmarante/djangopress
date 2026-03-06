"""Tests for core.services.i18n — auto-translation helper."""

from unittest.mock import patch
from django.test import TestCase
from core.services.i18n import build_i18n_field, auto_generate_slugs


class BuildI18nFieldTest(TestCase):
    """Test build_i18n_field() which builds complete i18n dicts."""

    def setUp(self):
        from core.models import SiteSettings
        self.settings = SiteSettings.load()
        self.settings.enabled_languages = [
            {'code': 'pt', 'name': 'Português'},
            {'code': 'en', 'name': 'English'},
        ]
        self.settings.default_language = 'pt'
        self.settings.save()

    def test_explicit_i18n_all_langs_returns_as_is(self):
        i18n = {'pt': 'Sobre Nós', 'en': 'About Us'}
        result = build_i18n_field(value_i18n=i18n)
        self.assertEqual(result, i18n)

    def test_single_value_fills_default_lang(self):
        result = build_i18n_field(value='Sobre Nós')
        self.assertEqual(result['pt'], 'Sobre Nós')
        self.assertIn('en', result)
        self.assertTrue(len(result['en']) > 0)

    def test_partial_i18n_fills_missing(self):
        result = build_i18n_field(value_i18n={'pt': 'Sobre Nós'})
        self.assertIn('en', result)
        self.assertEqual(result['pt'], 'Sobre Nós')

    def test_no_value_raises(self):
        with self.assertRaises(ValueError):
            build_i18n_field()

    @patch('core.services.i18n._translate_text')
    def test_translation_called_for_missing_langs(self, mock_translate):
        mock_translate.return_value = 'About Us'
        result = build_i18n_field(value='Sobre Nós')
        mock_translate.assert_called_once_with('Sobre Nós', 'pt', 'en')
        self.assertEqual(result['en'], 'About Us')

    @patch('core.services.i18n._translate_text')
    def test_skip_translation_when_all_present(self, mock_translate):
        build_i18n_field(value_i18n={'pt': 'Sobre', 'en': 'About'})
        mock_translate.assert_not_called()


class AutoGenerateSlugsTest(TestCase):

    def setUp(self):
        from core.models import SiteSettings
        self.settings = SiteSettings.load()
        self.settings.enabled_languages = [
            {'code': 'pt', 'name': 'Português'},
            {'code': 'en', 'name': 'English'},
        ]
        self.settings.default_language = 'pt'
        self.settings.save()

    def test_generates_slugs_from_titles(self):
        titles = {'pt': 'Sobre Nós', 'en': 'About Us'}
        result = auto_generate_slugs(titles)
        self.assertEqual(result['pt'], 'sobre-nos')
        self.assertEqual(result['en'], 'about-us')

    def test_explicit_slug_overrides_default_lang(self):
        titles = {'pt': 'Sobre Nós', 'en': 'About Us'}
        result = auto_generate_slugs(titles, slug='sobre')
        self.assertEqual(result['pt'], 'sobre')
        self.assertEqual(result['en'], 'about-us')
