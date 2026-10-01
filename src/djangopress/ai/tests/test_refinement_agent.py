"""Refinement agent: element edits return the element, it reads the language being
edited, and its JSON calls ask Gemini for JSON."""
from unittest import mock

from django.test import TestCase

from djangopress.ai.refinement_agent import tools as agent_tools
from djangopress.ai.refinement_agent.agent import RefinementAgent
from djangopress.ai.utils.llm_config import StandardizedLLMResponse
from djangopress.core.models import Page, SiteSettings

SELECTOR = 'section[data-section="hero"] > a:nth-child(2)'


def reply(text):
    return StandardizedLLMResponse(content=text, usage={'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2},
                                   finish_reason='STOP')


class AgentTest(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(
            title_i18n={'pt': 'Início', 'en': 'Home'}, slug_i18n={'pt': 'inicio', 'en': 'home'}, is_active=True,
            html_content_i18n={
                'pt': '<section data-section="hero" id="hero"><h1>Olá</h1><a class="btn">Reservar</a></section>',
                'en': '<section data-section="hero" id="hero"><h1>Hello</h1><a class="btn">Book</a></section>',
            },
        )

    def test_element_direct_edit_returns_the_element(self):
        agent = RefinementAgent()
        answer = reply('<actions>[{"tool": "update_styles", "params": {"selector": "%s", "add_classes": "text-xl"}}]</actions>'
                       '<response>Done.</response>' % SELECTOR.replace('"', '\\"'))
        with mock.patch.object(agent.llm, 'get_completion', return_value=answer):
            result = agent.handle('Bigger button', 'element', SELECTOR, self.page, lang='pt')
        html = result['options'][0]['html']
        self.assertTrue(html.startswith('<a '), html)
        self.assertIn('text-xl', html)
        self.assertNotIn('<section', html)

    def test_reads_the_editing_language(self):
        agent = RefinementAgent()
        answer = reply('<response>Nothing to do.</response>')
        with mock.patch.object(agent.llm, 'get_completion', return_value=answer) as call, \
                mock.patch('djangopress.ai.services.ContentGenerationService.refine_section_only',
                           return_value={'options': [], 'assistant_message': ''}):
            agent.handle('Bigger title', 'section', 'hero', self.page, lang='en')
        prompt = ' '.join(m['content'] for m in call.call_args_list[0].args[0])
        self.assertIn('Hello', prompt)
        self.assertNotIn('Olá', prompt)

    def test_apply_edits_asks_for_json(self):
        context = {'target_html': '<section data-section="hero"><h1>Olá</h1></section>', 'instructions': 'x',
                   'site_settings': SiteSettings.load()}
        with mock.patch('djangopress.ai.utils.llm_config.LLMBase.get_completion', return_value=reply('[]')) as call:
            agent_tools.apply_edits({'instructions': 'x'}, context)
        self.assertTrue(call.call_args.kwargs.get('json_output'))
