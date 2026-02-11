"""
Chat V3 Response Parser

Parses LLM JSON responses into structured objects.

Handles:
- Clean JSON
- JSON in code blocks
- Partial/malformed JSON (with recovery attempts)
"""

import json
import re
from typing import Optional, Dict, Any, List

from .types import AgentResponse, ToolCall, Plan, PlanStep
from .config import StepStatus
from .exceptions import ParseError


class ResponseParser:
    """
    Parse LLM JSON responses into AgentResponse objects.

    The parser is lenient and attempts recovery for common issues:
    - JSON in markdown code blocks
    - Trailing commas
    - Unescaped characters
    """

    def parse(self, text: str) -> AgentResponse:
        """
        Parse LLM response text into AgentResponse.

        Args:
            text: Raw text from LLM

        Returns:
            Parsed AgentResponse

        Raises:
            ParseError: If parsing fails after recovery attempts
        """
        # Try to extract JSON
        json_str = self._extract_json(text)
        if not json_str:
            raise ParseError("No JSON found in response", raw_response=text)

        # Try to parse
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            # Try to fix common issues
            try:
                json_str = self._fix_json(json_str)
                data = json.loads(json_str)
            except json.JSONDecodeError:
                raise ParseError(f"Invalid JSON: {e}", raw_response=text)

        # Validate structure
        self._validate_structure(data)

        # Build response
        return AgentResponse(
            thinking=data.get("thinking", ""),
            plan=self._parse_plan(data.get("plan")),
            tool_call=self._parse_tool_call(data.get("tool_call")),
            response=data.get("response"),
            plan_step=data.get("plan_step")
        )

    def _extract_json(self, text: str) -> Optional[str]:
        """
        Extract JSON from response text.

        Handles:
        - JSON in ```json code blocks
        - JSON in ``` code blocks
        - Raw JSON object
        """
        text = text.strip()

        # Try code block with json marker
        match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Try code block without marker
        match = re.search(r'```\s*(\{.*?\})\s*```', text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Try to find JSON object (greedy but balanced braces)
        # Start from the first { and try to find matching }
        start = text.find('{')
        if start == -1:
            return None

        depth = 0
        in_string = False
        escape_next = False
        end = start

        for i, char in enumerate(text[start:], start):
            if escape_next:
                escape_next = False
                continue

            if char == '\\':
                escape_next = True
                continue

            if char == '"' and not escape_next:
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    end = i
                    break

        if depth == 0:
            return text[start:end + 1]

        return None

    def _fix_json(self, json_str: str) -> str:
        """
        Attempt to fix common JSON issues.

        Fixes:
        - Trailing commas
        - Single quotes instead of double (Python dict syntax)
        - Unescaped newlines in strings
        """
        # Remove trailing commas before } or ]
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*]', ']', json_str)

        # Try to convert Python dict syntax to JSON
        # Replace single quotes with double quotes (carefully)
        # This is a simple approach - may not work for all edge cases
        try:
            # First try ast.literal_eval for Python dict syntax
            import ast
            parsed = ast.literal_eval(json_str)
            import json as json_module
            return json_module.dumps(parsed)
        except (ValueError, SyntaxError):
            pass

        return json_str

    def _validate_structure(self, data: Dict[str, Any]):
        """
        Validate the response structure.

        Raises:
            ParseError: If structure is invalid
        """
        if not isinstance(data, dict):
            raise ParseError("Response must be a JSON object")

        # Check for mutually exclusive fields
        has_tool_call = "tool_call" in data and data["tool_call"]
        has_response = "response" in data and data["response"]

        if has_tool_call and has_response:
            raise ParseError(
                "Response contains both 'tool_call' and 'response' - must have only one"
            )

        if not has_tool_call and not has_response:
            # Allow this - might be a plan-only response or need to prompt for continuation
            pass

    def _parse_tool_call(self, data: Optional[Dict]) -> Optional[ToolCall]:
        """Parse tool_call field into ToolCall object."""
        if not data:
            return None

        tool = data.get("tool")
        if not tool:
            raise ParseError("tool_call missing 'tool' field")

        params = data.get("params", {})

        return ToolCall(tool=tool, params=params)

    def _parse_plan(self, data: Optional[Dict]) -> Optional[Plan]:
        """Parse plan field into Plan object."""
        if not data:
            return None

        goal = data.get("goal", "")
        if not goal:
            raise ParseError("plan missing 'goal' field")

        steps_data = data.get("steps", [])
        steps = []

        for i, step_data in enumerate(steps_data):
            if isinstance(step_data, str):
                # Simple string step
                steps.append(PlanStep(
                    index=i,
                    description=step_data,
                    action_type="unknown"
                ))
            elif isinstance(step_data, dict):
                steps.append(PlanStep(
                    index=i,
                    description=step_data.get("description", f"Step {i + 1}"),
                    action_type=step_data.get("action_type", "unknown"),
                    status=StepStatus.PENDING
                ))

        return Plan(goal=goal, steps=steps)


# Singleton instance
response_parser = ResponseParser()


def parse_response(text: str) -> AgentResponse:
    """
    Convenience function to parse an LLM response.

    Args:
        text: Raw text from LLM

    Returns:
        Parsed AgentResponse
    """
    return response_parser.parse(text)
