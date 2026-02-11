"""
Projects Agent for Chat V4

Handles all project-related operations:
- CRUD operations for projects
- Status management (active, on_hold, completed, cancelled)
- Progress monitoring

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


class ProjectsAgent(BaseAgent, DatabaseAgentMixin, ActionDispatcherMixin):
    """
    Specialized agent for project operations.

    Receives goals like "Find the project named Work"
    and uses LLM to decide action (search) and params (query: "Work").
    """

    AGENT_TYPE = "projects"

    AVAILABLE_ACTIONS = [
        "create",
        "get",
        "update",
        "delete",
        "list",
        "search",
        "complete",
        "hold",
        "activate",
        "cancel",
        "archive",
        "unarchive",
        "get_status",
    ]

    PROJECT_FIELDS = [
        'id', 'name', 'description', 'status', 'area_id',
        'deadline', 'progress_percentage', 'completion_notes',
        'is_archived', 'created_at', 'updated_at'
    ]

    def get_actions_description(self) -> str:
        """Return description of available actions for LLM decision-making."""
        return """
### create
Create a new project.
Params:
- name (required): Project name
- description: Project description
- area_id: ID of the area this project belongs to
- status: active, on_hold (default: active)
- deadline: ISO date string (YYYY-MM-DD)

### get
Get a project by ID.
Params:
- project_id (required): The project ID
- include_tasks: true to include related tasks

### update
Update an existing project.
Params:
- project_id (required): The project ID
- name: New name
- description: New description
- status: New status
- deadline: New deadline
- progress_percentage: 0-100

### delete
Delete a project.
Params:
- project_id (required): The project ID

### list
List projects with filters.
Params:
- status: Filter by status (active, on_hold, completed, cancelled)
- area_id: Filter by area
- is_archived: true/false (default: false)
- limit: Max results (default: 50)

### search
Search projects by name or description.
Params:
- query (required): Search text
- limit: Max results (default: 20)

### complete
Mark a project as completed.
Params:
- project_id (required): The project ID
- completion_notes: Notes about completion

### hold
Put a project on hold.
Params:
- project_id (required): The project ID

### activate
Activate a project (set to active status).
Params:
- project_id (required): The project ID

### cancel
Cancel a project.
Params:
- project_id (required): The project ID

### archive
Archive a project.
Params:
- project_id (required): The project ID

### unarchive
Restore an archived project.
Params:
- project_id (required): The project ID

