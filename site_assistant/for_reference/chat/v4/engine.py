"""
Execution Engine for Chat V4

The core orchestration loop that coordinates agents and manages execution flow.
Implements the state machine for multi-step task execution.
"""

import logging
from dataclasses import dataclass
from typing import Optional, Callable, Dict, Any
from datetime import datetime

from .state import ExecutionState, StepResult
from .storage import ExecutionStorage, ExecutionLogger
from .errors import (
    V4Exception, PlanningError, StepExecutionError,
    ExecutionError, RetryHandler
)
from .agents.planner import PlannerAgent, QuickPlanner
from .agents.stepper import StepperAgent, StepDecision
from .agents.finisher import FinisherAgent
from .agents.base import AgentContext

logger = logging.getLogger(__name__)

# V4 Engine logging
V4_ENGINE_LOG = True

def engine_log(stage: str, message: str, data: dict = None):
    """Log engine events with visual formatting"""
    if not V4_ENGINE_LOG:
        return

    print(f"\n{'─'*80}")
    print(f"⚙️  ENGINE {stage.upper()}")
    print(f"{'─'*80}")
    print(f"   {message}")
    if data:
        for key, value in data.items():
            if isinstance(value, str) and len(value) > 150:
                value = value[:150] + "..."
            print(f"   • {key}: {value}")
    print(f"{'─'*80}")


@dataclass
class EngineResult:
    """Result from execution engine"""
    success: bool
    response: str
    awaiting_user: bool = False
    execution_id: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    steps_executed: int = 0
    error: Optional[str] = None


@dataclass
class EngineConfig:
    """Configuration for execution engine"""
    max_steps: int = 20
    max_retries: int = 3
    max_replan_attempts: int = 2
    enable_quick_planning: bool = True
    enable_confirmations: bool = True
    log_executions: bool = False
    model_name: str = "gemini-flash"  # Model from conversation settings


