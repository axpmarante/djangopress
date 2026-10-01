"""Stopping a running assistant turn, and editing the last message."""
import json
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from djangopress.core.models import SiteSettings
from djangopress.site_assistant import cancel
from djangopress.site_assistant.models import AssistantSession
from djangopress.site_assistant.services import AssistantService

ROUTER = 'djangopress.site_assistant.services.Router.classify'


def fc_response(name):
    part = SimpleNamespace(function_call=SimpleNamespace(name=name, args={}), text=None)
    return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(role='model', parts=[part]))])


class CancelFlagTest(TestCase):
    def test_flag_round_trip(self):
        self.assertFalse(cancel.is_cancelled('run-abc12345'))
        cancel.request_cancel('run-abc12345')
        self.assertTrue(cancel.is_cancelled('run-abc12345'))
        cancel.clear('run-abc12345')
        self.assertFalse(cancel.is_cancelled('run-abc12345'))

    def test_bad_ids_are_ignored(self):
        cancel.request_cancel('../../etc/passwd')
        self.assertFalse(cancel.is_cancelled('../../etc/passwd'))
        self.assertFalse(cancel.is_cancelled(None))


class StopTest(TestCase):
    def setUp(self):
        SiteSettings.load()
        self.user = get_user_model().objects.create_superuser('a', 'a@x.com', 'pw')
        self.session = AssistantSession.objects.create(created_by=self.user)

    def tearDown(self):
        cancel.clear('run-stop0001')

    def test_stopped_before_it_starts_makes_no_ai_call(self):
        cancel.request_cancel('run-stop0001')
        service = AssistantService(self.session)
        with mock.patch(ROUTER) as router, mock.patch.object(service.llm, 'get_completion_with_tools') as llm:
            result = service.handle_message('Muda o título', user=self.user, run_id='run-stop0001')
        router.assert_not_called()
        llm.assert_not_called()
        self.assertTrue(result['stopped'])

    def test_stop_during_the_loop_skips_the_next_step(self):
        service = AssistantService(self.session)

        def first_call(**kwargs):
            cancel.request_cancel('run-stop0001')     # operator clicks Stop while the model works
            return fc_response('list_pages')

        router = {'intents': ['pages'], 'needs_active_page': False, 'direct_response': None}
        with mock.patch(ROUTER, return_value=router), \
                mock.patch.object(service.llm, 'get_completion_with_tools', side_effect=first_call) as llm, \
                mock.patch('djangopress.site_assistant.services.ToolRegistry.execute') as tool:
            result = service.handle_message('Lista as páginas e muda tudo', user=self.user, run_id='run-stop0001')
        self.assertEqual(llm.call_count, 1)
        tool.assert_not_called()                      # the pending tool call is not executed
        self.assertTrue(result['stopped'])
        self.assertIn('Stopped', self.session.messages[-1]['content'])


class ApiTest(TestCase):
    def setUp(self):
        SiteSettings.load()
        self.client.force_login(get_user_model().objects.create_superuser('a', 'a@x.com', 'pw'))

    def test_cancel_endpoint(self):
        res = self.client.post('/site-assistant/api/cancel/', data=json.dumps({'run_id': 'run-api00001'}),
                               content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(cancel.is_cancelled('run-api00001'))
        cancel.clear('run-api00001')

    def test_cancel_endpoint_is_superuser_only(self):
        self.client.force_login(get_user_model().objects.create_user('s', 's@x.com', 'pw', is_staff=True))
        res = self.client.post('/site-assistant/api/cancel/', data=json.dumps({'run_id': 'run-api00002'}),
                               content_type='application/json')
        self.assertNotEqual(res.status_code, 200)
        self.assertFalse(cancel.is_cancelled('run-api00002'))

    def test_edit_replaces_the_last_turn(self):
        user = get_user_model().objects.get(username='a')
        session = AssistantSession.objects.create(created_by=user, messages=[
            {'role': 'user', 'content': 'primeira'}, {'role': 'assistant', 'content': 'ok 1'},
            {'role': 'user', 'content': 'pedido errado'}, {'role': 'assistant', 'content': 'feito errado'},
        ])
        reply = {'response': 'feito certo', 'actions': [], 'steps': [], 'set_active_page': None}

        def handle(svc, message, **kwargs):
            svc.session.add_message('user', message)
            svc.session.add_message('assistant', 'feito certo')
            return reply
        with mock.patch('djangopress.site_assistant.services.AssistantService.handle_message', autospec=True, side_effect=handle):
            res = self.client.post('/site-assistant/api/chat/', data=json.dumps(
                {'message': 'pedido certo', 'session_id': session.id, 'replace_last': True}), content_type='application/json')
        self.assertEqual(res.status_code, 200, res.content)
        session.refresh_from_db()
        self.assertEqual([m['content'] for m in session.messages], ['primeira', 'ok 1', 'pedido certo', 'feito certo'])


def text_response(text):
    part = SimpleNamespace(function_call=None, text=text)
    return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(role='model', parts=[part]))])


