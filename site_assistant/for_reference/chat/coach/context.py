"""
Coach Context Builder

Fetches journal-focused data for the executive coach:
- Goals (yearly, quarterly, monthly)
- Weekly planner status
- Daily planner status
- Habit completion
- Task overview
"""

from typing import Dict, Any, Optional
from datetime import date, timedelta
from django.utils import timezone


def fetch_coach_context(user) -> Dict[str, Any]:
    """
    Fetch all journal-related context for the coach.

    Returns dict with:
    - goals: {yearly, quarterly, monthly}
    - weekly_planner: current week's planner
    - daily_planner: today's planner
    - tasks: task counts and overdue info
    - habits: habit completion data
    """
    context = {
        'goals': fetch_goals_context(user),
        'weekly_planner': fetch_weekly_planner_context(user),
        'daily_planner': fetch_daily_planner_context(user),
        'tasks': fetch_tasks_context(user),
        'habits': fetch_habits_context(user),
    }

    return context


def fetch_goals_context(user) -> Dict[str, Any]:
    """Fetch active goals organized by type."""
    from journal.models import Goal

    today = date.today()
    current_quarter = (today.month - 1) // 3 + 1

    def goal_to_dict(g):
        return {
            'id': g.id,
            'title': g.title,
            'description': g.description[:200] if g.description else '',
            'progress': g.progress,
            'status': g.status,
            'key_results': g.key_results,
            'period': g.get_period_display(),
        }

    # Yearly goals
    yearly = Goal.objects.filter(
        user=user,
        goal_type='year',
        year=today.year,
        status='active'
    ).order_by('-progress', 'title')

    # Quarterly goals
    quarterly = Goal.objects.filter(
        user=user,
        goal_type='quarter',
        year=today.year,
        quarter=current_quarter,
        status='active'
    ).order_by('-progress', 'title')

    # Monthly goals
    monthly = Goal.objects.filter(
        user=user,
        goal_type='month',
        year=today.year,
        month=today.month,
        status='active'
    ).order_by('-progress', 'title')

    # Goals with no progress (stuck)
    stuck_goals = Goal.objects.filter(
        user=user,
        status='active',
        progress=0
    ).exclude(
        goal_type='year'  # Don't count yearly goals as "stuck" early in year
    ).order_by('created_at')

    return {
        'yearly': [goal_to_dict(g) for g in yearly],
        'quarterly': [goal_to_dict(g) for g in quarterly],
        'monthly': [goal_to_dict(g) for g in monthly],
        'stuck': [goal_to_dict(g) for g in stuck_goals[:5]],
        'counts': {
            'yearly': yearly.count(),
            'quarterly': quarterly.count(),
            'monthly': monthly.count(),
            'stuck': stuck_goals.count(),
        }
    }


def fetch_weekly_planner_context(user) -> Optional[Dict[str, Any]]:
    """Fetch current week's planner."""
    from journal.models import WeeklyPlannerEntry

    today = date.today()
    days_since_monday = today.weekday()
    week_start = today - timedelta(days=days_since_monday)

    try:
        entry = WeeklyPlannerEntry.objects.get(user=user, week_start=week_start)

        # Calculate priorities completion
        priorities = entry.top_priorities or []
        completed_priorities = sum(1 for p in priorities if p.get('completed', False))

        return {
            'id': entry.id,
            'week_start': entry.week_start.isoformat(),
            'week_end': entry.week_end.isoformat(),
            'week_display': entry.get_week_display(),
            'iso_week': entry.iso_week,
            # Planning
            'top_priorities': priorities,
            'priorities_completed': completed_priorities,
            'priorities_total': len(priorities),
            'week_plan': entry.week_plan,
            'projects_focus': entry.projects_focus,
            'habits_focus': entry.habits_focus,
            'weekly_goals': entry.weekly_goals,
            # Review
            'week_rating': entry.week_rating,
            'accomplishments': entry.accomplishments,
            'lessons_learned': entry.lessons_learned,
            # Status
            'is_planning_complete': entry.is_planning_complete,
            'is_review_complete': entry.is_review_complete,
            'completion_percentage': entry.get_completion_percentage(),
        }
    except WeeklyPlannerEntry.DoesNotExist:
        return None


def fetch_daily_planner_context(user) -> Optional[Dict[str, Any]]:
    """Fetch today's daily planner."""
    from journal.models import DailyPlannerEntry

    today = date.today()

    try:
        entry = DailyPlannerEntry.objects.get(user=user, date=today)

        return {
            'id': entry.id,
            'date': entry.date.isoformat(),
            'date_display': entry.date.strftime('%A, %B %d, %Y'),
            # Morning planning
            'important_tasks': entry.important_tasks,
            'tasks_to_delegate': entry.tasks_to_delegate,
            'intention': entry.intention,
            'good_day_reward': entry.good_day_reward,
            'schedule_blocks': entry.schedule_blocks,
            # Evening reflection
            'accomplishments': entry.accomplishments,
            'learnings': entry.learnings,
            'improvements': entry.improvements,
            # Habits
            'daily_habits': entry.daily_habits,
            'habits_completion': entry.get_habits_completion(),
            # Status
            'is_morning_complete': entry.is_morning_complete,
            'is_evening_complete': entry.is_evening_complete,
            'completion_percentage': entry.get_completion_percentage(),
        }
    except DailyPlannerEntry.DoesNotExist:
        return None


