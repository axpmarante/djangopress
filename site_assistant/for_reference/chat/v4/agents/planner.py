"""
Planner Agent for Chat V4

Analyzes user requests and creates execution plans.
Uses Sonnet model for intent understanding and plan generation.
"""

import logging
from typing import Optional, List, Dict, Any

from ..state import Plan, PlanStep
from ..llm import LLMClient, LLMResponse
from ..errors import PlanningError, ParseError

logger = logging.getLogger(__name__)


class PlannerAgent:
    """
    Creates execution plans from user requests.

    The Planner:
    - Analyzes user intent
    - Determines which agents and actions are needed
    - Creates a step-by-step execution plan
    - Handles plan revisions when execution fails

    Model: Sonnet (requires understanding intent and knowing all agent capabilities)
    """

    SYSTEM_PROMPT = """You are a Planning Agent for ZemoNotes, a personal knowledge management system.

Your ONLY job: Analyze the user request and create a sequence of agent goals.

## Available Agents

Each agent is a specialist that can interpret goals and decide what actions to take.

### tasks
Manages tasks - action items with due dates, priorities, and status.
Can: create tasks, update tasks, complete tasks, search for tasks, move tasks between containers, delete tasks.

### notes
Manages notes - captured knowledge, ideas, meeting notes.
Can: create notes, update notes, search notes, archive notes, move notes, link related notes, apply progressive summarization.

### projects
Manages projects - specific outcomes with deadlines.
Can: create projects, update projects, complete projects, archive projects, get project status with task progress.

### areas
Manages areas - ongoing responsibilities and life domains.
Can: create areas, update areas, archive areas, get area reviews with all related items.

### inbox
Manages the inbox - unorganized items awaiting processing.
Can: list inbox items, process items into containers, count inbox size, suggest organization.

### search
Cross-domain search across all content types.
Can: search globally across tasks, notes, projects, areas.

### calendar
Manages calendar events and deadlines.
Can: list events, find items by date range, show upcoming deadlines.

### journal
Manages daily journal entries.
Can: create entries, get entries for dates, search journal content.

### review
Performs periodic reviews (daily, weekly, monthly).
Can: generate review summaries, identify items needing attention.

### organize
Handles batch organization operations.
Can: move multiple items, apply tags, reorganize containers.

### tags
Manages tags across the system.
Can: list tags, apply tags, search by tags, suggest tags.

## Planning Guidelines

1. **One goal per step**: Each step should have a single, clear goal
2. **Use dependencies**: If step 2 needs results from step 1, set depends_on: [1]
3. **Be specific in goals**: Include all relevant details from the user's request
4. **Include context**: Pass along relevant context (names, dates, criteria) in the goal
5. **Let agents decide**: Don't specify HOW to accomplish the goal, just WHAT to accomplish

## Date Handling

When goals involve dates, include the actual date in the goal text:
- Today is provided in context - use it to calculate actual dates
- "end of month" → include the actual date like "due by 2025-12-31"
- "next Friday" → calculate and include "due by 2025-12-20"

## Output Format

Output ONLY valid JSON (no markdown, no explanation):
{
    "understanding": "what the user wants in your own words",
    "complexity": "simple|moderate|complex",
    "steps": [
        {
            "step_id": 1,
            "agent": "agent_name",
            "goal": "Natural language description of what this agent should accomplish",
            "depends_on": []
        }
    ],
    "reasoning": "why this sequence of agents makes sense"
}

## Examples

User: "Create a task to call John by end of month" (today is 2025-12-18)
{
    "understanding": "User wants to create a task to call John with a deadline at the end of December",
    "complexity": "simple",
    "steps": [
        {
            "step_id": 1,
            "agent": "tasks",
            "goal": "Create a task titled 'Call John' with a due date of 2025-12-31",
            "depends_on": []
        }
    ],
    "reasoning": "Single task creation, agent will determine appropriate priority"
}

User: "Move all overdue tasks to my Work project"
{
    "understanding": "User wants to find overdue tasks and move them to their Work project",
    "complexity": "moderate",
    "steps": [
        {
            "step_id": 1,
            "agent": "projects",
            "goal": "Find the project named 'Work' or similar",
            "depends_on": []
        },
        {
            "step_id": 2,
            "agent": "tasks",
            "goal": "Find all overdue incomplete tasks and move them to the Work project found in step 1",
            "depends_on": [1]
        }
    ],
    "reasoning": "Need to find project first, then tasks agent can find and move overdue tasks in one operation"
}

User: "Show me what I need to focus on today"
{
    "understanding": "User wants a summary of today's priorities and pending items",
    "complexity": "simple",
    "steps": [
        {
            "step_id": 1,
            "agent": "review",
            "goal": "Generate a daily focus summary showing tasks due today, overdue items, and any scheduled events",
            "depends_on": []
        }
    ],
    "reasoning": "Review agent can gather and synthesize today's priorities"
}

User: "Add a note about the meeting with Sarah to my Marketing project"
{
    "understanding": "User wants to create a meeting note in their Marketing project",
    "complexity": "moderate",
    "steps": [
        {
            "step_id": 1,
            "agent": "projects",
            "goal": "Find the project named 'Marketing' or similar",
            "depends_on": []
        },
        {
            "step_id": 2,
            "agent": "notes",
            "goal": "Create a meeting note about the meeting with Sarah in the Marketing project found in step 1",
            "depends_on": [1]
        }
    ],
    "reasoning": "Need to find project first, then create note in it"
}

Do NOT specify actions or parameters. Just describe the GOAL for each agent.
Do NOT execute anything. Do NOT talk to the user. Just create the plan."""

    def __init__(self, model_name: str = None):
        """Initialize the Planner with specified or default model"""
        self.llm = LLMClient(model_name=model_name or "claude")

    def create_plan(
        self,
        user_request: str,
        conversation_summary: str = "",
        resolved_references: Dict[str, List[int]] = None
    ) -> Plan:
        """
        Create an execution plan for the user request.

        Args:
            user_request: The user's request text
            conversation_summary: Summary of conversation context
            resolved_references: Pre-resolved entity references (e.g., {"task": [42]})

        Returns:
            Plan with steps to execute

        Raises:
            PlanningError: If planning fails
        """
        try:
            from datetime import date

            # Build context
            today = date.today()
            context_parts = [
                f"Today's date: {today.isoformat()} ({today.strftime('%A')})",
                f"User request: {user_request}"
            ]

            if conversation_summary:
                context_parts.append(f"\nConversation context: {conversation_summary}")

            if resolved_references:
                context_parts.append(f"\nResolved references: {resolved_references}")
                context_parts.append("(Use these IDs directly instead of searching)")

            context = "\n".join(context_parts)

            # Call LLM
            response = self.llm.chat_json([
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": context}
            ])

            # Parse response into Plan
            return self._parse_plan_response(response)

        except ParseError as e:
            logger.error(f"Failed to parse planner response: {e}")
            raise PlanningError(f"Failed to parse plan: {e}")
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            raise PlanningError(f"Planning failed: {e}")

    def revise_plan(
        self,
        original_request: str,
        original_plan: Plan,
        completed_results: List[Dict[str, Any]],
        failure_reason: str
    ) -> Plan:
        """
        Revise a plan based on execution results.

        Called when:
        - A step fails and needs replanning
        - Results reveal the plan needs adjustment
        - Max retries exceeded on a step

        Args:
            original_request: The original user request
            original_plan: The plan that was being executed
            completed_results: Results from completed steps
            failure_reason: Why revision is needed

        Returns:
            Revised Plan

        Raises:
            PlanningError: If replanning fails
        """
        try:
            # Build revision context
            context = f"""Original request: {original_request}

Original plan:
{self._format_plan_for_context(original_plan)}

Completed steps and results:
{self._format_results_for_context(completed_results)}

Reason for revision: {failure_reason}

Create a revised plan that:
1. Builds on successful steps (don't repeat them)
2. Addresses the failure reason
3. Completes the original request

Output the revised plan in the same JSON format."""

            response = self.llm.chat_json([
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": context}
            ])

            plan = self._parse_plan_response(response)
            plan.revision_count = original_plan.revision_count + 1
            plan.original_steps = original_plan.original_steps or original_plan.steps

            return plan

        except Exception as e:
            logger.error(f"Plan revision failed: {e}")
            raise PlanningError(f"Plan revision failed: {e}")

    def _parse_plan_response(self, response: Dict[str, Any]) -> Plan:
        """
        Parse LLM response into a Plan object.

        Args:
            response: Parsed JSON response from LLM

        Returns:
            Plan object

        Raises:
            PlanningError: If response is malformed
        """
        if not response.get('steps'):
            raise PlanningError("Plan has no steps")

        steps = []
        for step_data in response['steps']:
            # Validate required fields
            if 'step_id' not in step_data:
                raise PlanningError("Step missing step_id")

            # Support both 'agent' and 'agent_type' for flexibility
            agent_type = step_data.get('agent') or step_data.get('agent_type')
            if not agent_type:
                raise PlanningError(f"Step {step_data.get('step_id')} missing agent")

            if 'goal' not in step_data:
                raise PlanningError(f"Step {step_data.get('step_id')} missing goal")

            step = PlanStep(
                step_id=step_data['step_id'],
                agent_type=agent_type,
                goal=step_data['goal'],
                depends_on=step_data.get('depends_on', []),
            )
            steps.append(step)

        # Validate step IDs are unique
        step_ids = [s.step_id for s in steps]
        if len(step_ids) != len(set(step_ids)):
            raise PlanningError("Duplicate step IDs in plan")

        # Validate dependencies reference valid steps
        for step in steps:
            for dep_id in step.depends_on:
                if dep_id not in step_ids:
                    raise PlanningError(
                        f"Step {step.step_id} depends on non-existent step {dep_id}"
                    )
                if dep_id >= step.step_id:
                    raise PlanningError(
                        f"Step {step.step_id} cannot depend on later step {dep_id}"
                    )

        complexity = response.get('complexity', 'simple')
        if complexity not in ('simple', 'moderate', 'complex'):
            complexity = 'simple'

        return Plan(
            steps=steps,
            reasoning=response.get('reasoning', ''),
            estimated_complexity=complexity
        )

    def _format_plan_for_context(self, plan: Plan) -> str:
        """Format plan for inclusion in revision context"""
        lines = [f"Reasoning: {plan.reasoning}", "Steps:"]
        for step in plan.steps:
            status = f"[{step.status}]"
            lines.append(
                f"  {step.step_id}. {status} {step.agent_type}: {step.goal}"
            )
        return "\n".join(lines)

    def _format_results_for_context(self, results: List[Dict[str, Any]]) -> str:
        """Format step results for inclusion in revision context"""
        if not results:
            return "No steps completed yet."

        lines = []
        for result in results:
            status = "SUCCESS" if result.get('success') else "FAILED"
            lines.append(f"Step {result.get('step_id')}: {status}")
            if result.get('summary'):
                lines.append(f"  Summary: {result['summary']}")
            if result.get('error'):
                lines.append(f"  Error: {result['error']}")
            if result.get('output'):
                # Include relevant output data
                output = result['output']
                if isinstance(output, dict):
                    for key, value in list(output.items())[:3]:
                        if isinstance(value, list):
                            lines.append(f"  {key}: {len(value)} items")
                        else:
                            lines.append(f"  {key}: {value}")
        return "\n".join(lines)


