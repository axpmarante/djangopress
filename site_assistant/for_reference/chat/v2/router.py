"""
Chat V2 Router - Layer 0

Classifies incoming messages into:
- DIRECT: Can answer immediately with current context
- AGENTIC: Needs to create a plan and use tools
- CLARIFY: Request is ambiguous, need user clarification

The router is the first layer in V2 architecture. It uses a fast LLM
(gemini-lite) to classify requests with high accuracy.

Key insight: The system prompt has STRUCTURE (names, counts, IDs) but not
CONTENT (actual items, descriptions). The classifier understands this
distinction to route appropriately.
"""

import re
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from .memory import MemoryState, RouteType
from .prompts import (
    ROUTER_CLASSIFICATION_PROMPT,
    build_router_context,
    parse_router_response
)


@dataclass
class RouterResult:
    """Result from router classification."""
    route_type: RouteType
    confidence: float  # 0.0 to 1.0
    reason: str  # Brief explanation for debugging

    # For DIRECT routes - the actual response (combined classifier+responder)
    direct_response: Optional[str] = None

    # For AGENTIC routes
    detected_intent: Optional[str] = None  # e.g., "create_task", "search_notes"
    detected_entities: Optional[Dict[str, Any]] = None  # e.g., {"project": "Finance"}

    # For CLARIFY routes
    clarification_question: Optional[str] = None
    clarification_options: Optional[List[str]] = None

    # Token tracking from classification LLM call
    input_tokens: int = 0
    output_tokens: int = 0


