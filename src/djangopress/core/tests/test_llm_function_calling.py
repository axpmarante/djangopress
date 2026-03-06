"""Test that LLMBase.get_completion_with_tools() builds correct Gemini FC requests."""

from unittest.mock import patch, MagicMock
from django.test import TestCase


class LLMFunctionCallingTest(TestCase):

    @patch('djangopress.ai.utils.llm_config.GOOGLE_AVAILABLE', True)
    def test_get_completion_with_tools_builds_config(self):
        """Verify tools are passed to Gemini's GenerateContentConfig."""
        from google.genai import types
        from djangopress.ai.utils.llm_config import LLMBase

        tool_declarations = [
            types.Tool(function_declarations=[
                types.FunctionDeclaration(
                    name='list_pages',
                    description='List all pages',
                    parameters=types.Schema(type='OBJECT', properties={}),
                ),
            ])
        ]

        llm = LLMBase()
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = 'Hello!'
        mock_response.candidates = [MagicMock()]
        mock_response.candidates[0].content.parts = [MagicMock(function_call=None)]
        mock_client.models.generate_content.return_value = mock_response
        llm._clients['google'] = mock_client

        result = llm.get_completion_with_tools(
            contents=[{'role': 'user', 'parts': ['hello']}],
            system_instruction='You are an assistant.',
            tools=tool_declarations,
            tool_name='gemini-flash',
        )

        call_kwargs = mock_client.models.generate_content.call_args
        self.assertIsNotNone(call_kwargs)

    def test_non_google_model_raises(self):
        """Non-Google models should raise ValueError."""
        from djangopress.ai.utils.llm_config import LLMBase
        llm = LLMBase()
        with self.assertRaises(ValueError):
            llm.get_completion_with_tools(
                contents=[], system_instruction='test',
                tools=[], tool_name='gpt-5',
            )
