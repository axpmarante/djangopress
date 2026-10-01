"""insert_section adds one section where asked and translates only that section."""
import re
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from djangopress.core.models import Page, PageVersion, SiteSettings
from djangopress.site_assistant import changes
from djangopress.site_assistant.tools import ToolRegistry

TRANSLATE = 'djangopress.editor_v2.ai_apply.translate_snippet'
GENERATE = 'djangopress.ai.services.ContentGenerationService.generate_section'
NEW = '<section data-section="faq" id="faq"><h2>PT: Perguntas</h2></section>'


def fake_translate(html, source, target):
    return html.replace('PT:', f'{target.upper()}:')


def page_html(lang, names):
    prefix = 'PT' if lang == 'pt' else 'EN'
    return ''.join(f'<section data-section="{n}" id="{n}"><p>{prefix}: {n}</p></section>' for n in names)


class InsertSectionTest(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        names = ['hero', 'about', 'contacts']
        self.page = Page.objects.create(
            title_i18n={'pt': 'Início', 'en': 'Home'}, slug_i18n={'pt': 'inicio', 'en': 'home'}, is_active=True,
            html_content_i18n={'pt': page_html('pt', names), 'en': page_html('en', names)},
        )
        user = get_user_model().objects.create_superuser('a', 'a@x.com', 'pw')
        self.context = {'session': mock.Mock(active_page_id=self.page.id), 'user': user, 'active_page': self.page,
                        'changes': changes.TurnChanges('Põe umas FAQ', user)}

    def insert(self, new_html=NEW, **params):
        with mock.patch(GENERATE, return_value={'options': [{'html': new_html}], 'assistant_message': ''}) as gen, \
                mock.patch(TRANSLATE, side_effect=fake_translate) as tr:
            out = ToolRegistry.execute('insert_section', {'instructions': 'FAQ', **params}, self.context)
        self.gen, self.tr = gen, tr
        return out

    def order(self, lang):
        self.page.refresh_from_db()
        return re.findall(r'data-section="([^"]+)"', self.page.html_content_i18n[lang])

    def test_before_a_section_goes_after_the_previous_one(self):
        out = self.insert(position='before', anchor_section='contacts')
        self.assertTrue(out['success'], out)
        self.assertEqual(self.order('pt'), ['hero', 'about', 'faq', 'contacts'])
        self.assertEqual(self.order('en'), ['hero', 'about', 'faq', 'contacts'])
        self.assertEqual(self.gen.call_args.kwargs['insert_after'], 'about')

    def test_before_the_first_section_goes_to_the_top(self):
        self.insert(position='before', anchor_section='hero')
        self.assertEqual(self.order('pt'), ['faq', 'hero', 'about', 'contacts'])
        self.assertEqual(self.order('en'), ['faq', 'hero', 'about', 'contacts'])

    def test_after_start_and_end(self):
        self.insert(position='after', anchor_section='hero')
        self.assertEqual(self.order('pt'), ['hero', 'faq', 'about', 'contacts'])
        self.insert(new_html=NEW.replace('faq', 'top'), position='start')
        self.assertEqual(self.order('en')[0], 'top')
        self.insert(new_html=NEW.replace('faq', 'bottom'), position='end')
        self.assertEqual(self.order('en')[-1], 'bottom')

    def test_only_the_new_section_is_translated(self):
        self.page.refresh_from_db()
        before_en = self.page.html_content_i18n['en']
        self.insert(position='before', anchor_section='contacts')
        self.assertEqual(self.tr.call_count, 1)
        self.page.refresh_from_db()
        after_en = self.page.html_content_i18n['en']
        self.assertIn('EN: Perguntas', after_en)
        self.assertEqual(re.sub(r'<section data-section="faq".*?</section>', '', after_en), before_en)

    def test_a_taken_name_is_made_unique(self):
        self.insert(new_html=NEW.replace('faq', 'about'), position='end')
        names = self.order('pt')
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(names), 4)

    def test_unknown_anchor_fails_without_changing_the_page(self):
        out = self.insert(position='before', anchor_section='nope')
        self.assertFalse(out['success'])
        self.assertIn('hero', out['message'])           # lists the sections that exist
        self.assertEqual(self.order('pt'), ['hero', 'about', 'contacts'])

    def test_one_checkpoint_before_the_insert(self):
        PageVersion.objects.filter(page=self.page).delete()
        self.insert(position='end')
        self.assertEqual(PageVersion.objects.filter(page=self.page, kind='checkpoint').count(), 1)
