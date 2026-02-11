"""
Agent Registry for Chat V4

Central registry for all specialized agents.
Provides agent lookup by type and action validation.
"""

import logging
from typing import Dict, List, Optional, Type

from .base import BaseAgent

logger = logging.getLogger(__name__)


class AgentRegistry:
    """
    Registry for specialized agents.

    Provides:
    - Agent lookup by type
    - Action validation
    - Lazy loading of agents
    """

    # Mapping of agent type -> agent class
    _agent_classes: Dict[str, Type[BaseAgent]] = {}

    # Cached agent instances
    _instances: Dict[str, BaseAgent] = {}

    @classmethod
    def register(cls, agent_class: Type[BaseAgent]) -> None:
        """
        Register an agent class.

        Args:
            agent_class: The agent class to register
        """
        agent_type = agent_class.AGENT_TYPE
        if not agent_type:
            raise ValueError(f"Agent class {agent_class.__name__} has no AGENT_TYPE")

        cls._agent_classes[agent_type] = agent_class
        logger.debug(f"Registered agent: {agent_type}")

    @classmethod
    def get(cls, agent_type: str) -> Optional[BaseAgent]:
        """
        Get an agent instance by type.

        Args:
            agent_type: The agent type (e.g., 'tasks', 'notes')

        Returns:
            Agent instance or None if not found
        """
        # Check cache first
        if agent_type in cls._instances:
            return cls._instances[agent_type]

        # Look up class and instantiate
        agent_class = cls._agent_classes.get(agent_type)
        if agent_class:
            instance = agent_class()
            cls._instances[agent_type] = instance
            return instance

        logger.warning(f"Agent '{agent_type}' not in registry")
        return None

    @classmethod
    def get_or_mock(cls, agent_type: str) -> BaseAgent:
        """
        Get an agent or a mock agent for testing.

        Args:
            agent_type: The agent type

        Returns:
            Agent instance or MockAgent
        """
        agent = cls.get(agent_type)
        if agent:
            return agent

        logger.info(f"Agent '{agent_type}' not in registry, using mock")
        return MockAgent(agent_type)

    @classmethod
    def has_agent(cls, agent_type: str) -> bool:
        """Check if an agent type is registered"""
        return agent_type in cls._agent_classes

    @classmethod
    def list_agents(cls) -> List[str]:
        """List all registered agent types"""
        return list(cls._agent_classes.keys())

    @classmethod
    def get_actions(cls, agent_type: str) -> List[str]:
        """
        Get available actions for an agent type.

        Args:
            agent_type: The agent type

        Returns:
            List of action names or empty list
        """
        agent_class = cls._agent_classes.get(agent_type)
        if agent_class:
            return agent_class.AVAILABLE_ACTIONS
        return []

    @classmethod
    def validate_action(cls, agent_type: str, action: str) -> bool:
        """
        Validate an action for an agent type.

        Args:
            agent_type: The agent type
            action: The action name

        Returns:
            True if valid, False otherwise
        """
        actions = cls.get_actions(agent_type)
        return action in actions

    @classmethod
    def get_all_actions(cls) -> Dict[str, List[str]]:
        """
        Get all actions for all agents.

        Returns:
            Dict of agent_type -> list of actions
        """
        return {
            agent_type: agent_class.AVAILABLE_ACTIONS
            for agent_type, agent_class in cls._agent_classes.items()
        }

    @classmethod
    def clear(cls) -> None:
        """Clear the registry (for testing)"""
        cls._agent_classes.clear()
        cls._instances.clear()

    @classmethod
    def clear_instances(cls) -> None:
        """Clear cached instances (for testing)"""
        cls._instances.clear()


class MockAgent(BaseAgent):
    """
    Mock agent for testing when real agent isn't available.
    """

    AVAILABLE_ACTIONS = ['*']  # Accepts any action

    def __init__(self, agent_type: str):
        self.AGENT_TYPE = agent_type
        # Don't call super().__init__() to avoid LLM initialization

    def get_specific_prompt(self) -> str:
        return f"Mock agent for {self.AGENT_TYPE}"

    def execute(self, context) -> 'StepResult':
        from ..state import StepResult

        return StepResult(
            step_id=context.step_id,
            agent_type=self.AGENT_TYPE,
            action=context.action,
            success=True,
            output={'mock': True, 'params': context.params},
            summary=f"Mock executed {context.action}",
            entities_affected={}
        )

    def validate_action(self, action: str) -> bool:
        return True


def register_all_agents():
    """
    Register all specialized agents.

    Called at module load to populate the registry.
    """
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

    agents = [
        TasksAgent,
        NotesAgent,
        ProjectsAgent,
        AreasAgent,
        InboxAgent,
        SearchAgent,
        TagsAgent,
        JournalAgent,
        ReviewAgent,
        OrganizeAgent,
        CalendarAgent,
    ]

    for agent_class in agents:
        AgentRegistry.register(agent_class)

    logger.info(f"Registered {len(agents)} agents")


# Auto-register on import
try:
    register_all_agents()
except ImportError as e:
    logger.warning(f"Could not register all agents: {e}")
