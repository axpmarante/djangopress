"""read_section shows real HTML; update_element_styles adds/removes classes in every language."""
from unittest import mock

from django.test import TestCase

from djangopress.core.models import Page, SiteSettings
from djangopress.site_assistant.tools import ToolRegistry

HERO = '<section data-section="hero" id="hero" class="py-20 bg-white"><h1 class="text-4xl font-bold">{}</h1></section>'


class ReadRestyleTest(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(
            title_i18n={'pt': 'Início', 'en': 'Home'}, slug_i18n={'pt': 'inicio', 'en': 'home'}, is_active=True,
            html_content_i18n={'pt': HERO.format('Olá'), 'en': HERO.format('Hello')},
        )
        self.context = {'session': mock.Mock(active_page_id=self.page.id), 'user': None, 'active_page': self.page}

    def run_tool(self, name, **params):
        return ToolRegistry.execute(name, params, self.context)

    def classes(self, lang, tag='h1'):
        self.page.refresh_from_db()
        from bs4 import BeautifulSoup
        return BeautifulSoup(self.page.html_content_i18n[lang], 'html.parser').find(tag).get('class')

    def test_read_section_returns_the_editing_language_html(self):
        out = self.run_tool('read_section', section_name='hero')
        self.assertTrue(out['success'], out)
        self.assertIn('text-4xl font-bold', out['html'])
        self.assertIn('Olá', out['html'])

    def test_read_section_is_capped_with_a_note(self):
        self.page.html_content_i18n = {'pt': HERO.format('x' * 20000), 'en': HERO.format('y')}
        self.page.save()
        out = self.run_tool('read_section', section_name='hero')
        self.assertLessEqual(len(out['html']), 12000)
        self.assertIn('cut', out['message'])

    def test_read_section_unknown_lists_sections(self):
        out = self.run_tool('read_section', section_name='nope')
        self.assertFalse(out['success'])
        self.assertIn('hero', out['message'])

    def test_add_and_remove_classes_keep_the_others_in_every_language(self):
        out = self.run_tool('update_element_styles', selector='section[data-section="hero"] h1',
                            add_classes='text-center tracking-tight', remove_classes='font-bold')
        self.assertTrue(out['success'], out)
        for lang in ('pt', 'en'):
            self.assertEqual(self.classes(lang), ['text-4xl', 'text-center', 'tracking-tight'])

    def test_section_itself_by_name(self):
        self.run_tool('update_element_styles', section_name='hero', add_classes='bg-stone-100', remove_classes='bg-white')
        self.assertEqual(self.classes('en', 'section'), ['py-20', 'bg-stone-100'])

    def test_replace_all_still_works(self):
        self.run_tool('update_element_styles', selector='section[data-section="hero"] h1', new_classes='text-2xl')
        self.assertEqual(self.classes('pt'), ['text-2xl'])
        self.assertEqual(self.classes('en'), ['text-2xl'])

    def test_missing_element_is_reported(self):
        out = self.run_tool('update_element_styles', selector='section[data-section="hero"] h3', add_classes='x')
        self.assertFalse(out['success'])
