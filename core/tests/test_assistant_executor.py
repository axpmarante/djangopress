"""Tests for the site assistant executor — Phase 1 + Phase 2 flow.

Tests cover:
- Prompt builders (build_router_snapshot, build_executor_prompt, build_active_page_context)
- AssistantService.handle_message() two-phase flow
- Destructive action safety net in ToolRegistry
- Native FC loop with tool execution
"""

from unittest.mock import patch, MagicMock, PropertyMock
from django.test import TestCase
from django.contrib.auth import get_user_model

from core.models import Page, SiteSettings
from site_assistant.models import AssistantSession
from site_assistant.prompts import (
    build_active_page_context, build_router_snapshot, build_executor_prompt,
)
from site_assistant.services import AssistantService, PAGE_CONTEXT_MUTATIONS
from site_assistant.tools import (
    ToolRegistry, DESTRUCTIVE_TOOLS, _has_recent_confirmation,
)

User = get_user_model()


class BuildActivePageContextTest(TestCase):

    def test_no_page_returns_no_content(self):
        result = build_active_page_context(None)
        self.assertEqual(result, "Page has no content yet.")

    def test_empty_html_returns_no_content(self):
        page = MagicMock()
        page.html_content_i18n = {}
        result = build_active_page_context(page)
        self.assertEqual(result, "Page has no content yet.")

    def test_page_with_sections(self):
        page = MagicMock()
        page.html_content_i18n = {
            'pt': '<section data-section="hero" id="hero"><h1>Bem-vindo</h1></section>'
                  '<section data-section="features" id="features"><p>Coisas</p></section>',
        }
        result = build_active_page_context(page)
        self.assertIn('`hero`', result)
        self.assertIn('`features`', result)
        self.assertIn('Languages: pt', result)

    def test_page_with_no_sections(self):
        page = MagicMock()
        page.html_content_i18n = {'pt': '<div>Just a div</div>'}
        result = build_active_page_context(page)
        self.assertEqual(result, "Page has content but no structured sections found.")


class BuildRouterSnapshotTest(TestCase):

    def setUp(self):
        Page.objects.all().delete()
        s = SiteSettings.load()
        s.site_name_i18n = {'pt': 'Teste'}
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(
            title_i18n={'pt': 'Home'},
            slug_i18n={'pt': 'home'},
            is_active=True,
        )

    def test_snapshot_includes_pages(self):
        session = MagicMock()
        session.active_page = None
        snapshot = build_router_snapshot(session)
        self.assertIn('pages', snapshot)
        self.assertTrue(len(snapshot['pages']) >= 1)

    def test_snapshot_includes_active_page(self):
        session = MagicMock()
        session.active_page = self.page
        snapshot = build_router_snapshot(session)
        self.assertIn(f'#{self.page.id}', snapshot['active_page'])

    def test_snapshot_no_active_page(self):
        session = MagicMock()
        session.active_page = None
        snapshot = build_router_snapshot(session)
        self.assertEqual(snapshot['active_page'], 'none selected')

    def test_snapshot_includes_installed_apps(self):
        session = MagicMock()
        session.active_page = None
        snapshot = build_router_snapshot(session)
        self.assertIn('installed_apps', snapshot)
        self.assertIsInstance(snapshot['installed_apps'], list)


