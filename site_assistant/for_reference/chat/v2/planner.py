"""
Chat V2 Planner

Creates execution plans for AGENTIC requests.

The planner:
1. Takes a user message and detected intent/entities
2. Uses LLM to generate a step-by-step plan (or uses heuristics for simple cases)
3. Creates PlanStep objects in the database
4. Updates AgentMemory with the plan state

Key design decisions:
- Plans are kept minimal (usually 1-3 steps)
- Simple requests use pattern matching instead of LLM
- Complex requests use LLM to generate steps
- All plans are persisted for recovery and audit
"""

import json
import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

from django.db import transaction

from .models import AgentMemory, PlanStep
from .memory import MemoryState, RouteType
from .prompts import build_user_context


@dataclass
class PlanResult:
    """Result from plan creation."""
    success: bool
    goal: str
    steps: List[Dict[str, Any]]
    error: str = ""
    used_llm: bool = False


class Planner:
    """
    Creates execution plans for AGENTIC requests.

    Usage:
        planner = Planner(user)
        result = planner.create_plan(
            message="Create a task in Finance project",
            intent="create_task",
            entities={"project": "Finance"}
        )

        if result.success:
            planner.persist_plan(memory, result)
    """

    def __init__(self, user, llm_client=None):
        self.user = user
        self.llm_client = llm_client

    def create_plan(
        self,
        message: str,
        intent: str = "",
        entities: Dict[str, Any] = None,
        use_llm: bool = True
    ) -> PlanResult:
        """
        Create an execution plan for a user request.

        Args:
            message: The user's original message
            intent: Detected intent from router (optional)
            entities: Detected entities from router (optional)
            use_llm: Whether to use LLM for complex planning

        Returns:
            PlanResult with goal and steps
        """
        entities = entities or {}

        # Try heuristic planning first (faster, no LLM needed)
        heuristic_plan = self._heuristic_plan(message, intent, entities)
        if heuristic_plan:
            return heuristic_plan

        # Fall back to LLM planning for complex requests
        if use_llm and self.llm_client:
            return self._llm_plan(message, intent, entities)

        # Can't create a plan without LLM for complex requests
        return PlanResult(
            success=False,
            goal="",
            steps=[],
            error="Unable to create plan: request too complex for heuristics and no LLM available"
        )

    def _heuristic_plan(
        self,
        message: str,
        intent: str,
        entities: Dict[str, Any]
    ) -> Optional[PlanResult]:
        """
        Create plan using pattern matching for simple requests.

        Returns None if the request is too complex for heuristics.
        """
        message_lower = message.lower()

        # Pattern: Create task (with optional project/area)
        if intent == "create_task" or re.search(
            r'\b(create|add|new|make|criar|nova)\b.*\b(task|tarefa)\b', message_lower
        ):
            return self._plan_create_task(message, entities)

        # Pattern: Create note
        if intent == "create_note" or re.search(
            r'\b(create|add|new|make|criar|nova)\b.*\b(note|nota)\b', message_lower
        ) or any(p in message_lower for p in ["capture", "save this"]):
            return self._plan_create_note(message, entities)

        # Pattern: Search
        if intent == "search" or any(p in message_lower for p in [
            "search", "find", "look for", "buscar", "procurar", "show me", "list"
        ]):
            return self._plan_search(message, entities)

        # Pattern: Complete task
        if intent == "complete_task" or re.search(
            r'\b(complete|finish|done|mark.*done|concluir|feito)\b.*\b(task|tarefa)?\b', message_lower
        ):
            return self._plan_complete_task(message, entities)

        # Pattern: Move note/task
        if intent == "move" or any(p in message_lower for p in [
            "move to", "put in", "mover para", "colocar em"
        ]):
            return self._plan_move(message, entities)

        # Too complex for heuristics
        return None

    def _plan_create_task(
        self,
        message: str,
        entities: Dict[str, Any]
    ) -> PlanResult:
        """Create plan for task creation."""
        steps = []

        # Extract title from message
        title = self._extract_task_title(message)

        # If project is specified by name, need to search first
        project_name = entities.get("project")
        area_name = entities.get("area")

        if project_name:
            # Step 1: Find project
            steps.append({
                "description": f"Find project '{project_name}'",
                "tool": "search_tool",
                "action": "search",
                "resource_type": "project",
                "params": {"query": project_name, "limit": 1}
            })
            # Step 2: Create task in project
            steps.append({
                "description": f"Create task '{title}' in found project",
                "tool": "execute_tool",
                "action": "create",
                "resource_type": "task",
                "params": {
                    "title": title,
                    "container_type": "project",
                    "container_id": "${step_1_result.id}",  # Placeholder
                    "priority": entities.get("priority", "medium")
                }
            })
        elif area_name:
            # Step 1: Find area
            steps.append({
                "description": f"Find area '{area_name}'",
                "tool": "search_tool",
                "action": "search",
                "resource_type": "area",
                "params": {"query": area_name, "limit": 1}
            })
            # Step 2: Create task in area
            steps.append({
                "description": f"Create task '{title}' in found area",
                "tool": "execute_tool",
                "action": "create",
                "resource_type": "task",
                "params": {
                    "title": title,
                    "container_type": "area",
                    "container_id": "${step_1_result.id}",
                    "priority": entities.get("priority", "medium")
                }
            })
        else:
            # Single step: Create task in inbox
            steps.append({
                "description": f"Create task '{title}'",
                "tool": "execute_tool",
                "action": "create",
                "resource_type": "task",
                "params": {
                    "title": title,
                    "priority": entities.get("priority", "medium")
                }
            })

            # Add due date if mentioned
            if entities.get("due_date"):
                steps[-1]["params"]["due_date"] = entities["due_date"]

        return PlanResult(
            success=True,
            goal=f"Create task: {title}",
            steps=steps,
            used_llm=False
        )

    def _plan_create_note(
        self,
        message: str,
        entities: Dict[str, Any]
    ) -> PlanResult:
        """Create plan for note creation."""
        steps = []

        title = entities.get("title") or self._extract_note_title(message)
        content = entities.get("content", "")

        project_name = entities.get("project")
        area_name = entities.get("area")

        if project_name:
            steps.append({
                "description": f"Find project '{project_name}'",
                "tool": "search_tool",
                "action": "search",
                "resource_type": "project",
                "params": {"query": project_name, "limit": 1}
            })
            steps.append({
                "description": f"Create note '{title}' in found project",
                "tool": "execute_tool",
                "action": "create",
                "resource_type": "note",
                "params": {
                    "title": title,
                    "content": content,
                    "container_type": "project",
                    "container_id": "${step_1_result.id}"
                }
            })
        elif area_name:
            steps.append({
                "description": f"Find area '{area_name}'",
                "tool": "search_tool",
                "action": "search",
                "resource_type": "area",
                "params": {"query": area_name, "limit": 1}
            })
            steps.append({
                "description": f"Create note '{title}' in found area",
                "tool": "execute_tool",
                "action": "create",
                "resource_type": "note",
                "params": {
                    "title": title,
                    "content": content,
                    "container_type": "area",
                    "container_id": "${step_1_result.id}"
                }
            })
        else:
            steps.append({
                "description": f"Create note '{title}'",
                "tool": "execute_tool",
                "action": "create",
                "resource_type": "note",
                "params": {
                    "title": title,
                    "content": content
                }
            })

        return PlanResult(
            success=True,
            goal=f"Create note: {title}",
            steps=steps,
            used_llm=False
        )

    def _plan_search(
        self,
        message: str,
        entities: Dict[str, Any]
    ) -> PlanResult:
        """Create plan for search operations."""
        # Determine what to search
        resource_type = entities.get("resource_type", "note")
        query = entities.get("query") or self._extract_search_query(message)

        # Detect resource type from message
        message_lower = message.lower()
        if any(w in message_lower for w in ["task", "tarefa", "todo"]):
            resource_type = "task"
        elif any(w in message_lower for w in ["project", "projeto"]):
            resource_type = "project"
        elif any(w in message_lower for w in ["area", "área"]):
            resource_type = "area"

        steps = [{
            "description": f"Search {resource_type}s for '{query}'",
            "tool": "search_tool",
            "action": "search",
            "resource_type": resource_type,
            "params": {"query": query, "limit": 10}
        }]

        return PlanResult(
            success=True,
            goal=f"Search {resource_type}s: {query}",
            steps=steps,
            used_llm=False
        )

    def _plan_complete_task(
        self,
        message: str,
        entities: Dict[str, Any]
    ) -> PlanResult:
        """Create plan for completing a task."""
        task_id = entities.get("task_id")
        task_name = entities.get("task") or self._extract_task_reference(message)

        steps = []

        if task_id:
            # Direct completion by ID
            steps.append({
                "description": f"Complete task #{task_id}",
                "tool": "execute_tool",
                "action": "complete",
                "resource_type": "task",
                "params": {"id": task_id}
            })
        elif task_name:
            # Search first, then complete
            steps.append({
                "description": f"Find task '{task_name}'",
                "tool": "search_tool",
                "action": "search",
                "resource_type": "task",
                "params": {"query": task_name, "limit": 1}
            })
            steps.append({
                "description": "Complete the found task",
                "tool": "execute_tool",
                "action": "complete",
                "resource_type": "task",
                "params": {"id": "${step_1_result.id}"}
            })
        else:
            return PlanResult(
                success=False,
                goal="Complete task",
                steps=[],
                error="Could not identify which task to complete"
            )

        return PlanResult(
            success=True,
            goal=f"Complete task: {task_name or task_id}",
            steps=steps,
            used_llm=False
        )

    def _plan_move(
        self,
        message: str,
        entities: Dict[str, Any]
    ) -> PlanResult:
        """Create plan for moving items."""
        # This is more complex, might need LLM
        item_name = entities.get("item")
        destination = entities.get("destination")

        if not item_name or not destination:
            return None  # Let LLM handle it

        steps = [
            {
                "description": f"Find item '{item_name}'",
                "tool": "search_tool",
                "action": "search",
                "resource_type": "note",
                "params": {"query": item_name, "limit": 1}
            },
            {
                "description": f"Find destination '{destination}'",
                "tool": "search_tool",
                "action": "search",
                "resource_type": "project",  # Could be area too
                "params": {"query": destination, "limit": 1}
            },
            {
                "description": f"Move item to destination",
                "tool": "execute_tool",
                "action": "move",
                "resource_type": "note",
                "params": {
                    "id": "${step_1_result.id}",
                    "container_type": "project",
                    "container_id": "${step_2_result.id}"
                }
            }
        ]

        return PlanResult(
            success=True,
            goal=f"Move '{item_name}' to '{destination}'",
            steps=steps,
            used_llm=False
        )

    def _llm_plan(
        self,
        message: str,
        intent: str,
        entities: Dict[str, Any]
    ) -> PlanResult:
        """
        Use LLM to create a plan for complex requests.
        """
        try:
            # Build context
            user_context = build_user_context(self.user, include_para_summary=True)

            # Build planner prompt inline (was build_planner_prompt)
            entities_str = f"Detected entities: {entities}" if entities else ""
            prompt = f"""Create an execution plan for this request.

{user_context}

User request: "{message}"
{f"Detected intent: {intent}" if intent else ""}
{entities_str}

Respond with JSON:
{{
  "goal": "Brief description of what we're trying to accomplish",
  "steps": [
    {{
      "description": "Human-readable step description",
      "tool": "search_tool or execute_tool",
      "action": "search, create, update, etc.",
      "resource_type": "note, task, project, area",
      "params": {{}}
    }}
  ]
}}"""

            # Call LLM using get_completion interface
            messages = [
                {"role": "system", "content": "You are a task planner. Generate execution plans in JSON format."},
                {"role": "user", "content": prompt}
            ]
            response = self.llm_client.get_completion(messages=messages, tool_name="gemini-flash")
            response_text = response.choices[0].message.content

            # Parse response
            plan = self._parse_llm_plan(response_text)

            if plan:
                return PlanResult(
                    success=True,
                    goal=plan.get("goal", message),
                    steps=plan.get("steps", []),
                    used_llm=True
                )
            else:
                return PlanResult(
                    success=False,
                    goal="",
                    steps=[],
                    error="Failed to parse LLM plan response"
                )

        except Exception as e:
            return PlanResult(
                success=False,
                goal="",
                steps=[],
                error=f"LLM planning error: {str(e)}"
            )

    def _parse_llm_plan(self, response: str) -> Optional[Dict]:
        """Parse LLM response into plan structure."""
        # Try to find JSON in response
        json_patterns = [
            r'```json\s*(.*?)\s*```',
            r'```\s*(.*?)\s*```',
            r'(\{.*\})',
        ]

        for pattern in json_patterns:
            match = re.search(pattern, response, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1).strip())
                except json.JSONDecodeError:
                    continue

        return None

    @transaction.atomic
    def persist_plan(
        self,
        memory: AgentMemory,
        plan_result: PlanResult
    ) -> List[PlanStep]:
        """
        Persist a plan to the database.

        Creates PlanStep objects and updates AgentMemory state.

        Args:
            memory: The AgentMemory to attach the plan to
            plan_result: The plan to persist

        Returns:
            List of created PlanStep objects
        """
        # Clear any existing steps
        memory.steps.all().delete()

        # Create new steps
        db_steps = []
        for i, step in enumerate(plan_result.steps, 1):
            db_step = PlanStep.objects.create(
                memory=memory,
                order=i,
                description=step.get("description", f"Step {i}"),
                tool=step.get("tool", "search_tool"),
                action=step.get("action", "search"),
                resource_type=step.get("resource_type", ""),
                params=step.get("params", {}),
                status="pending"
            )
            db_steps.append(db_step)

        # Update memory state
        memory.task_goal = plan_result.goal
        memory.route_type = RouteType.AGENTIC.value
        memory.current_stage = 1
        memory.total_stages = len(plan_result.steps)
        memory.plan_state = {
            "steps": plan_result.steps,
            "used_llm": plan_result.used_llm
        }
        memory.stage_results = {}
        memory.pending_clarification = {}
        memory.save()

        return db_steps

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _extract_task_title(self, message: str) -> str:
        """Extract task title from message."""
        # Remove common prefixes
        patterns = [
            r"create (?:a )?task(?: called| named)?:?\s*['\"]?(.+?)['\"]?$",
            r"add (?:a )?task:?\s*['\"]?(.+?)['\"]?$",
            r"new task:?\s*['\"]?(.+?)['\"]?$",
            r"criar tarefa:?\s*['\"]?(.+?)['\"]?$",
            r"nova tarefa:?\s*['\"]?(.+?)['\"]?$",
        ]

        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                title = match.group(1).strip()
                # Remove container mentions
                title = re.sub(r"\s*(in|to|em|para)\s+\w+\s*(project|area|projeto|área).*$", "", title, flags=re.IGNORECASE)
                return title

        # Fallback: use everything after "task"
        parts = re.split(r'\btask\b', message, flags=re.IGNORECASE)
        if len(parts) > 1:
            return parts[1].strip().strip('"\'')

        return message.strip()[:100]  # Use first 100 chars

    def _extract_note_title(self, message: str) -> str:
        """Extract note title from message."""
        patterns = [
            r"create (?:a )?note(?: called| named)?:?\s*['\"]?(.+?)['\"]?$",
            r"add (?:a )?note:?\s*['\"]?(.+?)['\"]?$",
            r"new note:?\s*['\"]?(.+?)['\"]?$",
            r"criar nota:?\s*['\"]?(.+?)['\"]?$",
            r"nova nota:?\s*['\"]?(.+?)['\"]?$",
            r"capture:?\s*['\"]?(.+?)['\"]?$",
        ]

        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return "Quick Note"

    def _extract_search_query(self, message: str) -> str:
        """Extract search query from message."""
        patterns = [
            r"(?:search|find|look for|buscar|procurar)\s+(?:for\s+)?['\"]?(.+?)['\"]?$",
            r"(?:show|list)\s+(?:me\s+)?(?:all\s+)?['\"]?(.+?)['\"]?$",
        ]

        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        # Fallback: use the whole message after common words
        clean = re.sub(r"^(search|find|show|list|look for|buscar|procurar)\s*(for\s*|me\s*)?", "", message, flags=re.IGNORECASE)
        return clean.strip() or "recent"

    def _extract_task_reference(self, message: str) -> str:
        """Extract task reference from completion message."""
        patterns = [
            r"complete (?:the )?task ['\"]?(.+?)['\"]?$",   # complete task X
            r"complete (?:the )?['\"]?(.+?)['\"]? task",    # complete X task
            r"mark ['\"]?(.+?)['\"]? (?:as )?done",
            r"finish ['\"]?(.+?)['\"]?$",
            r"concluir ['\"]?(.+?)['\"]?$",
        ]

        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return ""


def create_plan(
    user,
    message: str,
    intent: str = "",
    entities: Dict[str, Any] = None,
    llm_client=None
) -> PlanResult:
    """
    Convenience function to create a plan.

    Usage:
        result = create_plan(user, "Create a task in Finance project")
        if result.success:
            print(f"Goal: {result.goal}")
            for step in result.steps:
                print(f"  - {step['description']}")
    """
    planner = Planner(user, llm_client)
    return planner.create_plan(message, intent, entities)
