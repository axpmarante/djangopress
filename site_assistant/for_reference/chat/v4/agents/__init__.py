"""
V4 Agents Package

Contains:
- BaseAgent: Abstract base class for all agents
- Orchestration agents: Planner, Stepper, Finisher
- Specialized agents: Tasks, Notes, Projects, Areas, Inbox, Search, Tags, Journal, Review, Organize, Calendar
- AgentRegistry: Central registry for agent lookup
"""

from .base import BaseAgent, AgentContext
from .planner import PlannerAgent, QuickPlanner
from .stepper import StepperAgent, StepDecision, StepperRules
from .finisher import FinisherAgent, ResponseFormatter
from .registry import AgentRegistry, register_all_agents

# Specialized agents
from .tasks import TasksAgent
from .notes import NotesAgent
from .projects import ProjectsAgent
from .areas import AreasAgent
from .inbox import InboxAgent
from .search import SearchAgent
from .tags import TagsAgent
from .journal import JournalAgent
from .review import ReviewAgent
from .organize import OrganizeAgent
from .calendar import CalendarAgent

__all__ = [
    # Base
    'BaseAgent',
    'AgentContext',
    # Orchestration
    'PlannerAgent',
    'QuickPlanner',
    'StepperAgent',
    'StepDecision',
    'StepperRules',
    'FinisherAgent',
    'ResponseFormatter',
    # Registry
    'AgentRegistry',
    'register_all_agents',
    # Specialized agents
    'TasksAgent',
    'NotesAgent',
    'ProjectsAgent',
    'AreasAgent',
    'InboxAgent',
    'SearchAgent',
    'TagsAgent',
    'JournalAgent',
    'ReviewAgent',
    'OrganizeAgent',
    'CalendarAgent',
]
