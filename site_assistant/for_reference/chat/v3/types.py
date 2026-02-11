"""
Chat V3 Types

Core type definitions for the V3 chat system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .config import PlanStatus, StepStatus, RouteType


# =============================================================================
# Tool Types
# =============================================================================

@dataclass
class ToolCall:
    """A tool invocation request."""
    tool: str  # "search" or "execute"
    params: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.tool}({self.params})"


@dataclass
class ToolResult:
    """Result from a tool execution."""
    success: bool
    data: Any = None
    summary: str = ""
    error: Optional[str] = None

    def __str__(self) -> str:
        if self.success:
            return f"Success: {self.summary}"
        return f"Error: {self.error}"


# =============================================================================
# Plan Types
# =============================================================================

@dataclass
class PlanStep:
    """Individual step in an execution plan."""
    index: int
    description: str
    action_type: str  # search, create, update, delete, move, etc.

    # Execution state
    status: StepStatus = StepStatus.PENDING
    result_summary: Optional[str] = None
    result_data: Optional[Dict] = None
    error: Optional[str] = None

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def mark_started(self):
        """Mark step as in progress."""
        self.status = StepStatus.IN_PROGRESS
        self.started_at = datetime.now()

    def mark_completed(self, result_summary: str, result_data: Dict = None):
        """Mark step as completed."""
        self.status = StepStatus.COMPLETED
        self.result_summary = result_summary
        self.result_data = result_data
        self.completed_at = datetime.now()

    def mark_failed(self, error: str):
        """Mark step as failed."""
        self.status = StepStatus.FAILED
        self.error = error
        self.completed_at = datetime.now()


@dataclass
class Plan:
    """Execution plan for a complex task."""
    goal: str
    steps: List[PlanStep] = field(default_factory=list)
    status: PlanStatus = PlanStatus.PENDING

    # Tracking
    current_step: int = 0
    discoveries: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def to_context_string(self) -> str:
        """Format plan for LLM context."""
        lines = [
            "## Current Plan",
            f"**Goal:** {self.goal}",
            f"**Progress:** Step {self.current_step + 1} of {len(self.steps)}",
            "",
            "### Steps"
        ]

        for i, step in enumerate(self.steps):
            if step.status == StepStatus.COMPLETED:
                status_icon = "[x]"
            elif step.status == StepStatus.IN_PROGRESS:
                status_icon = "[>]"
            elif step.status == StepStatus.FAILED:
                status_icon = "[!]"
            elif step.status == StepStatus.SKIPPED:
                status_icon = "[-]"
            else:
                status_icon = "[ ]"

            lines.append(f"{status_icon} {i + 1}. {step.description}")

            # Include result summary for completed steps
            if step.result_summary:
                lines.append(f"    Result: {step.result_summary}")
            elif step.error:
                lines.append(f"    Error: {step.error}")

        return "\n".join(lines)

    def get_current_step(self) -> Optional[PlanStep]:
        """Get the current step being executed."""
        if 0 <= self.current_step < len(self.steps):
            return self.steps[self.current_step]
        return None

    def advance(self):
        """Move to the next step."""
        if self.current_step < len(self.steps) - 1:
            self.current_step += 1
        else:
            self.status = PlanStatus.COMPLETED

    def is_complete(self) -> bool:
        """Check if all steps are done."""
        return all(
            s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED)
            for s in self.steps
        )


# =============================================================================
# Agent Response Types
# =============================================================================

@dataclass
class AgentResponse:
    """
    Parsed response from the LLM.

    Exactly one of tool_call or response will be set.
    """
    thinking: str = ""
    plan: Optional[Plan] = None
    tool_call: Optional[ToolCall] = None
    response: Optional[str] = None
    plan_step: Optional[int] = None  # Which plan step this advances

    def is_final(self) -> bool:
        """True if this is a final response (no more iterations)."""
        return self.response is not None

    def has_tool_call(self) -> bool:
        """True if there's a tool to execute."""
        return self.tool_call is not None

    def has_plan(self) -> bool:
        """True if a plan was created."""
        return self.plan is not None


@dataclass
class Iteration:
    """Record of a single iteration in the agent loop."""
    thinking: str
    tool_call: Optional[ToolCall] = None
    result: Optional[ToolResult] = None
    response: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class AgentResult:
    """Final result from the agent loop."""
    success: bool
    response: str
    iterations: List[Iteration] = field(default_factory=list)
    plan: Optional[Plan] = None
    error: Optional[str] = None

    # Token tracking
    total_input_tokens: int = 0
    total_output_tokens: int = 0


# =============================================================================
# Classification Types
# =============================================================================

@dataclass
class IntakeResult:
    """Result from intake classification."""
    route_type: RouteType
    confidence: float = 1.0
    reason: str = ""


# =============================================================================
# Discovery Types (for Memory)
# =============================================================================

@dataclass
class Discovery:
    """A discovery from a tool call."""
    tool: str
    query: Dict[str, Any]
    result_summary: str
    result_data: Any = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class Learning:
    """A learning extracted from interactions."""
    type: str  # "pattern", "preference", "failure"
    content: str
    context: Optional[Dict] = None
    timestamp: datetime = field(default_factory=datetime.now)
