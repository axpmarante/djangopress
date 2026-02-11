"""
Chat V3 Execute Tool

Mutation operations that change data.

Simplified from V2:
- Tool name is "execute" (not "execute_tool")
- Action is in params, not separate field
- Cleaner result format
"""

from typing import Dict, Any, List
from django.utils import timezone
from django.db import transaction

from .base import BaseTool
from ..types import ToolCall, ToolResult
from ..config import SafetyLevel


class ExecuteTool(BaseTool):
    """
    Execute tool for mutations.

    Usage:
        {"tool": "execute", "params": {"action": "create", "resource_type": "task", "params": {...}}}
        {"tool": "execute", "params": {"action": "complete", "resource_type": "task", "params": {"id": 42}}}
    """

    name = "execute"
    description = "Create, update, or delete items"
    safety_level = SafetyLevel.MUTATION

    ACTIONS = [
        "create", "update", "delete", "archive",
        "move", "complete", "start", "uncomplete",
        "add_tags", "remove_tags"
    ]

    def execute(self, call: ToolCall) -> ToolResult:
        """Execute a mutation action."""
        params = call.params
        action = params.get("action")
        resource_type = params.get("resource_type")
        action_params = params.get("params", {})

        if not action:
            return self._error("'action' is required")

        if action not in self.ACTIONS:
            return self._error(f"Unknown action: {action}. Available: {self.ACTIONS}")

        # Route to handler
        try:
            if action == "create":
                return self._create(resource_type, action_params)
            elif action == "update":
                return self._update(resource_type, action_params)
            elif action == "delete":
                return self._delete(resource_type, action_params)
            elif action == "archive":
                return self._archive(resource_type, action_params)
            elif action == "move":
                return self._move(resource_type, action_params)
            elif action == "complete":
                return self._complete(action_params)
            elif action == "start":
                return self._start(action_params)
            elif action == "uncomplete":
                return self._uncomplete(action_params)
            elif action == "add_tags":
                return self._add_tags(resource_type, action_params)
            elif action == "remove_tags":
                return self._remove_tags(resource_type, action_params)
        except Exception as e:
            return self._error(str(e))

    # =========================================================================
    # Create
    # =========================================================================

    def _create(self, resource_type: str, params: Dict) -> ToolResult:
        """Create a new item."""
        with transaction.atomic():
            if resource_type == "task":
                return self._create_task(params)
            elif resource_type == "note":
                return self._create_note(params)
            elif resource_type == "project":
                return self._create_project(params)
            elif resource_type == "area":
                return self._create_area(params)
            elif resource_type == "tag":
                return self._create_tag(params)
            else:
                return self._error(f"Cannot create resource type: {resource_type}")

    def _create_task(self, params: Dict) -> ToolResult:
        """Create a new task."""
        from tasks.models import Task

        title = params.get("title")
        if not title:
            return self._error("'title' is required for creating a task")

        due_date = self._parse_date(params.get("due_date")) if params.get("due_date") else None

        task = Task.objects.create(
            user=self.user,
            title=title,
            description=params.get("content", params.get("description", "")),
            status=params.get("status", "todo"),
            priority=params.get("priority", "medium"),
            due_date=due_date,
            container_type=params.get("container_type", "inbox"),
            container_id=params.get("container_id"),
        )

        if params.get("tags"):
            self._apply_tags_to_task(task, params["tags"])

        return self._success(
            data={"id": task.id, "title": task.title, "status": task.status},
            summary=f"Created task '{task.title}' (ID: {task.id})"
        )

    def _create_note(self, params: Dict) -> ToolResult:
        """Create a new note."""
        from notes.models import Note

        title = params.get("title", "Untitled Note")

        note = Note.objects.create(
            user=self.user,
            title=title,
            content=params.get("content", ""),
            note_type=params.get("note_type", "note"),
            container_type=params.get("container_type", "inbox"),
            container_id=params.get("container_id"),
            capture_date=timezone.now(),
        )

        if params.get("tags"):
            self._apply_tags_to_note(note, params["tags"])

        return self._success(
            data={"id": note.id, "title": note.title},
            summary=f"Created note '{note.title}' (ID: {note.id})"
        )

    def _create_project(self, params: Dict) -> ToolResult:
        """Create a new project."""
        from para.models import Project, Area

        name = params.get("name")
        if not name:
            return self._error("'name' is required for creating a project")

        area_id = params.get("area_id")
        if not area_id:
            return self._error("'area_id' is required for creating a project")

        try:
            area = Area.objects.get(id=area_id, user=self.user)
        except Area.DoesNotExist:
            return self._not_found("area", area_id)

        deadline = self._parse_date(params.get("deadline")) if params.get("deadline") else None

        project = Project.objects.create(
            user=self.user,
            name=name,
            area=area,
            description=params.get("description", ""),
            deadline=deadline,
            status="active",
        )

        return self._success(
            data={"id": project.id, "name": project.name, "area_name": area.name},
            summary=f"Created project '{project.name}' in area '{area.name}' (ID: {project.id})"
        )

    def _create_area(self, params: Dict) -> ToolResult:
        """Create a new area."""
        from para.models import Area

        name = params.get("name")
        if not name:
            return self._error("'name' is required for creating an area")

        parent = None
        if params.get("parent_id"):
            try:
                parent = Area.objects.get(id=params["parent_id"], user=self.user)
            except Area.DoesNotExist:
                return self._not_found("parent area", params["parent_id"])

        area = Area.objects.create(
            user=self.user,
            name=name,
            description=params.get("description", ""),
            parent=parent,
            is_active=True,
        )

        return self._success(
            data={"id": area.id, "name": area.name},
            summary=f"Created area '{area.name}' (ID: {area.id})"
        )

    def _create_tag(self, params: Dict) -> ToolResult:
        """Create a new tag."""
        from notes.models import Tag

        name = params.get("name")
        if not name:
            return self._error("'name' is required for creating a tag")

        tag, created = Tag.objects.get_or_create(
            name=name.lower(),
            defaults={
                "color": params.get("color", "#808080"),
                "tag_type": params.get("tag_type", "topic"),
            }
        )

        if created:
            return self._success(
                data={"id": tag.id, "name": tag.name},
                summary=f"Created tag '{tag.name}' (ID: {tag.id})"
            )
        else:
            return self._success(
                data={"id": tag.id, "name": tag.name, "already_existed": True},
                summary=f"Tag '{tag.name}' already exists (ID: {tag.id})"
            )

    # =========================================================================
    # Update
    # =========================================================================

    def _update(self, resource_type: str, params: Dict) -> ToolResult:
        """Update an existing item."""
        item_id = params.get("id")
        if not item_id:
            return self._error("'id' is required for update")

        patch = params.get("patch", {k: v for k, v in params.items() if k != "id"})

        with transaction.atomic():
            if resource_type == "task":
                return self._update_task(item_id, patch)
            elif resource_type == "note":
                return self._update_note(item_id, patch)
            elif resource_type == "project":
                return self._update_project(item_id, patch)
            elif resource_type == "area":
                return self._update_area(item_id, patch)
            else:
                return self._error(f"Cannot update resource type: {resource_type}")

    def _update_task(self, task_id: int, patch: Dict) -> ToolResult:
        """Update a task."""
        from tasks.models import Task

        try:
            task = Task.objects.get(id=task_id, user=self.user)
        except Task.DoesNotExist:
            return self._not_found("task", task_id)

        if "title" in patch:
            task.title = patch["title"]
        if "description" in patch or "content" in patch:
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
        if "waiting_on" in patch:
            task.waiting_on = patch["waiting_on"]

        task.save()

        if "tags" in patch:
            self._apply_tags_to_task(task, patch["tags"])

        return self._success(
            data={"id": task.id, "title": task.title, "status": task.status},
            summary=f"Updated task '{task.title}' (ID: {task.id})"
        )

    def _update_note(self, note_id: int, patch: Dict) -> ToolResult:
        """Update a note."""
        from notes.models import Note

        try:
            note = Note.objects.get(id=note_id, user=self.user)
        except Note.DoesNotExist:
            return self._not_found("note", note_id)

        if "title" in patch:
            note.title = patch["title"]
        if "content" in patch:
            note.content = patch["content"]

        note.save()

        if "tags" in patch:
            self._apply_tags_to_note(note, patch["tags"])

        return self._success(
            data={"id": note.id, "title": note.title},
            summary=f"Updated note '{note.title}' (ID: {note.id})"
        )

    def _update_project(self, project_id: int, patch: Dict) -> ToolResult:
        """Update a project."""
        from para.models import Project

        try:
            project = Project.objects.get(id=project_id, user=self.user)
        except Project.DoesNotExist:
            return self._not_found("project", project_id)

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

        return self._success(
            data={"id": project.id, "name": project.name},
            summary=f"Updated project '{project.name}' (ID: {project.id})"
        )

    def _update_area(self, area_id: int, patch: Dict) -> ToolResult:
        """Update an area."""
        from para.models import Area

        try:
            area = Area.objects.get(id=area_id, user=self.user)
        except Area.DoesNotExist:
            return self._not_found("area", area_id)

        if "name" in patch:
            area.name = patch["name"]
        if "description" in patch:
            area.description = patch["description"]

        area.save()

        return self._success(
            data={"id": area.id, "name": area.name},
            summary=f"Updated area '{area.name}' (ID: {area.id})"
        )

    # =========================================================================
    # Delete / Archive
    # =========================================================================

    def _delete(self, resource_type: str, params: Dict) -> ToolResult:
        """Soft delete (archive) an item."""
        return self._archive(resource_type, params)

    def _archive(self, resource_type: str, params: Dict) -> ToolResult:
        """Archive an item."""
        item_id = params.get("id")
        if not item_id:
            return self._error("'id' is required for archive")

        if resource_type == "task":
            from tasks.models import Task
            try:
                task = Task.objects.get(id=item_id, user=self.user)
                task.archive()
                return self._success(
                    data={"id": task.id, "title": task.title},
                    summary=f"Archived task '{task.title}' (ID: {task.id})"
                )
            except Task.DoesNotExist:
                return self._not_found("task", item_id)

        elif resource_type == "note":
            from notes.models import Note
            try:
                note = Note.objects.get(id=item_id, user=self.user)
                note.is_archived = True
                note.save(update_fields=['is_archived', 'updated_at'])
                return self._success(
                    data={"id": note.id, "title": note.title},
                    summary=f"Archived note '{note.title}' (ID: {note.id})"
                )
            except Note.DoesNotExist:
                return self._not_found("note", item_id)

        elif resource_type == "project":
            from para.models import Project
            try:
                project = Project.objects.get(id=item_id, user=self.user)
                project.status = 'archived'
                project.save(update_fields=['status', 'updated_at'])
                return self._success(
                    data={"id": project.id, "name": project.name},
                    summary=f"Archived project '{project.name}' (ID: {project.id})"
                )
            except Project.DoesNotExist:
                return self._not_found("project", item_id)

        elif resource_type == "area":
            from para.models import Area
            try:
                area = Area.objects.get(id=item_id, user=self.user)
                area.is_active = False
                area.save(update_fields=['is_active', 'updated_at'])
                return self._success(
                    data={"id": area.id, "name": area.name},
                    summary=f"Archived area '{area.name}' (ID: {area.id})"
                )
            except Area.DoesNotExist:
                return self._not_found("area", item_id)

        return self._error(f"Cannot archive resource type: {resource_type}")

    # =========================================================================
    # Move
    # =========================================================================

    def _move(self, resource_type: str, params: Dict) -> ToolResult:
        """Move an item to a different container."""
        item_id = params.get("id")
        container_type = params.get("container_type")
        container_id = params.get("container_id")

        if not item_id:
            return self._error("'id' is required for move")
        if not container_type:
            return self._error("'container_type' is required for move")

        if resource_type not in ["note", "task"]:
            return self._error(f"Cannot move resource type: {resource_type}")

        # Validate container exists
        if container_type == "project" and container_id:
            from para.models import Project
            if not Project.objects.filter(id=container_id, user=self.user).exists():
                return self._not_found("project", container_id)
        elif container_type == "area" and container_id:
            from para.models import Area
            if not Area.objects.filter(id=container_id, user=self.user).exists():
                return self._not_found("area", container_id)

        if resource_type == "task":
            from tasks.models import Task
            try:
                task = Task.objects.get(id=item_id, user=self.user)
                task.move_to(container_type, container_id if container_type != "inbox" else None)
                return self._success(
                    data={"id": task.id, "title": task.title, "container_type": task.container_type},
                    summary=f"Moved task '{task.title}' to {container_type}"
                )
            except Task.DoesNotExist:
                return self._not_found("task", item_id)

        elif resource_type == "note":
            from notes.models import Note
            try:
                note = Note.objects.get(id=item_id, user=self.user)
                note.container_type = container_type
                note.container_id = container_id if container_type != "inbox" else None
                note.save()
                return self._success(
                    data={"id": note.id, "title": note.title, "container_type": note.container_type},
                    summary=f"Moved note '{note.title}' to {container_type}"
                )
            except Note.DoesNotExist:
                return self._not_found("note", item_id)

    # =========================================================================
    # Task Actions
    # =========================================================================

    def _complete(self, params: Dict) -> ToolResult:
        """Mark a task as complete."""
        from tasks.models import Task

        task_id = params.get("id")
        if not task_id:
            return self._error("'id' is required for complete")

        try:
            task = Task.objects.get(id=task_id, user=self.user)
            task.mark_done()
            return self._success(
                data={"id": task.id, "title": task.title, "status": "done"},
                summary=f"Completed task '{task.title}' (ID: {task.id})"
            )
        except Task.DoesNotExist:
            return self._not_found("task", task_id)

    def _start(self, params: Dict) -> ToolResult:
        """Mark a task as in progress."""
        from tasks.models import Task

        task_id = params.get("id")
        if not task_id:
            return self._error("'id' is required for start")

        try:
            task = Task.objects.get(id=task_id, user=self.user)
            task.start()
            return self._success(
                data={"id": task.id, "title": task.title, "status": "in_progress"},
                summary=f"Started task '{task.title}' (ID: {task.id})"
            )
        except Task.DoesNotExist:
            return self._not_found("task", task_id)

    def _uncomplete(self, params: Dict) -> ToolResult:
        """Reopen a completed task."""
        from tasks.models import Task

        task_id = params.get("id")
        if not task_id:
            return self._error("'id' is required for uncomplete")

        try:
            task = Task.objects.get(id=task_id, user=self.user)
            task.mark_todo()
            return self._success(
                data={"id": task.id, "title": task.title, "status": "todo"},
                summary=f"Reopened task '{task.title}' (ID: {task.id})"
            )
        except Task.DoesNotExist:
            return self._not_found("task", task_id)

    # =========================================================================
    # Tags
    # =========================================================================

    def _add_tags(self, resource_type: str, params: Dict) -> ToolResult:
        """Add tags to an item."""
        item_id = params.get("id")
        tags = params.get("tags", [])

        if not item_id:
            return self._error("'id' is required")
        if not tags:
            return self._error("'tags' list is required")

        if resource_type == "task":
            from tasks.models import Task
            try:
                task = Task.objects.get(id=item_id, user=self.user)
                self._apply_tags_to_task(task, tags, clear_existing=False)
                return self._success(
                    data={"id": task.id, "tags": list(task.tags.values_list('name', flat=True))},
                    summary=f"Added tags to task '{task.title}'"
                )
            except Task.DoesNotExist:
                return self._not_found("task", item_id)

        elif resource_type == "note":
            from notes.models import Note
            try:
                note = Note.objects.get(id=item_id, user=self.user)
                self._apply_tags_to_note(note, tags, clear_existing=False)
                return self._success(
                    data={"id": note.id, "tags": list(note.tags.values_list('name', flat=True))},
                    summary=f"Added tags to note '{note.title}'"
                )
            except Note.DoesNotExist:
                return self._not_found("note", item_id)

        return self._error(f"Cannot add tags to resource type: {resource_type}")

    def _remove_tags(self, resource_type: str, params: Dict) -> ToolResult:
        """Remove tags from an item."""
        from notes.models import Tag

        item_id = params.get("id")
        tags = params.get("tags", [])

        if not item_id:
            return self._error("'id' is required")

        if resource_type == "task":
            from tasks.models import Task
            try:
                task = Task.objects.get(id=item_id, user=self.user)
                for tag_name in tags:
                    try:
                        tag = Tag.objects.get(name=tag_name.lower())
                        task.tags.remove(tag)
                    except Tag.DoesNotExist:
                        pass
                return self._success(
                    data={"id": task.id, "tags": list(task.tags.values_list('name', flat=True))},
                    summary=f"Removed tags from task '{task.title}'"
                )
            except Task.DoesNotExist:
                return self._not_found("task", item_id)

        elif resource_type == "note":
            from notes.models import Note
            try:
                note = Note.objects.get(id=item_id, user=self.user)
                for tag_name in tags:
                    try:
                        tag = Tag.objects.get(name=tag_name.lower())
                        note.tags.remove(tag)
                    except Tag.DoesNotExist:
                        pass
                return self._success(
                    data={"id": note.id, "tags": list(note.tags.values_list('name', flat=True))},
                    summary=f"Removed tags from note '{note.title}'"
                )
            except Note.DoesNotExist:
                return self._not_found("note", item_id)

        return self._error(f"Cannot remove tags from resource type: {resource_type}")

    # =========================================================================
    # Helpers
    # =========================================================================

    def _apply_tags_to_note(self, note, tag_names: List[str], clear_existing: bool = True):
        """Apply tags to a note."""
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

    def _apply_tags_to_task(self, task, tag_names: List[str], clear_existing: bool = True):
        """Apply tags to a task."""
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
