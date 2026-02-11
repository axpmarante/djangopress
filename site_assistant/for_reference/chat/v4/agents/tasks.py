"""
Tasks Agent for Chat V4

Handles all task-related operations:
- CRUD operations
- Status changes (todo, in_progress, waiting, done)
- Subtask management
- Recurrence handling
- Priority and deadline management

Architecture:
- Receives GOAL from planner
- Uses LLM to decide which action to take
- Executes action using handler methods
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import date, datetime, timedelta

from .base import (
    BaseAgent, AgentContext, ActionDecision,
    DatabaseAgentMixin, ActionDispatcherMixin
)
from ..state import StepResult

logger = logging.getLogger(__name__)


class TasksAgent(BaseAgent, DatabaseAgentMixin, ActionDispatcherMixin):
    """
    Specialized agent for task operations.

    Receives goals like "Create a task to call John by Friday"
    and uses LLM to decide action (create) and params (title, due_date).
    """

    AGENT_TYPE = "tasks"

    AVAILABLE_ACTIONS = [
        "create",
        "get",
        "update",
        "delete",
        "list",
        "search",
        "complete",
        "start",
        "set_waiting",
        "add_subtask",
        "move",
        "batch_update",
        "archive",
        "unarchive",
    ]

    TASK_FIELDS = [
        'id', 'title', 'description', 'status', 'priority',
        'due_date', 'container_type', 'container_id',
        'waiting_on', 'follow_up_date', 'recurrence_rule',
        'parent_task_id', 'is_archived', 'created_at', 'updated_at'
    ]

    def get_actions_description(self) -> str:
        """Return description of available actions for LLM decision-making."""
        return """
### create
Create a new task.
Params:
- title (required): Task title
- description: Task description
- priority: low, medium, high, urgent (default: medium)
- due_date: ISO date string (YYYY-MM-DD) or relative (today, tomorrow)
- container_type: inbox, project, area (default: inbox)
- container_id: ID of project/area (required if container_type is project/area)
- recurrence_rule: daily, weekly, biweekly, monthly, yearly

### get
Get a task by ID.
Params:
- task_id (required): The task ID

### update
Update an existing task.
Params:
- task_id (required): The task ID
- title: New title
- description: New description
- priority: New priority
- due_date: New due date
- status: todo, in_progress, waiting, done

### delete
Delete a task.
Params:
- task_id (required): The task ID

### list
List tasks with filters.
Params:
- status: Filter by status
- priority: Filter by priority
- container_type: Filter by container type
- container_id: Filter by container ID
- due_date: today, overdue, this_week
- is_archived: true/false (default: false)
- limit: Max results (default: 50)

### search
Search tasks by text query.
Params:
- query (required): Search text
- limit: Max results (default: 20)

### complete
Mark a task as done.
Params:
- task_id (required): The task ID

### start
Mark a task as in_progress.
Params:
- task_id (required): The task ID

### set_waiting
Set task to waiting status.
Params:
- task_id (required): The task ID
- waiting_on: What/who the task is waiting on
- follow_up_date: When to follow up

### move
Move task(s) to a different container.
Params:
- task_id: Single task ID, OR
- task_ids: List of task IDs (from working memory)
- container_type (required): project or area
- container_id: ID of destination (use from working memory if available)

### batch_update
Update multiple tasks at once.
Params:
- task_ids (required): List of task IDs
- updates: Dict of fields to update (priority, status, etc.)

### add_subtask
Add a subtask to a parent task.
Params:
- parent_id (required): Parent task ID
- title (required): Subtask title
- description: Subtask description

### archive
Archive a task.
Params:
- task_id (required): The task ID