def fetch_tasks_context(user) -> Dict[str, Any]:
    """Fetch task overview for coaching context."""
    from tasks.models import Task

    today = date.today()
    week_end = today + timedelta(days=7)

    tasks = Task.objects.filter(user=user, is_archived=False)

    # Counts
    overdue = tasks.filter(
        due_date__date__lt=today,
        status__in=['todo', 'in_progress', 'waiting']
    )
    due_today = tasks.filter(due_date__date=today).exclude(status='done')
    due_this_week = tasks.filter(
        due_date__date__gt=today,
        due_date__date__lte=week_end
    ).exclude(status='done')
    in_progress = tasks.filter(status='in_progress')
    waiting = tasks.filter(status='waiting')

    # Overdue details (for coaching to call out)
    overdue_list = []
    for t in overdue.order_by('due_date')[:5]:
        days_overdue = (today - t.due_date.date()).days
        overdue_list.append({
            'id': t.id,
            'title': t.title,
            'days_overdue': days_overdue,
            'priority': t.priority,
        })

    return {
        'overdue': overdue.count(),
        'overdue_tasks': overdue_list,
        'due_today': due_today.count(),
        'due_this_week': due_this_week.count(),
        'in_progress': in_progress.count(),
        'waiting': waiting.count(),
        'total_pending': tasks.exclude(status='done').count(),
    }


def fetch_habits_context(user) -> Dict[str, Any]:
    """Fetch habit tracking context."""
    from journal.models import UserHabit, DailyPlannerEntry

    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    # Active habits
    habits = UserHabit.objects.filter(user=user, is_active=True).order_by('sort_order')

    # This week's completion data
    week_entries = DailyPlannerEntry.objects.filter(
        user=user,
        date__gte=week_start,
        date__lte=today
    )

    habit_stats = []
    for habit in habits:
        habit_id_str = str(habit.id)
        completed_days = 0
        total_days = 0

        for entry in week_entries:
            if habit_id_str in entry.daily_habits:
                total_days += 1
                if entry.daily_habits[habit_id_str].get('completed', False):
                    completed_days += 1

        habit_stats.append({
            'id': habit.id,
            'name': habit.name,
            'icon': habit.icon,
            'completed_this_week': completed_days,
            'days_tracked': total_days,
        })

    return {
        'habits': habit_stats,
        'active_count': habits.count(),
    }


def fetch_patterns_context(user) -> Dict[str, Any]:
    """
    Analyze patterns for coaching insights.

    Looks at:
    - Goal progress trends
    - Habit consistency
    - Task completion patterns
    - Planning consistency
    """
    from journal.models import Goal, DailyPlannerEntry, WeeklyPlannerEntry
    from tasks.models import Task

    today = date.today()
    thirty_days_ago = today - timedelta(days=30)

    patterns = {}

    # Planning consistency
    daily_entries = DailyPlannerEntry.objects.filter(
        user=user,
        date__gte=thirty_days_ago
    )
    total_days = (today - thirty_days_ago).days + 1
    morning_complete = daily_entries.filter(is_morning_complete=True).count()
    evening_complete = daily_entries.filter(is_evening_complete=True).count()

    patterns['planning'] = {
        'days_with_entries': daily_entries.count(),
        'possible_days': total_days,
        'morning_complete_rate': round(morning_complete / max(daily_entries.count(), 1) * 100),
        'evening_complete_rate': round(evening_complete / max(daily_entries.count(), 1) * 100),
    }

    # Goals without progress
    stalled_goals = Goal.objects.filter(
        user=user,
        status='active',
        progress=0,
        created_at__lt=timezone.now() - timedelta(days=14)  # Created > 2 weeks ago
    ).count()

    patterns['goals'] = {
        'stalled_count': stalled_goals,
    }

    # Tasks completed vs created (last 7 days)
    week_ago = today - timedelta(days=7)
    tasks_completed = Task.objects.filter(
        user=user,
        status='done',
        updated_at__date__gte=week_ago
    ).count()
    tasks_created = Task.objects.filter(
        user=user,
        created_at__date__gte=week_ago
    ).count()

    patterns['tasks'] = {
        'completed_last_week': tasks_completed,
        'created_last_week': tasks_created,
        'net': tasks_completed - tasks_created,  # Positive = making progress
    }

    return patterns
