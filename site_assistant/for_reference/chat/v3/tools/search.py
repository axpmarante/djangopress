"""
Chat V3 Search Tool

Unified read-only search tool. Safe to retry, no side effects.

Simplified from V2:
- Tool name is "search" (not "search_tool")
- Cleaner result format
- Better summaries for LLM context
"""

from typing import Dict, Any, List
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta

from .base import BaseTool
from ..types import ToolCall, ToolResult
from ..config import SafetyLevel


class SearchTool(BaseTool):
    """
    Universal search tool for V3.

    Usage:
        {"tool": "search", "params": {"resource_type": "task", "filters": {"due": "overdue"}}}
        {"tool": "search", "params": {"resource_type": "project", "query": "Finance"}}
    """

    name = "search"
    description = "Search for items in the user's system"
    safety_level = SafetyLevel.READ_ONLY

    def execute(self, call: ToolCall) -> ToolResult:
        """Execute a search query."""
        params = call.params
        resource_type = params.get("resource_type", "note")
        query = params.get("query", "")
        filters = params.get("filters", {})
        limit = min(params.get("limit", 20), 50)
        offset = params.get("offset", 0)

        # If filters passed at top level, use them
        if not filters:
            filters = {k: v for k, v in params.items()
                      if k not in ["resource_type", "query", "limit", "offset", "filters"]}

        try:
            if resource_type == "task":
                return self._search_tasks(query, filters, limit, offset)
            elif resource_type == "note":
                return self._search_notes(query, filters, limit, offset)
            elif resource_type == "project":
                return self._search_projects(query, filters, limit, offset)
            elif resource_type == "area":
                return self._search_areas(query, filters, limit, offset)
            elif resource_type == "tag":
                return self._search_tags(query, filters, limit, offset)
            else:
                return self._error(f"Unknown resource type: {resource_type}")

        except Exception as e:
            return self._error(str(e))

    # =========================================================================
    # Task Search
    # =========================================================================

    def _search_tasks(self, query: str, filters: Dict, limit: int, offset: int) -> ToolResult:
        """Search tasks with filters."""
        from tasks.models import Task

        qs = Task.objects.filter(user=self.user)

        # ID filter (exact match - return single item with full details)
        if filters.get("id"):
            qs = qs.filter(id=filters["id"])
            items = list(qs)
            if not items:
                return self._not_found("task", filters["id"])
            return self._success(
                data=self._serialize_task(items[0], full=True),
                summary=f"Found task '{items[0].title}' (ID: {items[0].id})"
            )

        # Title filter
        if filters.get("title"):
            qs = qs.filter(title__icontains=filters["title"])

        # Text search
        if query:
            qs = qs.filter(
                Q(title__icontains=query) |
                Q(description__icontains=query)
            )

        # Status filter
        status = filters.get("status")
        if status == "pending":
            qs = qs.filter(status__in=['todo', 'in_progress', 'waiting'])
        elif status:
            qs = qs.filter(status=status)

        # Priority filter
        if filters.get("priority"):
            qs = qs.filter(priority=filters["priority"])

        # Due date shortcuts
        today = timezone.now().date()
        due = filters.get("due")
        if due == "overdue":
            qs = qs.filter(
                due_date__date__lt=today,
                status__in=['todo', 'in_progress', 'waiting']
            )
        elif due == "today":
            qs = qs.filter(due_date__date=today)
        elif due == "soon":
            soon = today + timedelta(days=2)
            qs = qs.filter(due_date__date__lte=soon, due_date__date__gt=today)
        elif due == "this_week":
            week_end = today + timedelta(days=7)
            qs = qs.filter(due_date__date__lte=week_end, due_date__date__gte=today)

        # Container filters
        if filters.get("container_type"):
            qs = qs.filter(container_type=filters["container_type"])
        if filters.get("container_id"):
            qs = qs.filter(container_id=filters["container_id"])

        # Archive filter
        if filters.get("is_archived") is not None:
            qs = qs.filter(is_archived=filters["is_archived"])
        elif not filters.get("include_archived"):
            qs = qs.exclude(is_archived=True)

        # Tag filter
        if filters.get("tags"):
            qs = qs.filter(tags__name__iexact=filters["tags"])

        # Order
        qs = qs.order_by('due_date', '-priority', '-updated_at')

        items = [self._serialize_task(t) for t in qs[offset:offset + limit]]
        return self._success(
            data=items,
            summary=self._format_task_summary(items)
        )

    # =========================================================================
    # Note Search
    # =========================================================================

    def _search_notes(self, query: str, filters: Dict, limit: int, offset: int) -> ToolResult:
        """Search notes with filters."""
        from notes.models import Note

        qs = Note.objects.filter(user=self.user)

        # ID filter
        if filters.get("id"):
            qs = qs.filter(id=filters["id"])
            items = list(qs)
            if not items:
                return self._not_found("note", filters["id"])
            return self._success(
                data=self._serialize_note(items[0], full=True),
                summary=f"Found note '{items[0].title}' (ID: {items[0].id})"
            )

        # Title filter
        if filters.get("title"):
            qs = qs.filter(title__icontains=filters["title"])

        # Text search
        if query:
            qs = qs.filter(
                Q(title__icontains=query) |
                Q(content__icontains=query)
            )

        # Archive filter
        if filters.get("is_archived") is not None:
            qs = qs.filter(is_archived=filters["is_archived"])
        else:
            qs = qs.exclude(is_archived=True)

        # Container filters
        if filters.get("container_type"):
            qs = qs.filter(container_type=filters["container_type"])
        if filters.get("container_id"):
            qs = qs.filter(container_id=filters["container_id"])

        # Tag filter
        if filters.get("tags"):
            qs = qs.filter(tags__name__iexact=filters["tags"])

        qs = qs.order_by('-updated_at')

        items = [self._serialize_note(n) for n in qs[offset:offset + limit]]
        return self._success(
            data=items,
            summary=self._format_note_summary(items)
        )

    # =========================================================================
    # Project Search
    # =========================================================================

    def _search_projects(self, query: str, filters: Dict, limit: int, offset: int) -> ToolResult:
        """Search projects with filters."""
        from para.models import Project

        qs = Project.objects.filter(user=self.user).select_related('area')

        # ID filter
        if filters.get("id"):
            qs = qs.filter(id=filters["id"])
            items = list(qs)
            if not items:
                return self._not_found("project", filters["id"])
            return self._success(
                data=self._serialize_project(items[0], full=True),
                summary=f"Found project '{items[0].name}' (ID: {items[0].id})"
            )

        # Name filter
        if filters.get("name"):
            qs = qs.filter(name__icontains=filters["name"])

        # Text search
        if query:
            qs = qs.filter(
                Q(name__icontains=query) |
                Q(description__icontains=query)
            )

        # Status filter
        if filters.get("status"):
            qs = qs.filter(status=filters["status"])
        elif not filters.get("include_archived"):
            qs = qs.exclude(status='archived')

        # Area filter
        if filters.get("area_id"):
            qs = qs.filter(area_id=filters["area_id"])

        qs = qs.order_by('-updated_at')

        items = [self._serialize_project(p) for p in qs[offset:offset + limit]]
        return self._success(
            data=items,
            summary=self._format_project_summary(items)
        )

    # =========================================================================
    # Area Search
    # =========================================================================

    def _search_areas(self, query: str, filters: Dict, limit: int, offset: int) -> ToolResult:
        """Search areas with filters."""
        from para.models import Area

        qs = Area.objects.filter(user=self.user)

        # ID filter
        if filters.get("id"):
            qs = qs.filter(id=filters["id"])
            items = list(qs)
            if not items:
                return self._not_found("area", filters["id"])
            return self._success(
                data=self._serialize_area(items[0], full=True),
                summary=f"Found area '{items[0].name}' (ID: {items[0].id})"
            )

        # Name filter
        if filters.get("name"):
            qs = qs.filter(name__icontains=filters["name"])

        # Text search
        if query:
            qs = qs.filter(
                Q(name__icontains=query) |
                Q(description__icontains=query)
            )

        # Active filter
        if filters.get("is_active") is not None:
            qs = qs.filter(is_active=filters["is_active"])
        else:
            qs = qs.filter(is_active=True)

        qs = qs.order_by('name')

        items = [self._serialize_area(a) for a in qs[offset:offset + limit]]
        return self._success(
            data=items,
            summary=self._format_area_summary(items)
        )

    # =========================================================================
    # Tag Search
    # =========================================================================

    def _search_tags(self, query: str, filters: Dict, limit: int, offset: int) -> ToolResult:
        """Search tags."""
        from notes.models import Tag

        qs = Tag.objects.filter(is_active=True)

        # ID filter
        if filters.get("id"):
            qs = qs.filter(id=filters["id"])
            items = list(qs)
            if not items:
                return self._not_found("tag", filters["id"])
            return self._success(
                data=self._serialize_tag(items[0]),
                summary=f"Found tag '{items[0].name}' (ID: {items[0].id})"
            )

        # Name filter
        if filters.get("name"):
            qs = qs.filter(name__icontains=filters["name"])

        # Text search
        if query:
            qs = qs.filter(name__icontains=query)

        qs = qs.order_by('-usage_count')

        items = [self._serialize_tag(t) for t in qs[offset:offset + limit]]
        return self._success(
            data=items,
            summary=f"Found {len(items)} tag(s)"
        )

    # =========================================================================
    # Serializers
    # =========================================================================

    def _serialize_task(self, task, full: bool = False) -> Dict:
        """Serialize a task."""
        data = {
            'id': task.id,
            'title': task.title or 'Untitled Task',
            'status': task.status,
            'priority': task.priority,
            'due_date': task.due_date.isoformat() if task.due_date else None,
            'container_type': task.container_type,
            'container_id': task.container_id,
        }

        if full:
            data['description'] = task.description
            data['waiting_on'] = task.waiting_on
            data['is_archived'] = task.is_archived
            data['tags'] = list(task.tags.values_list('name', flat=True))
            # Add container name
            data['container_name'] = self._get_container_name(
                task.container_type, task.container_id
            )

        return data

    def _serialize_note(self, note, full: bool = False) -> Dict:
        """Serialize a note."""
        data = {
            'id': note.id,
            'title': note.title or 'Untitled',
            'type': note.note_type,
            'container_type': note.container_type,
            'container_id': note.container_id,
        }

        if full:
            data['content'] = note.content
            data['is_archived'] = note.is_archived
            data['tags'] = list(note.tags.values_list('name', flat=True))

        return data

    def _serialize_project(self, project, full: bool = False) -> Dict:
        """Serialize a project."""
        data = {
            'id': project.id,
            'name': project.name,
            'status': project.status,
            'area_id': project.area_id,
            'area_name': project.area.name if project.area else None,
            'deadline': project.deadline.isoformat() if project.deadline else None,
        }

        if full:
            data['description'] = project.description
            data['progress'] = project.progress_percentage
            data['task_counts'] = project.get_task_counts()

        return data

    def _serialize_area(self, area, full: bool = False) -> Dict:
        """Serialize an area."""
        data = {
            'id': area.id,
            'name': area.name,
            'is_active': area.is_active,
            'projects_count': area.get_active_projects_count(),
        }

        if full:
            data['description'] = area.description
            data['parent_id'] = area.parent_id
            data['parent_name'] = area.parent.name if area.parent else None
            sub_areas = area.children.filter(is_active=True)
            data['sub_areas'] = [{'id': sa.id, 'name': sa.name} for sa in sub_areas]

        return data

    def _serialize_tag(self, tag) -> Dict:
        """Serialize a tag."""
        return {
            'id': tag.id,
            'name': tag.name,
            'color': tag.color,
            'usage_count': tag.usage_count,
        }

    def _get_container_name(self, container_type: str, container_id: int) -> str:
        """Get the name of a container."""
        if not container_id:
            return None

        if container_type == 'project':
            from para.models import Project
            try:
                return Project.objects.get(id=container_id).name
            except Project.DoesNotExist:
                return None
        elif container_type == 'area':
            from para.models import Area
            try:
                return Area.objects.get(id=container_id).name
            except Area.DoesNotExist:
                return None

        return None

    # =========================================================================
    # Summary Formatters
    # =========================================================================

    def _format_task_summary(self, items: List[Dict]) -> str:
        """Format task results for LLM context."""
        if not items:
            return "No tasks found"

        lines = [f"Found {len(items)} task(s):"]
        for item in items[:10]:
            status_icon = "[ ]" if item['status'] == 'todo' else "[>]" if item['status'] == 'in_progress' else "[x]"
            due = f" (due: {item['due_date'][:10]})" if item.get('due_date') else ""
            lines.append(f"  {status_icon} {item['title']} (ID: {item['id']}){due}")

        if len(items) > 10:
            lines.append(f"  ... and {len(items) - 10} more")

        return "\n".join(lines)

    def _format_note_summary(self, items: List[Dict]) -> str:
        """Format note results for LLM context."""
        if not items:
            return "No notes found"

        lines = [f"Found {len(items)} note(s):"]
        for item in items[:10]:
            lines.append(f"  - {item['title']} (ID: {item['id']})")

        if len(items) > 10:
            lines.append(f"  ... and {len(items) - 10} more")

        return "\n".join(lines)

    def _format_project_summary(self, items: List[Dict]) -> str:
        """Format project results for LLM context."""
        if not items:
            return "No projects found"

        lines = [f"Found {len(items)} project(s):"]
        for item in items[:10]:
            area = f" in {item['area_name']}" if item.get('area_name') else ""
            lines.append(f"  - {item['name']} (ID: {item['id']}){area}")

        if len(items) > 10:
            lines.append(f"  ... and {len(items) - 10} more")

        return "\n".join(lines)

    def _format_area_summary(self, items: List[Dict]) -> str:
        """Format area results for LLM context."""
        if not items:
            return "No areas found"

        lines = [f"Found {len(items)} area(s):"]
        for item in items[:10]:
            projects = f" ({item['projects_count']} projects)" if item.get('projects_count') else ""
            lines.append(f"  - {item['name']} (ID: {item['id']}){projects}")

        if len(items) > 10:
            lines.append(f"  ... and {len(items) - 10} more")

        return "\n".join(lines)
