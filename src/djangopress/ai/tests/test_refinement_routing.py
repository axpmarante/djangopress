"""The editor Chat asks the router first: a direct edit is applied at once, a
request that needs a new design comes back as 'delegate' without generating.
Every routing call is logged."""
from unittest import mock

from django.test import TestCase

from djangopress.ai.models import AICallLog
from djangopress.ai.refinement_agent.agent import RefinementAgent
from djangopress.ai.utils.llm_config import StandardizedLLMResponse
from djangopress.core.models import Page, SiteSettings

SERVICE = 'djangopress.ai.services.ContentGenerationService'


def reply(text):
    return StandardizedLLMResponse(content=text, usage={'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5},
                                   finish_reason='STOP')


class RoutingTest(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(title_i18n={'pt': 'Início'}, slug_i18n={'pt': 'inicio'}, is_active=True,
                                        html_content_i18n={'pt': '<section data-section="hero" id="hero"><h1>Olá</h1></section>'})

    def handle(self, answer, **kw):
        agent = RefinementAgent()
        with mock.patch.object(agent.llm, 'get_completion', return_value=reply(answer)), \
                mock.patch(f'{SERVICE}.refine_section_only') as gen:
            result = agent.handle('Redesenha', 'section', 'hero', self.page, lang='pt', **kw)
        return result, gen

    def test_without_delegation_a_regenerate_comes_back_unbuilt(self):
        result, gen = self.handle('<actions>[{"tool": "refine_with_ai", "params": {}}]</actions>', delegate=False)
        self.assertTrue(result['delegate'])
        gen.assert_not_called()

    def test_without_delegation_the_fallback_does_not_generate(self):
        result, gen = self.handle('<response>Not sure.</response>', delegate=False)
        self.assertTrue(result['delegate'])
        gen.assert_not_called()

    def test_a_direct_edit_still_returns_the_edit(self):
        result, _gen = self.handle('<actions>[{"tool": "update_styles", "params": {"selector": "h1", "add_classes": "text-6xl"}}]</actions>'
                                   '<response>Bigger.</response>', delegate=False)
        self.assertIn('text-6xl', result['options'][0]['html'])
        self.assertEqual(result['routing_tier'], 'direct_edit')

    def test_base_html_is_what_the_router_edits(self):
        base = '<section data-section="hero" id="hero"><h1>Opção B</h1></section>'
        result, _gen = self.handle('<actions>[{"tool": "update_styles", "params": {"selector": "h1", "add_classes": "italic"}}]</actions>'
                                   '<response>ok</response>', delegate=False, base_html=base)
        self.assertIn('Opção B', result['options'][0]['html'])

    def test_every_routing_call_is_logged(self):
        self.handle('<actions>[{"tool": "update_styles", "params": {"selector": "h1", "add_classes": "x"}}]</actions>'
                    '<response>ok</response>', delegate=False)
        log = AICallLog.objects.get(action='refine_routing')
        self.assertEqual(log.page, self.page)
        self.assertEqual(log.section_name, 'hero')
        self.assertEqual(log.total_tokens, 5)
        self.assertIn('Redesenha', log.user_prompt)


class ElementRootTest(TestCase):
    """'podes meter este botão com cor?' on an element: update_styles without a selector targets the element."""
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(title_i18n={'pt': 'P'}, slug_i18n={'pt': 'p'}, is_active=True, html_content_i18n={
            'pt': '<section data-section="hero" id="hero" class="py-10"><div><h1>Olá</h1>'
                  '<a class="inline-flex text-[#E3A11C]" href="/pt/">Reservar</a></div></section>'})

    def test_the_element_gets_the_classes(self):
        agent = RefinementAgent()
        answer = reply('<response>Cor dourada.</response><actions>[{"tool": "update_styles", "params": '
                       '{"add_classes": "bg-[#E3A11C] text-[#122538]", "remove_classes": "text-[#E3A11C]"}}]</actions>')
        with mock.patch.object(agent.llm, 'get_completion', return_value=answer):
            result = agent.handle('podes meter este botão com cor?', 'element',
                                  'section[data-section="hero"] > div:nth-child(1) > a:nth-child(2)', self.page,
                                  lang='pt', delegate=False)
        html = result['options'][0]['html']
        self.assertTrue(html.startswith('<a '), html)
        self.assertIn('bg-[#E3A11C]', html)
        self.assertNotIn('text-[#E3A11C]', html)

    def test_an_edit_that_changes_nothing_is_not_reported_as_done(self):
        agent = RefinementAgent()
        answer = reply('<response>Feito.</response><actions>[{"tool": "update_styles", "params": '
                       '{"selector": "h1", "add_classes": "italic"}}]</actions>')
        with mock.patch.object(agent.llm, 'get_completion', return_value=answer):
            result = agent.handle('botão com cor', 'element',
                                  'section[data-section="hero"] > div:nth-child(1) > a:nth-child(2)', self.page,
                                  lang='pt', delegate=False)
        self.assertTrue(result.get('delegate'), result)
