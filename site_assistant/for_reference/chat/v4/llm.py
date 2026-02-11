"""
LLM Client Wrapper for Chat V4

Provides a unified interface to LLM providers with:
- Model selection from conversation settings
- Token tracking
- Error handling
- Response parsing
"""

import json
import logging
from typing import Optional, Literal
from dataclasses import dataclass

from ai_assistant.llm_config import LLMBase, MODEL_CONFIG

from .errors import LLMError, ParseError

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Structured response from LLM call"""
    text: str
    input_tokens: int
    output_tokens: int
    model_used: str
    parsed_json: Optional[dict] = None

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class LLMClient:
    """
    Unified LLM client for V4 agents.

    Uses the model selected in the conversation settings (from MODEL_CONFIG in llm_config.py).
    Wraps LLMBase to provide:
    - Model selection from conversation
    - Consistent response format
    - JSON parsing with error handling
    - Token tracking
    """

    # Default model if none specified
    DEFAULT_MODEL = "gemini-flash"

    # Aliases for backward compatibility with old model names
    MODEL_ALIASES = {
        "sonnet": "claude",
        "haiku": "gemini-lite",
        "opus": "claude",
        "flash": "gemini-flash",
        "flash-lite": "gemini-lite"
    }

    def __init__(self, model_name: str = None, model: str = None):
        """
        Initialize LLM client.

        Args:
            model_name: Model name from llm_config.py MODEL_CONFIG
                       (e.g., "gemini-flash", "claude", "gpt-5.2")
            model: Legacy alias (for backward compatibility)
        """
        # Support both model_name and model (legacy)
        raw_model = model_name or model or self.DEFAULT_MODEL

        # Resolve aliases
        self.model_name = self.MODEL_ALIASES.get(raw_model, raw_model)
        self._llm = LLMBase()

        # Validate model exists in config
        if self.model_name not in MODEL_CONFIG:
            logger.warning(f"Model '{self.model_name}' not in MODEL_CONFIG, using default")
            self.model_name = self.DEFAULT_MODEL

    @classmethod
    def for_conversation(cls, conversation) -> 'LLMClient':
        """
        Create LLM client using the conversation's selected model.

        Args:
            conversation: Django Conversation instance

        Returns:
            LLMClient configured with conversation's model
        """
        model_name = getattr(conversation, 'model_name', None) or cls.DEFAULT_MODEL
        return cls(model_name=model_name)

    @classmethod
    def for_model(cls, model_name: str) -> 'LLMClient':
        """
        Create LLM client for a specific model.

        Args:
            model_name: Model name from MODEL_CONFIG

        Returns:
            LLMClient configured for that model
        """
        return cls(model_name=model_name)

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 2000,
        json_response: bool = False
    ) -> LLMResponse:
        """
        Send chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum response tokens
            json_response: If True, request JSON formatted response

        Returns:
            LLMResponse with text and token counts

        Raises:
            LLMError: If LLM call fails
        """
        try:
            # Call underlying LLM using tool_name to select from MODEL_CONFIG
            result = self._llm.get_completion(
                messages=messages,
                tool_name=self.model_name,  # Maps to MODEL_CONFIG key
                temperature=temperature,
                max_tokens=max_tokens
            )

            if not result:
                raise LLMError("Empty response from LLM")

            # Extract response from StandardizedLLMResponse
            text = result.choices[0].message.content
            input_tokens = getattr(result.usage, 'prompt_tokens', 0)
            output_tokens = getattr(result.usage, 'completion_tokens', 0)

            response = LLMResponse(
                text=text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model_used=self.model_name
            )

            # Try to parse JSON if requested or if response looks like JSON
            if json_response or text.strip().startswith('{'):
                try:
                    response.parsed_json = self._parse_json(text)
                except ParseError:
                    if json_response:
                        raise
                    # If not explicitly requested, just leave parsed_json as None

            return response

        except LLMError:
            raise
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise LLMError(f"LLM call failed: {e}")

    def chat_json(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 2000
    ) -> dict:
        """
        Send chat request expecting JSON response.

        Args:
            messages: List of message dicts
            temperature: Sampling temperature
            max_tokens: Maximum response tokens

        Returns:
            Parsed JSON dict

        Raises:
            LLMError: If LLM call fails
            ParseError: If response is not valid JSON
        """
        response = self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_response=True
        )

        if response.parsed_json is None:
            raise ParseError(
                "Failed to parse JSON response",
                raw_response=response.text
            )

        return response.parsed_json

    def _parse_json(self, text: str) -> dict:
        """
        Parse JSON from LLM response text.

        Handles common issues:
        - Code blocks (```json ... ```)
        - Leading/trailing text
        - Trailing commas

        Args:
            text: Raw response text

        Returns:
            Parsed JSON dict

        Raises:
            ParseError: If parsing fails
        """
        original_text = text

        # Remove markdown code blocks
        if '```' in text:
            # Extract content between code blocks
            import re
            code_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
            if code_match:
                text = code_match.group(1)

        # Find JSON object boundaries
        text = text.strip()

        # Find first { and last }
        start = text.find('{')
        end = text.rfind('}')

        if start == -1 or end == -1 or start > end:
            raise ParseError(
                "No JSON object found in response",
                raw_response=original_text
            )

        json_str = text[start:end + 1]

        # Fix trailing commas (common LLM mistake)
        json_str = self._fix_trailing_commas(json_str)

        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            # Try ast.literal_eval for Python dict syntax
            try:
                import ast
                return ast.literal_eval(json_str)
            except:
                pass

            raise ParseError(
                f"Invalid JSON: {e}",
                raw_response=original_text
            )

    def _fix_trailing_commas(self, json_str: str) -> str:
        """Remove trailing commas before } or ]"""
        import re
        # Remove trailing commas before closing brackets
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*]', ']', json_str)
        return json_str


class TokenTracker:
    """
    Tracks token usage across an execution.

    Provides:
    - Per-agent token tracking
    - Cost estimation
    - Budget enforcement
    """

    # Approximate costs per 1K tokens (as of 2024)
    COSTS = {
        "claude-sonnet": {"input": 0.003, "output": 0.015},
        "claude-haiku": {"input": 0.00025, "output": 0.00125},
        "claude-opus": {"input": 0.015, "output": 0.075},
        "gemini-flash": {"input": 0.0001, "output": 0.0002},
        "gemini-flash-lite": {"input": 0.00005, "output": 0.0001}
    }

    def __init__(self, budget_tokens: int = None):
        """
        Initialize tracker.

        Args:
            budget_tokens: Optional token budget limit
        """
        self.budget_tokens = budget_tokens
        self.usage = {}  # model -> {input: X, output: Y}
        self.by_agent = {}  # agent_type -> {input: X, output: Y}

    def track(
        self,
        response: LLMResponse,
        agent_type: str = None
    ) -> None:
        """
        Track tokens from a response.

        Args:
            response: LLM response with token counts
            agent_type: Optional agent type for per-agent tracking
        """
        model = response.model_used

        # Track by model
        if model not in self.usage:
            self.usage[model] = {"input": 0, "output": 0}
        self.usage[model]["input"] += response.input_tokens
        self.usage[model]["output"] += response.output_tokens

        # Track by agent
        if agent_type:
            if agent_type not in self.by_agent:
                self.by_agent[agent_type] = {"input": 0, "output": 0}
            self.by_agent[agent_type]["input"] += response.input_tokens
            self.by_agent[agent_type]["output"] += response.output_tokens

    @property
    def total_tokens(self) -> int:
        """Total tokens used across all models"""
        return sum(
            u["input"] + u["output"]
            for u in self.usage.values()
        )

    @property
    def total_input_tokens(self) -> int:
        """Total input tokens"""
        return sum(u["input"] for u in self.usage.values())

    @property
    def total_output_tokens(self) -> int:
        """Total output tokens"""
        return sum(u["output"] for u in self.usage.values())

    def estimate_cost(self) -> float:
        """
        Estimate total cost in USD.

        Returns:
            Estimated cost based on token usage
        """
        total = 0.0
        for model, usage in self.usage.items():
            costs = self.COSTS.get(model, {"input": 0.001, "output": 0.002})
            total += (usage["input"] / 1000) * costs["input"]
            total += (usage["output"] / 1000) * costs["output"]
        return total

    def is_over_budget(self) -> bool:
        """Check if over token budget"""
        if self.budget_tokens is None:
            return False
        return self.total_tokens > self.budget_tokens

    def remaining_budget(self) -> int | None:
        """Get remaining token budget"""
        if self.budget_tokens is None:
            return None
        return max(0, self.budget_tokens - self.total_tokens)

    def get_summary(self) -> dict:
        """Get usage summary"""
        return {
            "total_tokens": self.total_tokens,
            "total_input": self.total_input_tokens,
            "total_output": self.total_output_tokens,
            "by_model": self.usage,
            "by_agent": self.by_agent,
            "estimated_cost_usd": round(self.estimate_cost(), 4),
            "budget_tokens": self.budget_tokens,
            "remaining_budget": self.remaining_budget()
        }
