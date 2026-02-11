"""
Chat V2 Context Builder - Layer 1

Dynamic context assembly based on conversation state.
Builds minimal, relevant context to reduce token usage.

Key principles:
- First message: Full PARA summary (user needs orientation)
- Subsequent messages: Minimal context based on current task
- Active plan: Only step-relevant context
- Always include: User info, memory state, recent history
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, TYPE_CHECKING
from django.utils import timezone

from .memory import MemoryState, RouteType
from .router import RouterResult

if TYPE_CHECKING:
    from chat.models import Conversation, Message


@dataclass
class AssembledContext:
    """Result from context assembly."""

    # The assembled prompt sections
    system_prompt: str
    user_context: str
    memory_context: str
    history: List[Dict[str, str]]

    # Metadata
    is_first_message: bool
    route_type: Optional[RouteType]
    token_estimate: int
    context_sources: List[str]  # What was included (for debugging)

    def to_messages(self, user_message: str = "") -> List[Dict[str, str]]:
        """
        Convert to LLM message format.

        Returns list of messages ready for LLM API.
        """
        messages = []

        # System message with all context
        system_content = self.system_prompt
        if self.user_context:
            system_content += f"\n\n{self.user_context}"
        if self.memory_context:
            system_content += f"\n\n{self.memory_context}"

        messages.append({
            'role': 'system',
            'content': system_content
        })

        # Add conversation history
        for msg in self.history:
            messages.append(msg)

        # Add current user message if provided
        if user_message:
            messages.append({
                'role': 'user',
                'content': user_message
            })

        return messages


class DynamicContextBuilder:
    """
    Layer 1: Dynamic Context Assembly

    Builds context based on:
    - Is this the first message? (need full orientation)
    - What's the route type? (DIRECT needs less, AGENTIC needs more)
    - Is there an active plan? (only include step-relevant data)
    - What's in memory? (learnings, failures, progress)

    Token budget targets:
    - DIRECT: ~400-600 tokens
    - AGENTIC (first): ~800-1200 tokens
    - AGENTIC (continuing): ~500-800 tokens
    - CLARIFY: ~300-500 tokens
    """

    # Maximum messages to include in history
    MAX_HISTORY_MESSAGES = 10

    # Maximum characters per history message (truncate long ones)
    MAX_MESSAGE_LENGTH = 500

    def __init__(
        self,
        user,
        conversation: 'Conversation',
        memory_state: MemoryState
    ):
        self.user = user
        self.conversation = conversation
        self.memory = memory_state
        self._para_cache: Optional[Dict] = None

    def build(
        self,
        route_result: Optional[RouterResult] = None,
        include_tools: bool = True
    ) -> AssembledContext:
        """
        Build context based on current state.

        Args:
            route_result: Result from router classification
            include_tools: Whether to include tool definitions

        Returns:
            AssembledContext with all sections assembled
        """
        is_first = self._is_first_message()
        route_type = route_result.route_type if route_result else None

        context_sources = []

        # 1. Build system prompt
        system_prompt = self._build_system_prompt(
            route_type=route_type,
            include_tools=include_tools
        )
        context_sources.append('system_prompt')

        # 2. Build user context (PARA data)
        user_context = self._build_user_context(
            is_first=is_first,
            route_type=route_type,
            route_result=route_result
        )
        if user_context:
            context_sources.append('user_context')

        # 3. Build memory context
        memory_context = self._build_memory_context()
        if memory_context:
            context_sources.append('memory_context')

        # 4. Get relevant history
        history = self._get_relevant_history(route_type)
        if history:
            context_sources.append(f'history ({len(history)} messages)')

        # 5. Estimate tokens
        token_estimate = self._estimate_tokens(
            system_prompt, user_context, memory_context, history
        )

        return AssembledContext(
            system_prompt=system_prompt,
            user_context=user_context,
            memory_context=memory_context,
            history=history,
            is_first_message=is_first,
            route_type=route_type,
            token_estimate=token_estimate,
            context_sources=context_sources
        )

    def build_for_step(
        self,
        step_index: int,
        previous_results: Dict[str, Any] = None
    ) -> AssembledContext:
        """
        Build minimal context for executing a specific plan step.

        Used during AGENTIC plan execution. Only includes:
        - Minimal system prompt with tools
        - Step-relevant PARA context
        - Previous step results
        - No full history (already processed)
        """
        context_sources = ['step_context']

        # Minimal system prompt with tools
        system_prompt = self._build_system_prompt(
            route_type=RouteType.AGENTIC,
            include_tools=True,
            minimal=True
        )

        # Get current step info
        current_step = self.memory.get_current_step()

        # Build step-relevant user context
        user_context = self._build_step_context(current_step, previous_results)
        if user_context:
            context_sources.append('step_user_context')

        # Memory context (progress, learnings)
        memory_context = self._build_memory_context()
        if memory_context:
            context_sources.append('memory_context')

        # No history for step execution - we already know the goal
        history = []

        token_estimate = self._estimate_tokens(
            system_prompt, user_context, memory_context, history
        )

        return AssembledContext(
            system_prompt=system_prompt,
            user_context=user_context,
            memory_context=memory_context,
            history=history,
            is_first_message=False,
            route_type=RouteType.AGENTIC,
            token_estimate=token_estimate,
            context_sources=context_sources
        )

    # =========================================================================
    # Private: System Prompt Building
    # =========================================================================

    def _build_system_prompt(
        self,
        route_type: Optional[RouteType],
        include_tools: bool = True,
        minimal: bool = False
    ) -> str:
        """Build system prompt based on route type."""
        from .prompts import (
            SYSTEM_PROMPT_BASE,
            TOOL_DEFINITIONS,
            RESPONSE_FORMAT
        )

        if minimal:
            # For step execution - just base + tools
            prompt = SYSTEM_PROMPT_BASE
            if include_tools:
                prompt += f"\n\n{TOOL_DEFINITIONS}"
            return prompt

        if route_type == RouteType.DIRECT:
            # DIRECT: Minimal prompt, no tools
            return SYSTEM_PROMPT_BASE

        elif route_type == RouteType.CLARIFY:
            # CLARIFY: Minimal prompt focused on asking questions
            return f"""{SYSTEM_PROMPT_BASE}

