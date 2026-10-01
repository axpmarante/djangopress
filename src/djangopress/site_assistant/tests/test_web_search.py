"""Web search with sources, and no invented facts."""
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from djangopress.ai.utils.llm_config import LLMBase, ModelProvider
from djangopress.core.models import SiteSettings
from djangopress.site_assistant.models import AssistantSession
from djangopress.site_assistant.tool_declarations import build_tool_declarations
from djangopress.site_assistant.tools import site_tools


def grounded_response():
    chunk = lambda title, uri: SimpleNamespace(web=SimpleNamespace(title=title, uri=uri))
    meta = SimpleNamespace(web_search_queries=['livro leonel pereira'],
                           grounding_chunks=[chunk('postal.pt', 'https://x/1'), chunk('postal.pt', 'https://x/1'),
                                             chunk('ulisboa.pt', 'https://x/2')])
    return SimpleNamespace(text='Autores: Leonel Pereira, Hugo Pereira e João Navalho.',
                           candidates=[SimpleNamespace(grounding_metadata=meta, finish_reason=None)],
                           usage_metadata=None)


class FakeModels:
    def __init__(self):
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append(config)
        return grounded_response()


class WebSearchTest(TestCase):
    def test_llm_web_search_uses_google_search_and_returns_sources(self):
        models = FakeModels()
        with mock.patch.dict(LLMBase._clients, {ModelProvider.GOOGLE: SimpleNamespace(models=models)}):
            result = LLMBase().web_search('livro do chef')
        self.assertTrue(any(getattr(t, 'google_search', None) for t in models.calls[0].tools))
        self.assertIn('Leonel Pereira', result['text'])
        self.assertEqual(result['sources'], [{'title': 'postal.pt', 'url': 'https://x/1'},
                                             {'title': 'ulisboa.pt', 'url': 'https://x/2'}])

    def test_tool_returns_answer_and_sources(self):
        found = {'text': 'Autores: ...', 'sources': [{'title': 'postal.pt', 'url': 'https://x/1'}], 'queries': []}
        with mock.patch.object(LLMBase, 'web_search', return_value=found):
            out = site_tools.web_search({'query': 'livro do chef'}, {})
        self.assertTrue(out['success'])
        self.assertEqual(out['sources'], found['sources'])

    def test_tool_reports_failure(self):
        with mock.patch.object(LLMBase, 'web_search', side_effect=RuntimeError('quota')):
            out = site_tools.web_search({'query': 'x'}, {})
        self.assertFalse(out['success'])

    def test_web_search_is_always_available(self):
        names = [d.name for d in build_tool_declarations(['pages'])[0].function_declarations]
        self.assertIn('web_search', names)

    def test_prompt_forbids_invented_facts(self):
        from djangopress.site_assistant.prompts import build_executor_prompt, build_router_snapshot
        SiteSettings.load()
        user = get_user_model().objects.create_superuser('a', 'a@x.com', 'pw')
        session = AssistantSession.objects.create(created_by=user)
        prompt = build_executor_prompt(session, build_router_snapshot(session))
        self.assertIn('Never invent facts', prompt)
        self.assertIn('web_search', prompt)


class RouterRuleTest(TestCase):
    def test_router_sends_outside_facts_to_the_executor(self):
        from djangopress.site_assistant.router import ROUTER_PROMPT
        self.assertIn('facts outside the site', ROUTER_PROMPT)