class ReportTest(TestCase):
    ROUTER_RESULT = {'intents': ['pages'], 'needs_active_page': False, 'direct_response': None}

    def setUp(self):
        SiteSettings.load()
        self.user = get_user_model().objects.create_superuser('a', 'a@x.com', 'pw')
        self.session = AssistantSession.objects.create(created_by=self.user)

    def test_failed_steps_are_always_reported(self):
        service = AssistantService(self.session)
        replies = [fc_response('refine_section'), text_response('Adicionei a secção sobre o livro.')]
        failed = {'success': False, 'message': 'Tool error: [Errno 32] Broken pipe'}
        with mock.patch(ROUTER, return_value=self.ROUTER_RESULT), \
                mock.patch.object(service.llm, 'get_completion_with_tools', side_effect=replies), \
                mock.patch('djangopress.site_assistant.services.ToolRegistry.execute', return_value=failed):
            result = service.handle_message('Cria uma secção sobre o livro do chef', user=self.user)
        self.assertIn('Not done', result['response'])
        self.assertIn('Broken pipe', result['response'])

    def test_running_out_of_steps_lists_what_was_and_was_not_done(self):
        service = AssistantService(self.session)
        outcomes = iter([{'success': True, 'message': 'Updated classes on the hero title'},
                         {'success': False, 'message': 'Tool error: timeout'}] * 10)
        with mock.patch(ROUTER, return_value=self.ROUTER_RESULT), \
                mock.patch.object(service.llm, 'get_completion_with_tools', side_effect=lambda **k: fc_response('update_element_styles')), \
                mock.patch('djangopress.site_assistant.services.ToolRegistry.execute', side_effect=lambda *a, **k: next(outcomes)):
            result = service.handle_message('Faz tudo', user=self.user)
        self.assertNotIn('I completed the available operations', result['response'])
        self.assertIn('Done', result['response'])
        self.assertIn('Not done', result['response'])
        self.assertIn('timeout', result['response'])

    def test_prompt_asks_for_a_summary_and_a_question_when_unclear(self):
        from djangopress.site_assistant.prompts import build_executor_prompt, build_router_snapshot
        prompt = build_executor_prompt(self.session, build_router_snapshot(self.session))
        self.assertIn('what you did NOT do', prompt)
        self.assertIn('ask ONE short question', prompt)


class AttachmentsTest(TestCase):
    def setUp(self):
        SiteSettings.load()
        self.user = get_user_model().objects.create_superuser('a', 'a@x.com', 'pw')
        self.session = AssistantSession.objects.create(created_by=self.user)

    def test_attached_images_reach_the_chat_model(self):
        service = AssistantService(self.session)
        router = {'intents': ['pages'], 'needs_active_page': False, 'direct_response': None}
        png = b'\x89PNG\r\n\x1a\n' + b'0' * 20
        with mock.patch(ROUTER, return_value=router), \
                mock.patch.object(service.llm, 'get_completion_with_tools', return_value=text_response('Vejo azul.')) as llm:
            service.handle_message('Que cores vês?', user=self.user,
                                   reference_images=[{'bytes': png, 'mime_type': 'image/png'}])
        last = llm.call_args.kwargs['contents'][-1]
        kinds = [('image' if getattr(p, 'inline_data', None) else 'text') for p in last.parts]
        self.assertEqual(kinds, ['text', 'image'])

    def test_stop_after_only_reading_says_nothing_changed(self):
        service = AssistantService(self.session)
        service._run_id = 'run-read0001'
        result = service._stopped([{'tool': 'get_page_info', 'success': True, 'message': 'x'}], [], None)
        self.assertIn('Nothing was changed', result['response'])
