"""Every AI path uses the latest pipeline: the Chat's page scope and the site
assistant's refine_section / insert_section / refine_page all get the page's
design context, the design check and the section refinement model (Flash)."""
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from djangopress.ai import directions
from djangopress.core.models import Page, SiteSettings
from djangopress.site_assistant.tools import ToolRegistry

PAGE = ('<section data-section="hero" id="hero"><h2 class="text-[44px] font-light">Olá</h2></section>'
        '<section data-section="sobre" id="sobre"><h2 class="text-[44px] font-light">Sobre</h2></section>')
PAGE_OUT = ('<section data-section="hero" id="hero"><h2 class="text-[60px] font-bold bg-blue-600">Olá</h2></section>'
            '<section data-section="sobre" id="sobre"><h2 class="text-[44px] font-light">Sobre</h2></section>')
SERVICE = 'djangopress.ai.services.ContentGenerationService'


class Base(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}]
        s.default_language = 'pt'
        s.primary_color = '#C42014'
        s.save()
        self.page = Page.objects.create(title_i18n={'pt': 'Início'}, slug_i18n={'pt': 'inicio'}, is_active=True,
                                        html_content_i18n={'pt': PAGE})
        self.user = get_user_model().objects.create_superuser('a', 'a@x.com', 'pw')


class PageInStyleTest(Base):
    def test_page_refine_gets_the_context_flash_and_the_check(self):
        with mock.patch(f'{SERVICE}.refine_page_with_html',
                        return_value={'html_content_i18n': {'pt': PAGE_OUT}, 'lang': 'pt'}) as refine, \
                mock.patch(f'{SERVICE}.__init__', return_value=None) as init:
            result = directions.refine_page_in_style(self.page, 'Mais elegante', lang='pt')
        self.assertEqual(init.call_args.kwargs['model_name'], 'gemini-flash')
        self.assertEqual(refine.call_args.kwargs['model_override'], 'gemini-flash')
        self.assertIn('## Site design', refine.call_args.kwargs['design_context'])
        html = result['html_content_i18n']['pt']
        self.assertIn('<h2 class="text-[44px] font-light bg-[#C42014]">Olá</h2>', html)

    def test_the_prompt_carries_the_design_context(self):
        from djangopress.ai.utils.prompts import PromptTemplates
        _system, user = PromptTemplates.get_page_refinement_html_prompt(
            site_name='S', site_description='', project_briefing='', default_language='pt', page_html=PAGE,
            user_request='x', design_context='## Site design\nMARK')
        self.assertIn('MARK', user)


class ChatPageScopeTest(Base):
    def test_the_chat_page_scope_uses_the_page_in_style_helper(self):
        self.client.force_login(self.user)

        class Now:
            def __init__(self, target, daemon=None):
                self.target = target

            def start(self):
                self.target()

        with mock.patch('djangopress.editor_v2.api_views.threading.Thread', Now), \
                mock.patch('djangopress.ai.directions.refine_page_in_style',
                           return_value={'html_content_i18n': {'pt': PAGE}, 'lang': 'pt'}) as helper:
            res = self.client.post('/editor-v2/api/refine-page/stream/', data=json.dumps({
                'page_id': self.page.pk, 'instructions': 'Mais elegante'}), content_type='application/json',
                HTTP_REFERER='http://testserver/pt/?edit=v2')
            text = b''.join(res.streaming_content).decode()
        self.assertIn('event: complete', text)
        helper.assert_called_once()


class AssistantToolsTest(Base):
    def run_tool(self, name, **params):
        context = {'session': None, 'user': self.user, 'active_page': self.page}
        return ToolRegistry.execute(name, params, context)

    def test_refine_section_goes_through_one_direction(self):
        item = {'key': 'edit', 'name': 'Edit', 'html': PAGE.split('</section>')[0] + '</section>', 'why': '', 'notes': []}
        with mock.patch('djangopress.ai.directions.generate_directions', return_value=[item]) as gen:
            out = self.run_tool('refine_section', section_name='hero', instructions='Mais elegante')
        self.assertTrue(out['success'], out)
        self.assertEqual(gen.call_args.args[1:3], ('section', 'hero'))
        self.assertEqual(len(gen.call_args.kwargs['directions']), 1)

    def test_insert_section_goes_through_one_new_section_direction(self):
        item = {'key': 'refined', 'name': 'x', 'html': '<section data-section="faq" id="faq"><h2>FAQ</h2></section>',
                'why': '', 'notes': []}
        with mock.patch('djangopress.ai.directions.generate_directions', return_value=[item]) as gen:
            out = self.run_tool('insert_section', instructions='FAQ', position='end')
        self.assertTrue(out['success'], out)
        self.assertEqual(gen.call_args.args[1:3], ('new', 'sobre'))
        self.assertEqual(len(gen.call_args.kwargs['directions']), 1)

    def test_refine_page_goes_through_the_page_in_style_helper(self):
        with mock.patch('djangopress.ai.directions.refine_page_in_style',
                        return_value={'html_content_i18n': {'pt': PAGE}, 'lang': 'pt'}) as helper:
            out = self.run_tool('refine_page', instructions='Mais elegante')
        self.assertTrue(out['success'], out)
        helper.assert_called_once()
