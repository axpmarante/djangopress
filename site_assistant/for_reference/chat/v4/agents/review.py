"""
Review Agent for Chat V4

Handles review-related operations:
- Identifying stale/neglected items
- Cleanup suggestions
- Weekly review support
- Progress summaries
"""

import logging
from typing import Dict, List, Any
from datetime import date, timedelta

from .base import (
    BaseAgent, AgentContext, ActionDecision,
    DatabaseAgentMixin, ActionDispatcherMixin
)
from ..state import StepResult

logger = logging.getLogger(__name__)


class ReviewAgent(BaseAgent, DatabaseAgentMixin, ActionDispatcherMixin):
    """
    Specialized agent for review and maintenance operations.
    """

    AGENT_TYPE = "review"

    AVAILABLE_ACTIONS = [
        "stale_items",
        "neglected_projects",
        "overdue_tasks",
        "inbox_status",
        "cleanup_suggestions",
        "weekly_summary",
        "progress_report",
        "area_health",
    ]

    def get_actions_description(self) -> str:
        """Return description of available actions for LLM decision-making."""
        return """
### stale_items
Find items not updated in a while.
Params:
- days: Number of days threshold (default: 30)

### neglected_projects
Find active projects with no recent activity.
Params:
- days: Number of days threshold (default: 14)

### overdue_tasks
Get all overdue tasks grouped by urgency.
Params: none

### inbox_status
Get inbox status and recommendations.
Params: none

### cleanup_suggestions
Generate cleanup suggestions for the system.
Params: none

### weekly_summary
Generate a weekly summary of activity.
Params: none

### progress_report
Generate progress report for a project or area.
Params:
- project_id: ID of project to report on
- area_id: ID of area to report on
(One of project_id or area_id is required)

### area_health
Assess health of all areas.
Params: none
"""

    def _execute_action(self, context: AgentContext, decision: ActionDecision) -> StepResult:
        """Execute the decided action using dispatcher."""
        return self._dispatch_action(context, decision)

    # ========================================================================
    # Action Handlers
    # ========================================================================

    def _handle_stale_items(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Find items not updated in a while"""
        from notes.models import Note, Task
        from para.models import Project

        days = params.get('days', 30)
        threshold = date.today() - timedelta(days=days)

        results = {'notes': [], 'tasks': [], 'projects': []}

        # Stale notes
        stale_notes = Note.objects.filter(
            user_id=context.user_id,
            updated_at__date__lt=threshold,
            is_archived=False
        ).order_by('updated_at')[:20]

        results['notes'] = [
            {
                'id': n.id,
                'title': n.title,
                'last_updated': n.updated_at.date().isoformat(),
                'days_stale': (date.today() - n.updated_at.date()).days
            }
            for n in stale_notes
        ]

        # Stale tasks (not done, not updated)
        stale_tasks = Task.objects.filter(
            user_id=context.user_id,
            updated_at__date__lt=threshold,
            is_archived=False
        ).exclude(status='done').order_by('updated_at')[:20]

        results['tasks'] = [
            {
                'id': t.id,
                'title': t.title,
                'status': t.status,
                'last_updated': t.updated_at.date().isoformat(),
                'days_stale': (date.today() - t.updated_at.date()).days
            }
            for t in stale_tasks
        ]

        # Stale active projects
        stale_projects = Project.objects.filter(
            user_id=context.user_id,
            updated_at__date__lt=threshold,
            status='active',
            is_archived=False
        ).order_by('updated_at')[:10]

        results['projects'] = [
            {
                'id': p.id,
                'name': p.name,
                'last_updated': p.updated_at.date().isoformat(),
                'days_stale': (date.today() - p.updated_at.date()).days
            }
            for p in stale_projects
        ]

        total = sum(len(v) for v in results.values())

        return self._success_result(
            context,
            action="stale_items",
            output={
                'threshold_days': days,
                'results': results,
                'counts': {k: len(v) for k, v in results.items()},
                'total': total
            },
            summary=f"Found {total} stale item(s) not updated in {days}+ days",
            entities={
                'note': [n['id'] for n in results['notes']],
                'task': [t['id'] for t in results['tasks']],
                'project': [p['id'] for p in results['projects']]
            }
        )

    def _handle_neglected_projects(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Find active projects with no recent activity"""
        from para.models import Project
        from notes.models import Task

        days = params.get('days', 14)
        threshold = date.today() - timedelta(days=days)

        neglected = []

        active_projects = Project.objects.filter(
            user_id=context.user_id,
            status='active',
            is_archived=False
        )

        for project in active_projects:
            # Check for recent task activity
            recent_tasks = Task.objects.filter(
                user_id=context.user_id,
                container_type='project',
                container_id=project.id,
                updated_at__date__gte=threshold
            ).exists()

            if not recent_tasks and project.updated_at.date() < threshold:
                neglected.append({
                    'id': project.id,
                    'name': project.name,
                    'last_updated': project.updated_at.date().isoformat(),
                    'days_neglected': (date.today() - project.updated_at.date()).days,
                    'deadline': project.deadline.isoformat() if project.deadline else None
                })

        context.set_in_memory('neglected_projects', [p['id'] for p in neglected])

        return self._success_result(
            context,
            action="neglected_projects",
            output={
                'threshold_days': days,
                'projects': neglected,
                'count': len(neglected)
            },
            summary=f"Found {len(neglected)} neglected project(s) with no activity in {days}+ days",
            entities={'project': [p['id'] for p in neglected]}
        )

    def _handle_overdue_tasks(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Get all overdue tasks"""
        from notes.models import Task

        today = date.today()

        overdue = Task.objects.filter(
            user_id=context.user_id,
            due_date__lt=today,
            is_archived=False
        ).exclude(status='done').order_by('due_date')

        tasks_list = list(overdue[:50])

        # Group by how overdue
        by_urgency = {
            'critical': [],  # > 7 days overdue
            'urgent': [],    # 3-7 days overdue
            'overdue': []    # 1-2 days overdue
        }

        for task in tasks_list:
            days_overdue = (today - task.due_date).days
            task_data = {
                'id': task.id,
                'title': task.title,
                'due_date': task.due_date.isoformat(),
                'days_overdue': days_overdue,
                'priority': task.priority,
                'status': task.status
            }

            if days_overdue > 7:
                by_urgency['critical'].append(task_data)
            elif days_overdue >= 3:
                by_urgency['urgent'].append(task_data)
            else:
                by_urgency['overdue'].append(task_data)

        task_ids = [t.id for t in tasks_list]
        context.set_in_memory('overdue_tasks', task_ids)

        return self._success_result(
            context,
            action="overdue_tasks",
            output={
                'by_urgency': by_urgency,
                'counts': {k: len(v) for k, v in by_urgency.items()},
                'total': len(tasks_list)
            },
            summary=f"Found {len(tasks_list)} overdue task(s): {len(by_urgency['critical'])} critical, {len(by_urgency['urgent'])} urgent",
            entities={'task': task_ids}
        )

    def _handle_inbox_status(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Get inbox status and recommendations"""
        from notes.models import Note, Task

        # Count inbox items
        inbox_notes = Note.objects.filter(
            user_id=context.user_id,
            container_type='inbox',
            is_archived=False
        )

        inbox_tasks = Task.objects.filter(
            user_id=context.user_id,
            container_type='inbox',
            is_archived=False
        )

        note_count = inbox_notes.count()
        task_count = inbox_tasks.count()
        total = note_count + task_count

        # Find old inbox items
        old_threshold = date.today() - timedelta(days=7)
        old_items = (
            inbox_notes.filter(created_at__date__lt=old_threshold).count() +
            inbox_tasks.filter(created_at__date__lt=old_threshold).count()
        )

        # Generate recommendations
        recommendations = []
        if total > 20:
            recommendations.append("Your inbox has many items. Consider processing them.")
        if old_items > 5:
            recommendations.append(f"You have {old_items} items older than 7 days in inbox.")
        if task_count > note_count * 2:
            recommendations.append("Many tasks in inbox. Consider moving them to projects.")

        status = 'healthy' if total < 10 else 'attention_needed' if total < 30 else 'overflowing'

        return self._success_result(
            context,
            action="inbox_status",
            output={
                'note_count': note_count,
                'task_count': task_count,
                'total': total,
                'old_items': old_items,
                'status': status,
                'recommendations': recommendations
            },
            summary=f"Inbox: {total} items ({status})",
            entities={}
        )

    def _handle_cleanup_suggestions(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Generate cleanup suggestions"""
        from notes.models import Note, Task
        from para.models import Project, Area

        suggestions = []

        # Check for completed tasks that could be archived
        completed_tasks = Task.objects.filter(
            user_id=context.user_id,
            status='done',
            is_archived=False,
            updated_at__date__lt=date.today() - timedelta(days=7)
        ).count()

        if completed_tasks > 0:
            suggestions.append({
                'type': 'archive_completed_tasks',
                'count': completed_tasks,
                'message': f"Archive {completed_tasks} completed task(s) from 7+ days ago"
            })

        # Check for cancelled/completed projects
        old_projects = Project.objects.filter(
            user_id=context.user_id,
            status__in=['completed', 'cancelled'],
            is_archived=False
        ).count()

        if old_projects > 0:
            suggestions.append({
                'type': 'archive_finished_projects',
                'count': old_projects,
                'message': f"Archive {old_projects} completed/cancelled project(s)"
            })

        # Check for empty areas (Area uses is_active, not is_archived)
        empty_areas = []
        for area in Area.objects.filter(user_id=context.user_id, is_active=True):
            if not area.projects.filter(is_archived=False).exists():
                if not Note.objects.filter(user_id=context.user_id, container_type='area', container_id=area.id, is_archived=False).exists():
                    empty_areas.append(area.name)

        if empty_areas:
            suggestions.append({
                'type': 'review_empty_areas',
                'count': len(empty_areas),
                'items': empty_areas[:5],
                'message': f"Review {len(empty_areas)} area(s) with no content"
            })

        # Check for notes without tags
        untagged_notes = Note.objects.filter(
            user_id=context.user_id,
            is_archived=False,
            tags__isnull=True
        ).count()

        if untagged_notes > 10:
            suggestions.append({
                'type': 'tag_notes',
                'count': untagged_notes,
                'message': f"Add tags to {untagged_notes} untagged note(s)"
            })

        return self._success_result(
            context,
            action="cleanup_suggestions",
            output={
                'suggestions': suggestions,
                'count': len(suggestions)
            },
            summary=f"Generated {len(suggestions)} cleanup suggestion(s)",
            entities={}
        )

    def _handle_weekly_summary(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Generate weekly summary"""
        from notes.models import Note, Task
        from para.models import Project

        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)

        summary = {
            'week': f"{week_start.isoformat()} to {week_end.isoformat()}",
            'tasks': {},
            'notes': {},
            'projects': {}
        }

        # Tasks summary
        summary['tasks']['completed'] = Task.objects.filter(
            user_id=context.user_id,
            status='done',
            updated_at__date__gte=week_start,
            updated_at__date__lte=today
        ).count()

        summary['tasks']['created'] = Task.objects.filter(
            user_id=context.user_id,
            created_at__date__gte=week_start,
            created_at__date__lte=today
        ).count()

        summary['tasks']['pending'] = Task.objects.filter(
            user_id=context.user_id,
            status__in=['todo', 'in_progress', 'waiting'],
            is_archived=False
        ).count()

        # Notes summary
        summary['notes']['created'] = Note.objects.filter(
            user_id=context.user_id,
            created_at__date__gte=week_start,
            created_at__date__lte=today
        ).count()

        summary['notes']['updated'] = Note.objects.filter(
            user_id=context.user_id,
            updated_at__date__gte=week_start,
            updated_at__date__lte=today
        ).exclude(
            created_at__date__gte=week_start
        ).count()

        # Projects summary
        summary['projects']['active'] = Project.objects.filter(
            user_id=context.user_id,
            status='active',
            is_archived=False
        ).count()

        summary['projects']['completed_this_week'] = Project.objects.filter(
            user_id=context.user_id,
            status='completed',
            updated_at__date__gte=week_start
        ).count()

        return self._success_result(
            context,
            action="weekly_summary",
            output=summary,
            summary=f"This week: {summary['tasks']['completed']} tasks done, {summary['notes']['created']} notes created",
            entities={}
        )

    def _handle_progress_report(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Generate progress report for a project or area"""
        from para.models import Project, Area
        from notes.models import Task

        project_id = params.get('project_id')
        area_id = params.get('area_id')

        if project_id:
            project = self._get_object_or_none(Project, context.user_id, project_id)
            if not project:
                return self._not_found_result(context, "progress_report", "project", project_id)

            # Get project tasks
            tasks = Task.objects.filter(
                user_id=context.user_id,
                container_type='project',
                container_id=project_id
            )

            total = tasks.count()
            done = tasks.filter(status='done').count()
            in_progress = tasks.filter(status='in_progress').count()

            report = {
                'type': 'project',
                'id': project.id,
                'name': project.name,
                'status': project.status,
                'progress_percentage': project.progress_percentage or (done / total * 100 if total > 0 else 0),
                'tasks': {
                    'total': total,
                    'done': done,
                    'in_progress': in_progress,
                    'remaining': total - done
                },
                'deadline': project.deadline.isoformat() if project.deadline else None
            }

            return self._success_result(
                context,
                action="progress_report",
                output={'report': report},
                summary=f"Project '{project.name}': {done}/{total} tasks done ({report['progress_percentage']:.0f}%)",
                entities={'project': [project.id]}
            )

        elif area_id:
            area = self._get_object_or_none(Area, context.user_id, area_id)
            if not area:
                return self._not_found_result(context, "progress_report", "area", area_id)

            # Get area projects
            projects = area.projects.filter(is_archived=False)
            active = projects.filter(status='active').count()
            completed = projects.filter(status='completed').count()

            report = {
                'type': 'area',
                'id': area.id,
                'name': area.name,
                'projects': {
                    'total': projects.count(),
                    'active': active,
                    'completed': completed
                }
            }

            return self._success_result(
                context,
                action="progress_report",
                output={'report': report},
                summary=f"Area '{area.name}': {active} active project(s), {completed} completed",
                entities={'area': [area.id]}
            )

        else:
            return self._error_result(context, "progress_report", "Project ID or Area ID is required")

    def _handle_area_health(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Assess health of all areas"""
        from para.models import Area, Project
        from notes.models import Task

        areas = Area.objects.filter(
            user_id=context.user_id,
            is_active=True
        )

        health_reports = []

        for area in areas:
            projects = area.projects.filter(is_archived=False)
            active_projects = projects.filter(status='active').count()

            # Get tasks in area
            area_tasks = Task.objects.filter(
                user_id=context.user_id,
                container_type='area',
                container_id=area.id,
                is_archived=False
            )

            overdue = area_tasks.filter(
                due_date__lt=date.today()
            ).exclude(status='done').count()

            # Determine health
            if overdue > 5:
                health = 'critical'
            elif overdue > 0 or active_projects > 5:
                health = 'attention_needed'
            elif active_projects == 0:
                health = 'inactive'
            else:
                health = 'healthy'

            health_reports.append({
                'id': area.id,
                'name': area.name,
                'health': health,
                'active_projects': active_projects,
                'overdue_tasks': overdue
            })

        # Sort by health (critical first)
        health_order = {'critical': 0, 'attention_needed': 1, 'inactive': 2, 'healthy': 3}
        health_reports.sort(key=lambda x: health_order.get(x['health'], 4))

        return self._success_result(
            context,
            action="area_health",
            output={
                'areas': health_reports,
                'summary': {
                    'critical': sum(1 for a in health_reports if a['health'] == 'critical'),
                    'attention_needed': sum(1 for a in health_reports if a['health'] == 'attention_needed'),
                    'healthy': sum(1 for a in health_reports if a['health'] == 'healthy'),
                    'inactive': sum(1 for a in health_reports if a['health'] == 'inactive')
                }
            },
            summary=f"Assessed {len(health_reports)} area(s)",
            entities={'area': [a['id'] for a in health_reports]}
        )