### unarchive
Restore an archived task.
Params:
- task_id (required): The task ID
"""

    def _execute_action(self, context: AgentContext, decision: ActionDecision) -> StepResult:
        """Execute the decided action using dispatcher."""
        return self._dispatch_action(context, decision)

    # ========================================================================
    # Action Handlers - each receives (context, params)
    # ========================================================================

    def _handle_create(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Create a new task"""
        from notes.models import Task

        title = params.get('title')
        if not title:
            return self._error_result(context, "create", "Title is required")

        try:
            task = Task.objects.create(
                user_id=context.user_id,
                title=title,
                description=params.get('description', ''),
                status=params.get('status', 'todo'),
                priority=params.get('priority', 'medium'),
                due_date=self._parse_datetime(params.get('due_date')),
                container_type=params.get('container_type', 'inbox'),
                container_id=params.get('container_id'),
                recurrence_rule=params.get('recurrence_rule', '') or params.get('recurrence', ''),
                parent_task_id=params.get('parent_task_id'),
            )

            # Store in working memory for subsequent steps
            context.set_in_memory('created_task_id', task.id)
            context.set_in_memory('last_task', self._serialize_task(task))

            return self._success_result(
                context,
                action="create",
                output={'task': self._serialize_task(task)},
                summary=f"Created task '{task.title}'",
                entities={'task': [task.id]}
            )

        except Exception as e:
            logger.error(f"Task creation failed: {e}")
            return self._error_result(context, "create", str(e))

    def _handle_get(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Get a task by ID"""
        from notes.models import Task

        task_id = params.get('task_id') or params.get('id')
        if not task_id:
            return self._error_result(context, "get", "Task ID is required")

        task = self._get_object_or_none(Task, context.user_id, task_id)
        if not task:
            return self._not_found_result(context, "get", "task", task_id)

        return self._success_result(
            context,
            action="get",
            output={'task': self._serialize_task(task)},
            summary=f"Found task '{task.title}'",
            entities={'task': [task.id]}
        )

    def _handle_update(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Update a task"""
        from notes.models import Task

        task_id = params.get('task_id') or params.get('id')
        if not task_id:
            # Check working memory
            task_id = context.get_from_memory('created_task_id')

        if not task_id:
            return self._error_result(context, "update", "Task ID is required")

        task = self._get_object_or_none(Task, context.user_id, task_id)
        if not task:
            return self._not_found_result(context, "update", "task", task_id)

        # Update allowed fields
        updated_fields = []
        for field in ['title', 'description', 'priority', 'status', 'container_type', 'container_id', 'recurrence_rule']:
            if params.get(field) is not None:
                setattr(task, field, params.get(field))
                updated_fields.append(field)

        if params.get('due_date') is not None:
            task.due_date = self._parse_datetime(params.get('due_date'))
            updated_fields.append('due_date')

        if updated_fields:
            task.save()

        return self._success_result(
            context,
            action="update",
            output={'task': self._serialize_task(task), 'updated_fields': updated_fields},
            summary=f"Updated task '{task.title}' ({', '.join(updated_fields)})",
            entities={'task': [task.id]}
        )

    def _handle_delete(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Delete a task"""
        from notes.models import Task

        task_id = params.get('task_id') or params.get('id')
        if not task_id:
            return self._error_result(context, "delete", "Task ID is required")

        task = self._get_object_or_none(Task, context.user_id, task_id)
        if not task:
            return self._not_found_result(context, "delete", "task", task_id)

        title = task.title
        task.delete()

        return self._success_result(
            context,
            action="delete",
            output={'deleted_id': task_id, 'title': title},
            summary=f"Deleted task '{title}'",
            entities={'task': [task_id]}
        )

    def _handle_list(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """List tasks with optional filters"""
        from notes.models import Task

        queryset = self._get_user_queryset(Task, context.user_id)

        # Apply filters
        filters = {}

        status = params.get('status')
        if status:
            filters['status'] = status

        priority = params.get('priority')
        if priority:
            filters['priority'] = priority

        container_type = params.get('container_type')
        if container_type:
            filters['container_type'] = container_type

        container_id = params.get('container_id')
        if container_id:
            filters['container_id'] = container_id

        is_archived = params.get('is_archived', False)
        filters['is_archived'] = is_archived

        # Date filters
        due_filter = params.get('due_date') or params.get('due')
        if due_filter == 'today':
            filters['due_date__date'] = date.today()
        elif due_filter == 'overdue':
            filters['due_date__lt'] = datetime.now()
            filters['status__in'] = ['todo', 'in_progress', 'waiting']
        elif due_filter == 'this_week':
            today = date.today()
            week_end = today + timedelta(days=(6 - today.weekday()))
            filters['due_date__date__lte'] = week_end
            filters['due_date__date__gte'] = today

        queryset = self._apply_filters(queryset, filters)

        # Ordering
        order_by = params.get('order_by', '-created_at')
        queryset = queryset.order_by(order_by)

        # Limit
        limit = params.get('limit', 50)
        tasks = list(queryset[:limit])

        # Store in working memory for subsequent operations
        task_ids = [t.id for t in tasks]
        context.set_in_memory('found_tasks', task_ids)
        context.set_in_memory('found_task_ids', task_ids)

        return self._success_result(
            context,
            action="list",
            output={
                'tasks': [self._serialize_task(t) for t in tasks],
                'count': len(tasks),
                'task_ids': task_ids
            },
            summary=f"Found {len(tasks)} task(s)",
            entities={'task': task_ids}
        )

    def _handle_search(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Search tasks by query"""
        from notes.models import Task
        from django.db.models import Q

        query = params.get('query') or params.get('q')
        if not query:
            return self._error_result(context, "search", "Search query is required")

        queryset = self._get_user_queryset(Task, context.user_id)

        # Search in title and description
        queryset = queryset.filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        )

        # Apply additional filters
        is_archived = params.get('is_archived', False)
        queryset = queryset.filter(is_archived=is_archived)

        limit = params.get('limit', 20)
        tasks = list(queryset[:limit])

        task_ids = [t.id for t in tasks]
        context.set_in_memory('found_tasks', task_ids)
        context.set_in_memory('found_task_ids', task_ids)

        return self._success_result(
            context,
            action="search",
            output={
                'tasks': [self._serialize_task(t) for t in tasks],
                'count': len(tasks),
                'query': query
            },
            summary=f"Found {len(tasks)} task(s) matching '{query}'",
            entities={'task': task_ids}
        )

    def _handle_complete(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Mark task as done"""
        from notes.models import Task

        task_id = params.get('task_id') or params.get('id')
        if not task_id:
            task_id = context.get_from_memory('created_task_id')

        if not task_id:
            return self._error_result(context, "complete", "Task ID is required")

        task = self._get_object_or_none(Task, context.user_id, task_id)
        if not task:
            return self._not_found_result(context, "complete", "task", task_id)

        # Use the model's mark_done method if available
        if hasattr(task, 'mark_done'):
            task.mark_done()
        else:
            task.status = 'done'
            task.save()

        return self._success_result(
            context,
            action="complete",
            output={'task': self._serialize_task(task)},
            summary=f"Completed task '{task.title}'",
            entities={'task': [task.id]}
        )

    def _handle_start(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Mark task as in progress"""
        from notes.models import Task

        task_id = params.get('task_id') or params.get('id')
        if not task_id:
            return self._error_result(context, "start", "Task ID is required")

        task = self._get_object_or_none(Task, context.user_id, task_id)
        if not task:
            return self._not_found_result(context, "start", "task", task_id)

        if hasattr(task, 'start'):
            task.start()
        else:
            task.status = 'in_progress'
            task.save()

        return self._success_result(
            context,
            action="start",
            output={'task': self._serialize_task(task)},
            summary=f"Started task '{task.title}'",
            entities={'task': [task.id]}
        )

    def _handle_set_waiting(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Set task to waiting status"""
        from notes.models import Task

        task_id = params.get('task_id') or params.get('id')
        if not task_id:
            return self._error_result(context, "set_waiting", "Task ID is required")

        task = self._get_object_or_none(Task, context.user_id, task_id)
        if not task:
            return self._not_found_result(context, "set_waiting", "task", task_id)

        waiting_on = params.get('waiting_on', '')
        follow_up_date = self._parse_datetime(params.get('follow_up_date'))

        if hasattr(task, 'mark_waiting'):
            task.mark_waiting(waiting_on=waiting_on, follow_up_date=follow_up_date)
        else:
            task.status = 'waiting'
            task.waiting_on = waiting_on
            task.follow_up_date = follow_up_date
            task.save()

        return self._success_result(
            context,
            action="set_waiting",
            output={'task': self._serialize_task(task)},
            summary=f"Set task '{task.title}' to waiting on '{waiting_on}'",
            entities={'task': [task.id]}
        )

    def _handle_move(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Move task(s) to a different container"""
        from notes.models import Task

        # Get task IDs - can be single or multiple
        task_id = params.get('task_id')
        task_ids = params.get('task_ids') or context.get_from_memory('found_task_ids')

        if task_id:
            task_ids = [task_id]
        elif not task_ids:
            return self._error_result(context, "move", "Task ID(s) required")

        container_type = params.get('container_type')
        if not container_type:
            return self._error_result(context, "move", "container_type is required")

        # Get container_id from params or working memory
        container_id = params.get('container_id')
        if not container_id:
            # Try to get from working memory based on container type
            if container_type == 'project':
                container_id = context.get_from_memory('found_project_id')
                step_result = context.get_step_result(1)  # Often from step 1
                if step_result and 'project' in step_result.get('output', {}):
                    container_id = step_result['output']['project'].get('id')
            elif container_type == 'area':
                container_id = context.get_from_memory('found_area_id')

        moved_tasks = []
        for tid in task_ids:
            task = self._get_object_or_none(Task, context.user_id, tid)
            if task:
                task.container_type = container_type
                task.container_id = container_id
                task.save()
                moved_tasks.append(self._serialize_task(task))

        if not moved_tasks:
            return self._error_result(context, "move", "No tasks found to move")

        return self._success_result(
            context,
            action="move",
            output={
                'moved_count': len(moved_tasks),
                'tasks': moved_tasks,
                'container_type': container_type,
                'container_id': container_id
            },
            summary=f"Moved {len(moved_tasks)} task(s) to {container_type}",
            entities={'task': task_ids}
        )

    def _handle_batch_update(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Update multiple tasks at once"""
        from notes.models import Task

        task_ids = params.get('task_ids') or context.get_from_memory('found_task_ids')
        if not task_ids:
            return self._error_result(context, "batch_update", "Task IDs required")

        updates = params.get('updates', {})
        if not updates:
            return self._error_result(context, "batch_update", "Updates required")

        updated_tasks = []
        for tid in task_ids:
            task = self._get_object_or_none(Task, context.user_id, tid)
            if task:
                for field, value in updates.items():
                    if hasattr(task, field):
                        setattr(task, field, value)
                task.save()
                updated_tasks.append(self._serialize_task(task))

        return self._success_result(
            context,
            action="batch_update",
            output={
                'updated_count': len(updated_tasks),
                'tasks': updated_tasks,
                'updates': updates
            },
            summary=f"Updated {len(updated_tasks)} task(s)",
            entities={'task': task_ids}
        )

    def _handle_add_subtask(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Add a subtask to a parent task"""
        from notes.models import Task

        parent_id = params.get('parent_id') or params.get('task_id')
        if not parent_id:
            return self._error_result(context, "add_subtask", "Parent task ID is required")

        parent = self._get_object_or_none(Task, context.user_id, parent_id)
        if not parent:
            return self._not_found_result(context, "add_subtask", "parent task", parent_id)

        title = params.get('title')
        if not title:
            return self._error_result(context, "add_subtask", "Subtask title is required")

        subtask = Task.objects.create(
            user_id=context.user_id,
            title=title,
            description=params.get('description', ''),
            parent_task=parent,
            container_type=parent.container_type,
            container_id=parent.container_id,
            priority=params.get('priority', parent.priority),
        )

        context.set_in_memory('created_subtask_id', subtask.id)

        return self._success_result(
            context,
            action="add_subtask",
            output={
                'subtask': self._serialize_task(subtask),
                'parent_id': parent_id
            },
            summary=f"Added subtask '{subtask.title}' to '{parent.title}'",
            entities={'task': [subtask.id, parent_id]}
        )

    def _handle_archive(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Archive a task"""
        from notes.models import Task

        task_id = params.get('task_id') or params.get('id')
        if not task_id:
            return self._error_result(context, "archive", "Task ID is required")

        task = self._get_object_or_none(Task, context.user_id, task_id)
        if not task:
            return self._not_found_result(context, "archive", "task", task_id)

        task.is_archived = True
        task.save()

        return self._success_result(
            context,
            action="archive",
            output={'task': self._serialize_task(task)},
            summary=f"Archived task '{task.title}'",
            entities={'task': [task.id]}
        )

    def _handle_unarchive(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Unarchive a task"""
        from notes.models import Task

        task_id = params.get('task_id') or params.get('id')
        if not task_id:
            return self._error_result(context, "unarchive", "Task ID is required")

        task = self._get_object_or_none(Task, context.user_id, task_id)
        if not task:
            return self._not_found_result(context, "unarchive", "task", task_id)

        task.is_archived = False
        task.save()

        return self._success_result(
            context,
            action="unarchive",
            output={'task': self._serialize_task(task)},
            summary=f"Unarchived task '{task.title}'",
            entities={'task': [task.id]}
        )

    # ========================================================================
    # Helpers
    # ========================================================================

    def _serialize_task(self, task) -> Dict[str, Any]:
        """Serialize a task to dict"""
        return self._serialize_object(task, self.TASK_FIELDS)

    def _parse_datetime(self, value) -> Optional[datetime]:
        """Parse datetime from various formats"""
        from django.utils import timezone

        if not value:
            return None

        if isinstance(value, datetime):
            if timezone.is_naive(value):
                return timezone.make_aware(value)
            return value

        if isinstance(value, date) and not isinstance(value, datetime):
            dt = datetime.combine(value, datetime.max.time().replace(microsecond=0))
            return timezone.make_aware(dt)

        if isinstance(value, str):
            value_lower = value.lower()
            today = date.today()

            if value_lower == 'today':
                dt = datetime.combine(today, datetime.max.time().replace(microsecond=0))
                return timezone.make_aware(dt)
            elif value_lower == 'tomorrow':
                dt = datetime.combine(today + timedelta(days=1), datetime.max.time().replace(microsecond=0))
                return timezone.make_aware(dt)
            elif value_lower == 'next week':
                dt = datetime.combine(today + timedelta(days=7), datetime.max.time().replace(microsecond=0))
                return timezone.make_aware(dt)
            elif value_lower == 'next month':
                dt = datetime.combine(today + timedelta(days=30), datetime.max.time().replace(microsecond=0))
                return timezone.make_aware(dt)

            # Try parsing ISO format
            try:
                dt = datetime.fromisoformat(value)
                if timezone.is_naive(dt):
                    return timezone.make_aware(dt)
                return dt
            except ValueError:
                pass

            # Try common date formats
            for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y']:
                try:
                    dt = datetime.strptime(value, fmt)
                    dt = dt.replace(hour=23, minute=59, second=59)
                    return timezone.make_aware(dt)
                except ValueError:
                    continue

        return None
