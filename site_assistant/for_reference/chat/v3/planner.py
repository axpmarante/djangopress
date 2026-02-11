"""
Chat V3 Planner

Manages plan creation, persistence, and adaptation.

Responsibilities:
- Detect when tasks need plans
- Create plans from LLM-generated data
- Persist plans to database
- Manage plan lifecycle
- Adapt plans during execution
"""

import logging
from typing import Optional, List, Dict, Any

from django.utils import timezone

from .models import V3Plan, V3PlanStep, V3Memory
from .types import Plan, PlanStep, AgentResponse
from .config import PlanStatus, StepStatus, config

logger = logging.getLogger(__name__)


class Planner:
    """
    Manages plan creation and lifecycle.

    The Planner:
    1. Creates plans from LLM responses
    2. Persists plans to database
    3. Tracks plan progress
    4. Adapts plans when needed
    """

    # Patterns that suggest a task needs a plan
    PLAN_INDICATORS = [
        'all', 'every', 'each',           # Batch operations
        'move', 'organize', 'reorganize',  # Multi-step organization
        'review', 'summarize',             # Analysis tasks
        'find and', 'search and',          # Discover then act
        'multiple', 'several',             # Multiple items
    ]

    # Actions that typically don't need plans
    SIMPLE_ACTIONS = [
        'create a task',
        'create a note',
        'what\'s in',
        'show me',
        'how many',
        'list',
    ]

    def __init__(self, conversation):
        """
        Initialize the planner.

        Args:
            conversation: Django Conversation model instance
        """
        self.conversation = conversation
        self.user = conversation.user

    # =========================================================================
    # Plan Detection
    # =========================================================================

    def should_plan(self, user_message: str) -> bool:
        """
        Determine if a message likely needs a plan.

        This is a heuristic - the LLM makes the final decision.
        We use this to hint the LLM toward planning.

        Args:
            user_message: The user's request

        Returns:
            True if the message likely needs a plan
        """
        message_lower = user_message.lower()

        # Check for simple actions (no plan needed)
        for simple in self.SIMPLE_ACTIONS:
            if simple in message_lower:
                return False

        # Check for plan indicators
        for indicator in self.PLAN_INDICATORS:
            if indicator in message_lower:
                return True

        # Check message length - longer requests often need plans
        if len(user_message.split()) > 15:
            return True

        return False

    def get_planning_hint(self, user_message: str) -> str:
        """
        Get a hint to include in the prompt for complex tasks.

        Args:
            user_message: The user's request

        Returns:
            Planning hint string (empty if no plan needed)
        """
        if not self.should_plan(user_message):
            return ""

        return """
**This task may require multiple steps.** Consider creating a plan with:
- Clear steps to achieve the goal
- Search steps before action steps
- One action per step

Include a `plan` in your response if you determine this needs multiple steps.
"""

    # =========================================================================
    # Plan Creation
    # =========================================================================

    def create_plan_from_response(
        self,
        response: AgentResponse,
        original_request: str
    ) -> Optional[V3Plan]:
        """
        Create a persistent plan from an LLM response.

        Args:
            response: Parsed agent response containing plan data
            original_request: The original user message

        Returns:
            Created V3Plan instance, or None if no plan in response
        """
        if not response.plan:
            return None

        plan_data = response.plan

        # Create the plan
        db_plan = V3Plan.objects.create(
            conversation=self.conversation,
            goal=plan_data.goal,
            original_request=original_request,
            status='pending',
        )

        # Create steps
        for i, step in enumerate(plan_data.steps):
            V3PlanStep.objects.create(
                plan=db_plan,
                order=i,
                description=step.description,
                action_type=step.action_type,
                expected_tool=self._infer_tool(step.action_type),
            )

        logger.info(f"Created plan {db_plan.id}: {db_plan.goal} ({len(plan_data.steps)} steps)")

        # Update memory to reference this plan
        memory = self._get_or_create_memory()
        memory.active_plan = db_plan
        memory.current_goal = plan_data.goal
        memory.save(update_fields=['active_plan', 'current_goal', 'updated_at'])

        return db_plan

    def create_plan(
        self,
        goal: str,
        steps: List[Dict[str, Any]],
        original_request: str = ""
    ) -> V3Plan:
        """
        Create a plan directly (not from LLM response).

        Args:
            goal: What the plan aims to achieve
            steps: List of step definitions
            original_request: The original user message

        Returns:
            Created V3Plan instance
        """
        db_plan = V3Plan.objects.create(
            conversation=self.conversation,
            goal=goal,
            original_request=original_request,
            status='pending',
        )

        for i, step_def in enumerate(steps):
            V3PlanStep.objects.create(
                plan=db_plan,
                order=i,
                description=step_def.get('description', f'Step {i + 1}'),
                action_type=step_def.get('action_type', 'other'),
                expected_tool=step_def.get('tool', self._infer_tool(step_def.get('action_type', ''))),
                expected_params=step_def.get('params', {}),
            )

        logger.info(f"Created plan {db_plan.id}: {goal} ({len(steps)} steps)")
        return db_plan

    def _infer_tool(self, action_type: str) -> str:
        """Infer the expected tool from action type."""
        search_actions = ['search', 'find', 'list', 'get', 'read']
        if action_type.lower() in search_actions:
            return 'search'
        return 'execute'

    # =========================================================================
    # Plan Lifecycle
    # =========================================================================

    def get_active_plan(self) -> Optional[V3Plan]:
        """Get the currently active plan for this conversation."""
        return V3Plan.objects.filter(
            conversation=self.conversation,
            status__in=['pending', 'in_progress', 'adapted']
        ).order_by('-created_at').first()

    def start_plan(self, plan: V3Plan):
        """Mark a plan as started."""
        plan.start()

        # Start the first step
        first_step = plan.steps.filter(status='pending').order_by('order').first()
        if first_step:
            first_step.start()

        logger.info(f"Started plan {plan.id}")

    def complete_step(
        self,
        plan: V3Plan,
        step_index: int,
        result_summary: str,
        result_data: dict = None
    ):
        """
        Mark a step as completed and advance the plan.

        Args:
            plan: The plan
            step_index: Index of the completed step
            result_summary: Summary of what was accomplished
            result_data: Full result data
        """
        step = plan.steps.filter(order=step_index).first()
        if not step:
            logger.warning(f"Step {step_index} not found in plan {plan.id}")
            return

        step.complete(result_summary, result_data)

        # Add discovery to plan
        if result_data:
            key = f"step_{step_index}_result"
            plan.add_discovery(key, result_summary)

        # Advance to next step
        next_step = plan.advance_to_next_step()
        if next_step:
            next_step.start()
            logger.info(f"Plan {plan.id}: Completed step {step_index}, starting step {next_step.order}")
        else:
            logger.info(f"Plan {plan.id}: Completed all steps")

    def fail_step(self, plan: V3Plan, step_index: int, error: str):
        """
        Mark a step as failed.

        Args:
            plan: The plan
            step_index: Index of the failed step
            error: Error message
        """
        step = plan.steps.filter(order=step_index).first()
        if step:
            step.fail(error)
            logger.warning(f"Plan {plan.id}: Step {step_index} failed: {error}")

    def skip_step(self, plan: V3Plan, step_index: int, reason: str = ""):
        """
        Skip a step and advance.

        Args:
            plan: The plan
            step_index: Index of the step to skip
            reason: Why the step was skipped
        """
        step = plan.steps.filter(order=step_index).first()
        if step:
            step.skip(reason)
            plan.advance_to_next_step()
            logger.info(f"Plan {plan.id}: Skipped step {step_index}")

    def complete_plan(self, plan: V3Plan):
        """Mark a plan as completed."""
        plan.complete()

        # Clear from memory
        memory = self._get_or_create_memory()
        if memory.active_plan_id == plan.id:
            memory.active_plan = None
            memory.current_goal = ""
            memory.save(update_fields=['active_plan', 'current_goal', 'updated_at'])

        logger.info(f"Completed plan {plan.id}")

    def fail_plan(self, plan: V3Plan, reason: str = ""):
        """Mark a plan as failed."""
        plan.fail(reason)
        logger.error(f"Failed plan {plan.id}: {reason}")

    def cancel_plan(self, plan: V3Plan, reason: str = ""):
        """Cancel a plan."""
        plan.cancel(reason)
        logger.info(f"Cancelled plan {plan.id}: {reason}")

    # =========================================================================
    # Plan Adaptation
    # =========================================================================

    def adapt_plan(
        self,
        plan: V3Plan,
        reason: str,
        new_steps: List[Dict[str, Any]] = None,
        skip_current: bool = False
    ) -> V3Plan:
        """
        Adapt a plan based on execution results.

        Use cases:
        - Found more items than expected → add batching steps
        - Target doesn't exist → add creation step
        - Permission error → skip step

        Args:
            plan: The plan to adapt
            reason: Why the plan is being adapted
            new_steps: Optional new steps to add
            skip_current: Whether to skip the current step

        Returns:
            The adapted plan
        """
        if skip_current:
            current_step = plan.get_current_step()
            if current_step:
                current_step.skip(f"Adapted: {reason}")

        if new_steps:
            plan.add_adaptation(reason, new_steps)
            logger.info(f"Plan {plan.id}: Adapted - {reason}, added {len(new_steps)} steps")
        else:
            plan.add_adaptation(reason)
            logger.info(f"Plan {plan.id}: Adapted - {reason}")

        return plan

    def should_adapt_for_batch(
        self,
        plan: V3Plan,
        item_count: int,
        batch_threshold: int = 5
    ) -> bool:
        """
        Determine if plan should be adapted for batch processing.

        Args:
            plan: The current plan
            item_count: Number of items found
            batch_threshold: Threshold for batching

        Returns:
            True if batching adaptation is recommended
        """
        return item_count > batch_threshold

    def create_batch_steps(
        self,
        action: str,
        items: List[Dict],
        batch_size: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Create steps for batch processing.

        Args:
            action: The action to perform (e.g., 'move', 'complete')
            items: List of items to process
            batch_size: Items per batch step

        Returns:
            List of step definitions
        """
        steps = []
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            item_names = [item.get('title', item.get('name', f'ID:{item.get("id")}'))
                         for item in batch]
            steps.append({
                'description': f"{action.title()} items: {', '.join(item_names[:3])}{'...' if len(item_names) > 3 else ''}",
                'action_type': action,
                'params': {'ids': [item['id'] for item in batch]},
            })

        return steps

    # =========================================================================
    # Context Building
    # =========================================================================

    def get_plan_context(self, plan: Optional[V3Plan] = None) -> str:
        """
        Get plan context for LLM prompt.

        Args:
            plan: Specific plan, or None to get active plan

        Returns:
            Plan context string
        """
        if plan is None:
            plan = self.get_active_plan()

        if plan is None:
            return ""

        return plan.to_context_string()

    # =========================================================================
    # Memory Management
    # =========================================================================

    def _get_or_create_memory(self) -> V3Memory:
        """Get or create memory for this conversation."""
        memory, created = V3Memory.objects.get_or_create(
            conversation=self.conversation
        )
        return memory

    def record_discovery(
        self,
        tool: str,
        query: dict,
        result_summary: str,
        result_data: Any = None
    ):
        """
        Record a discovery in memory.

        Args:
            tool: Tool that was called
            query: Query parameters
            result_summary: Summary of results
            result_data: Full result data
        """
        memory = self._get_or_create_memory()
        memory.add_discovery(tool, query, result_summary, result_data)

    def record_learning(self, learning: str, learning_type: str = 'insight'):
        """
        Record a learning.

        Args:
            learning: What was learned
            learning_type: Type of learning
        """
        memory = self._get_or_create_memory()
        memory.add_learning(learning, learning_type)

    def record_failed_approach(self, approach: str, error: str):
        """
        Record a failed approach.

        Args:
            approach: What was tried
            error: Why it failed
        """
        memory = self._get_or_create_memory()
        memory.add_failed_approach(approach, error)

    def get_memory_context(self) -> str:
        """Get memory context for LLM prompt."""
        memory = self._get_or_create_memory()
        return memory.to_context_string()


# =============================================================================
# Convenience Functions
# =============================================================================

def get_planner(conversation) -> Planner:
    """Get a planner instance for a conversation."""
    return Planner(conversation)


def needs_plan(user_message: str, conversation) -> bool:
    """Quick check if a message likely needs a plan."""
    planner = Planner(conversation)
    return planner.should_plan(user_message)