class BuildExecutorPromptTest(TestCase):

    def setUp(self):
        Page.objects.all().delete()
        s = SiteSettings.load()
        s.site_name_i18n = {'pt': 'Meu Site'}
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}, {'code': 'en', 'name': 'EN'}]
        s.default_language = 'pt'
        s.save()

    def test_prompt_includes_site_name(self):
        session = MagicMock()
        session.active_page = None
        snapshot = build_router_snapshot(session)
        prompt = build_executor_prompt(session, snapshot)
        self.assertIn('Meu Site', prompt)

    def test_prompt_includes_languages(self):
        session = MagicMock()
        session.active_page = None
        snapshot = build_router_snapshot(session)
        prompt = build_executor_prompt(session, snapshot)
        self.assertIn('pt', prompt)
        self.assertIn('en', prompt)

    def test_prompt_no_active_page(self):
        session = MagicMock()
        session.active_page = None
        snapshot = build_router_snapshot(session)
        prompt = build_executor_prompt(session, snapshot)
        self.assertIn('No Active Page', prompt)

    def test_prompt_with_active_page(self):
        page = Page.objects.create(
            title_i18n={'pt': 'Contacto', 'en': 'Contact'},
            slug_i18n={'pt': 'contacto', 'en': 'contact'},
            html_content_i18n={'pt': '<section data-section="hero"><h1>Hello</h1></section>'},
        )
        session = MagicMock()
        session.active_page = page
        snapshot = build_router_snapshot(session)
        prompt = build_executor_prompt(session, snapshot)
        self.assertIn('Active Page', prompt)
        self.assertIn('Contacto', prompt)

    def test_prompt_includes_behavior_rules(self):
        session = MagicMock()
        session.active_page = None
        snapshot = build_router_snapshot(session)
        prompt = build_executor_prompt(session, snapshot)
        self.assertIn('LIGHTEST tool', prompt)
        self.assertIn('NEVER call delete tools directly', prompt)

    def test_prompt_includes_what_cannot_do(self):
        session = MagicMock()
        session.active_page = None
        snapshot = build_router_snapshot(session)
        prompt = build_executor_prompt(session, snapshot)
        self.assertIn('/backoffice/ai/', prompt)
        self.assertIn('/backoffice/media/', prompt)


class DestructiveActionSafetyNetTest(TestCase):

    def setUp(self):
        Page.objects.all().delete()
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}]
        s.default_language = 'pt'
        s.save()
        self.page = Page.objects.create(
            title_i18n={'pt': 'Test'},
            slug_i18n={'pt': 'test'},
        )

    def test_destructive_tools_set(self):
        """Verify the set of destructive tools."""
        self.assertIn('delete_page', DESTRUCTIVE_TOOLS)
        self.assertIn('delete_menu_item', DESTRUCTIVE_TOOLS)
        self.assertIn('delete_form', DESTRUCTIVE_TOOLS)

    def test_has_recent_confirmation_with_yes(self):
        session = MagicMock()
        session.messages = [
            {'role': 'user', 'content': 'delete the test page'},
            {'role': 'assistant', 'content': 'Are you sure you want to delete "Test"?'},
            {'role': 'user', 'content': 'yes'},
        ]
        context = {'session': session}
        self.assertTrue(_has_recent_confirmation(context))

    def test_has_recent_confirmation_with_sim(self):
        session = MagicMock()
        session.messages = [
            {'role': 'user', 'content': 'sim, confirmo'},
        ]
        context = {'session': session}
        self.assertTrue(_has_recent_confirmation(context))

    def test_has_recent_confirmation_with_no_confirmation(self):
        session = MagicMock()
        session.messages = [
            {'role': 'user', 'content': 'delete the test page'},
        ]
        context = {'session': session}
        self.assertFalse(_has_recent_confirmation(context))

    def test_has_recent_confirmation_empty_session(self):
        session = MagicMock()
        session.messages = []
        context = {'session': session}
        self.assertFalse(_has_recent_confirmation(context))

    def test_execute_blocks_destructive_without_confirmation(self):
        session = MagicMock()
        session.messages = [
            {'role': 'user', 'content': 'delete the test page'},
        ]
        context = {'session': session, 'active_page': None, 'user': None}
        result = ToolRegistry.execute('delete_page', {'page_id': self.page.id}, context)
        self.assertFalse(result['success'])
        self.assertIn('BLOCKED', result['message'])

    def test_execute_allows_destructive_with_confirmation(self):
        session = MagicMock()
        session.messages = [
            {'role': 'user', 'content': 'delete the test page'},
            {'role': 'assistant', 'content': 'Are you sure?'},
            {'role': 'user', 'content': 'yes, confirm'},
        ]
        session.active_page_id = None
        context = {'session': session, 'active_page': None, 'user': None}
        result = ToolRegistry.execute('delete_page', {'page_id': self.page.id}, context)
        self.assertTrue(result['success'])
        # Page should actually be deleted
        self.assertFalse(Page.objects.filter(pk=self.page.id).exists())

    def test_non_destructive_tool_not_blocked(self):
        context = {'session': MagicMock(), 'active_page': None, 'user': None}
        result = ToolRegistry.execute('list_pages', {}, context)
        self.assertTrue(result['success'])


