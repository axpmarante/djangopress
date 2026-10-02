"""A new section ("+ Add section") goes through the same pipeline as the Chat:
three directions in parallel, the page's design context, the design check, Flash."""
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from djangopress.ai import directions
from djangopress.ai.services import ContentGenerationService
from djangopress.ai.utils.llm_config import StandardizedLLMResponse
from djangopress.ai.utils.prompts import PromptTemplates
from djangopress.core.models import Page, SiteSettings
from djangopress.editor_v2 import chat

CTX = {'colors': [{'name': 'Primary', 'value': '#C42014'}], 'fonts': [{'role': 'Headings', 'family': 'Fraunces'}],
       'design_guide': '', 'references': [], 'vocabulary': [], 'images': [],
       'typography': {'h2': {'weight': 'font-light', 'sizes': {'': [44]}}}}
PAGE = '<section data-section="hero" id="hero"><h1>Olá</h1></section><section data-section="sobre" id="sobre"><p>x</p></section>'
NEW = '<section data-section="horario" id="horario"><h2 class="text-[50px] font-bold">Horário</h2></section>'


def reply(text):
    return StandardizedLLMResponse(content=text, usage={'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2},
                                   finish_reason='STOP')


class Base(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(title_i18n={'pt': 'Início'}, slug_i18n={'pt': 'inicio'}, is_active=True,
                                        html_content_i18n={'pt': PAGE})


class PromptTest(TestCase):
    def test_one_new_section_in_a_direction_with_the_design_context(self):
        system, user = PromptTemplates.get_section_generation_prompt(
            site_name='S', site_description='', project_briefing='', default_language='pt', full_page_html=PAGE,
            insert_after='hero', user_request='Horário e mapa',
            direction={'name': 'Bolder', 'brief': 'More presence.'}, design_context='## Site design\nMARK')
        both = system + user
        self.assertIn('More presence.', both)
        self.assertIn('ONE version', both)
        self.assertIn('MARK', user)
        self.assertNotIn('OPTION_1', both)
        self.assertNotIn('Keep output concise', both)
        self.assertNotIn('3 variations', both)


class ServiceTest(Base):
    def test_generate_section_in_a_direction_returns_one_option(self):
        service = ContentGenerationService(model_name='gemini-flash')
        with mock.patch.object(service.llm, 'get_completion', return_value=reply(NEW)) as call, \
                mock.patch('djangopress.ai.services.ComponentRegistry.select_components', return_value=[]):
            out = service.generate_section(page_id=self.page.pk, insert_after='hero', instructions='Horário', lang='pt',
                                           page=self.page, direction={'name': 'Bolder', 'brief': 'b'},
                                           design_context='## Site design\nMARK')
        self.assertEqual(len(out['options']), 1)
        self.assertIn('Horário', out['options'][0]['html'])
        self.assertIn('MARK', call.call_args.args[0][1]['content'])


class DirectionsTest(Base):
    def test_three_new_section_directions_on_flash(self):
        with mock.patch.object(directions, 'ContentGenerationService') as cls:
            cls.return_value.generate_section.return_value = {'options': [{'html': NEW}]}
            got = []
            result = directions.generate_directions(self.page, 'new', 'hero', 'Horário', lang='pt', context=CTX,
                                                    on_option=got.append)
        call = cls.return_value.generate_section
        self.assertEqual(call.call_count, 3)
        self.assertEqual({c.kwargs['insert_after'] for c in call.call_args_list}, {'hero'})
        self.assertEqual({c.kwargs['model_name'] for c in cls.call_args_list}, {'gemini-flash'})
        self.assertEqual([r['name'] for r in result], ["In the page's style", 'Bolder', 'Another layout'])
        self.assertIn('font-light', result[0]['html'])                    # the page's type scale applied
        self.assertIn('text-[44px]', result[0]['html'])


class ChatTurnTest(Base):
    def test_a_new_section_turn_streams_directions_without_the_router(self):
        events = []
        with mock.patch('djangopress.editor_v2.chat.generate_directions', return_value=[]) as gen, \
                mock.patch('djangopress.ai.refinement_agent.agent.RefinementAgent.handle') as handle, \
                mock.patch('djangopress.editor_v2.chat.build_design_context', return_value=CTX):
            result = chat.run_turn(self.page, scope='new', target='hero', instructions='Título dourado',
                                   mode='auto', lang='pt', emit=lambda e, d: events.append(e))
        handle.assert_not_called()
        self.assertEqual(gen.call_args.args[1:3], ('new', 'hero'))
        self.assertEqual(result['mode'], 'explore')

    def test_the_endpoint_accepts_a_new_section_at_the_top(self):
        user = get_user_model().objects.create_superuser('a', 'a@x.com', 'pw')
        self.client.force_login(user)
        with mock.patch('djangopress.editor_v2.chat_views._start_worker', side_effect=lambda fn: fn()), \
                mock.patch('djangopress.editor_v2.chat.generate_directions', return_value=[]) as gen, \
                mock.patch('djangopress.editor_v2.chat.build_design_context', return_value=CTX):
            res = self.client.post('/editor-v2/api/chat/stream/', data=json.dumps({
                'page_id': self.page.pk, 'scope': 'new', 'insert_after': None, 'instructions': 'Horário'}),
                content_type='application/json', HTTP_REFERER='http://testserver/pt/?edit=v2')
            text = b''.join(res.streaming_content).decode()
        self.assertIn('event: complete', text)
        self.assertEqual(gen.call_args.args[1:3], ('new', None))
