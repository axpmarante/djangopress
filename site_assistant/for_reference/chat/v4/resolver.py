"""
Reference Resolution for Chat V4

Resolves implicit references in user messages:
- Pronouns: "it", "that", "this", "them", "those"
- Implicit references: "the task", "the note", "the project"
- Context-based resolution using conversation state
"""

import re
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class ResolvedReference:
    """A resolved reference from the message"""
    original_text: str
    entity_type: str
    entity_ids: List[int]
    confidence: float
    source: str  # 'last_created', 'last_affected', 'mentioned', 'explicit'

    def to_dict(self) -> Dict[str, Any]:
        return {
            'original_text': self.original_text,
            'entity_type': self.entity_type,
            'entity_ids': self.entity_ids,
            'confidence': self.confidence,
            'source': self.source
        }


@dataclass
class ResolutionResult:
    """Result of reference resolution"""
    original_message: str
    resolved_message: str
    references: List[ResolvedReference]
    has_unresolved: bool
    unresolved_refs: List[str]

    def get_entities_by_type(self, entity_type: str) -> List[int]:
        """Get all resolved entity IDs for a type"""
        ids = []
        for ref in self.references:
            if ref.entity_type == entity_type:
                ids.extend(ref.entity_ids)
        return list(set(ids))

    def to_dict(self) -> Dict[str, Any]:
        return {
            'original_message': self.original_message,
            'resolved_message': self.resolved_message,
            'references': [r.to_dict() for r in self.references],
            'has_unresolved': self.has_unresolved,
            'unresolved_refs': self.unresolved_refs
        }


