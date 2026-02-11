"""
Search Agent for Chat V4

Handles cross-entity search operations:
- Full-text search across notes, tasks, projects, areas
- Tag-based searches
- Recent and due items

Architecture:
- Receives GOAL from planner
- Uses LLM to decide which action to take
- Executes action using handler methods
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import date, timedelta

from .base import (
    BaseAgent, AgentContext, ActionDecision,
    DatabaseAgentMixin, ActionDispatcherMixin
)
from ..state import StepResult

logger = logging.getLogger(__name__)


class SearchAgent(BaseAgent, DatabaseAgentMixin, ActionDispatcherMixin):
    """
    Specialized agent for cross-entity search operations.
    """

    AGENT_TYPE = "search"

    AVAILABLE_ACTIONS = [
        "search",
        "search_notes",
        "search_tasks",
        "search_projects",
        "search_areas",
        "search_by_tag",
        "recent",
        "due_soon",
    ]

    def get_actions_description(self) -> str:
        """Return description of available actions for LLM decision-making."""
        return """
### search
Search across all entity types.
Params:
- query (required): Search text
- limit: Max results per type (default: 10)
- include_archived: true/false (default: false)

### search_notes
Search only notes.
Params:
- query (required): Search text
- limit: Max results (default: 20)

### search_tasks
Search only tasks.
Params:
- query (required): Search text
- limit: Max results (default: 20)

### search_projects
Search only projects.
Params:
- query (required): Search text
- limit: Max results (default: 20)

### search_areas
Search only areas.
Params:
- query (required): Search text
- limit: Max results (default: 20)

### search_by_tag
Search items by tag name.
Params:
- tag (required): Tag name
- types: List of types to search (notes, tasks, projects)
- limit: Max results (default: 20)

### recent
Get recently modified items.
Params:
- days: Number of days to look back (default: 7)
- types: List of types (notes, tasks, projects)
- limit: Max results per type (default: 10)

