"""
Executive Coach Service

Extends V2 ChatService with coach-specific:
- System prompts (direct accountability)
- Context building (journal-focused)
- Router behavior (coaching classification)

Reuses V2's tool infrastructure for journal operations.
"""

import json
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from django.utils import timezone

from chat.models import Conversation, Message
from chat.v2.memory import MemoryState, RouteType, get_or_create_memory_state
from chat.v2.tools.base import ToolRegistry, ToolCall as ToolCallObj

from .prompts import (
    COACH_SYSTEM_PROMPT,
    COACH_AGENTIC_PROMPT,
    COACH_ROUTER_PROMPT,
    build_coach_context,
    get_time_of_day,
    parse_coach_response,
)
from .context import fetch_coach_context


DEBUG_COACH = False


def debug_print(label: str, data: Any = None):
    """Print debug info if enabled."""
    if not DEBUG_COACH:
        return
    if data is not None:
        print(f"[COACH] {label}: {str(data)[:300]}")
    else:
        print(f"[COACH] {label}")


@dataclass
class CoachResponse:
    """Response from coach chat processing."""
    success: bool
    message: str
    route_type: str
    data: Optional[Dict] = None
    error: Optional[str] = None

    # Metrics
    input_tokens: int = 0
    output_tokens: int = 0
    processing_time_ms: int = 0
    llm_calls: int = 0


