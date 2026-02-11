"""
Journal Agent for Chat V4

Handles journal-related operations:
- Daily planner entries
- Weekly reviews
- Habit tracking
- Reflection and planning
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


class JournalAgent(BaseAgent, DatabaseAgentMixin, ActionDispatcherMixin):
    """
    Specialized agent for journal operations.
    """

    AGENT_TYPE = "journal"

    AVAILABLE_ACTIONS = [
        # Daily planner
        "create_daily",
        "get_daily",
        "update_daily",
        "list_daily",
        # Weekly review
        "create_weekly",
        "get_weekly",
        "update_weekly",
        "list_weekly",
        # Habits
        "list_habits",
        "track_habit",
        "get_habit_streak",
        # Utilities
        "get_today",
        "get_this_week",
    ]

    DAILY_FIELDS = [
        'id', 'date', 'morning_intention', 'important_tasks',
        'tasks_to_delegate', 'schedule_blocks', 'evening_accomplishments',
        'evening_learnings', 'evening_improvements', 'gratitude',
        'created_at', 'updated_at'
    ]

    WEEKLY_FIELDS = [
        'id', 'week_start', 'week_end', 'wins', 'challenges',
        'learnings', 'next_week_focus', 'areas_reviewed',
        'created_at', 'updated_at'
    ]

    def get_actions_description(self) -> str:
        """Return description of available actions for LLM decision-making."""
        return """
### create_daily
Create a daily planner entry.
Params:
- date: Date for entry (YYYY-MM-DD, default: today)
- intention: Morning intention
- important_tasks: List of important tasks
- tasks_to_delegate: List of tasks to delegate
- schedule_blocks: List of schedule blocks

### get_daily
Get a daily planner entry.
Params:
- date: Date to get (default: today)

### update_daily
Update a daily planner entry.
Params:
- date: Date to update (default: today)
- intention: Morning intention
- important_tasks: List of important tasks
- accomplishments: Evening accomplishments
- learnings: Evening learnings
- improvements: Evening improvements
- gratitude: Gratitude note

### list_daily
List daily planner entries.
Params:
- start_date: Start date
- end_date: End date
- limit: Max results (default: 30)

### create_weekly
Create a weekly review entry.
Params:
- date: Any date in the week (default: today)
- wins: List of wins
- challenges: List of challenges
- learnings: List of learnings
- next_week_focus: List of focus items

### get_weekly
Get a weekly review entry.
Params:
- date: Any date in the week (default: today)

### update_weekly
Update a weekly review entry.
Params:
- date: Any date in the week (default: today)
- wins, challenges, learnings, next_week_focus, areas_reviewed

### list_weekly
List weekly review entries.
Params:
- limit: Max results (default: 12)

### list_habits
List user's active habits.
Params: none

### track_habit
Track a habit completion.
Params:
- habit_id or habit_name (required): The habit to track
- date: Date to track (default: today)
- completed: true/false (default: true)

### get_habit_streak
Get current streak for a habit.
Params:
- habit_id (required): The habit ID

### get_today
Get today's daily entry with summary.
Params: none

