"""Gemini 3 call settings: per-task temperature/thinking, system instruction,
finish reason, real usage, retry once, and no silent switch to another provider."""
from types import SimpleNamespace
from unittest import mock

from django.test import TestCase
from google.genai import types

from djangopress.ai.utils.llm_config import (
    LLMBase, MODEL_CONFIG, ModelProvider, get_ai_model, settings_for,
)


def fake_response(text='ok', finish='STOP', prompt=100, out=20, thoughts=5):
    return SimpleNamespace(
        text=text,
        candidates=[SimpleNamespace(finish_reason=types.FinishReason(finish), content=None)],
        usage_metadata=SimpleNamespace(prompt_token_count=prompt, candidates_token_count=out,
                                       thoughts_token_count=thoughts, total_token_count=prompt + out + thoughts),
    )


class FakeModels:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append(SimpleNamespace(model=model, contents=contents, config=config))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class NoOpenAI:
    """Any use of the OpenAI client is a test failure."""
    def __getattr__(self, name):
        raise AssertionError('OpenAI must not be called as a fallback')


MESSAGES = [{'role': 'system', 'content': 'You are a designer.'}, {'role': 'user', 'content': 'Make it nicer.'}]


class LLMSettingsTest(TestCase):
    def call(self, models, tool_name, **kwargs):
        clients = {ModelProvider.GOOGLE: SimpleNamespace(models=models), ModelProvider.OPENAI: NoOpenAI()}
        with mock.patch.dict(LLMBase._clients, clients), mock.patch('time.sleep'):
            return LLMBase().get_completion(MESSAGES, tool_name=tool_name, **kwargs)

    def test_model_key_carries_the_task(self):
        key = get_ai_model('refinement_section')
        self.assertEqual(key, 'gemini-flash')
        self.assertEqual(key.task, 'refinement_section')
        self.assertIs(MODEL_CONFIG[key], MODEL_CONFIG['gemini-flash'])

    def test_design_task_gets_high_thinking_and_temperature_one(self):
        models = FakeModels(fake_response())
        self.call(models, get_ai_model('refinement_section'))
        config = models.calls[0].config
        self.assertEqual(config.temperature, 1.0)
        self.assertEqual(config.thinking_config.thinking_level, types.ThinkingLevel.HIGH)

    def test_plain_key_gets_tier_default(self):
        self.assertEqual(settings_for('gemini-lite')['thinking_level'], 'low')
        self.assertEqual(settings_for(get_ai_model('assistant_executor'))['thinking_level'], 'medium')
        self.assertEqual(settings_for(get_ai_model('translation'))['thinking_level'], 'low')

    def test_system_message_is_a_system_instruction(self):
        models = FakeModels(fake_response())
        self.call(models, get_ai_model('refinement_section'))
        call = models.calls[0]
        self.assertEqual(call.config.system_instruction, 'You are a designer.')
        first_text = call.contents[0].parts[0].text
        self.assertEqual(first_text, 'Make it nicer.')

    def test_finish_reason_and_real_usage(self):
        models = FakeModels(fake_response(finish='MAX_TOKENS', prompt=1000, out=300, thoughts=50))
        response = self.call(models, get_ai_model('refinement_section'))
        self.assertEqual(response.finish_reason, 'MAX_TOKENS')
        self.assertEqual(response.usage.prompt_tokens, 1000)
        self.assertEqual(response.usage.completion_tokens, 350)   # answer + thinking
        self.assertEqual(response.usage.total_tokens, 1350)

    def test_error_is_raised_not_switched_to_openai(self):
        models = FakeModels(RuntimeError('400 INVALID_ARGUMENT'))
        with self.assertRaises(RuntimeError):
            self.call(models, get_ai_model('refinement_section'))
        self.assertEqual(len(models.calls), 1)

    def test_transient_error_is_retried_once(self):
        models = FakeModels(RuntimeError('503 UNAVAILABLE'), fake_response(text='second'))
        response = self.call(models, get_ai_model('refinement_section'))
        self.assertEqual(response.choices[0].message.content, 'second')
        self.assertEqual(len(models.calls), 2)

    def test_transient_error_twice_raises(self):
        models = FakeModels(RuntimeError('503 UNAVAILABLE'), RuntimeError('503 UNAVAILABLE'))
        with self.assertRaises(RuntimeError):
            self.call(models, get_ai_model('refinement_section'))

    def test_json_output(self):
        models = FakeModels(fake_response(text='{"a": 1}'))
        self.call(models, get_ai_model('assistant_router'), json_output=True)
        self.assertEqual(models.calls[0].config.response_mime_type, 'application/json')

    def test_function_calling_path_uses_task_settings(self):
        models = FakeModels(fake_response())
        clients = {ModelProvider.GOOGLE: SimpleNamespace(models=models)}
        with mock.patch.dict(LLMBase._clients, clients):
            LLMBase().get_completion_with_tools(contents=[], system_instruction='sys', tools=[],
                                                tool_name=get_ai_model('assistant_executor'))
        config = models.calls[0].config
        self.assertEqual(config.temperature, 1.0)
        self.assertEqual(config.thinking_config.thinking_level, types.ThinkingLevel.MEDIUM)


class VisionSettingsTest(TestCase):
    def test_vision_call_uses_task_settings(self):
        models = FakeModels(fake_response(text='seen'))
        clients = {ModelProvider.GOOGLE: SimpleNamespace(models=models)}
        with mock.patch.dict(LLMBase._clients, clients):
            out = LLMBase().get_vision_completion(
                'Describe', images=[{'bytes': b'\x89PNG....', 'mime_type': 'image/png'}],
                tool_name=get_ai_model('refinement_section'))
        text = out.choices[0].message.content if hasattr(out, 'choices') else out
        self.assertEqual(text, 'seen')
        self.assertEqual(models.calls[0].config.thinking_config.thinking_level, types.ThinkingLevel.HIGH)
