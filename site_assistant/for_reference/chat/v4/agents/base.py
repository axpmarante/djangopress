"""
Base Agent Class for Chat V4

Provides the abstract base class and common functionality
for all specialized agents in the V4 multi-agent system.

Architecture:
- Agents receive GOALS, not actions
- Agents use LLM to interpret goals and decide actions
- Agents handle errors and can signal need for replan/user input
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Dict, List, Callable
import logging
import json

from ..state import StepResult
from ..llm import LLMClient, LLMResponse
from ..errors import AgentError, ExecutionError, ErrorCategory

logger = logging.getLogger(__name__)


@dataclass
class AgentContext:
    """
    Context passed to specialized agents for step execution.

    Contains goal and context for the agent to interpret and execute.
    """

    user_id: str
    step_id: int
    goal: str  # Natural language goal for the agent to accomplish
    working_memory: Dict[str, Any]  # Results from previous steps
    model_name: str = "gemini-2.0-flash"  # Model for LLM calls
    retry_context: Optional[str] = None  # Context from previous failed attempt
    retry_count: int = 0

    def get_from_memory(self, key: str, default: Any = None) -> Any:
        """Get a value from working memory"""
        return self.working_memory.get(key, default)

    def set_in_memory(self, key: str, value: Any) -> None:
        """Set a value in working memory for subsequent steps"""
        self.working_memory[key] = value

    def get_step_result(self, step_id: int) -> Optional[Dict]:
        """Get result from a previous step"""
        return self.working_memory.get(f"step_{step_id}_result")


@dataclass
class ActionDecision:
    """
    Decision made by agent about what action to take.

    Returned by _decide_action() after LLM interprets the goal.
    """
    action: str
    params: Dict[str, Any]
    reasoning: str = ""


class BaseAgent(ABC):
    """
    Abstract base class for all specialized agents.

    Each agent:
    - Has a specific domain (tasks, notes, projects, etc.)
    - Receives a GOAL and uses LLM to decide what action to take
    - Executes the action using domain-specific handlers
    - Can signal need for replan or user input
    """

    # Override in subclasses
    AGENT_TYPE: str = ""
    AVAILABLE_ACTIONS: List[str] = []

    # Base prompt for action decision
    DECISION_PROMPT = """You are a specialized {agent_type} agent in a multi-agent system for ZemoNotes.

Your task: Analyze the goal and decide what action to take.

## Your Available Actions
{actions_description}

## Working Memory (results from previous steps)
{working_memory}

## Goal to Accomplish
{goal}

{retry_context}

## Instructions
1. Analyze the goal carefully
2. Choose the most appropriate action from your available actions
3. Determine the parameters needed for that action
4. If you need information from previous steps, use data from working memory

## Output Format
Output ONLY valid JSON (no markdown, no explanation):
{{
    "action": "action_name",
    "params": {{}},
    "reasoning": "brief explanation of why this action"
}}

If you cannot accomplish the goal with your available actions, output:
{{
    "action": "cannot_handle",
    "params": {{}},
    "reasoning": "explanation of why you cannot handle this"
}}
"""

    def __init__(self):
        """Initialize the agent"""
        pass

    def _get_llm(self, context: AgentContext) -> LLMClient:
        """Get LLM client using the model from context"""
        return LLMClient(model_name=context.model_name)

    @abstractmethod
    def get_actions_description(self) -> str:
        """
        Return description of available actions for this agent.

        Override in subclasses to define what actions are available
        and what parameters they accept.
        """
        pass

    def execute(self, context: AgentContext) -> StepResult:
        """
        Execute a goal by deciding action and running it.

        This is the main entry point called by the engine.

        Args:
            context: AgentContext with goal and working memory

        Returns:
            StepResult with execution outcome
        """
        try:
            # Step 1: Use LLM to decide what action to take
            decision = self._decide_action(context)

            if decision.action == "cannot_handle":
                return self._replan_result(
                    context,
                    reason=decision.reasoning,
                    suggestion="This goal may need a different agent or approach"
                )

            # Step 2: Validate the action
            if not self.validate_action(decision.action):
                return self._error_result(
                    context,
                    action=decision.action,
                    error=f"Invalid action '{decision.action}'. Available: {self.AVAILABLE_ACTIONS}"
                )

            # Step 3: Execute the action
            result = self._execute_action(context, decision)

            return result

        except Exception as e:
            logger.error(f"Agent {self.AGENT_TYPE} execution error: {e}")
            return self._error_result(
                context,
                action="unknown",
                error=str(e)
            )

    def _decide_action(self, context: AgentContext) -> ActionDecision:
        """
        Use LLM to interpret goal and decide what action to take.

        Args:
            context: Agent context with goal

        Returns:
            ActionDecision with action, params, and reasoning
        """
        # Build the decision prompt
        retry_section = ""
        if context.retry_context:
            retry_section = f"""
