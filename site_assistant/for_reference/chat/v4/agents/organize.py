"""
Organize Agent for Chat V4

Handles cross-entity organization operations:
- Moving items between containers
- Bulk archiving
- Batch operations
- Container management
"""

import logging
from typing import Dict, List, Any

from .base import (
    BaseAgent, AgentContext, ActionDecision,
    DatabaseAgentMixin, ActionDispatcherMixin
)
from ..state import StepResult

logger = logging.getLogger(__name__)


class OrganizeAgent(BaseAgent, DatabaseAgentMixin, ActionDispatcherMixin):
    """
    Specialized agent for cross-entity organization operations.
    """

    AGENT_TYPE = "organize"

    AVAILABLE_ACTIONS = [
        "move",
        "move_bulk",
        "archive",
        "archive_bulk",
        "unarchive_bulk",
        "delete_bulk",
        "copy_to_project",
        "merge_notes",
    ]

    def get_actions_description(self) -> str:
        """Return description of available actions for LLM decision-making."""
        return """
### move
Move a single item to a new container.
Params:
- item_type: note or task (default: note)
- item_id (required): The item ID
- container_type (required): inbox, project, or area
- container_id: ID of destination (required for project/area)

### move_bulk
Move multiple items to a new container.
Params:
- item_type: note or task (default: note)
- item_ids: List of item IDs (or uses found_notes/found_tasks from memory)
- container_type (required): inbox, project, or area
- container_id: ID of destination

### archive
Archive a single item.
Params:
- item_type: note, task, project, or area (default: note)
- item_id (required): The item ID

### archive_bulk
Archive multiple items.
Params:
- item_type: note, task, or project (default: note)
- item_ids: List of item IDs (or uses found_* from memory)

### unarchive_bulk
Unarchive multiple items.
Params:
- item_type: note, task, or project (default: note)
- item_ids (required): List of item IDs

### delete_bulk
Delete multiple items (use with caution).
Params:
- item_type: note or task (default: note)
- item_ids (required): List of item IDs
- confirm (required): true to confirm deletion

### copy_to_project
Copy tasks from one project to another.
Params:
- source_project_id (required): Source project ID
- target_project_id (required): Target project ID
- include_completed: true/false (default: false)

### merge_notes
Merge multiple notes into one.
Params:
- note_ids (required): List of note IDs (minimum 2)
- target_note_id: ID of note to merge into (uses first if not specified)
- delete_sources: true to delete source notes after merge (default: false)
"""

    def _execute_action(self, context: AgentContext, decision: ActionDecision) -> StepResult:
        """Execute the decided action using dispatcher."""
        return self._dispatch_action(context, decision)

    # ========================================================================
    # Action Handlers
    # ========================================================================

    def _handle_move(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Move a single item to a new container"""
        from notes.models import Note, Task

        item_type = params.get('item_type', 'note')
        item_id = params.get('item_id') or params.get('id')
        container_type = params.get('container_type')
        container_id = params.get('container_id')

        if not item_id:
            return self._error_result(context, "move", "Item ID is required")

        if not container_type:
            return self._error_result(context, "move", "Container type is required (inbox, project, or area)")

        if container_type in ['project', 'area'] and not container_id:
            return self._error_result(context, "move", f"Container ID is required for {container_type}")

        # Get the item
        if item_type == 'note':
            item = self._get_object_or_none(Note, context.user_id, item_id)
        else:
            item = self._get_object_or_none(Task, context.user_id, item_id)

        if not item:
            return self._not_found_result(context, "move", item_type, item_id)

        # Validate container exists
        if container_type == 'project':
            from para.models import Project
            if not Project.objects.filter(pk=container_id, user_id=context.user_id).exists():
                return self._not_found_result(context, "move", "project", container_id)
        elif container_type == 'area':
            from para.models import Area
            if not Area.objects.filter(pk=container_id, user_id=context.user_id).exists():
                return self._not_found_result(context, "move", "area", container_id)

        old_container = f"{item.container_type}:{item.container_id}"

        item.container_type = container_type
        item.container_id = container_id if container_type != 'inbox' else None
        item.save()

        return self._success_result(
            context,
            action="move",
            output={
                'item_type': item_type,
                'item_id': item_id,
                'title': item.title,
                'from': old_container,
                'to': f"{container_type}:{container_id}"
            },
            summary=f"Moved '{item.title}' to {container_type}",
            entities={item_type: [item_id]}
        )

    def _handle_move_bulk(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Move multiple items to a new container"""
        from notes.models import Note, Task

        item_type = params.get('item_type', 'note')
        item_ids = params.get('item_ids', [])
        container_type = params.get('container_type')
        container_id = params.get('container_id')

        # Get from working memory if not provided
        if not item_ids:
            if item_type == 'note':
                item_ids = context.get_from_memory('found_notes', [])
            else:
                item_ids = context.get_from_memory('found_tasks', [])

        if not item_ids:
            return self._error_result(context, "move_bulk", "Item IDs are required")

        if not container_type:
            return self._error_result(context, "move_bulk", "Container type is required")

        # Validate container
        if container_type == 'project':
            from para.models import Project
            if not Project.objects.filter(pk=container_id, user_id=context.user_id).exists():
                return self._not_found_result(context, "move_bulk", "project", container_id)
        elif container_type == 'area':
            from para.models import Area
            if not Area.objects.filter(pk=container_id, user_id=context.user_id).exists():
                return self._not_found_result(context, "move_bulk", "area", container_id)

        # Move items
        if item_type == 'note':
            model = Note
        else:
            model = Task

        updated = model.objects.filter(
            pk__in=item_ids,
            user_id=context.user_id
        ).update(
            container_type=container_type,
            container_id=container_id if container_type != 'inbox' else None
        )

        return self._success_result(
            context,
            action="move_bulk",
            output={
                'item_type': item_type,
                'moved_count': updated,
                'item_ids': list(item_ids),
                'container_type': container_type,
                'container_id': container_id
            },
            summary=f"Moved {updated} {item_type}(s) to {container_type}",
            entities={item_type: list(item_ids)}
        )

    def _handle_archive(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Archive a single item"""
        from notes.models import Note, Task
        from para.models import Project, Area

        item_type = params.get('item_type', 'note')
        item_id = params.get('item_id') or params.get('id')

        if not item_id:
            return self._error_result(context, "archive", "Item ID is required")

        # Get and archive the item
        if item_type == 'note':
            item = self._get_object_or_none(Note, context.user_id, item_id)
        elif item_type == 'task':
            item = self._get_object_or_none(Task, context.user_id, item_id)
        elif item_type == 'project':
            item = self._get_object_or_none(Project, context.user_id, item_id)
        elif item_type == 'area':
            item = self._get_object_or_none(Area, context.user_id, item_id)
        else:
            return self._error_result(context, "archive", f"Unknown item type: {item_type}")

        if not item:
            return self._not_found_result(context, "archive", item_type, item_id)

        # Area model uses is_active (inverted), others use is_archived
        if item_type == 'area':
            item.is_active = False
        else:
            item.is_archived = True
        item.save()

        name = getattr(item, 'title', None) or getattr(item, 'name', str(item_id))

        return self._success_result(
            context,
            action="archive",
            output={
                'item_type': item_type,
                'item_id': item_id,
                'title': name
            },
            summary=f"Archived {item_type} '{name}'",
            entities={item_type: [item_id]}
        )

    def _handle_archive_bulk(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Archive multiple items"""
        from notes.models import Note, Task
        from para.models import Project

        item_type = params.get('item_type', 'note')
        item_ids = params.get('item_ids', [])

        # Get from working memory if not provided
        if not item_ids:
            memory_key = f'found_{item_type}s'
            item_ids = context.get_from_memory(memory_key, [])

        if not item_ids:
            return self._error_result(context, "archive_bulk", "Item IDs are required")

        # Archive items
        if item_type == 'note':
            model = Note
        elif item_type == 'task':
            model = Task
        elif item_type == 'project':
            model = Project
        else:
            return self._error_result(context, "archive_bulk", f"Unknown item type: {item_type}")

        updated = model.objects.filter(
            pk__in=item_ids,
            user_id=context.user_id
        ).update(is_archived=True)

        return self._success_result(
            context,
            action="archive_bulk",
            output={
                'item_type': item_type,
                'archived_count': updated,
                'item_ids': list(item_ids)
            },
            summary=f"Archived {updated} {item_type}(s)",
            entities={item_type: list(item_ids)}
        )

    def _handle_unarchive_bulk(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Unarchive multiple items"""
        from notes.models import Note, Task
        from para.models import Project

        item_type = params.get('item_type', 'note')
        item_ids = params.get('item_ids', [])

        if not item_ids:
            return self._error_result(context, "unarchive_bulk", "Item IDs are required")

        if item_type == 'note':
            model = Note
        elif item_type == 'task':
            model = Task
        elif item_type == 'project':
            model = Project
        else:
            return self._error_result(context, "unarchive_bulk", f"Unknown item type: {item_type}")

        updated = model.objects.filter(
            pk__in=item_ids,
            user_id=context.user_id
        ).update(is_archived=False)

        return self._success_result(
            context,
            action="unarchive_bulk",
            output={
                'item_type': item_type,
                'unarchived_count': updated,
                'item_ids': list(item_ids)
            },
            summary=f"Unarchived {updated} {item_type}(s)",
            entities={item_type: list(item_ids)}
        )

    def _handle_delete_bulk(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Delete multiple items (use with caution)"""
        from notes.models import Note, Task

        item_type = params.get('item_type', 'note')
        item_ids = params.get('item_ids', [])
        confirm = params.get('confirm', False)

        if not item_ids:
            return self._error_result(context, "delete_bulk", "Item IDs are required")

        if not confirm:
            return self._error_result(
                context, "delete_bulk",
                f"Please confirm deletion of {len(item_ids)} {item_type}(s) by setting confirm=true"
            )

        if item_type == 'note':
            model = Note
        elif item_type == 'task':
            model = Task
        else:
            return self._error_result(context, "delete_bulk", f"Bulk delete not supported for: {item_type}")

        deleted, _ = model.objects.filter(
            pk__in=item_ids,
            user_id=context.user_id
        ).delete()

        return self._success_result(
            context,
            action="delete_bulk",
            output={
                'item_type': item_type,
                'deleted_count': deleted,
                'item_ids': list(item_ids)
            },
            summary=f"Deleted {deleted} {item_type}(s)",
            entities={item_type: list(item_ids)}
        )

    def _handle_copy_to_project(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Copy tasks from one project to another"""
        from notes.models import Task

        source_project_id = params.get('source_project_id')
        target_project_id = params.get('target_project_id')
        include_completed = params.get('include_completed', False)

        if not source_project_id or not target_project_id:
            return self._error_result(context, "copy_to_project", "Source and target project IDs are required")

        # Validate projects exist
        from para.models import Project
        source = self._get_object_or_none(Project, context.user_id, source_project_id)
        if not source:
            return self._not_found_result(context, "copy_to_project", "source project", source_project_id)

        target = self._get_object_or_none(Project, context.user_id, target_project_id)
        if not target:
            return self._not_found_result(context, "copy_to_project", "target project", target_project_id)

        # Get tasks to copy
        tasks = Task.objects.filter(
            user_id=context.user_id,
            container_type='project',
            container_id=source_project_id,
            is_archived=False
        )

        if not include_completed:
            tasks = tasks.exclude(status='done')

        copied_ids = []
        for task in tasks:
            new_task = Task.objects.create(
                user_id=context.user_id,
                title=task.title,
                description=task.description,
                status='todo',
                priority=task.priority,
                due_date=task.due_date,
                container_type='project',
                container_id=target_project_id
            )
            copied_ids.append(new_task.id)

        return self._success_result(
            context,
            action="copy_to_project",
            output={
                'source_project': source.name,
                'target_project': target.name,
                'copied_count': len(copied_ids),
                'new_task_ids': copied_ids
            },
            summary=f"Copied {len(copied_ids)} task(s) from '{source.name}' to '{target.name}'",
            entities={'task': copied_ids, 'project': [source_project_id, target_project_id]}
        )

    def _handle_merge_notes(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Merge multiple notes into one"""
        from notes.models import Note

        note_ids = params.get('note_ids', [])
        target_note_id = params.get('target_note_id')
        delete_sources = params.get('delete_sources', False)

        if len(note_ids) < 2:
            return self._error_result(context, "merge_notes", "At least 2 note IDs are required to merge")

        if target_note_id and target_note_id not in note_ids:
            note_ids = [target_note_id] + list(note_ids)

        # Get all notes
        notes = list(Note.objects.filter(
            pk__in=note_ids,
            user_id=context.user_id
        ).order_by('created_at'))

        if len(notes) < 2:
            return self._error_result(context, "merge_notes", "Could not find enough notes to merge")

        # First note becomes the target
        target = notes[0]
        source_notes = notes[1:]

        # Merge content
        merged_content = target.content or ''
        for note in source_notes:
            merged_content += f"\n\n---\n\n## {note.title}\n\n{note.content or ''}"

        target.content = merged_content
        target.save()

        # Optionally delete sources
        deleted_count = 0
        if delete_sources:
            for note in source_notes:
                note.delete()
                deleted_count += 1

        return self._success_result(
            context,
            action="merge_notes",
            output={
                'target_note': {
                    'id': target.id,
                    'title': target.title
                },
                'merged_count': len(source_notes),
                'deleted_sources': deleted_count
            },
            summary=f"Merged {len(source_notes)} note(s) into '{target.title}'",
            entities={'note': [target.id]}
        )