class CoachService:
    """
    Executive Coach Chat Service.

    Like ChatServiceV2 but with coaching persona and journal-focused context.

    Usage:
        service = CoachService(user, conversation, llm_client)
        response = service.send_message("How am I doing on my goals?")
    """

    MAX_TOOL_ITERATIONS = 8

    def __init__(self, user, conversation: Conversation, llm_client=None):
        self.user = user
        self.conversation = conversation
        self.llm_client = llm_client

        # Memory for conversation state
        self.memory_state, self.db_memory = get_or_create_memory_state(conversation)

        # Tool registry (same as V2)
        self.tool_registry = ToolRegistry(user)

        # Fetch journal-focused context
        self.journal_context = fetch_coach_context(user)
        self.time_of_day = get_time_of_day()

    def send_message(self, user_content: str) -> CoachResponse:
        """Process a user message with coaching persona."""
        start_time = time.time()
        debug_print(f"Message: {user_content[:100]}...")

        # Save user message
        self._save_user_message(user_content)

        try:
            # Route the message
            route_result = self._classify_message(user_content)
            debug_print(f"Route: {route_result['classification']}")

            classification = route_result['classification']

            if classification == 'DIRECT':
                response = self._handle_direct(route_result)
            elif classification == 'AGENTIC':
                response = self._handle_agentic(user_content)
            elif classification == 'CLARIFY':
                response = self._handle_clarify(route_result)
            else:
                response = CoachResponse(
                    success=False,
                    message="I'm not sure how to help with that. What's on your mind?",
                    route_type="ERROR"
                )

            response.processing_time_ms = int((time.time() - start_time) * 1000)

            # Save assistant message
            self._save_assistant_message(response.message, response)

            # Save memory state
            if self.memory_state._is_dirty:
                self.memory_state.save_to_db(self.db_memory)

            return response

        except Exception as e:
            debug_print(f"ERROR: {str(e)}")
            import traceback
            traceback.print_exc()

            error_response = CoachResponse(
                success=False,
                message="I encountered an issue. Let's try that again - what were you asking?",
                route_type="ERROR",
                error=str(e),
                processing_time_ms=int((time.time() - start_time) * 1000)
            )
            self._save_assistant_message(error_response.message, error_response)
            return error_response

    def _classify_message(self, user_content: str) -> Dict[str, Any]:
        """
        Classify message using coach router prompt.

        Returns dict with classification and optional response/reason/question.
        """
        if not self.llm_client:
            return {'classification': 'AGENTIC', 'reason': 'No LLM for classification'}

        # Build router context
        context_str = build_coach_context(
            self.user,
            self.journal_context,
            self.time_of_day
        )

        # Get conversation history
        history = self._get_conversation_history()

        messages = [
            {'role': 'system', 'content': COACH_ROUTER_PROMPT},
            {'role': 'user', 'content': f"{context_str}\n\n---\n\n{history}\n\nUser: {user_content}"}
        ]

        try:
            response = self.llm_client.get_completion(
                messages=messages,
                tool_name=self.conversation.model_name
            )
            llm_text = response.choices[0].message.content
            debug_print(f"Router response: {llm_text[:200]}...")

            return parse_coach_response(llm_text)

        except Exception as e:
            debug_print(f"Router error: {e}")
            return {'classification': 'AGENTIC', 'reason': f'Router error: {e}'}

    def _handle_direct(self, route_result: Dict) -> CoachResponse:
        """Handle DIRECT - response provided by router."""
        return CoachResponse(
            success=True,
            message=route_result.get('response', "What's on your mind?"),
            route_type='DIRECT',
            llm_calls=1
        )

    def _handle_clarify(self, route_result: Dict) -> CoachResponse:
        """Handle CLARIFY - ask for more information."""
        return CoachResponse(
            success=True,
            message=route_result.get('question', "Tell me more - what specifically are you trying to accomplish?"),
            route_type='CLARIFY',
            llm_calls=1
        )

    def _handle_agentic(self, user_content: str) -> CoachResponse:
        """Handle AGENTIC - interactive tool loop with coaching style."""
        if not self.llm_client:
            return CoachResponse(
                success=False,
                message="I need access to process this request.",
                route_type='AGENTIC',
                error="No LLM client"
            )

        # Build initial context with coach persona and tools
        context_str = build_coach_context(
            self.user,
            self.journal_context,
            self.time_of_day
        )

        history = self._get_conversation_history()

        messages = [
            {'role': 'system', 'content': COACH_AGENTIC_PROMPT},
            {'role': 'user', 'content': f"{context_str}\n\n---\n\nConversation:\n{history}\n\nUser: {user_content}"}
        ]

        # Interactive loop
        iteration = 0
        llm_calls = 0
        total_input_tokens = 0
        total_output_tokens = 0
        tool_results = []

        while iteration < self.MAX_TOOL_ITERATIONS:
            iteration += 1
            debug_print(f"Iteration {iteration}")

            # Call LLM
            try:
                response = self.llm_client.get_completion(
                    messages=messages,
                    tool_name=self.conversation.model_name
                )
                llm_text = response.choices[0].message.content
                llm_calls += 1

                # Track tokens
                if hasattr(response, 'usage') and response.usage:
                    total_input_tokens += getattr(response.usage, 'prompt_tokens', 0) or 0
                    total_output_tokens += getattr(response.usage, 'completion_tokens', 0) or 0

                debug_print(f"LLM: {llm_text[:200]}...")

            except Exception as e:
                debug_print(f"LLM error: {e}")
                return CoachResponse(
                    success=False,
                    message="I hit a snag. What were you asking?",
                    route_type='AGENTIC',
                    error=str(e),
                    llm_calls=llm_calls
                )

            # Parse response
            parsed = self._parse_agentic_response(llm_text)

            if parsed.get('error'):
                # Ask LLM to fix
                messages.append({'role': 'assistant', 'content': llm_text})
                messages.append({
                    'role': 'user',
                    'content': f"Please respond with valid JSON containing 'tool_call' or 'response'. Error: {parsed['error']}"
                })
                continue

            # Check for final response
            if parsed.get('response'):
                return CoachResponse(
                    success=True,
                    message=parsed['response'],
                    route_type='AGENTIC',
                    data={'tool_results': tool_results} if tool_results else None,
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    llm_calls=llm_calls
                )

            # Execute tool call
            if parsed.get('tool_call'):
                tool_call = parsed['tool_call']
                debug_print(f"Tool: {tool_call.get('tool')}.{tool_call.get('action', 'search')}")

                result = self._execute_tool(tool_call)
                tool_results.append({
                    'tool': tool_call.get('tool', 'unknown'),
                    'action': tool_call.get('action', 'search'),
                    'resource_type': tool_call.get('resource_type', ''),
                    'result': result
                })

                # Add to messages
                messages.append({'role': 'assistant', 'content': llm_text})
                result_str = self._format_tool_result(result)
                messages.append({
                    'role': 'user',
                    'content': f"Tool result:\n{result_str}\n\nContinue with coaching insight or make another tool call."
                })
                continue

            # Neither - ask to continue
            messages.append({'role': 'assistant', 'content': llm_text})
            messages.append({
                'role': 'user',
                'content': "Respond with 'tool_call' for an action or 'response' to answer."
            })

        # Max iterations
        return CoachResponse(
            success=False,
            message="I got stuck in my analysis. Let's simplify - what's the one thing you want to focus on?",
            route_type='AGENTIC',
            error=f"Max iterations ({self.MAX_TOOL_ITERATIONS})",
            llm_calls=llm_calls
        )

    def _parse_agentic_response(self, llm_text: str) -> Dict[str, Any]:
        """Parse LLM response for tool_call or response."""
        import re

        # Try to extract JSON
        patterns = [
            r'```json\s*(.*?)\s*```',
            r'```\s*(.*?)\s*```',
            r'(\{.*\})',
        ]

        json_str = None
        for pattern in patterns:
            match = re.search(pattern, llm_text, re.DOTALL)
            if match:
                json_str = match.group(1).strip()
                break

        if not json_str:
            json_str = llm_text.strip()

        try:
            data = json.loads(json_str)
            if isinstance(data, dict):
                if 'tool_call' in data and data['tool_call']:
                    return {'tool_call': data['tool_call']}
                if 'response' in data and data['response']:
                    return {'response': data['response']}
            return {'error': 'JSON must have tool_call or response'}
        except json.JSONDecodeError as e:
            return {'error': f'Invalid JSON: {e}'}

    def _execute_tool(self, tool_call: Dict) -> Dict:
        """Execute a tool call."""
        tool_name = tool_call.get('tool', 'search_tool')
        action = tool_call.get('action', 'search')
        resource_type = tool_call.get('resource_type', 'goal')

        params = tool_call.get('params', {})
        if not params and tool_call.get('filters'):
            params = {'filters': tool_call['filters']}

        try:
            call_obj = ToolCallObj(
                tool=tool_name,
                action=action,
                resource_type=resource_type,
                params=params
            )
            result = self.tool_registry.execute(call_obj)
            return {
                'status': result.status.value,
                'data': result.data,
                'message': result.message,
                'error': result.error
            }
        except Exception as e:
            return {'status': 'error', 'data': None, 'message': '', 'error': str(e)}

    def _format_tool_result(self, result: Dict) -> str:
        """Format tool result for LLM."""
        status = result.get('status', 'unknown')
        message = result.get('message', '')
        error = result.get('error', '')
        data = result.get('data')

        lines = []

        if status == 'success':
            lines.append(f"✓ {message}" if message else "✓ Success")
        else:
            lines.append(f"✗ {error or message or 'Error'}")

        if data:
            if isinstance(data, dict):
                if data.get('items'):
                    items = data['items']
                    lines.append(f"Found {len(items)} items:")
                    for item in items[:5]:
                        title = item.get('title') or item.get('name', 'Untitled')
                        lines.append(f"  - {title} (ID: {item.get('id', '?')})")
                elif data.get('id'):
                    lines.append(f"  ID: {data['id']}")
                    lines.append(f"  Title: {data.get('title') or data.get('name', 'Untitled')}")

        return "\n".join(lines)

    def _get_conversation_history(self, limit: int = 10) -> str:
        """Get recent conversation history."""
        messages = self.conversation.messages.order_by('-created_at')[:limit]
        messages = list(reversed(messages))

        lines = []
        for msg in messages:
            role = "User" if msg.role == 'user' else "Coach"
            lines.append(f"{role}: {msg.content[:500]}")

        return "\n".join(lines) if lines else "(New conversation)"

    def _save_user_message(self, content: str) -> Message:
        """Save user message."""
        return Message.objects.create(
            conversation=self.conversation,
            role='user',
            content=content
        )

    def _save_assistant_message(self, content: str, response: CoachResponse) -> Message:
        """Save assistant message."""
        message = Message.objects.create(
            conversation=self.conversation,
            role='assistant',
            content=content,
            model_used=self.conversation.model_name or "",
            processing_time_ms=response.processing_time_ms,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            is_error=not response.success,
            error_message=response.error or ""
        )

        # Update conversation totals
        self.conversation.total_input_tokens = (self.conversation.total_input_tokens or 0) + response.input_tokens
        self.conversation.total_output_tokens = (self.conversation.total_output_tokens or 0) + response.output_tokens
        self.conversation.last_message_at = timezone.now()
        self.conversation.save(update_fields=['total_input_tokens', 'total_output_tokens', 'last_message_at'])

        return message