class ExecutionEngine:
    """
    Main execution engine that coordinates all agents.

    Implements the state machine:
    planning → stepping → executing_step → stepping → ... → finishing → completed

    The engine:
    - Receives user requests and creates execution plans
    - Iterates through plan steps, calling appropriate agents
    - Handles errors, retries, and replanning
    - Generates final responses
    """

    def __init__(
        self,
        user_id: str,
        conversation_id: str,
        config: EngineConfig = None,
        agent_registry: Dict[str, Callable] = None,
        conversation=None,
        user=None
    ):
        """
        Initialize execution engine.

        Args:
            user_id: User ID for the execution
            conversation_id: Conversation ID
            config: Engine configuration
            agent_registry: Optional dict mapping agent_type -> agent factory
            conversation: Conversation model instance (for storage)
            user: User model instance (for storage)
        """
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.config = config or EngineConfig()
        self.conversation = conversation
        self.user = user

        # Initialize orchestration agents with conversation's model
        model = self.config.model_name
        self.planner = PlannerAgent(model_name=model)
        self.stepper = StepperAgent(model_name=model)
        self.finisher = FinisherAgent(model_name=model)

        # Agent registry for specialized agents (to be populated in Phase 4)
        self.agent_registry = agent_registry or {}

    def _save_state(self, state: ExecutionState) -> None:
        """Save execution state with conversation and user context."""
        ExecutionStorage.save(state, self.conversation, self.user)

    def execute(
        self,
        user_request: str,
        conversation_summary: str = "",
        resolved_references: Dict[str, list] = None
    ) -> EngineResult:
        """
        Execute a user request.

        Main entry point for processing requests that need planning.

        Args:
            user_request: The user's request text
            conversation_summary: Summary of conversation context
            resolved_references: Pre-resolved entity references

        Returns:
            EngineResult with response and metadata
        """
        # Initialize execution state
        state = ExecutionState(
            conversation_id=self.conversation_id,
            user_id=self.user_id,
            user_request=user_request,
            resolved_references=resolved_references or {},
            status="planning"
        )

        ExecutionLogger.log_start(state)

        try:
            # Run the execution loop
            result = self._run_execution_loop(state, conversation_summary)
            return result

        except Exception as e:
            logger.error(f"Execution failed: {e}", exc_info=True)
            state.status = "failed"
            state.add_error(str(e), category="engine")
            self._save_state(state)

            return EngineResult(
                success=False,
                response=f"I encountered an error processing your request: {str(e)}",
                execution_id=state.execution_id,
                error=str(e)
            )

    def resume(
        self,
        execution_id: str,
        user_response: str
    ) -> EngineResult:
        """
        Resume a paused execution with user response.

        Called when user responds to an ask_user prompt.

        Args:
            execution_id: ID of paused execution
            user_response: User's response

        Returns:
            EngineResult with response and metadata
        """
        # Load execution state
        state = ExecutionStorage.load(execution_id)

        if not state:
            return EngineResult(
                success=False,
                response="I couldn't find that conversation. Let's start fresh.",
                error="Execution not found"
            )

        if state.status != "awaiting_user":
            return EngineResult(
                success=False,
                response="There's no pending question to answer.",
                error="Not awaiting user response"
            )

        # Store user response and resume
        state.user_response = user_response
        state.status = "stepping"
        state.pending_question = None
        state.pending_options = None

        self._save_state(state)

        try:
            return self._run_execution_loop(state, "")
        except Exception as e:
            logger.error(f"Resume failed: {e}", exc_info=True)
            return EngineResult(
                success=False,
                response=f"I encountered an error: {str(e)}",
                execution_id=execution_id,
                error=str(e)
            )

    def _run_execution_loop(
        self,
        state: ExecutionState,
        conversation_summary: str
    ) -> EngineResult:
        """
        Run the main execution loop.

        Implements the state machine transitions.
        """
        steps_executed = 0
        replan_count = 0

        while steps_executed < self.config.max_steps:

            # PLANNING STATE
            if state.status == "planning":
                engine_log("planning", f"Creating plan for: '{state.user_request}'")
                try:
                    plan = self._create_plan(
                        state.user_request,
                        conversation_summary,
                        state.resolved_references
                    )
                    state.plan = plan
                    state.status = "stepping"
                    self._save_state(state)
                    logger.debug(f"Plan created with {len(plan.steps)} steps")

                    # Log plan details
                    steps_summary = "\n".join([
                        f"      {s.step_id}. {s.agent_type}.{s.action} - {s.description}"
                        for s in plan.steps
                    ])
                    engine_log("plan created", f"Plan with {len(plan.steps)} step(s)", {
                        "complexity": plan.estimated_complexity,
                        "reasoning": plan.reasoning,
                        "steps": f"\n{steps_summary}"
                    })

                except PlanningError as e:
                    state.status = "failed"
                    state.add_error(str(e), category="planning")
                    self._save_state(state)
                    return EngineResult(
                        success=False,
                        response=f"I couldn't figure out how to help with that: {e}",
                        execution_id=state.execution_id,
                        error=str(e)
                    )

            # STEPPING STATE
            elif state.status == "stepping":
                decision = self.stepper.decide(state)
                logger.debug(f"Stepper decision: {decision.action}")
                engine_log("stepper", f"Decision: {decision.action}", {
                    "step_id": decision.step_id if decision.step_id else "N/A",
                    "reason": decision.replan_reason or decision.failure_reason or "proceeding"
                })

                if decision.action == "execute":
                    state.status = "executing_step"
                    state.current_step = decision.step_id

                elif decision.action == "retry":
                    state.status = "executing_step"
                    state.current_step = decision.step_id
                    state.working_memory['_retry_modification'] = decision.retry_modification
                    state.increment_retry(decision.step_id)

                elif decision.action == "replan":
                    if replan_count >= self.config.max_replan_attempts:
                        state.status = "failed"
                        state.add_error("Max replanning attempts exceeded", category="engine")
                        break

                    replan_count += 1
                    state.status = "planning"
                    # Store results for revision context
                    state.working_memory['_replan_reason'] = decision.replan_reason

                    try:
                        new_plan = self.planner.revise_plan(
                            original_request=state.user_request,
                            original_plan=state.plan,
                            completed_results=[
                                r.to_dict() for r in state.get_completed_results()
                            ],
                            failure_reason=decision.replan_reason
                        )
                        state.plan = new_plan
                        state.status = "stepping"
                    except PlanningError as e:
                        state.status = "failed"
                        state.add_error(str(e), category="replan")
                        break

                elif decision.action == "ask_user":
                    state.status = "awaiting_user"
                    state.pending_question = decision.question
                    state.pending_options = decision.options
                    self._save_state(state)
                    ExecutionStorage.set_conversation_execution(
                        self.conversation_id,
                        state.execution_id
                    )

                    # Format question for user
                    question = self.finisher.synthesize_question(
                        decision.question,
                        decision.options
                    )

                    return EngineResult(
                        success=True,
                        response=question,
                        awaiting_user=True,
                        execution_id=state.execution_id,
                        input_tokens=state.total_input_tokens,
                        output_tokens=state.total_output_tokens,
                        steps_executed=steps_executed
                    )

                elif decision.action == "complete":
                    state.status = "finishing"

                elif decision.action == "fail":
                    state.status = "failed"
                    state.add_error(
                        decision.failure_reason or "Execution failed",
                        category="stepper"
                    )
                    break

                self._save_state(state)

            # EXECUTING_STEP STATE
            elif state.status == "executing_step":
                step = state.get_step(state.current_step)

                if not step:
                    state.add_error(f"Step {state.current_step} not found", category="engine")
                    state.status = "stepping"
                    continue

                # Mark step as running
                step.status = "running"
                self._save_state(state)

                engine_log("executing", f"Running step {step.step_id}: {step.agent_type}.{step.action}", {
                    "description": step.description,
                    "params": str(step.params)[:200] if step.params else "none",
                    "depends_on": str(step.depends_on) if step.depends_on else "none"
                })

                try:
                    result = self._execute_step(step, state)
                    state.step_results[step.step_id] = result

                    if result.success:
                        step.status = "completed"
                        # Update working memory with outputs
                        self._update_working_memory(state, step, result)
                        engine_log("step complete", f"✅ Step {step.step_id} succeeded", {
                            "summary": result.summary,
                            "entities_affected": str(result.entities_affected) if result.entities_affected else "none",
                            "output_keys": str(list(result.output.keys())) if result.output else "none"
                        })
                    else:
                        step.status = "failed"
                        state.add_error(
                            result.error or "Step failed",
                            step_id=step.step_id,
                            category="step"
                        )
                        engine_log("step failed", f"❌ Step {step.step_id} failed", {
                            "error": result.error
                        })

                    state.add_tokens(result.tokens_used // 2, result.tokens_used // 2)
                    steps_executed += 1

                    ExecutionLogger.log_step(state, step.step_id, result.to_dict())

                except Exception as e:
                    logger.error(f"Step execution error: {e}", exc_info=True)
                    step.status = "failed"
                    state.step_results[step.step_id] = StepResult(
                        step_id=step.step_id,
                        agent_type=step.agent_type,
                        action=step.action,
                        success=False,
                        output={},
                        summary="",
                        error=str(e)
                    )
                    state.add_error(str(e), step_id=step.step_id, category="exception")

                state.status = "stepping"
                self._save_state(state)

            # FINISHING STATE
            elif state.status == "finishing":
                engine_log("finishing", f"Generating final response")
                response = self.finisher.synthesize(state, conversation_summary)
                state.status = "completed"
                state.completed_at = datetime.now()
                self._save_state(state)
                ExecutionLogger.log_complete(state)
                engine_log("complete", f"Execution complete", {
                    "steps_executed": steps_executed,
                    "response_preview": response[:150] + "..." if len(response) > 150 else response
                })

                # Clear conversation execution mapping
                ExecutionStorage.clear_conversation_execution(self.conversation_id)

                return EngineResult(
                    success=True,
                    response=response,
                    execution_id=state.execution_id,
                    input_tokens=state.total_input_tokens,
                    output_tokens=state.total_output_tokens,
                    steps_executed=steps_executed
                )

            # COMPLETED or FAILED - shouldn't reach here in loop
            else:
                break

        # Max steps exceeded or failed
        if state.status != "completed":
            if state.status != "failed":
                state.status = "failed"
                state.add_error("Max execution steps exceeded", category="engine")

            self._save_state(state)
            ExecutionLogger.log_error(state, "Max steps or failure")

            # Generate partial response
            response = self.finisher.synthesize_partial(
                state,
                "Some steps couldn't be completed."
            )

            return EngineResult(
                success=False,
                response=response,
                execution_id=state.execution_id,
                input_tokens=state.total_input_tokens,
                output_tokens=state.total_output_tokens,
                steps_executed=steps_executed,
                error="Execution incomplete"
            )

    def _create_plan(
        self,
        user_request: str,
        conversation_summary: str,
        resolved_references: Dict[str, list]
    ):
        """Create execution plan, trying quick planning first"""
        # Try quick planning for simple requests
        if self.config.enable_quick_planning:
            quick_plan = QuickPlanner.try_quick_plan(user_request)
            if quick_plan:
                logger.debug("Using quick plan")
                return quick_plan

        # Use full planner
        return self.planner.create_plan(
            user_request,
            conversation_summary,
            resolved_references
        )

    def _execute_step(
        self,
        step,
        state: ExecutionState
    ) -> StepResult:
        """
        Execute a single plan step.

        Args:
            step: PlanStep to execute
            state: Current execution state

        Returns:
            StepResult with outcome
        """
        agent_type = step.agent_type

        # Get agent from registry
        agent_factory = self.agent_registry.get(agent_type)

        if not agent_factory:
            # Agent not yet implemented - return mock result for testing
            logger.warning(f"Agent '{agent_type}' not in registry, using mock")
            return self._mock_step_result(step, state)

        # Create agent instance
        agent = agent_factory()

        # Build agent context
        retry_mod = state.working_memory.pop('_retry_modification', None)
        context = AgentContext(
            user_id=self.user_id,
            step_id=step.step_id,
            action=step.action,
            params=self._resolve_step_params(step, state),
            working_memory=state.working_memory,
            model_name=self.config.model_name,  # Pass model from config
            retry_context=retry_mod,
            retry_count=state.get_retry_count(step.step_id)
        )

        # Execute with agent
        # Note: In Phase 4, agents will be async, but for now we support sync
        import asyncio
        if asyncio.iscoroutinefunction(agent.execute):
            result = asyncio.run(agent.execute(context))
        else:
            result = agent.execute(context)

        return result

    def _mock_step_result(
        self,
        step,
        state: ExecutionState
    ) -> StepResult:
        """
        Create mock result for testing when agent not implemented.

        This allows testing the orchestration flow before all agents exist.
        """
        return StepResult(
            step_id=step.step_id,
            agent_type=step.agent_type,
            action=step.action,
            success=True,
            output={"mock": True, "params": step.params},
            summary=f"[Mock] {step.description or f'{step.agent_type}.{step.action}'}",
            entities_affected={},
            tokens_used=0
        )

    def _resolve_step_params(
        self,
        step,
        state: ExecutionState
    ) -> Dict[str, Any]:
        """
        Resolve step parameters, substituting references from working memory.

        Handles patterns like:
        - "from_step_1": Uses output from step 1
        - "step_1.tasks": Gets 'tasks' key from step 1 output
        """
        params = step.params.copy()

        for key, value in params.items():
            if isinstance(value, str):
                # Check for step output reference
                if value.startswith("step_") and "." in value:
                    parts = value.split(".", 1)
                    step_ref = parts[0]  # e.g., "step_1"
                    field = parts[1]     # e.g., "tasks"

                    step_id = int(step_ref.replace("step_", ""))
                    if step_id in state.step_results:
                        result = state.step_results[step_id]
                        if field in result.output:
                            params[key] = result.output[field]

                # Check for working memory reference
                elif value.startswith("memory."):
                    mem_key = value.replace("memory.", "")
                    if mem_key in state.working_memory:
                        params[key] = state.working_memory[mem_key]

        # Also add IDs from dependent steps automatically
        for dep_id in step.depends_on:
            if dep_id in state.step_results:
                result = state.step_results[dep_id]
                if result.success:
                    # Make dependent step outputs available
                    for out_key, out_val in result.output.items():
                        if out_key not in params:
                            # Use convention: dep step output as optional param
                            params[f"_from_step_{dep_id}_{out_key}"] = out_val

        return params

    def _update_working_memory(
        self,
        state: ExecutionState,
        step,
        result: StepResult
    ):
        """Update working memory with step results"""
        # Store full output under step key
        state.working_memory[f"step_{step.step_id}_output"] = result.output

        # Extract commonly needed values
        output = result.output

        # Task IDs
        if 'tasks' in output and isinstance(output['tasks'], list):
            task_ids = [t.get('id') for t in output['tasks'] if t.get('id')]
            if task_ids:
                state.working_memory['found_tasks'] = task_ids
                state.working_memory['last_found_task_ids'] = task_ids

        # Note IDs
        if 'notes' in output and isinstance(output['notes'], list):
            note_ids = [n.get('id') for n in output['notes'] if n.get('id')]
            if note_ids:
                state.working_memory['found_notes'] = note_ids

        # Project/Area IDs
        if 'projects' in output and isinstance(output['projects'], list):
            if len(output['projects']) == 1:
                state.working_memory['target_project_id'] = output['projects'][0].get('id')
            state.working_memory['found_projects'] = [
                p.get('id') for p in output['projects'] if p.get('id')
            ]

        if 'areas' in output and isinstance(output['areas'], list):
            if len(output['areas']) == 1:
                state.working_memory['target_area_id'] = output['areas'][0].get('id')

        # Single item created
        if 'task' in output and isinstance(output['task'], dict):
            state.working_memory['last_created_task'] = output['task'].get('id')

        if 'note' in output and isinstance(output['note'], dict):
            state.working_memory['last_created_note'] = output['note'].get('id')

        if 'project' in output and isinstance(output['project'], dict):
            state.working_memory['last_created_project'] = output['project'].get('id')
