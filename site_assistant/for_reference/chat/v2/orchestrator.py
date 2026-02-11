"""
Chat V2 Orchestrator

Main entry point for the V2 chat architecture.

The orchestrator:
1. Routes messages (DIRECT / AGENTIC / CLARIFY)
2. Assembles dynamic context
3. For AGENTIC: Interactive loop where LLM makes tool calls one at a time
4. Manages AgentMemory state
5. Generates final responses

Interactive Loop (AGENTIC):
- LLM receives context + tools
- LLM responds with tool_call OR response
- If tool_call: execute, show result to LLM, loop
- If response: return to user
- Max iterations prevent infinite loops

This replaces ChatService for V2-enabled conversations.
"""

import json
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from django.utils import timezone
from django.db import transaction

from ..models import Conversation, Message, ChatVELExecution
from .models import AgentMemory
from .memory import MemoryState, RouteType, get_or_create_memory_state
from .router import Router, RouterResult
from .context import DynamicContextBuilder
from .tools.base import ToolRegistry


# Debug flag - set to False for production
DEBUG_V2 = False


def debug_print(label: str, data: Any = None):
    """Print debug info if enabled."""
    if not DEBUG_V2:
        return
    if data is not None:
        if isinstance(data, (dict, list)):
            try:
                print(f"[V2] {label}: {json.dumps(data, indent=2, default=str)[:500]}")
            except:
                print(f"[V2] {label}: {str(data)[:500]}")
        else:
            print(f"[V2] {label}: {data}")
    else:
        print(f"[V2] {label}")


@dataclass
class LLMResult:
    """Result from an LLM call including text and token usage."""
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    success: bool = True
    error: Optional[str] = None


@dataclass
class ChatResponse:
    """Response from chat processing."""
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

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        result = {
            'success': self.success,
            'message': self.message,
            'route_type': self.route_type,
        }
        if self.data:
            result['data'] = self.data
        if self.error:
            result['error'] = self.error
        return result


