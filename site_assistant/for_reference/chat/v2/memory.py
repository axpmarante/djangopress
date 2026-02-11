"""
Chat V2 Memory State

Runtime state management for LLM conversations.
Bridges database storage (AgentMemory) and LLM context injection.

Key concepts:
- LLMs are stateless - each call needs full context
- MemoryState loads from DB, mutates in memory, saves back
- to_context_string() generates text for LLM system prompt
- _is_dirty tracks if changes need to be saved
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, TYPE_CHECKING
from datetime import datetime
from enum import Enum

if TYPE_CHECKING:
    from .models import AgentMemory


class RouteType(str, Enum):
    """
    Classification types for the Router (Layer 0).

    DIRECT: LLM can answer immediately with current context
    AGENTIC: LLM needs to create a plan and use tools
    CLARIFY: Request is ambiguous, need user clarification
    """
    DIRECT = "DIRECT"
    AGENTIC = "AGENTIC"
    CLARIFY = "CLARIFY"


@dataclass
class MemoryState:
    """
    Runtime state that gets injected into LLM context.

    This dataclass bridges:
    - Database storage (AgentMemory model)
    - LLM prompts (to_context_string method)

    Usage:
        # Load from DB
        db_memory = conversation.agent_memory
        state = MemoryState.from_db(db_memory)

        # Use in LLM context
        context = state.to_context_string()

        # Mutate during execution
        state.start_task("Create task in Finance project", RouteType.AGENTIC, steps)
        state.advance_stage("Found project", {"id": 5, "name": "Finance"})

        # Save back to DB
        if state._is_dirty:
            state.save_to_db(db_memory)
    """

    # Task tracking
    task_goal: str = ""
    route_type: str = ""  # DIRECT, AGENTIC, CLARIFY

    # Progress (for AGENTIC flows)
    current_stage: int = 0
    total_stages: int = 0

    # Flexible state storage
    plan_state: Dict[str, Any] = field(default_factory=dict)
    stage_results: Dict[str, Any] = field(default_factory=dict)

    # Learning from experience
    failed_approaches: List[str] = field(default_factory=list)
    key_learnings: List[str] = field(default_factory=list)

    # Clarification state
    pending_clarification: Dict[str, Any] = field(default_factory=dict)

    # Dirty flag for persistence
    _is_dirty: bool = field(default=False, repr=False)

    # =========================================================================
    # Serialization
    # =========================================================================

    @classmethod
    def from_db(cls, memory: 'AgentMemory') -> 'MemoryState':
        """Load state from database model."""
        return cls(
            task_goal=memory.task_goal or "",
            route_type=memory.route_type or "",
            current_stage=memory.current_stage,
            total_stages=memory.total_stages,
            plan_state=memory.plan_state or {},
            stage_results=memory.stage_results or {},
            failed_approaches=list(memory.failed_approaches or []),
            key_learnings=list(memory.key_learnings or []),
            pending_clarification=memory.pending_clarification or {},
            _is_dirty=False,
        )

    def save_to_db(self, memory: 'AgentMemory') -> None:
        """Persist state to database model."""
        memory.task_goal = self.task_goal
        memory.route_type = self.route_type
        memory.current_stage = self.current_stage
        memory.total_stages = self.total_stages
        memory.plan_state = self.plan_state
        memory.stage_results = self.stage_results
        memory.failed_approaches = self.failed_approaches
        memory.key_learnings = self.key_learnings
        memory.pending_clarification = self.pending_clarification
        memory.save()
        self._is_dirty = False

    # =========================================================================
    # Context Generation
    # =========================================================================

    def to_context_string(self) -> str:
        """
        Generate context string for LLM injection.

        This is injected into the system prompt to give the LLM
        awareness of the current task state, progress, and learnings.
        """
        if not self.task_goal and not self.pending_clarification and not self.key_learnings:
            return ""

        lines = []

        # Active task
        if self.task_goal:
            lines.append("## Current Task")
            lines.append(f"**Goal:** {self.task_goal}")
            lines.append(f"**Route:** {self.route_type}")

            if self.total_stages > 0:
                progress_pct = int((self.current_stage - 1) / self.total_stages * 100) if self.current_stage > 0 else 0
                lines.append(f"**Progress:** Step {self.current_stage} of {self.total_stages} ({progress_pct}%)")

                # Show plan steps with status
                steps = self.plan_state.get('steps', [])
                if steps:
                    lines.append("\n### Plan")
                    for i, step in enumerate(steps, 1):
                        if i < self.current_stage:
                            status = "completed"
                            icon = "[x]"
                        elif i == self.current_stage:
                            status = "current"
                            icon = "[>]"
                        else:
                            status = "pending"
                            icon = "[ ]"

                        desc = step.get('description', f"{step.get('tool', '?')}.{step.get('action', '?')}")
                        lines.append(f"  {icon} {i}. {desc}")

            lines.append("")

        # Completed stage results
        if self.stage_results:
            lines.append("## Completed Steps")
            for stage_num, result in sorted(self.stage_results.items(), key=lambda x: int(x[0])):
                summary = result.get('summary', str(result))
                # Truncate long summaries
                if len(summary) > 200:
                    summary = summary[:200] + "..."
                lines.append(f"  **Step {stage_num}:** {summary}")
            lines.append("")

        # Key learnings (always show if present)
        if self.key_learnings:
            lines.append("## Key Learnings")
            for learning in self.key_learnings[-5:]:  # Last 5
                lines.append(f"  - {learning}")
            lines.append("")

        # Failed approaches (always show if present)
        if self.failed_approaches:
            lines.append("## Avoid (Previously Failed)")
            for approach in self.failed_approaches[-5:]:  # Last 5
                lines.append(f"  - {approach}")
            lines.append("")

        # Pending clarification
        if self.pending_clarification:
            lines.append("## Awaiting Clarification")
            question = self.pending_clarification.get('question', '')
            lines.append(f"**Question asked:** {question}")

            options = self.pending_clarification.get('options', [])
            if options:
                lines.append("**Options presented:**")
                for opt in options:
                    lines.append(f"  - {opt}")

            context = self.pending_clarification.get('context', {})
            if context:
                lines.append(f"**Context:** {context}")
            lines.append("")

        return "\n".join(lines)

    # =========================================================================
    # State Queries
    # =========================================================================

    def is_plan_active(self) -> bool:
        """Check if there's an active plan in progress."""
        return self.total_stages > 0 and self.current_stage <= self.total_stages

    def is_plan_complete(self) -> bool:
        """Check if plan finished all stages."""
        return self.total_stages > 0 and self.current_stage > self.total_stages

    def is_awaiting_clarification(self) -> bool:
        """Check if waiting for user clarification."""
        return bool(self.pending_clarification)

    def has_active_task(self) -> bool:
        """Check if there's any active task (plan or clarification)."""
        return bool(self.task_goal) or self.is_awaiting_clarification()

    def get_current_step(self) -> Optional[Dict]:
        """Get the current step definition from plan_state."""
        steps = self.plan_state.get('steps', [])
        if 0 < self.current_stage <= len(steps):
            return steps[self.current_stage - 1]  # 1-indexed
        return None

    def get_previous_result(self) -> Optional[Dict]:
        """Get the result from the previous stage."""
        prev_stage = str(self.current_stage - 1)
        return self.stage_results.get(prev_stage)

    # =========================================================================
    # State Mutations
    # =========================================================================

    def start_task(
        self,
        goal: str,
        route_type: RouteType | str,
        steps: List[Dict] = None
    ) -> None:
        """
        Initialize a new task.

        Args:
            goal: What the user wants to achieve
            route_type: DIRECT, AGENTIC, or CLARIFY
            steps: List of step definitions for AGENTIC tasks
        """
        self.task_goal = goal
        self.route_type = route_type.value if isinstance(route_type, RouteType) else route_type
        self.current_stage = 1 if steps else 0
        self.total_stages = len(steps) if steps else 0
        self.plan_state = {'steps': steps} if steps else {}
        self.stage_results = {}
        self.pending_clarification = {}
        self._is_dirty = True

    def advance_stage(
        self,
        result_summary: str,
        result_data: Any = None
    ) -> None:
        """
        Mark current stage complete and advance to next.

        Args:
            result_summary: Human-readable summary of what was accomplished
            result_data: Structured data from the step execution
        """
        self.stage_results[str(self.current_stage)] = {
            'summary': result_summary,
            'data': result_data,
            'completed_at': datetime.now().isoformat()
        }

        if self.current_stage <= self.total_stages:
            self.current_stage += 1

        self._is_dirty = True

    def complete_task(self, final_summary: str = "") -> None:
        """
        Mark task as fully completed.

        Optionally adds a learning from the completion.
        Clears task state but preserves learnings and failed approaches.
        """
        if final_summary:
            self.add_learning(f"Completed: {final_summary[:100]}")

        self.task_goal = ""
        self.route_type = ""
        self.current_stage = 0
        self.total_stages = 0
        self.plan_state = {}
        self.stage_results = {}
        self.pending_clarification = {}
        self._is_dirty = True

    def cancel_task(self, reason: str = "") -> None:
        """
        Cancel the current task.

        Records the cancellation as a failed approach if reason provided.
        """
        if reason:
            self.add_failed_approach(f"Cancelled: {reason}")

        self.task_goal = ""
        self.route_type = ""
        self.current_stage = 0
        self.total_stages = 0
        self.plan_state = {}
        self.stage_results = {}
        self.pending_clarification = {}
        self._is_dirty = True

    def add_failed_approach(self, approach: str) -> None:
        """
        Record a failed approach to avoid repeating.

        Keeps only the last 10 failed approaches.
        """
        if approach and approach not in self.failed_approaches:
            self.failed_approaches.append(approach)
            self.failed_approaches = self.failed_approaches[-10:]
            self._is_dirty = True

    def add_learning(self, learning: str) -> None:
        """
        Record an insight for future reference.

        Keeps only the last 10 learnings.
        """
        if learning and learning not in self.key_learnings:
            self.key_learnings.append(learning)
            self.key_learnings = self.key_learnings[-10:]
            self._is_dirty = True

    def set_clarification(
        self,
        question: str,
        options: List[str] = None,
        context: Dict = None
    ) -> None:
        """
        Set pending clarification state.

        Args:
            question: The question to ask the user
            options: List of suggested options (optional)
            context: Additional context about the clarification
        """
        self.pending_clarification = {
            'question': question,
            'options': options or [],
            'context': context or {},
            'asked_at': datetime.now().isoformat()
        }
        self._is_dirty = True

    def clear_clarification(self) -> None:
        """Clear clarification after user responds."""
        self.pending_clarification = {}
        self._is_dirty = True

    def clear_all(self) -> None:
        """
        Reset everything including learnings.

        Use this for completely fresh state (e.g., new conversation context).
        """
        self.task_goal = ""
        self.route_type = ""
        self.current_stage = 0
        self.total_stages = 0
        self.plan_state = {}
        self.stage_results = {}
        self.failed_approaches = []
        self.key_learnings = []
        self.pending_clarification = {}
        self._is_dirty = True


def get_or_create_memory_state(conversation) -> tuple['MemoryState', 'AgentMemory']:
    """
    Helper to get or create memory state for a conversation.

    Returns:
        Tuple of (MemoryState, AgentMemory db object)
    """
    from .models import AgentMemory

    memory, created = AgentMemory.objects.get_or_create(
        conversation=conversation,
        defaults={
            'task_goal': '',
            'route_type': '',
            'current_stage': 0,
            'total_stages': 0,
        }
    )

    state = MemoryState.from_db(memory)
    return state, memory