### due_soon
Get tasks and projects due soon.
Params:
- days: Number of days ahead (default: 7)
- limit: Max results (default: 20)
"""

    def _execute_action(self, context: AgentContext, decision: ActionDecision) -> StepResult:
        """Execute the decided action using dispatcher."""
        return self._dispatch_action(context, decision)

    def _handle_search(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Search across all entity types"""
        from notes.models import Note, Task
        from para.models import Project, Area
        from django.db.models import Q

        query = params.get('query') or params.get('q')
        if not query:
            return self._error_result(context, "search", "Search query is required")

        limit = params.get('limit', 10)
        include_archived = params.get('include_archived', False)

        results = {'notes': [], 'tasks': [], 'projects': [], 'areas': []}

        # Search notes
        notes_qs = Note.objects.filter(user_id=context.user_id).filter(
            Q(title__icontains=query) | Q(content__icontains=query)
        )
        if not include_archived:
            notes_qs = notes_qs.filter(is_archived=False)
        notes = list(notes_qs[:limit])
        results['notes'] = [{'id': n.id, 'title': n.title, 'type': 'note'} for n in notes]

        # Search tasks
        tasks_qs = Task.objects.filter(user_id=context.user_id).filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        )
        if not include_archived:
            tasks_qs = tasks_qs.filter(is_archived=False)
        tasks = list(tasks_qs[:limit])
        results['tasks'] = [{'id': t.id, 'title': t.title, 'type': 'task', 'status': t.status} for t in tasks]

        # Search projects
        projects_qs = Project.objects.filter(user_id=context.user_id).filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )
        if not include_archived:
            projects_qs = projects_qs.filter(is_archived=False)
        projects = list(projects_qs[:limit])
        results['projects'] = [{'id': p.id, 'name': p.name, 'type': 'project'} for p in projects]

        # Search areas
        areas_qs = Area.objects.filter(user_id=context.user_id).filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )
        if not include_archived:
            areas_qs = areas_qs.filter(is_active=True)
        areas = list(areas_qs[:limit])
        results['areas'] = [{'id': a.id, 'name': a.name, 'type': 'area'} for a in areas]

        total = sum(len(v) for v in results.values())

        context.set_in_memory('search_results', results)
        context.set_in_memory('search_query', query)

        return self._success_result(
            context,
            action="search",
            output={'results': results, 'total': total, 'query': query},
            summary=f"Found {total} results for '{query}'"
        )

    def _handle_search_notes(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Search only notes"""
        from notes.models import Note
        from django.db.models import Q

        query = params.get('query') or params.get('q')
        if not query:
            return self._error_result(context, "search_notes", "Search query is required")

        limit = params.get('limit', 20)
        queryset = Note.objects.filter(user_id=context.user_id, is_archived=False).filter(
            Q(title__icontains=query) | Q(content__icontains=query)
        )
        notes = list(queryset[:limit])

        return self._success_result(
            context,
            action="search_notes",
            output={'notes': [{'id': n.id, 'title': n.title} for n in notes], 'count': len(notes)},
            summary=f"Found {len(notes)} note(s) matching '{query}'"
        )

    def _handle_search_tasks(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Search only tasks"""
        from notes.models import Task
        from django.db.models import Q

        query = params.get('query') or params.get('q')
        if not query:
            return self._error_result(context, "search_tasks", "Search query is required")

        limit = params.get('limit', 20)
        queryset = Task.objects.filter(user_id=context.user_id, is_archived=False).filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        )
        tasks = list(queryset[:limit])

        return self._success_result(
            context,
            action="search_tasks",
            output={'tasks': [{'id': t.id, 'title': t.title, 'status': t.status} for t in tasks], 'count': len(tasks)},
            summary=f"Found {len(tasks)} task(s) matching '{query}'"
        )

    def _handle_search_projects(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Search only projects"""
        from para.models import Project
        from django.db.models import Q

        query = params.get('query') or params.get('q')
        if not query:
            return self._error_result(context, "search_projects", "Search query is required")

        limit = params.get('limit', 20)
        queryset = Project.objects.filter(user_id=context.user_id, is_archived=False).filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )
        projects = list(queryset[:limit])

        return self._success_result(
            context,
            action="search_projects",
            output={'projects': [{'id': p.id, 'name': p.name, 'status': p.status} for p in projects], 'count': len(projects)},
            summary=f"Found {len(projects)} project(s) matching '{query}'"
        )

    def _handle_search_areas(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Search only areas"""
        from para.models import Area
        from django.db.models import Q

        query = params.get('query') or params.get('q')
        if not query:
            return self._error_result(context, "search_areas", "Search query is required")

        limit = params.get('limit', 20)
        queryset = Area.objects.filter(user_id=context.user_id, is_active=True).filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )
        areas = list(queryset[:limit])

        return self._success_result(
            context,
            action="search_areas",
            output={'areas': [{'id': a.id, 'name': a.name} for a in areas], 'count': len(areas)},
            summary=f"Found {len(areas)} area(s) matching '{query}'"
        )

    def _handle_search_by_tag(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Search items by tag"""
        from notes.models import Note, Tag

        tag_name = params.get('tag')
        if not tag_name:
            return self._error_result(context, "search_by_tag", "Tag name is required")

        # Find the tag
        tag = Tag.objects.filter(user_id=context.user_id, name__iexact=tag_name).first()
        if not tag:
            return self._success_result(
                context,
                action="search_by_tag",
                output={'tag': tag_name, 'notes': [], 'count': 0},
                summary=f"No items found with tag '{tag_name}'"
            )

        limit = params.get('limit', 20)
        notes = list(tag.notes.filter(is_archived=False)[:limit])

        return self._success_result(
            context,
            action="search_by_tag",
            output={
                'tag': {'id': tag.id, 'name': tag.name},
                'notes': [{'id': n.id, 'title': n.title} for n in notes],
                'count': len(notes)
            },
            summary=f"Found {len(notes)} item(s) with tag '{tag_name}'"
        )

    def _handle_recent(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Get recently modified items"""
        from notes.models import Note, Task
        from para.models import Project
        from django.utils import timezone

        days = params.get('days', 7)
        limit = params.get('limit', 10)
        since = timezone.now() - timedelta(days=days)

        results = {'notes': [], 'tasks': [], 'projects': []}

        # Recent notes
        notes = Note.objects.filter(
            user_id=context.user_id,
            is_archived=False,
            updated_at__gte=since
        ).order_by('-updated_at')[:limit]
        results['notes'] = [{'id': n.id, 'title': n.title} for n in notes]

        # Recent tasks
        tasks = Task.objects.filter(
            user_id=context.user_id,
            is_archived=False,
            updated_at__gte=since
        ).order_by('-updated_at')[:limit]
        results['tasks'] = [{'id': t.id, 'title': t.title, 'status': t.status} for t in tasks]

        # Recent projects
        projects = Project.objects.filter(
            user_id=context.user_id,
            is_archived=False,
            updated_at__gte=since
        ).order_by('-updated_at')[:limit]
        results['projects'] = [{'id': p.id, 'name': p.name} for p in projects]

        total = sum(len(v) for v in results.values())

        return self._success_result(
            context,
            action="recent",
            output={'results': results, 'total': total, 'days': days},
            summary=f"Found {total} items modified in the last {days} days"
        )

    def _handle_due_soon(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Get tasks and projects due soon"""
        from notes.models import Task
        from para.models import Project
        from django.utils import timezone
        from datetime import datetime

        days = params.get('days', 7)
        limit = params.get('limit', 20)
        now = timezone.now()
        deadline = now + timedelta(days=days)

        results = {'tasks': [], 'projects': []}

        # Tasks due soon
        tasks = Task.objects.filter(
            user_id=context.user_id,
            is_archived=False,
            status__in=['todo', 'in_progress', 'waiting'],
            due_date__lte=deadline,
            due_date__gte=now
        ).order_by('due_date')[:limit]
        results['tasks'] = [
            {'id': t.id, 'title': t.title, 'due_date': t.due_date.isoformat() if t.due_date else None}
            for t in tasks
        ]

        # Projects due soon
        projects = Project.objects.filter(
            user_id=context.user_id,
            is_archived=False,
            status='active',
            deadline__lte=deadline.date(),
            deadline__gte=now.date()
        ).order_by('deadline')[:limit]
        results['projects'] = [
            {'id': p.id, 'name': p.name, 'deadline': p.deadline.isoformat() if p.deadline else None}
            for p in projects
        ]

        total = len(results['tasks']) + len(results['projects'])

        return self._success_result(
            context,
            action="due_soon",
            output={'results': results, 'total': total, 'days': days},
            summary=f"Found {total} items due in the next {days} days"
        )