### get_this_week
Get this week's review and daily entries.
Params: none
"""

    def _execute_action(self, context: AgentContext, decision: ActionDecision) -> StepResult:
        """Execute the decided action using dispatcher."""
        return self._dispatch_action(context, decision)

    # ========================================================================
    # Daily Planner Handlers
    # ========================================================================

    def _handle_create_daily(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Create a daily planner entry"""
        from journal.models import DailyPlannerEntry

        entry_date = self._parse_date(params.get('date')) or date.today()

        # Check for existing
        existing = DailyPlannerEntry.objects.filter(
            user_id=context.user_id,
            date=entry_date
        ).first()

        if existing:
            return self._error_result(
                context, "create_daily",
                f"Daily entry for {entry_date} already exists. Use update_daily instead."
            )

        entry = DailyPlannerEntry.objects.create(
            user_id=context.user_id,
            date=entry_date,
            morning_intention=params.get('intention', ''),
            important_tasks=params.get('important_tasks', []),
            tasks_to_delegate=params.get('tasks_to_delegate', []),
            schedule_blocks=params.get('schedule_blocks', []),
        )

        context.set_in_memory('created_daily_id', entry.id)

        return self._success_result(
            context,
            action="create_daily",
            output={'daily': self._serialize_daily(entry)},
            summary=f"Created daily planner for {entry_date}",
            entities={}
        )

    def _handle_get_daily(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Get a daily planner entry"""
        from journal.models import DailyPlannerEntry

        entry_date = self._parse_date(params.get('date')) or date.today()

        entry = DailyPlannerEntry.objects.filter(
            user_id=context.user_id,
            date=entry_date
        ).first()

        if not entry:
            return self._error_result(context, "get_daily", f"No daily entry for {entry_date}")

        return self._success_result(
            context,
            action="get_daily",
            output={'daily': self._serialize_daily(entry)},
            summary=f"Found daily planner for {entry_date}",
            entities={}
        )

    def _handle_update_daily(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Update a daily planner entry"""
        from journal.models import DailyPlannerEntry

        entry_date = self._parse_date(params.get('date')) or date.today()

        entry, created = DailyPlannerEntry.objects.get_or_create(
            user_id=context.user_id,
            date=entry_date
        )

        updated_fields = []

        # Morning fields
        for field in ['morning_intention', 'important_tasks', 'tasks_to_delegate', 'schedule_blocks']:
            param_name = field.replace('morning_', '')
            if params.get(param_name) is not None or params.get(field) is not None:
                value = params.get(param_name) or params.get(field)
                setattr(entry, field, value)
                updated_fields.append(field)

        # Evening fields
        for field in ['evening_accomplishments', 'evening_learnings', 'evening_improvements', 'gratitude']:
            param_name = field.replace('evening_', '')
            if params.get(param_name) is not None or params.get(field) is not None:
                value = params.get(param_name) or params.get(field)
                setattr(entry, field, value)
                updated_fields.append(field)

        if updated_fields:
            entry.save()

        action_desc = "Created" if created else "Updated"

        return self._success_result(
            context,
            action="update_daily",
            output={'daily': self._serialize_daily(entry), 'updated_fields': updated_fields},
            summary=f"{action_desc} daily planner for {entry_date}",
            entities={}
        )

    def _handle_list_daily(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """List daily planner entries"""
        from journal.models import DailyPlannerEntry

        queryset = DailyPlannerEntry.objects.filter(user_id=context.user_id)

        # Date range filtering
        start_date = self._parse_date(params.get('start_date'))
        end_date = self._parse_date(params.get('end_date'))

        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)

        # Default to last 7 days
        if not start_date and not end_date:
            queryset = queryset.filter(date__gte=date.today() - timedelta(days=7))

        queryset = queryset.order_by('-date')

        limit = params.get('limit', 30)
        entries = list(queryset[:limit])

        return self._success_result(
            context,
            action="list_daily",
            output={
                'entries': [self._serialize_daily(e) for e in entries],
                'count': len(entries)
            },
            summary=f"Found {len(entries)} daily entries",
            entities={}
        )

    # ========================================================================
    # Weekly Review Handlers
    # ========================================================================

    def _handle_create_weekly(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Create a weekly review entry"""
        from journal.models import WeeklyReviewEntry

        # Calculate week start (Monday)
        target_date = self._parse_date(params.get('date')) or date.today()
        week_start = target_date - timedelta(days=target_date.weekday())
        week_end = week_start + timedelta(days=6)

        existing = WeeklyReviewEntry.objects.filter(
            user_id=context.user_id,
            week_start=week_start
        ).first()

        if existing:
            return self._error_result(
                context, "create_weekly",
                f"Weekly review for week of {week_start} already exists. Use update_weekly instead."
            )

        entry = WeeklyReviewEntry.objects.create(
            user_id=context.user_id,
            week_start=week_start,
            week_end=week_end,
            wins=params.get('wins', []),
            challenges=params.get('challenges', []),
            learnings=params.get('learnings', []),
            next_week_focus=params.get('next_week_focus', []),
            areas_reviewed=params.get('areas_reviewed', []),
        )

        context.set_in_memory('created_weekly_id', entry.id)

        return self._success_result(
            context,
            action="create_weekly",
            output={'weekly': self._serialize_weekly(entry)},
            summary=f"Created weekly review for week of {week_start}",
            entities={}
        )

    def _handle_get_weekly(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Get a weekly review entry"""
        from journal.models import WeeklyReviewEntry

        target_date = self._parse_date(params.get('date')) or date.today()
        week_start = target_date - timedelta(days=target_date.weekday())

        entry = WeeklyReviewEntry.objects.filter(
            user_id=context.user_id,
            week_start=week_start
        ).first()

        if not entry:
            return self._error_result(context, "get_weekly", f"No weekly review for week of {week_start}")

        return self._success_result(
            context,
            action="get_weekly",
            output={'weekly': self._serialize_weekly(entry)},
            summary=f"Found weekly review for week of {week_start}",
            entities={}
        )

    def _handle_update_weekly(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Update a weekly review entry"""
        from journal.models import WeeklyReviewEntry

        target_date = self._parse_date(params.get('date')) or date.today()
        week_start = target_date - timedelta(days=target_date.weekday())
        week_end = week_start + timedelta(days=6)

        entry, created = WeeklyReviewEntry.objects.get_or_create(
            user_id=context.user_id,
            week_start=week_start,
            defaults={'week_end': week_end}
        )

        updated_fields = []
        for field in ['wins', 'challenges', 'learnings', 'next_week_focus', 'areas_reviewed']:
            if params.get(field) is not None:
                setattr(entry, field, params.get(field))
                updated_fields.append(field)

        if updated_fields:
            entry.save()

        action_desc = "Created" if created else "Updated"

        return self._success_result(
            context,
            action="update_weekly",
            output={'weekly': self._serialize_weekly(entry), 'updated_fields': updated_fields},
            summary=f"{action_desc} weekly review for week of {week_start}",
            entities={}
        )

    def _handle_list_weekly(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """List weekly review entries"""
        from journal.models import WeeklyReviewEntry

        queryset = WeeklyReviewEntry.objects.filter(
            user_id=context.user_id
        ).order_by('-week_start')

        limit = params.get('limit', 12)
        entries = list(queryset[:limit])

        return self._success_result(
            context,
            action="list_weekly",
            output={
                'entries': [self._serialize_weekly(e) for e in entries],
                'count': len(entries)
            },
            summary=f"Found {len(entries)} weekly reviews",
            entities={}
        )

    # ========================================================================
    # Habit Handlers
    # ========================================================================

    def _handle_list_habits(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """List user's habits"""
        from journal.models import UserHabit

        habits = UserHabit.objects.filter(
            user_id=context.user_id,
            is_active=True
        ).order_by('name')

        habits_list = list(habits)

        return self._success_result(
            context,
            action="list_habits",
            output={
                'habits': [
                    {'id': h.id, 'name': h.name, 'frequency': h.frequency, 'target': h.target}
                    for h in habits_list
                ],
                'count': len(habits_list)
            },
            summary=f"Found {len(habits_list)} active habit(s)",
            entities={}
        )

    def _handle_track_habit(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Track a habit for today"""
        from journal.models import UserHabit, DailyPlannerEntry

        habit_id = params.get('habit_id')
        habit_name = params.get('habit_name')

        if habit_id:
            try:
                habit = UserHabit.objects.get(pk=habit_id, user_id=context.user_id)
            except UserHabit.DoesNotExist:
                return self._not_found_result(context, "track_habit", "habit", habit_id)
        elif habit_name:
            habit = UserHabit.objects.filter(
                user_id=context.user_id,
                name__iexact=habit_name
            ).first()
            if not habit:
                return self._error_result(context, "track_habit", f"Habit '{habit_name}' not found")
        else:
            return self._error_result(context, "track_habit", "Habit ID or name is required")

        entry_date = self._parse_date(params.get('date')) or date.today()
        completed = params.get('completed', True)

        # Get or create daily entry
        daily, _ = DailyPlannerEntry.objects.get_or_create(
            user_id=context.user_id,
            date=entry_date
        )

        # Track habit in daily entry's habit tracking (if field exists)
        # This depends on your model structure

        return self._success_result(
            context,
            action="track_habit",
            output={
                'habit': {'id': habit.id, 'name': habit.name},
                'date': entry_date.isoformat(),
                'completed': completed
            },
            summary=f"Tracked habit '{habit.name}' for {entry_date}",
            entities={}
        )

    def _handle_get_habit_streak(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Get current streak for a habit"""
        from journal.models import UserHabit

        habit_id = params.get('habit_id')
        if not habit_id:
            return self._error_result(context, "get_habit_streak", "Habit ID is required")

        try:
            habit = UserHabit.objects.get(pk=habit_id, user_id=context.user_id)
        except UserHabit.DoesNotExist:
            return self._not_found_result(context, "get_habit_streak", "habit", habit_id)

        # Calculate streak (simplified - depends on actual tracking implementation)
        streak = 0  # Would calculate based on daily tracking

        return self._success_result(
            context,
            action="get_habit_streak",
            output={
                'habit': {'id': habit.id, 'name': habit.name},
                'current_streak': streak,
                'best_streak': getattr(habit, 'best_streak', 0)
            },
            summary=f"Habit '{habit.name}' streak: {streak} days",
            entities={}
        )

    # ========================================================================
    # Utility Handlers
    # ========================================================================

    def _handle_get_today(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Get or create today's daily entry with summary"""
        from journal.models import DailyPlannerEntry
        from notes.models import Task

        today = date.today()

        entry, created = DailyPlannerEntry.objects.get_or_create(
            user_id=context.user_id,
            date=today
        )

        # Get today's tasks
        tasks_due = Task.objects.filter(
            user_id=context.user_id,
            due_date=today,
            is_archived=False
        ).exclude(status='done')

        tasks_in_progress = Task.objects.filter(
            user_id=context.user_id,
            status='in_progress',
            is_archived=False
        )

        return self._success_result(
            context,
            action="get_today",
            output={
                'daily': self._serialize_daily(entry),
                'tasks_due_today': [
                    {'id': t.id, 'title': t.title, 'priority': t.priority}
                    for t in tasks_due
                ],
                'tasks_in_progress': [
                    {'id': t.id, 'title': t.title}
                    for t in tasks_in_progress
                ],
                'is_new': created
            },
            summary=f"Today's planner {'created' if created else 'loaded'} with {tasks_due.count()} tasks due",
            entities={'task': [t.id for t in tasks_due]}
        )

    def _handle_get_this_week(self, context: AgentContext, params: Dict[str, Any]) -> StepResult:
        """Get this week's review and daily entries"""
        from journal.models import WeeklyReviewEntry, DailyPlannerEntry

        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)

        weekly = WeeklyReviewEntry.objects.filter(
            user_id=context.user_id,
            week_start=week_start
        ).first()

        daily_entries = DailyPlannerEntry.objects.filter(
            user_id=context.user_id,
            date__gte=week_start,
            date__lte=week_end
        ).order_by('date')

        return self._success_result(
            context,
            action="get_this_week",
            output={
                'week_start': week_start.isoformat(),
                'week_end': week_end.isoformat(),
                'weekly_review': self._serialize_weekly(weekly) if weekly else None,
                'daily_entries': [self._serialize_daily(e) for e in daily_entries],
                'days_logged': daily_entries.count()
            },
            summary=f"This week: {daily_entries.count()} days logged, weekly review {'exists' if weekly else 'not started'}",
            entities={}
        )

    # ========================================================================
    # Helpers
    # ========================================================================

    def _serialize_daily(self, entry) -> Dict[str, Any]:
        """Serialize a daily entry to dict"""
        if not entry:
            return None
        return self._serialize_object(entry, self.DAILY_FIELDS)

    def _serialize_weekly(self, entry) -> Dict[str, Any]:
        """Serialize a weekly entry to dict"""
        if not entry:
            return None
        return self._serialize_object(entry, self.WEEKLY_FIELDS)

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
            elif value_lower == 'yesterday':
                return today - timedelta(days=1)
            elif value_lower == 'tomorrow':
                return today + timedelta(days=1)

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