## Previous Attempt Failed
{context.retry_context}
Attempt: {context.retry_count + 1}
Please try a different approach or adjust parameters.
"""

        # Format working memory for display
        memory_str = self._format_working_memory(context.working_memory)

        prompt = self.DECISION_PROMPT.format(
            agent_type=self.AGENT_TYPE,
            actions_description=self.get_actions_description(),
            working_memory=memory_str,
            goal=context.goal,
            retry_context=retry_section
        )

        try:
            llm = self._get_llm(context)
            response = llm.chat_json([
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Goal: {context.goal}"}
            ])

            return ActionDecision(
                action=response.get('action', 'unknown'),
                params=response.get('params', {}),
                reasoning=response.get('reasoning', '')
            )

        except Exception as e:
            logger.error(f"Agent {self.AGENT_TYPE} decision error: {e}")
            # Return a fallback decision
            return ActionDecision(
                action="cannot_handle",
                params={},
                reasoning=f"Error during decision: {str(e)}"
            )

    def _format_working_memory(self, memory: Dict[str, Any]) -> str:
        """Format working memory for prompt inclusion"""
        if not memory:
            return "No previous step results available."

        parts = []
        for key, value in memory.items():
            if key.startswith("step_") and key.endswith("_result"):
                step_num = key.split("_")[1]
                parts.append(f"Step {step_num} result: {json.dumps(value, default=str)[:500]}")
            else:
                parts.append(f"{key}: {json.dumps(value, default=str)[:200]}")

        return "\n".join(parts) if parts else "No previous step results available."

    @abstractmethod
    def _execute_action(self, context: AgentContext, decision: ActionDecision) -> StepResult:
        """
        Execute the decided action.

        Override in subclasses to implement action handlers.

        Args:
            context: Agent context
            decision: The action decision from LLM

        Returns:
            StepResult from executing the action
        """
        pass

    def validate_action(self, action: str) -> bool:
        """Check if action is valid for this agent"""
        return action in self.AVAILABLE_ACTIONS

    # =========================================================================
    # Result Helpers
    # =========================================================================

    def _success_result(
        self,
        context: AgentContext,
        action: str,
        output: Dict[str, Any],
        summary: str,
        entities: Dict[str, List[int]] = None,
        tokens_used: int = 0
    ) -> StepResult:
        """Create a successful step result."""
        return StepResult(
            step_id=context.step_id,
            agent_type=self.AGENT_TYPE,
            action=action,
            success=True,
            output=output,
            summary=summary,
            entities_affected=entities or {},
            tokens_used=tokens_used
        )

    def _error_result(
        self,
        context: AgentContext,
        action: str,
        error: str,
        tokens_used: int = 0
    ) -> StepResult:
        """Create an error step result."""
        return StepResult(
            step_id=context.step_id,
            agent_type=self.AGENT_TYPE,
            action=action,
            success=False,
            output={},
            summary="",
            error=error,
            tokens_used=tokens_used
        )

    def _replan_result(
        self,
        context: AgentContext,
        reason: str,
        suggestion: str = "",
        attempted_action: str = "",
        context_data: Dict[str, Any] = None
    ) -> StepResult:
        """
        Create a result that signals need for replanning.

        Use when the agent cannot complete the goal and the plan
        needs to be revised.
        """
        return StepResult(
            step_id=context.step_id,
            agent_type=self.AGENT_TYPE,
            action=attempted_action or "replan_requested",
            success=False,
            output={},
            summary="",
            error=reason,
            need_replan=True,
            replan_context={
                "reason": reason,
                "suggestion": suggestion,
                "goal": context.goal,
                "data": context_data or {}
            }
        )

    def _user_input_result(
        self,
        context: AgentContext,
        question: str,
        options: List[str] = None,
        action: str = ""
    ) -> StepResult:
        """
        Create a result that signals need for user input.

        Use when the agent needs clarification from the user
        to proceed with the goal.
        """
        return StepResult(
            step_id=context.step_id,
            agent_type=self.AGENT_TYPE,
            action=action or "user_input_requested",
            success=False,
            output={},
            summary="",
            need_user_input=True,
            user_question=question,
            user_options=options
        )

    def _not_found_result(
        self,
        context: AgentContext,
        action: str,
        resource_type: str,
        identifier: Any,
        suggest_create: bool = False
    ) -> StepResult:
        """
        Create a not-found error result.

        Can optionally suggest replanning to create the resource.
        """
        error_msg = f"{resource_type.title()} not found: {identifier}"

        if suggest_create:
            return self._replan_result(
                context,
                reason=error_msg,
                suggestion=f"May need to create the {resource_type} first",
                attempted_action=action
            )

        return self._error_result(context, action, error_msg)


class DatabaseAgentMixin:
    """
    Mixin for agents that interact with the database.

    Provides common database operations with error handling.
    """

    def _get_user_queryset(self, model_class, user_id: str):
        """Get queryset filtered by user"""
        return model_class.objects.filter(user_id=user_id)

    def _get_object_or_none(self, model_class, user_id: str, pk: int):
        """Get object by PK or return None"""
        try:
            return model_class.objects.get(user_id=user_id, pk=pk)
        except model_class.DoesNotExist:
            return None

    def _search_by_name(self, model_class, user_id: str, name: str, name_field: str = 'name'):
        """
        Search for objects by name (case-insensitive contains).

        Returns list of matches.
        """
        from django.db.models import Q
        filter_kwargs = {f'{name_field}__icontains': name}
        return list(
            model_class.objects.filter(user_id=user_id, **filter_kwargs)[:10]
        )

    def _apply_filters(self, queryset, filters: Dict[str, Any]):
        """Apply filters to queryset."""
        for key, value in filters.items():
            if value is None:
                continue

            if key.endswith('__in') or key.endswith('__contains'):
                queryset = queryset.filter(**{key: value})
            elif key.endswith('__isnull'):
                queryset = queryset.filter(**{key: value})
            elif isinstance(value, list):
                queryset = queryset.filter(**{f"{key}__in": value})
            else:
                queryset = queryset.filter(**{key: value})

        return queryset

    def _serialize_object(self, obj, fields: List[str]) -> Dict[str, Any]:
        """Serialize model object to dict."""
        result = {}
        for field_name in fields:
            value = getattr(obj, field_name, None)
            if hasattr(value, 'isoformat'):
                value = value.isoformat()
            elif hasattr(value, 'pk'):
                value = value.pk
            result[field_name] = value
        return result


class ActionDispatcherMixin:
    """
    Mixin for dispatching actions to handler methods.

    Agents can use this to route actions to specific methods
    based on action name.
    """

    def _get_action_handler(self, action: str) -> Optional[Callable]:
        """
        Get handler method for an action.

        Looks for method named _handle_{action}.
        """
        handler_name = f"_handle_{action}"
        return getattr(self, handler_name, None)

    def _dispatch_action(
        self,
        context: AgentContext,
        decision: ActionDecision
    ) -> StepResult:
        """
        Dispatch action to appropriate handler.

        Args:
            context: Agent context
            decision: Action decision with action name and params

        Returns:
            StepResult from handler
        """
        handler = self._get_action_handler(decision.action)
        if handler is None:
            return self._error_result(
                context,
                action=decision.action,
                error=f"No handler for action: {decision.action}"
            )

        try:
            return handler(context, decision.params)
        except Exception as e:
            logger.error(
                f"Action {decision.action} failed in {self.AGENT_TYPE}: {e}"
            )
            return self._error_result(context, decision.action, str(e))
