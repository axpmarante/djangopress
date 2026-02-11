"""
Areas Agent for Chat V4

Handles all area-related operations:
- CRUD operations for areas
- Hierarchical area management
- Area-project relationships

Architecture:
- Receives GOAL from planner
- Uses LLM to decide which action to take
- Executes action using handler methods
"""

import logging
from typing import Dict, List, Any, Optional

from .base import (
    BaseAgent, AgentContext, ActionDecision,
    DatabaseAgentMixin, ActionDispatcherMixin
)
from ..state import StepResult

logger = logging.getLogger(__name__)


class AreasAgent(BaseAgent, DatabaseAgentMixin, ActionDispatcherMixin):
    """
    Specialized agent for area operations.

    Receives goals like "Find the area named Health"
    and uses LLM to decide action (search) and params (query: "Health").
    """

    AGENT_TYPE = "areas"

    AVAILABLE_ACTIONS = [
        "create",
        "get",
        "update",
        "delete",
        "list",
        "search",
        "get_children",
        "get_projects",
        "get_review",
        "archive",
        "unarchive",
    ]

    AREA_FIELDS = [
        'id', 'name', 'description', 'color_code', 'icon',
        'parent_id', 'is_business_area', 'is_active',
        'created_at', 'updated_at'
    ]

    def get_actions_description(self) -> str:
        """Return description of available actions for LLM decision-making."""
        return """
### create
Create a new area.
Params:
- name (required): Area name
- description: Area description
- color_code: Hex color code (e.g., #4CAF50)
- icon: Icon name
- parent_id: ID of parent area for hierarchy
- is_business_area: true/false (default: false)

### get
Get an area by ID.
Params:
- area_id (required): The area ID
- include_children: true to include child areas
- include_projects: true to include projects

### update
Update an existing area.
Params:
- area_id (required): The area ID
- name: New name
- description: New description
- color_code: New color
- parent_id: New parent area

### delete
Delete an area.
Params:
- area_id (required): The area ID

### list
List areas with filters.
Params:
- parent_id: Filter by parent area
- is_business_area: Filter by business area flag
- is_active: true/false (default: true)
- limit: Max results (default: 50)

### search
Search areas by name or description.
Params:
- query (required): Search text
- limit: Max results (default: 20)

### get_children
Get child areas of a parent.
Params:
- area_id (required): Parent area ID

### get_projects
Get projects in an area.
Params:
- area_id (required): The area ID
- include_completed: true to include completed projects

### get_review
Get area review with projects, tasks, notes summary.
Params:
- area_id (required): The area ID

### archive
Archive an area.
Params:
- area_id (required): The area ID

### unarchive
Restore an archived area.
Params:
- area_id (required): The area ID
"""

    def _execute_action(self, context: AgentContext, decision: ActionDecision) -> StepResult:
        """Execute the decided action using dispatcher."""
        return self._dispatch_action(context, decision)

    # ========================================================================
    # Action Handlers
    # ========================================================================

    def _handle_create(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Create a new area"""
        from para.models import Area

        name = params.get('name')
        if not name:
            return self._error_result(context, "create", "Area name is required")

        try:
            area = Area.objects.create(
                user_id=context.user_id,
                name=name,
                description=params.get('description', ''),
                color_code=params.get('color_code', ''),
                icon=params.get('icon', ''),
                parent_id=params.get('parent_id'),
                is_business_area=params.get('is_business_area', False),
            )

            context.set_in_memory('created_area_id', area.id)
            context.set_in_memory('found_area_id', area.id)

            return self._success_result(
                context,
                action="create",
                output={'area': self._serialize_area(area)},
                summary=f"Created area '{area.name}'",
                entities={'area': [area.id]}
            )

        except Exception as e:
            logger.error(f"Area creation failed: {e}")
            return self._error_result(context, "create", str(e))

    def _handle_get(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Get an area by ID"""
        from para.models import Area

        area_id = params.get('area_id') or params.get('id')
        if not area_id:
            return self._error_result(context, "get", "Area ID is required")

        area = self._get_object_or_none(Area, context.user_id, area_id)
        if not area:
            return self._not_found_result(context, "get", "area", area_id)

        area_data = self._serialize_area(area)

        if params.get('include_children', False):
            children = area.children.filter(is_active=True)
            area_data['children'] = [self._serialize_area(c) for c in children]

        if params.get('include_projects', False):
            projects = area.projects.filter(is_archived=False)
            area_data['projects'] = [{'id': p.id, 'name': p.name, 'status': p.status} for p in projects]

        context.set_in_memory('found_area_id', area.id)

        return self._success_result(
            context,
            action="get",
            output={'area': area_data},
            summary=f"Found area '{area.name}'",
            entities={'area': [area.id]}
        )

    def _handle_update(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Update an area"""
        from para.models import Area

        area_id = params.get('area_id') or params.get('id')
        if not area_id:
            area_id = context.get_from_memory('created_area_id')

        if not area_id:
            return self._error_result(context, "update", "Area ID is required")

        area = self._get_object_or_none(Area, context.user_id, area_id)
        if not area:
            return self._not_found_result(context, "update", "area", area_id)

        updated_fields = []
        for field in ['name', 'description', 'color_code', 'icon', 'parent_id', 'is_business_area']:
            if params.get(field) is not None:
                setattr(area, field, params.get(field))
                updated_fields.append(field)

        if updated_fields:
            area.save()

        return self._success_result(
            context,
            action="update",
            output={'area': self._serialize_area(area), 'updated_fields': updated_fields},
            summary=f"Updated area '{area.name}' ({', '.join(updated_fields)})",
            entities={'area': [area.id]}
        )

    def _handle_delete(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Delete an area"""
        from para.models import Area

        area_id = params.get('area_id') or params.get('id')
        if not area_id:
            return self._error_result(context, "delete", "Area ID is required")

        area = self._get_object_or_none(Area, context.user_id, area_id)
        if not area:
            return self._not_found_result(context, "delete", "area", area_id)

        name = area.name
        area.delete()

        return self._success_result(
            context,
            action="delete",
            output={'deleted_id': area_id, 'name': name},
            summary=f"Deleted area '{name}'",
            entities={'area': [area_id]}
        )

    def _handle_list(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """List areas with optional filters"""
        from para.models import Area

        queryset = self._get_user_queryset(Area, context.user_id)

        filters = {}

        parent_id = params.get('parent_id')
        if parent_id:
            filters['parent_id'] = parent_id
        elif params.get('top_level', False):
            filters['parent_id__isnull'] = True

        is_business = params.get('is_business_area')
        if is_business is not None:
            filters['is_business_area'] = is_business

        is_active = params.get('is_active', True)
        filters['is_active'] = is_active

        queryset = self._apply_filters(queryset, filters)
        queryset = queryset.order_by('name')

        limit = params.get('limit', 50)
        areas = list(queryset[:limit])

        area_ids = [a.id for a in areas]
        context.set_in_memory('found_areas', area_ids)
        context.set_in_memory('found_area_ids', area_ids)

        return self._success_result(
            context,
            action="list",
            output={'areas': [self._serialize_area(a) for a in areas], 'count': len(areas)},
            summary=f"Found {len(areas)} area(s)",
            entities={'area': area_ids}
        )

    def _handle_search(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Search areas by query"""
        from para.models import Area
        from django.db.models import Q

        query = params.get('query') or params.get('q') or params.get('name')
        if not query:
            return self._error_result(context, "search", "Search query is required")

        queryset = self._get_user_queryset(Area, context.user_id)
        queryset = queryset.filter(Q(name__icontains=query) | Q(description__icontains=query))
        queryset = queryset.filter(is_active=True)

        limit = params.get('limit', 20)
        areas = list(queryset[:limit])

        area_ids = [a.id for a in areas]
        context.set_in_memory('found_areas', area_ids)
        context.set_in_memory('found_area_ids', area_ids)

        if len(areas) == 1:
            context.set_in_memory('found_area_id', areas[0].id)

        return self._success_result(
            context,
            action="search",
            output={'areas': [self._serialize_area(a) for a in areas], 'count': len(areas), 'query': query},
            summary=f"Found {len(areas)} area(s) matching '{query}'",
            entities={'area': area_ids}
        )

    def _handle_get_children(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Get child areas"""
        from para.models import Area

        area_id = params.get('area_id') or params.get('id')
        if not area_id:
            return self._error_result(context, "get_children", "Area ID is required")

        area = self._get_object_or_none(Area, context.user_id, area_id)
        if not area:
            return self._not_found_result(context, "get_children", "area", area_id)

        children = list(area.children.filter(is_active=True))

        return self._success_result(
            context,
            action="get_children",
            output={'area_id': area_id, 'children': [self._serialize_area(c) for c in children]},
            summary=f"Found {len(children)} child area(s) for '{area.name}'",
            entities={'area': [area_id] + [c.id for c in children]}
        )

    def _handle_get_projects(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Get projects in an area"""
        from para.models import Area

        area_id = params.get('area_id') or params.get('id')
        if not area_id:
            return self._error_result(context, "get_projects", "Area ID is required")

        area = self._get_object_or_none(Area, context.user_id, area_id)
        if not area:
            return self._not_found_result(context, "get_projects", "area", area_id)

        projects = area.projects.all()
        if not params.get('include_completed', False):
            projects = projects.exclude(status='completed')
        if not params.get('include_archived', False):
            projects = projects.filter(is_archived=False)

        projects_list = list(projects)

        return self._success_result(
            context,
            action="get_projects",
            output={
                'area_id': area_id,
                'area_name': area.name,
                'projects': [{'id': p.id, 'name': p.name, 'status': p.status} for p in projects_list]
            },
            summary=f"Found {len(projects_list)} project(s) in '{area.name}'",
            entities={'area': [area_id], 'project': [p.id for p in projects_list]}
        )

    def _handle_get_review(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Get area review with summary"""
        from para.models import Area
        from notes.models import Note, Task

        area_id = params.get('area_id') or params.get('id')
        if not area_id:
            return self._error_result(context, "get_review", "Area ID is required")

        area = self._get_object_or_none(Area, context.user_id, area_id)
        if not area:
            return self._not_found_result(context, "get_review", "area", area_id)

        # Get counts
        projects = area.projects.filter(is_archived=False)
        active_projects = projects.filter(status='active').count()
        completed_projects = projects.filter(status='completed').count()

        tasks = Task.objects.filter(user_id=context.user_id, container_type='area', container_id=area_id, is_archived=False)
        open_tasks = tasks.exclude(status='done').count()
        done_tasks = tasks.filter(status='done').count()

        notes = Note.objects.filter(user_id=context.user_id, container_type='area', container_id=area_id, is_archived=False)
        notes_count = notes.count()

        review = {
            'area': self._serialize_area(area),
            'projects': {'active': active_projects, 'completed': completed_projects},
            'tasks': {'open': open_tasks, 'done': done_tasks},
            'notes': {'count': notes_count}
        }

        return self._success_result(
            context,
            action="get_review",
            output=review,
            summary=f"Area '{area.name}': {active_projects} active projects, {open_tasks} open tasks",
            entities={'area': [area_id]}
        )

    def _handle_archive(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Archive an area"""
        from para.models import Area

        area_id = params.get('area_id') or params.get('id')
        if not area_id:
            return self._error_result(context, "archive", "Area ID is required")

        area = self._get_object_or_none(Area, context.user_id, area_id)
        if not area:
            return self._not_found_result(context, "archive", "area", area_id)

        area.is_active = False
        area.save()

        return self._success_result(
            context,
            action="archive",
            output={'area': self._serialize_area(area)},
            summary=f"Archived area '{area.name}'",
            entities={'area': [area.id]}
        )

    def _handle_unarchive(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Unarchive an area"""
        from para.models import Area

        area_id = params.get('area_id') or params.get('id')
        if not area_id:
            return self._error_result(context, "unarchive", "Area ID is required")

        area = self._get_object_or_none(Area, context.user_id, area_id)
        if not area:
            return self._not_found_result(context, "unarchive", "area", area_id)

        area.is_active = True
        area.save()

        return self._success_result(
            context,
            action="unarchive",
            output={'area': self._serialize_area(area)},
            summary=f"Unarchived area '{area.name}'",
            entities={'area': [area.id]}
        )

    # ========================================================================
    # Helpers
    # ========================================================================

    def _serialize_area(self, area) -> Dict[str, Any]:
        """Serialize an area to dict"""
        data = self._serialize_object(area, self.AREA_FIELDS)
        if area.parent:
            data['parent_name'] = area.parent.name
        return data
