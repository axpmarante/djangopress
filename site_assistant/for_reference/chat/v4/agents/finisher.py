"""
Finisher Agent for Chat V4

Creates final user-facing responses from execution results.
Uses Sonnet model for natural language generation.
"""

import logging
from typing import Dict, Any, List, Optional

from ..state import ExecutionState, StepResult
from ..llm import LLMClient

logger = logging.getLogger(__name__)


class FinisherAgent:
    """
    Creates final user-facing response from execution results.

    The Finisher:
    - Summarizes what was accomplished
    - Reports any failures or partial results
    - Provides actionable next steps
    - Maintains natural conversation tone

    Model: Sonnet (natural language generation)
    """

    SYSTEM_PROMPT = """You are the AI assistant for ZemoNotes, a Second Brain personal knowledge management system.

Your role is to act as an **EXECUTIVE COACH** and **CHIEF OF STAFF** helping users manage their productivity system effectively.

## Your Personality

- **Warm but professional**: Like a trusted advisor who genuinely cares about their success
- **Proactive**: Don't just report what happened—offer insights and next steps
- **Encouraging**: Celebrate wins, no matter how small
- **Action-oriented**: Always guide toward what to do next

## Your Task

Create a helpful, engaging response based on the execution results provided.

## Response Guidelines

1. **Acknowledge the action**: Confirm what was done
2. **Provide context**: Give relevant details (counts, names, specifics)
3. **Add value**: Offer observations, patterns, or suggestions
4. **Guide next steps**: What might they want to do next?

## Formatting

- Use conversational language, not robotic system messages
- For lists of items (5 or fewer), show them with titles
- For larger lists, summarize with counts and highlight important ones
- Use light markdown formatting (bold for emphasis, bullets for lists)
- Keep it scannable—don't write walls of text

## Tone Examples

Instead of: "Inbox has 1 note(s) and 2 task(s)"
Write: "Your inbox has 3 items waiting for you: 1 note and 2 tasks. Want me to help you organize them into projects, or should we tackle the tasks first?"

Instead of: "Task created successfully"
Write: "Got it! I've added 'Review Q1 goals' to your tasks with high priority. It's in your inbox—would you like to assign it to a specific project?"

Instead of: "Generated 0 organization suggestion(s)"
Write: "I looked at your inbox items but couldn't find obvious matches to your existing projects or areas. You might want to review them manually, or we could create a new project for them."

## For Inbox Processing Specifically

When showing inbox contents:
- List each item with its title
- Note any overdue tasks or important items
- Suggest organization options based on available projects/areas
- If no suggestions, explain why and offer alternatives

Output ONLY the response text, nothing else. No JSON, no explanation."""

    def __init__(self, model_name: str = None):
        """Initialize the Finisher with specified or default model"""
        self.llm = LLMClient(model_name=model_name or "claude")

    def synthesize(
        self,
        state: ExecutionState,
        conversation_summary: str = ""
    ) -> str:
        """
        Create final response from execution state.

        Args:
            state: Completed execution state
            conversation_summary: Optional conversation context

        Returns:
            Natural language response for the user
        """
        # Try quick response first for simple cases
        quick = self._try_quick_response(state)
        if quick:
            return quick

        # Build context for LLM
        context = self._build_context(state, conversation_summary)

        try:
            response = self.llm.chat([
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": context}
            ])
            return response.text.strip()
        except Exception as e:
            logger.error(f"Finisher LLM call failed: {e}")
            return self._fallback_response(state)

    def synthesize_partial(
        self,
        state: ExecutionState,
        reason: str = ""
    ) -> str:
        """
        Create response for partial/interrupted execution.

        Used when:
        - Execution was cancelled
        - Max iterations reached
        - Unrecoverable error occurred

        Args:
            state: Current execution state
            reason: Why execution stopped

        Returns:
            Response explaining partial results
        """
        completed = state.get_completed_results()

        if not completed:
            return f"I wasn't able to complete your request. {reason}"

        # Build partial results summary
        summaries = [r.summary for r in completed if r.summary]

        if summaries:
            result_text = " ".join(summaries[:3])
            return f"I partially completed your request: {result_text}. {reason}"
        else:
            return f"I made some progress but couldn't fully complete your request. {reason}"

    def synthesize_question(
        self,
        question: str,
        options: List[str] = None,
        context: str = ""
    ) -> str:
        """
        Format a question for the user.

        Args:
            question: The question to ask
            options: Optional list of choices
            context: Optional context about why we're asking

        Returns:
            Formatted question string
        """
        parts = []

        if context:
            parts.append(context)

        parts.append(question)

        if options:
            parts.append("\n")
            for i, option in enumerate(options, 1):
                parts.append(f"{i}. {option}")

        return "\n".join(parts)

    def _try_quick_response(self, state: ExecutionState) -> Optional[str]:
        """
        Try to generate response without LLM for very simple cases only.

        We're very restrictive here because we want the LLM to generate
        rich, contextual responses with the executive coach personality.

        Returns response string or None if LLM needed.
        """
        # Always use LLM for richer responses
        # Only skip for trivial single-action confirmations
        return None

    def _build_context(
        self,
        state: ExecutionState,
        conversation_summary: str
    ) -> str:
        """Build rich context for Finisher LLM"""
        parts = [f"Original request: {state.user_request}"]

        if conversation_summary:
            parts.append(f"\nConversation context: {conversation_summary}")

        parts.append("\n\nExecution results:")

        for step_id in sorted(state.step_results.keys()):
            result = state.step_results[step_id]
            step = state.get_step(step_id)

            step_desc = step.description if step else f"Step {step_id}"
            status = "SUCCESS" if result.success else "FAILED"

            parts.append(f"\n{step_id}. {step_desc}")
            parts.append(f"   Status: {status}")

            if result.summary:
                parts.append(f"   Summary: {result.summary}")

            if result.error:
                parts.append(f"   Error: {result.error}")

            # Include rich output details for context
            if result.success and result.output:
                parts.append(f"   Output data:")
                output_detail = self._format_output_detail(result.output)
                parts.append(output_detail)

            if result.entities_affected:
                for entity_type, ids in result.entities_affected.items():
                    parts.append(f"   {entity_type.title()}s affected: {len(ids)}")

        # Add error summary if there were failures
        failed = [r for r in state.step_results.values() if not r.success]
        if failed:
            parts.append(f"\n\nNote: {len(failed)} step(s) failed")

        return "\n".join(parts)

    def _format_output_detail(self, output: Dict[str, Any]) -> str:
        """Format output data with rich details for the LLM"""
        lines = []

        for key, value in output.items():
            if isinstance(value, list):
                if len(value) == 0:
                    lines.append(f"      {key}: (empty)")
                elif len(value) <= 10:
                    # Show items with their details
                    lines.append(f"      {key}:")
                    for item in value:
                        if isinstance(item, dict):
                            title = item.get('title') or item.get('name', 'Untitled')
                            item_type = item.get('type') or item.get('priority', '')
                            due = item.get('due_date', '')
                            status = item.get('status', '')

                            detail_parts = [f"        - {title}"]
                            if item_type:
                                detail_parts.append(f"[{item_type}]")
                            if status:
                                detail_parts.append(f"({status})")
                            if due:
                                detail_parts.append(f"due: {due}")
                            lines.append(" ".join(detail_parts))
                        else:
                            lines.append(f"        - {item}")
                else:
                    lines.append(f"      {key}: {len(value)} items")
            elif isinstance(value, dict):
                if 'title' in value or 'name' in value:
                    name = value.get('title') or value.get('name')
                    lines.append(f"      {key}: {name}")
                else:
                    # Nested dict - show key fields
                    useful_fields = {k: v for k, v in value.items()
                                   if k not in ('id', 'user_id') and v}
                    if useful_fields:
                        lines.append(f"      {key}: {useful_fields}")
            elif key not in ('id', 'user_id') and value is not None:
                lines.append(f"      {key}: {value}")

        return "\n".join(lines) if lines else "      (no details)"

    def _summarize_output(self, output: Dict[str, Any]) -> str:
        """Create brief summary of step output"""
        summaries = []

        for key, value in output.items():
            if isinstance(value, list):
                if len(value) > 0:
                    # Try to get meaningful info from first item
                    first = value[0]
                    if isinstance(first, dict):
                        name = first.get('title') or first.get('name')
                        if name and len(value) <= 3:
                            names = [
                                v.get('title') or v.get('name')
                                for v in value if isinstance(v, dict)
                            ]
                            summaries.append(f"{', '.join(filter(None, names))}")
                        else:
                            summaries.append(f"{len(value)} {key}")
                    else:
                        summaries.append(f"{len(value)} {key}")
            elif isinstance(value, dict):
                if 'id' in value and ('title' in value or 'name' in value):
                    name = value.get('title') or value.get('name')
                    summaries.append(f"{key}: {name}")
            elif value and key not in ('id', 'user_id'):
                summaries.append(f"{key}: {value}")

        return ", ".join(summaries[:3]) if summaries else ""

    def _fallback_response(self, state: ExecutionState) -> str:
        """Generate fallback response when LLM fails"""
        completed = state.get_completed_results()
        failed = state.get_failed_results()

        if completed and not failed:
            summaries = [r.summary for r in completed if r.summary]
            if summaries:
                return " ".join(summaries)
            return "Done! Your request has been completed."

        if failed and not completed:
            errors = [r.error for r in failed if r.error]
            if errors:
                return f"I encountered an issue: {errors[0]}"
            return "I wasn't able to complete your request. Please try again."

        if completed and failed:
            success_summaries = [r.summary for r in completed if r.summary]
            success_text = " ".join(success_summaries) if success_summaries else "Some actions completed"
            return f"{success_text}, but some steps failed. Please check the results."

        return "I processed your request."


