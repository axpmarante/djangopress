"""
Chat V2 Execute Tool

Mutation operations that change data. Includes:
- CRUD: create, update, delete, archive
- Actions: move, complete, start
- External: send_email, webhook (future)
"""

from typing import Dict, Any, List, Optional
from datetime import timedelta
from django.utils import timezone
from django.db import transaction

from .base import BaseTool, ToolCall, ToolResult, ToolStatus


class ExecuteTool(BaseTool):
    """
    Execute tool for mutations and actions.

    All operations that create, modify, or delete data.
    """

    name = "execute_tool"
    actions = [
        # CRUD
        "create",
        "update",
        "delete",
        "archive",
        # Actions
        "move",
        "complete",
        "start",
        "uncomplete",
        # Tags
        "add_tags",
        "remove_tags",
        # Subtasks
        "create_subtask",
        "list_subtasks",
        "complete_subtask",
        "uncomplete_subtask",
        "update_subtask",
        "delete_subtask",
        # Goals
        "complete_goal",
        "abandon_goal",
        # Daily Planner
        "toggle_habit",
    ]
    resource_types = ["note", "task", "project", "area", "tag", "subtask", "goal", "daily_planner", "weekly_planner"]

    # Actions that require confirmation
    CONFIRM_ACTIONS = ["delete"]

    def execute(self, call: ToolCall) -> ToolResult:
        """Execute a mutation action."""
        action = call.action
        resource_type = call.resource_type
        params = call.params

        # Route to appropriate handler
        if action == "create":
            return self._create(resource_type, params)
        elif action == "update":
            return self._update(resource_type, params)
        elif action == "delete":
            return self._delete(resource_type, params)
        elif action == "archive":
            return self._archive(resource_type, params)
        elif action == "move":
            return self._move(resource_type, params)
        elif action == "complete":
            return self._complete(params)
        elif action == "start":
            return self._start(params)
        elif action == "uncomplete":
            return self._uncomplete(params)
        elif action == "add_tags":
            return self._add_tags(resource_type, params)
        elif action == "remove_tags":
            return self._remove_tags(resource_type, params)
        # Subtask actions
        elif action == "create_subtask":
            return self._create_subtask(params)
        elif action == "list_subtasks":
            return self._list_subtasks(params)
        elif action == "complete_subtask":
            return self._complete_subtask(params)
        elif action == "uncomplete_subtask":
            return self._uncomplete_subtask(params)
        elif action == "update_subtask":
            return self._update_subtask(params)
        elif action == "delete_subtask":
            return self._delete_subtask(params)
        # Goal actions
        elif action == "complete_goal":
            return self._complete_goal(params)
        elif action == "abandon_goal":
            return self._abandon_goal(params)
        # Daily planner actions
        elif action == "toggle_habit":
            return self._toggle_habit(params)
        else:
            return self._result(
                ToolStatus.ERROR,
                error=f"Unknown action: {action}",
                action=action
            )

    # =========================================================================
    # Create Action
    # =========================================================================

    def _create(self, resource_type: str, params: Dict[str, Any]) -> ToolResult:
        """
        Create a new item.

        Params vary by resource_type:
        - note: title, content, note_type, tags[], container_type, container_id
        - task: title, content, due_date, priority, tags[], container_type, container_id
        - project: name, description, area_id, deadline
        - area: name, description, maintenance_standard
        - tag: name, color, tag_type
        """
        try:
            with transaction.atomic():
                if resource_type == "note":
                    return self._create_note(params)
                elif resource_type == "task":
                    return self._create_task(params)
                elif resource_type == "project":
                    return self._create_project(params)
                elif resource_type == "area":
                    return self._create_area(params)
                elif resource_type == "tag":
                    return self._create_tag(params)
                elif resource_type == "goal":
                    return self._create_goal(params)
                elif resource_type == "daily_planner":
                    return self._create_daily_planner(params)
                elif resource_type == "weekly_planner":
                    return self._create_weekly_planner(params)
                else:
                    return self._result(
                        ToolStatus.VALIDATION_ERROR,
                        error=f"Cannot create resource type: {resource_type}",
                        action="create"
                    )
        except Exception as e:
            return self._result(
                ToolStatus.ERROR,
                error=str(e),
                action="create",
                resource_type=resource_type
            )

    def _create_note(self, params: Dict) -> ToolResult:
        """Create a new note."""
        from notes.models import Note

        title = params.get("title", "Untitled Note")
        content = params.get("content", "")
        note_type = params.get("note_type", "note")

        # Validate note_type (task is not a valid note type - use Task model instead)
        valid_note_types = ['note', 'checklist', 'meeting', 'resource']
        if note_type not in valid_note_types:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error=f"Invalid note_type '{note_type}'. Valid types: {', '.join(valid_note_types)}. Use create action with resource_type='task' to create tasks.",
                action="create",
                resource_type="note"
            )

        note = Note.objects.create(
            user=self.user,
            title=title,
            content=content,
            note_type=note_type,
            container_type=params.get("container_type", "inbox"),
            container_id=params.get("container_id"),
            capture_date=timezone.now(),
        )

        # Add tags
        if params.get("tags"):
            self._apply_tags(note, params["tags"])

        return self._result(
            ToolStatus.SUCCESS,
            data={"id": note.id, "title": note.title, "type": note.note_type},
            message=f"Created note '{note.title}' (ID: {note.id})",
            action="create",
            resource_type="note"
        )

    def _create_task(self, params: Dict) -> ToolResult:
        """Create a new task using the Task model."""
        from tasks.models import Task

        title = params.get("title", "Untitled Task")

        # Parse due date
        due_date = None
        if params.get("due_date"):
            due_date = self._parse_date(params["due_date"])

        task = Task.objects.create(
            user=self.user,
            title=title,
            description=params.get("content", ""),
            status=params.get("status", "todo"),
            priority=params.get("priority", "medium"),
            due_date=due_date,
            container_type=params.get("container_type", "inbox"),
            container_id=params.get("container_id"),
        )

        # Add tags
        if params.get("tags"):
            self._apply_task_tags(task, params["tags"])

        return self._result(
            ToolStatus.SUCCESS,
            data={
                "id": task.id,
                "title": task.title,
                "status": task.status,
                "priority": task.priority,
                "due_date": task.due_date.isoformat() if task.due_date else None
            },
            message=f"Created task '{task.title}' (ID: {task.id})",
            action="create",
            resource_type="task"
        )

    def _create_project(self, params: Dict) -> ToolResult:
        """Create a new project."""
        from para.models import Project, Area

        name = params.get("name")
        if not name:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error="'name' is required for creating a project",
                action="create",
                resource_type="project"
            )

        area_id = params.get("area_id")
        if not area_id:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error="'area_id' is required for creating a project",
                action="create",
                resource_type="project"
            )

        # Verify area exists
        try:
            area = Area.objects.get(id=area_id, user=self.user)
        except Area.DoesNotExist:
            return self._result(
                ToolStatus.NOT_FOUND,
                error=f"Area with ID {area_id} not found",
                action="create",
                resource_type="project"
            )

        # Parse deadline
        deadline = None
        if params.get("deadline"):
            deadline = self._parse_date(params["deadline"])

        project = Project.objects.create(
            user=self.user,
            name=name,
            area=area,
            description=params.get("description", ""),
            deadline=deadline,
            status="active",
        )

        return self._result(
            ToolStatus.SUCCESS,
            data={
                "id": project.id,
                "name": project.name,
                "area_id": area.id,
                "area_name": area.name,
                "deadline": project.deadline.isoformat() if project.deadline else None
            },
            message=f"Created project '{project.name}' in area '{area.name}' (ID: {project.id})",
            action="create",
            resource_type="project"
        )

    def _create_area(self, params: Dict) -> ToolResult:
        """Create a new area."""
        from para.models import Area

        name = params.get("name")
        if not name:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error="'name' is required for creating an area",
                action="create",
                resource_type="area"
            )

        # Handle parent area for sub-areas
        parent_id = params.get("parent_id")
        parent = None
        if parent_id:
            try:
                parent = Area.objects.get(id=parent_id, user=self.user)
            except Area.DoesNotExist:
                return self._result(
                    ToolStatus.NOT_FOUND,
                    error=f"Parent area with ID {parent_id} not found",
                    action="create",
                    resource_type="area"
                )

        area = Area.objects.create(
            user=self.user,
            name=name,
            description=params.get("description", ""),
            parent=parent,
            is_business_area=params.get("is_business_area", False),
            area_type=params.get("area_type", "general"),
            is_active=True,
        )

        return self._result(
            ToolStatus.SUCCESS,
            data={"id": area.id, "name": area.name},
            message=f"Created area '{area.name}' (ID: {area.id})",
            action="create",
            resource_type="area"
        )

    def _create_tag(self, params: Dict) -> ToolResult:
        """Create a new tag."""
        from notes.models import Tag

        name = params.get("name")
        if not name:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error="'name' is required for creating a tag",
                action="create",
                resource_type="tag"
            )

        tag, created = Tag.objects.get_or_create(
            name=name.lower(),
            defaults={
                "color": params.get("color", "#808080"),
                "tag_type": params.get("tag_type", "topic"),
            }
        )

        if not created:
            return self._result(
                ToolStatus.SUCCESS,
                data={"id": tag.id, "name": tag.name, "existed": True},
                message=f"Tag '{tag.name}' already exists (ID: {tag.id})",
                action="create",
                resource_type="tag"
            )

        return self._result(
            ToolStatus.SUCCESS,
            data={"id": tag.id, "name": tag.name},
            message=f"Created tag '{tag.name}' (ID: {tag.id})",
            action="create",
            resource_type="tag"
        )

    # =========================================================================
    # Update Action
    # =========================================================================

    def _update(self, resource_type: str, params: Dict[str, Any]) -> ToolResult:
        """
        Update an existing item.

        Params:
            id: int - Item ID (required)
            patch: dict - Fields to update
        """
        item_id = params.get("id")
        patch = params.get("patch", params)  # Allow flat params or nested patch

        if not item_id:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error="'id' is required for update",
                action="update",
                resource_type=resource_type
            )

        try:
            with transaction.atomic():
                if resource_type == "note":
                    return self._update_note(item_id, patch)
                elif resource_type == "task":
                    return self._update_task(item_id, patch)
                elif resource_type == "project":
                    return self._update_project(item_id, patch)
                elif resource_type == "area":
                    return self._update_area(item_id, patch)
                elif resource_type == "goal":
                    return self._update_goal(item_id, patch)
                elif resource_type == "daily_planner":
                    return self._update_daily_planner(item_id, patch)
                elif resource_type == "weekly_planner":
                    return self._update_weekly_planner(item_id, patch)
                else:
                    return self._result(
                        ToolStatus.VALIDATION_ERROR,
                        error=f"Cannot update resource type: {resource_type}",
                        action="update"
                    )
        except Exception as e:
            return self._result(
                ToolStatus.ERROR,
                error=str(e),
                action="update",
                resource_type=resource_type
            )

    def _update_note(self, note_id: int, patch: Dict) -> ToolResult:
        """Update a note."""
        from notes.models import Note

        try:
            note = Note.objects.get(id=note_id, user=self.user)
        except Note.DoesNotExist:
            return self._result(
                ToolStatus.NOT_FOUND,
                error=f"Note with ID {note_id} not found",
                action="update",
                resource_type="note"
            )

        # Apply updates
        if "title" in patch:
            note.title = patch["title"]
        if "content" in patch:
            note.content = patch["content"]
        if "note_type" in patch:
            note.note_type = patch["note_type"]
        if "is_archived" in patch:
            note.is_archived = patch["is_archived"]

        note.save()

        # Update tags if provided
        if "tags" in patch:
            self._apply_tags(note, patch["tags"])

        return self._result(
            ToolStatus.SUCCESS,
            data={"id": note.id, "title": note.title},
            message=f"Updated note '{note.title}' (ID: {note.id})",
            action="update",
            resource_type="note"
        )

    def _update_task(self, task_id: int, patch: Dict) -> ToolResult:
        """Update a task using Task model."""
        from tasks.models import Task

        try:
            task = Task.objects.get(id=task_id, user=self.user)
        except Task.DoesNotExist:
            return self._result(
                ToolStatus.NOT_FOUND,
                error=f"Task with ID {task_id} not found",
                action="update",
                resource_type="task"
            )

        # Apply updates
        if "title" in patch:
            task.title = patch["title"]
        if "content" in patch or "description" in patch:
            task.description = patch.get("description", patch.get("content", ""))
        if "status" in patch:
            task.status = patch["status"]
            if patch["status"] == "done":
                task.completed_at = timezone.now()
            else:
                task.completed_at = None
        if "priority" in patch:
            task.priority = patch["priority"]
        if "due_date" in patch:
            task.due_date = self._parse_date(patch["due_date"])
        if "is_archived" in patch:
            task.is_archived = patch["is_archived"]
        # Waiting status fields
        if "waiting_on" in patch:
            task.waiting_on = patch["waiting_on"]
        if "follow_up_date" in patch:
            task.follow_up_date = self._parse_date(patch["follow_up_date"])

        task.save()

        # Update tags if provided
        if "tags" in patch:
            self._apply_task_tags(task, patch["tags"])

        return self._result(
            ToolStatus.SUCCESS,
            data={"id": task.id, "title": task.title, "status": task.status},
            message=f"Updated task '{task.title}' (ID: {task.id})",
            action="update",
            resource_type="task"
        )

    def _update_project(self, project_id: int, patch: Dict) -> ToolResult:
        """Update a project."""
        from para.models import Project

        try:
            project = Project.objects.get(id=project_id, user=self.user)
        except Project.DoesNotExist:
            return self._result(
                ToolStatus.NOT_FOUND,
                error=f"Project with ID {project_id} not found",
                action="update",
                resource_type="project"
            )

        if "name" in patch:
            project.name = patch["name"]
        if "description" in patch:
            project.description = patch["description"]
        if "status" in patch:
            project.status = patch["status"]
        if "deadline" in patch:
            project.deadline = self._parse_date(patch["deadline"])
        if "progress_percentage" in patch:
            project.progress_percentage = patch["progress_percentage"]

        project.save()

        return self._result(
            ToolStatus.SUCCESS,
            data={"id": project.id, "name": project.name},
            message=f"Updated project '{project.name}' (ID: {project.id})",
            action="update",
            resource_type="project"
        )

    def _update_area(self, area_id: int, patch: Dict) -> ToolResult:
        """Update an area."""
        from para.models import Area

        try:
            area = Area.objects.get(id=area_id, user=self.user)
        except Area.DoesNotExist:
            return self._result(
                ToolStatus.NOT_FOUND,
                error=f"Area with ID {area_id} not found",
                action="update",
                resource_type="area"
            )

        if "name" in patch:
            area.name = patch["name"]
        if "description" in patch:
            area.description = patch["description"]
        if "is_business_area" in patch:
            area.is_business_area = patch["is_business_area"]
        if "area_type" in patch:
            area.area_type = patch["area_type"]
        if "parent_id" in patch:
            if patch["parent_id"]:
                try:
                    parent = Area.objects.get(id=patch["parent_id"], user=self.user)
                    area.parent = parent
                except Area.DoesNotExist:
                    pass
            else:
                area.parent = None

        area.save()

        return self._result(
            ToolStatus.SUCCESS,
            data={"id": area.id, "name": area.name},
            message=f"Updated area '{area.name}' (ID: {area.id})",
            action="update",
            resource_type="area"
        )

    # =========================================================================
    # Delete Action (Soft Delete)
    # =========================================================================

    def _delete(self, resource_type: str, params: Dict[str, Any]) -> ToolResult:
        """
        Soft delete (archive) an item.

        Params:
            id: int - Item ID (required)
        """
        # For now, delete is the same as archive (soft delete)
        return self._archive(resource_type, params)

    # =========================================================================
    # Archive Action
    # =========================================================================

    def _archive(self, resource_type: str, params: Dict[str, Any]) -> ToolResult:
        """
        Archive an item (soft delete).

        Params:
            id: int - Item ID (required)
        """
        item_id = params.get("id")
        if not item_id:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error="'id' is required for archive",
                action="archive",
                resource_type=resource_type
            )

        try:
            if resource_type == "note":
                return self._archive_note(item_id)
            elif resource_type == "task":
                return self._archive_task(item_id)
            elif resource_type == "project":
                return self._archive_project(item_id)
            elif resource_type == "area":
                return self._archive_area(item_id)
            else:
                return self._result(
                    ToolStatus.VALIDATION_ERROR,
                    error=f"Cannot archive resource type: {resource_type}",
                    action="archive"
                )
        except Exception as e:
            return self._result(
                ToolStatus.ERROR,
                error=str(e),
                action="archive",
                resource_type=resource_type
            )

    def _archive_note(self, note_id: int) -> ToolResult:
        """Archive a note."""
        from notes.models import Note

        try:
            note = Note.objects.get(id=note_id, user=self.user)
        except Note.DoesNotExist:
            return self._result(
                ToolStatus.NOT_FOUND,
                error=f"Note with ID {note_id} not found",
                action="archive",
                resource_type="note"
            )

        note.is_archived = True
        note.save(update_fields=['is_archived', 'updated_at'])

        return self._result(
            ToolStatus.SUCCESS,
            data={"id": note.id, "title": note.title},
            message=f"Archived note '{note.title}' (ID: {note.id})",
            action="archive",
            resource_type="note"
        )

    def _archive_task(self, task_id: int) -> ToolResult:
        """Archive a task."""
        from tasks.models import Task

        try:
            task = Task.objects.get(id=task_id, user=self.user)
        except Task.DoesNotExist:
            return self._result(
                ToolStatus.NOT_FOUND,
                error=f"Task with ID {task_id} not found",
                action="archive",
                resource_type="task"
            )

        task.archive()

        return self._result(
            ToolStatus.SUCCESS,
            data={"id": task.id, "title": task.title},
            message=f"Archived task '{task.title}' (ID: {task.id})",
            action="archive",
            resource_type="task"
        )

    def _archive_project(self, project_id: int) -> ToolResult:
        """Archive a project."""
        from para.models import Project

        try:
            project = Project.objects.get(id=project_id, user=self.user)
        except Project.DoesNotExist:
            return self._result(
                ToolStatus.NOT_FOUND,
                error=f"Project with ID {project_id} not found",
                action="archive",
                resource_type="project"
            )

        project.status = 'archived'
        project.save(update_fields=['status', 'updated_at'])

        return self._result(
            ToolStatus.SUCCESS,
            data={"id": project.id, "name": project.name},
            message=f"Archived project '{project.name}' (ID: {project.id})",
            action="archive",
            resource_type="project"
        )

    def _archive_area(self, area_id: int) -> ToolResult:
        """Archive an area."""
        from para.models import Area

        try:
            area = Area.objects.get(id=area_id, user=self.user)
        except Area.DoesNotExist:
            return self._result(
                ToolStatus.NOT_FOUND,
                error=f"Area with ID {area_id} not found",
                action="archive",
                resource_type="area"
            )

        area.is_active = False
        area.save(update_fields=['is_active', 'updated_at'])

        return self._result(
            ToolStatus.SUCCESS,
            data={"id": area.id, "name": area.name},
            message=f"Archived area '{area.name}' (ID: {area.id})",
            action="archive",
            resource_type="area"
        )

    # =========================================================================
    # Move Action
    # =========================================================================

    def _move(self, resource_type: str, params: Dict[str, Any]) -> ToolResult:
        """
        Move an item to a different container.

        Params:
            id: int - Item ID (required)
            container_type: str - Target container type (project, area, inbox)
            container_id: int - Target container ID (not needed for inbox)
        """
        item_id = params.get("id")
        container_type = params.get("container_type")
        container_id = params.get("container_id")

        if not item_id:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error="'id' is required for move",
                action="move",
                resource_type=resource_type
            )

        if not container_type:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error="'container_type' is required for move",
                action="move",
                resource_type=resource_type
            )

        if resource_type not in ["note", "task"]:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error=f"Cannot move resource type: {resource_type}",
                action="move"
            )

        # Validate container exists
        if container_type == "project":
            from para.models import Project
            if not Project.objects.filter(id=container_id, user=self.user).exists():
                return self._result(
                    ToolStatus.NOT_FOUND,
                    error=f"Project with ID {container_id} not found",
                    action="move",
                    resource_type=resource_type
                )
        elif container_type == "area":
            from para.models import Area
            if not Area.objects.filter(id=container_id, user=self.user).exists():
                return self._result(
                    ToolStatus.NOT_FOUND,
                    error=f"Area with ID {container_id} not found",
                    action="move",
                    resource_type=resource_type
                )

        try:
            if resource_type == "task":
                from tasks.models import Task
                task = Task.objects.get(id=item_id, user=self.user)
                task.move_to(container_type, container_id if container_type != "inbox" else None)
                return self._result(
                    ToolStatus.SUCCESS,
                    data={
                        "id": task.id,
                        "title": task.title,
                        "container_type": task.container_type,
                        "container_id": task.container_id
                    },
                    message=f"Moved task '{task.title}' to {container_type} (ID: {container_id})",
                    action="move",
                    resource_type="task"
                )
            else:
                from notes.models import Note
                note = Note.objects.get(id=item_id, user=self.user)
                note.container_type = container_type
                note.container_id = container_id if container_type != "inbox" else None
                note.save()
                return self._result(
                    ToolStatus.SUCCESS,
                    data={
                        "id": note.id,
                        "title": note.title,
                        "container_type": note.container_type,
                        "container_id": note.container_id
                    },
                    message=f"Moved note '{note.title}' to {container_type} (ID: {container_id})",
                    action="move",
                    resource_type="note"
                )

        except Exception as e:
            return self._result(
                ToolStatus.NOT_FOUND,
                error=f"{resource_type.capitalize()} with ID {item_id} not found",
                action="move",
                resource_type=resource_type
            )

    # =========================================================================
    # Task-specific Actions
    # =========================================================================

    def _complete(self, params: Dict[str, Any]) -> ToolResult:
        """Mark a task as complete."""
        task_id = params.get("id")
        if not task_id:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error="'id' is required for complete",
                action="complete",
                resource_type="task"
            )

        try:
            from tasks.models import Task

            task = Task.objects.get(id=task_id, user=self.user)
            task.mark_done()

            return self._result(
                ToolStatus.SUCCESS,
                data={"id": task.id, "title": task.title, "status": "done"},
                message=f"Completed task '{task.title}' (ID: {task.id})",
                action="complete",
                resource_type="task"
            )

        except Task.DoesNotExist:
            return self._result(
                ToolStatus.NOT_FOUND,
                error=f"Task with ID {task_id} not found",
                action="complete",
                resource_type="task"
            )

    def _start(self, params: Dict[str, Any]) -> ToolResult:
        """Mark a task as in progress."""
        task_id = params.get("id")
        if not task_id:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error="'id' is required for start",
                action="start",
                resource_type="task"
            )

        try:
            from tasks.models import Task

            task = Task.objects.get(id=task_id, user=self.user)
            task.start()

            return self._result(
                ToolStatus.SUCCESS,
                data={"id": task.id, "title": task.title, "status": "in_progress"},
                message=f"Started task '{task.title}' (ID: {task.id})",
                action="start",
                resource_type="task"
            )

        except Task.DoesNotExist:
            return self._result(
                ToolStatus.NOT_FOUND,
                error=f"Task with ID {task_id} not found",
                action="start",
                resource_type="task"
            )

    def _uncomplete(self, params: Dict[str, Any]) -> ToolResult:
        """Reopen a completed task."""
        task_id = params.get("id")
        if not task_id:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error="'id' is required for uncomplete",
                action="uncomplete",
                resource_type="task"
            )

        try:
            from tasks.models import Task

            task = Task.objects.get(id=task_id, user=self.user)
            task.mark_todo()

            return self._result(
                ToolStatus.SUCCESS,
                data={"id": task.id, "title": task.title, "status": "todo"},
                message=f"Reopened task '{task.title}' (ID: {task.id})",
                action="uncomplete",
                resource_type="task"
            )

        except Task.DoesNotExist:
            return self._result(
                ToolStatus.NOT_FOUND,
                error=f"Task with ID {task_id} not found",
                action="uncomplete",
                resource_type="task"
            )

    # =========================================================================
    # Tag Actions
    # =========================================================================

    def _add_tags(self, resource_type: str, params: Dict[str, Any]) -> ToolResult:
        """Add tags to an item."""
        item_id = params.get("id")
        tags = params.get("tags", [])

        if not item_id:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error="'id' is required",
                action="add_tags",
                resource_type=resource_type
            )

        if not tags:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error="'tags' array is required",
                action="add_tags",
                resource_type=resource_type
            )

        try:
            from notes.models import Note

            note = Note.objects.get(id=item_id, user=self.user)
            self._apply_tags(note, tags, clear_existing=False)

            return self._result(
                ToolStatus.SUCCESS,
                data={"id": note.id, "tags": list(note.tags.values_list('name', flat=True))},
                message=f"Added tags to '{note.title}'",
                action="add_tags",
                resource_type=resource_type
            )

        except Note.DoesNotExist:
            return self._result(
                ToolStatus.NOT_FOUND,
                error=f"Note with ID {item_id} not found",
                action="add_tags",
                resource_type=resource_type
            )

    def _remove_tags(self, resource_type: str, params: Dict[str, Any]) -> ToolResult:
        """Remove tags from an item."""
        item_id = params.get("id")
        tags = params.get("tags", [])

        if not item_id:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error="'id' is required",
                action="remove_tags",
                resource_type=resource_type
            )

        try:
            from notes.models import Note, Tag

            note = Note.objects.get(id=item_id, user=self.user)

            for tag_name in tags:
                try:
                    tag = Tag.objects.get(name=tag_name.lower())
                    note.tags.remove(tag)
                except Tag.DoesNotExist:
                    pass

            return self._result(
                ToolStatus.SUCCESS,
                data={"id": note.id, "tags": list(note.tags.values_list('name', flat=True))},
                message=f"Removed tags from '{note.title}'",
                action="remove_tags",
                resource_type=resource_type
            )

        except Note.DoesNotExist:
            return self._result(
                ToolStatus.NOT_FOUND,
                error=f"Note with ID {item_id} not found",
                action="remove_tags",
                resource_type=resource_type
            )

    # =========================================================================
    # Helpers
    # =========================================================================

    def _apply_tags(self, note, tag_names: List[str], clear_existing: bool = True):
        """Apply tags to a note, creating them if needed."""
        from notes.models import Tag

        if clear_existing:
            note.tags.clear()

        for tag_name in tag_names:
            if not tag_name:
                continue
            tag, _ = Tag.objects.get_or_create(
                name=tag_name.lower().strip(),
                defaults={"tag_type": "topic"}
            )
            note.tags.add(tag)
            tag.usage_count += 1
            tag.save(update_fields=['usage_count'])

    def _apply_task_tags(self, task, tag_names: List[str], clear_existing: bool = True):
        """Apply tags to a task, creating them if needed."""
        from notes.models import Tag

        if clear_existing:
            task.tags.clear()

        for tag_name in tag_names:
            if not tag_name:
                continue
            tag, _ = Tag.objects.get_or_create(
                name=tag_name.lower().strip(),
                defaults={"tag_type": "topic"}
            )
            task.tags.add(tag)
            tag.usage_count += 1
            tag.save(update_fields=['usage_count'])

    def _parse_date(self, date_str: str):
        """Parse date string to datetime."""
        from datetime import datetime

        if not date_str:
            return None

        # Try common formats
        formats = [
            "%Y-%m-%d",           # 2024-12-20
            "%Y-%m-%dT%H:%M:%S",  # 2024-12-20T14:30:00
            "%Y-%m-%d %H:%M:%S",  # 2024-12-20 14:30:00
            "%d/%m/%Y",           # 20/12/2024
            "%m/%d/%Y",           # 12/20/2024
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return timezone.make_aware(dt) if timezone.is_naive(dt) else dt
            except ValueError:
                continue

        return None

    # =========================================================================
    # Subtask Actions
    # =========================================================================

    def _create_subtask(self, params: Dict[str, Any]) -> ToolResult:
        """
        Create a subtask under a parent task.

        Params:
            parent_id: int - Parent task ID (required)
            title: str - Subtask title (required)
            description: str - Subtask description
            due_date: str - Due date
            priority: str - low, medium, high, urgent
        """
        from tasks.models import Task

        parent_id = params.get("parent_id")
        title = params.get("title")

        if not parent_id:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error="'parent_id' is required for create_subtask",
                action="create_subtask",
                resource_type="subtask"
            )

        if not title:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error="'title' is required for create_subtask",
                action="create_subtask",
                resource_type="subtask"
            )

        try:
            parent = Task.objects.get(id=parent_id, user=self.user)
        except Task.DoesNotExist:
            return self._result(
                ToolStatus.NOT_FOUND,
                error=f"Parent task with ID {parent_id} not found",
                action="create_subtask",
                resource_type="subtask"
            )

        # Create subtask using model method
        priority = params.get("priority", parent.priority)
        subtask = parent.add_subtask(
            title=title,
            description=params.get("description", ""),
            priority=priority,
        )

        # Handle due_date
        if params.get("due_date"):
            subtask.due_date = self._parse_date(params["due_date"])
            subtask.save()

        return self._result(
            ToolStatus.SUCCESS,
            data={
                "id": subtask.id,
                "title": subtask.title,
                "parent_task_id": parent.id,
                "parent_task_title": parent.title,
                "status": subtask.status,
                "priority": subtask.priority,
            },
            message=f"Created subtask '{subtask.title}' under task '{parent.title}' (ID: {subtask.id})",
            action="create_subtask",
            resource_type="subtask"
        )

    def _list_subtasks(self, params: Dict[str, Any]) -> ToolResult:
        """
        List all subtasks of a parent task.

        Params:
            parent_id: int - Parent task ID (required)
            status: str - Filter by status (optional)
        """
        from tasks.models import Task

        parent_id = params.get("parent_id")

        if not parent_id:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error="'parent_id' is required for list_subtasks",
                action="list_subtasks",
                resource_type="subtask"
            )

        try:
            parent = Task.objects.get(id=parent_id, user=self.user)
        except Task.DoesNotExist:
            return self._result(
                ToolStatus.NOT_FOUND,
                error=f"Parent task with ID {parent_id} not found",
                action="list_subtasks",
                resource_type="subtask"
            )

        subtasks = parent.get_all_subtasks()

        # Filter by status if provided
        status = params.get("status")
        if status == "pending":
            subtasks = subtasks.filter(status__in=['todo', 'in_progress', 'waiting'])
        elif status in ['todo', 'in_progress', 'waiting', 'done']:
            subtasks = subtasks.filter(status=status)

        subtask_list = [
            {
                "id": st.id,
                "title": st.title,
                "status": st.status,
                "priority": st.priority,
                "due_date": st.due_date.isoformat() if st.due_date else None,
                "is_overdue": st.is_overdue,
            }
            for st in subtasks
        ]

        return self._result(
            ToolStatus.SUCCESS,
            data={
                "parent_id": parent.id,
                "parent_title": parent.title,
                "count": len(subtask_list),
                "completed_count": len([s for s in subtask_list if s["status"] == "done"]),
                "subtasks": subtask_list,
            },
            message=f"Found {len(subtask_list)} subtasks for task '{parent.title}'",
            action="list_subtasks",
            resource_type="subtask"
        )

    def _complete_subtask(self, params: Dict[str, Any]) -> ToolResult:
        """Mark a subtask as completed."""
        from tasks.models import Task

        subtask_id = params.get("id")

        if not subtask_id:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error="'id' is required for complete_subtask",
                action="complete_subtask",
                resource_type="subtask"
            )

        try:
            subtask = Task.objects.get(id=subtask_id, user=self.user)
        except Task.DoesNotExist:
            return self._result(
                ToolStatus.NOT_FOUND,
                error=f"Subtask with ID {subtask_id} not found",
                action="complete_subtask",
                resource_type="subtask"
            )

        if not subtask.is_subtask:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error=f"Task {subtask_id} is not a subtask. Use 'complete' action instead.",
                action="complete_subtask",
                resource_type="subtask"
            )

        subtask.mark_done()
        parent = subtask.parent_task

        return self._result(
            ToolStatus.SUCCESS,
            data={
                "id": subtask.id,
                "title": subtask.title,
                "status": "done",
                "parent_task_id": parent.id,
                "parent_progress": f"{parent.completed_subtask_count}/{parent.subtask_count}",
            },
            message=f"Completed subtask '{subtask.title}' ({parent.completed_subtask_count}/{parent.subtask_count} done)",
            action="complete_subtask",
            resource_type="subtask"
        )

    def _uncomplete_subtask(self, params: Dict[str, Any]) -> ToolResult:
        """Mark a subtask as not completed."""
        from tasks.models import Task

        subtask_id = params.get("id")

        if not subtask_id:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error="'id' is required for uncomplete_subtask",
                action="uncomplete_subtask",
                resource_type="subtask"
            )

        try:
            subtask = Task.objects.get(id=subtask_id, user=self.user)
        except Task.DoesNotExist:
            return self._result(
                ToolStatus.NOT_FOUND,
                error=f"Subtask with ID {subtask_id} not found",
                action="uncomplete_subtask",
                resource_type="subtask"
            )

        if not subtask.is_subtask:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error=f"Task {subtask_id} is not a subtask. Use 'uncomplete' action instead.",
                action="uncomplete_subtask",
                resource_type="subtask"
            )

        subtask.mark_todo()
        parent = subtask.parent_task

        return self._result(
            ToolStatus.SUCCESS,
            data={
                "id": subtask.id,
                "title": subtask.title,
                "status": "todo",
                "parent_task_id": parent.id,
                "parent_progress": f"{parent.completed_subtask_count}/{parent.subtask_count}",
            },
            message=f"Reopened subtask '{subtask.title}' ({parent.completed_subtask_count}/{parent.subtask_count} done)",
            action="uncomplete_subtask",
            resource_type="subtask"
        )

    def _update_subtask(self, params: Dict[str, Any]) -> ToolResult:
        """
        Update a subtask.

        Params:
            id: int - Subtask ID (required)
            title: str - New title
            description: str - New description
            due_date: str - New due date
            priority: str - New priority
        """
        from tasks.models import Task

        subtask_id = params.get("id")

        if not subtask_id:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error="'id' is required for update_subtask",
                action="update_subtask",
                resource_type="subtask"
            )

        try:
            subtask = Task.objects.get(id=subtask_id, user=self.user)
        except Task.DoesNotExist:
            return self._result(
                ToolStatus.NOT_FOUND,
                error=f"Subtask with ID {subtask_id} not found",
                action="update_subtask",
                resource_type="subtask"
            )

        if not subtask.is_subtask:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error=f"Task {subtask_id} is not a subtask. Use 'update' action instead.",
                action="update_subtask",
                resource_type="subtask"
            )

        # Apply updates
        if "title" in params:
            subtask.title = params["title"]
        if "description" in params:
            subtask.description = params["description"]
        if "due_date" in params:
            subtask.due_date = self._parse_date(params["due_date"])
        if "priority" in params:
            subtask.priority = params["priority"]

        subtask.save()

        return self._result(
            ToolStatus.SUCCESS,
            data={
                "id": subtask.id,
                "title": subtask.title,
                "status": subtask.status,
                "priority": subtask.priority,
                "parent_task_id": subtask.parent_task_id,
            },
            message=f"Updated subtask '{subtask.title}' (ID: {subtask.id})",
            action="update_subtask",
            resource_type="subtask"
        )

    def _delete_subtask(self, params: Dict[str, Any]) -> ToolResult:
        """Delete a subtask permanently."""
        from tasks.models import Task

        subtask_id = params.get("id")

        if not subtask_id:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error="'id' is required for delete_subtask",
                action="delete_subtask",
                resource_type="subtask"
            )

        try:
            subtask = Task.objects.get(id=subtask_id, user=self.user)
        except Task.DoesNotExist:
            return self._result(
                ToolStatus.NOT_FOUND,
                error=f"Subtask with ID {subtask_id} not found",
                action="delete_subtask",
                resource_type="subtask"
            )

        if not subtask.is_subtask:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error=f"Task {subtask_id} is not a subtask. Use 'delete' action instead.",
                action="delete_subtask",
                resource_type="subtask"
            )

        parent = subtask.parent_task
        subtask_title = subtask.title

        subtask.delete()

        return self._result(
            ToolStatus.SUCCESS,
            data={
                "id": subtask_id,
                "title": subtask_title,
                "parent_task_id": parent.id,
                "deleted": True,
            },
            message=f"Deleted subtask '{subtask_title}' from task '{parent.title}'",
            action="delete_subtask",
            resource_type="subtask"
        )

    # =========================================================================
    # Goal Actions
    # =========================================================================

    def _create_goal(self, params: Dict) -> ToolResult:
        """Create a new goal."""
        from journal.models import Goal, JournalType

        title = params.get("title")
        goal_type = params.get("goal_type")
        year = params.get("year")

        if not title:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error="'title' is required for creating a goal",
                action="create",
                resource_type="goal"
            )

        if not goal_type or goal_type not in ['year', 'quarter', 'month']:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error="'goal_type' is required and must be 'year', 'quarter', or 'month'",
                action="create",
                resource_type="goal"
            )

        if not year:
            year = timezone.now().year

        # Validate quarter/month based on type
        quarter = params.get("quarter")
        month = params.get("month")

        if goal_type == 'quarter' and not quarter:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error="'quarter' is required for quarterly goals",
                action="create",
                resource_type="goal"
            )

        if goal_type == 'month':
            if not month:
                return self._result(
                    ToolStatus.VALIDATION_ERROR,
                    error="'month' is required for monthly goals",
                    action="create",
                    resource_type="goal"
                )
            if not quarter:
                quarter = (month - 1) // 3 + 1

        # Get or create journal type for goals
        journal_type, _ = JournalType.objects.get_or_create(
            user=self.user,
            slug='goals',
            defaults={'name': 'Goals', 'frequency': 'as_needed'}
        )

        goal = Goal.objects.create(
            user=self.user,
            title=title,
            description=params.get("description", ""),
            goal_type=goal_type,
            year=year,
            quarter=quarter,
            month=month,
            key_results=params.get("key_results", []),
        )

        # Link to parent goal if provided
        if params.get("parent_goal_id"):
            try:
                parent = Goal.objects.get(id=params["parent_goal_id"], user=self.user)
                goal.parent_goal = parent
                goal.save()
            except Goal.DoesNotExist:
                pass

        # Link to area/project if provided
        if params.get("linked_area_id"):
            from para.models import Area
            try:
                goal.linked_area = Area.objects.get(id=params["linked_area_id"], user=self.user)
                goal.save()
            except Area.DoesNotExist:
                pass

        if params.get("linked_project_id"):
            from para.models import Project
            try:
                goal.linked_project = Project.objects.get(id=params["linked_project_id"], user=self.user)
                goal.save()
            except Project.DoesNotExist:
                pass

        return self._result(
            ToolStatus.SUCCESS,
            data={
                "id": goal.id,
                "title": goal.title,
                "goal_type": goal.goal_type,
                "period": goal.get_period_display(),
            },
            message=f"Created {goal.get_goal_type_display()} goal '{goal.title}' for {goal.get_period_display()} (ID: {goal.id})",
            action="create",
            resource_type="goal"
        )

    def _update_goal(self, goal_id: int, patch: Dict) -> ToolResult:
        """Update a goal."""
        from journal.models import Goal

        try:
            goal = Goal.objects.get(id=goal_id, user=self.user)
        except Goal.DoesNotExist:
            return self._result(
                ToolStatus.NOT_FOUND,
                error=f"Goal with ID {goal_id} not found",
                action="update",
                resource_type="goal"
            )

        if "title" in patch:
            goal.title = patch["title"]
        if "description" in patch:
            goal.description = patch["description"]
        if "status" in patch:
            if patch["status"] in ['active', 'completed', 'abandoned']:
                goal.status = patch["status"]
                if patch["status"] == 'completed':
                    goal.progress = 100
        if "progress" in patch:
            goal.progress = max(0, min(100, patch["progress"]))
        if "key_results" in patch:
            goal.key_results = patch["key_results"]

        goal.save()

        return self._result(
            ToolStatus.SUCCESS,
            data={"id": goal.id, "title": goal.title, "status": goal.status, "progress": goal.progress},
            message=f"Updated goal '{goal.title}' (ID: {goal.id})",
            action="update",
            resource_type="goal"
        )

    def _complete_goal(self, params: Dict) -> ToolResult:
        """Mark a goal as completed."""
        from journal.models import Goal

        goal_id = params.get("id")
        if not goal_id:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error="'id' is required for complete_goal",
                action="complete_goal",
                resource_type="goal"
            )

        try:
            goal = Goal.objects.get(id=goal_id, user=self.user)
        except Goal.DoesNotExist:
            return self._result(
                ToolStatus.NOT_FOUND,
                error=f"Goal with ID {goal_id} not found",
                action="complete_goal",
                resource_type="goal"
            )

        goal.mark_completed()

        return self._result(
            ToolStatus.SUCCESS,
            data={"id": goal.id, "title": goal.title, "status": "completed", "progress": 100},
            message=f"Completed goal '{goal.title}' (ID: {goal.id})",
            action="complete_goal",
            resource_type="goal"
        )

    def _abandon_goal(self, params: Dict) -> ToolResult:
        """Mark a goal as abandoned."""
        from journal.models import Goal

        goal_id = params.get("id")
        if not goal_id:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error="'id' is required for abandon_goal",
                action="abandon_goal",
                resource_type="goal"
            )

        try:
            goal = Goal.objects.get(id=goal_id, user=self.user)
        except Goal.DoesNotExist:
            return self._result(
                ToolStatus.NOT_FOUND,
                error=f"Goal with ID {goal_id} not found",
                action="abandon_goal",
                resource_type="goal"
            )

        goal.mark_abandoned()

        return self._result(
            ToolStatus.SUCCESS,
            data={"id": goal.id, "title": goal.title, "status": "abandoned"},
            message=f"Abandoned goal '{goal.title}' (ID: {goal.id})",
            action="abandon_goal",
            resource_type="goal"
        )

    # =========================================================================
    # Daily Planner Actions
    # =========================================================================

    def _create_daily_planner(self, params: Dict) -> ToolResult:
        """Create a daily planner entry."""
        from journal.models import DailyPlannerEntry, JournalType
        from datetime import datetime

        # Parse date (default to today)
        if params.get("date"):
            try:
                target_date = datetime.strptime(params["date"], '%Y-%m-%d').date()
            except ValueError:
                return self._result(
                    ToolStatus.VALIDATION_ERROR,
                    error="Invalid date format. Use YYYY-MM-DD",
                    action="create",
                    resource_type="daily_planner"
                )
        else:
            target_date = timezone.now().date()

        # Check if entry already exists
        if DailyPlannerEntry.objects.filter(user=self.user, date=target_date).exists():
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error=f"Daily planner for {target_date.isoformat()} already exists. Use update instead.",
                action="create",
                resource_type="daily_planner"
            )

        # Get or create journal type
        journal_type, _ = JournalType.objects.get_or_create(
            user=self.user,
            slug='daily',
            defaults={'name': 'Daily Planner', 'frequency': 'daily'}
        )

        entry = DailyPlannerEntry.objects.create(
            user=self.user,
            journal_type=journal_type,
            date=target_date,
            important_tasks=params.get("important_tasks", []),
            tasks_to_delegate=params.get("tasks_to_delegate", []),
            good_day_reward=params.get("good_day_reward", ""),
            intention=params.get("intention", ""),
        )

        # Initialize habits from UserHabit
        entry.initialize_habits()
        entry.save()

        return self._result(
            ToolStatus.SUCCESS,
            data={
                "id": entry.id,
                "date": entry.date.isoformat(),
                "date_display": entry.date.strftime('%A, %B %d, %Y'),
            },
            message=f"Created daily planner for {entry.date.strftime('%A, %B %d, %Y')} (ID: {entry.id})",
            action="create",
            resource_type="daily_planner"
        )

    def _update_daily_planner(self, entry_id: int, patch: Dict) -> ToolResult:
        """Update a daily planner entry."""
        from journal.models import DailyPlannerEntry

        try:
            entry = DailyPlannerEntry.objects.get(id=entry_id, user=self.user)
        except DailyPlannerEntry.DoesNotExist:
            return self._result(
                ToolStatus.NOT_FOUND,
                error=f"Daily planner with ID {entry_id} not found",
                action="update",
                resource_type="daily_planner"
            )

        # Morning planning fields
        if "important_tasks" in patch:
            entry.important_tasks = patch["important_tasks"]
        if "tasks_to_delegate" in patch:
            entry.tasks_to_delegate = patch["tasks_to_delegate"]
        if "good_day_reward" in patch:
            entry.good_day_reward = patch["good_day_reward"]
        if "intention" in patch:
            entry.intention = patch["intention"]
        if "schedule_blocks" in patch:
            entry.schedule_blocks = patch["schedule_blocks"]

        # Evening reflection fields
        if "accomplishments" in patch:
            entry.accomplishments = patch["accomplishments"]
        if "learnings" in patch:
            entry.learnings = patch["learnings"]
        if "improvements" in patch:
            entry.improvements = patch["improvements"]
        if "additional_notes" in patch:
            entry.additional_notes = patch["additional_notes"]

        # Completion flags
        if "is_morning_complete" in patch:
            entry.is_morning_complete = patch["is_morning_complete"]
        if "is_evening_complete" in patch:
            entry.is_evening_complete = patch["is_evening_complete"]

        entry.save()

        return self._result(
            ToolStatus.SUCCESS,
            data={
                "id": entry.id,
                "date": entry.date.isoformat(),
                "is_morning_complete": entry.is_morning_complete,
                "is_evening_complete": entry.is_evening_complete,
            },
            message=f"Updated daily planner for {entry.date.strftime('%A, %B %d, %Y')} (ID: {entry.id})",
            action="update",
            resource_type="daily_planner"
        )

    def _toggle_habit(self, params: Dict) -> ToolResult:
        """Toggle a habit's completion status in a daily planner."""
        from journal.models import DailyPlannerEntry, UserHabit
        from datetime import datetime

        habit_id = params.get("habit_id")
        if not habit_id:
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error="'habit_id' is required for toggle_habit",
                action="toggle_habit",
                resource_type="daily_planner"
            )

        # Parse date (default to today)
        if params.get("date"):
            try:
                target_date = datetime.strptime(params["date"], '%Y-%m-%d').date()
            except ValueError:
                return self._result(
                    ToolStatus.VALIDATION_ERROR,
                    error="Invalid date format. Use YYYY-MM-DD",
                    action="toggle_habit",
                    resource_type="daily_planner"
                )
        else:
            target_date = timezone.now().date()

        # Verify habit exists
        try:
            habit = UserHabit.objects.get(id=habit_id, user=self.user)
        except UserHabit.DoesNotExist:
            return self._result(
                ToolStatus.NOT_FOUND,
                error=f"Habit with ID {habit_id} not found",
                action="toggle_habit",
                resource_type="daily_planner"
            )

        # Get or create daily entry
        try:
            entry = DailyPlannerEntry.objects.get(user=self.user, date=target_date)
        except DailyPlannerEntry.DoesNotExist:
            return self._result(
                ToolStatus.NOT_FOUND,
                error=f"Daily planner for {target_date.isoformat()} not found. Create one first.",
                action="toggle_habit",
                resource_type="daily_planner"
            )

        habit_key = str(habit_id)

        # Initialize habits if needed
        if habit_key not in entry.daily_habits:
            entry.initialize_habits()

        if habit_key in entry.daily_habits:
            current_status = entry.daily_habits[habit_key].get('completed', False)
            new_status = params.get('completed', not current_status)
            entry.daily_habits[habit_key]['completed'] = new_status
            entry.save()

            return self._result(
                ToolStatus.SUCCESS,
                data={
                    "habit_id": habit_id,
                    "habit_name": habit.name,
                    "date": target_date.isoformat(),
                    "completed": new_status,
                    "habits_completion": entry.get_habits_completion(),
                },
                message=f"{'Completed' if new_status else 'Uncompleted'} habit '{habit.name}' for {target_date.isoformat()}",
                action="toggle_habit",
                resource_type="daily_planner"
            )
        else:
            return self._result(
                ToolStatus.ERROR,
                error=f"Habit {habit_id} not found in daily habits",
                action="toggle_habit",
                resource_type="daily_planner"
            )

    # =========================================================================
    # Weekly Planner Actions
    # =========================================================================

    def _create_weekly_planner(self, params: Dict) -> ToolResult:
        """Create a weekly planner entry."""
        from journal.models import WeeklyPlannerEntry, JournalType
        from datetime import datetime

        # Parse date to get week start (Monday)
        if params.get("week_start"):
            try:
                week_start = datetime.strptime(params["week_start"], '%Y-%m-%d').date()
            except ValueError:
                return self._result(
                    ToolStatus.VALIDATION_ERROR,
                    error="Invalid week_start format. Use YYYY-MM-DD",
                    action="create",
                    resource_type="weekly_planner"
                )
        elif params.get("date"):
            try:
                target_date = datetime.strptime(params["date"], '%Y-%m-%d').date()
                days_since_monday = target_date.weekday()
                week_start = target_date - timedelta(days=days_since_monday)
            except ValueError:
                return self._result(
                    ToolStatus.VALIDATION_ERROR,
                    error="Invalid date format. Use YYYY-MM-DD",
                    action="create",
                    resource_type="weekly_planner"
                )
        else:
            today = timezone.now().date()
            days_since_monday = today.weekday()
            week_start = today - timedelta(days=days_since_monday)

        # Check if entry already exists
        if WeeklyPlannerEntry.objects.filter(user=self.user, week_start=week_start).exists():
            return self._result(
                ToolStatus.VALIDATION_ERROR,
                error=f"Weekly planner for week starting {week_start.isoformat()} already exists. Use update instead.",
                action="create",
                resource_type="weekly_planner"
            )

        # Get or create journal type
        journal_type, _ = JournalType.objects.get_or_create(
            user=self.user,
            slug='weekly',
            defaults={'name': 'Weekly Planner', 'frequency': 'weekly'}
        )

        entry = WeeklyPlannerEntry.objects.create(
            user=self.user,
            journal_type=journal_type,
            date=week_start,
            week_start=week_start,
            top_priorities=params.get("top_priorities", []),
            week_plan=params.get("week_plan", ""),
            projects_focus=params.get("projects_focus", []),
            habits_focus=params.get("habits_focus", []),
        )

        # Link available monthly goals
        available_goals = entry.get_available_monthly_goals()
        entry.linked_monthly_goals.set(available_goals)

        return self._result(
            ToolStatus.SUCCESS,
            data={
                "id": entry.id,
                "week_start": entry.week_start.isoformat(),
                "week_end": entry.week_end.isoformat(),
                "week_display": entry.get_week_display(),
            },
            message=f"Created weekly planner for {entry.get_week_display()} (ID: {entry.id})",
            action="create",
            resource_type="weekly_planner"
        )

    def _update_weekly_planner(self, entry_id: int, patch: Dict) -> ToolResult:
        """Update a weekly planner entry."""
        from journal.models import WeeklyPlannerEntry

        try:
            entry = WeeklyPlannerEntry.objects.get(id=entry_id, user=self.user)
        except WeeklyPlannerEntry.DoesNotExist:
            return self._result(
                ToolStatus.NOT_FOUND,
                error=f"Weekly planner with ID {entry_id} not found",
                action="update",
                resource_type="weekly_planner"
            )

        # Planning fields
        if "weekly_goals" in patch:
            entry.weekly_goals = patch["weekly_goals"]
        if "top_priorities" in patch:
            entry.top_priorities = patch["top_priorities"]
        if "week_plan" in patch:
            entry.week_plan = patch["week_plan"]
        if "projects_focus" in patch:
            entry.projects_focus = patch["projects_focus"]
        if "habits_focus" in patch:
            entry.habits_focus = patch["habits_focus"]

        # Review fields
        if "week_rating" in patch:
            entry.week_rating = max(1, min(10, patch["week_rating"]))
        if "accomplishments" in patch:
            entry.accomplishments = patch["accomplishments"]
        if "lessons_learned" in patch:
            entry.lessons_learned = patch["lessons_learned"]

        # Completion flags
        if "is_planning_complete" in patch:
            entry.is_planning_complete = patch["is_planning_complete"]
        if "is_review_complete" in patch:
            entry.is_review_complete = patch["is_review_complete"]

        entry.save()

        return self._result(
            ToolStatus.SUCCESS,
            data={
                "id": entry.id,
                "week_display": entry.get_week_display(),
                "is_planning_complete": entry.is_planning_complete,
                "is_review_complete": entry.is_review_complete,
            },
            message=f"Updated weekly planner for {entry.get_week_display()} (ID: {entry.id})",
            action="update",
            resource_type="weekly_planner"
        )
