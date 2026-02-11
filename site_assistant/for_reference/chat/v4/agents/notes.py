"""
Notes Agent for Chat V4

Handles all note-related operations:
- CRUD operations for various note types
- Progressive summarization (4 layers)
- Note linkages
- Tag management on notes

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


class NotesAgent(BaseAgent, DatabaseAgentMixin, ActionDispatcherMixin):
    """
    Specialized agent for note operations.

    Receives goals like "Create a meeting note about Sarah in Marketing project"
    and uses LLM to decide action (create) and params (title, note_type, container).
    """

    AGENT_TYPE = "notes"

    AVAILABLE_ACTIONS = [
        "create",
        "get",
        "update",
        "delete",
        "list",
        "search",
        "summarize",
        "add_layer",
        "link",
        "unlink",
        "get_links",
        "move",
        "archive",
        "unarchive",
        "add_tag",
        "remove_tag",
    ]

    NOTE_FIELDS = [
        'id', 'title', 'content', 'note_type', 'container_type', 'container_id',
        'summary', 'is_archived', 'created_at', 'updated_at'
    ]

    LINKAGE_TYPES = [
        'related', 'supports', 'contradicts', 'extends',
        'summarizes', 'references', 'questions', 'answers'
    ]

    def get_actions_description(self) -> str:
        """Return description of available actions for LLM decision-making."""
        return """
### create
Create a new note.
Params:
- title (required): Note title
- content: Note content/body
- note_type: note, checklist, meeting, resource (default: note)
- container_type: inbox, project, area (default: inbox)
- container_id: ID of project/area (use from working memory if available)

### get
Get a note by ID.
Params:
- note_id (required): The note ID
- include_tags: true to include tags
- include_links: true to include linked notes

### update
Update an existing note.
Params:
- note_id (required): The note ID
- title: New title
- content: New content
- note_type: New type

### delete
Delete a note.
Params:
- note_id (required): The note ID

### list
List notes with filters.
Params:
- note_type: Filter by type
- container_type: Filter by container type
- container_id: Filter by container ID
- has_summary: true/false to filter by summarization status
- is_archived: true/false (default: false)
- limit: Max results (default: 50)

### search
Search notes by text query.
Params:
- query (required): Search text
- limit: Max results (default: 20)

### summarize
Prepare a note for AI summarization.
Params:
- note_id (required): The note ID

### add_layer
Add progressive summarization layer.
Params:
- note_id (required): The note ID
- layer (required): 1, 2, 3, or 4
- content (required): The layer content

### link
Create a link between two notes.
Params:
- source_id (required): Source note ID
- target_id (required): Target note ID
- relationship: related, supports, contradicts, extends, summarizes, references, questions, answers (default: related)

### unlink
Remove a link between two notes.
Params:
- source_id (required): Source note ID
- target_id (required): Target note ID

### get_links
Get all links for a note.
Params:
- note_id (required): The note ID

### move
Move a note to a different container.
Params:
- note_id (required): The note ID
- container_type (required): project or area
- container_id: ID of destination

### archive
Archive a note.
Params:
- note_id (required): The note ID

### unarchive
Restore an archived note.
Params:
- note_id (required): The note ID

### add_tag
Add a tag to a note.
Params:
- note_id (required): The note ID
- tag_id: Existing tag ID, OR
- tag_name: Create/find tag by name

