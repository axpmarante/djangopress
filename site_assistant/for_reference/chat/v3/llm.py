"""
Chat V3 LLM Client

Wrapper around the LLMBase client to provide a simplified interface for V3.
"""

from typing import List, Dict, Any, Optional


class LLMClient:
    """
    LLM client wrapper for V3.

    Adapts the LLMBase interface to what the AgentLoop expects.
    """

    def __init__(self, conversation=None, model_name: str = None):
        """
        Initialize the LLM client.

        Args:
            conversation: Optional conversation to get model from
            model_name: Optional model name override
        """
        from ai_assistant.llm_config import LLMBase

        self._llm = LLMBase()
        self._model_name = model_name

        # Get model from conversation if available
        if conversation and hasattr(conversation, 'model_name') and conversation.model_name:
            self._model_name = conversation.model_name
        elif not self._model_name:
            self._model_name = 'gemini-flash'  # Default to a fast model

    def chat(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Send messages to the LLM and get a response.

        Args:
            messages: List of message dicts with 'role' and 'content'

        Returns:
            Dict with 'text', 'input_tokens', 'output_tokens'
        """
        try:
            response = self._llm.get_completion(
                messages=messages,
                tool_name=self._model_name
            )

            # Extract content
            text = ""
            if hasattr(response, 'choices') and response.choices:
                text = response.choices[0].message.content

            # Extract usage
            input_tokens = 0
            output_tokens = 0
            if hasattr(response, 'usage'):
                input_tokens = getattr(response.usage, 'prompt_tokens', 0)
                output_tokens = getattr(response.usage, 'completion_tokens', 0)

            return {
                'text': text,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens
            }

        except Exception as e:
            # Return error as text so the agent can handle it
            return {
                'text': f'{{"thinking": "LLM error", "response": "I encountered an error: {str(e)}"}}',
                'input_tokens': 0,
                'output_tokens': 0,
                'error': str(e)
            }


def get_llm_client(conversation=None, model_name: str = None) -> LLMClient:
    """
    Get an LLM client instance.

    Args:
        conversation: Optional conversation for model context
        model_name: Optional model name override

    Returns:
        LLMClient instance
    """
    return LLMClient(conversation, model_name)
