"""
Chat V3 Agent Loop

The iterative execution engine - heart of the V3 architecture.

Flow:
1. Build context for iteration
2. Call LLM
3. Parse response
4. Execute tool (if any)
5. Loop until final response or max iterations

Phase 2 additions:
- Plan persistence via Planner
- Step tracking and progress
- Discovery and learning recording
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from django.utils import timezone

from .config import config, RouteType
from .types import (
    AgentResponse, AgentResult, Iteration,
    ToolCall, ToolResult, Plan, Discovery
)
from .parser import ResponseParser
from .planner import Planner
from .prompts import (
    build_agentic_prompt,
    build_continuation_prompt,
    build_retry_prompt
)
from .tools.base import ToolRegistry
from .exceptions import ParseError, MaxIterationsError

logger = logging.getLogger(__name__)


class AgentLoop:
    """
    Iterative execution engine for agentic tasks.

    The loop:
    1. Calls LLM with context
    2. Parses JSON response
    3. Executes tool call (if any)
    4. Continues until final response or max iterations
    """

    def __init__(self, user, conversation, llm_client=None):
        """
        Initialize the agent loop.

        Args:
            user: Django user object
            conversation: Conversation model instance
            llm_client: LLM client (will use default if not provided)
        """
        self.user = user
        self.conversation = conversation
        self.llm_client = llm_client
        self.tool_registry = ToolRegistry(user)
        self.parser = ResponseParser()
        self.planner = Planner(conversation)

        # State
        self.iterations: List[Iteration] = []
        self.discoveries: List[Discovery] = []
        self.plan: Optional[Plan] = None
        self.db_plan = None  # Persisted plan model

        # Token tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0

        # Check for existing active plan
        self._load_active_plan()

    def run(self, user_message: str) -> AgentResult:
        """
        Run the agent loop.

        Args:
            user_message: The user's request

        Returns:
            AgentResult with final response and metadata
        """
        consecutive_errors = 0

        for i in range(config.MAX_ITERATIONS):
            try:
                # Build context for this iteration
                context = self._build_iteration_context(user_message, i)

                # Call LLM
                llm_result = self._call_llm(context, i)

                # Parse response
                try:
                    parsed = self.parser.parse(llm_result['text'])
                    consecutive_errors = 0  # Reset on successful parse
                except ParseError as e:
                    consecutive_errors += 1
                    logger.warning(f"Parse error (attempt {consecutive_errors}): {e}")

                    if consecutive_errors >= config.MAX_PARSE_RETRIES:
                        return AgentResult(
                            success=False,
                            response="I had trouble processing this request. Could you try rephrasing?",
                            iterations=self.iterations,
                            error=str(e),
                            total_input_tokens=self.total_input_tokens,
                            total_output_tokens=self.total_output_tokens
                        )

                    # Add retry guidance and continue
                    self._add_retry_context(str(e))
                    continue

                # Store plan if created (and persist to database)
                if parsed.plan and not self.plan:
                    self.plan = parsed.plan
                    self.db_plan = self.planner.create_plan_from_response(parsed, user_message)
                    if self.db_plan:
                        self.planner.start_plan(self.db_plan)
                    logger.info(f"Plan created: {self.plan.goal} ({len(self.plan.steps)} steps)")

                # Check for final response
                if parsed.is_final():
                    # Complete the plan if we have one
                    if self.db_plan:
                        self.planner.complete_plan(self.db_plan)

                    return AgentResult(
                        success=True,
                        response=parsed.response,
                        iterations=self.iterations,
                        plan=self.plan,
                        total_input_tokens=self.total_input_tokens,
                        total_output_tokens=self.total_output_tokens
                    )

                # Execute tool call
                if parsed.has_tool_call():
                    tool_result = self._execute_tool(parsed.tool_call)

                    # Record iteration
                    self.iterations.append(Iteration(
                        thinking=parsed.thinking,
                        tool_call=parsed.tool_call,
                        result=tool_result,
                        timestamp=datetime.now()
                    ))

                    # Record discovery (both in-memory and persistent)
                    self.discoveries.append(Discovery(
                        tool=parsed.tool_call.tool,
                        query=parsed.tool_call.params,
                        result_summary=tool_result.summary,
                        result_data=tool_result.data
                    ))
                    self.planner.record_discovery(
                        tool=parsed.tool_call.tool,
                        query=parsed.tool_call.params,
                        result_summary=tool_result.summary,
                        result_data=tool_result.data
                    )

                    # Update plan progress if applicable
                    if self.plan and parsed.plan_step is not None:
                        self._update_plan_progress(parsed.plan_step, tool_result)

                    # Handle plan adaptation based on results
                    if self.db_plan:
                        if tool_result.success:
                            self._check_plan_adaptation(parsed.tool_call, tool_result)
                        else:
                            # Adapt plan for error
                            self.adapt_plan_for_error(
                                tool_result.error or "Unknown error",
                                parsed.tool_call
                            )

                    continue

                # Neither response nor tool call - shouldn't happen
                logger.warning("LLM returned neither response nor tool_call")
                consecutive_errors += 1
                self._add_retry_context("Response must include either 'tool_call' or 'response'")

            except Exception as e:
                logger.error(f"Error in iteration {i}: {e}")
                consecutive_errors += 1

                if consecutive_errors >= config.MAX_CONSECUTIVE_ERRORS:
                    return AgentResult(
                        success=False,
                        response="I encountered an error processing your request. Please try again.",
                        iterations=self.iterations,
                        error=str(e),
                        total_input_tokens=self.total_input_tokens,
                        total_output_tokens=self.total_output_tokens
                    )

        # Max iterations reached
        return AgentResult(
            success=False,
            response=self._build_max_iterations_response(),
            iterations=self.iterations,
            plan=self.plan,
            error="Max iterations reached",
            total_input_tokens=self.total_input_tokens,
            total_output_tokens=self.total_output_tokens
        )

    def _build_iteration_context(self, user_message: str, iteration: int) -> List[Dict]:
        """Build context for a single iteration."""
        messages = []

        # System prompt (first iteration gets full context)
        if iteration == 0:
            # Combine in-memory working memory with persistent memory
            working_memory = self._format_working_memory()
            memory_context = self._get_memory_context()
            if memory_context and working_memory:
                combined_memory = f"{working_memory}\n\n{memory_context}"
            else:
                combined_memory = working_memory or memory_context

            # Get plan context (from DB or in-memory)
            plan_context = ""
            if self.db_plan:
                plan_context = self.db_plan.to_context_string()
            elif self.plan:
                plan_context = self.plan.to_context_string()

            system_prompt = build_agentic_prompt(
                user=self.user,
                working_memory=combined_memory,
                plan_context=plan_context,
                conversation_context=self._get_conversation_context()
            )
            messages.append({"role": "system", "content": system_prompt})

            # Add planning hint if task may need a plan
            planning_hint = self._get_planning_hint(user_message)
            if planning_hint and not self.plan:
                user_content = f"{user_message}\n\n{planning_hint}"
            else:
                user_content = user_message

            messages.append({"role": "user", "content": user_content})
        else:
            # Continuation - include previous tool results
            last_iteration = self.iterations[-1] if self.iterations else None
            if last_iteration and last_iteration.result:
                continuation = build_continuation_prompt(last_iteration.result.summary)
                messages.append({"role": "user", "content": continuation})

        return messages

    def _call_llm(self, messages: List[Dict], iteration: int) -> Dict:
        """
        Call the LLM.

        Args:
            messages: List of message dicts
            iteration: Current iteration number

        Returns:
            Dict with 'text', 'input_tokens', 'output_tokens'
        """
        # Get LLM client
        if self.llm_client is None:
            from .llm import get_llm_client
            self.llm_client = get_llm_client(self.conversation)

        # Build full message list for non-first iterations
        if iteration > 0:
            # Reconstruct conversation from iterations
            full_messages = self._build_full_message_history(messages)
        else:
            full_messages = messages

        # Call LLM
        result = self.llm_client.chat(full_messages)

        # Track tokens
        self.total_input_tokens += result.get('input_tokens', 0)
        self.total_output_tokens += result.get('output_tokens', 0)

        return result

    def _build_full_message_history(self, new_messages: List[Dict]) -> List[Dict]:
        """Build full message history including previous iterations."""
        messages = []

        # Start with system prompt from first iteration
        if self.iterations:
            # Get the original system prompt
            first_context = build_agentic_prompt(
                user=self.user,
                working_memory=self._format_working_memory(),
                plan_context=self.plan.to_context_string() if self.plan else "",
                conversation_context=self._get_conversation_context()
            )
            messages.append({"role": "system", "content": first_context})

        # Add iteration history
        for it in self.iterations:
            # Assistant's tool call
            assistant_content = {
                "thinking": it.thinking,
            }
            if it.tool_call:
                assistant_content["tool_call"] = {
                    "tool": it.tool_call.tool,
                    "params": it.tool_call.params
                }
            messages.append({
                "role": "assistant",
                "content": str(assistant_content)
            })

            # Tool result
            if it.result:
                messages.append({
                    "role": "user",
                    "content": build_continuation_prompt(it.result.summary)
                })

        # Add new messages
        messages.extend(new_messages)

        return messages

    def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
        """Execute a tool call."""
        logger.info(f"Executing tool: {tool_call.tool} with params: {tool_call.params}")
        return self.tool_registry.execute(tool_call)

    def _format_working_memory(self) -> str:
        """Format working memory (discoveries) for context."""
        if not self.discoveries:
            return ""

        lines = ["## Working Memory (previous discoveries)"]
        for d in self.discoveries[-config.MAX_DISCOVERIES_IN_CONTEXT:]:
            lines.append(f"- {d.result_summary}")

        return "\n".join(lines)

    def _get_conversation_context(self) -> str:
        """Get recent conversation history."""
        messages = self.conversation.messages.order_by('-created_at')[:config.MAX_CONVERSATION_HISTORY]
        messages = list(reversed(messages))

        if not messages:
            return ""

        lines = ["## Recent Conversation"]
        for msg in messages:
            role = "User" if msg.role == "user" else "Assistant"
            content = msg.content[:300] + "..." if len(msg.content) > 300 else msg.content
            lines.append(f"**{role}:** {content}")

        return "\n".join(lines)

    def _update_plan_progress(self, step_index: int, result: ToolResult):
        """Update plan progress after a step completes."""
        # Update in-memory plan
        if self.plan and step_index < len(self.plan.steps):
            step = self.plan.steps[step_index]
            if result.success:
                step.mark_completed(result.summary, result.data)
            else:
                step.mark_failed(result.error or "Unknown error")

            # Advance to next step if current completed
            if step_index == self.plan.current_step:
                self.plan.advance()

        # Update persisted plan
        if self.db_plan:
            if result.success:
                self.planner.complete_step(
                    self.db_plan,
                    step_index,
                    result.summary,
                    result.data
                )
            else:
                self.planner.fail_step(
                    self.db_plan,
                    step_index,
                    result.error or "Unknown error"
                )

    def _add_retry_context(self, error_message: str):
        """Add retry guidance after an error."""
        # This will be picked up in the next iteration
        retry_discovery = Discovery(
            tool="system",
            query={"error": error_message},
            result_summary=f"Error: {error_message}. Please try again with valid JSON."
        )
        self.discoveries.append(retry_discovery)

    def _build_max_iterations_response(self) -> str:
        """Build a helpful response when max iterations reached."""
        completed = [it for it in self.iterations if it.result and it.result.success]

        if completed:
            summaries = [it.result.summary for it in completed[:5]]
            return f"""I wasn't able to complete everything, but here's what I found:

{chr(10).join(f'- {s}' for s in summaries)}

Would you like me to continue with a more specific request?"""

        return """I had trouble completing this request. Could you try:
- Breaking it into smaller steps
- Being more specific about what you need
- Checking if the items you mentioned exist"""

    def _load_active_plan(self):
        """Load any existing active plan for this conversation."""
        active_plan = self.planner.get_active_plan()
        if active_plan:
            self.db_plan = active_plan
            self.plan = active_plan.to_dataclass()
            logger.info(f"Loaded active plan {active_plan.id}: {active_plan.goal}")

    def _get_memory_context(self) -> str:
        """Get memory context from the planner."""
        return self.planner.get_memory_context()

    def _get_planning_hint(self, user_message: str) -> str:
        """Get planning hint if task may need a plan."""
        return self.planner.get_planning_hint(user_message)

    def _check_plan_adaptation(self, tool_call: ToolCall, result: ToolResult):
        """
        Check if plan should be adapted based on tool results.

        Triggers adaptation for:
        - Search found many items (may need batching)
        - Search found no items (may need different approach)
        - Important context discovered (add to plan discoveries)
        """
        if not self.db_plan or not result.success:
            return

        # Extract result data
        data = result.data if result.data else {}

        # Check for search results that may need batching
        if tool_call.tool == 'search' and isinstance(data, list):
            item_count = len(data)

            # Store discovery of how many items were found
            resource_type = tool_call.params.get('resource_type', 'items')
            self.db_plan.add_discovery(
                f"found_{resource_type}_count",
                item_count
            )

            # Check if batching is needed
            if self.planner.should_adapt_for_batch(self.db_plan, item_count):
                # Get the next step to see what action is planned
                next_step = self.db_plan.get_next_pending_step()
                if next_step and next_step.action_type in ['move', 'update', 'complete', 'delete']:
                    # Create batch steps
                    batch_steps = self.planner.create_batch_steps(
                        action=next_step.action_type,
                        items=data,
                        batch_size=config.BATCH_SIZE if hasattr(config, 'BATCH_SIZE') else 5
                    )

                    if len(batch_steps) > 1:
                        self.planner.adapt_plan(
                            self.db_plan,
                            reason=f"Found {item_count} items, creating batch processing steps",
                            new_steps=batch_steps,
                            skip_current=True  # Skip the original single-item step
                        )
                        logger.info(f"Plan adapted for batch processing: {item_count} items in {len(batch_steps)} batches")

        # Check for empty search results
        elif tool_call.tool == 'search' and (not data or (isinstance(data, list) and len(data) == 0)):
            resource_type = tool_call.params.get('resource_type', 'items')
            query = tool_call.params.get('query', '')

            # Record that nothing was found
            self.planner.record_learning(
                f"Search for {resource_type} with query '{query}' returned no results",
                learning_type='empty_search'
            )

            # Note: The LLM will handle this in the next iteration
            # We could add adaptation logic here to suggest alternatives

        # For execute actions, store important IDs
        elif tool_call.tool == 'execute':
            action = tool_call.params.get('action', '')
            if action == 'create' and isinstance(data, dict):
                # Store created item ID
                item_id = data.get('id')
                item_type = tool_call.params.get('resource_type', 'item')
                if item_id:
                    self.db_plan.add_discovery(f"created_{item_type}_id", item_id)

    def adapt_plan_for_error(self, error: str, tool_call: ToolCall):
        """
        Adapt plan after a tool error.

        Args:
            error: The error message
            tool_call: The tool call that failed
        """
        if not self.db_plan:
            return

        # Record the failed approach
        self.planner.record_failed_approach(
            approach=f"{tool_call.tool} with {tool_call.params}",
            error=error
        )

        # Check if this is a recoverable error
        recoverable_patterns = [
            'not found',
            'does not exist',
            'no results',
            'permission',
        ]

        is_recoverable = any(pattern in error.lower() for pattern in recoverable_patterns)

        if is_recoverable:
            # The LLM will try a different approach
            logger.info(f"Recoverable error in plan: {error}")
        else:
            # May need to fail the current step
            current_step = self.db_plan.get_current_step()
            if current_step:
                self.planner.fail_step(self.db_plan, current_step.order, error)
                logger.warning(f"Plan step failed: {error}")
