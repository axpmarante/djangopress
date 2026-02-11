"""
Inbox Agent for Chat V4

Handles inbox-related operations:
- Quick capture of notes and tasks
- Inbox listing and processing
- Moving items out of inbox

Architecture:
- Receives GOAL from planner
- Uses LLM to decide which action to take
- Executes action using handler methods
"""

import logging
from typing import Dict, List, Any

from .base import (
    BaseAgent, AgentContext, ActionDecision,
    DatabaseAgentMixin, ActionDispatcherMixin
)
from ..state import StepResult

logger = logging.getLogger(__name__)


class InboxAgent(BaseAgent, DatabaseAgentMixin, ActionDispatcherMixin):
    """
    Specialized agent for inbox operations.
    """

    AGENT_TYPE = "inbox"

    AVAILABLE_ACTIONS = [
        "capture",
        "capture_task",
        "list",
        "count",
        "process",
    ]

    def get_actions_description(self) -> str:
        """Return description of available actions for LLM decision-making."""
        return """
### capture
Quick capture a note to inbox.
Params:
- content (required): Note content
- title: Note title (auto-generated from content if not provided)

### capture_task
Quick capture a task to inbox.
Params:
- title (required): Task title
- description: Task description
- priority: low, medium, high (default: medium)

### list
List all inbox items (notes and tasks).
Params:
- limit: Max results per type (default: 50)
- include_notes: true/false (default: true)
- include_tasks: true/false (default: true)

### count
Count inbox items.
Params: none

### process
Move an inbox item to a container.
Params:
- item_type (required): note or task
- item_id (required): The item ID
- container_type (required): project or area
- container_id: ID of destination
"""

    def _execute_action(self, context: AgentContext, decision: ActionDecision) -> StepResult:
        """Execute the decided action using dispatcher."""
        return self._dispatch_action(context, decision)

    def _handle_capture(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Quick capture a note to inbox"""
        from notes.models import Note

        content = params.get('content') or params.get('text')
        if not content:
            return self._error_result(context, "capture", "Content is required")

        title = params.get('title')
        if not title:
            first_line = content.split('\n')[0]
            title = first_line[:50] + ('...' if len(first_line) > 50 else '')

        note = Note.objects.create(
            user_id=context.user_id,
            title=title,
            content=content,
            note_type='note',
            container_type='inbox',
            container_id=None
        )

        context.set_in_memory('captured_note_id', note.id)

        return self._success_result(
            context,
            action="capture",
            output={'note': {'id': note.id, 'title': note.title}},
            summary=f"Captured to inbox: '{note.title}'",
            entities={'note': [note.id]}
        )

    def _handle_capture_task(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Quick capture a task to inbox"""
        from notes.models import Task

        title = params.get('title')
        if not title:
            return self._error_result(context, "capture_task", "Task title is required")

        task = Task.objects.create(
            user_id=context.user_id,
            title=title,
            description=params.get('description', ''),
            priority=params.get('priority', 'medium'),
            status='todo',
            container_type='inbox',
            container_id=None
        )

        context.set_in_memory('captured_task_id', task.id)

        return self._success_result(
            context,
            action="capture_task",
            output={'task': {'id': task.id, 'title': task.title}},
            summary=f"Captured task to inbox: '{task.title}'",
            entities={'task': [task.id]}
        )

    def _handle_list(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """List all inbox items"""
        from notes.models import Note, Task

        include_notes = params.get('include_notes', True)
        include_tasks = params.get('include_tasks', True)
        limit = params.get('limit', 50)

        result = {'notes': [], 'tasks': [], 'total': 0}

        if include_notes:
            notes = Note.objects.filter(
                user_id=context.user_id,
                container_type='inbox',
                is_archived=False
            ).order_by('-created_at')[:limit]
            result['notes'] = [{'id': n.id, 'title': n.title, 'type': n.note_type} for n in notes]

        if include_tasks:
            tasks = Task.objects.filter(
                user_id=context.user_id,
                container_type='inbox',
                is_archived=False
            ).order_by('-created_at')[:limit]
            result['tasks'] = [{'id': t.id, 'title': t.title, 'priority': t.priority} for t in tasks]

        result['total'] = len(result['notes']) + len(result['tasks'])

        return self._success_result(
            context,
            action="list",
            output=result,
            summary=f"Inbox: {len(result['notes'])} notes, {len(result['tasks'])} tasks",
            entities={'note': [n['id'] for n in result['notes']], 'task': [t['id'] for t in result['tasks']]}
        )

    def _handle_count(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Count inbox items"""
        from notes.models import Note, Task

        notes_count = Note.objects.filter(
            user_id=context.user_id,
            container_type='inbox',
            is_archived=False
        ).count()

        tasks_count = Task.objects.filter(
            user_id=context.user_id,
            container_type='inbox',
            is_archived=False
        ).count()

        return self._success_result(
            context,
            action="count",
            output={'notes': notes_count, 'tasks': tasks_count, 'total': notes_count + tasks_count},
            summary=f"Inbox has {notes_count + tasks_count} items ({notes_count} notes, {tasks_count} tasks)"
        )

    def _handle_process(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Move an inbox item to a container"""
        from notes.models import Note, Task

        item_type = params.get('item_type')
        item_id = params.get('item_id')
        container_type = params.get('container_type')
        container_id = params.get('container_id')

        if not item_type or not item_id:
            return self._error_result(context, "process", "item_type and item_id are required")

        if not container_type:
            return self._error_result(context, "process", "container_type is required")

        # Get container_id from working memory if not provided
        if not container_id:
            if container_type == 'project':
                container_id = context.get_from_memory('found_project_id')
            elif container_type == 'area':
                container_id = context.get_from_memory('found_area_id')

        if item_type == 'note':
            item = self._get_object_or_none(Note, context.user_id, item_id)
            if not item:
                return self._not_found_result(context, "process", "note", item_id)
        elif item_type == 'task':
            item = self._get_object_or_none(Task, context.user_id, item_id)
            if not item:
                return self._not_found_result(context, "process", "task", item_id)
        else:
            return self._error_result(context, "process", "item_type must be 'note' or 'task'")

        item.container_type = container_type
        item.container_id = container_id
        item.save()

        return self._success_result(
            context,
            action="process",
            output={'item_type': item_type, 'item_id': item_id, 'container_type': container_type},
            summary=f"Moved {item_type} '{item.title}' to {container_type}",
            entities={item_type: [item_id]}
        )
