"""
Stepper Agent for Chat V4

Decides what happens next based on current execution state.
Uses Haiku model for fast, simple decisions (called frequently).
"""

import logging
from dataclasses import dataclass
from typing import Optional, Literal, Dict, Any, List

from ..state import ExecutionState, Plan, PlanStep, StepResult
from ..llm import LLMClient
from ..errors import ExecutionError, ErrorCategory

logger = logging.getLogger(__name__)


# Decision types
DecisionAction = Literal[
    "execute",      # Execute next step
    "retry",        # Retry failed step with modification
    "replan",       # Request plan revision
    "ask_user",     # Ask user for input
    "complete",     # Mark execution complete
    "fail"          # Mark execution failed
]


@dataclass
class StepDecision:
    """Decision from Stepper agent"""
    action: DecisionAction
    step_id: Optional[int] = None
    retry_modification: Optional[str] = None
    replan_reason: Optional[str] = None
    question: Optional[str] = None
    options: Optional[List[str]] = None
    failure_reason: Optional[str] = None
    confidence: float = 1.0


class StepperAgent:
    """
    Decides what happens next based on current execution state.

    The Stepper:
    - Determines which step to execute next
    - Decides whether to retry failed steps
    - Triggers replanning when needed
    - Asks user for clarification
    - Marks execution complete or failed

    Model: Haiku (simple decision logic, called frequently)
    """

    SYSTEM_PROMPT = """You are a Step Controller for an execution engine.

Your ONLY job: Look at current execution state and decide what happens next.

## Possible Decisions

1. Execute next step (dependencies satisfied, step pending):
   {"action": "execute", "step_id": N}

2. Retry a failed step with modification:
   {"action": "retry", "step_id": N, "retry_modification": "description of what to change"}

3. Request plan revision (current plan won't work):
   {"action": "replan", "replan_reason": "why we need a new plan"}

4. Ask user for input (need clarification or confirmation):
   {"action": "ask_user", "question": "what to ask", "options": ["option1", "option2"]}

5. Mark execution complete (all steps done):
   {"action": "complete"}

6. Mark execution failed (can't continue):
   {"action": "fail", "failure_reason": "why we can't continue"}

## Decision Guidelines

- If last step succeeded and more pending steps exist → execute next
- If last step failed and retries < 3 → retry with modification
- If last step failed and retries >= 3 → replan or fail
- If step found ambiguous data (multiple matches) → ask_user to select
- If step found no data when expected → replan or ask_user
- If destructive action affects many items (>10) → ask_user to confirm
- If all steps completed successfully → complete
- If dependencies cannot be satisfied → replan

## Input Format

You receive the current execution state including:
- The plan with step statuses
- Results from completed/failed steps
- Retry counts
- Working memory contents

Output ONLY the decision JSON, nothing else."""

    MAX_RETRIES = 3
    CONFIRMATION_THRESHOLDS = {
        'delete': 1,       # Confirm deleting any items
        'archive': 5,      # Confirm archiving 5+ items
        'move': 10,        # Confirm moving 10+ items
        'batch_update': 10 # Confirm batch updating 10+ items
    }

    def __init__(self, model_name: str = None):
        """Initialize the Stepper with specified or default model"""
        self.llm = LLMClient(model_name=model_name or "gemini-lite")

    def decide(self, state: ExecutionState) -> StepDecision:
        """
        Decide the next action based on execution state.

        Args:
            state: Current execution state

        Returns:
            StepDecision with next action
        """
        # Try quick decision first (no LLM needed)
        quick_decision = self._try_quick_decision(state)
        if quick_decision:
            logger.debug(f"Quick decision: {quick_decision.action}")
            return quick_decision

        # Need LLM for complex decision
        try:
            context = self._build_context(state)
            response = self.llm.chat_json([
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": context}
            ])
            return self._parse_decision(response)
        except Exception as e:
            logger.error(f"Stepper LLM call failed: {e}")
            # Fallback: try to continue or fail gracefully
            return self._fallback_decision(state)

    def _try_quick_decision(self, state: ExecutionState) -> Optional[StepDecision]:
        """
        Try to make decision without LLM call.

        Handles common cases:
        - No plan → fail
        - All steps completed → complete
        - Next step ready → execute
        - Step needs confirmation → ask_user
        """
        if not state.plan or not state.plan.steps:
            return StepDecision(
                action="fail",
                failure_reason="No execution plan"
            )

        # Check if all steps are done
        all_done = all(
            step.status in ("completed", "skipped")
            for step in state.plan.steps
        )
        if all_done:
            return StepDecision(action="complete")

        # Check for any running step (shouldn't happen, but handle it)
        running = [s for s in state.plan.steps if s.status == "running"]
        if running:
            # Wait for it to complete
            return None

        # Find next executable step
        completed_ids = state.get_completed_step_ids()

        for step in state.plan.steps:
            if step.status == "pending":
                # Check dependencies
                deps_satisfied = all(
                    dep_id in completed_ids
                    for dep_id in step.depends_on
                )
                if deps_satisfied:
                    # Check if this step needs confirmation
                    confirmation = self._check_confirmation_needed(step, state)
                    if confirmation:
                        return confirmation

                    return StepDecision(
                        action="execute",
                        step_id=step.step_id
                    )

            elif step.status == "failed":
                # Check retry count
                retries = state.get_retry_count(step.step_id)
                if retries < self.MAX_RETRIES:
                    # Need LLM to determine modification
                    return None
                else:
                    # Max retries exceeded - need LLM decision
                    return None

        # No obvious next step - need LLM
        return None

    def _check_confirmation_needed(
        self,
        step: PlanStep,
        state: ExecutionState
    ) -> Optional[StepDecision]:
        """
        Check if step needs user confirmation before execution.

        Args:
            step: Step to check
            state: Current execution state

        Returns:
            StepDecision to ask_user if confirmation needed, None otherwise
        """
        action = step.action
        threshold = self.CONFIRMATION_THRESHOLDS.get(action)

        if threshold is None:
            return None

        # Check working memory for item counts from previous searches
        # Look for data that this step will operate on
        affected_count = 0

        for dep_id in step.depends_on:
            result = state.step_results.get(dep_id)
            if result and result.success:
                # Count items in result
                output = result.output
                for key in ['tasks', 'notes', 'items', 'projects', 'areas']:
                    if key in output and isinstance(output[key], list):
                        affected_count = max(affected_count, len(output[key]))

        # Also check working memory
        for key in ['found_tasks', 'found_notes', 'found_items']:
            if key in state.working_memory:
                items = state.working_memory[key]
                if isinstance(items, list):
                    affected_count = max(affected_count, len(items))

        if affected_count >= threshold:
            return StepDecision(
                action="ask_user",
                question=f"This will {action} {affected_count} items. Proceed?",
                options=["Yes, proceed", "No, cancel"]
            )

        return None

    def _build_context(self, state: ExecutionState) -> str:
        """Build context string for Stepper LLM"""
        parts = [
            f"Request: {state.user_request}",
            f"Status: {state.status}",
            f"Current step: {state.current_step}",
            "",
            "Plan steps:"
        ]

        for step in state.plan.steps:
            result = state.step_results.get(step.step_id)
            deps = f" (depends on: {step.depends_on})" if step.depends_on else ""

            if result:
                if result.success:
                    result_str = f" → SUCCESS: {result.summary}"
                else:
                    retries = state.get_retry_count(step.step_id)
                    result_str = f" → FAILED (retries: {retries}): {result.error}"
            else:
                result_str = ""

            parts.append(
                f"  {step.step_id}. [{step.status}] {step.agent_type}.{step.action}{deps}{result_str}"
            )
            if step.description:
                parts.append(f"      Description: {step.description}")

        # Add working memory summary
        if state.working_memory:
            parts.append("")
            parts.append("Working memory:")
            for key, value in list(state.working_memory.items())[:5]:
                if isinstance(value, list):
                    parts.append(f"  {key}: {len(value)} items")
                elif isinstance(value, dict):
                    parts.append(f"  {key}: {list(value.keys())[:3]}")
                else:
                    parts.append(f"  {key}: {str(value)[:50]}")

        # Add recent errors
        if state.errors:
            parts.append("")
            parts.append("Recent errors:")
            for err in state.errors[-3:]:
                parts.append(f"  - {err.get('message', str(err))[:100]}")

        return "\n".join(parts)

    def _parse_decision(self, response: Dict[str, Any]) -> StepDecision:
        """Parse LLM response into StepDecision"""
        action = response.get('action', 'fail')

        if action not in ('execute', 'retry', 'replan', 'ask_user', 'complete', 'fail'):
            logger.warning(f"Unknown action '{action}', defaulting to fail")
            action = 'fail'

        return StepDecision(
            action=action,
            step_id=response.get('step_id'),
            retry_modification=response.get('retry_modification'),
            replan_reason=response.get('replan_reason'),
            question=response.get('question'),
            options=response.get('options'),
            failure_reason=response.get('failure_reason'),
            confidence=response.get('confidence', 1.0)
        )

    def _fallback_decision(self, state: ExecutionState) -> StepDecision:
        """
        Fallback decision when LLM fails.

        Tries to make a safe decision based on state.
        """
        # If we have completed results, try to finish
        if state.step_results and not state.has_failures():
            if state.all_steps_completed():
                return StepDecision(action="complete")

        # If there are pending steps, try the first one
        for step in state.plan.steps:
            if step.status == "pending":
                deps_satisfied = all(
                    dep_id in state.get_completed_step_ids()
                    for dep_id in step.depends_on
                )
                if deps_satisfied:
                    return StepDecision(action="execute", step_id=step.step_id)

        # Can't determine next action
        return StepDecision(
            action="fail",
            failure_reason="Unable to determine next action"
        )


