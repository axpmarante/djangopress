"""The editor Chat turn: a specific request is edited and applied at once; an
open one gets three design directions streamed one by one; a follow-up can start
from an unapplied option; Stop, reference images and news posts work."""
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from djangopress.ai.models import RefinementSession
from djangopress.core.models import Page, PageVersion, SiteSettings
from djangopress.editor_v2 import chat, chat_views
from djangopress.site_assistant import cancel

TRANSLATE = 'djangopress.editor_v2.ai_apply.translate_snippet'
HANDLE = 'djangopress.ai.refinement_agent.agent.RefinementAgent.handle'
DIRECTIONS = 'djangopress.editor_v2.chat.generate_directions'
HERO_PT = '<section data-section="hero" id="hero"><h1 class="text-4xl">PT: Olá</h1></section>'
HERO_EN = '<section data-section="hero" id="hero"><h1 class="text-4xl">EN: Hello</h1></section>'


def fake_translate(html, source, target):
    return html.replace('PT:', f'{target.upper()}:')


def fake_directions(page, scope, target, instructions, **kw):
    chosen = kw.get('directions') or [{'key': 'refined', 'name': 'Close to current'}, {'key': 'bold', 'name': 'Bolder'},
                                      {'key': 'layout', 'name': 'New layout'}]
    items = []
    for d in chosen:
        if kw.get('is_cancelled') and kw['is_cancelled']():
            break
        item = {'key': d['key'], 'name': d['name'], 'html': f'<section data-section="hero">{d["name"]}</section>',
                'why': 'fits', 'notes': []}
        items.append(item)
        if kw.get('on_option'):
            kw['on_option'](item)
    return items