class QuickPlanner:
    """
    Rule-based planner for simple, common requests.

    Bypasses LLM for obvious single-step operations,
    reducing latency and cost.
    """

    # Patterns for quick planning (regex pattern -> goal template)
    # Use {0} as placeholder for captured group
    QUICK_PATTERNS = {
        # Simple task creation
        r'^create\s+(?:a\s+)?task\s*[:\s]+(.+)$': {
            'agent': 'tasks',
            'goal_template': "Create a task titled '{0}'"
        },
        # Simple note creation
        r'^create\s+(?:a\s+)?note\s*[:\s]+(.+)$': {
            'agent': 'notes',
            'goal_template': "Create a note titled '{0}'"
        },
        # List inbox
        r'^(?:show|list|what\'?s?\s+in)\s+(?:my\s+)?inbox': {
            'agent': 'inbox',
            'goal_template': "List all items in the inbox including tasks and notes"
        },
        # Count tasks
        r'^how\s+many\s+tasks': {
            'agent': 'search',
            'goal_template': "Count the total number of tasks"
        },
        # Show overdue tasks
        r'^(?:show|list|what are)\s+(?:my\s+)?overdue\s+tasks': {
            'agent': 'tasks',
            'goal_template': "Find and list all overdue tasks"
        },
        # Show today's tasks
        r'^(?:show|list|what are)\s+(?:my\s+)?(?:tasks?\s+)?(?:for\s+)?today': {
            'agent': 'tasks',
            'goal_template': "Find and list all tasks due today"
        },
    }

    @classmethod
    def try_quick_plan(cls, request: str) -> Optional[Plan]:
        """
        Try to create a quick plan without LLM.

        Args:
            request: User request text

        Returns:
            Plan if quick planning succeeded, None otherwise
        """
        import re

        request_stripped = request.strip()

        for pattern, template in cls.QUICK_PATTERNS.items():
            # Use IGNORECASE to match case-insensitively but preserve original case in groups
            match = re.match(pattern, request_stripped, re.IGNORECASE)
            if match:
                goal = template['goal_template']

                # Fill in captured groups
                if match.groups():
                    goal = goal.format(*[g.strip() for g in match.groups()])

                step = PlanStep(
                    step_id=1,
                    agent_type=template['agent'],
                    goal=goal,
                )

                return Plan(
                    steps=[step],
                    reasoning="Quick plan - single obvious action",
                    estimated_complexity="simple"
                )

        return None
