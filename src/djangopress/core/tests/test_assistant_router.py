"""Tests for site_assistant.router — intent classification."""

from unittest.mock import patch, MagicMock
from django.test import TestCase
from site_assistant.router import Router


class RouterClassifyTest(TestCase):

    def setUp(self):
        from core.models import SiteSettings
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}]
        s.default_language = 'pt'
        s.save()

    @patch('site_assistant.router.LLMBase')
    def test_greeting_returns_direct_response(self, MockLLM):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"intents":["greeting"],"needs_active_page":false,"direct_response":"Olá!"}'
        MockLLM.return_value.get_completion.return_value = mock_response

        result = Router.classify('hi', snapshot={'default_language': 'pt', 'site_name': 'Test', 'pages': []}, history='')
        self.assertEqual(result['direct_response'], 'Olá!')
        self.assertIn('greeting', result['intents'])

    @patch('site_assistant.router.LLMBase')
    def test_page_edit_returns_intents(self, MockLLM):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"intents":["page_edit"],"needs_active_page":true,"direct_response":null}'
        MockLLM.return_value.get_completion.return_value = mock_response

        result = Router.classify('change the hero title', snapshot={'default_language': 'pt', 'site_name': 'Test', 'pages': []}, history='')
        self.assertIn('page_edit', result['intents'])
        self.assertTrue(result['needs_active_page'])
        self.assertIsNone(result['direct_response'])

    @patch('site_assistant.router.LLMBase')
    def test_multi_intent(self, MockLLM):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"intents":["pages","navigation"],"needs_active_page":false,"direct_response":null}'
        MockLLM.return_value.get_completion.return_value = mock_response

        result = Router.classify('create a new page and add it to the menu', snapshot={'default_language': 'pt', 'site_name': 'Test', 'pages': []}, history='')
        self.assertIn('pages', result['intents'])
        self.assertIn('navigation', result['intents'])

    @patch('site_assistant.router.LLMBase')
    def test_fallback_on_error(self, MockLLM):
        MockLLM.return_value.get_completion.side_effect = Exception('API error')
        result = Router.classify('test', snapshot={'default_language': 'pt', 'site_name': 'Test', 'pages': []}, history='')
        self.assertIsNone(result['direct_response'])
        self.assertTrue(len(result['intents']) > 0)

    @patch('site_assistant.router.LLMBase')
    def test_malformed_json_fallback(self, MockLLM):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = 'not json at all'
        MockLLM.return_value.get_completion.return_value = mock_response

        result = Router.classify('test', snapshot={'default_language': 'pt', 'site_name': 'Test', 'pages': []}, history='')
        self.assertIsNone(result['direct_response'])
        self.assertTrue(len(result['intents']) > 0)
