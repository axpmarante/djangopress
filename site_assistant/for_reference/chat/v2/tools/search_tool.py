"""
Chat V2 Search Tool

Unified read-only query tool. Safe to retry, no side effects.

Replaces data_tool with a simpler, more powerful interface:
- Single tool with filters on any model field
- Shortcut filters for common queries (due: "overdue", status: "pending")
- Returns one or many items based on filters
"""

from typing import Dict, Any, List, Optional
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta

from .base import BaseTool, ToolCall, ToolResult, ToolStatus


class SearchTool(BaseTool):
    """
    Unified search tool for all read operations.

    Usage:
        # Get by ID
        {"tool": "search_tool", "resource_type": "task", "filters": {"id": 42}}

        # Search by text
        {"tool": "search_tool", "resource_type": "note", "query": "meeting notes"}

        # Filter by fields
        {"tool": "search_tool", "resource_type": "task", "filters": {"due": "overdue"}}

        # Combine query and filters
        {"tool": "search_tool", "resource_type": "task", "query": "report", "filters": {"priority": "high"}}
    """

    name = "search_tool"
    actions = ["search"]  # Single action, but we keep for compatibility
    resource_types = ["note", "task", "project", "area", "tag", "goal", "daily_planner", "weekly_planner"]

    def execute(self, call: ToolCall) -> ToolResult:
        """Execute a search query."""
        resource_type = call.resource_type or "note"
        params = call.params

        # Extract search parameters
        query = params.get("query", "")
        filters = params.get("filters", {})
        limit = min(params.get("limit", 20), 50)
        offset = params.get("offset", 0)

        # If filters passed at top level (not nested), use them directly
        if not filters:
            filters = {k: v for k, v in params.items()
                      if k not in ["query", "limit", "offset", "filters"]}

        try:
            if resource_type == "task":
                items = self._search_tasks(query, filters, limit, offset)
            elif resource_type == "note":
                items = self._search_notes(query, filters, limit, offset)
            elif resource_type == "project":
                items = self._search_projects(query, filters, limit, offset)
            elif resource_type == "area":
                items = self._search_areas(query, filters, limit, offset)
            elif resource_type == "tag":
                items = self._search_tags(query, filters, limit, offset)
            elif resource_type == "goal":
                items = self._search_goals(query, filters, limit, offset)
            elif resource_type == "daily_planner":
                items = self._search_daily_planners(query, filters, limit, offset)
            elif resource_type == "weekly_planner":
                items = self._search_weekly_planners(query, filters, limit, offset)
            else:
                return self._result(
                    ToolStatus.VALIDATION_ERROR,
                    error=f"Unknown resource type: {resource_type}",
                    action="search"
                )

            # If searching by ID and found exactly one, return it directly
            if filters.get("id") and len(items) == 1:
                return self._result(
                    ToolStatus.SUCCESS,
                    data=items[0],
                    message=f"Found {resource_type} '{items[0].get('title', items[0].get('name', 'item'))}'",
                    action="search",
                    resource_type=resource_type
                )

            # If searching by ID and not found
            if filters.get("id") and len(items) == 0:
                return self._result(
                    ToolStatus.NOT_FOUND,
                    error=f"{resource_type.capitalize()} with ID {filters['id']} not found",
                    action="search",
                    resource_type=resource_type
                )

            return self._result(
                ToolStatus.SUCCESS,
                data={"items": items, "count": len(items)},
                message=f"Found {len(items)} {resource_type}(s)",
                action="search",
                resource_type=resource_type
            )

        except Exception as e:
            return self._result(
                ToolStatus.ERROR,
                error=str(e),
                action="search",
                resource_type=resource_type
            )

    # =========================================================================
    # Task Search
    # =========================================================================

    def _search_tasks(self, query: str, filters: Dict, limit: int, offset: int) -> List[Dict]:
        """
        Search tasks with filters.

        Filters:
            id: int - Exact match
            status: str - "todo", "in_progress", "waiting", "done" or "pending" shortcut
            priority: str - "low", "medium", "high", "urgent"
            due: str - Shortcut: "overdue", "today", "soon", "this_week"
            due_date: str - Exact date or with __lt, __lte, __gt, __gte
            container_type: str - "project", "area", "inbox"
            container_id: int - ID of container
            is_archived: bool - Filter by archived status
            tags: str - Filter by tag name
        """
        from tasks.models import Task

        qs = Task.objects.filter(user=self.user)

        # ID filter (exact match)
        if filters.get("id"):
            qs = qs.filter(id=filters["id"])
            items = list(qs)
            return [self._serialize_task(t, full=True) for t in items]

        # Title filter (case-insensitive contains)
        if filters.get("title"):
            qs = qs.filter(title__icontains=filters["title"])

        # Text search (searches title and description)
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

        # Direct due_date filter with operators
        if filters.get("due_date"):
            qs = self._apply_date_filter(qs, "due_date", filters["due_date"])

        # Container filters
        if filters.get("container_type"):
            qs = qs.filter(container_type=filters["container_type"])
        if filters.get("container_id"):
            qs = qs.filter(container_id=filters["container_id"])

        # Archived filter
        if filters.get("is_archived") is not None:
            qs = qs.filter(is_archived=filters["is_archived"])
        elif not filters.get("include_archived"):
            qs = qs.exclude(is_archived=True)

        # Tag filter
        if filters.get("tags"):
            qs = qs.filter(tags__name__iexact=filters["tags"])

        # Order by due date, then priority
        qs = qs.order_by('due_date', '-priority', '-updated_at')

        return [self._serialize_task(t) for t in qs[offset:offset + limit]]

    # =========================================================================
    # Note Search
    # =========================================================================

    def _search_notes(self, query: str, filters: Dict, limit: int, offset: int) -> List[Dict]:
        """
        Search notes (excluding tasks) with filters.

        Filters:
            id: int - Exact match
            title: str - Filter by title (case-insensitive contains)
            container_type: str - "project", "area", "inbox"
            container_id: int - ID of container
            is_archived: bool - Filter by archived status
            note_type: str - "note", "reference", etc.
            tags: str - Filter by tag name
        """
        from notes.models import Note

        qs = Note.objects.filter(user=self.user)

        # ID filter
        if filters.get("id"):
            qs = qs.filter(id=filters["id"])
            items = list(qs)
            return [self._serialize_note(n, full=True) for n in items]

        # Title filter (case-insensitive contains)
        if filters.get("title"):
            qs = qs.filter(title__icontains=filters["title"])

        # Text search (searches title and content)
        if query:
            qs = qs.filter(
                Q(title__icontains=query) |
                Q(content__icontains=query)
            )

        # Archived filter
        if filters.get("is_archived") is not None:
            qs = qs.filter(is_archived=filters["is_archived"])
        else:
            qs = qs.exclude(is_archived=True)

        # Container filters
        if filters.get("container_type"):
            qs = qs.filter(container_type=filters["container_type"])
        if filters.get("container_id"):
            qs = qs.filter(container_id=filters["container_id"])

        # Note type filter
        if filters.get("note_type"):
            qs = qs.filter(note_type=filters["note_type"])

        # Tag filter
        if filters.get("tags"):
            qs = qs.filter(tags__name__iexact=filters["tags"])

        # Order by updated
        qs = qs.order_by('-updated_at')

        return [self._serialize_note(n) for n in qs[offset:offset + limit]]

    # =========================================================================
    # Project Search
    # =========================================================================

    def _search_projects(self, query: str, filters: Dict, limit: int, offset: int) -> List[Dict]:
        """
        Search projects with filters.

        Filters:
            id: int - Exact match
            name: str - Filter by name (case-insensitive contains)
            status: str - "active", "completed", "on_hold", "archived"
            area_id: int - Filter by parent area
            deadline: str - Date filter with operators
        """
        from para.models import Project

        qs = Project.objects.filter(user=self.user).select_related('area')

        # ID filter
        if filters.get("id"):
            qs = qs.filter(id=filters["id"])
            items = list(qs)
            return [self._serialize_project(p, full=True) for p in items]

        # Name filter (case-insensitive contains)
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

        # Deadline filter
        if filters.get("deadline"):
            qs = self._apply_date_filter(qs, "deadline", filters["deadline"])

        qs = qs.order_by('-updated_at')

        return [self._serialize_project(p) for p in qs[offset:offset + limit]]

    # =========================================================================
    # Area Search
    # =========================================================================

    def _search_areas(self, query: str, filters: Dict, limit: int, offset: int) -> List[Dict]:
        """
        Search areas with filters.

        Filters:
            id: int - Exact match
            name: str - Filter by name (case-insensitive contains)
            is_active: bool - Active areas only
        """
        from para.models import Area

        qs = Area.objects.filter(user=self.user)

        # ID filter
        if filters.get("id"):
            qs = qs.filter(id=filters["id"])
            items = list(qs)
            return [self._serialize_area(a, full=True) for a in items]

        # Name filter (case-insensitive contains)
        if filters.get("name"):
            qs = qs.filter(name__icontains=filters["name"])

        # Text search (searches name and description)
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

        return [self._serialize_area(a) for a in qs[offset:offset + limit]]

    # =========================================================================
    # Tag Search
    # =========================================================================

    def _search_tags(self, query: str, filters: Dict, limit: int, offset: int) -> List[Dict]:
        """
        Search tags.

        Filters:
            id: int - Exact match
            name: str - Filter by name (case-insensitive contains)
            tag_type: str - Filter by type
        """
        from notes.models import Tag

        qs = Tag.objects.filter(is_active=True)

        # ID filter
        if filters.get("id"):
            qs = qs.filter(id=filters["id"])
            items = list(qs)
            return [self._serialize_tag(t) for t in items]

        # Name filter (case-insensitive contains)
        if filters.get("name"):
            qs = qs.filter(name__icontains=filters["name"])

        # Text search
        if query:
            qs = qs.filter(name__icontains=query)

        # Type filter
        if filters.get("tag_type"):
            qs = qs.filter(tag_type=filters["tag_type"])

        qs = qs.order_by('-usage_count')

        return [self._serialize_tag(t) for t in qs[offset:offset + limit]]

    # =========================================================================
    # Goal Search
    # =========================================================================

    def _search_goals(self, query: str, filters: Dict, limit: int, offset: int) -> List[Dict]:
        """
        Search goals with filters.

        Filters:
            id: int - Exact match
            title: str - Filter by title (case-insensitive contains)
            goal_type: str - "year", "quarter", "month"
            year: int - Filter by year
            quarter: int - Filter by quarter (1-4)
            month: int - Filter by month (1-12)
            status: str - "active", "completed", "abandoned"
            current: bool - Get current period goals (shortcuts to current year/quarter/month)
        """
        from journal.models import Goal

        qs = Goal.objects.filter(user=self.user)

        # ID filter
        if filters.get("id"):
            qs = qs.filter(id=filters["id"])
            items = list(qs)
            return [self._serialize_goal(g, full=True) for g in items]

        # Title filter (case-insensitive contains)
        if filters.get("title"):
            qs = qs.filter(title__icontains=filters["title"])

        # Text search (searches title and description)
        if query:
            qs = qs.filter(
                Q(title__icontains=query) |
                Q(description__icontains=query)
            )

        # Goal type filter
        if filters.get("goal_type"):
            qs = qs.filter(goal_type=filters["goal_type"])

        # Year filter (default to current year if not specified and not searching all)
        if filters.get("year"):
            qs = qs.filter(year=filters["year"])
        elif filters.get("current"):
            today = timezone.now().date()
            qs = qs.filter(year=today.year)

        # Quarter filter
        if filters.get("quarter"):
            qs = qs.filter(quarter=filters["quarter"])
        elif filters.get("current") and filters.get("goal_type") in ["quarter", "month"]:
            today = timezone.now().date()
            current_quarter = (today.month - 1) // 3 + 1
            qs = qs.filter(quarter=current_quarter)

        # Month filter
        if filters.get("month"):
            qs = qs.filter(month=filters["month"])
        elif filters.get("current") and filters.get("goal_type") == "month":
            today = timezone.now().date()
            qs = qs.filter(month=today.month)

        # Status filter
        status = filters.get("status", "active")
        if status:
            qs = qs.filter(status=status)

        qs = qs.order_by('-goal_type', 'quarter', 'month', 'title')

        return [self._serialize_goal(g) for g in qs[offset:offset + limit]]

    # =========================================================================
    # Daily Planner Search
    # =========================================================================

    def _search_daily_planners(self, query: str, filters: Dict, limit: int, offset: int) -> List[Dict]:
        """
        Search daily planner entries with filters.

        Filters:
            id: int - Exact match
            date: str - Specific date (YYYY-MM-DD)
            today: bool - Get today's entry
            start_date: str - Date range start
            end_date: str - Date range end
            is_morning_complete: bool
            is_evening_complete: bool
        """
        from journal.models import DailyPlannerEntry
        from datetime import datetime

        qs = DailyPlannerEntry.objects.filter(user=self.user)

        # ID filter
        if filters.get("id"):
            qs = qs.filter(id=filters["id"])
            items = list(qs)
            return [self._serialize_daily_planner(d, full=True) for d in items]

        # Today shortcut
        if filters.get("today"):
            today = timezone.now().date()
            qs = qs.filter(date=today)
            items = list(qs)
            return [self._serialize_daily_planner(d, full=True) for d in items]

        # Specific date
        if filters.get("date"):
            try:
                target_date = datetime.strptime(filters["date"], '%Y-%m-%d').date()
                qs = qs.filter(date=target_date)
                items = list(qs)
                return [self._serialize_daily_planner(d, full=True) for d in items]
            except ValueError:
                pass

        # Date range
        if filters.get("start_date"):
            try:
                start = datetime.strptime(filters["start_date"], '%Y-%m-%d').date()
                qs = qs.filter(date__gte=start)
            except ValueError:
                pass

        if filters.get("end_date"):
            try:
                end = datetime.strptime(filters["end_date"], '%Y-%m-%d').date()
                qs = qs.filter(date__lte=end)
            except ValueError:
                pass

        # Completion filters
        if filters.get("is_morning_complete") is not None:
            qs = qs.filter(is_morning_complete=filters["is_morning_complete"])
        if filters.get("is_evening_complete") is not None:
            qs = qs.filter(is_evening_complete=filters["is_evening_complete"])

        qs = qs.order_by('-date')

        return [self._serialize_daily_planner(d) for d in qs[offset:offset + limit]]

    # =========================================================================
    # Weekly Planner Search
    # =========================================================================

    def _search_weekly_planners(self, query: str, filters: Dict, limit: int, offset: int) -> List[Dict]:
        """
        Search weekly planner entries with filters.

        Filters:
            id: int - Exact match
            date: str - Any date within the week (YYYY-MM-DD)
            week_start: str - Monday of the week (YYYY-MM-DD)
            current: bool - Get current week's entry
            year: int - Filter by year
            is_planning_complete: bool
            is_review_complete: bool
        """
        from journal.models import WeeklyPlannerEntry
        from datetime import datetime

        qs = WeeklyPlannerEntry.objects.filter(user=self.user)

        # ID filter
        if filters.get("id"):
            qs = qs.filter(id=filters["id"])
            items = list(qs)
            return [self._serialize_weekly_planner(w, full=True) for w in items]

        # Current week shortcut
        if filters.get("current"):
            today = timezone.now().date()
            days_since_monday = today.weekday()
            week_start = today - timedelta(days=days_since_monday)
            qs = qs.filter(week_start=week_start)
            items = list(qs)
            return [self._serialize_weekly_planner(w, full=True) for w in items]

        # Specific week start
        if filters.get("week_start"):
            try:
                week_start = datetime.strptime(filters["week_start"], '%Y-%m-%d').date()
                qs = qs.filter(week_start=week_start)
                items = list(qs)
                return [self._serialize_weekly_planner(w, full=True) for w in items]
            except ValueError:
                pass

        # Date within week
        if filters.get("date"):
            try:
                target_date = datetime.strptime(filters["date"], '%Y-%m-%d').date()
                days_since_monday = target_date.weekday()
                week_start = target_date - timedelta(days=days_since_monday)
                qs = qs.filter(week_start=week_start)
                items = list(qs)
                return [self._serialize_weekly_planner(w, full=True) for w in items]
            except ValueError:
                pass

        # Year filter
        if filters.get("year"):
            qs = qs.filter(week_start__year=filters["year"])

        # Completion filters
        if filters.get("is_planning_complete") is not None:
            qs = qs.filter(is_planning_complete=filters["is_planning_complete"])
        if filters.get("is_review_complete") is not None:
            qs = qs.filter(is_review_complete=filters["is_review_complete"])

        qs = qs.order_by('-week_start')

        return [self._serialize_weekly_planner(w) for w in qs[offset:offset + limit]]

    # =========================================================================
    # Helpers
    # =========================================================================

    def _apply_date_filter(self, qs, field: str, value):
        """Apply date filter with optional operators."""
        from datetime import datetime

        # If it's a dict with operators
        if isinstance(value, dict):
            for op, date_val in value.items():
                parsed = self._parse_date(date_val)
                if parsed:
                    if op == "__lt":
                        qs = qs.filter(**{f"{field}__lt": parsed})
                    elif op == "__lte":
                        qs = qs.filter(**{f"{field}__lte": parsed})
                    elif op == "__gt":
                        qs = qs.filter(**{f"{field}__gt": parsed})
                    elif op == "__gte":
                        qs = qs.filter(**{f"{field}__gte": parsed})
        else:
            # Simple date match
            parsed = self._parse_date(value)
            if parsed:
                qs = qs.filter(**{f"{field}__date": parsed.date()})

        return qs

    def _parse_date(self, date_str: str):
        """Parse date string."""
        from datetime import datetime

        if not date_str:
            return None

        formats = [
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%d/%m/%Y",
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return timezone.make_aware(dt) if timezone.is_naive(dt) else dt
            except ValueError:
                continue

        return None

    # =========================================================================
    # Serializers
    # =========================================================================

    def _serialize_task(self, task, full: bool = False) -> Dict:
        """Serialize a task to dict."""
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
            data['follow_up_date'] = task.follow_up_date.isoformat() if task.follow_up_date else None
            data['is_recurring'] = task.is_recurring
            data['is_archived'] = task.is_archived
            data['created_at'] = task.created_at.isoformat() if task.created_at else None
            data['updated_at'] = task.updated_at.isoformat() if task.updated_at else None
            data['tags'] = list(task.tags.values_list('name', flat=True))
            # Add container name for context
            if task.container_type == 'project' and task.container_id:
                from para.models import Project
                try:
                    project = Project.objects.get(id=task.container_id)
                    data['container_name'] = project.name
                except Project.DoesNotExist:
                    data['container_name'] = None
            elif task.container_type == 'area' and task.container_id:
                from para.models import Area
                try:
                    area = Area.objects.get(id=task.container_id)
                    data['container_name'] = area.name
                except Area.DoesNotExist:
                    data['container_name'] = None
            else:
                data['container_name'] = None

        return data

    def _serialize_note(self, note, full: bool = False) -> Dict:
        """Serialize a note to dict."""
        data = {
            'id': note.id,
            'title': note.title or 'Untitled',
            'type': note.note_type,
            'container_type': note.container_type,
            'container_id': note.container_id,
            'is_archived': note.is_archived,
            'updated_at': note.updated_at.isoformat() if note.updated_at else None,
        }

        if full:
            data['content'] = note.content
            data['created_at'] = note.created_at.isoformat() if note.created_at else None
            data['tags'] = list(note.tags.values_list('name', flat=True))
            data['has_summary'] = bool(note.summary)

        return data

    def _serialize_project(self, project, full: bool = False) -> Dict:
        """Serialize a project to dict."""
        data = {
            'id': project.id,
            'title': project.name,
            'name': project.name,
            'status': project.status,
            'area_id': project.area_id,
            'area_name': project.area.name if project.area else None,
            'area_full_path': project.area.get_full_path() if project.area else None,
            'deadline': project.deadline.isoformat() if project.deadline else None,
            'progress': project.progress_percentage,
        }

        if full:
            data['description'] = project.description
            data['created_at'] = project.created_at.isoformat() if project.created_at else None
            data['updated_at'] = project.updated_at.isoformat() if project.updated_at else None
            data['task_counts'] = project.get_task_counts()

        return data

    def _serialize_area(self, area, full: bool = False) -> Dict:
        """Serialize an area to dict."""
        data = {
            'id': area.id,
            'title': area.name,
            'name': area.name,
            'full_path': area.get_full_path(),
            'is_active': area.is_active,
            'projects_count': area.get_active_projects_count(),
            'parent_id': area.parent_id,
            'depth': area.get_depth(),
        }

        if full:
            data['description'] = area.description
            data['is_business_area'] = area.is_business_area
            data['created_at'] = area.created_at.isoformat() if area.created_at else None
            data['parent_name'] = area.parent.name if area.parent else None
            # Include sub-areas
            sub_areas = area.children.filter(is_active=True)
            data['sub_areas'] = [{'id': sa.id, 'name': sa.name} for sa in sub_areas]

        return data

    def _serialize_tag(self, tag) -> Dict:
        """Serialize a tag to dict."""
        return {
            'id': tag.id,
            'title': tag.name,
            'name': tag.name,
            'tag_type': tag.tag_type,
            'color': tag.color,
            'usage_count': tag.usage_count,
        }

    def _serialize_goal(self, goal, full: bool = False) -> Dict:
        """Serialize a goal to dict."""
        data = {
            'id': goal.id,
            'title': goal.title,
            'goal_type': goal.goal_type,
            'goal_type_display': goal.get_goal_type_display(),
            'year': goal.year,
            'quarter': goal.quarter,
            'month': goal.month,
            'period_display': goal.get_period_display(),
            'status': goal.status,
            'progress': goal.progress,
        }

        if full:
            data['description'] = goal.description
            data['key_results'] = goal.key_results
            data['parent_goal_id'] = goal.parent_goal_id
            data['linked_area_id'] = goal.linked_area_id
            data['linked_project_id'] = goal.linked_project_id
            data['sub_goal_count'] = goal.sub_goals.count()
            data['created_at'] = goal.created_at.isoformat() if goal.created_at else None
            data['updated_at'] = goal.updated_at.isoformat() if goal.updated_at else None

        return data

    def _serialize_daily_planner(self, entry, full: bool = False) -> Dict:
        """Serialize a daily planner entry to dict."""
        data = {
            'id': entry.id,
            'date': entry.date.isoformat(),
            'date_display': entry.date.strftime('%A, %B %d, %Y'),
            'is_morning_complete': entry.is_morning_complete,
            'is_evening_complete': entry.is_evening_complete,
            'completion_percentage': entry.get_completion_percentage(),
            'habits_completion': entry.get_habits_completion(),
        }

        if full:
            data['important_tasks'] = entry.important_tasks
            data['tasks_to_delegate'] = entry.tasks_to_delegate
            data['good_day_reward'] = entry.good_day_reward
            data['intention'] = entry.intention
            data['schedule_blocks'] = entry.schedule_blocks
            data['accomplishments'] = entry.accomplishments
            data['learnings'] = entry.learnings
            data['improvements'] = entry.improvements
            data['additional_notes'] = entry.additional_notes
            data['daily_habits'] = entry.daily_habits
            data['created_at'] = entry.created_at.isoformat() if entry.created_at else None
            data['updated_at'] = entry.updated_at.isoformat() if entry.updated_at else None

        return data

    def _serialize_weekly_planner(self, entry, full: bool = False) -> Dict:
        """Serialize a weekly planner entry to dict."""
        data = {
            'id': entry.id,
            'week_start': entry.week_start.isoformat(),
            'week_end': entry.week_end.isoformat(),
            'iso_week': entry.iso_week,
            'week_display': entry.get_week_display(),
            'is_planning_complete': entry.is_planning_complete,
            'is_review_complete': entry.is_review_complete,
            'completion_percentage': entry.get_completion_percentage(),
        }

        if full:
            data['weekly_goals'] = entry.weekly_goals
            data['top_priorities'] = entry.top_priorities
            data['projects_focus'] = entry.projects_focus
            data['habits_focus'] = entry.habits_focus
            data['week_plan'] = entry.week_plan
            data['week_rating'] = entry.week_rating
            data['accomplishments'] = entry.accomplishments
            data['lessons_learned'] = entry.lessons_learned
            data['priorities_completion'] = entry.get_priorities_completion()
            data['linked_monthly_goal_ids'] = list(entry.linked_monthly_goals.values_list('id', flat=True))
            data['created_at'] = entry.created_at.isoformat() if entry.created_at else None
            data['updated_at'] = entry.updated_at.isoformat() if entry.updated_at else None

        return data