Your task is to ask a clarifying question to understand what the user wants.
Be specific and provide options when possible."""

        else:  # AGENTIC or unknown
            # Full prompt with tools
            prompt = SYSTEM_PROMPT_BASE
            if include_tools:
                prompt += f"\n\n{TOOL_DEFINITIONS}\n\n{RESPONSE_FORMAT}"
            return prompt

    # =========================================================================
    # Private: User Context Building
    # =========================================================================

    def _build_user_context(
        self,
        is_first: bool,
        route_type: Optional[RouteType],
        route_result: Optional[RouterResult] = None
    ) -> str:
        """Build user context section based on state."""

        # Check if conversation is scoped to a specific project/area
        # If so, include rich context for brainstorming
        is_scoped = (
            self.conversation.context_type in ['project', 'area'] and
            self.conversation.context_id
        )

        # For DIRECT routes OR scoped conversations, use V1's rich context
        # so the LLM has all the data it needs for brainstorming
        if route_type == RouteType.DIRECT or is_scoped:
            from chat.context import ContextBuilder
            builder = ContextBuilder(self.user, self.conversation)
            return builder.format_for_system_prompt()

        lines = [
            "## User Context",
            f"User: {self.user.first_name or self.user.username}",
            f"Date: {timezone.now().strftime('%Y-%m-%d')} ({timezone.now().strftime('%A')})",
            f"Time: {timezone.now().strftime('%H:%M')}",
        ]

        # Determine how much PARA context to include
        if is_first or not self.memory.has_active_task():
            # First message or new request: Full PARA summary
            lines.append("")
            lines.append(self._build_para_summary())

        elif self.memory.is_plan_active():
            # Active plan: Only relevant context for current step
            step = self.memory.get_current_step()
            if step:
                step_context = self._get_step_relevant_para(step, route_result)
                if step_context:
                    lines.append("")
                    lines.append(step_context)

        return "\n".join(lines)

    def _build_para_summary(self) -> str:
        """Build full PARA system summary."""
        para = self._get_para_data()

        lines = ["## Your PARA System"]

        # Areas
        areas = para.get('areas', [])
        if areas:
            lines.append(f"\n### Areas ({len(areas)})")
            for area in areas[:8]:  # Limit to 8
                projects_count = area.get('projects_count', 0)
                lines.append(f"- **{area['name']}** (ID: {area['id']}) - {projects_count} projects")

        # Active Projects
        projects = para.get('projects', [])
        if projects:
            lines.append(f"\n### Active Projects ({len(projects)})")
            for proj in projects[:8]:  # Limit to 8
                deadline = f" | Due: {proj['deadline']}" if proj.get('deadline') else ""
                area = f" [{proj.get('area_name', 'No area')}]"
                lines.append(f"- **{proj['name']}** (ID: {proj['id']}){area}{deadline}")

        # Task Summary
        tasks = para.get('tasks_summary', {})
        if tasks.get('total', 0) > 0:
            lines.append("\n### Tasks Summary")
            lines.append(f"- Total: {tasks.get('total', 0)} | "
                        f"Overdue: {tasks.get('overdue', 0)} | "
                        f"Due Today: {tasks.get('due_today', 0)} | "
                        f"In Progress: {tasks.get('in_progress', 0)}")

        # Inbox
        inbox_count = para.get('inbox_count', 0)
        if inbox_count > 0:
            lines.append(f"\n### Inbox")
            lines.append(f"- {inbox_count} items waiting to be processed")

        return "\n".join(lines)

    def _get_step_relevant_para(
        self,
        step: Dict[str, Any],
        route_result: Optional[RouterResult] = None
    ) -> str:
        """Get only PARA context relevant to current step."""
        lines = ["## Relevant Context"]

        resource_type = step.get('resource_type', '')
        action = step.get('action', '')
        params = step.get('params', {})

        # If step references a specific container, load that
        container_type = params.get('container_type')
        container_id = params.get('container_id')
        container_name = params.get('container_name')

        # Also check route_result entities
        if route_result and route_result.detected_entities:
            entities = route_result.detected_entities
            container_name = container_name or entities.get('container_name')
            container_type = container_type or entities.get('container_type')

        if container_type == 'project':
            project_context = self._get_project_context(container_id, container_name)
            if project_context:
                lines.append(project_context)
        elif container_type == 'area':
            area_context = self._get_area_context(container_id, container_name)
            if area_context:
                lines.append(area_context)

        # If searching/listing, include summary of what exists
        if action in ['search', 'list'] and not container_type:
            para = self._get_para_data()
            if resource_type == 'project':
                projects = para.get('projects', [])
                if projects:
                    lines.append(f"Available projects: {len(projects)}")
            elif resource_type == 'area':
                areas = para.get('areas', [])
                if areas:
                    lines.append(f"Available areas: {len(areas)}")

        if len(lines) > 1:
            return "\n".join(lines)
        return ""

    def _get_project_context(
        self,
        project_id: Optional[int] = None,
        project_name: Optional[str] = None
    ) -> str:
        """Get context for a specific project."""
        from para.models import Project

        try:
            if project_id:
                project = Project.objects.get(id=project_id, user=self.user)
            elif project_name:
                project = Project.objects.filter(
                    user=self.user,
                    name__icontains=project_name
                ).first()
            else:
                return ""

            if not project:
                return ""

            lines = [
                f"### Project: {project.name}",
                f"- ID: {project.id}",
                f"- Area: {project.area.name}",
                f"- Status: {project.status}",
            ]

            if project.deadline:
                lines.append(f"- Deadline: {project.deadline.strftime('%Y-%m-%d')}")

            # Get task counts
            task_counts = project.get_task_counts()
            if task_counts.get('total', 0) > 0:
                lines.append(f"- Tasks: {task_counts.get('completed', 0)}/{task_counts.get('total', 0)} completed")

            return "\n".join(lines)

        except Exception:
            return ""

    def _get_area_context(
        self,
        area_id: Optional[int] = None,
        area_name: Optional[str] = None
    ) -> str:
        """Get context for a specific area."""
        from para.models import Area

        try:
            if area_id:
                area = Area.objects.get(id=area_id, user=self.user)
            elif area_name:
                area = Area.objects.filter(
                    user=self.user,
                    name__icontains=area_name
                ).first()
            else:
                return ""

            if not area:
                return ""

            lines = [
                f"### Area: {area.name}",
                f"- ID: {area.id}",
                f"- Active Projects: {area.get_active_projects_count()}",
            ]

            if area.description:
                lines.append(f"- Description: {area.description[:100]}")

            return "\n".join(lines)

        except Exception:
            return ""

    def _build_step_context(
        self,
        step: Optional[Dict[str, Any]],
        previous_results: Optional[Dict[str, Any]]
    ) -> str:
        """Build context specifically for step execution."""
        lines = []

        # User info
        lines.append(f"User: {self.user.first_name or self.user.username}")
        lines.append(f"Date: {timezone.now().strftime('%Y-%m-%d')}")

        # Previous step results (if any)
        if previous_results:
            lines.append("\n## Previous Step Results")
            for stage_num, result in previous_results.items():
                summary = result.get('summary', str(result))[:200]
                lines.append(f"Step {stage_num}: {summary}")

                # Include data if it contains IDs we might need
                data = result.get('data', {})
                if isinstance(data, dict):
                    if data.get('id'):
                        lines.append(f"  → Created/Found ID: {data.get('id')}")
                    if data.get('items'):
                        lines.append(f"  → Found {len(data.get('items', []))} items")

        # Current step info
        if step:
            lines.append(f"\n## Current Step")
            lines.append(f"Action: {step.get('tool', 'unknown')}.{step.get('action', 'unknown')}")
            lines.append(f"Description: {step.get('description', 'Execute step')}")

            params = step.get('params', {})
            if params:
                lines.append(f"Parameters: {params}")

        return "\n".join(lines)

    # =========================================================================
    # Private: Memory Context
    # =========================================================================

    def _build_memory_context(self) -> str:
        """Build memory context from MemoryState."""
        return self.memory.to_context_string()

    # =========================================================================
    # Private: History Management
    # =========================================================================

    def _get_relevant_history(
        self,
        route_type: Optional[RouteType]
    ) -> List[Dict[str, str]]:
        """Get relevant conversation history."""

        # For step execution, we don't need history
        if self.memory.is_plan_active() and self.memory.current_stage > 1:
            return []

        messages = list(
            self.conversation.messages
            .exclude(role='system')
            .order_by('-created_at')[:self.MAX_HISTORY_MESSAGES]
        )
        messages.reverse()

        history = []
        for msg in messages:
            content = msg.content

            # Truncate long messages
            if len(content) > self.MAX_MESSAGE_LENGTH:
                content = content[:self.MAX_MESSAGE_LENGTH] + "... [truncated]"

            history.append({
                'role': msg.role,
                'content': content
            })

        return history

    # =========================================================================
    # Private: Helpers
    # =========================================================================

    def _is_first_message(self) -> bool:
        """Check if this is the first message in the conversation."""
        return self.conversation.messages.count() == 0

    def _get_para_data(self) -> Dict[str, Any]:
        """Get PARA data (cached)."""
        if self._para_cache is None:
            self._para_cache = self._fetch_para_data()
        return self._para_cache

    def _fetch_para_data(self) -> Dict[str, Any]:
        """Fetch PARA summary data from database."""
        from para.models import Area, Project
        from notes.models import Note
        from tasks.models import Task

        # Areas with project counts (root areas only)
        areas = []
        for area in Area.objects.filter(
            user=self.user,
            is_active=True,
            parent__isnull=True  # Root areas only
        )[:10]:
            areas.append({
                'id': area.id,
                'name': area.name,
                'full_path': area.get_full_path(),
                'projects_count': area.get_active_projects_count(),
                'sub_areas_count': area.children.filter(is_active=True).count(),
            })

        # Active projects
        projects = []
        for proj in Project.objects.filter(
            user=self.user,
            status='active'
        ).select_related('area')[:10]:
            projects.append({
                'id': proj.id,
                'name': proj.name,
                'area_name': proj.area.name if proj.area else None,
                'area_full_path': proj.area.get_full_path() if proj.area else None,
                'deadline': proj.deadline.strftime('%Y-%m-%d') if proj.deadline else None,
            })

        # Task summary from Task model
        today = timezone.now().date()
        tasks = Task.objects.filter(
            user=self.user,
            is_archived=False
        )

        tasks_summary = {
            'total': tasks.exclude(status='done').count(),
            'overdue': tasks.filter(
                due_date__date__lt=today,
                status__in=['todo', 'in_progress', 'waiting']
            ).count(),
            'due_today': tasks.filter(
                due_date__date=today,
                status__in=['todo', 'in_progress', 'waiting']
            ).count(),
            'in_progress': tasks.filter(status='in_progress').count(),
            'waiting': tasks.filter(status='waiting').count(),
        }

        # Inbox count (notes in inbox)
        inbox_count = Note.objects.filter(
            user=self.user,
            container_type='inbox',
            is_archived=False
        ).count()

        return {
            'areas': areas,
            'projects': projects,
            'tasks_summary': tasks_summary,
            'inbox_count': inbox_count,
        }

    def _estimate_tokens(
        self,
        system_prompt: str,
        user_context: str,
        memory_context: str,
        history: List[Dict[str, str]]
    ) -> int:
        """
        Rough token estimation.

        Uses ~4 characters per token as approximation.
        """
        total_chars = len(system_prompt) + len(user_context) + len(memory_context)

        for msg in history:
            total_chars += len(msg.get('content', ''))

        return total_chars // 4


def build_context(
    user,
    conversation: 'Conversation',
    memory_state: MemoryState,
    route_result: Optional[RouterResult] = None
) -> AssembledContext:
    """
    Convenience function to build context.

    Usage:
        context = build_context(user, conversation, memory_state, route_result)
        messages = context.to_messages(user_message)
    """
    builder = DynamicContextBuilder(user, conversation, memory_state)
    return builder.build(route_result)