class ChatServiceV2:
    """
    V2 Chat Service - Main orchestrator.

    Usage:
        service = ChatServiceV2(user, conversation, llm_client)
        response = service.send_message("Create a task in Finance project")

        print(response.message)  # User-facing response
        print(response.route_type)  # DIRECT, AGENTIC, or CLARIFY
    """

    # Safety limits
    MAX_PLAN_STEPS = 10
    MAX_TOOL_ITERATIONS = 10  # Max tool calls per request

    def __init__(self, user, conversation: Conversation, llm_client=None):
        self.user = user
        self.conversation = conversation
        self.llm_client = llm_client

        # Get or create memory first (needed for other components)
        self.memory_state, self.db_memory = get_or_create_memory_state(conversation)

        # Initialize components (order matters - context_builder needed by router)
        self.tool_registry = ToolRegistry(user)
        self.context_builder = DynamicContextBuilder(user, conversation, self.memory_state)
        # Router gets context_builder for combined classification + DIRECT response
        self.router = Router(user, conversation, self.memory_state, self.context_builder)

    def send_message(self, user_content: str) -> ChatResponse:
        """
        Process a user message and return response.

        Main entry point - coordinates the entire V2 flow.
        """
        start_time = time.time()
        debug_print("=" * 50)
        debug_print(f"SEND MESSAGE: {user_content[:100]}...")

        # Save user message
        user_message = self._save_user_message(user_content)

        try:
            # Step 1: Route the message
            route_result = self._route_message(user_content)
            debug_print(f"Route: {route_result.route_type.value}")

            # Step 2: Handle based on route type
            if route_result.route_type == RouteType.DIRECT:
                response = self._handle_direct(user_content, route_result)

            elif route_result.route_type == RouteType.AGENTIC:
                response = self._handle_agentic(user_content, route_result)

            elif route_result.route_type == RouteType.CLARIFY:
                response = self._handle_clarify(user_content, route_result)

            else:
                response = ChatResponse(
                    success=False,
                    message="Unable to process request",
                    route_type="ERROR",
                    error=f"Unknown route type: {route_result.route_type}"
                )

            # Calculate total time
            response.processing_time_ms = int((time.time() - start_time) * 1000)

            # Save assistant message
            self._save_assistant_message(response.message, response)

            # Update conversation title if needed
            from chat.title_service import update_conversation_title
            if update_conversation_title(self.conversation):
                debug_print(f"Title updated to: {self.conversation.title}")

            # Save memory state if dirty
            if self.memory_state._is_dirty:
                self.memory_state.save_to_db(self.db_memory)

            debug_print(f"Response ({response.processing_time_ms}ms): {response.message[:100]}...")
            return response

        except Exception as e:
            debug_print(f"ERROR: {str(e)}")
            import traceback
            traceback.print_exc()

            error_response = ChatResponse(
                success=False,
                message="I encountered an error processing your request. Please try again.",
                route_type="ERROR",
                error=str(e),
                processing_time_ms=int((time.time() - start_time) * 1000)
            )

            self._save_assistant_message(error_response.message, error_response)
            return error_response

    # =========================================================================
    # Route Handlers
    # =========================================================================

    def _handle_direct(
        self,
        user_content: str,
        route_result: RouterResult
    ) -> ChatResponse:
        """
        Handle DIRECT route - response already provided by combined classifier.

        The router's LLM classification also includes the response for DIRECT
        routes, so we don't need an additional LLM call.
        """
        debug_print("Handling DIRECT route")

        # Use the response from the combined classifier (no extra LLM call!)
        # Tokens from router classification are tracked via route_result
        if route_result.direct_response:
            return ChatResponse(
                success=True,
                message=route_result.direct_response,
                route_type=RouteType.DIRECT.value,
                input_tokens=getattr(route_result, 'input_tokens', 0),
                output_tokens=getattr(route_result, 'output_tokens', 0),
                llm_calls=1  # Already counted in classification
            )

        # Fallback: if no direct_response (e.g., fast pattern match), generate one
        debug_print("No direct_response, falling back to LLM call")
        if self.llm_client:
            self.context_builder.memory = self.memory_state
            context = self.context_builder.build(route_result, include_tools=False)
            messages = context.to_messages()
            llm_result = self._call_llm(messages)

            return ChatResponse(
                success=True,
                message=llm_result.text,
                route_type=RouteType.DIRECT.value,
                input_tokens=llm_result.input_tokens,
                output_tokens=llm_result.output_tokens,
                llm_calls=1
            )

        # No LLM - generate simple response
        return self._generate_simple_response(user_content, route_result)

    def _handle_agentic(
        self,
        user_content: str,
        route_result: RouterResult
    ) -> ChatResponse:
        """
        Handle AGENTIC route - interactive tool execution loop.

        Flow:
        1. Build context with tools
        2. LLM responds with tool_call or response
        3. If tool_call: execute, add result to messages, loop
        4. If response: return to user
        5. Max iterations to prevent infinite loops
        """
        debug_print("Handling AGENTIC route (interactive)")

        if not self.llm_client:
            return ChatResponse(
                success=False,
                message="I need an LLM to process this request.",
                route_type=RouteType.AGENTIC.value,
                error="No LLM client available"
            )

        # Build initial context with tools
        self.context_builder.memory = self.memory_state
        context = self.context_builder.build(route_result, include_tools=True)
        messages = context.to_messages()

        # Track iterations, tokens, and results
        iteration = 0
        llm_calls = 0
        parse_error_count = 0  # Track consecutive parse errors
        MAX_PARSE_ERRORS = 3   # Max retries for parse errors
        total_input_tokens = 0
        total_output_tokens = 0
        tool_results = []

        while iteration < self.MAX_TOOL_ITERATIONS:
            iteration += 1
            debug_print(f"Iteration {iteration}")

            # Call LLM
            llm_result = self._call_llm(messages)
            llm_calls += 1
            total_input_tokens += llm_result.input_tokens
            total_output_tokens += llm_result.output_tokens
            debug_print(f"LLM response: {llm_result.text[:200]}...")
            debug_print(f"Tokens: +{llm_result.input_tokens} in, +{llm_result.output_tokens} out")

            # Parse response
            parsed = self._parse_interactive_response(llm_result.text)

            if parsed.get('error'):
                parse_error_count += 1
                debug_print(f"Parse error ({parse_error_count}/{MAX_PARSE_ERRORS}): {parsed['error']}")

                # If too many parse errors, give up and return what we have
                if parse_error_count >= MAX_PARSE_ERRORS:
                    debug_print(f"Max parse errors reached, returning error response")
                    return ChatResponse(
                        success=False,
                        message="I had trouble understanding the response format. Please try rephrasing your request.",
                        route_type=RouteType.AGENTIC.value,
                        error=f"Max parse errors ({MAX_PARSE_ERRORS}) reached: {parsed['error']}",
                        input_tokens=total_input_tokens,
                        output_tokens=total_output_tokens,
                        llm_calls=llm_calls
                    )

                # Try to recover - ask LLM to fix its response
                messages.append({'role': 'assistant', 'content': llm_result.text})
                messages.append({
                    'role': 'user',
                    'content': f"Your response wasn't valid JSON. Please respond with a JSON object containing either 'tool_call' or 'response'. Error: {parsed['error']}"
                })
                continue
            else:
                # Reset parse error count on successful parse
                parse_error_count = 0

            # Check for final response
            if parsed.get('response'):
                debug_print("Got final response")
                debug_print(f"Total tokens: {total_input_tokens} in, {total_output_tokens} out")
                return ChatResponse(
                    success=True,
                    message=parsed['response'],
                    route_type=RouteType.AGENTIC.value,
                    data={'tool_results': tool_results} if tool_results else None,
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    llm_calls=llm_calls
                )

            # Check for tool call
            if parsed.get('tool_call'):
                tool_call = parsed['tool_call']
                debug_print(f"Tool call: {tool_call.get('tool')}.{tool_call.get('action', 'search')}")

                # Execute the tool
                tool_result = self._execute_tool_call(tool_call)
                tool_results.append({
                    'tool': tool_call.get('tool', 'unknown'),
                    'action': tool_call.get('action') or 'search',  # Default to 'search' if None
                    'resource_type': tool_call.get('resource_type', 'note'),
                    'result': tool_result
                })

                # Add assistant message (the tool call)
                messages.append({'role': 'assistant', 'content': llm_result.text})

                # Add tool result as user message (system feedback)
                result_message = self._format_tool_result(tool_result)
                messages.append({
                    'role': 'user',
                    'content': f"Tool result:\n{result_message}\n\nContinue with the next step, or provide a final response if done."
                })

                debug_print(f"Tool result: {result_message[:200]}...")
                continue

            # Neither response nor tool_call - ask for clarification
            debug_print("No tool_call or response found")
            messages.append({'role': 'assistant', 'content': llm_result.text})
            messages.append({
                'role': 'user',
                'content': "Please respond with either a 'tool_call' to take an action, or a 'response' to answer the user."
            })

        # Max iterations reached
        debug_print(f"Max iterations ({self.MAX_TOOL_ITERATIONS}) reached")
        debug_print(f"Total tokens: {total_input_tokens} in, {total_output_tokens} out")
        return ChatResponse(
            success=False,
            message="I wasn't able to complete the request after multiple attempts. Please try rephrasing your request.",
            route_type=RouteType.AGENTIC.value,
            error=f"Max iterations ({self.MAX_TOOL_ITERATIONS}) reached",
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            llm_calls=llm_calls
        )

    def _handle_clarify(
        self,
        user_content: str,
        route_result: RouterResult
    ) -> ChatResponse:
        """
        Handle CLARIFY route - request is ambiguous.
        """
        debug_print("Handling CLARIFY route")

        # Generate clarification question
        question = route_result.clarification_question or \
            "Could you provide more details about what you'd like me to do?"

        return self._ask_clarification(question, user_content)

    # =========================================================================
    # Clarification Handling
    # =========================================================================

    def _ask_clarification(
        self,
        question: str,
        original_message: str,
        options: List[str] = None
    ) -> ChatResponse:
        """Set clarification state and return question."""
        self.memory_state.set_clarification(
            question=question,
            options=options,
            context={'original_message': original_message}
        )

        return ChatResponse(
            success=True,
            message=question,
            route_type=RouteType.CLARIFY.value,
            data={'options': options} if options else None
        )

    def _handle_clarification_response(self, user_content: str) -> ChatResponse:
        """Handle user's response to a clarification question."""
        debug_print("Handling clarification response")

        # Get original context
        clarification = self.memory_state.pending_clarification
        original_message = clarification.get('context', {}).get('original_message', '')

        # Clear clarification state
        self.memory_state.clear_clarification()

        # Combine original message with clarification
        enhanced_message = f"{original_message} {user_content}".strip()

        # Re-route with enhanced context
        route_result = self._route_message(enhanced_message)

        if route_result.route_type == RouteType.AGENTIC:
            return self._handle_agentic(enhanced_message, route_result)
        elif route_result.route_type == RouteType.DIRECT:
            return self._handle_direct(enhanced_message, route_result)
        else:
            # Still unclear - ask again
            return self._ask_clarification(
                "I still need more information. What specifically would you like me to do?",
                original_message
            )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _route_message(self, user_content: str) -> RouterResult:
        """Route the message using the Router."""
        # Update router's memory state reference in case it changed
        self.router.memory = self.memory_state
        return self.router.classify(user_content)

    def _call_llm(self, messages: List[Dict]) -> LLMResult:
        """Call LLM and return response with token usage."""
        if not self.llm_client:
            return LLMResult(
                text="I don't have access to generate a response right now.",
                success=False,
                error="No LLM client available"
            )

        try:
            response = self.llm_client.get_completion(
                messages=messages,
                tool_name=self.conversation.model_name
            )

            # Extract token usage (handle different response formats)
            input_tokens = 0
            output_tokens = 0
            if hasattr(response, 'usage') and response.usage:
                input_tokens = getattr(response.usage, 'prompt_tokens', 0) or 0
                output_tokens = getattr(response.usage, 'completion_tokens', 0) or 0

            return LLMResult(
                text=response.choices[0].message.content,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                success=True
            )

        except Exception as e:
            debug_print(f"LLM call failed: {e}")
            return LLMResult(
                text=f"I encountered an error: {str(e)}",
                success=False,
                error=str(e)
            )

    def _parse_interactive_response(self, llm_response: str) -> Dict[str, Any]:
        """
        Parse LLM response for interactive loop.

        Expects JSON with either:
        - {"tool_call": {...}} - to execute a tool
        - {"response": "..."} - final answer to user

        Returns dict with parsed content or {'error': '...'} on failure.
        """
        import re

        # Try to extract JSON from response
        json_patterns = [
            r'```json\s*(.*?)\s*```',  # Markdown code block
            r'```\s*(.*?)\s*```',  # Generic code block
            r'(\{.*\})',  # Raw JSON object
        ]

        json_str = None
        for pattern in json_patterns:
            match = re.search(pattern, llm_response, re.DOTALL)
            if match:
                json_str = match.group(1).strip()
                break

        if not json_str:
            # Try the whole response as JSON
            json_str = llm_response.strip()

        try:
            data = json.loads(json_str)

            # Validate structure
            if isinstance(data, dict):
                # Check for tool_call (singular)
                if 'tool_call' in data and data['tool_call']:
                    return {'tool_call': data['tool_call'], 'thinking': data.get('thinking', '')}

                # Check for tool_calls (plural) - handle legacy format
                if 'tool_calls' in data and data['tool_calls']:
                    # Take first tool call only
                    return {'tool_call': data['tool_calls'][0], 'thinking': data.get('thinking', '')}

                # Check for response
                if 'response' in data and data['response']:
                    return {'response': data['response'], 'thinking': data.get('thinking', '')}

            return {'error': 'JSON must contain either "tool_call" or "response"'}

        except json.JSONDecodeError as e:
            return {'error': f'Invalid JSON: {str(e)}'}

    def _execute_tool_call(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a single tool call and return result.

        Args:
            tool_call: Dict with tool, action, resource_type, params/filters

        Returns:
            Dict with status, data, message, error
        """
        from .tools.base import ToolCall as ToolCallObj

        # Normalize the tool call structure
        tool_name = tool_call.get('tool', 'search_tool')
        action = tool_call.get('action', 'search')
        resource_type = tool_call.get('resource_type', 'note')

        # Handle params - could be in 'params', 'filters', or at top level
        params = tool_call.get('params', {})
        if not params and tool_call.get('filters'):
            params = {'filters': tool_call['filters']}
        if not params and tool_call.get('query'):
            params = {'query': tool_call['query']}

        # For search_tool, extract filters/query from top level if needed
        if tool_name == 'search_tool':
            if 'filters' not in params and tool_call.get('filters'):
                params['filters'] = tool_call['filters']
            if 'query' not in params and tool_call.get('query'):
                params['query'] = tool_call['query']
            if 'limit' not in params and tool_call.get('limit'):
                params['limit'] = tool_call['limit']

        debug_print(f"Executing: {tool_name}.{action}({resource_type})", params)

        try:
            # Create tool call object
            call_obj = ToolCallObj(
                tool=tool_name,
                action=action,
                resource_type=resource_type,
                params=params
            )

            # Execute via registry
            result = self.tool_registry.execute(call_obj)

            return {
                'status': result.status.value,
                'data': result.data,
                'message': result.message,
                'error': result.error
            }

        except Exception as e:
            debug_print(f"Tool execution error: {e}")
            return {
                'status': 'error',
                'data': None,
                'message': '',
                'error': str(e)
            }

    def _format_tool_result(self, result: Dict[str, Any]) -> str:
        """
        Format tool result for LLM consumption.

        Makes the result readable so LLM can understand what happened.
        """
        status = result.get('status', 'unknown')
        message = result.get('message', '')
        error = result.get('error', '')
        data = result.get('data')

        lines = []

        # Status line
        if status == 'success':
            lines.append(f"✓ Success: {message}" if message else "✓ Success")
        elif status == 'not_found':
            lines.append(f"✗ Not found: {error or message or 'Item not found'}")
        else:
            lines.append(f"✗ Error: {error or message or 'Unknown error'}")

        # Data details
        if data:
            if isinstance(data, dict):
                # Single item
                if data.get('id'):
                    item_type = 'Item'
                    title = data.get('title') or data.get('name') or 'Untitled'
                    lines.append(f"  ID: {data['id']}")
                    lines.append(f"  Title: {title}")

                    # Add relevant fields
                    if data.get('status'):
                        lines.append(f"  Status: {data['status']}")
                    if data.get('priority'):
                        lines.append(f"  Priority: {data['priority']}")
                    if data.get('due_date'):
                        lines.append(f"  Due: {data['due_date']}")
                    if data.get('container_type'):
                        lines.append(f"  Container: {data['container_type']} (ID: {data.get('container_id', '?')})")

                # List of items
                elif data.get('items'):
                    items = data['items']
                    count = data.get('count', len(items))
                    lines.append(f"  Found {count} item(s):")

                    for item in items[:5]:  # Show first 5
                        title = item.get('title') or item.get('name') or 'Untitled'
                        item_id = item.get('id', '?')
                        extra = []
                        if item.get('status'):
                            extra.append(item['status'])
                        if item.get('due_date'):
                            extra.append(f"due: {item['due_date']}")
                        extra_str = f" ({', '.join(extra)})" if extra else ""
                        lines.append(f"    - {title} [ID: {item_id}]{extra_str}")

                    if count > 5:
                        lines.append(f"    ... and {count - 5} more")

                # Count result
                elif 'count' in data:
                    lines.append(f"  Count: {data['count']}")

        return "\n".join(lines)

    def _generate_simple_response(
        self,
        user_content: str,
        route_result: RouterResult
    ) -> ChatResponse:
        """Generate simple response without LLM."""
        # For common patterns, provide canned responses
        lower = user_content.lower()

        if any(g in lower for g in ['hello', 'hi', 'hey', 'oi', 'olá']):
            return ChatResponse(
                success=True,
                message="Hello! How can I help you with your notes and tasks today?",
                route_type=RouteType.DIRECT.value
            )

        if any(t in lower for t in ['thank', 'thanks', 'obrigado']):
            return ChatResponse(
                success=True,
                message="You're welcome! Let me know if you need anything else.",
                route_type=RouteType.DIRECT.value
            )

        if 'help' in lower:
            return ChatResponse(
                success=True,
                message="I can help you manage your notes, tasks, and projects. "
                        "Try saying things like:\n"
                        "- Create a task called...\n"
                        "- Search for notes about...\n"
                        "- List my active projects\n"
                        "- Complete the task...",
                route_type=RouteType.DIRECT.value
            )

        # Generic fallback
        return ChatResponse(
            success=True,
            message="I understand. What would you like me to do?",
            route_type=RouteType.DIRECT.value
        )

    def _save_user_message(self, content: str) -> Message:
        """Save user message to database."""
        return Message.objects.create(
            conversation=self.conversation,
            role='user',
            content=content
        )

    def _save_assistant_message(
        self,
        content: str,
        response: ChatResponse
    ) -> Message:
        """Save assistant message to database with token tracking."""
        import uuid

        message = Message.objects.create(
            conversation=self.conversation,
            role='assistant',
            content=content,
            model_used=self.conversation.model_name or "",
            processing_time_ms=response.processing_time_ms,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            is_error=not response.success,
            error_message=response.error or "",
            has_vel_commands=bool(response.data and response.data.get('tool_results')),
            vel_session_id=str(uuid.uuid4())[:8] if response.data and response.data.get('tool_results') else ""
        )

        # Update conversation token counters
        self.conversation.total_input_tokens = (self.conversation.total_input_tokens or 0) + response.input_tokens
        self.conversation.total_output_tokens = (self.conversation.total_output_tokens or 0) + response.output_tokens
        self.conversation.save(update_fields=['total_input_tokens', 'total_output_tokens', 'last_message_at'])

        debug_print(f"Saved tokens - Message: {response.input_tokens}in/{response.output_tokens}out, "
                   f"Conversation total: {self.conversation.total_input_tokens}in/{self.conversation.total_output_tokens}out")

        # Save tool executions to ChatVELExecution (like V1 does)
        if response.data and response.data.get('tool_results'):
            self._save_tool_executions(message, response.data['tool_results'])

        return message

    def _save_tool_executions(self, message: Message, tool_results: list):
        """Save tool execution records for V2 (mirrors V1's _save_vel_executions)."""
        import uuid

        for tool_result in tool_results:
            tool_name = tool_result.get('tool') or 'unknown'
            action = tool_result.get('action') or 'search'
            resource_type = tool_result.get('resource_type') or ''
            result = tool_result.get('result') or {}

            # Build action name (e.g., "search_note" or "create_task")
            action_name = f"{action}_{resource_type}" if resource_type else action

            # Map status
            status = result.get('status', 'error')
            if status == 'success':
                db_status = 'success'
            elif status == 'not_found':
                db_status = 'error'
            else:
                db_status = 'error'

            # Build result summary
            result_message = result.get('message', '')
            result_error = result.get('error', '')
            result_summary = result_message or result_error or f"{action} completed"

            # Build result_data with item info for links
            result_data = {}
            data = result.get('data')
            if data:
                if isinstance(data, dict):
                    # Single item created/updated
                    if data.get('id'):
                        result_data = {
                            'id': data.get('id'),
                            'title': data.get('title') or data.get('name'),
                            'type': resource_type,
                        }
                    # List of items
                    elif data.get('items'):
                        result_data = {
                            'count': data.get('count', len(data['items'])),
                            'items': data['items'][:5],  # Store first 5 for reference
                            'type': resource_type,
                        }

            ChatVELExecution.objects.create(
                message=message,
                audit_id=str(uuid.uuid4())[:8],
                action=action_name,
                status=db_status,
                result_summary=result_summary[:500],  # Limit length
                result_data=result_data,
            )


def send_message_v2(user, conversation: Conversation, content: str, llm_client=None) -> ChatResponse:
    """
    Convenience function to send a message using V2 architecture.

    Usage:
        response = send_message_v2(user, conversation, "Create a task")
        print(response.message)
    """
    service = ChatServiceV2(user, conversation, llm_client)
    return service.send_message(content)
