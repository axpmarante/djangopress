"""
Chat V2 Executor

Executes plan steps one at a time.

The executor:
1. Takes a plan step and executes it using the ToolRegistry
2. Handles placeholder resolution (${step_1_result.id})
3. Manages retries for failed steps
4. Updates AgentMemory after each step
5. Can run a complete plan to completion

Key design decisions:
- Steps execute sequentially (later steps can depend on earlier results)
- Placeholders allow referencing previous step results
- Failed steps can be retried up to max_retries times
- All state changes are persisted for recovery
"""

import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from .models import AgentMemory, PlanStep
from .memory import MemoryState, get_or_create_memory_state
from .tools.base import ToolRegistry, ToolCall, ToolResult, ToolStatus


@dataclass
class StepResult:
    """Result from executing a single step."""
    success: bool
    step_number: int
    data: Optional[Dict] = None
    message: str = ""
    error: str = ""
    execution_time_ms: int = 0
    retried: bool = False


@dataclass
class PlanExecutionResult:
    """Result from executing a complete plan."""
    success: bool
    completed_steps: int
    total_steps: int
    step_results: List[StepResult] = field(default_factory=list)
    final_message: str = ""
    error: str = ""


class Executor:
    """
    Executes plan steps and manages execution state.

    Usage:
        executor = Executor(user)

        # Execute a single step
        result = executor.execute_step(memory, step)

        # Run entire plan to completion
        result = executor.run_plan(memory)
    """

    def __init__(self, user):
        self.user = user
        self.tool_registry = ToolRegistry(user)

    def execute_step(
        self,
        memory: AgentMemory,
        step: PlanStep = None
    ) -> StepResult:
        """
        Execute a single plan step.

        Args:
            memory: AgentMemory containing the plan state
            step: Specific step to execute (or None for current step)

        Returns:
            StepResult with execution outcome
        """
        # Get the step to execute
        if step is None:
            step = self._get_current_step(memory)
            if step is None:
                return StepResult(
                    success=False,
                    step_number=memory.current_stage,
                    error="No current step to execute"
                )

        start_time = timezone.now()

        try:
            # Mark step as in progress
            step.start()

            # Resolve placeholders in params
            resolved_params = self._resolve_placeholders(
                step.params,
                memory.stage_results
            )

            # Create tool call
            tool_call = ToolCall(
                tool=step.tool,
                action=step.action,
                resource_type=step.resource_type,
                params=resolved_params
            )

            # Execute via tool registry
            tool_result = self.tool_registry.execute(tool_call)

            # Calculate execution time
            end_time = timezone.now()
            exec_time_ms = int((end_time - start_time).total_seconds() * 1000)

            if tool_result.is_success():
                # Step succeeded
                result_data = self._extract_result_data(tool_result)
                step.complete(result_data)

                # Update memory state
                self._update_memory_success(memory, step, tool_result)

                return StepResult(
                    success=True,
                    step_number=step.order,
                    data=result_data,
                    message=tool_result.message,
                    execution_time_ms=exec_time_ms
                )
            else:
                # Step failed
                error_msg = tool_result.error or tool_result.message or "Unknown error"

                # Check if we can retry
                if step.can_retry():
                    step.retry()
                    return StepResult(
                        success=False,
                        step_number=step.order,
                        error=error_msg,
                        execution_time_ms=exec_time_ms,
                        retried=True
                    )
                else:
                    step.fail(error_msg)
                    self._update_memory_failure(memory, step, error_msg)
                    return StepResult(
                        success=False,
                        step_number=step.order,
                        error=error_msg,
                        execution_time_ms=exec_time_ms
                    )

        except Exception as e:
            end_time = timezone.now()
            exec_time_ms = int((end_time - start_time).total_seconds() * 1000)

            error_msg = str(e)
            step.fail(error_msg)
            self._update_memory_failure(memory, step, error_msg)

            return StepResult(
                success=False,
                step_number=step.order,
                error=error_msg,
                execution_time_ms=exec_time_ms
            )

    def run_plan(
        self,
        memory: AgentMemory,
        max_steps: int = 10
    ) -> PlanExecutionResult:
        """
        Execute all remaining steps in a plan.

        Args:
            memory: AgentMemory containing the plan
            max_steps: Safety limit on steps to execute

        Returns:
            PlanExecutionResult with overall outcome
        """
        step_results = []
        completed = 0

        for _ in range(max_steps):
            # Check if plan is complete
            if memory.current_stage > memory.total_stages:
                break

            # Get and execute current step
            step = self._get_current_step(memory)
            if step is None:
                break

            result = self.execute_step(memory, step)
            step_results.append(result)

            if result.success:
                completed += 1
            elif result.retried:
                # Retry the same step
                continue
            else:
                # Step failed, stop execution
                return PlanExecutionResult(
                    success=False,
                    completed_steps=completed,
                    total_steps=memory.total_stages,
                    step_results=step_results,
                    error=f"Step {step.order} failed: {result.error}"
                )

            # Refresh memory from DB to get updated current_stage
            memory.refresh_from_db()

        # Check final state
        success = memory.current_stage > memory.total_stages

        return PlanExecutionResult(
            success=success,
            completed_steps=completed,
            total_steps=memory.total_stages,
            step_results=step_results,
            final_message=self._summarize_results(step_results) if success else ""
        )

    def execute_single_step_and_advance(
        self,
        memory: AgentMemory
    ) -> Tuple[StepResult, bool]:
        """
        Execute the current step and advance memory.

        Returns:
            Tuple of (StepResult, is_plan_complete)
        """
        result = self.execute_step(memory)

        # Refresh to get latest state
        memory.refresh_from_db()

        is_complete = memory.current_stage > memory.total_stages

        return result, is_complete

    # =========================================================================
    # Private Helper Methods
    # =========================================================================

    def _get_current_step(self, memory: AgentMemory) -> Optional[PlanStep]:
        """Get the current step to execute."""
        try:
            return PlanStep.objects.get(
                memory=memory,
                order=memory.current_stage
            )
        except PlanStep.DoesNotExist:
            return None

    def _resolve_placeholders(
        self,
        params: Dict[str, Any],
        stage_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Resolve placeholder references in params.

        Placeholders like ${step_1_result.id} are replaced with
        actual values from previous step results.
        """
        resolved = {}

        for key, value in params.items():
            if isinstance(value, str) and "${" in value:
                resolved[key] = self._resolve_single_placeholder(value, stage_results)
            elif isinstance(value, dict):
                resolved[key] = self._resolve_placeholders(value, stage_results)
            else:
                resolved[key] = value

        return resolved

    def _resolve_single_placeholder(
        self,
        value: str,
        stage_results: Dict[str, Any]
    ) -> Any:
        """
        Resolve a single placeholder string.

        Patterns:
        - ${step_N_result.field} - Get field from step N result
        - ${step_N_result.items[0].field} - Get field from first item
        """
        pattern = r'\$\{step_(\d+)_result\.([^}]+)\}'
        match = re.search(pattern, value)

        if not match:
            return value

        step_num = match.group(1)
        field_path = match.group(2)

        # Get the stage result
        stage_result = stage_results.get(step_num, {})
        data = stage_result.get("data", stage_result)

        # Navigate the field path
        try:
            result = self._navigate_path(data, field_path)

            # If the placeholder is the entire value, return the resolved type
            if value == f"${{step_{step_num}_result.{field_path}}}":
                return result

            # Otherwise, string substitution
            return value.replace(match.group(0), str(result))

        except (KeyError, IndexError, TypeError):
            # Couldn't resolve, return original
            return value

    def _navigate_path(self, data: Any, path: str) -> Any:
        """Navigate a dotted path with array indexing support."""
        current = data

        # Handle paths like "items[0].id" or "id"
        parts = re.split(r'\.|\[|\]', path)
        parts = [p for p in parts if p]  # Remove empty strings

        for part in parts:
            if isinstance(current, dict):
                current = current[part]
            elif isinstance(current, list):
                current = current[int(part)]
            else:
                raise KeyError(f"Cannot navigate '{part}' in {type(current)}")

        return current

    def _extract_result_data(self, tool_result: ToolResult) -> Dict[str, Any]:
        """Extract relevant data from tool result for storage."""
        data = tool_result.data

        # If it's a search/list result with items, store them for display
        if isinstance(data, dict):
            if "items" in data and data["items"]:
                first_item = data["items"][0]
                return {
                    "id": first_item.get("id"),
                    "title": first_item.get("title"),
                    "count": data.get("count", len(data["items"])),
                    "items": data["items"][:15]  # Store up to 15 items for display
                }
            return data

        return {"raw": data}

    @transaction.atomic
    def _update_memory_success(
        self,
        memory: AgentMemory,
        step: PlanStep,
        tool_result: ToolResult
    ) -> None:
        """Update memory state after successful step."""
        # Store stage result
        stage_results = memory.stage_results or {}
        stage_results[str(step.order)] = {
            "summary": tool_result.message,
            "data": self._extract_result_data(tool_result),
            "completed_at": timezone.now().isoformat()
        }

        # Advance to next stage
        memory.stage_results = stage_results
        memory.current_stage = step.order + 1
        memory.save(update_fields=['stage_results', 'current_stage', 'updated_at'])

    def _update_memory_failure(
        self,
        memory: AgentMemory,
        step: PlanStep,
        error: str
    ) -> None:
        """Update memory state after failed step."""
        # Record failure
        failed_approaches = memory.failed_approaches or []
        failed_approaches.append(f"Step {step.order} ({step.description}): {error}")
        failed_approaches = failed_approaches[-10:]  # Keep last 10

        memory.failed_approaches = failed_approaches
        memory.save(update_fields=['failed_approaches', 'updated_at'])

    def _summarize_results(self, step_results: List[StepResult]) -> str:
        """Create a summary of execution results."""
        lines = []

        for result in step_results:
            if result.success:
                lines.append(f"Step {result.step_number}: {result.message}")
            else:
                lines.append(f"Step {result.step_number}: Failed - {result.error}")

        return "\n".join(lines)


def execute_current_step(user, conversation) -> Tuple[StepResult, bool]:
    """
    Convenience function to execute the current step.

    Returns:
        Tuple of (StepResult, is_plan_complete)
    """
    from .models import AgentMemory

    try:
        memory = AgentMemory.objects.get(conversation=conversation)
    except AgentMemory.DoesNotExist:
        return StepResult(
            success=False,
            step_number=0,
            error="No agent memory found"
        ), True

    executor = Executor(user)
    return executor.execute_single_step_and_advance(memory)


def run_full_plan(user, conversation) -> PlanExecutionResult:
    """
    Convenience function to run a complete plan.
    """
    from .models import AgentMemory

    try:
        memory = AgentMemory.objects.get(conversation=conversation)
    except AgentMemory.DoesNotExist:
        return PlanExecutionResult(
            success=False,
            completed_steps=0,
            total_steps=0,
            error="No agent memory found"
        )

    executor = Executor(user)
    return executor.run_plan(memory)