class ReferenceResolver:
    """
    Resolves implicit references in user messages.

    Uses conversation state to map pronouns and implicit references
    to specific entity IDs.
    """

    # Singular pronouns/references
    SINGULAR_REFS = {
        'it': None,  # Generic, needs context
        'that': None,
        'this': None,
        'the task': 'task',
        'that task': 'task',
        'this task': 'task',
        'the note': 'note',
        'that note': 'note',
        'this note': 'note',
        'the project': 'project',
        'that project': 'project',
        'this project': 'project',
        'the area': 'area',
        'that area': 'area',
        'this area': 'area',
    }

    # Plural pronouns/references
    PLURAL_REFS = {
        'them': None,
        'those': None,
        'these': None,
        'the tasks': 'task',
        'those tasks': 'task',
        'these tasks': 'task',
        'the notes': 'note',
        'those notes': 'note',
        'these notes': 'note',
        'the projects': 'project',
        'those projects': 'project',
        'these projects': 'project',
    }

    # Action context hints - what entity type an action usually targets
    ACTION_ENTITY_HINTS = {
        'complete': 'task',
        'finish': 'task',
        'done': 'task',
        'check off': 'task',
        'summarize': 'note',
        'distill': 'note',
        'highlight': 'note',
        'archive': None,  # Could be any
        'delete': None,
        'move': None,
    }

    @classmethod
    def resolve(
        cls,
        message: str,
        last_created: Dict[str, int] = None,
        last_affected: Dict[str, List[int]] = None,
        mentioned: Dict[str, List[int]] = None
    ) -> ResolutionResult:
        """
        Resolve references in a message.

        Args:
            message: User message
            last_created: Dict of entity_type -> last created ID
            last_affected: Dict of entity_type -> list of recently affected IDs
            mentioned: Dict of entity_type -> list of mentioned IDs

        Returns:
            ResolutionResult with resolved references
        """
        last_created = last_created or {}
        last_affected = last_affected or {}
        mentioned = mentioned or {}

        resolved_refs = []
        unresolved_refs = []
        resolved_message = message

        # Detect action context for better resolution
        action_context = cls._detect_action_context(message)

        # First, try to resolve singular references
        for ref_text, entity_type in cls.SINGULAR_REFS.items():
            if cls._contains_reference(message, ref_text):
                resolved = cls._resolve_singular(
                    ref_text,
                    entity_type,
                    action_context,
                    last_created,
                    last_affected,
                    mentioned
                )

                if resolved:
                    resolved_refs.append(resolved)
                    # Update message with resolved reference
                    resolved_message = cls._annotate_reference(
                        resolved_message, ref_text, resolved
                    )
                else:
                    unresolved_refs.append(ref_text)

        # Then, try to resolve plural references
        for ref_text, entity_type in cls.PLURAL_REFS.items():
            if cls._contains_reference(message, ref_text):
                resolved = cls._resolve_plural(
                    ref_text,
                    entity_type,
                    action_context,
                    last_affected,
                    mentioned
                )

                if resolved:
                    resolved_refs.append(resolved)
                    resolved_message = cls._annotate_reference(
                        resolved_message, ref_text, resolved
                    )
                else:
                    unresolved_refs.append(ref_text)

        return ResolutionResult(
            original_message=message,
            resolved_message=resolved_message,
            references=resolved_refs,
            has_unresolved=len(unresolved_refs) > 0,
            unresolved_refs=unresolved_refs
        )

    @classmethod
    def _contains_reference(cls, message: str, ref_text: str) -> bool:
        """Check if message contains a reference (word boundary aware)"""
        pattern = r'\b' + re.escape(ref_text) + r'\b'
        return bool(re.search(pattern, message, re.IGNORECASE))

    @classmethod
    def _detect_action_context(cls, message: str) -> Optional[str]:
        """Detect what entity type the action likely targets"""
        msg_lower = message.lower()
        for action, entity_type in cls.ACTION_ENTITY_HINTS.items():
            if action in msg_lower:
                return entity_type
        return None

    @classmethod
    def _resolve_singular(
        cls,
        ref_text: str,
        explicit_type: Optional[str],
        action_context: Optional[str],
        last_created: Dict[str, int],
        last_affected: Dict[str, List[int]],
        mentioned: Dict[str, List[int]]
    ) -> Optional[ResolvedReference]:
        """Resolve a singular reference"""

        # Determine entity type
        entity_type = explicit_type or action_context

        if entity_type:
            # Try last created first (most likely target)
            if entity_type in last_created:
                return ResolvedReference(
                    original_text=ref_text,
                    entity_type=entity_type,
                    entity_ids=[last_created[entity_type]],
                    confidence=0.9,
                    source='last_created'
                )

            # Try last affected
            if entity_type in last_affected and last_affected[entity_type]:
                return ResolvedReference(
                    original_text=ref_text,
                    entity_type=entity_type,
                    entity_ids=[last_affected[entity_type][0]],  # First one
                    confidence=0.8,
                    source='last_affected'
                )

            # Try mentioned
            if entity_type in mentioned and mentioned[entity_type]:
                return ResolvedReference(
                    original_text=ref_text,
                    entity_type=entity_type,
                    entity_ids=[mentioned[entity_type][-1]],  # Most recent
                    confidence=0.7,
                    source='mentioned'
                )

        else:
            # No explicit type - try to infer from context
            # Priority: last_created > last_affected > mentioned

            # Check what was last created
            if last_created:
                # Take the most recent (assuming dict order preservation)
                for etype, eid in reversed(list(last_created.items())):
                    return ResolvedReference(
                        original_text=ref_text,
                        entity_type=etype,
                        entity_ids=[eid],
                        confidence=0.75,
                        source='last_created'
                    )

            # Check what was last affected
            if last_affected:
                for etype, eids in reversed(list(last_affected.items())):
                    if eids:
                        return ResolvedReference(
                            original_text=ref_text,
                            entity_type=etype,
                            entity_ids=[eids[0]],
                            confidence=0.65,
                            source='last_affected'
                        )

        return None

    @classmethod
    def _resolve_plural(
        cls,
        ref_text: str,
        explicit_type: Optional[str],
        action_context: Optional[str],
        last_affected: Dict[str, List[int]],
        mentioned: Dict[str, List[int]]
    ) -> Optional[ResolvedReference]:
        """Resolve a plural reference"""

        entity_type = explicit_type or action_context

        if entity_type:
            # Try last affected first (for plurals)
            if entity_type in last_affected and last_affected[entity_type]:
                return ResolvedReference(
                    original_text=ref_text,
                    entity_type=entity_type,
                    entity_ids=last_affected[entity_type],
                    confidence=0.85,
                    source='last_affected'
                )

            # Try mentioned
            if entity_type in mentioned and mentioned[entity_type]:
                return ResolvedReference(
                    original_text=ref_text,
                    entity_type=entity_type,
                    entity_ids=mentioned[entity_type],
                    confidence=0.75,
                    source='mentioned'
                )

        else:
            # No explicit type - take whatever was last affected
            if last_affected:
                for etype, eids in reversed(list(last_affected.items())):
                    if eids:
                        return ResolvedReference(
                            original_text=ref_text,
                            entity_type=etype,
                            entity_ids=eids,
                            confidence=0.6,
                            source='last_affected'
                        )

        return None

    @classmethod
    def _annotate_reference(
        cls,
        message: str,
        ref_text: str,
        resolved: ResolvedReference
    ) -> str:
        """Add annotation to resolved reference in message"""
        # Create annotation like "it [task:42]"
        annotation = f"[{resolved.entity_type}:{','.join(map(str, resolved.entity_ids))}]"

        # Replace first occurrence with annotated version
        pattern = r'\b' + re.escape(ref_text) + r'\b'
        return re.sub(
            pattern,
            f"{ref_text} {annotation}",
            message,
            count=1,
            flags=re.IGNORECASE
        )

    @classmethod
    def needs_resolution(cls, message: str) -> bool:
        """Check if message contains references that need resolution"""
        msg_lower = message.lower()

        all_refs = list(cls.SINGULAR_REFS.keys()) + list(cls.PLURAL_REFS.keys())
        for ref in all_refs:
            if cls._contains_reference(message, ref):
                return True

        return False

    @classmethod
    def extract_explicit_ids(cls, message: str) -> Dict[str, List[int]]:
        """
        Extract explicitly mentioned IDs from message.

        Patterns like:
        - "task #42" or "task 42"
        - "note id 15"
        - "#123"
        """
        result = {}

        # Pattern: "task #42" or "task 42"
        for entity_type in ['task', 'note', 'project', 'area']:
            pattern = rf'\b{entity_type}\s*#?(\d+)\b'
            matches = re.findall(pattern, message, re.IGNORECASE)
            if matches:
                result[entity_type] = [int(m) for m in matches]

        # Pattern: standalone "#123" (usually task)
        standalone = re.findall(r'(?<!\w)#(\d+)\b', message)
        if standalone and 'task' not in result:
            result['task'] = [int(m) for m in standalone]

        return result
