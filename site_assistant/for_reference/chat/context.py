"""
Context Builder for Chat App

Builds comprehensive context from user's Second Brain data
to provide the LLM with full awareness of the user's PARA system.
"""
import json
from typing import Dict, Any, List, Optional
from django.utils import timezone
from django.db.models import Count, Q

# Debug flag - set to True to see context building details
DEBUG_CONTEXT = True


def debug_print(label: str, data: Any = None, separator: bool = False):
    """Print debug info if DEBUG_CONTEXT is enabled"""
    if not DEBUG_CONTEXT:
        return
    if separator:
        print(f"\n{'='*60}")
        print(f"[CONTEXT] {label}")
        print('='*60)
    elif data is not None:
        if isinstance(data, (dict, list)):
            import json
            print(f"[CONTEXT] {label}:")
            print(json.dumps(data, indent=2, default=str)[:2000])  # Truncate large outputs
        else:
            print(f"[CONTEXT] {label}: {data}")
    else:
        print(f"[CONTEXT] {label}")


class ContextBuilder:
    """
    Builds comprehensive context from user's Second Brain data.
    Provides full PARA overview, recent activity, and current state.
    """

    def __init__(self, user, conversation=None):
        self.user = user
        self.conversation = conversation

    def build_full_context(self) -> Dict[str, Any]:
        """
        Build complete context including all PARA data.
        Returns structured dict for system prompt construction.
        """
        debug_print("Building Full Context", separator=True)
        debug_print(f"User: {self.user.username}")
        debug_print(f"Conversation: {self.conversation.id if self.conversation else 'None'}")
        if self.conversation:
            debug_print(f"Context Type: {self.conversation.context_type}")
            debug_print(f"Context ID: {self.conversation.context_id}")

        user_summary = self._get_user_summary()
        debug_print("User Summary", user_summary)

        # Get recent activity based on user interactions
        recent_activity = self._get_recent_activity()
        debug_print("Recent Activity", recent_activity)

        areas = self._get_areas_context()
        debug_print(f"Areas Found: {len(areas)}")

        projects = self._get_projects_context()
        debug_print(f"Projects Found: {len(projects)}")

        recent_notes = self._get_recent_notes()
        debug_print(f"Recent Notes: {len(recent_notes)}")

        inbox_summary = self._get_inbox_summary()
        debug_print("Inbox Summary", inbox_summary)

        tasks_summary = self._get_tasks_summary()
        debug_print("Tasks Summary", tasks_summary)

        tags = self._get_tags_context()
        debug_print(f"Tags Found: {len(tags)}")

        scoped_context = self._get_scoped_context()
        if scoped_context:
            debug_print("Scoped Context", scoped_context)

        return {
            'user_summary': user_summary,
            'recent_activity': recent_activity,
            'areas': areas,
            'projects': projects,
            'recent_notes': recent_notes,
            'inbox_summary': inbox_summary,
            'tasks_summary': tasks_summary,
            'tags': tags,
            'scoped_context': scoped_context,
        }

    def _get_user_summary(self) -> Dict:
        """Basic user info, context, and current time"""
        return {
            'username': self.user.username,
            'first_name': self.user.first_name or self.user.username,
            'current_date': timezone.now().strftime('%Y-%m-%d'),
            'current_time': timezone.now().strftime('%H:%M'),
            'current_day': timezone.now().strftime('%A'),
            # User context fields
            'about': getattr(self.user, 'about', '') or '',
            'current_focus': getattr(self.user, 'current_focus', '') or '',
            'goals': getattr(self.user, 'goals', '') or '',
            'ai_preferences': getattr(self.user, 'ai_preferences', '') or '',
        }

    def _get_recent_activity(self) -> Dict:
        """Get user's recent activity based on interaction tracking."""
        from Core.services import InteractionService
        return InteractionService.get_context_for_prompt(self.user, days=14)

    def _get_areas_context(self) -> List[Dict]:
        """Get all active areas with key info, including hierarchy"""
        from para.models import Area
        from notes.models import Note
        from tasks.models import Task

        # Get root areas (no parent) - they will include their children
        areas = Area.objects.filter(
            user=self.user,
            is_active=True,
            parent__isnull=True  # Only root areas
        ).prefetch_related('projects', 'children')

        result = []
        for area in areas:
            # Count notes for this area
            notes_count = Note.objects.filter(
                user=self.user,
                container_type='area',
                container_id=area.id,
                is_archived=False
            ).count()

            # Count tasks from new Task model
            tasks_count = Task.objects.filter(
                user=self.user,
                container_type='area',
                container_id=area.id,
                is_archived=False
            ).exclude(status='done').count()

            # Get sub-areas
            sub_areas = []
            for child in area.get_children():
                child_notes = Note.objects.filter(
                    user=self.user, container_type='area',
                    container_id=child.id, is_archived=False
                ).count()
                child_tasks = Task.objects.filter(
                    user=self.user, container_type='area',
                    container_id=child.id, is_archived=False
                ).exclude(status='done').count()
                sub_areas.append({
                    'id': child.id,
                    'name': child.name,
                    'notes_count': child_notes,
                    'tasks_count': child_tasks,
                    'active_projects_count': child.get_active_projects_count(),
                })

            result.append({
                'id': area.id,
                'name': area.name,
                'full_path': area.get_full_path(),
                'description': (area.description[:200] + '...') if area.description and len(area.description) > 200 else area.description,
                'active_projects_count': area.get_active_projects_count(),
                'notes_count': notes_count,
                'tasks_count': tasks_count,
                'is_business': area.is_business_area,
                'area_type': area.area_type,
                'area_type_display': area.get_area_type_display(),
                'needs_review': area.needs_review(),
                'sub_areas': sub_areas,
                'sub_areas_count': len(sub_areas),
            })

        return result

    def _get_projects_context(self) -> List[Dict]:
        """Get all active projects with status"""
        from para.models import Project

        projects = Project.objects.filter(
            user=self.user,
            status__in=['active', 'on_hold']
        ).select_related('area')

        return [
            {
                'id': project.id,
                'name': project.name,
                'area_name': project.area.name,
                'area_id': project.area.id,
                'area_full_path': project.area.get_full_path(),
                'description': (project.description[:200] + '...') if project.description and len(project.description) > 200 else project.description,
                'status': project.status,
                'progress': project.progress_percentage,
                'deadline': project.deadline.isoformat() if project.deadline else None,
                'is_overdue': project.is_overdue(),
                'urgency': project.get_urgency_level(),
                'task_counts': project.get_task_counts(),
            }
            for project in projects
        ]

    def _get_recent_notes(self, limit: int = 15) -> List[Dict]:
        """Get recently modified/created notes"""
        from notes.models import Note

        notes = Note.objects.filter(
            user=self.user,
            is_archived=False
        ).order_by('-updated_at')[:limit]

        return [
            {
                'id': note.id,
                'title': note.title[:100] if note.title else 'Untitled',
                'type': note.note_type,
                'container_type': note.container_type,
                'container_id': note.container_id,
                'is_archived': note.is_archived,
                'has_summary': bool(note.summary),
                'tags': list(note.tags.values_list('name', flat=True)[:5]),
                'updated_at': note.updated_at.strftime('%Y-%m-%d'),
            }
            for note in notes
        ]

    def _get_inbox_summary(self) -> Dict:
        """Summary of inbox state"""
        from notes.models import Note

        inbox_notes = Note.objects.filter(user=self.user, container_type='inbox', is_archived=False)
        oldest = inbox_notes.order_by('capture_date').first()

        # Get type breakdown
        type_counts = dict(
            inbox_notes.values('note_type').annotate(
                count=Count('id')
            ).values_list('note_type', 'count')
        )

        return {
            'total_count': inbox_notes.count(),
            'oldest_date': oldest.capture_date.strftime('%Y-%m-%d') if oldest else None,
            'types': type_counts,
        }

    def _get_tasks_summary(self) -> Dict:
        """Summary of task state using new Task model"""
        from tasks.models import Task
        from datetime import timedelta

        tasks = Task.objects.filter(
            user=self.user,
            is_archived=False
        )

        today = timezone.now().date()

        # Get overdue tasks (due date passed, not done)
        overdue_tasks = tasks.filter(
            due_date__date__lt=today,
            status__in=['todo', 'in_progress', 'waiting']
        )

        # Get due today
        due_today = tasks.filter(
            due_date__date=today,
            status__in=['todo', 'in_progress', 'waiting']
        )

        # Get upcoming (next 7 days)
        next_week = today + timedelta(days=7)
        due_soon = tasks.filter(
            due_date__date__gt=today,
            due_date__date__lte=next_week,
            status__in=['todo', 'in_progress', 'waiting']
        )

        # Get waiting tasks with follow-up info
        waiting_tasks = tasks.filter(status='waiting')
        follow_up_due = waiting_tasks.filter(follow_up_date__date__lte=today)

        return {
            'total': tasks.exclude(status='done').count(),
            'todo': tasks.filter(status='todo').count(),
            'in_progress': tasks.filter(status='in_progress').count(),
            'waiting': tasks.filter(status='waiting').count(),
            'done': tasks.filter(status='done').count(),
            'overdue': overdue_tasks.count(),
            'overdue_tasks': [
                {
                    'id': t.id,
                    'title': t.title[:50],
                    'due': t.due_date.strftime('%Y-%m-%d') if t.due_date else None,
                    'priority': t.priority,
                }
                for t in overdue_tasks[:5]
            ],
            'due_today': due_today.count(),
            'due_soon': due_soon.count(),
            'follow_up_due': follow_up_due.count(),
        }

    def _get_tags_context(self) -> List[Dict]:
        """Get frequently used tags"""
        from notes.models import Tag

        tags = Tag.objects.filter(is_active=True).order_by('-usage_count')[:20]

        return [
            {'name': tag.name, 'type': tag.tag_type, 'usage_count': tag.usage_count}
            for tag in tags
        ]

    def _get_scoped_context(self) -> Optional[Dict]:
        """Get additional context if conversation is scoped to a project/area"""
        if not self.conversation:
            return None

        if self.conversation.context_type == 'project' and self.conversation.context_id:
            return self._get_project_detail_context(self.conversation.context_id)
        elif self.conversation.context_type == 'area' and self.conversation.context_id:
            return self._get_area_detail_context(self.conversation.context_id)

        return None

    def _get_project_detail_context(self, project_id: int) -> Optional[Dict]:
        """
        Get comprehensive context for a specific project.
        Includes full project details, area context, all notes with content, and all tasks.
        Designed to support brainstorming and project planning conversations.
        """
        from para.models import Project
        from notes.models import Note
        from tasks.models import Task

        try:
            project = Project.objects.select_related('area').get(
                id=project_id, user=self.user
            )
        except Project.DoesNotExist:
            return None

        area = project.area

        # Get ALL project notes (not just 20) with content for brainstorming
        notes = Note.objects.filter(
            user=self.user,
            container_type='project',
            container_id=project_id,
            is_archived=False
        ).prefetch_related('tags').order_by('-updated_at')

        # Get ALL project tasks from Task model (only parent tasks, not subtasks)
        tasks = Task.objects.filter(
            user=self.user,
            container_type='project',
            container_id=project_id,
            is_archived=False,
            parent_task__isnull=True  # Only get parent tasks, not subtasks
        ).prefetch_related('subtasks').order_by('status', '-priority', 'due_date')

        # Calculate task statistics
        total_tasks = tasks.count()
        completed_tasks = tasks.filter(status='done').count()
        pending_tasks = tasks.exclude(status='done')
        overdue_tasks = [t for t in pending_tasks if t.is_overdue]

        # Get other projects in same area for context
        sibling_projects = Project.objects.filter(
            area=area,
            status='active'
        ).exclude(id=project_id)[:5]

        return {
            'type': 'project',
            'is_focused': True,  # Flag to indicate this is a focused conversation
            'project': {
                'id': project.id,
                'name': project.name,
                'description': project.description,
                'status': project.status,
                'progress': project.progress_percentage,
                'deadline': project.deadline.isoformat() if project.deadline else None,
                'days_until_deadline': (project.deadline - timezone.now().date()).days if project.deadline else None,
                'is_overdue': project.is_overdue(),
                'urgency': project.get_urgency_level(),
                'created_at': project.created_at.strftime('%Y-%m-%d'),
                'completion_notes': project.completion_notes,
            },
            'area': {
                'id': area.id,
                'name': area.name,
                'full_path': area.get_full_path(),
                'description': area.description,
                'is_business': area.is_business_area,
                'area_type': area.area_type,
                'area_type_display': area.get_area_type_display(),
            },
            'sibling_projects': [
                {'id': p.id, 'name': p.name, 'status': p.status}
                for p in sibling_projects
            ],
            'task_stats': {
                'total': total_tasks,
                'completed': completed_tasks,
                'pending': total_tasks - completed_tasks,
                'overdue': len(overdue_tasks),
            },
            'tasks': [
                {
                    'id': t.id,
                    'title': t.title,
                    'description': t.description[:500] if t.description else '',
                    'status': t.status,
                    'is_done': t.status == 'done',
                    'due': t.due_date.strftime('%Y-%m-%d') if t.due_date else None,
                    'priority': t.priority,
                    'is_overdue': t.is_overdue,
                    'is_waiting': t.status == 'waiting',
                    'waiting_on': t.waiting_on if t.status == 'waiting' else None,
                    # Subtask info
                    'has_subtasks': t.has_subtasks,
                    'subtask_count': t.subtask_count,
                    'completed_subtask_count': t.completed_subtask_count,
                    'subtasks': [
                        {'id': st.id, 'title': st.title, 'status': st.status}
                        for st in t.subtasks.all()[:5]  # Show up to 5 subtasks
                    ] if t.has_subtasks else [],
                }
                for t in tasks
            ],
            'notes': [
                {
                    'id': n.id,
                    'title': n.title,
                    'type': n.note_type,
                    'content_preview': n.content[:300] + '...' if n.content and len(n.content) > 300 else n.content,
                    'has_summary': bool(n.summary),
                    'summary': n.summary[:500] if n.summary else None,
                    'tags': list(n.tags.values_list('name', flat=True)),
                    'updated_at': n.updated_at.strftime('%Y-%m-%d'),
                }
                for n in notes
            ],
        }

    def _get_area_detail_context(self, area_id: int) -> Optional[Dict]:
        """
        Get comprehensive context for a specific area.
        Includes full area details, all projects with their status, notes, and sub-areas.
        Designed to support area review and project planning conversations.
        """
        from para.models import Area, Project
        from notes.models import Note
        from tasks.models import Task

        try:
            area = Area.objects.get(id=area_id, user=self.user)
        except Area.DoesNotExist:
            return None

        # Get ALL area projects with details
        projects = Project.objects.filter(area=area).order_by('-status', '-updated_at')

        active_projects = [p for p in projects if p.status == 'active']
        on_hold_projects = [p for p in projects if p.status == 'on_hold']
        completed_projects = [p for p in projects if p.status == 'completed']

        # Get area notes with content
        notes = Note.objects.filter(
            user=self.user,
            container_type='area',
            container_id=area_id,
            is_archived=False
        ).prefetch_related('tags').order_by('-updated_at')

        # Get area tasks from Task model (only parent tasks, not subtasks)
        tasks = Task.objects.filter(
            user=self.user,
            container_type='area',
            container_id=area_id,
            is_archived=False,
            parent_task__isnull=True  # Only get parent tasks, not subtasks
        ).prefetch_related('subtasks').order_by('status', '-priority', 'due_date')

        # Get sub-areas
        sub_areas = []
        for child in area.get_children():
            child_projects = child.get_active_projects_count()
            sub_areas.append({
                'id': child.id,
                'name': child.name,
                'active_projects_count': child_projects,
            })

        return {
            'type': 'area',
            'is_focused': True,
            'area': {
                'id': area.id,
                'name': area.name,
                'full_path': area.get_full_path(),
                'description': area.description,
                'is_business': area.is_business_area,
                'area_type': area.area_type,
                'area_type_display': area.get_area_type_display(),
                'needs_review': area.needs_review(),
                'last_review_date': area.last_review_date.isoformat() if area.last_review_date else None,
                'is_sub_area': area.parent is not None,
                'parent_area': {'id': area.parent.id, 'name': area.parent.name} if area.parent else None,
            },
            'sub_areas': sub_areas,
            'project_stats': {
                'total': projects.count(),
                'active': len(active_projects),
                'on_hold': len(on_hold_projects),
                'completed': len(completed_projects),
            },
            'projects': [
                {
                    'id': p.id,
                    'name': p.name,
                    'description': p.description[:200] if p.description else '',
                    'status': p.status,
                    'progress': p.progress_percentage,
                    'deadline': p.deadline.isoformat() if p.deadline else None,
                    'is_overdue': p.is_overdue(),
                    'urgency': p.get_urgency_level(),
                    'task_counts': p.get_task_counts(),
                }
                for p in projects if p.status in ['active', 'on_hold']
            ],
            'completed_projects': [
                {'id': p.id, 'name': p.name, 'completed_at': p.completed_at.strftime('%Y-%m-%d') if p.completed_at else None}
                for p in completed_projects[:5]
            ],
            'tasks': [
                {
                    'id': t.id,
                    'title': t.title,
                    'status': t.status,
                    'is_done': t.status == 'done',
                    'due': t.due_date.strftime('%Y-%m-%d') if t.due_date else None,
                    'priority': t.priority,
                    'is_overdue': t.is_overdue,
                    'is_waiting': t.status == 'waiting',
                    'waiting_on': t.waiting_on if t.status == 'waiting' else None,
                    # Subtask info
                    'has_subtasks': t.has_subtasks,
                    'subtask_count': t.subtask_count,
                    'completed_subtask_count': t.completed_subtask_count,
                }
                for t in tasks
            ],
            'notes': [
                {
                    'id': n.id,
                    'title': n.title,
                    'type': n.note_type,
                    'content_preview': n.content[:300] + '...' if n.content and len(n.content) > 300 else n.content,
                    'tags': list(n.tags.values_list('name', flat=True)),
                    'updated_at': n.updated_at.strftime('%Y-%m-%d'),
                }
                for n in notes
            ],
        }

    def format_for_system_prompt(self) -> str:
        """
        Format context as markdown text for system prompt.
        Uses focused format for scoped conversations (project/area).
        """
        debug_print("Formatting Context for System Prompt", separator=True)
        ctx = self.build_full_context()

        # Check if this is a scoped conversation (project/area focused)
        if ctx.get('scoped_context'):
            return self._format_scoped_system_prompt(ctx)

        # Default: Full PARA context
        return self._format_full_system_prompt(ctx)

    def _format_scoped_system_prompt(self, ctx: Dict) -> str:
        """
        Format context for scoped conversations (project/area).
        Focuses heavily on the scoped context, minimal summary of the rest.
        """
        sc = ctx['scoped_context']
        lines = []

        if sc['type'] == 'project':
            lines.extend(self._format_project_focused_context(ctx, sc))
        elif sc['type'] == 'area':
            lines.extend(self._format_area_focused_context(ctx, sc))

        return "\n".join(lines)

    def _format_project_focused_context(self, ctx: Dict, sc: Dict) -> List[str]:
        """Format context focused on a specific project for brainstorming."""
        proj = sc['project']
        area = sc.get('area', {})
        task_stats = sc.get('task_stats', {})

        user = ctx['user_summary']
        lines = [
            "=" * 60,
            "# PROJECT BRAINSTORM SESSION",
            "=" * 60,
            "",
            "You are helping the user brainstorm, plan, and work on a specific project.",
            "You have FULL ACCESS to all project details, notes, and tasks below.",
            "Focus on being a helpful collaborator for THIS project.",
            "",
            f"**User:** {user['first_name']}",
            f"**Date:** {user['current_date']} ({user['current_day']})",
            f"**Time:** {user['current_time']}",
            "",
        ]

        # User Profile Context
        has_profile = any([user['about'], user['current_focus'], user['goals'], user['ai_preferences']])
        if has_profile:
            lines.append("## About the User")
            if user['about']:
                lines.append(f"**Background:** {user['about']}")
            if user['current_focus']:
                lines.append(f"**Current Focus:** {user['current_focus']}")
            if user['goals']:
                lines.append(f"**Goals:** {user['goals']}")
            if user['ai_preferences']:
                lines.append(f"**Communication Preferences:** {user['ai_preferences']}")
            lines.append("")

        # Project Header
        lines.append("=" * 60)
        lines.append(f"# PROJECT: {proj['name']}")
        lines.append("=" * 60)
        lines.append("")

        # Key Metrics
        lines.append("## Quick Stats")
        status_emoji = {'active': '🚀', 'on_hold': '⏸️', 'completed': '✅'}.get(proj['status'], '📁')
        lines.append(f"- **Status:** {status_emoji} {proj['status'].upper()}")
        lines.append(f"- **Progress:** {proj['progress']}%")

        if proj.get('deadline'):
            days = proj.get('days_until_deadline')
            if days and days < 0:
                lines.append(f"- **Deadline:** {proj['deadline']} 🔴 OVERDUE by {abs(days)} days!")
            elif days and days <= 7:
                lines.append(f"- **Deadline:** {proj['deadline']} 🟠 {days} days left!")
            elif days:
                lines.append(f"- **Deadline:** {proj['deadline']} ({days} days left)")
            else:
                lines.append(f"- **Deadline:** {proj['deadline']}")

        lines.append(f"- **Tasks:** {task_stats.get('pending', 0)} pending, {task_stats.get('completed', 0)} done")
        if task_stats.get('overdue', 0) > 0:
            lines.append(f"- **⚠️ Overdue Tasks:** {task_stats['overdue']}")
        lines.append("")

        # Parent Area (brief)
        lines.append("## Area Context")
        lines.append(f"**Area:** {area.get('name', 'Unknown')} (ID: {area.get('id', 'N/A')})")
        if area.get('description'):
            lines.append(f"**Description:** {area['description'][:200]}...")
        lines.append("")

        # Project Description (FULL - important for brainstorming)
        if proj.get('description'):
            lines.append("## Project Description")
            lines.append(proj['description'])
            lines.append("")


        # ALL Tasks with Details
        lines.append("=" * 40)
        lines.append("## PROJECT TASKS")
        lines.append("=" * 40)

        if sc.get('tasks'):
            pending_tasks = [t for t in sc['tasks'] if not t['is_completed']]
            completed_tasks = [t for t in sc['tasks'] if t['is_completed']]

            if pending_tasks:
                lines.append("")
                lines.append("### Pending Tasks")
                for task in pending_tasks:
                    priority_icon = {'urgent': '🔴', 'high': '🟠', 'medium': '🟡', 'low': '🟢', 'normal': '⚪'}.get(task.get('priority'), '⚪')
                    overdue_flag = " ⚠️ OVERDUE" if task.get('is_overdue') else ""
                    due_str = f" | Due: {task['due']}" if task.get('due') else ""
                    subtask_str = f" | {task.get('completed_subtask_count', 0)}/{task.get('subtask_count', 0)} subtasks" if task.get('has_subtasks') else ""

                    lines.append(f"")
                    lines.append(f"**{priority_icon} {task['title']}** (ID: {task['id']}){due_str}{subtask_str}{overdue_flag}")
                    if task.get('content'):
                        lines.append(f"   {task['content']}")
                    # Show subtasks if present
                    if task.get('subtasks'):
                        for st in task['subtasks']:
                            st_status = '✅' if st['status'] == 'done' else '⬜'
                            lines.append(f"   {st_status} {st['title']} (ID: {st['id']})")

            if completed_tasks:
                lines.append("")
                lines.append("### Completed Tasks")
                for task in completed_tasks[:15]:
                    lines.append(f"- ✅ {task['title']} (ID: {task['id']})")
                if len(completed_tasks) > 15:
                    lines.append(f"   ...and {len(completed_tasks) - 15} more completed")
        else:
            lines.append("")
            lines.append("*No tasks yet - consider creating tasks to break down the work.*")
        lines.append("")

        # ALL Notes with Content
        lines.append("=" * 40)
        lines.append("## PROJECT NOTES & RESEARCH")
        lines.append("=" * 40)

        if sc.get('notes'):
            for note in sc['notes']:
                lines.append("")
                tags_str = f" | Tags: {', '.join(note['tags'])}" if note.get('tags') else ""
                lines.append(f"### {note['title']} (ID: {note['id']}, Type: {note['type']}){tags_str}")

                if note.get('executive_summary'):
                    lines.append(f"**Summary:** {note['executive_summary']}")
                    lines.append("")

                if note.get('content_preview'):
                    lines.append(note['content_preview'])
                lines.append("")
        else:
            lines.append("")
            lines.append("*No notes yet - consider capturing ideas, research, or meeting notes.*")
        lines.append("")

        # Related Projects (brief)
        if sc.get('sibling_projects'):
            lines.append("## Other Projects in This Area")
            for sp in sc['sibling_projects']:
                lines.append(f"- {sp['name']} [{sp['status']}] (ID: {sp['id']})")
            lines.append("")

        # Minimal System Summary
        lines.append("---")
        lines.append("## Quick Reference (Other Items)")
        lines.append(f"- **Total Areas:** {len(ctx.get('areas', []))}")
        lines.append(f"- **Active Projects:** {len(ctx.get('projects', []))}")
        tasks = ctx.get('tasks_summary', {})
        if tasks.get('overdue', 0) > 0:
            lines.append(f"- **⚠️ Overdue Tasks (all):** {tasks['overdue']}")
        inbox = ctx.get('inbox_summary', {})
        if inbox.get('total_count', 0) > 0:
            lines.append(f"- **Inbox Items:** {inbox['total_count']}")
        lines.append("")

        return lines

    def _format_area_focused_context(self, ctx: Dict, sc: Dict) -> List[str]:
        """Format context focused on a specific area for brainstorming."""
        area = sc['area']
        project_stats = sc.get('project_stats', {})
        user = ctx['user_summary']

        lines = [
            "=" * 60,
            "# AREA BRAINSTORM SESSION",
            "=" * 60,
            "",
            "You are helping the user review, plan, and manage a specific area of responsibility.",
            "You have FULL ACCESS to all area details, projects, notes, and tasks below.",
            "Focus on being a helpful collaborator for THIS area.",
            "",
            f"**User:** {user['first_name']}",
            f"**Date:** {user['current_date']} ({user['current_day']})",
            f"**Time:** {user['current_time']}",
            "",
        ]

        # User Profile Context
        has_profile = any([user['about'], user['current_focus'], user['goals'], user['ai_preferences']])
        if has_profile:
            lines.append("## About the User")
            if user['about']:
                lines.append(f"**Background:** {user['about']}")
            if user['current_focus']:
                lines.append(f"**Current Focus:** {user['current_focus']}")
            if user['goals']:
                lines.append(f"**Goals:** {user['goals']}")
            if user['ai_preferences']:
                lines.append(f"**Communication Preferences:** {user['ai_preferences']}")
            lines.append("")

        # Area Header
        lines.append("=" * 60)
        lines.append(f"# AREA: {area['name']}")
        lines.append("=" * 60)
        lines.append("")

        # Key Metrics
        lines.append("## Quick Stats")
        lines.append(f"- **Type:** {'🏢 Business' if area.get('is_business') else '🏠 Personal'}")
        lines.append(f"- **Active Projects:** {project_stats.get('active', 0)}")
        lines.append(f"- **On Hold:** {project_stats.get('on_hold', 0)}")
        lines.append(f"- **Completed:** {project_stats.get('completed', 0)}")
        if area.get('needs_review'):
            lines.append("- **⚠️ STATUS: NEEDS REVIEW**")
        if area.get('last_review_date'):
            lines.append(f"- **Last Review:** {area['last_review_date']}")
        lines.append("")

        # Area Description (FULL)
        if area.get('description'):
            lines.append("## Area Description")
            lines.append(area['description'])
            lines.append("")


        # ALL Projects with Details
        lines.append("=" * 40)
        lines.append("## AREA PROJECTS")
        lines.append("=" * 40)

        if sc.get('projects'):
            lines.append("")
            for proj in sc['projects']:
                status_icon = {'active': '🚀', 'on_hold': '⏸️', 'completed': '✅'}.get(proj['status'], '📁')
                urgency_flag = ""
                if proj.get('urgency') == 'overdue':
                    urgency_flag = " 🔴 OVERDUE"
                elif proj.get('urgency') == 'urgent':
                    urgency_flag = " 🟠 URGENT"

                deadline_str = f" | Due: {proj['deadline']}" if proj.get('deadline') else ""
                task_counts = proj.get('task_counts', {})
                progress_str = f" | Progress: {proj.get('progress', 0)}%"
                task_str = f" | Tasks: {task_counts.get('completed', 0)}/{task_counts.get('total', 0)}" if task_counts.get('total', 0) > 0 else ""

                lines.append(f"### {status_icon} {proj['name']} (ID: {proj['id']}){urgency_flag}")
                lines.append(f"Status: {proj['status']}{deadline_str}{progress_str}{task_str}")
                if proj.get('description'):
                    lines.append(f"")
                    lines.append(proj['description'][:300] + "..." if len(proj.get('description', '')) > 300 else proj.get('description', ''))
                lines.append("")
        else:
            lines.append("")
            lines.append("*No projects yet - consider creating projects to organize work in this area.*")
        lines.append("")

        # Completed Projects (brief)
        if sc.get('completed_projects'):
            lines.append("### Recently Completed")
            for proj in sc['completed_projects']:
                lines.append(f"- ✅ {proj['name']} (completed: {proj.get('completed_at', 'N/A')})")
            lines.append("")

        # Area-Level Tasks
        if sc.get('tasks'):
            pending = [t for t in sc['tasks'] if not t['is_completed']]
            if pending:
                lines.append("## Area-Level Tasks")
                for task in pending:
                    priority_icon = {'urgent': '🔴', 'high': '🟠', 'medium': '🟡', 'low': '🟢', 'normal': '⚪'}.get(task.get('priority'), '⚪')
                    due_str = f" | Due: {task['due']}" if task.get('due') else ""
                    lines.append(f"- {priority_icon} **{task['title']}** (ID: {task['id']}){due_str}")
                    if task.get('content'):
                        lines.append(f"   {task['content'][:200]}...")
                lines.append("")

        # Area Notes
        lines.append("=" * 40)
        lines.append("## AREA NOTES & REFERENCE")
        lines.append("=" * 40)

        if sc.get('notes'):
            for note in sc['notes'][:15]:
                tags_str = f" | Tags: {', '.join(note['tags'])}" if note.get('tags') else ""
                lines.append(f"")
                lines.append(f"### {note['title']} (ID: {note['id']}, Type: {note['type']}){tags_str}")
                if note.get('content_preview'):
                    lines.append(note['content_preview'][:300] + "..." if len(note.get('content_preview', '')) > 300 else note.get('content_preview', ''))
            if len(sc['notes']) > 15:
                lines.append(f"")
                lines.append(f"*...and {len(sc['notes']) - 15} more notes*")
        else:
            lines.append("")
            lines.append("*No notes yet - consider capturing reference material or documentation.*")
        lines.append("")

        # Minimal System Summary
        lines.append("---")
        lines.append("## Quick Reference (Other Items)")
        other_areas = [a for a in ctx.get('areas', []) if a['id'] != area['id']]
        lines.append(f"- **Other Areas:** {len(other_areas)}")
        tasks = ctx.get('tasks_summary', {})
        if tasks.get('overdue', 0) > 0:
            lines.append(f"- **⚠️ Overdue Tasks (all):** {tasks['overdue']}")
        inbox = ctx.get('inbox_summary', {})
        if inbox.get('total_count', 0) > 0:
            lines.append(f"- **Inbox Items:** {inbox['total_count']}")
        lines.append("")

        return lines

    def _format_full_system_prompt(self, ctx: Dict) -> str:
        """Format the full PARA context (non-scoped conversations)."""
        lines = [
            f"# User Context for {ctx['user_summary']['first_name']}",
            f"**Current Date:** {ctx['user_summary']['current_date']} ({ctx['user_summary']['current_day']})",
            f"**Current Time:** {ctx['user_summary']['current_time']}",
            "",
        ]

        # User Profile Context (about, focus, goals, preferences)
        user = ctx['user_summary']
        has_profile = any([user['about'], user['current_focus'], user['goals'], user['ai_preferences']])
        if has_profile:
            lines.append("## User Profile")
            if user['about']:
                lines.append(f"**About:** {user['about']}")
            if user['current_focus']:
                lines.append(f"**Current Focus:** {user['current_focus']}")
            if user['goals']:
                lines.append(f"**Goals:** {user['goals']}")
            if user['ai_preferences']:
                lines.append(f"**AI Preferences:** {user['ai_preferences']}")
            lines.append("")

        # Recent Activity (what user has been working on based on interaction tracking)
        recent_activity = ctx.get('recent_activity', {})
        if recent_activity.get('has_data'):
            from Core.services import InteractionService
            activity_text = InteractionService.format_context_for_prompt(recent_activity)
            if activity_text:
                lines.append(activity_text)
                lines.append("")

        # Scoped context (if conversation is about a specific project/area)
        if ctx['scoped_context']:
            sc = ctx['scoped_context']
            if sc['type'] == 'project':
                proj = sc['project']
                area = sc.get('area', {})
                task_stats = sc.get('task_stats', {})

                # Prominent header for project-focused mode
                lines.append("=" * 60)
                lines.append("# 🎯 PROJECT FOCUS MODE")
                lines.append("This conversation is focused on a specific project.")
                lines.append("Help the user brainstorm, plan, create notes/tasks, and advance this project.")
                lines.append("=" * 60)
                lines.append("")

                # Project Details
                lines.append("## Project Details")
                lines.append(f"**Name:** {proj['name']} (ID: {proj['id']})")
                lines.append(f"**Status:** {proj['status'].upper()}")
                if proj.get('urgency') and proj['urgency'] != 'none':
                    urgency_labels = {'overdue': '🔴 OVERDUE', 'urgent': '🟠 URGENT', 'soon': '🟡 DUE SOON'}
                    lines.append(f"**Urgency:** {urgency_labels.get(proj['urgency'], proj['urgency'])}")
                if proj.get('deadline'):
                    days = proj.get('days_until_deadline')
                    days_str = f" ({days} days remaining)" if days and days > 0 else " (OVERDUE)" if days and days < 0 else ""
                    lines.append(f"**Deadline:** {proj['deadline']}{days_str}")
                lines.append(f"**Progress:** {proj['progress']}%")
                lines.append("")

                if proj.get('description'):
                    lines.append("### Project Description")
                    lines.append(proj['description'])
                    lines.append("")


                # Area Context
                lines.append("## Parent Area")
                lines.append(f"**Area:** {area.get('name', 'Unknown')} (ID: {area.get('id', 'N/A')})")
                if area.get('description'):
                    lines.append(f"**Description:** {area['description']}")
                lines.append("")

                # Related Projects
                if sc.get('sibling_projects'):
                    lines.append("### Other Projects in This Area")
                    for sp in sc['sibling_projects']:
                        lines.append(f"- {sp['name']} [{sp['status']}] (ID: {sp['id']})")
                    lines.append("")

                # Task Overview
                lines.append("## Project Tasks")
                lines.append(f"**Total:** {task_stats.get('total', 0)} | **Completed:** {task_stats.get('completed', 0)} | **Pending:** {task_stats.get('pending', 0)}")
                if task_stats.get('overdue', 0) > 0:
                    lines.append(f"**⚠️ Overdue:** {task_stats['overdue']} tasks need attention!")
                lines.append("")

                if sc.get('tasks'):
                    # Group tasks by status
                    pending_tasks = [t for t in sc['tasks'] if not t['is_completed']]
                    completed_tasks = [t for t in sc['tasks'] if t['is_completed']]

                    if pending_tasks:
                        lines.append("### Pending Tasks")
                        for task in pending_tasks:
                            priority_icon = {'urgent': '🔴', 'high': '🟠', 'medium': '🟡', 'low': '🟢'}.get(task.get('priority'), '⚪')
                            overdue_flag = " ⚠️ OVERDUE" if task.get('is_overdue') else ""
                            due_str = f" (due: {task['due']})" if task.get('due') else ""
                            subtask_str = f" [{task.get('completed_subtask_count', 0)}/{task.get('subtask_count', 0)} subtasks]" if task.get('has_subtasks') else ""
                            lines.append(f"- {priority_icon} **{task['title']}** [ID: {task['id']}]{due_str}{subtask_str}{overdue_flag}")
                            if task.get('content'):
                                lines.append(f"  {task['content'][:200]}...")
                            # Show subtasks if present
                            if task.get('subtasks'):
                                for st in task['subtasks']:
                                    st_icon = '✅' if st['status'] == 'done' else '⬜'
                                    lines.append(f"    {st_icon} {st['title']} [ID: {st['id']}]")
                        lines.append("")

                    if completed_tasks:
                        lines.append("### Completed Tasks")
                        for task in completed_tasks[:10]:  # Show last 10 completed
                            lines.append(f"- ✅ {task['title']} [ID: {task['id']}]")
                        if len(completed_tasks) > 10:
                            lines.append(f"  ...and {len(completed_tasks) - 10} more completed tasks")
                        lines.append("")
                else:
                    lines.append("*No tasks yet. Consider creating tasks to break down the project.*")
                    lines.append("")

                # Project Notes
                lines.append("## Project Notes & Research")
                if sc.get('notes'):
                    for note in sc['notes']:
                        tags_str = f" [{', '.join(note['tags'])}]" if note.get('tags') else ""
                        lines.append(f"### {note['title']} (ID: {note['id']}, {note['type']}){tags_str}")
                        if note.get('executive_summary'):
                            lines.append(f"**Summary:** {note['executive_summary']}")
                        elif note.get('content_preview'):
                            lines.append(note['content_preview'])
                        lines.append("")
                else:
                    lines.append("*No notes yet. Consider capturing ideas, research, or meeting notes.*")
                    lines.append("")

                lines.append("---")
                lines.append("")

            elif sc['type'] == 'area':
                area = sc['area']
                project_stats = sc.get('project_stats', {})

                # Prominent header for area-focused mode
                lines.append("=" * 60)
                lines.append("# 🎯 AREA FOCUS MODE")
                lines.append("This conversation is focused on a specific area of responsibility.")
                lines.append("Help the user review, plan projects, and maintain standards for this area.")
                lines.append("=" * 60)
                lines.append("")

                # Area Details
                lines.append("## Area Details")
                lines.append(f"**Name:** {area['name']} (ID: {area['id']})")
                lines.append(f"**Type:** {'Business' if area.get('is_business') else 'Personal'}")
                if area.get('needs_review'):
                    lines.append("**⚠️ STATUS: NEEDS REVIEW**")
                if area.get('last_review_date'):
                    lines.append(f"**Last Review:** {area['last_review_date']}")
                lines.append("")


                if area.get('description'):
                    lines.append("### Area Description")
                    lines.append(area['description'])
                    lines.append("")

                # Projects Overview
                lines.append("## Area Projects")
                lines.append(f"**Total:** {project_stats.get('total', 0)} | **Active:** {project_stats.get('active', 0)} | **On Hold:** {project_stats.get('on_hold', 0)} | **Completed:** {project_stats.get('completed', 0)}")
                lines.append("")

                if sc.get('projects'):
                    lines.append("### Active & On-Hold Projects")
                    for proj in sc['projects']:
                        status_icon = "🚀" if proj['status'] == 'active' else "⏸️"
                        urgency_flag = ""
                        if proj.get('urgency') == 'overdue':
                            urgency_flag = " 🔴 OVERDUE"
                        elif proj.get('urgency') == 'urgent':
                            urgency_flag = " 🟠 URGENT"
                        deadline_str = f" (due: {proj['deadline']})" if proj.get('deadline') else ""
                        task_counts = proj.get('task_counts', {})
                        task_str = f" [{task_counts.get('completed', 0)}/{task_counts.get('total', 0)} tasks]" if task_counts.get('total', 0) > 0 else ""

                        lines.append(f"- {status_icon} **{proj['name']}** (ID: {proj['id']}){deadline_str}{urgency_flag}{task_str}")
                        if proj.get('description'):
                            lines.append(f"  {proj['description'][:150]}...")
                    lines.append("")

                if sc.get('completed_projects'):
                    lines.append("### Recently Completed Projects")
                    for proj in sc['completed_projects']:
                        lines.append(f"- ✅ {proj['name']} (completed: {proj.get('completed_at', 'N/A')})")
                    lines.append("")

                # Area Tasks
                if sc.get('tasks'):
                    pending = [t for t in sc['tasks'] if not t['is_completed']]
                    if pending:
                        lines.append("### Area-Level Tasks")
                        for task in pending:
                            priority_icon = {'urgent': '🔴', 'high': '🟠', 'medium': '🟡', 'low': '🟢'}.get(task.get('priority'), '⚪')
                            due_str = f" (due: {task['due']})" if task.get('due') else ""
                            lines.append(f"- {priority_icon} {task['title']} [ID: {task['id']}]{due_str}")
                        lines.append("")

                # Area Notes
                if sc.get('notes'):
                    lines.append("## Area Notes & Reference")
                    for note in sc['notes'][:10]:
                        tags_str = f" [{', '.join(note['tags'])}]" if note.get('tags') else ""
                        lines.append(f"- **{note['title']}** (ID: {note['id']}, {note['type']}){tags_str}")
                        if note.get('content_preview'):
                            lines.append(f"  {note['content_preview'][:150]}...")
                    if len(sc['notes']) > 10:
                        lines.append(f"  ...and {len(sc['notes']) - 10} more notes")
                    lines.append("")

                lines.append("---")
                lines.append("")

        # Compact PARA Catalog - shows what exists without flooding context
        lines.append("## PARA Catalog")
        lines.append("*Compact view of all areas and projects. Use tools for details.*")
        lines.append("")

        catalog = {
            "areas_catalog": [],
            "projects_catalog": [],
            "lookup_hints": {
                "area_details": "get_area(id), get_area_projects(id), get_area_tasks(id), get_area_notes(id)",
                "project_details": "get_project(id), get_project_tasks(id), get_project_notes(id)",
                "tasks": "list_tasks(status, due, priority, container_type, container_id)",
                "search": "search_all(query), search_notes(query)",
                "inbox": "get_inbox()",
                "rule": "NEVER invent data - always fetch first"
            }
        }

        # Build compact areas catalog with explicit hierarchy
        if ctx['areas']:
            for area in ctx['areas']:
                # Add root area (parent_id is null)
                area_entry = {
                    "id": area['id'],
                    "name": area['name'],
                    "parent_id": None,
                    "active_projects": area['active_projects_count']
                }
                catalog["areas_catalog"].append(area_entry)

                # Add sub-areas with explicit parent reference
                for sub_area in area.get('sub_areas', []):
                    sub_entry = {
                        "id": sub_area['id'],
                        "name": sub_area['name'],
                        "parent_id": area['id'],
                        "active_projects": sub_area.get('active_projects_count', 0)
                    }
                    catalog["areas_catalog"].append(sub_entry)

        # Build compact projects catalog
        if ctx['projects']:
            for proj in ctx['projects']:
                proj_entry = {
                    "id": proj['id'],
                    "name": proj['name'],
                    "area_id": proj['area_id'],
                    "status": proj['status']
                }
                # Only add deadline if it exists
                if proj.get('deadline'):
                    proj_entry["deadline"] = proj['deadline']
                # Only add urgency if it's notable
                if proj.get('urgency') and proj['urgency'] not in ['normal', 'none', None]:
                    proj_entry["urgency"] = proj['urgency']
                catalog["projects_catalog"].append(proj_entry)

        lines.append("```json")
        lines.append(json.dumps(catalog, indent=2))
        lines.append("```")
        lines.append("")

        # Tasks Summary
        lines.append("## Tasks Overview")
        tasks = ctx['tasks_summary']
        lines.append(f"**Total:** {tasks['total']} | To Do: {tasks['todo']} | In Progress: {tasks['in_progress']} | Done: {tasks['done']}")
        if tasks['overdue'] > 0:
            lines.append(f"**⚠️ OVERDUE:** {tasks['overdue']} tasks")
            for t in tasks['overdue_tasks']:
                lines.append(f"  - {t['title']} [ID: {t['id']}] (was due: {t['due']})")
        if tasks['due_today'] > 0:
            lines.append(f"**📅 Due Today:** {tasks['due_today']} tasks")
        if tasks['due_soon'] > 0:
            lines.append(f"**🔜 Due This Week:** {tasks['due_soon']} tasks")
        lines.append("")

        # Inbox Status
        lines.append("## Inbox Status")
        inbox = ctx['inbox_summary']
        lines.append(f"**Items in Inbox:** {inbox['total_count']}")
        if inbox['types']:
            type_str = ", ".join([f"{k}: {v}" for k, v in inbox['types'].items()])
            lines.append(f"**Types:** {type_str}")
        if inbox['oldest_date']:
            lines.append(f"**Oldest Item:** {inbox['oldest_date']}")
        lines.append("")

        # Recent Notes (brief)
        lines.append("## Recent Notes")
        if ctx['recent_notes']:
            for note in ctx['recent_notes'][:10]:
                tags_str = f" [{', '.join(note['tags'])}]" if note['tags'] else ""
                lines.append(f"- {note['title']} (ID: {note['id']}, {note['type']}){tags_str}")
        else:
            lines.append("- No recent notes")

        return "\n".join(lines)
