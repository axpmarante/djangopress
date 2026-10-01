"""Editor AI endpoints save through the apply service, in the editing language,
and the refinement conversation records which option was applied."""
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from djangopress.ai.models import RefinementSession
from djangopress.core.models import Page, SiteSettings

TRANSLATE = 'djangopress.editor_v2.ai_apply.translate_snippet'


def fake_translate(html, source, target):
    return html.replace('PT:', f'{target.upper()}:')


class AIEndpointTest(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(
            title_i18n={'pt': 'Início', 'en': 'Home'}, slug_i18n={'pt': 'inicio', 'en': 'home'}, is_active=True,
            html_content_i18n={
                'pt': '<section data-section="hero" id="hero"><h1>PT: Olá</h1></section>',
                'en': '<section data-section="hero" id="hero"><h1>EN: Hello</h1></section>',
            },
        )
        self.client.force_login(get_user_model().objects.create_superuser('a', 'a@x.com', 'pw'))

    def post(self, url, body, lang='pt'):
        return self.client.post(url, data=json.dumps({'page_id': self.page.id, **body}),
                                content_type='application/json', HTTP_REFERER=f'http://testserver/{lang}/?edit=v2')

    def html(self, lang):
        self.page.refresh_from_db()
        return self.page.html_content_i18n[lang]


class ApplyOptionTest(AIEndpointTest):
    def test_section_replace_updates_every_language(self):
        with mock.patch(TRANSLATE, side_effect=fake_translate):
            res = self.post('/editor-v2/api/apply-option/', {
                'scope': 'section', 'section_name': 'hero',
                'html': '<section data-section="hero" id="hero"><h1>PT: Novo</h1></section>'})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['translated_languages'], ['en'])
        self.assertIn('PT: Novo', self.html('pt'))
        self.assertIn('EN: Novo', self.html('en'))

    def test_insert_renames_duplicate(self):
        with mock.patch(TRANSLATE, side_effect=fake_translate):
            res = self.post('/editor-v2/api/apply-option/', {
                'mode': 'insert', 'insert_after': 'hero',
                'html': '<section data-section="hero" id="hero"><p>PT: dup</p></section>'})
        self.assertEqual(res.json()['section_name'], 'hero-2')
        self.assertIn('data-section="hero-2"', self.html('en'))

    def test_element_scope_refuses_a_section(self):
        res = self.post('/editor-v2/api/apply-option/', {
            'scope': 'element', 'selector': 'section[data-section="hero"] > h1:nth-child(1)',
            'html': '<section data-section="hero"><h1>x</h1></section>'})
        self.assertEqual(res.status_code, 400)
        self.assertIn('PT: Olá', self.html('pt'))

    def test_applied_option_is_recorded_in_the_conversation(self):
        session = RefinementSession.objects.create(page=self.page, title='t')
        with mock.patch(TRANSLATE, side_effect=fake_translate):
            self.post('/editor-v2/api/apply-option/', {
                'scope': 'section', 'section_name': 'hero', 'session_id': session.id, 'option_index': 2,
                'html': '<section data-section="hero" id="hero"><h1>PT: B</h1></section>'})
        session.refresh_from_db()
        self.assertIn('Applied option 2 to hero.', json.dumps(session.messages))


class SavePageTest(AIEndpointTest):
    def test_save_ai_page_takes_html_and_translates(self):
        with mock.patch(TRANSLATE, side_effect=fake_translate):
            res = self.post('/editor-v2/api/save-ai-page/', {
                'html': '<section data-section="hero" id="hero"><h1>PT: Página</h1></section>'})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertIn('EN: Página', self.html('en'))


class InlineThread:
    """Runs the stream's worker synchronously (the in-memory test DB locks across threads)."""
    def __init__(self, target=None, daemon=None, **kwargs):
        self.target = target

    def start(self):
        self.target()

    def join(self, timeout=None):
        pass


def sse_events(response):
    text = b''.join(response.streaming_content).decode()
    return [block for block in text.split('\n\n') if block.strip()]


@mock.patch('djangopress.editor_v2.api_views.threading.Thread', InlineThread)
class LanguageTest(AIEndpointTest):
    def test_refine_multi_stream_passes_the_editing_language(self):
        options = {'options': [{'html': '<section data-section="hero" id="hero"><h1>x</h1></section>'}],
                   'assistant_message': 'ok'}
        with mock.patch('djangopress.ai.refinement_agent.agent.RefinementAgent.handle', return_value=options) as handle:
            res = self.post('/editor-v2/api/refine-multi/stream/', {
                'scope': 'section', 'section_name': 'hero', 'instructions': 'Bigger', 'multi_option': True}, lang='en')
            sse_events(res)
        self.assertEqual(handle.call_args.kwargs['lang'], 'en')

    def test_refine_page_stream_returns_html_of_the_editing_language(self):
        result = {'html_content_i18n': {'pt': '<section data-section="hero"><h1>PT</h1></section>',
                                        'en': '<section data-section="hero"><h1>EN</h1></section>'}}
        with mock.patch('djangopress.ai.services.ContentGenerationService.refine_page_with_html', return_value=result) as refine:
            res = self.post('/editor-v2/api/refine-page/stream/', {'instructions': 'Shorter'}, lang='en')
            events = sse_events(res)
            complete = [b for b in events if 'event: complete' in b]
            self.assertTrue(complete, events)
            complete = complete[0]
        self.assertEqual(refine.call_args.kwargs['lang'], 'en')
        payload = json.loads(complete.split('data:', 1)[1])
        self.assertEqual(payload['html'], '<section data-section="hero"><h1>EN</h1></section>')


@mock.patch('djangopress.editor_v2.api_views.threading.Thread', InlineThread)
class PageStreamLanguageTest(AIEndpointTest):
    def test_preview_is_the_refined_copy_not_another_language(self):
        result = {'html_content_i18n': {'es': '<section data-section="hero"><h1>ES viejo</h1></section>',
                                        'pt': '<section data-section="hero"><h1>PT novo</h1></section>', 'en': ''},
                  'lang': 'pt'}
        with mock.patch('djangopress.ai.services.ContentGenerationService.refine_page_with_html', return_value=result):
            res = self.post('/editor-v2/api/refine-page/stream/', {'instructions': 'Shorter'}, lang='en')
            complete = [b for b in sse_events(res) if 'event: complete' in b][0]
        self.assertEqual(json.loads(complete.split('data:', 1)[1])['html'], '<section data-section="hero"><h1>PT novo</h1></section>')