class ChatBase(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(title_i18n={'pt': 'Início', 'en': 'Home'}, slug_i18n={'pt': 'inicio', 'en': 'home'},
                                        is_active=True, html_content_i18n={'pt': HERO_PT, 'en': HERO_EN})
        PageVersion.objects.filter(page=self.page).delete()
        self.user = get_user_model().objects.create_superuser('a', 'a@x.com', 'pw')
        self.events = []

    def emit(self, event, data):
        self.events.append((event, data))

    def names(self):
        return [e for e, _d in self.events]

    def turn(self, instructions, handle=None, **kw):
        args = dict(scope='section', target='hero', instructions=instructions, mode='auto', lang='pt',
                    user=self.user, emit=self.emit)
        args.update(kw)
        with mock.patch(HANDLE, return_value=handle or {'delegate': True, 'assistant_message': '', 'routing_ms': 1}) as h, \
                mock.patch(DIRECTIONS, side_effect=fake_directions) as d, \
                mock.patch(TRANSLATE, side_effect=fake_translate), \
                mock.patch('djangopress.editor_v2.chat.build_design_context', return_value={
                    'colors': [{'name': 'Primary', 'value': '#C42014'}], 'fonts': [{'role': 'Headings', 'family': 'Fraunces'}],
                    'references': [{'label': 'Hero'}], 'vocabulary': [], 'images': [], 'design_guide': ''}):
            result = chat.run_turn(self.page, **args)
        self.handle, self.directions = h, d
        return result


class IntentTest(TestCase):
    def test_table(self):
        cases = {
            'Torna esta secção mais elegante': 'explore', 'Redesenha isto': 'explore',
            'quero ver 3 propostas': 'explore', 'Give me some ideas for this': 'explore',
            'make it more modern': 'explore', 'muda o layout': 'explore',
            'Título a dourado': 'quick', 'Make the title bigger': 'quick', 'menos espaço em cima': 'quick',
            'centra o texto': 'quick', 'button colour red': 'quick',
            'Título dourado e mais elegante': 'explore',    # explore wins
            'Olá': None,
        }
        for text, want in cases.items():
            self.assertEqual(chat.classify_intent(text), want, text)


class RunTurnTest(ChatBase):
    def test_an_open_request_streams_three_directions_and_saves_nothing(self):
        result = self.turn('Mais elegante')
        self.assertEqual([n for n in self.names() if n != 'step'], ['context', 'option', 'option', 'option'])
        self.assertEqual(self.events[[n for n in self.names()].index('context')][1]['matches']['references'], ['Hero'])
        self.assertEqual(result['mode'], 'explore')
        self.handle.assert_not_called()
        self.page.refresh_from_db()
        self.assertEqual(self.page.html_content_i18n['pt'], HERO_PT)

    def test_a_specific_request_is_applied_at_once_with_a_checkpoint(self):
        edited = HERO_PT.replace('text-4xl', 'text-6xl text-[#C9A961]')
        result = self.turn('Título dourado', handle={'options': [{'html': edited}], 'assistant_message': 'Done.',
                                                    'routing_tier': 'direct_edit'})
        applied = dict(self.events)['applied']
        self.assertIn('text-6xl', applied['html'])
        self.assertEqual(applied['translated'], ['en'])
        self.assertEqual(result['mode'], 'quick')
        self.page.refresh_from_db()
        self.assertIn('text-6xl', self.page.html_content_i18n['en'])
        self.assertEqual(PageVersion.objects.filter(page=self.page, kind='checkpoint').count(), 1)
        self.directions.assert_not_called()

    def test_auto_switches_to_directions_when_the_router_wants_a_new_design(self):
        result = self.turn('Faz qualquer coisa com isto')
        self.handle.assert_called_once()
        self.assertEqual(self.handle.call_args.kwargs['delegate'], False)
        self.assertEqual(self.names().count('option'), 3)
        self.assertEqual(result['mode'], 'explore')

    def test_explicit_quick_that_needs_generation_applies_one_result(self):
        result = self.turn('Faz qualquer coisa com isto', mode='quick')
        self.assertEqual(len(self.directions.call_args.kwargs['directions']), 1)
        self.assertIn('applied', self.names())
        self.assertEqual(result['mode'], 'quick')

    def test_a_follow_up_on_an_option_makes_one_new_version_and_saves_nothing(self):
        base = '<section data-section="hero">B</section>'
        self.turn('Gosto, mas com fundo escuro', base_html=base)
        self.assertEqual(self.directions.call_args.kwargs['base_html'], base)
        options = [d for e, d in self.events if e == 'option']
        self.assertEqual([o['key'] for o in options], ['next'])
        self.assertNotIn('applied', self.names())
        self.handle.assert_not_called()

    def test_stop_before_the_run(self):
        cancel.request_cancel('run-abcdef12')
        try:
            result = self.turn('Mais elegante', run_id='run-abcdef12')
        finally:
            cancel.clear('run-abcdef12')
        self.assertTrue(result['cancelled'])
        self.assertNotIn('option', self.names())

    def test_element_scope_uses_the_element_section_for_context(self):
        self.turn('Mais elegante', scope='element', target='section[data-section="hero"] > h1')
        self.assertEqual(self.directions.call_args.args[1:3], ('element', 'section[data-section="hero"] > h1'))


class EndpointTest(ChatBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def stream(self, body, files=None, handle=None):
        def run_now(fn):
            fn()
        with mock.patch.object(chat_views, '_start_worker', side_effect=run_now), \
                mock.patch(HANDLE, return_value=handle or {'delegate': True, 'assistant_message': '', 'routing_ms': 1}), \
                mock.patch(DIRECTIONS, side_effect=fake_directions) as d, \
                mock.patch(TRANSLATE, side_effect=fake_translate), \
                mock.patch('djangopress.editor_v2.chat.build_design_context', return_value={'colors': [], 'fonts': [],
                                                                                             'references': []}):
            payload = {'page_id': self.page.id, 'scope': 'section', 'section_name': 'hero', 'mode': 'auto', **body}
            if files is None:
                res = self.client.post('/editor-v2/api/chat/stream/', data=json.dumps(payload),
                                       content_type='application/json', HTTP_REFERER='http://testserver/pt/?edit=v2')
            else:
                res = self.client.post('/editor-v2/api/chat/stream/', data={'payload': json.dumps(payload),
                                                                            'reference_images': files},
                                       HTTP_REFERER='http://testserver/pt/?edit=v2')
            text = b''.join(res.streaming_content).decode()
        self.directions = d
        events = []
        for block in text.split('\n\n'):
            lines = block.strip().split('\n')
            name = next((l[6:].strip() for l in lines if l.startswith('event:')), 'message')
            data = next((l[5:].strip() for l in lines if l.startswith('data:')), None)
            if data:
                events.append((name, json.loads(data)))
        return events

    def test_explore_streams_and_records_the_conversation(self):
        events = self.stream({'instructions': 'Mais elegante'})
        names = [e for e, _d in events]
        self.assertEqual(names.count('option'), 3)
        self.assertEqual(names[-1], 'complete')
        session = RefinementSession.objects.get(id=events[-1][1]['session_id'])
        self.assertEqual([m['role'] for m in session.messages], ['user', 'assistant'])
        self.assertIn('Bolder', session.messages[-1]['content'])

    def test_reference_images_reach_the_turn(self):
        files = [SimpleUploadedFile(f'r{i}.png', b'\x89PNG' + bytes(10), content_type='image/png') for i in range(2)]
        self.stream({'instructions': 'Neste estilo'}, files=files)
        images = self.directions.call_args.kwargs['images']
        self.assertEqual(len(images), 2)
        self.assertEqual(images[0]['mime_type'], 'image/png')
        self.assertTrue(images[0]['bytes'].startswith(b'\x89PNG'))

    def test_too_many_or_wrong_files_are_refused(self):
        six = [SimpleUploadedFile(f'r{i}.png', b'x', content_type='image/png') for i in range(6)]
        self.assertEqual(self.stream({'instructions': 'x'}, files=six)[0][0], 'error')
        pdf = [SimpleUploadedFile('a.pdf', b'x', content_type='application/pdf')]
        self.assertEqual(self.stream({'instructions': 'x'}, files=pdf)[0][0], 'error')

    def test_a_news_post(self):
        from djangopress.news.models import NewsPost
        post = NewsPost.objects.create(title_i18n={'pt': 'N'}, slug_i18n={'pt': 'n'}, html_content_i18n={'pt': HERO_PT})
        ct = ContentType.objects.get_for_model(post)
        events = self.stream({'instructions': 'Mais elegante', 'page_id': None, 'content_type_id': ct.id,
                              'object_id': post.pk})
        self.assertEqual(events[-1][0], 'complete', events)
        session = RefinementSession.objects.get(id=events[-1][1]['session_id'])
        self.assertEqual((session.content_type, session.object_id), (ct, post.pk))
        self.assertIs(self.directions.call_args.args[0].__class__, NewsPost)

    def test_missing_target_is_an_error(self):
        events = self.stream({'instructions': 'x', 'section_name': ''})
        self.assertEqual(events[0][0], 'error')

    def test_editors_who_are_not_superusers_are_refused(self):
        editor = get_user_model().objects.create_user('e', 'e@x.com', 'pw', is_staff=True)
        self.client.force_login(editor)
        res = self.client.post('/editor-v2/api/chat/stream/', data='{}', content_type='application/json')
        self.assertIn(res.status_code, (302, 403))

    def test_cancel_endpoint_sets_the_flag(self):
        res = self.client.post('/editor-v2/api/chat/cancel/', data=json.dumps({'run_id': 'run-12345678'}),
                               content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(cancel.is_cancelled('run-12345678'))
        cancel.clear('run-12345678')
        bad = self.client.post('/editor-v2/api/chat/cancel/', data=json.dumps({'run_id': '../x'}),
                               content_type='application/json')
        self.assertEqual(bad.status_code, 400)


class OldEndpointsTest(ChatBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_apply_option_returns_the_saved_html(self):
        with mock.patch(TRANSLATE, side_effect=fake_translate):
            res = self.client.post('/editor-v2/api/apply-option/', data=json.dumps({
                'page_id': self.page.id, 'scope': 'section', 'section_name': 'hero',
                'html': '<section data-section="hero" id="hero"><h1>PT: Novo</h1></section>'}),
                content_type='application/json', HTTP_REFERER='http://testserver/pt/?edit=v2')
        self.assertIn('PT: Novo', res.json()['html'])

    def test_refine_multi_stream_works_for_a_news_post(self):
        from djangopress.news.models import NewsPost
        post = NewsPost.objects.create(title_i18n={'pt': 'N'}, slug_i18n={'pt': 'n'}, html_content_i18n={'pt': HERO_PT})
        ct = ContentType.objects.get_for_model(post)

        class Now:
            def __init__(self, target, daemon=None):
                self.target = target

            def start(self):
                self.target()

        with mock.patch('djangopress.editor_v2.api_views.threading.Thread', Now), \
                mock.patch(HANDLE, return_value={'options': [{'html': HERO_PT}], 'assistant_message': 'ok'}):
            res = self.client.post('/editor-v2/api/refine-multi/stream/', data=json.dumps({
                'content_type_id': ct.id, 'object_id': post.pk, 'scope': 'section', 'section_name': 'hero',
                'instructions': 'x'}), content_type='application/json', HTTP_REFERER='http://testserver/pt/?edit=v2')
            text = b''.join(res.streaming_content).decode()
        self.assertIn('event: complete', text)
        self.assertNotIn('not found', text)


class ContextEndpointTest(ChatBase):
    def test_matches_for_a_section_before_any_request(self):
        self.client.force_login(self.user)
        with mock.patch('djangopress.editor_v2.chat_views.build_design_context',
                        return_value={'colors': [{'name': 'P', 'value': '#C42014'}], 'fonts': [{'role': 'Body', 'family': 'Inter'}],
                                      'references': [{'label': 'Hero'}]}) as build:
            res = self.client.get('/editor-v2/api/chat/context/', {'page_id': self.page.id, 'scope': 'section',
                                                                   'section_name': 'hero'})
        self.assertEqual(res.json()['matches'], {'colors': ['#C42014'], 'fonts': ['Inter'], 'references': ['Hero']})
        self.assertEqual(build.call_args.args[1], 'hero')

    def test_element_uses_its_section(self):
        self.client.force_login(self.user)
        with mock.patch('djangopress.editor_v2.chat_views.build_design_context',
                        return_value={'colors': [], 'fonts': [], 'references': []}) as build:
            self.client.get('/editor-v2/api/chat/context/', {'page_id': self.page.id, 'scope': 'element',
                                                             'selector': 'section[data-section="hero"] > h1'})
        self.assertEqual(build.call_args.args[1], 'hero')
