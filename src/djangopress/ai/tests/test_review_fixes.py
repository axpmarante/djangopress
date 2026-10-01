"""Fixes from the phase 1-2 review: the page refine reports which language it
wrote, truncated translations are errors, and top_p/top_k are not sent."""
from types import SimpleNamespace
from unittest import mock

from django.test import TestCase

from djangopress.ai.services import ContentGenerationService
from djangopress.ai.tests.test_llm_settings import FakeModels, NoOpenAI, fake_response
from djangopress.ai.utils.llm_config import LLMBase, ModelProvider, StandardizedLLMResponse, get_ai_model
from djangopress.core.models import Page, SiteSettings


def answer(text, finish='STOP'):
    return StandardizedLLMResponse(content=text, usage={'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2},
                                   finish_reason=finish)


class ReviewFixesTest(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}, {'code': 'es', 'name': 'ES'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(
            title_i18n={'pt': 'Início'}, slug_i18n={'pt': 'inicio'}, is_active=True,
            html_content_i18n={'es': '<section data-section="hero" id="hero"><h1>Hola</h1></section>',
                               'pt': '<section data-section="hero" id="hero"><h1>Olá</h1></section>',
                               'en': ''},
        )

    def test_page_refine_reports_the_language_it_wrote(self):
        service = ContentGenerationService()
        refined = '<section data-section="hero" id="hero"><h1>Olá de novo</h1></section>'
        with mock.patch.object(service.llm, 'get_completion', return_value=answer(refined)):
            result = service.refine_page_with_html(page_id=self.page.id, instructions='x', lang='en')
        self.assertEqual(result['lang'], 'pt')            # EN copy is empty -> the PT copy is what was refined
        self.assertEqual(result['html_content_i18n']['pt'], refined)

    def test_translation_cut_off_is_an_error(self):
        service = ContentGenerationService()
        with mock.patch.object(service.llm, 'get_completion',
                               return_value=answer('<section data-section="hero"><h1>Hi</h1></section>', 'MAX_TOKENS')):
            with self.assertRaisesRegex(ValueError, 'cut off'):
                service.translate_html('<section data-section="hero"><h1>Olá</h1></section>', 'pt', 'en')

    def test_translation_much_shorter_than_source_is_an_error(self):
        service = ContentGenerationService()
        source = ''.join(f'<section data-section="s{i}"><p>{"texto " * 200}</p></section>' for i in range(4))
        with mock.patch.object(service.llm, 'get_completion',
                               return_value=answer('<section data-section="s0"><p>text</p></section>')):
            with self.assertRaises(ValueError):
                service.translate_html(source, 'pt', 'en')

    def test_top_p_and_top_k_are_not_sent(self):
        models = FakeModels(fake_response())
        clients = {ModelProvider.GOOGLE: SimpleNamespace(models=models), ModelProvider.OPENAI: NoOpenAI()}
        with mock.patch.dict(LLMBase._clients, clients):
            LLMBase().get_completion([{'role': 'user', 'content': 'x'}], tool_name=get_ai_model('refinement_section'))
        config = models.calls[0].config
        self.assertIsNone(config.top_p)
        self.assertIsNone(config.top_k)