class AssistantServiceDirectResponseTest(TestCase):
    """Test that Phase 1 direct responses skip Phase 2."""

    def setUp(self):
        Page.objects.all().delete()
        s = SiteSettings.load()
        s.site_name_i18n = {'pt': 'Teste'}
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}]
        s.default_language = 'pt'
        s.save()
        self.user = User.objects.create_user(username='testadmin', password='pass', is_superuser=True)
        self.session = AssistantSession.objects.create(
            created_by=self.user,
            model_used='gemini-flash',
        )

    @patch('site_assistant.services.Router.classify')
    def test_direct_response_returns_without_fc(self, mock_classify):
        mock_classify.return_value = {
            'intents': ['greeting'],
            'needs_active_page': False,
            'direct_response': 'Hello!',
        }
        service = AssistantService(self.session)
        result = service.handle_message('hi', user=self.user)

        self.assertEqual(result['response'], 'Hello!')
        self.assertEqual(result['actions'], [])
        self.assertEqual(result['steps'], [])
        self.assertIsNone(result['set_active_page'])


class AssistantServiceFCLoopTest(TestCase):
    """Test the Phase 2 native FC loop."""

    def setUp(self):
        Page.objects.all().delete()
        s = SiteSettings.load()
        s.site_name_i18n = {'pt': 'Teste'}
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}]
        s.default_language = 'pt'
        s.save()
        self.user = User.objects.create_user(
            username='testadmin2', password='pass', is_superuser=True
        )
        self.session = AssistantSession.objects.create(
            created_by=self.user,
            model_used='gemini-flash',
        )

    def _make_fc_response(self, function_calls=None, text=None):
        """Helper to build a mock Gemini FC response."""
        mock_response = MagicMock()
        parts = []

        if function_calls:
            for name, args in function_calls:
                part = MagicMock()
                part.function_call = MagicMock()
                part.function_call.name = name
                part.function_call.args = args
                part.text = None
                parts.append(part)

        if text:
            part = MagicMock()
            part.function_call = None
            part.text = text
            parts.append(part)

        content = MagicMock()
        content.parts = parts
        content.role = 'model'

        candidate = MagicMock()
        candidate.content = content

        mock_response.candidates = [candidate]
        return mock_response

    @patch('site_assistant.services.Router.classify')
    @patch('site_assistant.services.LLMBase')
    def test_text_only_response(self, MockLLM, mock_classify):
        """LLM returns text without function calls."""
        mock_classify.return_value = {
            'intents': ['pages'],
            'needs_active_page': False,
            'direct_response': None,
        }

        # LLM returns a text response (no FC)
        text_response = self._make_fc_response(text='You have 3 pages.')
        MockLLM.return_value.get_completion_with_tools.return_value = text_response

        service = AssistantService(self.session)
        result = service.handle_message('how many pages?', user=self.user)

        self.assertEqual(result['response'], 'You have 3 pages.')
        self.assertEqual(result['actions'], [])
        self.assertEqual(result['steps'], [])

    @patch('site_assistant.services.Router.classify')
    @patch('site_assistant.services.LLMBase')
    def test_single_tool_call_then_text(self, MockLLM, mock_classify):
        """LLM calls a tool, gets result, then responds with text."""
        mock_classify.return_value = {
            'intents': ['pages'],
            'needs_active_page': False,
            'direct_response': None,
        }

        # First call: LLM makes a function call
        fc_response = self._make_fc_response(
            function_calls=[('list_pages', {})]
        )
        # Second call: LLM responds with text
        text_response = self._make_fc_response(text='Here are your pages.')

        MockLLM.return_value.get_completion_with_tools.side_effect = [
            fc_response, text_response
        ]

        # Create a test page so list_pages returns data
        Page.objects.create(
            title_i18n={'pt': 'Home'},
            slug_i18n={'pt': 'home'},
            is_active=True,
        )

        service = AssistantService(self.session)
        result = service.handle_message('list my pages', user=self.user)

        self.assertEqual(result['response'], 'Here are your pages.')
        self.assertEqual(len(result['actions']), 1)
        self.assertEqual(result['actions'][0]['tool'], 'list_pages')
        self.assertTrue(result['actions'][0]['success'])
        self.assertEqual(len(result['steps']), 1)

    @patch('site_assistant.services.Router.classify')
    @patch('site_assistant.services.LLMBase')
    def test_llm_error_returns_error_message(self, MockLLM, mock_classify):
        mock_classify.return_value = {
            'intents': ['pages'],
            'needs_active_page': False,
            'direct_response': None,
        }

        MockLLM.return_value.get_completion_with_tools.side_effect = Exception('API error')

        service = AssistantService(self.session)
        result = service.handle_message('list pages', user=self.user)

        self.assertIn('error', result['response'].lower())
        self.assertEqual(result['actions'], [])

    @patch('site_assistant.services.Router.classify')
    @patch('site_assistant.services.LLMBase')
    def test_request_additional_tools(self, MockLLM, mock_classify):
        """LLM requests additional tool categories via meta-tool."""
        mock_classify.return_value = {
            'intents': ['pages'],
            'needs_active_page': False,
            'direct_response': None,
        }

        # First call: request additional tools
        fc_response = self._make_fc_response(
            function_calls=[('request_additional_tools', {'categories': ['navigation']})]
        )
        # Second call: text response
        text_response = self._make_fc_response(text='Done.')

        MockLLM.return_value.get_completion_with_tools.side_effect = [
            fc_response, text_response
        ]

        service = AssistantService(self.session)
        result = service.handle_message('also check my menu', user=self.user)

        self.assertEqual(result['response'], 'Done.')
        self.assertEqual(len(result['actions']), 1)
        self.assertEqual(result['actions'][0]['tool'], 'request_additional_tools')

    @patch('site_assistant.services.Router.classify')
    @patch('site_assistant.services.LLMBase')
    def test_no_candidates_returns_error(self, MockLLM, mock_classify):
        mock_classify.return_value = {
            'intents': ['pages'],
            'needs_active_page': False,
            'direct_response': None,
        }

        mock_response = MagicMock()
        mock_response.candidates = []
        MockLLM.return_value.get_completion_with_tools.return_value = mock_response

        service = AssistantService(self.session)
        result = service.handle_message('hello', user=self.user)

        self.assertEqual(result['response'], 'No response from the model.')

    @patch('site_assistant.services.Router.classify')
    @patch('site_assistant.services.LLMBase')
    def test_auto_title_on_first_exchange(self, MockLLM, mock_classify):
        mock_classify.return_value = {
            'intents': ['greeting'],
            'needs_active_page': False,
            'direct_response': 'Hi there!',
        }

        service = AssistantService(self.session)
        result = service.handle_message('Hello, how are you?', user=self.user)

        self.session.refresh_from_db()
        self.assertEqual(self.session.title, 'Hello, how are you?')


