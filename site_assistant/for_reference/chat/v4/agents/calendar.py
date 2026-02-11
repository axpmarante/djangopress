"""
Calendar Agent for Chat V4

Handles calendar and timeline operations:
- Deadline queries
- Timeline views
- Scheduling
- Date-based filtering
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import date, datetime, timedelta
from collections import defaultdict

from .base import (
    BaseAgent, AgentContext, ActionDecision,
    DatabaseAgentMixin, ActionDispatcherMixin
)
from ..state import StepResult

logger = logging.getLogger(__name__)


class CalendarAgent(BaseAgent, DatabaseAgentMixin, ActionDispatcherMixin):
    """
    Specialized agent for calendar and timeline operations.
    """

    AGENT_TYPE = "calendar"

    AVAILABLE_ACTIONS = [
        "today",
        "tomorrow",
        "this_week",
        "next_week",
        "this_month",
        "date_range",
        "deadlines",
        "timeline",
        "free_days",
        "busiest_days",
    ]

    def get_actions_description(self) -> str:
        """Return description of available actions for LLM decision-making."""
        return """
### today
Get tasks and deadlines for today.
Params: none

### tomorrow
Get tasks and deadlines for tomorrow.
Params: none

### this_week
Get tasks and deadlines for the current week.
Params: none

### next_week
Get tasks and deadlines for next week.
Params: none

### this_month
Get tasks and deadlines for the current month.
Params: none

### date_range
Get items for a custom date range.
Params:
- start_date (required): Start date (YYYY-MM-DD or "today", "tomorrow")
- end_date: End date (defaults to start_date)

### deadlines
Get upcoming deadlines for tasks and projects.
Params:
- days: Number of days ahead (default: 30)

### timeline
Get a day-by-day timeline view.
Params:
- days: Number of days to show (default: 14)

### free_days
Find days with no scheduled items.
Params:
- days: Number of days to check (default: 14)

