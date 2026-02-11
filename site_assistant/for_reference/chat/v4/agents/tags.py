"""
Tags Agent for Chat V4

Handles tag-related operations:
- Tag CRUD
- Bulk tagging
- Tag suggestions
- Tag statistics
"""

import logging
from typing import Dict, List, Any

from .base import (
    BaseAgent, AgentContext, ActionDecision,
    DatabaseAgentMixin, ActionDispatcherMixin
)
from ..state import StepResult

logger = logging.getLogger(__name__)


class TagsAgent(BaseAgent, DatabaseAgentMixin, ActionDispatcherMixin):
    """
    Specialized agent for tag operations.
    """

    AGENT_TYPE = "tags"

    AVAILABLE_ACTIONS = [
        "create",
        "get",
        "update",
        "delete",
        "list",
        "search",
        "bulk_add",
        "bulk_remove",
        "get_notes",
        "suggest",
        "stats",
        "merge",
    ]

    TAG_FIELDS = ['id', 'name', 'tag_type', 'created_at']

    # Tag types from the model
    TAG_TYPES = ['context', 'person', 'topic', 'status', 'energy', 'location', 'project', 'area']

    def get_actions_description(self) -> str:
        """Return description of available actions for LLM decision-making."""
        return """
### create
Create a new tag.
Params:
- name (required): Tag name
- tag_type: Type of tag (default: topic)
  Valid types: context, person, topic, status, energy, location, project, area

### get
Get a tag by ID or name.
Params:
- id or tag_id: Tag ID
- name: Tag name (alternative to ID)

### update
Update a tag's name or type.
Params:
- id or tag_id (required): Tag ID
- name: New tag name
- tag_type: New tag type

### delete
Delete a tag.
Params:
- id or tag_id (required): Tag ID

### list
List all tags.
Params:
- tag_type: Filter by type (optional)
- order_by: Sort field (default: name, or "usage")
- limit: Max results (default: 100)

### search
Search tags by name.
Params:
- query or q (required): Search text
- limit: Max results (default: 20)

### bulk_add
Add a tag to multiple notes.
Params:
- tag_id: Tag ID (or use tag_name)
- tag_name: Tag name to add (creates if needed)
- note_ids: List of note IDs (or uses found_notes from memory)
- tag_type: Type if creating new tag (default: topic)

### bulk_remove
Remove a tag from multiple notes.
Params:
- tag_id (required): Tag ID
- note_ids: List of note IDs (or uses found_notes from memory)

### get_notes
Get all notes with a specific tag.
Params:
- id or tag_id: Tag ID
- name: Tag name (alternative to ID)
- limit: Max results (default: 50)

### suggest
Suggest tags for a note based on content.
Params:
- note_id: Note ID to analyze
- content: Text content to analyze (alternative to note_id)

### stats
Get tag usage statistics.
Params: none

### merge
Merge two tags into one (moves notes, deletes source).
Params:
- source_id (required): Tag ID to merge from (will be deleted)
- target_id (required): Tag ID to merge into (will be kept)
"""

    def _execute_action(self, context: AgentContext, decision: ActionDecision) -> StepResult:
        """Execute the decided action using dispatcher."""
        return self._dispatch_action(context, decision)

    # ========================================================================
    # Action Handlers
    # ========================================================================

    def _handle_create(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Create a new tag"""
        from notes.models import Tag

        name = params.get('name')
        if not name:
            return self._error_result(context, "create", "Tag name is required")

        tag_type = params.get('tag_type', 'topic')
        if tag_type not in self.TAG_TYPES:
            return self._error_result(context, "create", f"Invalid tag type. Use: {', '.join(self.TAG_TYPES)}")

        # Check for existing
        existing = Tag.objects.filter(
            user_id=context.user_id,
            name__iexact=name
        ).first()

        if existing:
            return self._error_result(context, "create", f"Tag '{name}' already exists")

        tag = Tag.objects.create(
            user_id=context.user_id,
            name=name,
            tag_type=tag_type
        )

        context.set_in_memory('created_tag_id', tag.id)

        return self._success_result(
            context,
            action="create",
            output={'tag': self._serialize_tag(tag)},
            summary=f"Created tag '{tag.name}' ({tag.tag_type})",
            entities={'tag': [tag.id]}
        )

    def _handle_get(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Get a tag by ID or name"""
        from notes.models import Tag

        tag_id = params.get('id') or params.get('tag_id')
        tag_name = params.get('name')

        if tag_id:
            tag = self._get_object_or_none(Tag, context.user_id, tag_id)
        elif tag_name:
            tag = Tag.objects.filter(
                user_id=context.user_id,
                name__iexact=tag_name
            ).first()
        else:
            return self._error_result(context, "get", "Tag ID or name is required")

        if not tag:
            return self._not_found_result(context, "get", "tag", tag_id or tag_name)

        tag_data = self._serialize_tag(tag)
        tag_data['note_count'] = tag.notes.count()

        return self._success_result(
            context,
            action="get",
            output={'tag': tag_data},
            summary=f"Found tag '{tag.name}'",
            entities={'tag': [tag.id]}
        )

    def _handle_update(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Update a tag"""
        from notes.models import Tag

        tag_id = params.get('id') or params.get('tag_id')
        if not tag_id:
            return self._error_result(context, "update", "Tag ID is required")

        tag = self._get_object_or_none(Tag, context.user_id, tag_id)
        if not tag:
            return self._not_found_result(context, "update", "tag", tag_id)

        updated_fields = []

        new_name = params.get('name')
        if new_name and new_name != tag.name:
            # Check for conflicts
            if Tag.objects.filter(user_id=context.user_id, name__iexact=new_name).exclude(pk=tag_id).exists():
                return self._error_result(context, "update", f"Tag '{new_name}' already exists")
            tag.name = new_name
            updated_fields.append('name')

        new_type = params.get('tag_type')
        if new_type:
            if new_type not in self.TAG_TYPES:
                return self._error_result(context, "update", f"Invalid tag type. Use: {', '.join(self.TAG_TYPES)}")
            tag.tag_type = new_type
            updated_fields.append('tag_type')

        if updated_fields:
            tag.save()

        return self._success_result(
            context,
            action="update",
            output={'tag': self._serialize_tag(tag)},
            summary=f"Updated tag '{tag.name}'",
            entities={'tag': [tag.id]}
        )

    def _handle_delete(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Delete a tag"""
        from notes.models import Tag

        tag_id = params.get('id') or params.get('tag_id')
        if not tag_id:
            return self._error_result(context, "delete", "Tag ID is required")

        tag = self._get_object_or_none(Tag, context.user_id, tag_id)
        if not tag:
            return self._not_found_result(context, "delete", "tag", tag_id)

        name = tag.name
        note_count = tag.notes.count()
        tag.delete()

        return self._success_result(
            context,
            action="delete",
            output={'deleted_id': tag_id, 'name': name, 'affected_notes': note_count},
            summary=f"Deleted tag '{name}' (was on {note_count} notes)",
            entities={'tag': [tag_id]}
        )

    def _handle_list(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """List all tags"""
        from notes.models import Tag
        from django.db.models import Count

        queryset = self._get_user_queryset(Tag, context.user_id)

        tag_type = params.get('tag_type')
        if tag_type:
            queryset = queryset.filter(tag_type=tag_type)

        # Add note count annotation
        queryset = queryset.annotate(note_count=Count('notes'))

        order_by = params.get('order_by', 'name')
        if order_by == 'usage':
            queryset = queryset.order_by('-note_count')
        else:
            queryset = queryset.order_by(order_by)

        limit = params.get('limit', 100)
        tags = list(queryset[:limit])

        tag_ids = [t.id for t in tags]

        return self._success_result(
            context,
            action="list",
            output={
                'tags': [
                    {**self._serialize_tag(t), 'note_count': t.note_count}
                    for t in tags
                ],
                'count': len(tags)
            },
            summary=f"Found {len(tags)} tag(s)",
            entities={'tag': tag_ids}
        )

    def _handle_search(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Search tags by name"""
        from notes.models import Tag

        query = params.get('query') or params.get('q')
        if not query:
            return self._error_result(context, "search", "Search query is required")

        queryset = self._get_user_queryset(Tag, context.user_id)
        queryset = queryset.filter(name__icontains=query)

        limit = params.get('limit', 20)
        tags = list(queryset[:limit])

        tag_ids = [t.id for t in tags]

        return self._success_result(
            context,
            action="search",
            output={
                'query': query,
                'tags': [self._serialize_tag(t) for t in tags],
                'count': len(tags)
            },
            summary=f"Found {len(tags)} tag(s) matching '{query}'",
            entities={'tag': tag_ids}
        )

    def _handle_bulk_add(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Add a tag to multiple notes"""
        from notes.models import Note, Tag

        tag_id = params.get('tag_id')
        tag_name = params.get('tag_name')
        note_ids = params.get('note_ids', [])

        if not note_ids:
            note_ids = context.get_from_memory('found_notes', [])

        if not note_ids:
            return self._error_result(context, "bulk_add", "Note IDs are required")

        # Get or create tag
        if tag_id:
            tag = self._get_object_or_none(Tag, context.user_id, tag_id)
        elif tag_name:
            tag, _ = Tag.objects.get_or_create(
                user_id=context.user_id,
                name=tag_name,
                defaults={'tag_type': params.get('tag_type', 'topic')}
            )
        else:
            return self._error_result(context, "bulk_add", "Tag ID or name is required")

        if not tag:
            return self._not_found_result(context, "bulk_add", "tag", tag_id)

        # Add tag to notes
        notes = Note.objects.filter(
            user_id=context.user_id,
            pk__in=note_ids
        )

        added_count = 0
        for note in notes:
            if not note.tags.filter(pk=tag.id).exists():
                note.tags.add(tag)
                added_count += 1

        return self._success_result(
            context,
            action="bulk_add",
            output={
                'tag': self._serialize_tag(tag),
                'added_to': added_count,
                'note_ids': list(note_ids)
            },
            summary=f"Added tag '{tag.name}' to {added_count} note(s)",
            entities={'tag': [tag.id], 'note': list(note_ids)}
        )

    def _handle_bulk_remove(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Remove a tag from multiple notes"""
        from notes.models import Note, Tag

        tag_id = params.get('tag_id')
        note_ids = params.get('note_ids', [])

        if not note_ids:
            note_ids = context.get_from_memory('found_notes', [])

        if not tag_id:
            return self._error_result(context, "bulk_remove", "Tag ID is required")

        if not note_ids:
            return self._error_result(context, "bulk_remove", "Note IDs are required")

        tag = self._get_object_or_none(Tag, context.user_id, tag_id)
        if not tag:
            return self._not_found_result(context, "bulk_remove", "tag", tag_id)

        notes = Note.objects.filter(
            user_id=context.user_id,
            pk__in=note_ids
        )

        removed_count = 0
        for note in notes:
            if note.tags.filter(pk=tag.id).exists():
                note.tags.remove(tag)
                removed_count += 1

        return self._success_result(
            context,
            action="bulk_remove",
            output={
                'tag': self._serialize_tag(tag),
                'removed_from': removed_count,
                'note_ids': list(note_ids)
            },
            summary=f"Removed tag '{tag.name}' from {removed_count} note(s)",
            entities={'tag': [tag.id], 'note': list(note_ids)}
        )

    def _handle_get_notes(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Get all notes with a tag"""
        from notes.models import Tag

        tag_id = params.get('id') or params.get('tag_id')
        tag_name = params.get('name')

        if tag_id:
            tag = self._get_object_or_none(Tag, context.user_id, tag_id)
        elif tag_name:
            tag = Tag.objects.filter(
                user_id=context.user_id,
                name__iexact=tag_name
            ).first()
        else:
            return self._error_result(context, "get_notes", "Tag ID or name is required")

        if not tag:
            return self._not_found_result(context, "get_notes", "tag", tag_id or tag_name)

        notes = tag.notes.filter(is_archived=False)

        limit = params.get('limit', 50)
        notes_list = list(notes[:limit])

        note_ids = [n.id for n in notes_list]
        context.set_in_memory('found_notes', note_ids)

        return self._success_result(
            context,
            action="get_notes",
            output={
                'tag': self._serialize_tag(tag),
                'notes': [
                    {'id': n.id, 'title': n.title, 'note_type': n.note_type}
                    for n in notes_list
                ],
                'count': len(notes_list)
            },
            summary=f"Found {len(notes_list)} note(s) with tag '{tag.name}'",
            entities={'tag': [tag.id], 'note': note_ids}
        )

    def _handle_suggest(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Suggest tags for a note based on content"""
        from notes.models import Note, Tag

        note_id = params.get('note_id')
        content = params.get('content')

        if note_id:
            note = self._get_object_or_none(Note, context.user_id, note_id)
            if not note:
                return self._not_found_result(context, "suggest", "note", note_id)
            content = f"{note.title} {note.content}"
        elif not content:
            return self._error_result(context, "suggest", "Note ID or content is required")

        # Get all user's tags
        all_tags = Tag.objects.filter(user_id=context.user_id)

        # Simple keyword matching for suggestions
        content_lower = content.lower()
        suggestions = []

        for tag in all_tags:
            tag_words = tag.name.lower().split()
            if any(word in content_lower for word in tag_words):
                suggestions.append({
                    'id': tag.id,
                    'name': tag.name,
                    'type': tag.tag_type,
                    'confidence': 'high' if tag.name.lower() in content_lower else 'medium'
                })

        # Sort by confidence
        suggestions.sort(key=lambda x: 0 if x['confidence'] == 'high' else 1)

        return self._success_result(
            context,
            action="suggest",
            output={
                'suggestions': suggestions[:10],
                'count': len(suggestions)
            },
            summary=f"Suggested {min(len(suggestions), 10)} tag(s)",
            entities={}
        )

    def _handle_stats(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Get tag usage statistics"""
        from notes.models import Tag
        from django.db.models import Count

        tags = Tag.objects.filter(
            user_id=context.user_id
        ).annotate(
            note_count=Count('notes')
        ).order_by('-note_count')

        # Group by type
        by_type = {}
        for tag in tags:
            if tag.tag_type not in by_type:
                by_type[tag.tag_type] = []
            by_type[tag.tag_type].append({
                'id': tag.id,
                'name': tag.name,
                'count': tag.note_count
            })

        total_tags = tags.count()
        used_tags = tags.filter(note_count__gt=0).count()
        unused_tags = total_tags - used_tags

        top_tags = [
            {'id': t.id, 'name': t.name, 'count': t.note_count}
            for t in tags[:10]
        ]

        return self._success_result(
            context,
            action="stats",
            output={
                'total_tags': total_tags,
                'used_tags': used_tags,
                'unused_tags': unused_tags,
                'top_tags': top_tags,
                'by_type': {k: len(v) for k, v in by_type.items()}
            },
            summary=f"You have {total_tags} tag(s), {used_tags} in use",
            entities={}
        )

    def _handle_merge(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Merge two tags into one"""
        from notes.models import Tag

        source_id = params.get('source_id')
        target_id = params.get('target_id')

        if not source_id or not target_id:
            return self._error_result(context, "merge", "Source and target tag IDs are required")

        if source_id == target_id:
            return self._error_result(context, "merge", "Source and target cannot be the same")

        source_tag = self._get_object_or_none(Tag, context.user_id, source_id)
        if not source_tag:
            return self._not_found_result(context, "merge", "source tag", source_id)

        target_tag = self._get_object_or_none(Tag, context.user_id, target_id)
        if not target_tag:
            return self._not_found_result(context, "merge", "target tag", target_id)

        # Move all notes from source to target
        source_notes = source_tag.notes.all()
        moved_count = 0

        for note in source_notes:
            if not note.tags.filter(pk=target_id).exists():
                note.tags.add(target_tag)
            note.tags.remove(source_tag)
            moved_count += 1

        source_name = source_tag.name
        source_tag.delete()

        return self._success_result(
            context,
            action="merge",
            output={
                'merged_into': self._serialize_tag(target_tag),
                'deleted_tag': source_name,
                'notes_moved': moved_count
            },
            summary=f"Merged '{source_name}' into '{target_tag.name}' ({moved_count} notes)",
            entities={'tag': [target_id]}
        )

    # ========================================================================
    # Helpers
    # ========================================================================

    def _serialize_tag(self, tag) -> Dict[str, Any]:
        """Serialize a tag to dict"""
        return self._serialize_object(tag, self.TAG_FIELDS)