class AssistantServiceBuildContentsTest(TestCase):
    """Test the _build_contents method."""

    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}]
        s.default_language = 'pt'
        s.save()
        self.user = User.objects.create_user(
            username='testadmin3', password='pass', is_superuser=True
        )
        self.session = AssistantSession.objects.create(
            created_by=self.user,
            model_used='gemini-flash',
        )

    def test_empty_history(self):
        """With no history, just the current message."""
        self.session.add_message('user', 'hello')
        service = AssistantService(self.session)
        contents = service._build_contents('hello')

        # Should have just one user content (current message)
        self.assertEqual(len(contents), 1)
        self.assertEqual(contents[0].role, 'user')

    def test_with_history(self):
        """With previous messages, build proper alternating contents."""
        self.session.add_message('user', 'first message')
        self.session.add_message('assistant', 'first reply')
        self.session.add_message('user', 'second message')  # current message

        service = AssistantService(self.session)
        contents = service._build_contents('second message')

        # Should have: user (first), model (reply), user (current)
        self.assertEqual(len(contents), 3)
        self.assertEqual(contents[0].role, 'user')
        self.assertEqual(contents[1].role, 'model')
        self.assertEqual(contents[2].role, 'user')


class PageContextMutationsTest(TestCase):
    """Verify the PAGE_CONTEXT_MUTATIONS set."""

    def test_expected_mutations(self):
        expected = {
            'set_active_page', 'create_page',
            'refine_section', 'refine_page',
            'remove_section', 'reorder_sections',
            'update_element_styles', 'update_element_attribute',
            'refine_header', 'refine_footer',
        }
        self.assertEqual(PAGE_CONTEXT_MUTATIONS, expected)
