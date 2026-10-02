"""edit_text changes or removes exact wording without regenerating the section: the rest of
the HTML stays byte for byte, and only the changed elements are translated."""
from unittest import mock

from bs4 import BeautifulSoup

from django.contrib.auth import get_user_model
from django.test import TestCase

from djangopress.core.models import Page, SiteSettings
from djangopress.site_assistant import changes
from djangopress.site_assistant.prompts import build_executor_prompt
from djangopress.site_assistant.tool_declarations import PAGE_EDIT_TOOLS
from djangopress.site_assistant.tools import ToolRegistry

TRANSLATE = 'djangopress.editor_v2.ai_apply.translate_snippet'
GENERATE = 'djangopress.ai.directions.generate_directions'

PT = ('<section data-section="manifesto" id="manifesto"><div class="mx-auto">'
      '<h2 class="font-light">Do not copy</h2>'
      '<p class="lead">Produto da Ria Formosa, técnica de alta cozinha — e meias-doses para que cada pessoa prove '
      'três ou quatro pratos.</p></div></section>'
      '<section data-section="carta" id="carta"><p class="x">Uma viagem pela carreira do chef, feita para partilhar.</p>'
      '<p class="y">Meias-doses para partilhar.</p><img src="/a.jpg" alt="Prato"></section>')
EN = ('<section data-section="manifesto" id="manifesto"><div class="mx-auto">'
      '<h2 class="font-light">Do not copy</h2>'
      '<p class="lead">Ria Formosa produce, fine-dining technique — and half portions so everyone can try '
      'three or four dishes.</p></div></section>'
      '<section data-section="carta" id="carta"><p class="x">A journey through the chef\'s career, made to share.</p>'
      '<p class="y">Half portions to share.</p><img src="/a.jpg" alt="Dish"></section>')


def fake_translate(html, source, target):
    return html.replace('Produto da Ria Formosa, técnica de alta cozinha.', 'Ria Formosa produce, fine-dining technique.') \
               .replace('Uma viagem pela carreira do chef.', "A journey through the chef's career.")


class EditTextTest(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(title_i18n={'pt': 'Início', 'en': 'Home'}, slug_i18n={'pt': 'inicio', 'en': 'home'},
                                        is_active=True, html_content_i18n={'pt': PT, 'en': EN})
        user = get_user_model().objects.create_superuser('a', 'a@x.com', 'pw')
        self.context = {'session': mock.Mock(active_page_id=self.page.id), 'user': user, 'active_page': self.page,
                        'changes': changes.TurnChanges('Tira as meias-doses', user)}

    def edit(self, **params):
        with mock.patch(TRANSLATE, side_effect=fake_translate) as tr, mock.patch(GENERATE) as gen:
            out = ToolRegistry.execute('edit_text', params, self.context)
        self.tr, self.gen = tr, gen
        self.page.refresh_from_db()
        return out

    def test_removes_a_phrase_and_tidies_the_punctuation(self):
        out = self.edit(section_name='manifesto', find=' — e meias-doses para que cada pessoa prove três ou quatro pratos',
                        replace='')
        self.assertTrue(out['success'], out)
        self.assertIn('<p class="lead">Produto da Ria Formosa, técnica de alta cozinha.</p>', self.page.html_content_i18n['pt'])

    def test_nothing_else_in_the_page_changes(self):
        self.edit(section_name='manifesto', find=' — e meias-doses para que cada pessoa prove três ou quatro pratos',
                  replace='')
        norm = lambda h: str(BeautifulSoup(h, 'html.parser'))   # the engine always re-serializes (e.g. <img/>)
        pt = self.page.html_content_i18n['pt']
        self.assertEqual(norm(pt.replace('<p class="lead">Produto da Ria Formosa, técnica de alta cozinha.</p>', '')),
                         norm(PT.replace('<p class="lead">Produto da Ria Formosa, técnica de alta cozinha — e meias-doses '
                                         'para que cada pessoa prove três ou quatro pratos.</p>', '')))

    def test_no_section_is_regenerated(self):
        self.edit(section_name='manifesto', find='meias-doses', replace='pratos')
        self.gen.assert_not_called()

    def test_only_the_changed_element_is_translated(self):
        self.edit(section_name='manifesto', find=' — e meias-doses para que cada pessoa prove três ou quatro pratos',
                  replace='')
        self.assertEqual(self.tr.call_count, 1)
        self.assertEqual(self.tr.call_args.args[0], '<p class="lead">Produto da Ria Formosa, técnica de alta cozinha.</p>')
        en = self.page.html_content_i18n['en']
        self.assertIn('<p class="lead">Ria Formosa produce, fine-dining technique.</p>', en)
        self.assertIn('<p class="x">A journey through the chef\'s career, made to share.</p>', en)

    def test_without_a_section_it_covers_the_whole_page(self):
        out = self.edit(find=', feita para partilhar', replace='')
        self.assertTrue(out['success'], out)
        self.assertIn('<p class="x">Uma viagem pela carreira do chef.</p>', self.page.html_content_i18n['pt'])
        self.assertIn('carta', out['message'])

    def test_an_element_left_empty_is_removed_in_every_language(self):
        out = self.edit(section_name='carta', find='Meias-doses para partilhar.', replace='')
        self.assertTrue(out['success'], out)
        self.assertNotIn('class="y"', self.page.html_content_i18n['pt'])
        self.assertNotIn('class="y"', self.page.html_content_i18n['en'])
        self.assertIn('alt="Dish"', self.page.html_content_i18n['en'])

    def test_text_that_is_not_there_is_reported(self):
        out = self.edit(section_name='manifesto', find='zona de estopada', replace='')
        self.assertFalse(out['success'])
        self.assertIn('not found', out['message'])
        self.assertEqual(self.page.html_content_i18n['pt'], PT)

    def test_matching_ignores_case_and_spacing(self):
        out = self.edit(section_name='carta', find='MEIAS-DOSES  para partilhar.', replace='')
        self.assertTrue(out['success'], out)

    def test_it_is_undoable_like_the_other_page_tools(self):
        self.edit(section_name='manifesto', find='meias-doses', replace='pratos')
        self.assertTrue(self.context['changes'].items)


class EditTextWiringTest(TestCase):
    def test_declared_for_the_model(self):
        self.assertIn('edit_text', [d.name for d in PAGE_EDIT_TOOLS])

    def test_the_prompt_prefers_it_for_wording_and_asks_about_unclear_words(self):
        session = mock.Mock(active_page=None, active_page_id=None, messages=[])
        prompt = build_executor_prompt(session, {'pages': [], 'site_name': 'S'})
        self.assertIn('edit_text', prompt)
        self.assertIn('dictation', prompt)
