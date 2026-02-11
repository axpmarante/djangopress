"""
Chat V2 Models

Database models for the V2 chat architecture.
Handles persistent state management for LLM conversations.
"""

from django.db import models
from django.conf import settings
from django.utils import timezone

from Core.models import BaseModel


class AgentMemory(BaseModel):
    """
    Persistent memory for LLM state management.

    Solves the statelessness problem - each LLM call gets full context
    reconstructed from this memory plus conversation history.

    Key fields:
    - task_goal: What the user wants to achieve
    - route_type: DIRECT, AGENTIC, or CLARIFY
    - current_stage/total_stages: Progress through plan
    - plan_state: Flexible JSON for plan steps and intermediate data
    - stage_results: Results from each completed stage
    - failed_approaches: What didn't work (avoid repeating)
    - key_learnings: Insights discovered during execution
    - pending_clarification: Question waiting for user response
    """

    conversation = models.OneToOneField(
        'chat.Conversation',
        on_delete=models.CASCADE,
        related_name='agent_memory'
    )

    # Current task tracking
    task_goal = models.TextField(
        blank=True,
        help_text="What the user wants to achieve"
    )
    route_type = models.CharField(
        max_length=20,
        blank=True,
        help_text="DIRECT, AGENTIC, or CLARIFY"
    )

    # Plan progress (for AGENTIC flows)
    current_stage = models.PositiveIntegerField(
        default=0,
        help_text="Current step being executed (1-indexed)"
    )
    total_stages = models.PositiveIntegerField(
        default=0,
        help_text="Total steps in the plan"
    )

    # Flexible state storage
    plan_state = models.JSONField(
        default=dict,
        blank=True,
        help_text="Plan steps, tool params, intermediate data"
    )
    stage_results = models.JSONField(
        default=dict,
        blank=True,
        help_text="Results from each completed stage (keyed by stage number)"
    )

    # Learning from experience
    failed_approaches = models.JSONField(
        default=list,
        blank=True,
        help_text="Approaches that didn't work - avoid repeating"
    )
    key_learnings = models.JSONField(
        default=list,
        blank=True,
        help_text="Insights discovered during execution"
    )

    # Clarification state (for CLARIFY flows)
    pending_clarification = models.JSONField(
        default=dict,
        blank=True,
        help_text="Question asked, options provided, context for clarification"
    )

    class Meta:
        db_table = 'chat_agent_memory'
        verbose_name = 'Agent Memory'
        verbose_name_plural = 'Agent Memories'

    def __str__(self):
        if self.total_stages > 0:
            status = f"Step {self.current_stage}/{self.total_stages}"
        elif self.task_goal:
            status = f"Goal: {self.task_goal[:30]}..."
        else:
            status = "No active task"
        return f"Memory for Conv #{self.conversation_id}: {status}"

    def is_plan_active(self) -> bool:
        """Check if there's an active plan in progress."""
        return self.total_stages > 0 and self.current_stage <= self.total_stages

    def is_plan_complete(self) -> bool:
        """Check if plan has finished all stages."""
        return self.total_stages > 0 and self.current_stage > self.total_stages

    def is_awaiting_clarification(self) -> bool:
        """Check if waiting for user clarification."""
        return bool(self.pending_clarification)

    def get_current_step(self) -> dict | None:
        """Get the current step definition from plan_state."""
        steps = self.plan_state.get('steps', [])
        if 0 < self.current_stage <= len(steps):
            return steps[self.current_stage - 1]  # 1-indexed
        return None

    def clear_task(self):
        """Reset task state after completion or cancellation."""
        self.task_goal = ""
        self.route_type = ""
        self.current_stage = 0
        self.total_stages = 0
        self.plan_state = {}
        self.stage_results = {}
        self.pending_clarification = {}
        self.save()

    def clear_all(self):
        """Reset everything including learnings (new conversation context)."""
        self.clear_task()
        self.failed_approaches = []
        self.key_learnings = []
        self.save()


class PlanStep(BaseModel):
    """
    Individual step in an AGENTIC execution plan.

    Separated from AgentMemory for:
    - Better querying and filtering
    - Audit trail of executed steps
    - Easier status tracking per step

    Each step specifies:
    - Which tool to use (search_tool or execute_tool)
    - Which action (search, create, update, etc.)
    - Parameters for the action
    - Status and results
    """

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped'),
    ]

    memory = models.ForeignKey(
        AgentMemory,
        on_delete=models.CASCADE,
        related_name='steps'
    )

    # Step definition
    order = models.PositiveIntegerField(
        help_text="Step order (1-indexed)"
    )
    description = models.TextField(
        help_text="Human-readable step description"
    )

    # Tool configuration
    tool = models.CharField(
        max_length=50,
        help_text="Tool name: search_tool or execute_tool"
    )
    action = models.CharField(
        max_length=50,
        help_text="Action: search, list, read, create, update, delete, etc."
    )
    resource_type = models.CharField(
        max_length=50,
        blank=True,
        help_text="Resource type: note, task, project, area, tag"
    )
    params = models.JSONField(
        default=dict,
        blank=True,
        help_text="Parameters for the tool action"
    )

    # Execution state
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    result = models.JSONField(
        null=True,
        blank=True,
        help_text="Result data from successful execution"
    )
    error = models.TextField(
        blank=True,
        help_text="Error message if execution failed"
    )

    # Timing
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When execution started"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When execution completed (success or failure)"
    )

    # Retry tracking
    retry_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of retry attempts"
    )
    max_retries = models.PositiveIntegerField(
        default=2,
        help_text="Maximum retry attempts allowed"
    )

    class Meta:
        db_table = 'chat_plan_steps'
        ordering = ['memory', 'order']
        unique_together = [['memory', 'order']]
        verbose_name = 'Plan Step'
        verbose_name_plural = 'Plan Steps'

    def __str__(self):
        return f"Step {self.order}: {self.tool}.{self.action} ({self.status})"

    def start(self):
        """Mark step as in progress."""
        self.status = 'in_progress'
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at', 'updated_at'])

    def complete(self, result: dict = None):
        """Mark step as completed with result."""
        self.status = 'completed'
        self.result = result
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'result', 'completed_at', 'updated_at'])

    def fail(self, error: str):
        """Mark step as failed with error message."""
        self.status = 'failed'
        self.error = error
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'error', 'completed_at', 'updated_at'])

    def skip(self, reason: str = ""):
        """Mark step as skipped."""
        self.status = 'skipped'
        self.error = reason
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'error', 'completed_at', 'updated_at'])

    def can_retry(self) -> bool:
        """Check if step can be retried."""
        return self.status == 'failed' and self.retry_count < self.max_retries

    def retry(self):
        """Reset step for retry."""
        if not self.can_retry():
            raise ValueError(f"Step cannot be retried (attempts: {self.retry_count}/{self.max_retries})")
        self.status = 'pending'
        self.retry_count += 1
        self.error = ""
        self.result = None
        self.started_at = None
        self.completed_at = None
        self.save()

    @property
    def duration_ms(self) -> int | None:
        """Get execution duration in milliseconds."""
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            return int(delta.total_seconds() * 1000)
        return None