class ResponseFormatter:
    """
    Helper for formatting specific types of responses.

    Provides consistent formatting for common result types.
    """

    @staticmethod
    def format_task_list(tasks: List[Dict], max_items: int = 5) -> str:
        """Format a list of tasks for display"""
        if not tasks:
            return "No tasks found."

        if len(tasks) <= max_items:
            lines = []
            for task in tasks:
                title = task.get('title', 'Untitled')
                status = task.get('status', '')
                priority = task.get('priority', '')
                due = task.get('due_date', '')

                parts = [f"- {title}"]
                if priority in ('high', 'urgent'):
                    parts.append(f"[{priority}]")
                if due:
                    parts.append(f"(due: {due})")

                lines.append(" ".join(parts))
            return "\n".join(lines)
        else:
            return f"Found {len(tasks)} tasks."

    @staticmethod
    def format_note_list(notes: List[Dict], max_items: int = 5) -> str:
        """Format a list of notes for display"""
        if not notes:
            return "No notes found."

        if len(notes) <= max_items:
            lines = []
            for note in notes:
                title = note.get('title', 'Untitled')
                note_type = note.get('type', 'standard')
                lines.append(f"- {title} ({note_type})")
            return "\n".join(lines)
        else:
            return f"Found {len(notes)} notes."

    @staticmethod
    def format_count(count: int, resource_type: str, qualifiers: str = "") -> str:
        """Format a count response"""
        if count == 0:
            return f"You have no {qualifiers} {resource_type}s.".replace("  ", " ")
        elif count == 1:
            return f"You have 1 {qualifiers} {resource_type}.".replace("  ", " ")
        else:
            return f"You have {count} {qualifiers} {resource_type}s.".replace("  ", " ")

    @staticmethod
    def format_created(resource_type: str, name: str, details: Dict = None) -> str:
        """Format a creation confirmation"""
        response = f"Created {resource_type} '{name}'"

        if details:
            extras = []
            if details.get('priority'):
                extras.append(f"{details['priority']} priority")
            if details.get('due_date'):
                extras.append(f"due {details['due_date']}")
            if details.get('container'):
                extras.append(f"in {details['container']}")

            if extras:
                response += f" with {', '.join(extras)}"

        return response + "."

    @staticmethod
    def format_moved(count: int, resource_type: str, destination: str) -> str:
        """Format a move confirmation"""
        if count == 1:
            return f"Moved 1 {resource_type} to {destination}."
        else:
            return f"Moved {count} {resource_type}s to {destination}."

    @staticmethod
    def format_updated(count: int, resource_type: str, changes: str = "") -> str:
        """Format an update confirmation"""
        if count == 1:
            base = f"Updated 1 {resource_type}"
        else:
            base = f"Updated {count} {resource_type}s"

        if changes:
            return f"{base}: {changes}."
        return f"{base}."
