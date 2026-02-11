"""
Execution State Models for Chat V4

Contains dataclasses for managing execution state:
- PlanStep: Single step in an execution plan
- Plan: Complete execution plan
- StepResult: Result of executing a step
- ExecutionState: Central state for a single execution
"""

from dataclasses import dataclass, field
from typing import Optional, Literal, Any, Dict, List
from datetime import datetime
import uuid
import json


# Type aliases
ExecutionStatus = Literal[
    "planning",
    "stepping",
    "executing_step",
    "awaiting_user",
    "finishing",
    "completed",
    "failed"
]

StepStatus = Literal[
    "pending",
    "running",
    "completed",
    "failed",
    "skipped"
]

AgentType = Literal[
    "tasks",
    "notes",
    "projects",
    "areas",
    "inbox",
    "search"
]

Complexity = Literal["simple", "moderate", "complex"]


@dataclass
class PlanStep:
    """
    Single step in an execution plan.

    Each step specifies an agent and a goal. The agent uses its
    domain expertise to interpret the goal and decide what actions
    to take.
    """

    step_id: int
    agent_type: str
    goal: str  # Natural language goal for the agent to accomplish
    depends_on: List[int] = field(default_factory=list)
    status: StepStatus = "pending"

    def to_dict(self) -> dict:
        """Serialize to dictionary"""
        return {
            'step_id': self.step_id,
            'agent_type': self.agent_type,
            'goal': self.goal,
            'depends_on': self.depends_on,
            'status': self.status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'PlanStep':
        """Create from dictionary"""
        return cls(
            step_id=data['step_id'],
            agent_type=data['agent_type'],
            goal=data.get('goal', ''),
            depends_on=data.get('depends_on', []),
            status=data.get('status', 'pending'),
        )


@dataclass
class Plan:
    """Execution plan created by Planner agent"""

    steps: List[PlanStep]
    reasoning: str
    estimated_complexity: Complexity = "simple"
    revision_count: int = 0
    original_steps: List[PlanStep] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    def get_pending_steps(self) -> List[PlanStep]:
        """Get all pending steps"""
        return [s for s in self.steps if s.status == "pending"]

    def get_next_executable_step(self, completed_step_ids: set) -> Optional[PlanStep]:
        """Get next step whose dependencies are satisfied"""
        for step in self.steps:
            if step.status != "pending":
                continue
            # Check if all dependencies are completed
            if all(dep_id in completed_step_ids for dep_id in step.depends_on):
                return step
        return None

    def to_dict(self) -> dict:
        """Serialize to dictionary"""
        return {
            'steps': [s.to_dict() for s in self.steps],
            'reasoning': self.reasoning,
            'estimated_complexity': self.estimated_complexity,
            'revision_count': self.revision_count,
            'original_steps': [s.to_dict() for s in self.original_steps],
            'created_at': self.created_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Plan':
        """Create from dictionary"""
        return cls(
            steps=[PlanStep.from_dict(s) for s in data.get('steps', [])],
            reasoning=data.get('reasoning', ''),
            estimated_complexity=data.get('estimated_complexity', 'simple'),
            revision_count=data.get('revision_count', 0),
            original_steps=[PlanStep.from_dict(s) for s in data.get('original_steps', [])],
            created_at=datetime.fromisoformat(data['created_at']) if data.get('created_at') else datetime.now()
        )


@dataclass
class StepResult:
    """
    Result of executing a single step.

    Contains the outcome of an agent's execution, including:
    - What action was taken (decided by the agent)
    - Success/failure status
    - Output data and summary
    - Signals for engine (need_replan, need_user_input)
    """

    step_id: int
    agent_type: str
    action: str  # The action the agent decided to take
    success: bool
    output: Dict[str, Any]
    summary: str

    # Error information
    error: Optional[str] = None

    # Signals for engine - agent can request special handling
    need_replan: bool = False
    replan_context: Optional[Dict[str, Any]] = None  # Why replan is needed

    need_user_input: bool = False
    user_question: Optional[str] = None  # Question to ask user
    user_options: Optional[List[str]] = None  # Options for user to choose

    # Tracking
    entities_affected: Dict[str, List[int]] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    tokens_used: int = 0

    def __post_init__(self):
        if self.completed_at is None and self.success is not None:
            self.completed_at = datetime.now()

    def to_dict(self) -> dict:
        """Serialize to dictionary"""
        return {
            'step_id': self.step_id,
            'agent_type': self.agent_type,
            'action': self.action,
            'success': self.success,
            'output': self.output,
            'summary': self.summary,
            'error': self.error,
            'need_replan': self.need_replan,
            'replan_context': self.replan_context,
            'need_user_input': self.need_user_input,
            'user_question': self.user_question,
            'user_options': self.user_options,
            'entities_affected': self.entities_affected,
            'started_at': self.started_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'tokens_used': self.tokens_used
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'StepResult':
        """Create from dictionary"""
        return cls(
            step_id=data['step_id'],
            agent_type=data['agent_type'],
            action=data.get('action', ''),
            success=data['success'],
            output=data.get('output', {}),
            summary=data.get('summary', ''),
            error=data.get('error'),
            need_replan=data.get('need_replan', False),
            replan_context=data.get('replan_context'),
            need_user_input=data.get('need_user_input', False),
            user_question=data.get('user_question'),
            user_options=data.get('user_options'),
            entities_affected=data.get('entities_affected', {}),
            started_at=datetime.fromisoformat(data['started_at']) if data.get('started_at') else datetime.now(),
            completed_at=datetime.fromisoformat(data['completed_at']) if data.get('completed_at') else None,
            tokens_used=data.get('tokens_used', 0)
        )


@dataclass
class ExecutionState:
    """
    Central state for a single execution (request → response).

    This is the shared state that enables stateless agents to work together.
    Persisted to cache/Redis during execution for recovery and debugging.
    """

    # Identity
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: str = ""
    user_id: str = ""

    # Request info
    user_request: str = ""
    message_type: str = ""  # From intake classifier
    resolved_references: Dict[str, List[int]] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.now)

    # Plan
    plan: Optional[Plan] = None

    # Execution tracking
    current_step: int = 0
    status: ExecutionStatus = "planning"

    # Results
    step_results: Dict[int, StepResult] = field(default_factory=dict)
    working_memory: Dict[str, Any] = field(default_factory=dict)

    # User communication
    pending_question: Optional[str] = None
    pending_options: Optional[List[str]] = None
    user_response: Optional[str] = None

    # Error tracking
    errors: List[Dict[str, Any]] = field(default_factory=list)
    retry_count: Dict[int, int] = field(default_factory=dict)

    # Token tracking
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    # Timing
    completed_at: Optional[datetime] = None

    @property
    def total_tokens(self) -> int:
        """Total tokens used"""
        return self.total_input_tokens + self.total_output_tokens

    def get_step(self, step_id: int) -> Optional[PlanStep]:
        """Get step by ID"""
        if self.plan:
            for step in self.plan.steps:
                if step.step_id == step_id:
                    return step
        return None

    def get_completed_step_ids(self) -> set:
        """Get IDs of all completed steps"""
        return {
            step_id for step_id, result in self.step_results.items()
            if result.success
        }

    def get_completed_results(self) -> List[StepResult]:
        """Get all successful step results"""
        return [r for r in self.step_results.values() if r.success]

    def get_failed_results(self) -> List[StepResult]:
        """Get all failed step results"""
        return [r for r in self.step_results.values() if not r.success]

    def add_error(self, error: str, step_id: Optional[int] = None, category: str = "unknown"):
        """Add an error to the error list"""
        self.errors.append({
            'message': error,
            'step_id': step_id,
            'category': category,
            'timestamp': datetime.now().isoformat()
        })

    def increment_retry(self, step_id: int) -> int:
        """Increment retry count for a step, return new count"""
        self.retry_count[step_id] = self.retry_count.get(step_id, 0) + 1
        return self.retry_count[step_id]

    def get_retry_count(self, step_id: int) -> int:
        """Get retry count for a step"""
        return self.retry_count.get(step_id, 0)

    def add_tokens(self, input_tokens: int = 0, output_tokens: int = 0):
        """Add tokens to tracking"""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens

    def all_steps_completed(self) -> bool:
        """Check if all plan steps are completed"""
        if not self.plan:
            return True
        return all(
            step.status in ("completed", "skipped")
            for step in self.plan.steps
        )

    def has_failures(self) -> bool:
        """Check if any steps failed"""
        return any(not r.success for r in self.step_results.values())

    def to_dict(self) -> dict:
        """Serialize to dictionary for storage"""
        return {
            'execution_id': self.execution_id,
            'conversation_id': self.conversation_id,
            'user_id': self.user_id,
            'user_request': self.user_request,
            'message_type': self.message_type,
            'resolved_references': self.resolved_references,
            'started_at': self.started_at.isoformat(),
            'plan': self.plan.to_dict() if self.plan else None,
            'current_step': self.current_step,
            'status': self.status,
            'step_results': {
                str(k): v.to_dict() for k, v in self.step_results.items()
            },
            'working_memory': self.working_memory,
            'pending_question': self.pending_question,
            'pending_options': self.pending_options,
            'user_response': self.user_response,
            'errors': self.errors,
            'retry_count': {str(k): v for k, v in self.retry_count.items()},
            'total_input_tokens': self.total_input_tokens,
            'total_output_tokens': self.total_output_tokens,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ExecutionState':
        """Create from dictionary"""
        state = cls(
            execution_id=data['execution_id'],
            conversation_id=data.get('conversation_id', ''),
            user_id=data.get('user_id', ''),
            user_request=data.get('user_request', ''),
            message_type=data.get('message_type', ''),
            resolved_references=data.get('resolved_references', {}),
            started_at=datetime.fromisoformat(data['started_at']) if data.get('started_at') else datetime.now(),
            plan=Plan.from_dict(data['plan']) if data.get('plan') else None,
            current_step=data.get('current_step', 0),
            status=data.get('status', 'planning'),
            working_memory=data.get('working_memory', {}),
            pending_question=data.get('pending_question'),
            pending_options=data.get('pending_options'),
            user_response=data.get('user_response'),
            errors=data.get('errors', []),
            total_input_tokens=data.get('total_input_tokens', 0),
            total_output_tokens=data.get('total_output_tokens', 0),
            completed_at=datetime.fromisoformat(data['completed_at']) if data.get('completed_at') else None
        )

        # Restore step_results
        for step_id, result_data in data.get('step_results', {}).items():
            state.step_results[int(step_id)] = StepResult.from_dict(result_data)

        # Restore retry_count
        for step_id, count in data.get('retry_count', {}).items():
            state.retry_count[int(step_id)] = count

        return state

    def to_json(self) -> str:
        """Serialize to JSON string"""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> 'ExecutionState':
        """Create from JSON string"""
        return cls.from_dict(json.loads(json_str))

    def get_summary_for_context(self) -> dict:
        """Get a summary suitable for passing to agents as context"""
        return {
            'execution_id': self.execution_id,
            'request': self.user_request,
            'status': self.status,
            'current_step': self.current_step,
            'steps_completed': len(self.get_completed_results()),
            'steps_total': len(self.plan.steps) if self.plan else 0,
            'has_errors': bool(self.errors),
            'working_memory_keys': list(self.working_memory.keys())
        }