### get_status
Get project status with task counts and progress.
Params:
- project_id (required): The project ID
"""

    def _execute_action(self, context: AgentContext, decision: ActionDecision) -> StepResult:
        """Execute the decided action using dispatcher."""
        return self._dispatch_action(context, decision)

    # ========================================================================
    # Action Handlers - each receives (context, params)
    # ========================================================================

    def _handle_create(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Create a new project"""
        from para.models import Project

        name = params.get('name')
        if not name:
            return self._error_result(context, "create", "Project name is required")

        try:
            project = Project.objects.create(
                user_id=context.user_id,
                name=name,
                description=params.get('description', ''),
                area_id=params.get('area_id'),
                status=params.get('status', 'active'),
                deadline=self._parse_date(params.get('deadline')),
            )

            context.set_in_memory('created_project_id', project.id)
            context.set_in_memory('found_project_id', project.id)
            context.set_in_memory('last_project', self._serialize_project(project))

            return self._success_result(
                context,
                action="create",
                output={'project': self._serialize_project(project)},
                summary=f"Created project '{project.name}'",
                entities={'project': [project.id]}
            )

        except Exception as e:
            logger.error(f"Project creation failed: {e}")
            return self._error_result(context, "create", str(e))

    def _handle_get(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Get a project by ID"""
        from para.models import Project

        project_id = params.get('project_id') or params.get('id')
        if not project_id:
            return self._error_result(context, "get", "Project ID is required")

        project = self._get_object_or_none(Project, context.user_id, project_id)
        if not project:
            return self._not_found_result(context, "get", "project", project_id)

        project_data = self._serialize_project(project)

        # Include tasks if requested
        if params.get('include_tasks', False):
            from notes.models import Task
            tasks = Task.objects.filter(
                user_id=context.user_id,
                container_type='project',
                container_id=project_id
            )
            project_data['tasks'] = [
                {'id': t.id, 'title': t.title, 'status': t.status}
                for t in tasks
            ]

        context.set_in_memory('found_project_id', project.id)

        return self._success_result(
            context,
            action="get",
            output={'project': project_data},
            summary=f"Found project '{project.name}'",
            entities={'project': [project.id]}
        )

    def _handle_update(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Update a project"""
        from para.models import Project

        project_id = params.get('project_id') or params.get('id')
        if not project_id:
            project_id = context.get_from_memory('created_project_id')

        if not project_id:
            return self._error_result(context, "update", "Project ID is required")

        project = self._get_object_or_none(Project, context.user_id, project_id)
        if not project:
            return self._not_found_result(context, "update", "project", project_id)

        updated_fields = []
        for field in ['name', 'description', 'status', 'area_id', 'progress_percentage', 'completion_notes']:
            if params.get(field) is not None:
                setattr(project, field, params.get(field))
                updated_fields.append(field)

        if params.get('deadline') is not None:
            project.deadline = self._parse_date(params.get('deadline'))
            updated_fields.append('deadline')

        if updated_fields:
            project.save()

        return self._success_result(
            context,
            action="update",
            output={'project': self._serialize_project(project), 'updated_fields': updated_fields},
            summary=f"Updated project '{project.name}' ({', '.join(updated_fields)})",
            entities={'project': [project.id]}
        )

    def _handle_delete(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Delete a project"""
        from para.models import Project

        project_id = params.get('project_id') or params.get('id')
        if not project_id:
            return self._error_result(context, "delete", "Project ID is required")

        project = self._get_object_or_none(Project, context.user_id, project_id)
        if not project:
            return self._not_found_result(context, "delete", "project", project_id)

        name = project.name
        project.delete()

        return self._success_result(
            context,
            action="delete",
            output={'deleted_id': project_id, 'name': name},
            summary=f"Deleted project '{name}'",
            entities={'project': [project_id]}
        )

    def _handle_list(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """List projects with optional filters"""
        from para.models import Project

        queryset = self._get_user_queryset(Project, context.user_id)

        filters = {}

        status = params.get('status')
        if status:
            filters['status'] = status

        area_id = params.get('area_id')
        if area_id:
            filters['area_id'] = area_id

        is_archived = params.get('is_archived', False)
        filters['is_archived'] = is_archived

        queryset = self._apply_filters(queryset, filters)

        order_by = params.get('order_by', '-created_at')
        queryset = queryset.order_by(order_by)

        limit = params.get('limit', 50)
        projects = list(queryset[:limit])

        project_ids = [p.id for p in projects]
        context.set_in_memory('found_projects', project_ids)
        context.set_in_memory('found_project_ids', project_ids)

        return self._success_result(
            context,
            action="list",
            output={
                'projects': [self._serialize_project(p) for p in projects],
                'count': len(projects),
                'project_ids': project_ids
            },
            summary=f"Found {len(projects)} project(s)",
            entities={'project': project_ids}
        )

    def _handle_search(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Search projects by query"""
        from para.models import Project
        from django.db.models import Q

        query = params.get('query') or params.get('q') or params.get('name')
        if not query:
            return self._error_result(context, "search", "Search query is required")

        queryset = self._get_user_queryset(Project, context.user_id)
        queryset = queryset.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )

        is_archived = params.get('is_archived', False)
        queryset = queryset.filter(is_archived=is_archived)

        limit = params.get('limit', 20)
        projects = list(queryset[:limit])

        project_ids = [p.id for p in projects]
        context.set_in_memory('found_projects', project_ids)
        context.set_in_memory('found_project_ids', project_ids)

        # If we found exactly one, also set it as the found project
        if len(projects) == 1:
            context.set_in_memory('found_project_id', projects[0].id)

        return self._success_result(
            context,
            action="search",
            output={
                'projects': [self._serialize_project(p) for p in projects],
                'count': len(projects),
                'query': query
            },
            summary=f"Found {len(projects)} project(s) matching '{query}'",
            entities={'project': project_ids}
        )

    def _handle_complete(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Mark project as completed"""
        from para.models import Project

        project_id = params.get('project_id') or params.get('id')
        if not project_id:
            return self._error_result(context, "complete", "Project ID is required")

        project = self._get_object_or_none(Project, context.user_id, project_id)
        if not project:
            return self._not_found_result(context, "complete", "project", project_id)

        project.status = 'completed'
        project.progress_percentage = 100
        project.completion_notes = params.get('completion_notes', '')
        project.save()

        return self._success_result(
            context,
            action="complete",
            output={'project': self._serialize_project(project)},
            summary=f"Completed project '{project.name}'",
            entities={'project': [project.id]}
        )

    def _handle_hold(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Put project on hold"""
        from para.models import Project

        project_id = params.get('project_id') or params.get('id')
        if not project_id:
            return self._error_result(context, "hold", "Project ID is required")

        project = self._get_object_or_none(Project, context.user_id, project_id)
        if not project:
            return self._not_found_result(context, "hold", "project", project_id)

        project.status = 'on_hold'
        project.save()

        return self._success_result(
            context,
            action="hold",
            output={'project': self._serialize_project(project)},
            summary=f"Put project '{project.name}' on hold",
            entities={'project': [project.id]}
        )

    def _handle_activate(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Activate a project"""
        from para.models import Project

        project_id = params.get('project_id') or params.get('id')
        if not project_id:
            return self._error_result(context, "activate", "Project ID is required")

        project = self._get_object_or_none(Project, context.user_id, project_id)
        if not project:
            return self._not_found_result(context, "activate", "project", project_id)

        project.status = 'active'
        project.save()

        return self._success_result(
            context,
            action="activate",
            output={'project': self._serialize_project(project)},
            summary=f"Activated project '{project.name}'",
            entities={'project': [project.id]}
        )

    def _handle_cancel(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Cancel a project"""
        from para.models import Project

        project_id = params.get('project_id') or params.get('id')
        if not project_id:
            return self._error_result(context, "cancel", "Project ID is required")

        project = self._get_object_or_none(Project, context.user_id, project_id)
        if not project:
            return self._not_found_result(context, "cancel", "project", project_id)

        project.status = 'cancelled'
        project.save()

        return self._success_result(
            context,
            action="cancel",
            output={'project': self._serialize_project(project)},
            summary=f"Cancelled project '{project.name}'",
            entities={'project': [project.id]}
        )

    def _handle_archive(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Archive a project"""
        from para.models import Project

        project_id = params.get('project_id') or params.get('id')
        if not project_id:
            return self._error_result(context, "archive", "Project ID is required")

        project = self._get_object_or_none(Project, context.user_id, project_id)
        if not project:
            return self._not_found_result(context, "archive", "project", project_id)

        project.is_archived = True
        project.save()

        return self._success_result(
            context,
            action="archive",
            output={'project': self._serialize_project(project)},
            summary=f"Archived project '{project.name}'",
            entities={'project': [project.id]}
        )

    def _handle_unarchive(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Unarchive a project"""
        from para.models import Project

        project_id = params.get('project_id') or params.get('id')
        if not project_id:
            return self._error_result(context, "unarchive", "Project ID is required")

        project = self._get_object_or_none(Project, context.user_id, project_id)
        if not project:
            return self._not_found_result(context, "unarchive", "project", project_id)

        project.is_archived = False
        project.save()

        return self._success_result(
            context,
            action="unarchive",
            output={'project': self._serialize_project(project)},
            summary=f"Unarchived project '{project.name}'",
            entities={'project': [project.id]}
        )

    def _handle_get_status(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Get project status with task counts and progress"""
        from para.models import Project
        from notes.models import Task

        project_id = params.get('project_id') or params.get('id')
        if not project_id:
            return self._error_result(context, "get_status", "Project ID is required")

        project = self._get_object_or_none(Project, context.user_id, project_id)
        if not project:
            return self._not_found_result(context, "get_status", "project", project_id)

        # Get task counts
        tasks = Task.objects.filter(
            user_id=context.user_id,
            container_type='project',
            container_id=project_id
        )

        total_tasks = tasks.count()
        completed_tasks = tasks.filter(status='done').count()
        in_progress_tasks = tasks.filter(status='in_progress').count()
        overdue_tasks = tasks.filter(
            status__in=['todo', 'in_progress', 'waiting'],
            due_date__lt=datetime.now()
        ).count()

        progress = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

        status_data = {
            'project': self._serialize_project(project),
            'task_stats': {
                'total': total_tasks,
                'completed': completed_tasks,
                'in_progress': in_progress_tasks,
                'overdue': overdue_tasks,
                'remaining': total_tasks - completed_tasks
            },
            'progress_percentage': round(progress, 1)
        }

        context.set_in_memory('found_project_id', project.id)

        return self._success_result(
            context,
            action="get_status",
            output=status_data,
            summary=f"Project '{project.name}': {completed_tasks}/{total_tasks} tasks complete ({round(progress)}%)",
            entities={'project': [project.id]}
        )

    # ========================================================================
    # Helpers
    # ========================================================================

    def _serialize_project(self, project) -> Dict[str, Any]:
        """Serialize a project to dict"""
        data = self._serialize_object(project, self.PROJECT_FIELDS)
        if project.area:
            data['area_name'] = project.area.name
        return data

    def _parse_date(self, value) -> Optional[date]:
        """Parse date from various formats"""
        if not value:
            return None

        if isinstance(value, date):
            return value

        if isinstance(value, datetime):
            return value.date()

        if isinstance(value, str):
            value_lower = value.lower()
            today = date.today()

            if value_lower == 'today':
                return today
            elif value_lower == 'tomorrow':
                return today + timedelta(days=1)
            elif value_lower == 'next week':
                return today + timedelta(days=7)
            elif value_lower == 'next month':
                return today + timedelta(days=30)

            try:
                return datetime.fromisoformat(value).date()
            except ValueError:
                pass

            for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y']:
                try:
                    return datetime.strptime(value, fmt).date()
                except ValueError:
                    continue

        return None
