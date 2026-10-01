"""Assistant AI refines update every language through the editor's apply service."""
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from djangopress.core.models import Page, SiteSettings
from djangopress.site_assistant.tools import page_tools

TRANSLATE = 'djangopress.editor_v2.ai_apply.translate_snippet'


def fake_translate(html, source, target):
    return html.replace('PT:', f'{target.upper()}:')


class AssistantRefineTest(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(
            title_i18n={'pt': 'Início', 'en': 'Home'}, slug_i18n={'pt': 'inicio', 'en': 'home'}, is_active=True,
            html_content_i18n={'pt': '<section data-section="hero" id="hero"><h1>PT: Olá</h1></section>',
                               'en': '<section data-section="hero" id="hero"><h1>EN: Hello</h1></section>'},
        )
        user = get_user_model().objects.create_superuser('a', 'a@x.com', 'pw')
        session = mock.Mock(active_page_id=self.page.id)
        self.context = {'session': session, 'user': user, 'active_page': self.page}

    def html(self, lang):
        self.page.refresh_from_db()
        return self.page.html_content_i18n[lang]

    def test_refine_section_writes_every_language(self):
        result = {'options': [{'html': '<section data-section="hero" id="hero"><h1>PT: Novo</h1></section>'}],
                  'assistant_message': 'ok'}
        with mock.patch('djangopress.ai.services.ContentGenerationService.refine_section_only', return_value=result), \
                mock.patch(TRANSLATE, side_effect=fake_translate):
            out = page_tools.refine_section({'section_name': 'hero', 'instructions': 'x'}, self.context)
        self.assertTrue(out['success'], out)
        self.assertIn('PT: Novo', self.html('pt'))
        self.assertIn('EN: Novo', self.html('en'))

    def test_refine_page_writes_every_language(self):
        result = {'html_content_i18n': {'pt': '<section data-section="hero" id="hero"><h1>PT: Página</h1></section>'}}
        with mock.patch('djangopress.ai.services.ContentGenerationService.refine_page_with_html', return_value=result), \
                mock.patch(TRANSLATE, side_effect=fake_translate):
            out = page_tools.refine_page({'instructions': 'x'}, self.context)
        self.assertTrue(out['success'], out)
        self.assertIn('EN: Página', self.html('en'))


class RouterJsonTest(TestCase):
    def test_router_asks_for_json(self):
        from djangopress.ai.utils.llm_config import StandardizedLLMResponse
        from djangopress.site_assistant.router import Router
        answer = StandardizedLLMResponse(content='{"intents": [], "needs_active_page": false, "direct_response": "Olá"}')
        with mock.patch('djangopress.ai.utils.llm_config.LLMBase.get_completion', return_value=answer) as call:
            Router().classify('Olá', {'pages': [], 'stats': {}}, '')
        self.assertTrue(call.call_args.kwargs.get('json_output'))