class StepperRules:
    """
    Rule-based helper for common Stepper decisions.

    Provides deterministic logic for predictable scenarios.
    """

    @staticmethod
    def should_retry(
        error: ExecutionError,
        retry_count: int,
        max_retries: int = 3
    ) -> bool:
        """Determine if a step should be retried"""
        if retry_count >= max_retries:
            return False
        return error.retryable

    @staticmethod
    def get_retry_modification(error: ExecutionError) -> str:
        """Get suggested modification for retry"""
        modifications = {
            ErrorCategory.RATE_LIMIT: "Reduce batch size and add delay",
            ErrorCategory.TIMEOUT: "Process fewer items at once",
            ErrorCategory.VALIDATION: "Check and fix parameter format",
            ErrorCategory.PARSE_ERROR: "Request simpler response format",
            ErrorCategory.LLM_ERROR: "Simplify the request",
        }
        return modifications.get(error.category, "Try again with adjusted parameters")

    @staticmethod
    def should_replan(
        error: ExecutionError,
        retry_count: int,
        max_retries: int = 3
    ) -> bool:
        """Determine if replanning is needed"""
        # Replan if max retries exceeded for retryable error
        if error.retryable and retry_count >= max_retries:
            return True

        # Replan for certain error types
        if error.category == ErrorCategory.NOT_FOUND:
            return True

        return False

    @staticmethod
    def needs_user_input(
        step: PlanStep,
        result: StepResult
    ) -> Optional[str]:
        """
        Check if step result requires user input.

        Returns question to ask, or None.
        """
        if not result.success:
            return None

        output = result.output

        # Multiple matches found - need selection
        for key in ['projects', 'areas', 'tasks', 'notes']:
            if key in output and isinstance(output[key], list):
                items = output[key]
                if len(items) > 1 and step.action == "search":
                    # Check if next step needs a specific item
                    names = [
                        item.get('name') or item.get('title', f"Item {item.get('id')}")
                        for item in items[:5]
                    ]
                    return f"Found {len(items)} matches. Which one did you mean?"

        return None