class Router:
    """
    Layer 0: Request Classification (Combined Classifier + DIRECT Responder)

    Determines how to handle each incoming message:
    - Check if continuing an existing plan
    - Check if responding to a clarification
    - Otherwise, use LLM to classify as DIRECT/AGENTIC/CLARIFY

    For DIRECT routes, the LLM also provides the response immediately,
    saving an additional LLM call.

    Uses full conversation history to understand context (e.g., "yes" makes
    sense when following a question).
    """

    # Cancellation patterns (still use fast pattern for these)
    CANCELLATION_PATTERNS = [
        r'^(cancel|stop|abort|nevermind|never mind|cancelar|parar|deixa)\s*$',
    ]

    # Fast patterns for obvious AGENTIC mutations (skip LLM call)
    OBVIOUS_AGENTIC_PATTERNS = [
        r'\b(create|criar|make|adicionar|add)\b.*(task|tarefa|note|nota|project|projeto)',
        r'\b(delete|deletar|remove|remover|archive|arquivar)\b',
        r'\b(complete|completar|finish|finalizar|done|feito)\b.*(task|tarefa)',
        r'\b(move|mover)\b.*(to|para)',
    ]

    def __init__(self, user, conversation, memory_state: MemoryState, context_builder=None):
        self.user = user
        self.conversation = conversation
        self.memory = memory_state
        self.context_builder = context_builder  # For building full context with history

    def classify(self, message: str) -> RouterResult:
        """
        Classify the incoming message using combined classifier + DIRECT responder.

        Order of checks:
        1. Is there a pending clarification? → Pass to LLM with context
        2. Is there an active plan? → Check for continuation/cancellation
        3. Fast pattern check for obvious AGENTIC mutations
        4. LLM classification (also provides response for DIRECT)
        """
        message_lower = message.lower().strip()

        # 1. Pending clarification - let LLM handle with full context
        # (removed special handling - LLM sees conversation history)

        # 2. Check for active plan continuation/cancellation
        if self.memory.is_plan_active():
            cancel_result = self._check_cancellation(message_lower)
            if cancel_result:
                return cancel_result
            # Otherwise, let LLM decide with conversation context

        # 3. Fast patterns for obvious AGENTIC mutations (saves LLM call)
        fast_result = self._fast_pattern_check(message_lower)
        if fast_result:
            return fast_result

        # 4. LLM classification (combined classifier + DIRECT responder)
        return self._classify_by_llm(message)

    def _check_cancellation(self, message_lower: str) -> Optional[RouterResult]:
        """Check for explicit cancellation of active plan."""
        for pattern in self.CANCELLATION_PATTERNS:
            if re.search(pattern, message_lower):
                return RouterResult(
                    route_type=RouteType.DIRECT,
                    confidence=0.95,
                    reason="User cancelled active plan",
                    direct_response="Ok, I've cancelled the current operation.",
                    detected_intent="cancel_plan"
                )
        return None

    def _fast_pattern_check(self, message_lower: str) -> Optional[RouterResult]:
        """
        Fast pattern check for obvious AGENTIC mutations.
        Returns None if LLM classification is needed.

        Note: We don't fast-track DIRECT patterns because we want
        the LLM to provide the response, not just classify.
        """
        # Obvious AGENTIC mutations (skip LLM classification call)
        for pattern in self.OBVIOUS_AGENTIC_PATTERNS:
            if re.search(pattern, message_lower):
                return RouterResult(
                    route_type=RouteType.AGENTIC,
                    confidence=0.95,
                    reason=f"Fast pattern (mutation): {pattern}"
                )

        # Need LLM classification (will also provide response if DIRECT)
        return None

    def _extract_entities(self, message: str) -> Dict[str, Any]:
        """Extract entities (resource types, names, etc.) from message."""
        entities = {}

        # Extract resource type
        resource_patterns = {
            'note': r'\b(note|nota)\b',
            'task': r'\b(task|tarefa)\b',
            'project': r'\b(project|projeto)\b',
            'area': r'\b(area|área)\b',
        }
        for resource_type, pattern in resource_patterns.items():
            if re.search(pattern, message, re.IGNORECASE):
                entities['resource_type'] = resource_type
                break

        # Extract quoted text (likely a title or name)
        quoted = re.findall(r'["\']([^"\']+)["\']', message)
        if quoted:
            entities['quoted_text'] = quoted

        # Extract "called X" or "named X" patterns
        name_match = re.search(r'(?:called|named|titled|chamado|chamada)\s+["\']?([^"\',.]+)["\']?', message, re.IGNORECASE)
        if name_match:
            entities['name'] = name_match.group(1).strip()

        # Extract "in/to project X" patterns
        container_match = re.search(r'(?:in|to|into|no|na|para)\s+(?:the\s+)?(?:project|projeto)\s+["\']?([^"\',.]+)["\']?', message, re.IGNORECASE)
        if container_match:
            entities['container_name'] = container_match.group(1).strip()
            entities['container_type'] = 'project'

        # Extract "in/to area X" patterns
        area_match = re.search(r'(?:in|to|into|no|na|para)\s+(?:the\s+)?(?:area|área)\s+["\']?([^"\',.]+)["\']?', message, re.IGNORECASE)
        if area_match:
            entities['container_name'] = area_match.group(1).strip()
            entities['container_type'] = 'area'

        return entities

    def _classify_by_llm(self, message: str) -> RouterResult:
        """
        Combined classifier + DIRECT responder.

        Uses the conversation's selected model with full context including:
        - User profile and preferences
        - PARA structure (areas, projects, task counts)
        - Conversation history

        For DIRECT routes, the LLM also provides the response immediately.
        """
        from ai_assistant.llm_config import LLMBase

        # Build full context (user profile, PARA structure, etc.)
        if self.context_builder:
            # Use the context builder to get full user context
            # Pass DIRECT route type to get rich PARA context
            dummy_route = RouterResult(
                route_type=RouteType.DIRECT,
                confidence=0.0,
                reason="building context"
            )
            context = self.context_builder.build(dummy_route, include_tools=False)

            # Combine all context sections (system_prompt + user_context + memory_context)
            # This gives the LLM the full rich context like the old DIRECT handler had
            user_context = context.system_prompt
            if context.user_context:
                user_context += f"\n\n{context.user_context}"
            if context.memory_context:
                user_context += f"\n\n{context.memory_context}"
        else:
            # Fallback to minimal router context
            user_context = build_router_context(self.user)

        # Combine classification prompt with user context
        system_message = f"{ROUTER_CLASSIFICATION_PROMPT}\n\n{user_context}"

        # Build messages with conversation history
        messages = [{'role': 'system', 'content': system_message}]

        # Add conversation history (from database)
        # Note: The current user message has already been saved to the database
        # by the orchestrator before routing is called, so it's already in the history.
        # We don't need to add it again manually.
        history_messages = self.conversation.messages.all().order_by('created_at')
        for msg in history_messages:
            if msg.role in ['user', 'assistant']:
                messages.append({
                    'role': msg.role,
                    'content': msg.content
                })

        try:
            llm = LLMBase()
            # Use conversation's model for quality responses
            response = llm.get_completion(
                messages=messages,
                tool_name=self.conversation.model_name
            )

            result_text = response.choices[0].message.content

            # Extract token usage
            input_tokens = 0
            output_tokens = 0
            if hasattr(response, 'usage') and response.usage:
                input_tokens = getattr(response.usage, 'prompt_tokens', 0) or 0
                output_tokens = getattr(response.usage, 'completion_tokens', 0) or 0

            # Parse the response
            parsed = parse_router_response(result_text)

            classification = parsed['classification']

            # Handle response that might be a dict (convert to string)
            direct_response = parsed.get('response', '')
            if isinstance(direct_response, dict):
                import json
                direct_response = json.dumps(direct_response, indent=2)

            if classification == 'DIRECT':
                return RouterResult(
                    route_type=RouteType.DIRECT,
                    confidence=0.85,
                    reason="LLM classified as DIRECT",
                    direct_response=direct_response,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens
                )
            elif classification == 'CLARIFY':
                return RouterResult(
                    route_type=RouteType.CLARIFY,
                    confidence=0.85,
                    reason=f"LLM: needs clarification",
                    clarification_question=parsed.get('question', 'Could you please provide more details?'),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens
                )
            else:  # AGENTIC
                return RouterResult(
                    route_type=RouteType.AGENTIC,
                    confidence=0.85,
                    reason=f"LLM: {parsed.get('reason', 'needs tools')}",
                    detected_entities=self._extract_entities(message),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens
                )

        except Exception as e:
            # On LLM failure, default to AGENTIC (safer - will try to help)
            return RouterResult(
                route_type=RouteType.AGENTIC,
                confidence=0.5,
                reason=f"LLM classification failed, defaulting to AGENTIC: {str(e)}"
            )


def classify_message(user, conversation, memory_state: MemoryState, message: str) -> RouterResult:
    """
    Convenience function to classify a message.

    Usage:
        result = classify_message(user, conversation, memory_state, "Create a task")
        if result.route_type == RouteType.AGENTIC:
            # Create plan and execute
    """
    router = Router(user, conversation, memory_state)
    return router.classify(message)