### remove_tag
Remove a tag from a note.
Params:
- note_id (required): The note ID
- tag_id (required): The tag ID
"""

    def _execute_action(self, context: AgentContext, decision: ActionDecision) -> StepResult:
        """Execute the decided action using dispatcher."""
        return self._dispatch_action(context, decision)

    # ========================================================================
    # Action Handlers - each receives (context, params)
    # ========================================================================

    def _handle_create(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Create a new note"""
        from notes.models import Note

        title = params.get('title')
        if not title:
            return self._error_result(context, "create", "Title is required")

        # Get container_id from params or working memory
        container_id = params.get('container_id')
        container_type = params.get('container_type', 'inbox')

        if not container_id and container_type == 'project':
            container_id = context.get_from_memory('found_project_id')
        elif not container_id and container_type == 'area':
            container_id = context.get_from_memory('found_area_id')

        try:
            note = Note.objects.create(
                user_id=context.user_id,
                title=title,
                content=params.get('content', ''),
                note_type=params.get('note_type', 'note'),
                container_type=container_type,
                container_id=container_id,
            )

            context.set_in_memory('created_note_id', note.id)
            context.set_in_memory('last_note', self._serialize_note(note))

            return self._success_result(
                context,
                action="create",
                output={'note': self._serialize_note(note)},
                summary=f"Created note '{note.title}'",
                entities={'note': [note.id]}
            )

        except Exception as e:
            logger.error(f"Note creation failed: {e}")
            return self._error_result(context, "create", str(e))

    def _handle_get(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Get a note by ID"""
        from notes.models import Note

        note_id = params.get('note_id') or params.get('id')
        if not note_id:
            return self._error_result(context, "get", "Note ID is required")

        note = self._get_object_or_none(Note, context.user_id, note_id)
        if not note:
            return self._not_found_result(context, "get", "note", note_id)

        note_data = self._serialize_note(note)

        if params.get('include_tags', False):
            note_data['tags'] = [{'id': t.id, 'name': t.name, 'type': t.tag_type}
                                 for t in note.tags.all()]

        if params.get('include_links', False):
            note_data['links'] = self._get_note_links(note)

        return self._success_result(
            context,
            action="get",
            output={'note': note_data},
            summary=f"Found note '{note.title}'",
            entities={'note': [note.id]}
        )

    def _handle_update(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Update a note"""
        from notes.models import Note

        note_id = params.get('note_id') or params.get('id')
        if not note_id:
            note_id = context.get_from_memory('created_note_id')

        if not note_id:
            return self._error_result(context, "update", "Note ID is required")

        note = self._get_object_or_none(Note, context.user_id, note_id)
        if not note:
            return self._not_found_result(context, "update", "note", note_id)

        updated_fields = []
        for field in ['title', 'content', 'note_type', 'container_type', 'container_id']:
            if params.get(field) is not None:
                setattr(note, field, params.get(field))
                updated_fields.append(field)

        if updated_fields:
            note.save()

        return self._success_result(
            context,
            action="update",
            output={'note': self._serialize_note(note), 'updated_fields': updated_fields},
            summary=f"Updated note '{note.title}' ({', '.join(updated_fields)})",
            entities={'note': [note.id]}
        )

    def _handle_delete(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Delete a note"""
        from notes.models import Note

        note_id = params.get('note_id') or params.get('id')
        if not note_id:
            return self._error_result(context, "delete", "Note ID is required")

        note = self._get_object_or_none(Note, context.user_id, note_id)
        if not note:
            return self._not_found_result(context, "delete", "note", note_id)

        title = note.title
        note.delete()

        return self._success_result(
            context,
            action="delete",
            output={'deleted_id': note_id, 'title': title},
            summary=f"Deleted note '{title}'",
            entities={'note': [note_id]}
        )

    def _handle_list(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """List notes with optional filters"""
        from notes.models import Note

        queryset = self._get_user_queryset(Note, context.user_id)

        filters = {}

        note_type = params.get('note_type')
        if note_type:
            filters['note_type'] = note_type

        container_type = params.get('container_type')
        if container_type:
            filters['container_type'] = container_type

        container_id = params.get('container_id')
        if container_id:
            filters['container_id'] = container_id

        is_archived = params.get('is_archived', False)
        filters['is_archived'] = is_archived

        has_summary = params.get('has_summary')
        if has_summary is True:
            filters['summary__isnull'] = False
        elif has_summary is False:
            filters['summary__isnull'] = True

        queryset = self._apply_filters(queryset, filters)

        order_by = params.get('order_by', '-updated_at')
        queryset = queryset.order_by(order_by)

        limit = params.get('limit', 50)
        notes = list(queryset[:limit])

        note_ids = [n.id for n in notes]
        context.set_in_memory('found_notes', note_ids)
        context.set_in_memory('found_note_ids', note_ids)

        return self._success_result(
            context,
            action="list",
            output={
                'notes': [self._serialize_note(n) for n in notes],
                'count': len(notes),
                'note_ids': note_ids
            },
            summary=f"Found {len(notes)} note(s)",
            entities={'note': note_ids}
        )

    def _handle_search(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Search notes by query"""
        from notes.models import Note
        from django.db.models import Q

        query = params.get('query') or params.get('q')
        if not query:
            return self._error_result(context, "search", "Search query is required")

        queryset = self._get_user_queryset(Note, context.user_id)
        queryset = queryset.filter(
            Q(title__icontains=query) | Q(content__icontains=query)
        )

        is_archived = params.get('is_archived', False)
        queryset = queryset.filter(is_archived=is_archived)

        limit = params.get('limit', 20)
        notes = list(queryset[:limit])

        note_ids = [n.id for n in notes]
        context.set_in_memory('found_notes', note_ids)
        context.set_in_memory('found_note_ids', note_ids)

        return self._success_result(
            context,
            action="search",
            output={
                'notes': [self._serialize_note(n) for n in notes],
                'count': len(notes),
                'query': query
            },
            summary=f"Found {len(notes)} note(s) matching '{query}'",
            entities={'note': note_ids}
        )

    def _handle_summarize(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Prepare a note for AI summarization"""
        from notes.models import Note

        note_id = params.get('note_id') or params.get('id')
        if not note_id:
            return self._error_result(context, "summarize", "Note ID is required")

        note = self._get_object_or_none(Note, context.user_id, note_id)
        if not note:
            return self._not_found_result(context, "summarize", "note", note_id)

        return self._success_result(
            context,
            action="summarize",
            output={
                'note_id': note_id,
                'title': note.title,
                'needs_ai': True,
                'content_length': len(note.content or '')
            },
            summary=f"Note '{note.title}' ready for summarization",
            entities={'note': [note.id]}
        )

    def _handle_add_layer(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Add summary to a note (legacy add_layer support)"""
        from notes.models import Note

        note_id = params.get('note_id') or params.get('id')
        if not note_id:
            return self._error_result(context, "add_layer", "Note ID is required")

        note = self._get_object_or_none(Note, context.user_id, note_id)
        if not note:
            return self._not_found_result(context, "add_layer", "note", note_id)

        content = params.get('content')
        if not content:
            return self._error_result(context, "add_layer", "Content is required")

        # All layers now just update the summary field
        note.summary = content
        note.save()

        return self._success_result(
            context,
            action="add_layer",
            output={'note': self._serialize_note(note)},
            summary=f"Added summary to '{note.title}'",
            entities={'note': [note.id]}
        )

    def _handle_link(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Create a link between two notes"""
        from notes.models import Note, NoteLinkage

        source_id = params.get('source_id')
        target_id = params.get('target_id')
        relationship = params.get('relationship', 'related')

        if not source_id or not target_id:
            return self._error_result(context, "link", "Source and target note IDs are required")

        if relationship not in self.LINKAGE_TYPES:
            return self._error_result(context, "link", f"Invalid relationship. Use: {', '.join(self.LINKAGE_TYPES)}")

        source = self._get_object_or_none(Note, context.user_id, source_id)
        if not source:
            return self._not_found_result(context, "link", "source note", source_id)

        target = self._get_object_or_none(Note, context.user_id, target_id)
        if not target:
            return self._not_found_result(context, "link", "target note", target_id)

        existing = NoteLinkage.objects.filter(source_note=source, target_note=target).first()

        if existing:
            existing.relationship_type = relationship
            existing.save()
            message = f"Updated link between '{source.title}' and '{target.title}'"
        else:
            NoteLinkage.objects.create(source_note=source, target_note=target, relationship_type=relationship)
            message = f"Linked '{source.title}' to '{target.title}' ({relationship})"

        return self._success_result(
            context,
            action="link",
            output={'source_id': source_id, 'target_id': target_id, 'relationship': relationship},
            summary=message,
            entities={'note': [source_id, target_id]}
        )

    def _handle_unlink(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Remove a link between two notes"""
        from notes.models import NoteLinkage

        source_id = params.get('source_id')
        target_id = params.get('target_id')

        if not source_id or not target_id:
            return self._error_result(context, "unlink", "Source and target note IDs are required")

        deleted, _ = NoteLinkage.objects.filter(
            source_note_id=source_id,
            target_note_id=target_id,
            source_note__user_id=context.user_id
        ).delete()

        if deleted:
            return self._success_result(
                context,
                action="unlink",
                output={'source_id': source_id, 'target_id': target_id},
                summary=f"Removed link between notes {source_id} and {target_id}",
                entities={'note': [source_id, target_id]}
            )
        else:
            return self._error_result(context, "unlink", "Link not found")

    def _handle_get_links(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Get all links for a note"""
        from notes.models import Note

        note_id = params.get('note_id') or params.get('id')
        if not note_id:
            return self._error_result(context, "get_links", "Note ID is required")

        note = self._get_object_or_none(Note, context.user_id, note_id)
        if not note:
            return self._not_found_result(context, "get_links", "note", note_id)

        links = self._get_note_links(note)

        return self._success_result(
            context,
            action="get_links",
            output={'note_id': note_id, 'links': links},
            summary=f"Found {len(links['outgoing']) + len(links['incoming'])} link(s) for '{note.title}'",
            entities={'note': [note_id]}
        )

    def _handle_move(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Move a note to a different container"""
        from notes.models import Note

        note_id = params.get('note_id') or params.get('id')
        if not note_id:
            return self._error_result(context, "move", "Note ID is required")

        note = self._get_object_or_none(Note, context.user_id, note_id)
        if not note:
            return self._not_found_result(context, "move", "note", note_id)

        container_type = params.get('container_type')
        if not container_type:
            return self._error_result(context, "move", "container_type is required")

        container_id = params.get('container_id')
        if not container_id:
            if container_type == 'project':
                container_id = context.get_from_memory('found_project_id')
            elif container_type == 'area':
                container_id = context.get_from_memory('found_area_id')

        note.container_type = container_type
        note.container_id = container_id
        note.save()

        return self._success_result(
            context,
            action="move",
            output={'note': self._serialize_note(note)},
            summary=f"Moved note '{note.title}' to {container_type}",
            entities={'note': [note.id]}
        )

    def _handle_archive(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Archive a note"""
        from notes.models import Note

        note_id = params.get('note_id') or params.get('id')
        if not note_id:
            return self._error_result(context, "archive", "Note ID is required")

        note = self._get_object_or_none(Note, context.user_id, note_id)
        if not note:
            return self._not_found_result(context, "archive", "note", note_id)

        note.is_archived = True
        note.save()

        return self._success_result(
            context,
            action="archive",
            output={'note': self._serialize_note(note)},
            summary=f"Archived note '{note.title}'",
            entities={'note': [note.id]}
        )

    def _handle_unarchive(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Unarchive a note"""
        from notes.models import Note

        note_id = params.get('note_id') or params.get('id')
        if not note_id:
            return self._error_result(context, "unarchive", "Note ID is required")

        note = self._get_object_or_none(Note, context.user_id, note_id)
        if not note:
            return self._not_found_result(context, "unarchive", "note", note_id)

        note.is_archived = False
        note.save()

        return self._success_result(
            context,
            action="unarchive",
            output={'note': self._serialize_note(note)},
            summary=f"Unarchived note '{note.title}'",
            entities={'note': [note.id]}
        )

    def _handle_add_tag(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Add a tag to a note"""
        from notes.models import Note, Tag

        note_id = params.get('note_id') or params.get('id')
        if not note_id:
            return self._error_result(context, "add_tag", "Note ID is required")

        note = self._get_object_or_none(Note, context.user_id, note_id)
        if not note:
            return self._not_found_result(context, "add_tag", "note", note_id)

        tag_id = params.get('tag_id')
        tag_name = params.get('tag_name')

        if tag_id:
            tag = self._get_object_or_none(Tag, context.user_id, tag_id)
        elif tag_name:
            tag, _ = Tag.objects.get_or_create(
                user_id=context.user_id,
                name=tag_name,
                defaults={'tag_type': params.get('tag_type', 'topic')}
            )
        else:
            return self._error_result(context, "add_tag", "Tag ID or name is required")

        if not tag:
            return self._not_found_result(context, "add_tag", "tag", tag_id)

        note.tags.add(tag)

        return self._success_result(
            context,
            action="add_tag",
            output={'note_id': note_id, 'tag': {'id': tag.id, 'name': tag.name}},
            summary=f"Added tag '{tag.name}' to '{note.title}'",
            entities={'note': [note.id], 'tag': [tag.id]}
        )

    def _handle_remove_tag(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Remove a tag from a note"""
        from notes.models import Note, Tag

        note_id = params.get('note_id') or params.get('id')
        if not note_id:
            return self._error_result(context, "remove_tag", "Note ID is required")

        note = self._get_object_or_none(Note, context.user_id, note_id)
        if not note:
            return self._not_found_result(context, "remove_tag", "note", note_id)

        tag_id = params.get('tag_id')
        if not tag_id:
            return self._error_result(context, "remove_tag", "Tag ID is required")

        tag = self._get_object_or_none(Tag, context.user_id, tag_id)
        if not tag:
            return self._not_found_result(context, "remove_tag", "tag", tag_id)

        note.tags.remove(tag)

        return self._success_result(
            context,
            action="remove_tag",
            output={'note_id': note_id, 'tag_id': tag_id},
            summary=f"Removed tag '{tag.name}' from '{note.title}'",
            entities={'note': [note.id], 'tag': [tag.id]}
        )

    # ========================================================================
    # Helpers
    # ========================================================================

    def _serialize_note(self, note) -> Dict[str, Any]:
        """Serialize a note to dict"""
        return self._serialize_object(note, self.NOTE_FIELDS)

    def _get_note_links(self, note) -> Dict[str, List[Dict]]:
        """Get all links for a note"""
        from notes.models import NoteLinkage

        outgoing = NoteLinkage.objects.filter(source_note=note).select_related('target_note')
        incoming = NoteLinkage.objects.filter(target_note=note).select_related('source_note')

        return {
            'outgoing': [
                {'target_id': link.target_note.id, 'target_title': link.target_note.title, 'relationship': link.relationship_type}
                for link in outgoing
            ],
            'incoming': [
                {'source_id': link.source_note.id, 'source_title': link.source_note.title, 'relationship': link.relationship_type}
                for link in incoming
            ]
        }