### busiest_days
Find the busiest days by item count.
Params:
- days: Number of days to check (default: 30)
"""

    def _execute_action(self, context: AgentContext, decision: ActionDecision) -> StepResult:
        """Execute the decided action using dispatcher."""
        return self._dispatch_action(context, decision)

    # ========================================================================
    # Action Handlers
    # ========================================================================

    def _handle_today(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Get items for today"""
        today = date.today()
        return self._get_items_for_date_range(context, today, today, "today", action="today")

    def _handle_tomorrow(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Get items for tomorrow"""
        tomorrow = date.today() + timedelta(days=1)
        return self._get_items_for_date_range(context, tomorrow, tomorrow, "tomorrow", action="tomorrow")

    def _handle_this_week(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Get items for this week"""
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        return self._get_items_for_date_range(context, week_start, week_end, "this week", action="this_week")

    def _handle_next_week(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Get items for next week"""
        today = date.today()
        next_week_start = today + timedelta(days=(7 - today.weekday()))
        next_week_end = next_week_start + timedelta(days=6)
        return self._get_items_for_date_range(context, next_week_start, next_week_end, "next week", action="next_week")

    def _handle_this_month(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Get items for this month"""
        today = date.today()
        month_start = today.replace(day=1)
        # Get last day of month
        if today.month == 12:
            month_end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        return self._get_items_for_date_range(context, month_start, month_end, "this month", action="this_month")

    def _handle_date_range(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Get items for a custom date range"""
        start_date = self._parse_date(params.get('start_date'))
        end_date = self._parse_date(params.get('end_date'))

        if not start_date:
            return self._error_result(context, "date_range", "Start date is required")

        if not end_date:
            end_date = start_date

        if end_date < start_date:
            return self._error_result(context, "date_range", "End date must be after start date")

        return self._get_items_for_date_range(
            context, start_date, end_date,
            f"{start_date.isoformat()} to {end_date.isoformat()}"
        )

    def _handle_deadlines(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Get upcoming deadlines"""
        from notes.models import Task
        from para.models import Project
        from django.utils import timezone

        days = params.get('days', 30)
        today = timezone.now().date()
        end_date = today + timedelta(days=days)

        deadlines = []

        # Task deadlines
        tasks = Task.objects.filter(
            user_id=context.user_id,
            due_date__gte=today,
            due_date__lte=end_date,
            is_archived=False
        ).exclude(status='done').order_by('due_date')

        for task in tasks:
            # Convert datetime to date for days calculation
            task_due_date = task.due_date.date() if hasattr(task.due_date, 'date') else task.due_date
            deadlines.append({
                'type': 'task',
                'id': task.id,
                'title': task.title,
                'date': task.due_date.isoformat(),
                'days_until': (task_due_date - today).days,
                'priority': task.priority
            })

        # Project deadlines
        projects = Project.objects.filter(
            user_id=context.user_id,
            deadline__gte=today,
            deadline__lte=end_date,
            status='active',
            is_archived=False
        ).order_by('deadline')

        for project in projects:
            deadlines.append({
                'type': 'project',
                'id': project.id,
                'title': project.name,
                'date': project.deadline.isoformat(),
                'days_until': (project.deadline - today).days
            })

        # Sort by date
        deadlines.sort(key=lambda x: x['date'])

        return self._success_result(
            context,
            action="deadlines",
            output={
                'days_ahead': days,
                'deadlines': deadlines,
                'count': len(deadlines),
                'by_type': {
                    'tasks': sum(1 for d in deadlines if d['type'] == 'task'),
                    'projects': sum(1 for d in deadlines if d['type'] == 'project')
                }
            },
            summary=f"Found {len(deadlines)} deadline(s) in the next {days} days",
            entities={
                'task': [d['id'] for d in deadlines if d['type'] == 'task'],
                'project': [d['id'] for d in deadlines if d['type'] == 'project']
            }
        )

    def _handle_timeline(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Get a timeline view of items"""
        from notes.models import Task
        from para.models import Project

        days = params.get('days', 14)
        today = date.today()

        # Build timeline day by day
        timeline = []

        for i in range(days):
            current_date = today + timedelta(days=i)
            day_data = {
                'date': current_date.isoformat(),
                'day_name': current_date.strftime('%A'),
                'is_today': current_date == today,
                'is_weekend': current_date.weekday() >= 5,
                'tasks': [],
                'project_deadlines': []
            }

            # Tasks due this day
            tasks = Task.objects.filter(
                user_id=context.user_id,
                due_date=current_date,
                is_archived=False
            ).exclude(status='done')

            day_data['tasks'] = [
                {'id': t.id, 'title': t.title, 'priority': t.priority, 'status': t.status}
                for t in tasks
            ]

            # Project deadlines
            projects = Project.objects.filter(
                user_id=context.user_id,
                deadline=current_date,
                status='active',
                is_archived=False
            )

            day_data['project_deadlines'] = [
                {'id': p.id, 'name': p.name}
                for p in projects
            ]

            day_data['item_count'] = len(day_data['tasks']) + len(day_data['project_deadlines'])
            timeline.append(day_data)

        total_items = sum(d['item_count'] for d in timeline)
        busy_days = sum(1 for d in timeline if d['item_count'] > 3)

        return self._success_result(
            context,
            action="timeline",
            output={
                'days': days,
                'timeline': timeline,
                'total_items': total_items,
                'busy_days': busy_days
            },
            summary=f"Timeline for next {days} days: {total_items} items, {busy_days} busy days",
            entities={}
        )

    def _handle_free_days(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Find days with no scheduled items"""
        from notes.models import Task
        from para.models import Project

        days = params.get('days', 14)
        today = date.today()
        end_date = today + timedelta(days=days)

        # Get all dates with tasks
        task_dates = set(
            Task.objects.filter(
                user_id=context.user_id,
                due_date__gte=today,
                due_date__lte=end_date,
                is_archived=False
            ).exclude(status='done').values_list('due_date', flat=True)
        )

        # Get all dates with project deadlines
        project_dates = set(
            Project.objects.filter(
                user_id=context.user_id,
                deadline__gte=today,
                deadline__lte=end_date,
                status='active',
                is_archived=False
            ).values_list('deadline', flat=True)
        )

        busy_dates = task_dates | project_dates

        free_days = []
        for i in range(days):
            current_date = today + timedelta(days=i)
            if current_date not in busy_dates:
                free_days.append({
                    'date': current_date.isoformat(),
                    'day_name': current_date.strftime('%A'),
                    'is_weekend': current_date.weekday() >= 5
                })

        return self._success_result(
            context,
            action="free_days",
            output={
                'days_checked': days,
                'free_days': free_days,
                'free_count': len(free_days),
                'weekday_free': sum(1 for d in free_days if not d['is_weekend']),
                'weekend_free': sum(1 for d in free_days if d['is_weekend'])
            },
            summary=f"Found {len(free_days)} free day(s) in the next {days} days",
            entities={}
        )

    def _handle_busiest_days(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Find the busiest days"""
        from notes.models import Task
        from para.models import Project

        days = params.get('days', 30)
        today = date.today()
        end_date = today + timedelta(days=days)

        # Count items per day
        day_counts = defaultdict(lambda: {'tasks': 0, 'projects': 0})

        # Count tasks
        tasks = Task.objects.filter(
            user_id=context.user_id,
            due_date__gte=today,
            due_date__lte=end_date,
            is_archived=False
        ).exclude(status='done').values('due_date')

        for task in tasks:
            day_counts[task['due_date']]['tasks'] += 1

        # Count project deadlines
        projects = Project.objects.filter(
            user_id=context.user_id,
            deadline__gte=today,
            deadline__lte=end_date,
            status='active',
            is_archived=False
        ).values('deadline')

        for project in projects:
            day_counts[project['deadline']]['projects'] += 1

        # Convert to list and sort
        busiest = []
        for d, counts in day_counts.items():
            total = counts['tasks'] + counts['projects']
            if total > 0:
                busiest.append({
                    'date': d.isoformat(),
                    'day_name': d.strftime('%A'),
                    'tasks': counts['tasks'],
                    'projects': counts['projects'],
                    'total': total
                })

        busiest.sort(key=lambda x: x['total'], reverse=True)

        return self._success_result(
            context,
            action="busiest_days",
            output={
                'days_checked': days,
                'busiest_days': busiest[:10],
                'days_with_items': len(busiest),
                'max_items_day': busiest[0] if busiest else None
            },
            summary=f"Found {len(busiest)} day(s) with scheduled items",
            entities={}
        )

    # ========================================================================
    # Helpers
    # ========================================================================

    def _get_items_for_date_range(
        self,
        context: AgentContext,
        start_date: date,
        end_date: date,
        label: str,
        action: str = "date_range"
    ) -> StepResult:
        """Get all items for a date range"""
        from notes.models import Task
        from para.models import Project

        items = {'tasks': [], 'project_deadlines': [], 'overdue': []}

        today = date.today()

        # Tasks in range
        tasks = Task.objects.filter(
            user_id=context.user_id,
            due_date__gte=start_date,
            due_date__lte=end_date,
            is_archived=False
        ).order_by('due_date')

        for task in tasks:
            task_data = {
                'id': task.id,
                'title': task.title,
                'due_date': task.due_date.isoformat(),
                'priority': task.priority,
                'status': task.status
            }
            items['tasks'].append(task_data)

        # Project deadlines in range
        projects = Project.objects.filter(
            user_id=context.user_id,
            deadline__gte=start_date,
            deadline__lte=end_date,
            status='active',
            is_archived=False
        ).order_by('deadline')

        for project in projects:
            items['project_deadlines'].append({
                'id': project.id,
                'name': project.name,
                'deadline': project.deadline.isoformat()
            })

        # Also include overdue if start_date is today
        if start_date == today:
            overdue = Task.objects.filter(
                user_id=context.user_id,
                due_date__lt=today,
                is_archived=False
            ).exclude(status='done').order_by('due_date')

            for task in overdue:
                items['overdue'].append({
                    'id': task.id,
                    'title': task.title,
                    'due_date': task.due_date.isoformat(),
                    'days_overdue': (today - task.due_date).days
                })

        total = len(items['tasks']) + len(items['project_deadlines'])

        task_ids = [t['id'] for t in items['tasks']] + [t['id'] for t in items['overdue']]
        project_ids = [p['id'] for p in items['project_deadlines']]

        return self._success_result(
            context,
            action=action,
            output={
                'date_range': {
                    'start': start_date.isoformat(),
                    'end': end_date.isoformat(),
                    'label': label
                },
                'items': items,
                'counts': {
                    'tasks': len(items['tasks']),
                    'project_deadlines': len(items['project_deadlines']),
                    'overdue': len(items['overdue'])
                },
                'total': total
            },
            summary=f"{label.title()}: {len(items['tasks'])} task(s), {len(items['project_deadlines'])} deadline(s)" +
                    (f", {len(items['overdue'])} overdue" if items['overdue'] else ""),
            entities={'task': task_ids, 'project': project_ids}
        )

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
            elif value_lower == 'yesterday':
                return today - timedelta(days=1)

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
